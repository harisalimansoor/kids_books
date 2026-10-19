"""
app/api_server.py
───────────────────────────────────────────────────────────────────────────────
FastAPI backend for the Personalized Kids Maths Workbook React Application.
Provides endpoints for:
- Grades, topics, foods, hobbies registry and querying
- Stem eligibility and counting stats
- Isolated job runtime management and face uploads
- Background asynchronous AI workbook generation pipeline
- Job progress polling and live step status
- PDF download and image preview serving
"""

from __future__ import annotations

import base64
import concurrent.futures
import os
import sys
import threading

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from PIL import Image

# Ensure app and repo roots are in sys.path
PIPELINE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except Exception:
    pass

from app.pdf_generator import generate_pdf
from app.utils import create_safe_filename
from app.grade_config import (
    get_grade_topics,
    grade_select_options,
    is_grade_available,
    generate_job_id,
    get_runtime_dir,
    write_job_metadata,
    read_job_metadata,
    get_grade_features,
    get_backcover_image_path,
    GradeNotFoundError,
)
import stem_pipeline as _stem_pipeline
import image_generator as _image_generator_mod
import front_cover_generator as _front_cover_mod

ADULT_ROLES = _stem_pipeline.ADULT_ROLES
ROLE_DISPLAY = _stem_pipeline.ROLE_DISPLAY
display_name_for_role = _stem_pipeline.display_name_for_role
fill_question_text = _stem_pipeline.fill_question_text
list_ready_stems = _stem_pipeline.list_ready_stems
list_template_foods = _stem_pipeline.list_template_foods
list_template_hobbies = _stem_pipeline.list_template_hobbies
list_topics = _stem_pipeline.list_topics
mcq_from_meta = _stem_pipeline.mcq_from_meta
partition_by_interests = _stem_pipeline.partition_by_interests
partition_by_adult_roles = _stem_pipeline.partition_by_adult_roles
partition_by_child_gender = _stem_pipeline.partition_by_child_gender
select_stems = _stem_pipeline.select_stems
stems_for_available_roles = _stem_pipeline.stems_for_available_roles
topic_label = _stem_pipeline.topic_label
generate_mcq_ai = getattr(_stem_pipeline, "generate_mcq_ai", None)
substitute_favourite_foods = _stem_pipeline.substitute_favourite_foods

build_workbook_items_ai_generated = _image_generator_mod.build_workbook_items_ai_generated
generate_front_cover = _front_cover_mod.generate_front_cover
FrontCoverError = _front_cover_mod.FrontCoverError

job_states: Dict[str, Dict[str, Any]] = {}
job_lock = threading.Lock()
_feedback_stop = threading.Event()


def _feedback_loop():
    while not _feedback_stop.wait(60):
        try:
            from app.email_service import process_due_feedback_emails
            process_due_feedback_emails()
        except Exception as exc:
            print(f"[FEEDBACK] scheduler: {exc}")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    worker = threading.Thread(target=_feedback_loop, daemon=True, name="feedback-mailer")
    worker.start()
    yield
    _feedback_stop.set()


app = FastAPI(
    title="Kids Maths Workbook Generator API",
    description="Backend API powering the React UI for personalized workbook creation",
    version="2.0.0",
    lifespan=_lifespan,
)

# Enable CORS for React frontend (Vite default: http://localhost:5173, plus others)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.admin_router import (
    router as admin_router,
    ClaimDownload,
    FeedbackSubmit,
    claim_job_download,
    submit_public_feedback,
)
from app.email_service import SUPPORT_EMAIL, get_feedback_by_token

app.include_router(admin_router)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _stem_within_counting(stem: dict, max_n: int) -> bool:
    meta = stem.get("meta") or {}
    answer = meta.get("answer") or {}
    correct = str(answer.get("correct") or "").strip()
    nums = []
    if correct.isdigit():
        nums.append(int(correct))
    for g in meta.get("visual_groups") or []:
        try:
            nums.append(int(g.get("count") or 0))
        except (TypeError, ValueError):
            pass
        try:
            if g.get("circled_count") is not None:
                nums.append(int(g["circled_count"]))
        except (TypeError, ValueError):
            pass
    if not nums:
        return True
    return max(nums) <= int(max_n)


def _is_mcq_incomplete(it: dict) -> bool:
    opts_val = it.get("options")
    if not opts_val:
        return True
    if isinstance(opts_val, dict):
        raw = opts_val.get("options") or []
    elif isinstance(opts_val, (list, tuple)):
        raw = opts_val
    else:
        return True
    valid = [str(o).strip() for o in raw if str(o).strip() and str(o).strip() != "-"]
    return len(valid) < 2


# ── Pydantic Request Models ──────────────────────────────────────────────────

class StemStatsRequest(BaseModel):
    grade_id: str
    selected_topics: List[str] = Field(default_factory=list)
    counting_ability: int = 20
    available_adult_roles: List[str] = Field(default_factory=list)
    has_child_photo: bool = False
    has_sibling_photo: bool = False
    favourite_foods: List[str] = Field(default_factory=list)
    favourite_hobbies: List[str] = Field(default_factory=list)
    favourite_sports: List[str] = Field(default_factory=list)
    favourite_characters: List[str] = Field(default_factory=list)
    favourite_cartoons: List[str] = Field(default_factory=list)
    gender: str = "Boy"


class GenerateRequest(BaseModel):
    job_id: Optional[str] = None
    student_name: str
    gender: str
    subject: str = "Math"
    child_age: int = 6
    grade_id: str
    grade_label: Optional[str] = None
    family_names: Dict[str, str] = Field(default_factory=dict)
    favourite_foods: List[str] = Field(default_factory=list)
    favourite_hobbies: List[str] = Field(default_factory=list)
    favourite_sports: List[str] = Field(default_factory=list)
    favourite_characters: List[str] = Field(default_factory=list)
    favourite_cartoons: List[str] = Field(default_factory=list)
    selected_topics: List[str] = Field(default_factory=list)
    num_questions: int = 6
    include_images: bool = True
    counting_ability: int = 20
    fav_color: str = ""
    anything_else: str = ""
    location: str = ""


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    image_model = getattr(_image_generator_mod, "IMAGE_GEN_MODEL", "openai/gpt-image-2")
    provider = "openrouter"
    has_api_key = False
    try:
        from app.admin_store import get_active_image_runtime, has_image_api_key
        rt = get_active_image_runtime()
        image_model = rt.get("model") or image_model
        provider = rt.get("provider") or provider
        has_api_key = has_image_api_key()
    except Exception:
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        has_api_key = bool(api_key and api_key.strip() and not api_key.startswith("sk-or-v1-xxxx"))
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "api_key_configured": has_api_key,
        "image_model": image_model,
        "image_provider": provider,
    }


_GRADE_DETAIL_CACHE: dict[str, dict] = {}


@app.get("/api/grades")
def get_grades():
    options = grade_select_options()
    return {
        "grades": options,
    }


@app.get("/api/grade/{grade_id}")
def get_grade_detail(grade_id: str):
    if grade_id in _GRADE_DETAIL_CACHE:
        return _GRADE_DETAIL_CACHE[grade_id]

    available = is_grade_available(grade_id)
    if not available:
        res = {
            "grade_id": grade_id,
            "available": False,
            "topics": [],
            "available_foods": [],
            "available_hobbies": [],
            "features": {},
        }
        _GRADE_DETAIL_CACHE[grade_id] = res
        return res

    try:
        topic_ids = get_grade_topics(grade_id) or list_topics(grade_id)
        foods = list_template_foods(grade_id)
        hobbies = list_template_hobbies(grade_id)
        features = get_grade_features(grade_id)
        topics = [{"id": t, "label": topic_label(t, grade_id)} for t in topic_ids]
        res = {
            "grade_id": grade_id,
            "available": True,
            "topics": topics,
            "available_foods": foods,
            "available_hobbies": hobbies,
            "features": features,
        }
        _GRADE_DETAIL_CACHE[grade_id] = res
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/stems/stats")
def calculate_stem_stats(req: StemStatsRequest):
    if not is_grade_available(req.grade_id):
        return {
            "available": False,
            "ready_count": 0,
            "primary_count": 0,
            "fallback_count": 0,
            "eligible_count": 0,
            "matched_interests_count": 0,
        }

    pool = list_ready_stems(req.grade_id, topics=req.selected_topics or None)
    counted = [s for s in pool if _stem_within_counting(s, req.counting_ability)]
    n_primary = sum(1 for s in counted if s.get("bank") == "primary")
    n_fallback = sum(1 for s in counted if s.get("bank") == "fallback")

    adult_roles_set = set(req.available_adult_roles)
    eligible = stems_for_available_roles(
        counted,
        adult_roles_set,
        has_child_photo=req.has_child_photo,
        has_sibling_photo=req.has_sibling_photo,
    ) if req.has_child_photo else []

    matched, _ = partition_by_interests(
        eligible,
        favourite_foods=req.favourite_foods,
        favourite_hobbies=req.favourite_hobbies,
    )

    return {
        "available": True,
        "ready_count": len(counted),
        "primary_count": n_primary,
        "fallback_count": n_fallback,
        "eligible_count": len(eligible),
        "matched_interests_count": len(matched),
    }


@app.post("/api/upload-face")
async def upload_face(
    role: str = Form(...),
    job_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    if not job_id:
        job_id = generate_job_id()

    uploads_dir = get_runtime_dir(job_id, "uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Clean up any existing upload files for this role first
    for old_p in uploads_dir.glob(f"{role}_face.*"):
        try:
            old_p.unlink()
        except OSError:
            pass

    content = await file.read()
    file_ext = Path(file.filename or "image.png").suffix.lower() or ".png"

    # Support all image formats (PNG, JPG, JPEG, WEBP, HEIC, HEIF, BMP, TIFF, GIF, etc.)
    warning = None
    width, height = 0, 0
    saved_as_png = False
    target_path = uploads_dir / f"{role}_face.png"

    try:
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception:
            pass

        from PIL import ImageOps
        img = Image.open(BytesIO(content))
        # Automatically fix mobile photo rotation based on EXIF orientation
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        width, height = img.size

        # Normalize to standard PNG for universal browser preview and AI model compatibility
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            norm_img = img.convert("RGBA")
        else:
            norm_img = img.convert("RGB")

        norm_img.save(target_path, format="PNG")
        saved_as_png = True

        if min(width, height) < 150:
            warning = f"Low resolution ({width}x{height}px). A clearer photo will produce better character resemblance."
    except Exception as parse_err:
        print(f"[UPLOAD] Pillow parse notice for {file.filename}: {parse_err}. Writing raw bytes.")
        target_path = uploads_dir / f"{role}_face{file_ext}"
        target_path.write_bytes(content)

    return {
        "job_id": job_id,
        "role": role,
        "filename": target_path.name,
        "path": str(target_path),
        "preview_url": f"/api/jobs/{job_id}/preview/uploads/{target_path.name}",
        "width": width,
        "height": height,
        "warning": warning,
    }


@app.delete("/api/jobs/{job_id}/faces/{role}")
def delete_face(job_id: str, role: str):
    uploads_dir = get_runtime_dir(job_id, "uploads")
    if not uploads_dir.exists():
        return {"status": "ok", "deleted": False}

    deleted = False
    for p in uploads_dir.glob(f"{role}_face.*"):
        try:
            p.unlink()
            deleted = True
        except OSError:
            pass

    return {"status": "ok", "deleted": deleted}


@app.get("/api/jobs/{job_id}/faces")
def list_uploaded_faces(job_id: str):
    uploads_dir = get_runtime_dir(job_id, "uploads")
    if not uploads_dir.exists():
        return {"faces": []}

    faces = []
    for p in uploads_dir.glob("*_face.*"):
        role = p.stem.replace("_face", "")
        role_label = ROLE_DISPLAY.get(role, "Pet 1" if role == "pet_1" else "Pet 2" if role == "pet_2" else role.title())
        faces.append({
            "role": role,
            "role_label": role_label,
            "filename": p.name,
            "preview_url": f"/api/jobs/{job_id}/preview/uploads/{p.name}",
        })
    return {"faces": faces}


# ── Pipeline Generation Background Worker ────────────────────────────────────

def _run_generation_task(job_id: str, req_data: dict):
    with job_lock:
        state = job_states.setdefault(job_id, {})
        state["status"] = "in_progress"
        state["phase"] = "preparing"
        state["progress"] = 0.05
        state["message"] = "Initializing workbook configuration..."
        state["items"] = []
        state["skipped"] = []
        state["error"] = None
        state["pdf_ready"] = False

    grade_id = req_data["grade_id"]
    student_name = (req_data.get("student_name") or "").strip()
    gender = (req_data.get("gender") or "").strip()

    # Intelligent name-based fallback if gender was somehow left unselected
    if not gender or gender.lower() == "select":
        lower_name = student_name.lower()
        female_names = {
            "alia", "aaliyah", "maya", "emma", "olivia", "sophia", "ava", "isabella",
            "mia", "amelia", "harper", "evelyn", "charlotte", "lily", "emily", "chloe",
            "zara", "daisy", "grace", "zoe", "lucy", "ruby", "alice", "ivy", "ella",
            "layla", "freya", "florence", "hannah", "sarah", "leila", "anaya", "fatima", "aisha"
        }
        if lower_name in female_names or lower_name.endswith(("ia", "lla", "ina", "ette")):
            gender = "Girl"
        else:
            gender = "Boy"

    family_names = {k: v for k, v in req_data.get("family_names", {}).items() if v}
    favourite_foods = req_data.get("favourite_foods", [])
    favourite_hobbies = req_data.get("favourite_hobbies", [])
    favourite_sports = req_data.get("favourite_sports", [])
    favourite_characters = req_data.get("favourite_characters", [])
    favourite_cartoons = req_data.get("favourite_cartoons", [])
    selected_topics = req_data.get("selected_topics", [])
    num_questions = int(req_data.get("num_questions", 6))

    include_images = bool(req_data.get("include_images", True))
    counting_ability = int(req_data.get("counting_ability", 20))
    fav_color = req_data.get("fav_color", "").strip()
    anything_else = req_data.get("anything_else", "").strip()
    location = (req_data.get("location") or "").strip()
    grade_label = req_data.get("grade_label") or grade_id
    subject = req_data.get("subject", "Math") or "Math"

    # Bidirectional family name aliases
    if "father" in family_names and "dad" not in family_names:
        family_names["dad"] = family_names["father"]
    elif "dad" in family_names and "father" not in family_names:
        family_names["father"] = family_names["dad"]
    if "mother" in family_names and "mum" not in family_names:
        family_names["mum"] = family_names["mother"]
    elif "mum" in family_names and "mother" not in family_names:
        family_names["mother"] = family_names["mum"]

    try:
        # Resolve saved face paths
        uploads_dir = get_runtime_dir(job_id, "uploads")
        saved_face_paths: Dict[str, str] = {}
        if uploads_dir.exists():
            for p in uploads_dir.glob("*_face.*"):
                role = p.stem.replace("_face", "").lower().strip()
                saved_face_paths[role] = str(p)

        ROLE_ALIASES = {
            "dad": "father",
            "father": "father",
            "mum": "mother",
            "mom": "mother",
            "mother": "mother",
            "grandma": "grandmother",
            "grandmother": "grandmother",
            "grandad": "grandfather",
            "grandpa": "grandfather",
            "grandfather": "grandfather",
            "uncle": "uncle",
            "aunt": "aunt",
            "brother": "brother",
            "sister": "sister",
            "sibling": "sibling",
        }

        available_adult_roles = set()
        for r in saved_face_paths.keys():
            canonical = ROLE_ALIASES.get(r, r)
            if canonical in ADULT_ROLES or canonical in ("mother", "father", "grandmother", "grandfather", "uncle", "aunt"):
                available_adult_roles.add(canonical)

        sibling_roles = ("sibling", "brother", "sister")
        has_child_photo = any(r in saved_face_paths for r in ("user", "child"))
        has_sibling_photo = any(r in saved_face_paths for r in sibling_roles)
        if has_sibling_photo:
            available_adult_roles.update(r for r in sibling_roles if r in saved_face_paths)

        # Resolve pets from both req_data and saved upload files
        raw_pets = req_data.get("pets") or []
        pet_meta = {}
        for idx, p in enumerate(raw_pets, start=1):
            if isinstance(p, dict):
                pid = (p.get("id") or f"pet_{idx}").strip()
                pet_meta[pid] = p

        # Map common single pet alias uploads (e.g. pet_face.* or dog_face.*) to pet_1 if pet_1 not set
        for alias_key in ("pet", "dog", "cat", "puppy", "kitten"):
            if alias_key in saved_face_paths and "pet_1" not in saved_face_paths:
                saved_face_paths["pet_1"] = saved_face_paths[alias_key]

        pets_info = []
        seen_pet_ids = set()

        for role_key in ("pet_1", "pet_2"):
            img_path = saved_face_paths.get(role_key)
            meta = pet_meta.get(role_key, {})
            p_name = (meta.get("name") or "").strip()
            p_type = (meta.get("type") or "Pet").strip()
            if img_path or p_name:
                seen_pet_ids.add(role_key)
                pets_info.append({
                    "id": role_key,
                    "name": p_name or (p_type if p_type and p_type != "Pet" else "My Pet"),
                    "type": p_type,
                    "image_path": img_path,
                })

        for idx, p in enumerate(raw_pets, start=1):
            if isinstance(p, dict):
                pid = (p.get("id") or f"pet_{idx}").strip()
                if pid not in seen_pet_ids:
                    p_name = (p.get("name") or "").strip()
                    p_type = (p.get("type") or "Pet").strip()
                    img_path = saved_face_paths.get(pid)
                    if p_name or img_path:
                        seen_pet_ids.add(pid)
                        pets_info.append({
                            "id": pid,
                            "name": p_name or (p_type if p_type and p_type != "Pet" else "My Pet"),
                            "type": p_type,
                            "image_path": img_path,
                        })

        print(f"[JOB {job_id}] Resolved {len(pets_info)} pets: {[(p['name'], p['type'], bool(p['image_path'])) for p in pets_info]}")

        # Write initial metadata
        write_job_metadata(job_id, {
            "workbook_id": job_id,
            "created_at": datetime.now().isoformat(),
            "student_name": student_name,
            "gender": gender,
            "grade_id": grade_id,
            "grade_display": grade_label,
            "selected_topics": selected_topics,
            "num_questions": num_questions,
            "location": location,
            "generation_status": "in_progress",
        })

        with job_lock:
            state["phase"] = "selecting_stems"
            state["progress"] = 0.15
            state["message"] = f"Filtering & selecting best curriculum stems for {student_name}..."

        # Query and filter stems strictly within counting ability
        pool = list_ready_stems(grade_id, topics=selected_topics or None)
        counted_pool = [s for s in pool if _stem_within_counting(s, counting_ability)]
        if counted_pool:
            pool = counted_pool
        else:
            all_grade = list_ready_stems(grade_id)
            pool = [s for s in all_grade if _stem_within_counting(s, counting_ability)]

        if include_images:
            role_filtered = stems_for_available_roles(
                pool,
                available_adult_roles,
                has_child_photo=has_child_photo,
                has_sibling_photo=has_sibling_photo,
                require_personalizable=False,
            )
            if role_filtered:
                pool = role_filtered
            elif has_child_photo:
                # If topic-restricted role filter was too tight, search all grade topics within counting limit
                all_grade = list_ready_stems(grade_id)
                all_grade_counted = [s for s in all_grade if _stem_within_counting(s, counting_ability)]
                role_filtered_all = stems_for_available_roles(
                    all_grade_counted,
                    available_adult_roles,
                    has_child_photo=has_child_photo,
                    has_sibling_photo=has_sibling_photo,
                    require_personalizable=False,
                )
                if role_filtered_all:
                    pool = role_filtered_all

        if not pool:
            raise ValueError("No matching stems found for the selected grade, counting range, and family photos.")

        # Gender match: strictly prioritize same_gender stems first
        same_gender, other_gender = partition_by_child_gender(pool, gender)
        chosen: List[Dict[str, Any]] = []

        # 1. First priority: Stems matching child gender
        if same_gender:
            uses_adult_same, child_only_same = partition_by_adult_roles(same_gender, available_adult_roles)
            if uses_adult_same and len(chosen) < num_questions:
                chosen.extend(select_stems(
                    uses_adult_same,
                    min(len(uses_adult_same), num_questions - len(chosen)),
                    favourite_foods=favourite_foods,
                    favourite_hobbies=favourite_hobbies,
                    strict_interests=False,
                    bank_balance=True,
                ))
            if child_only_same and len(chosen) < num_questions:
                chosen.extend(select_stems(
                    child_only_same,
                    min(len(child_only_same), num_questions - len(chosen)),
                    favourite_foods=favourite_foods,
                    favourite_hobbies=favourite_hobbies,
                    strict_interests=False,
                    bank_balance=True,
                ))

        # 2. Second priority: Backfill remaining slots from other_gender if needed
        if len(chosen) < num_questions and other_gender:
            chosen_ids = {s["stem_id"] for s in chosen}
            remaining_other = [s for s in other_gender if s["stem_id"] not in chosen_ids]
            if remaining_other:
                uses_adult_other, child_only_other = partition_by_adult_roles(remaining_other, available_adult_roles)
                if uses_adult_other and len(chosen) < num_questions:
                    chosen.extend(select_stems(
                        uses_adult_other,
                        min(len(uses_adult_other), num_questions - len(chosen)),
                        favourite_foods=favourite_foods,
                        favourite_hobbies=favourite_hobbies,
                        strict_interests=False,
                        bank_balance=True,
                    ))
                if child_only_other and len(chosen) < num_questions:
                    chosen.extend(select_stems(
                        child_only_other,
                        min(len(child_only_other), num_questions - len(chosen)),
                        favourite_foods=favourite_foods,
                        favourite_hobbies=favourite_hobbies,
                        strict_interests=False,
                        bank_balance=True,
                    ))

        # If still short (e.g. strict topic filter had too few stems), backfill from wider grade stems
        if len(chosen) < num_questions:
            chosen_ids = {s["stem_id"] for s in chosen}
            wider_pool = list_ready_stems(grade_id)
            wider_pool = [s for s in wider_pool if _stem_within_counting(s, counting_ability)]
            if include_images:
                wider_pool = stems_for_available_roles(
                    wider_pool,
                    available_adult_roles,
                    has_child_photo=has_child_photo,
                    has_sibling_photo=has_sibling_photo,
                    require_personalizable=False,
                )
            remaining_wider = [s for s in wider_pool if s["stem_id"] not in chosen_ids]
            if remaining_wider:
                fill = select_stems(
                    remaining_wider,
                    num_questions - len(chosen),
                    strict_interests=False,
                    bank_balance=False,
                )
                chosen.extend(fill)

        if not chosen:
            raise ValueError("Could not select suitable stems for workbook generation.")

        # ── Launch Front Cover Generation Concurrently in Background ────────
        cover_future = None
        cover_executor = None
        cover_api_key = ""
        try:
            from app.admin_store import has_image_api_key
            if has_image_api_key():
                cover_api_key = "configured"
        except Exception:
            cover_api_key = getattr(_front_cover_mod, "OPENROUTER_API_KEY", "")
        if cover_api_key and cover_api_key.strip():
            cover_category = ", ".join(sorted({topic_label(t, grade_id) for t in (selected_topics or [])})) or grade_label
            cover_topics = selected_topics or []
            cover_topic_labels = [topic_label(t, grade_id) for t in cover_topics]
            cover_catalog = [
                topic_label(t, grade_id) for t in get_grade_topics(grade_id)
                if "mix" not in str(t).lower()
            ]
            cover_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            cover_future = cover_executor.submit(
                generate_front_cover,
                child_name=student_name,
                category=cover_category,
                face_paths=saved_face_paths,
                family_names=family_names,
                subject=subject,
                selected_topics=cover_topic_labels,
                all_available_topics=cover_catalog,
                grade=grade_label,
                grade_id=grade_id,
                job_id=job_id,
                theme_color=fav_color,
                pets=pets_info,
            )

        items: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        if include_images:
            with job_lock:
                state["phase"] = "generating_images"
                state["progress"] = 0.25
                state["message"] = f"Generating AI illustrations for {len(chosen)} math questions in parallel..."

            def on_progress_cb(i: int, total: int, stem_id: str):
                frac = 0.25 + (0.50 * (i / max(total, 1)))
                with job_lock:
                    state["progress"] = round(frac, 2)
                    state["message"] = f"Generated illustration {i}/{total} ({stem_id})..."

            items, skipped = build_workbook_items_ai_generated(
                chosen,
                user_name=student_name,
                family_names=family_names,
                face_paths=saved_face_paths,
                child_gender=gender,
                out_dir=get_runtime_dir(job_id, "generated_images"),
                on_progress=on_progress_cb,
                grade_id=grade_id,
                max_workers=4,
                fav_color=fav_color,
                favourite_foods=favourite_foods,
                favourite_sports=favourite_sports,
                favourite_hobbies=favourite_hobbies,
                favourite_characters=favourite_characters,
                favourite_cartoons=favourite_cartoons,
            )
        else:
            for stem in chosen:
                role = stem["template_adult_role"]
                q_text = fill_question_text(
                    stem["question_template"],
                    user_name=student_name,
                    adult_role=role or "mother",
                    family_names=family_names,
                    child_gender=gender,
                )
                custom_meta = stem.get("meta") or {}

                sq_dict = None
                try:
                    from app.math_visual_engine import infer_structured_question
                    sq_dict = infer_structured_question(
                        q_text,
                        meta=custom_meta,
                        grade_id=grade_id,
                        stem_id=stem["stem_id"],
                    ).to_dict()
                except Exception:
                    pass

                items.append({
                    "stem_id": stem["stem_id"],
                    "topic": stem["topic"],
                    "topic_label": topic_label(stem["topic"], grade_id),
                    "adult_role": role,
                    "adult_name": display_name_for_role(role, family_names) if role else "",
                    "question": q_text,
                    "bank": stem.get("bank") or "",
                    "image_path": None,
                    "options": mcq_from_meta(custom_meta, question=q_text),
                    "correct": str((custom_meta.get("answer") or {}).get("correct") or ""),
                    "structured_math": sq_dict,
                })

        if not items:
            raise ValueError("All questions were skipped or failed to generate.")

        # MCQ Verification / Generation
        with job_lock:
            state["phase"] = "verifying_mcq"
            state["progress"] = 0.78
            state["message"] = "Verifying math questions and multiple-choice options..."

        if generate_mcq_ai:
            for it in items:
                if _is_mcq_incomplete(it):
                    ai_mcq = generate_mcq_ai(it["question"])
                    if ai_mcq and ai_mcq.get("options"):
                        it["options"] = ai_mcq
                        it["correct"] = ai_mcq.get("correct_answer", "")

        # Collect Front Cover
        cover_image_path: Optional[str] = None
        if cover_future is not None:
            with job_lock:
                state["phase"] = "finalizing_cover"
                state["progress"] = 0.85
                state["message"] = "Finalizing personalized AI front cover..."
            try:
                cov_p = cover_future.result(timeout=120)
                cover_image_path = str(cov_p)
            except Exception as fc_err:
                print(f"[COVER ERROR]: {fc_err}")
                cover_image_path = None
            finally:
                if cover_executor:
                    cover_executor.shutdown(wait=False)

        # PDF Compilation
        with job_lock:
            state["phase"] = "compiling_pdf"
            state["progress"] = 0.90
            state["message"] = "Compiling the A4 portrait workbook..."

        questions = [f"{i}. {it['question']}" for i, it in enumerate(items, start=1)]
        image_paths = [it.get("image_path") for it in items] if include_images else None
        question_topics = [it["topic_label"] for it in items]
        question_adults = [it["adult_name"] for it in items]
        question_options = [it["options"] for it in items]
        topic_header = ", ".join(sorted({it["topic_label"] for it in items}))

        extras = []
        if favourite_foods:
            extras.append("Foods: " + ", ".join(favourite_foods))
        if favourite_sports:
            extras.append("Sports: " + ", ".join(favourite_sports))
        if favourite_hobbies:
            extras.append("Hobbies: " + ", ".join(favourite_hobbies))
        if favourite_characters:
            extras.append("Characters: " + ", ".join(favourite_characters))
        if favourite_cartoons:
            extras.append("Cartoons: " + ", ".join(favourite_cartoons))
        if anything_else:
            extras.append(anything_else)
        picture_theme = " · ".join(extras)

        pdf_bytes = generate_pdf(
            student_name,
            grade_label,
            topic_header,
            questions,
            image_paths,
            question_topics=question_topics,
            favourite_colour=fav_color,
            picture_theme=picture_theme,
            workbook_title=f"{student_name}'s {subject} Practice Book",
            workbook_subtitle=f"Personalised {grade_label} {subject} practice · MyInteliBooks",
            question_adults=question_adults,
            question_options=question_options,
            cover_image_path=cover_image_path,
            grade_id=grade_id,
            pets=pets_info,
            favourite_foods=favourite_foods,
            favourite_sports=favourite_sports,
            favourite_hobbies=favourite_hobbies,
            favourite_characters=favourite_characters,
            favourite_cartoons=favourite_cartoons,
        )


        pdf_dir = get_runtime_dir(job_id, "generated_pdfs")
        pdf_filename = create_safe_filename(student_name)
        pdf_path = pdf_dir / pdf_filename
        pdf_path.write_bytes(pdf_bytes)

        bc_img = get_backcover_image_path()
        write_job_metadata(job_id, {
            "generation_status": "complete",
            "pdf_path": str(pdf_path),
            "pdf_filename": pdf_filename,
            "has_pdf": True,
            "total_questions": len(items),
            "selected_topics": selected_topics or [],
            "gender": gender,
            "location": location,
            "student_name": student_name,
            "grade_id": grade_id,
            "grade_display": grade_label,
            "has_backcover": bool(bc_img and bc_img.exists()),
            "completed_at": datetime.now().isoformat(),
        })

        # Format items for frontend preview
        preview_items = []
        for idx, it in enumerate(items, start=1):
            img_p = it.get("image_path")
            img_url = None
            if img_p and Path(img_p).exists():
                img_url = f"/api/jobs/{job_id}/preview/generated_images/{Path(img_p).name}"
            
            opts = it.get("options")
            options_list = []
            if isinstance(opts, dict):
                options_list = opts.get("options") or []
            elif isinstance(opts, (list, tuple)):
                options_list = list(opts)

            topic_title = it.get("topic_label") or it.get("topic") or f"Math Question {idx}"
            ans = it.get("correct")
            if ans is None:
                ans = it.get("correct_answer") or it.get("answer") or ""

            preview_items.append({
                "stem_id": it.get("stem_id") or f"stem_{idx}",
                "topic": it.get("topic") or "math",
                "topic_label": topic_title,
                "adult_role": it.get("adult_role") or "",
                "adult_name": it.get("adult_name") or "",
                "question": it.get("question") or it.get("question_text") or "",
                "correct": str(ans) if ans is not None else "",
                "options": options_list,
                "image_url": img_url,
            })

        cover_preview_url = None
        if cover_image_path and Path(cover_image_path).exists():
            cover_preview_url = f"/api/jobs/{job_id}/preview/front_cover/{Path(cover_image_path).name}"

        with job_lock:
            state["status"] = "completed"
            state["job_id"] = job_id
            state["phase"] = "complete"
            state["progress"] = 1.0
            state["message"] = f"Hooray! Personalized workbook for {student_name} is complete!"
            state["student_name"] = student_name
            state["grade_id"] = grade_id
            state["grade_label"] = grade_label
            state["selected_topics"] = selected_topics or []
            state["items"] = preview_items
            state["skipped"] = skipped
            state["pdf_filename"] = pdf_filename
            state["pdf_url"] = f"/api/jobs/{job_id}/pdf"
            state["cover_url"] = cover_preview_url
            state["pdf_ready"] = True

    except Exception as exc:
        import traceback
        traceback.print_exc()
        with job_lock:
            state["status"] = "failed"
            state["error"] = str(exc)
            state["message"] = f"Generation stopped: {exc}"
            state["progress"] = 0.0


@app.post("/api/generate")
def start_generation(req: GenerateRequest, background_tasks: BackgroundTasks):
    if not is_grade_available(req.grade_id):
        raise HTTPException(
            status_code=400,
            detail=f"{req.grade_id} content is not available yet.",
        )

    job_id = req.job_id or generate_job_id()

    with job_lock:
        job_states[job_id] = {
            "job_id": job_id,
            "status": "starting",
            "phase": "init",
            "progress": 0.02,
            "message": "Starting workbook generation...",
            "student_name": req.student_name,
            "error": None,
            "pdf_ready": False,
        }

    background_tasks.add_task(_run_generation_task, job_id, req.dict())

    return {
        "job_id": job_id,
        "status": "queued",
        "poll_url": f"/api/jobs/{job_id}/status",
    }


@app.get("/api/jobs/{job_id}/status")
def get_job_status(job_id: str):
    with job_lock:
        if job_id in job_states:
            return job_states[job_id]

    # Fallback to metadata on disk if server restarted
    try:
        meta = read_job_metadata(job_id)
        if meta:
            pdf_path_str = meta.get("pdf_path")
            pdf_ready = bool(pdf_path_str and Path(pdf_path_str).exists())
            pdf_filename = meta.get("pdf_filename", f"{job_id}.pdf")
            return {
                "job_id": job_id,
                "status": meta.get("generation_status", "unknown"),
                "phase": "complete" if pdf_ready else "unknown",
                "progress": 1.0 if pdf_ready else 0.0,
                "message": "Workbook loaded from records." if pdf_ready else "Job found.",
                "pdf_ready": pdf_ready,
                "pdf_filename": pdf_filename,
                "pdf_url": f"/api/jobs/{job_id}/pdf" if pdf_ready else None,
                "items": [],
            }
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/jobs/{job_id}/pdf")
def download_job_pdf(job_id: str):
    pdf_dir = get_runtime_dir(job_id, "generated_pdfs")
    if not pdf_dir.exists():
        raise HTTPException(status_code=404, detail="PDF directory not found")

    pdfs = list(pdf_dir.glob("*.pdf"))
    if not pdfs:
        raise HTTPException(status_code=404, detail="No PDF has been generated for this job yet")

    pdf_file = pdfs[0]
    return FileResponse(
        str(pdf_file),
        media_type="application/pdf",
        filename=pdf_file.name,
        headers={"Content-Disposition": f'inline; filename="{pdf_file.name}"'},
    )


@app.post("/api/jobs/{job_id}/claim-download")
def claim_download(job_id: str, body: ClaimDownload):
    return claim_job_download(job_id, body.email)


@app.get("/api/feedback/{token}")
def public_feedback_get(token: str):
    rec = get_feedback_by_token(token)
    if not rec:
        raise HTTPException(status_code=404, detail="This feedback link is invalid or has expired.")
    already = rec.get("status") == "replied"
    return {
        "token": token,
        "student_name": rec.get("student_name") or "",
        "grade_display": rec.get("grade_display") or rec.get("grade_id") or "",
        "status": rec.get("status"),
        "already_replied": already,
        "support_email": SUPPORT_EMAIL,
        "question_count": rec.get("question_count") or 0,
        "topics": rec.get("topics") or [],
    }


@app.post("/api/feedback/{token}")
def public_feedback_post(token: str, body: FeedbackSubmit):
    return submit_public_feedback(token, body)


@app.get("/api/backcover")
def serve_current_backcover():
    """Serve the active backcover image for preview or verification."""
    bc_path = get_backcover_image_path()
    if not bc_path or not bc_path.exists():
        raise HTTPException(status_code=404, detail="Backcover image not found")
    return FileResponse(str(bc_path))


@app.get("/api/jobs/{job_id}/preview/{subdir}/{filename}")
def serve_job_image(job_id: str, subdir: str, filename: str):
    # Allowed subdirs for security
    if subdir not in ("uploads", "generated_images", "front_cover", "last_page", "backcover"):
        raise HTTPException(status_code=400, detail="Invalid resource directory")

    target_dir = get_runtime_dir(job_id, subdir)
    target_path = target_dir / filename
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")

    return FileResponse(str(target_path))


@app.get("/api/assets/foods/{filename}")
def serve_food_icon(filename: str):
    icon_path = REPO_ROOT / "shared" / "icons" / "foods" / filename
    if not icon_path.exists() or not icon_path.is_file():
        raise HTTPException(status_code=404, detail="Food icon not found")
    media_type = "image/svg+xml" if filename.endswith(".svg") else "image/png"
    return FileResponse(str(icon_path), media_type=media_type)


@app.get("/api/assets/characters/{filename}")
def serve_character_badge(filename: str):
    badge_path = REPO_ROOT / "shared" / "characters" / filename
    if not badge_path.exists() or not badge_path.is_file():
        raise HTTPException(status_code=404, detail="Character badge not found")
    return FileResponse(str(badge_path), media_type="image/png")


@app.get("/api/assets/pets/{filename}")
def serve_pet_image(filename: str):
    pet_path = REPO_ROOT / "shared" / "pets" / filename
    if not pet_path.exists() or not pet_path.is_file():
        raise HTTPException(status_code=404, detail="Pet image not found")
    return FileResponse(str(pet_path), media_type="image/png")

# ── Static React Frontend Serving ────────────────────────────────────────────
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    # Mount assets folder
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def serve_react_app(full_path: str):
        # Don't intercept API calls
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, reload=True)

