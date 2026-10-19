"""
Admin REST API: prompts, models, stems, PDF analytics, and feedback inbox.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from PIL import Image

from app.admin_store import (
    JOBS_DIR,
    get_active_image_runtime,
    has_image_api_key,
    is_masked_secret,
    iter_job_metadata,
    load_feedback,
    load_models,
    load_settings,
    public_models_payload,
    public_settings_payload,
    save_models,
    save_settings,
    upsert_feedback,
)
from app.email_service import (
    SUPPORT_EMAIL,
    build_feedback_email_html,
    get_feedback_by_token,
    process_due_feedback_emails,
    schedule_feedback_for_job,
    send_feedback_email,
)
from app.grade_config import (
    GRADES_DIR,
    PromptNotFoundError,
    get_grade_config,
    get_grade_dir,
    get_questions_roots,
    get_topic_label,
    list_grades,
    read_job_metadata,
    write_job_metadata,
)

import os

router = APIRouter(prefix="/api/admin", tags=["admin"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STEM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,80}$")

REPO_ROOT = Path(__file__).resolve().parent.parent
FOODS_DIR = REPO_ROOT / "shared" / "icons" / "foods"
CHARACTERS_DIR = REPO_ROOT / "shared" / "characters"
PETS_DIR = REPO_ROOT / "shared" / "pets"

try:
    import rembg
    _HAS_REMBG = True
except Exception:
    _HAS_REMBG = False


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminCredentialsUpdate(BaseModel):
    old_password: Optional[str] = None
    email: str
    password: str


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except Exception:
                pass
    return total


def _safe_grade(grade_id: str) -> str:
    gid = (grade_id or "").strip()
    if not gid or "/" in gid or "\\" in gid or ".." in gid:
        raise HTTPException(400, "Invalid grade id")
    return gid


class PromptWrite(BaseModel):
    content: str = ""


class PromptCreate(BaseModel):
    name: str
    content: str = ""


class ActiveModelUpdate(BaseModel):
    provider: str
    model_id: str


class ProviderModelUpdate(BaseModel):
    provider: str
    model_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    cost_per_call: Optional[str] = None
    cost_notes: Optional[str] = None
    best_for: Optional[str] = None
    endpoint: Optional[str] = None


class ApiKeysUpdate(BaseModel):
    openrouter: Optional[str] = None
    openai: Optional[str] = None
    gemini: Optional[str] = None


class SettingsUpdate(BaseModel):
    feedback_delay_hours: Optional[int] = None
    support_email: Optional[str] = None
    public_base_url: Optional[str] = None
    smtp: Optional[Dict[str, Any]] = None
    imap: Optional[Dict[str, Any]] = None


class StemWrite(BaseModel):
    question: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    category: Optional[str] = None


class StemCreate(BaseModel):
    stem_id: str
    topic: str
    bank: str = "fallback"
    question: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    category: Optional[str] = None


class BulkReplace(BaseModel):
    find: str
    replace: str


class FeedbackSubmit(BaseModel):
    rating: Optional[int] = None
    message: str = ""
    name: str = ""


class ClaimDownload(BaseModel):
    email: str


# ── Prompts ──────────────────────────────────────────────────────────────────

@router.get("/grades")
def admin_grades():
    grades = []
    for entry in list_grades(enabled_only=False):
        gid = entry.get("id")
        prompts = []
        try:
            grade_dir = get_grade_dir(gid)
            pdir = grade_dir / "prompts"
            if pdir.is_dir():
                prompts = sorted(p.stem for p in pdir.glob("*.md"))
        except Exception:
            pass
        grades.append({**entry, "prompt_files": prompts})
    return {"grades": grades}


@router.get("/prompts/{grade_id}")
def list_prompts(grade_id: str):
    gid = _safe_grade(grade_id)
    try:
        grade_dir = get_grade_dir(gid)
    except Exception as exc:
        raise HTTPException(404, str(exc))
    prompts_dir = grade_dir / "prompts"
    items = []
    if prompts_dir.is_dir():
        for path in sorted(prompts_dir.glob("*.md")):
            items.append({
                "name": path.stem,
                "filename": path.name,
                "path": str(path.relative_to(grade_dir)),
                "bytes": path.stat().st_size,
                "is_master": path.stem == "question_image",
            })
    master = next((i for i in items if i["is_master"]), None)
    others = [i for i in items if not i["is_master"]]
    return {
        "grade_id": gid,
        "master": master,
        "prompts": items,
        "grade_prompts": others,
    }


@router.get("/prompts/{grade_id}/{name}")
def get_prompt(grade_id: str, name: str):
    path = _prompt_path(grade_id, name)
    return {
        "grade_id": grade_id,
        "name": path.stem,
        "filename": path.name,
        "content": path.read_text(encoding="utf-8"),
        "is_master": path.stem == "question_image",
    }


@router.put("/prompts/{grade_id}/{name}")
def save_prompt(grade_id: str, name: str, body: PromptWrite):
    path = _prompt_path(grade_id, name, must_exist=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.content, encoding="utf-8")
    _ensure_prompt_in_grade_config(grade_id, path.stem)
    return {"ok": True, "name": path.stem}


@router.post("/prompts/{grade_id}")
def create_prompt(grade_id: str, body: PromptCreate):
    name = re.sub(r"[^A-Za-z0-9_-]", "", (body.name or "").strip())
    if not name:
        raise HTTPException(400, "Prompt name is required")
    gid = _safe_grade(grade_id)
    try:
        grade_dir = get_grade_dir(gid)
    except Exception as exc:
        raise HTTPException(404, str(exc))
    path = grade_dir / "prompts" / f"{name}.md"
    if path.exists():
        raise HTTPException(409, f"Prompt '{name}' already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.content or f"# {name}\n\n", encoding="utf-8")
    _ensure_prompt_in_grade_config(gid, name)
    return {"ok": True, "name": name}


@router.delete("/prompts/{grade_id}/{name}")
def delete_prompt(grade_id: str, name: str):
    path = _prompt_path(grade_id, name)
    if path.stem == "question_image":
        raise HTTPException(400, "The master question_image prompt cannot be deleted.")
    path.unlink()
    return {"ok": True}


def _prompt_path(grade_id: str, name: str, *, must_exist: bool = True) -> Path:
    gid = _safe_grade(grade_id)
    clean = re.sub(r"[^A-Za-z0-9_-]", "", name)
    if not clean:
        raise HTTPException(400, "Invalid prompt name")
    try:
        grade_dir = get_grade_dir(gid)
    except Exception as exc:
        raise HTTPException(404, str(exc))
    path = grade_dir / "prompts" / f"{clean}.md"
    if must_exist and not path.is_file():
        raise HTTPException(404, f"Prompt '{clean}' not found for {gid}")
    return path


def _ensure_prompt_in_grade_config(grade_id: str, name: str) -> None:
    try:
        cfg_path = get_grade_dir(grade_id) / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        prompts = cfg.setdefault("prompts", {})
        if name not in prompts:
            prompts[name] = f"prompts/{name}.md"
            cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        pass


# ── Models ───────────────────────────────────────────────────────────────────

@router.get("/models")
def get_models():
    rt = get_active_image_runtime()
    payload = public_models_payload()
    payload["runtime"] = {
        "provider": rt["provider"],
        "provider_name": rt["provider_name"],
        "model": rt["model"],
        "endpoint": rt["endpoint"],
        "description": rt.get("description"),
        "cost_per_call": rt.get("cost_per_call"),
        "api_key_configured": has_image_api_key(),
    }
    return payload


@router.put("/models/active")
def set_active_model(body: ActiveModelUpdate):
    models = load_models()
    pid = body.provider.strip().lower()
    providers = models.get("providers") or {}
    if pid not in providers:
        raise HTTPException(400, f"Unknown provider '{pid}'")
    found = None
    for m in providers[pid].get("models") or []:
        m["active"] = m.get("id") == body.model_id
        if m.get("id") == body.model_id:
            found = m
    if not found:
        raise HTTPException(404, f"Model '{body.model_id}' not in {pid}")
    models["active_provider"] = pid
    models["active_model_id"] = body.model_id
    save_models(models)
    return get_models()


@router.put("/models/item")
def update_model_item(body: ProviderModelUpdate):
    models = load_models()
    pid = body.provider.strip().lower()
    provider = (models.get("providers") or {}).get(pid)
    if not provider:
        raise HTTPException(400, f"Unknown provider '{pid}'")
    found = None
    for m in provider.get("models") or []:
        if m.get("id") == body.model_id:
            found = m
            break
    if not found:
        raise HTTPException(404, "Model not found")
    for field in ("name", "description", "cost_per_call", "cost_notes", "best_for", "endpoint"):
        val = getattr(body, field)
        if val is not None:
            found[field] = val
    save_models(models)
    return get_models()


@router.put("/models/keys")
def update_api_keys(body: ApiKeysUpdate):
    incoming = body.dict(exclude_none=True)
    cleaned = {}
    current = (load_settings().get("api_keys") or {})
    for k, v in incoming.items():
        if v is None or is_masked_secret(v):
            continue
        cleaned[k] = v.strip()
    if cleaned:
        save_settings({"api_keys": {**current, **cleaned}})
    return public_settings_payload()


@router.get("/settings")
def get_settings():
    return public_settings_payload()


@router.put("/settings")
def update_settings(body: SettingsUpdate):
    patch: Dict[str, Any] = {}
    if body.feedback_delay_hours is not None:
        patch["feedback_delay_hours"] = max(1, min(int(body.feedback_delay_hours), 24 * 14))
    if body.support_email is not None:
        patch["support_email"] = body.support_email.strip() or SUPPORT_EMAIL
    if body.public_base_url is not None:
        patch["public_base_url"] = body.public_base_url.strip().rstrip("/")
    if body.smtp is not None:
        smtp = dict(body.smtp)
        if is_masked_secret(str(smtp.get("password") or "")):
            smtp.pop("password", None)
        patch["smtp"] = smtp
    if body.imap is not None:
        imap = dict(body.imap)
        if is_masked_secret(str(imap.get("password") or "")):
            imap.pop("password", None)
        patch["imap"] = imap
    if patch:
        save_settings(patch)
    return public_settings_payload()


# ── Stems ────────────────────────────────────────────────────────────────────

@router.get("/stems/{grade_id}")
def list_stems(grade_id: str, topic: str = "", bank: str = "", q: str = "", companion: str = "", category: str = ""):
    gid = _safe_grade(grade_id)
    items = _walk_stems(gid)
    topic_l = topic.strip().lower()
    bank_l = bank.strip().lower()
    comp_l = companion.strip().lower()
    cat_l = category.strip().lower()
    query = q.strip().lower()
    if topic_l:
        items = [s for s in items if s["topic"].lower() == topic_l]
    if bank_l:
        items = [s for s in items if s["bank"].lower() == bank_l]
    if comp_l and comp_l != "all":
        items = [s for s in items if s.get("companion_role", "").lower() == comp_l]
    if cat_l and cat_l != "all":
        items = [s for s in items if s.get("category", "").lower() == cat_l]
    if query:
        items = [
            s for s in items
            if query in s["stem_id"].lower()
            or query in (s.get("question") or "").lower()
            or query in (s.get("core_question") or "").lower()
            or query in s["topic"].lower()
            or query in (s.get("category") or "").lower()
            or query in (s.get("topic_label") or "").lower()
            or query in (s.get("companion_label") or "").lower()
        ]
    all_stems = _walk_stems(gid)
    topics = sorted({s["topic"] for s in all_stems})
    return {
        "grade_id": gid,
        "count": len(items),
        "topics": topics,
        "stems": items,
        "companions": [
            {"id": "all", "label": "All Companions"},
            {"id": "father", "label": "Dad"},
            {"id": "mother", "label": "Mum"},
            {"id": "sibling", "label": "Sibling"},
            {"id": "grandmother", "label": "Grandma"},
            {"id": "grandfather", "label": "Grandad"},
        ],
        "categories": [
            {"id": "all", "label": "All Categories"},
            {"id": "counting", "label": "Counting & Objects"},
            {"id": "time", "label": "Time & Clocks"},
            {"id": "geometry", "label": "Geometry & Angles"},
            {"id": "measurement", "label": "Measurement"},
            {"id": "fractions", "label": "Fractions"},
            {"id": "money", "label": "Money"},
            {"id": "statistics", "label": "Statistics"},
            {"id": "patterns", "label": "Patterns"},
            {"id": "general", "label": "General"},
        ],
    }


@router.get("/stems/{grade_id}/{bank}/{topic}/{stem_id}")
def get_stem(grade_id: str, bank: str, topic: str, stem_id: str):
    stem_dir = _stem_dir(grade_id, bank, topic, stem_id)
    meta_path = stem_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "Stem not found")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    q_file = stem_dir / (meta.get("question_file") or "question.txt")
    question = q_file.read_text(encoding="utf-8") if q_file.exists() else ""
    from app.stem_pipeline import infer_stem_category
    cat = (meta.get("category") or "").strip().lower() or infer_stem_category(meta, topic=topic, question=question)
    return {
        "grade_id": grade_id,
        "bank": bank,
        "topic": topic,
        "category": cat,
        "stem_id": stem_id,
        "question": question,
        "meta": meta,
        "path": str(stem_dir),
    }


@router.put("/stems/{grade_id}/{bank}/{topic}/{stem_id}")
def update_stem(grade_id: str, bank: str, topic: str, stem_id: str, body: StemWrite):
    stem_dir = _stem_dir(grade_id, bank, topic, stem_id)
    meta_path = stem_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "Stem not found")
    meta = body.meta or json.loads(meta_path.read_text(encoding="utf-8"))
    meta["stem_id"] = meta.get("stem_id") or stem_id
    meta["topic"] = meta.get("topic") or topic
    if body.category is not None:
        meta["category"] = body.category.strip().lower()
    q_name = meta.get("question_file") or "question.txt"
    (stem_dir / q_name).write_text(body.question, encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True}


@router.post("/stems/{grade_id}")
def create_stem(grade_id: str, body: StemCreate):
    gid = _safe_grade(grade_id)
    stem_id = (body.stem_id or "").strip()
    topic = re.sub(r"[^A-Za-z0-9_-]", "", (body.topic or "").strip())
    bank = (body.bank or "fallback").strip().lower()
    if bank not in ("primary", "fallback"):
        raise HTTPException(400, "bank must be primary or fallback")
    if not STEM_ID_RE.match(stem_id):
        raise HTTPException(400, "stem_id must be letters, numbers, underscore or hyphen")
    if not topic:
        raise HTTPException(400, "topic is required")
    try:
        grade_dir = get_grade_dir(gid)
    except Exception as exc:
        raise HTTPException(404, str(exc))
    stem_dir = grade_dir / "questions" / bank / topic / stem_id
    if stem_dir.exists():
        raise HTTPException(409, "A stem with that id already exists")
    stem_dir.mkdir(parents=True, exist_ok=True)
    meta = dict(body.meta or {})
    meta.setdefault("stem_id", stem_id)
    meta.setdefault("grade", gid.lower())
    meta.setdefault("topic", topic)
    meta["category"] = (body.category or meta.get("category") or "counting").strip().lower()
    meta.setdefault("question_file", "question.txt")
    meta.setdefault("image_file", "placeholder.png")
    meta.setdefault("status", "ready")
    meta.setdefault("validation", {"verified": True})
    meta.setdefault("personalisation", {
        "face_slots": ["child"],
        "template_adult_role": None,
        "allowed_adult_roles": [],
        "name_placeholders": {"user_name": "child"},
        "child_gender": "",
    })
    meta.setdefault("answer", {"type": "other", "correct": "", "options": []})
    (stem_dir / "question.txt").write_text(body.question, encoding="utf-8")
    (stem_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    img_path = stem_dir / "placeholder.png"
    if not img_path.exists():
        Image.new("RGB", (64, 64), (238, 242, 255)).save(img_path)
    return {"ok": True, "stem_id": stem_id, "bank": bank, "topic": topic}


@router.delete("/stems/{grade_id}/{bank}/{topic}/{stem_id}")
def delete_stem(grade_id: str, bank: str, topic: str, stem_id: str):
    stem_dir = _stem_dir(grade_id, bank, topic, stem_id)
    if not stem_dir.exists():
        raise HTTPException(404, "Stem not found")
    shutil.rmtree(stem_dir)
    return {"ok": True}


@router.post("/stems/{grade_id}/bulk-delete")
def bulk_delete_stems(grade_id: str):
    gid = _safe_grade(grade_id)
    deleted = 0
    for root in _question_roots(gid):
        if not root.is_dir():
            continue
        for topic_dir in list(root.iterdir()):
            if not topic_dir.is_dir():
                continue
            for stem_dir in list(topic_dir.iterdir()):
                if stem_dir.is_dir() and (stem_dir / "meta.json").exists():
                    shutil.rmtree(stem_dir)
                    deleted += 1
    return {"ok": True, "deleted": deleted}


@router.post("/stems/{grade_id}/bulk-replace")
def bulk_replace_stems(grade_id: str, body: BulkReplace):
    if not body.find:
        raise HTTPException(400, "find text is required")
    gid = _safe_grade(grade_id)
    updated = 0
    for stem in _walk_stems(gid, include_question=True):
        text = stem.get("question") or ""
        if body.find not in text:
            continue
        new_text = text.replace(body.find, body.replace)
        q_path = Path(stem["question_path"])
        q_path.write_text(new_text, encoding="utf-8")
        updated += 1
    return {"ok": True, "updated": updated}


def _question_roots(grade_id: str) -> List[Path]:
    try:
        return get_questions_roots(grade_id)
    except Exception:
        grade_dir = GRADES_DIR / grade_id
        roots = []
        for key in ("primary", "fallback"):
            p = grade_dir / "questions" / key
            if p.is_dir():
                roots.append(p)
        return roots


def _extract_companion_info(stem_id: str, meta: dict, question: str) -> tuple[str, str]:
    sid = stem_id.lower()
    q = question.lower()
    pers = meta.get("personalisation") or {}
    template_role = str(pers.get("template_adult_role") or "").lower()
    face_slots = [str(s).lower() for s in (pers.get("face_slots") or [])]

    if "_father_" in sid or "_dad_" in sid or "{father_name}" in q or template_role == "father" or "father" in face_slots:
        return "father", "Dad"
    if "_mother_" in sid or "_mum_" in sid or "{mother_name}" in q or template_role == "mother" or "mother" in face_slots:
        return "mother", "Mum"
    if "_sibling_" in sid or "{sibling_name}" in q or template_role == "sibling" or "sibling" in face_slots:
        return "sibling", "Sibling"
    if "_grandmother_" in sid or "_grandma_" in sid or "{grandmother_name}" in q or template_role == "grandmother" or "grandmother" in face_slots:
        return "grandmother", "Grandma"
    if "_grandfather_" in sid or "_grandad_" in sid or "{grandfather_name}" in q or template_role == "grandfather" or "grandfather" in face_slots:
        return "grandfather", "Grandad"
    return "solo", "Solo"


def _clean_core_question(question: str) -> str:
    """Strips repetitive robotic boilerplate to reveal the core mathematical problem."""
    text = question.strip()
    text = re.sub(r"^Look at the picture!\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^(?:\{user_name\}|[A-Z][a-z]+)\s+and\s+(?:\{[a-z_]+_name\}|his\s+\w+|her\s+\w+|their\s+\w+|[A-Z][a-z]+)\s*(?:solve|are solving|are working together on|work together on|work with|look at|are investigating|are exploring|are finding|investigate)[^:.!?]*[:.!?]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip() or question.strip()


def _walk_stems(grade_id: str, *, include_question: bool = True) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for root in _question_roots(grade_id):
        bank = root.name
        if not root.is_dir():
            continue
        for topic_dir in sorted(root.iterdir()):
            if not topic_dir.is_dir():
                continue
            for stem_dir in sorted(topic_dir.iterdir()):
                meta_path = stem_dir / "meta.json"
                if not stem_dir.is_dir() or not meta_path.is_file():
                    continue
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                q_file = stem_dir / (meta.get("question_file") or "question.txt")
                question = ""
                if include_question and q_file.exists():
                    try:
                        question = q_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        question = ""
                answer = meta.get("answer") or {}
                stem_id = meta.get("stem_id") or stem_dir.name
                topic_name = meta.get("topic") or topic_dir.name
                companion_role, companion_label = _extract_companion_info(stem_id, meta, question)
                core_q = _clean_core_question(question)
                topic_lbl = get_topic_label(topic_name, grade_id)
                from app.stem_pipeline import infer_stem_category
                cat = (meta.get("category") or "").strip().lower() or infer_stem_category(meta, topic=topic_name, question=question)

                items.append({
                    "stem_id": stem_id,
                    "topic": topic_name,
                    "topic_label": topic_lbl,
                    "category": cat,
                    "companion_role": companion_role,
                    "companion_label": companion_label,
                    "bank": bank,
                    "status": meta.get("status") or "",
                    "verified": bool((meta.get("validation") or {}).get("verified")),
                    "question": question,
                    "core_question": core_q,
                    "question_preview": (core_q[:180] + "…") if len(core_q) > 180 else core_q,
                    "correct": (answer.get("correct") if isinstance(answer, dict) else "") or "",
                    "question_path": str(q_file),
                })
    return items


def _stem_dir(grade_id: str, bank: str, topic: str, stem_id: str) -> Path:
    gid = _safe_grade(grade_id)
    bank_c = (bank or "").strip().lower()
    topic_c = re.sub(r"[^A-Za-z0-9_-]", "", topic)
    stem_c = re.sub(r"[^A-Za-z0-9_-]", "", stem_id)
    if bank_c not in ("primary", "fallback") or not topic_c or not stem_c:
        raise HTTPException(400, "Invalid stem path")
    try:
        grade_dir = get_grade_dir(gid)
    except Exception as exc:
        raise HTTPException(404, str(exc))
    stem_dir = grade_dir / "questions" / bank_c / topic_c / stem_c
    if not str(stem_dir.resolve()).startswith(str((grade_dir / "questions").resolve())):
        raise HTTPException(400, "Invalid stem path")
    return stem_dir


# ── PDF analytics ────────────────────────────────────────────────────────────

@router.get("/pdfs")
def list_pdfs(
    name: str = "",
    month: str = "",
    year: str = "",
    grade: str = "",
    num_questions: str = "",
    gender: str = "",
    location: str = "",
):
    jobs = iter_job_metadata()
    rows = []
    for meta in jobs:
        created = meta.get("created_at") or meta.get("completed_at") or meta.get("email_captured_at") or ""
        dt = _parse_dt(created)
        row = {
            "job_id": meta.get("job_id"),
            "student_name": meta.get("student_name") or "",
            "grade_id": meta.get("grade_id") or "",
            "grade_display": meta.get("grade_display") or meta.get("grade_id") or "",
            "topics": meta.get("selected_topics") or [],
            "question_count": int(meta.get("total_questions") or meta.get("num_questions") or 0),
            "gender": meta.get("gender") or "",
            "location": meta.get("location") or "",
            "status": meta.get("generation_status") or "",
            "has_pdf": bool(meta.get("has_pdf")),
            "pdf_filename": meta.get("pdf_filename") or "",
            "created_at": created,
            "year": dt.year if dt else None,
            "month": dt.month if dt else None,
            "download_email": meta.get("download_email") or "",
        }
        if not row["has_pdf"] and row["status"] not in ("complete", "completed"):
            continue
        if name and name.lower() not in row["student_name"].lower() and name.lower() not in (row["job_id"] or "").lower():
            continue
        if grade and grade != row["grade_id"] and grade.lower() not in (row["grade_display"] or "").lower():
            continue
        if gender and gender.lower() != (row["gender"] or "").lower():
            continue
        if location and location.lower() not in (row["location"] or "").lower():
            continue
        if year:
            try:
                if row["year"] != int(year):
                    continue
            except ValueError:
                continue
        if month:
            try:
                if row["month"] != int(month):
                    continue
            except ValueError:
                continue
        if num_questions:
            try:
                if row["question_count"] != int(num_questions):
                    continue
            except ValueError:
                continue
        rows.append(row)

    summary = _pdf_summary(rows)
    return {"count": len(rows), "pdfs": rows, "summary": summary}


@router.get("/pdfs/summary")
def pdf_summary():
    jobs = [m for m in iter_job_metadata() if m.get("has_pdf") or m.get("generation_status") in ("complete", "completed")]
    rows = []
    for meta in jobs:
        created = meta.get("created_at") or meta.get("completed_at") or ""
        dt = _parse_dt(created)
        rows.append({
            "student_name": meta.get("student_name") or "",
            "grade_id": meta.get("grade_id") or "",
            "grade_display": meta.get("grade_display") or "",
            "topics": meta.get("selected_topics") or [],
            "question_count": int(meta.get("total_questions") or meta.get("num_questions") or 0),
            "gender": meta.get("gender") or "",
            "location": meta.get("location") or "",
            "year": dt.year if dt else None,
            "month": dt.month if dt else None,
        })
    return _pdf_summary(rows)


def _pdf_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_grade: Dict[str, int] = {}
    by_gender: Dict[str, int] = {}
    by_location: Dict[str, int] = {}
    by_topic: Dict[str, int] = {}
    by_month: Dict[str, int] = {}
    q_counts: Dict[str, int] = {}
    for row in rows:
        g = row.get("grade_display") or row.get("grade_id") or "Unknown"
        by_grade[g] = by_grade.get(g, 0) + 1
        gender = (row.get("gender") or "Unspecified") or "Unspecified"
        by_gender[gender] = by_gender.get(gender, 0) + 1
        loc = (row.get("location") or "Unknown").strip() or "Unknown"
        by_location[loc] = by_location.get(loc, 0) + 1
        for t in row.get("topics") or []:
            by_topic[str(t)] = by_topic.get(str(t), 0) + 1
        if row.get("year") and row.get("month"):
            key = f"{row['year']}-{int(row['month']):02d}"
            by_month[key] = by_month.get(key, 0) + 1
        qc = str(row.get("question_count") or 0)
        q_counts[qc] = q_counts.get(qc, 0) + 1
    top_gender = max(by_gender.items(), key=lambda kv: kv[1])[0] if by_gender else None
    top_location = max(by_location.items(), key=lambda kv: kv[1])[0] if by_location else None
    return {
        "total_pdfs": len(rows),
        "by_grade": by_grade,
        "by_gender": by_gender,
        "by_location": by_location,
        "by_topic": by_topic,
        "by_month": by_month,
        "by_question_count": q_counts,
        "most_generated_gender": top_gender,
        "most_generated_location": top_location,
    }


def _parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", ""))
    except Exception:
        return None


# ── Feedback ─────────────────────────────────────────────────────────────────

@router.get("/feedback")
def list_feedback():
    items = load_feedback()
    items_sorted = sorted(
        items,
        key=lambda r: r.get("replied_at") or r.get("sent_at") or r.get("created_at") or "",
        reverse=True,
    )
    return {
        "support_email": SUPPORT_EMAIL,
        "count": len(items_sorted),
        "items": items_sorted,
    }


@router.get("/feedback/preview")
def preview_feedback_email(student_name: str = "Ayaan", grade_label: str = "Grade 1"):
    settings = load_settings()
    delay = int(settings.get("feedback_delay_hours") or 48)
    html = build_feedback_email_html(
        student_name=student_name,
        grade_label=grade_label,
        question_count=6,
        topics=["Addition", "Money"],
        feedback_url=f"{(settings.get('public_base_url') or 'http://localhost:5173').rstrip('/')}/feedback/preview",
        delay_days=max(1, round(delay / 24)),
    )
    return {"html": html, "from": SUPPORT_EMAIL}


@router.post("/feedback/{token}/send-now")
def send_feedback_now(token: str):
    rec = get_feedback_by_token(token)
    if not rec:
        raise HTTPException(404, "Feedback record not found")
    try:
        updated = send_feedback_email(rec)
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"ok": True, "item": updated}


@router.post("/feedback/process-due")
def process_due():
    sent = process_due_feedback_emails()
    return {"ok": True, "sent": sent}


# Public-ish helpers used by api_server as well

def claim_job_download(job_id: str, email_addr: str) -> dict:
    email_addr = (email_addr or "").strip().lower()
    if not EMAIL_RE.match(email_addr):
        raise HTTPException(400, "Please enter a valid email address")
    pdf_dir = JOBS_DIR / job_id / "generated_pdfs"
    if not pdf_dir.exists() or not list(pdf_dir.glob("*.pdf")):
        raise HTTPException(404, "No PDF has been generated for this job yet")
    record = schedule_feedback_for_job(job_id, email_addr)
    return {
        "ok": True,
        "email": email_addr,
        "pdf_url": f"/api/jobs/{job_id}/pdf",
        "feedback_scheduled_at": record.get("scheduled_at"),
        "support_email": SUPPORT_EMAIL,
    }


def submit_public_feedback(token: str, body: FeedbackSubmit) -> dict:
    rec = get_feedback_by_token(token)
    if not rec:
        raise HTTPException(404, "This feedback link is invalid or has expired.")
    rating = body.rating
    if rating is not None and not (1 <= int(rating) <= 5):
        raise HTTPException(400, "Rating must be 1–5")
    updated = {
        **rec,
        "status": "replied",
        "source": "web_form",
        "rating": int(rating) if rating is not None else rec.get("rating"),
        "message": (body.message or "").strip(),
        "respondent_name": (body.name or "").strip(),
        "replied_at": datetime.now().isoformat(),
    }
    upsert_feedback(updated)
    if rec.get("job_id"):
        try:
            write_job_metadata(rec["job_id"], {
                "feedback_status": "replied",
                "feedback_rating": updated.get("rating"),
            })
        except Exception:
            pass
    return {"ok": True, "support_email": SUPPORT_EMAIL}


# ── Admin Auth & Security ───────────────────────────────────────────────────

@router.post("/auth/login")
def admin_login(body: AdminLoginRequest):
    settings = load_settings()
    auth_config = settings.get("admin_auth") or {
        "email": os.environ.get("ADMIN_EMAIL", "admin@myintelibooks.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "admin123"),
    }
    input_email = (body.email or "").strip().lower()
    input_pass = body.password or ""
    expected_email = (auth_config.get("email") or "admin@myintelibooks.com").strip().lower()
    expected_pass = auth_config.get("password") or "admin123"

    if input_email == expected_email and input_pass == expected_pass:
        import hashlib
        tok = hashlib.sha256(f"{input_email}:{input_pass}:{datetime.now().date()}".encode()).hexdigest()[:24]
        return {
            "ok": True,
            "email": input_email,
            "token": f"adm_{tok}",
            "message": "Admin authorization granted",
        }
    raise HTTPException(status_code=401, detail="Invalid admin email or password. Default is admin@myintelibooks.com / admin123")


@router.post("/auth/change")
def admin_change_credentials(body: AdminCredentialsUpdate):
    settings = load_settings()
    auth_config = settings.get("admin_auth") or {
        "email": os.environ.get("ADMIN_EMAIL", "admin@myintelibooks.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "admin123"),
    }
    expected_pass = auth_config.get("password") or "admin123"
    if body.old_password and body.old_password != expected_pass:
        raise HTTPException(status_code=400, detail="Current password does not match")

    new_email = (body.email or "").strip().lower()
    if not EMAIL_RE.match(new_email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address")
    if len(body.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    settings["admin_auth"] = {
        "email": new_email,
        "password": body.password,
    }
    save_settings(settings)
    return {"ok": True, "email": new_email, "message": "Admin credentials successfully updated"}


# ── System Diagnostics & Health ──────────────────────────────────────────────

@router.get("/diagnostics")
def system_diagnostics():
    import platform
    import sys

    settings = load_settings()
    models = load_models()
    active_prov = models.get("active_provider", "openrouter")
    active_model_id = models.get("active_model_id", "openai/gpt-image-2")

    prov_data = models.get("providers", {}).get(active_prov, {})
    model_obj = next((m for m in prov_data.get("models", []) if m.get("id") == active_model_id), None)

    api_keys = settings.get("api_keys", {})
    keys_status = {
        "openrouter": bool(api_keys.get("openrouter") or os.environ.get("OPENROUTER_API_KEY")),
        "openai": bool(api_keys.get("openai") or os.environ.get("OPENAI_API_KEY")),
        "gemini": bool(api_keys.get("gemini") or os.environ.get("GEMINI_API_KEY")),
    }

    foods_count = len(list(FOODS_DIR.glob("*.svg"))) + len(list(FOODS_DIR.glob("*.png"))) if FOODS_DIR.exists() else 0
    chars_count = len(list(CHARACTERS_DIR.glob("*.png"))) if CHARACTERS_DIR.exists() else 0
    pets_count = len(list(PETS_DIR.glob("*.*"))) if PETS_DIR.exists() else 0

    jobs = list(iter_job_metadata())
    pdf_count = sum(1 for j in jobs if j.get("has_pdf") or j.get("generation_status") in ("complete", "completed"))
    storage_bytes = _dir_size(JOBS_DIR)

    grades_data = list_grades(enabled_only=False)
    total_stems = 0
    from app.stem_pipeline import list_ready_stems
    for g in grades_data:
        try:
            stems = list_ready_stems(g["id"])
            total_stems += len(stems)
        except Exception:
            pass

    return {
        "server": {
            "status": "online",
            "python_version": sys.version.split(" ")[0],
            "os": platform.system(),
            "rembg_available": _HAS_REMBG,
            "support_email": settings.get("support_email", SUPPORT_EMAIL),
        },
        "active_model": {
            "provider": active_prov,
            "provider_name": prov_data.get("name", active_prov),
            "model_id": active_model_id,
            "model_name": model_obj.get("name", active_model_id) if model_obj else active_model_id,
            "cost_per_call": model_obj.get("cost_per_call", "$0.04") if model_obj else "$0.04",
            "endpoint": model_obj.get("endpoint", "images") if model_obj else "images",
        },
        "keys": keys_status,
        "storage": {
            "total_jobs": len(jobs),
            "completed_pdfs": pdf_count,
            "storage_mb": round(storage_bytes / (1024 * 1024), 2),
        },
        "assets": {
            "food_icons": foods_count,
            "character_badges": chars_count,
            "pets": pets_count,
            "total_stems": total_stems,
            "grades_count": len(grades_data),
        },
    }


# ── Asset Library Explorer ───────────────────────────────────────────────────

@router.get("/assets")
def list_available_assets():
    foods = []
    if FOODS_DIR.exists():
        for f in sorted(FOODS_DIR.glob("*.*")):
            if f.suffix.lower() in (".svg", ".png"):
                name = f.stem.replace("_", " ").title()
                foods.append({
                    "filename": f.name,
                    "name": name,
                    "url": f"/api/assets/foods/{f.name}",
                    "type": f.suffix.replace(".", "").upper(),
                })

    characters = []
    if CHARACTERS_DIR.exists():
        for c in sorted(CHARACTERS_DIR.glob("*.png")):
            name = c.stem.replace("_", " ").title()
            characters.append({
                "filename": c.name,
                "name": name,
                "url": f"/api/assets/characters/{c.name}",
            })

    pets = []
    if PETS_DIR.exists():
        for p in sorted(PETS_DIR.glob("*.*")):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                name = p.stem.replace("_", " ").title()
                pets.append({
                    "filename": p.name,
                    "name": name,
                    "url": f"/api/assets/pets/{p.name}",
                })

    return {
        "foods": foods,
        "characters": characters,
        "pets": pets,
    }


# ── Recent Jobs Feed ─────────────────────────────────────────────────────────

@router.get("/jobs/recent")
def recent_jobs(limit: int = 20):
    all_jobs = list(iter_job_metadata())

    def _sort_key(m):
        return m.get("completed_at") or m.get("created_at") or ""

    sorted_jobs = sorted(all_jobs, key=_sort_key, reverse=True)[:limit]
    results = []
    for m in sorted_jobs:
        jid = m.get("job_id") or m.get("workbook_id") or ""
        pdf_file = m.get("pdf_filename") or f"{jid}.pdf"
        has_pdf = bool(m.get("has_pdf") or m.get("generation_status") in ("complete", "completed"))
        results.append({
            "job_id": jid,
            "student_name": m.get("student_name") or "Child",
            "gender": m.get("gender") or "Unspecified",
            "grade_id": m.get("grade_id") or "",
            "grade_display": m.get("grade_display") or m.get("grade_label") or m.get("grade_id") or "Primary",
            "selected_topics": m.get("selected_topics") or [],
            "total_questions": int(m.get("total_questions") or m.get("num_questions") or 6),
            "status": m.get("generation_status") or ("completed" if has_pdf else "pending"),
            "has_pdf": has_pdf,
            "pdf_filename": pdf_file,
            "pdf_url": f"/api/jobs/{jid}/pdf" if has_pdf else None,
            "completed_at": m.get("completed_at") or m.get("created_at") or "",
        })
    return {"jobs": results}
