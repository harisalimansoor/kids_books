"""
Bank-first stem helpers for the new_pipeline workbook flow.

Select ready role-locked templates → fill name placeholders → personalize faces.
Answers come from meta.json (never re-guessed by an LLM).
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent
TEMPLATES_ROOT = PIPELINE_ROOT / "question_templates"
GRADE_ROOT = TEMPLATES_ROOT / "grade_1"

if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

ROLE_DISPLAY = {
    "mother": "Mum",
    "father": "Dad",
    "grandmother": "Grandma",
    "grandfather": "Grandad",
}

ADULT_ROLES = tuple(ROLE_DISPLAY.keys())


def list_topics() -> list[str]:
    if not GRADE_ROOT.is_dir():
        return []
    topics = []
    for p in sorted(GRADE_ROOT.iterdir()):
        if not p.is_dir():
            continue
        if any((p / d / "meta.json").is_file() for d in p.iterdir() if d.is_dir()):
            topics.append(p.name)
    return topics


def topic_label(topic_id: str) -> str:
    return topic_id.replace("_", " ").title()


def load_stem(stem_dir: Path) -> dict:
    meta = json.loads((stem_dir / "meta.json").read_text(encoding="utf-8"))
    q_file = stem_dir / (meta.get("question_file") or "question.txt")
    question = q_file.read_text(encoding="utf-8").strip() if q_file.exists() else ""
    img_name = meta.get("image_file") or ""
    img_path = stem_dir / img_name if img_name else None
    pers = meta.get("personalisation") or {}
    locked = (pers.get("template_adult_role") or "").strip().lower()
    return {
        "stem_dir": stem_dir,
        "stem_id": meta.get("stem_id") or stem_dir.name,
        "topic": meta.get("topic") or stem_dir.parent.name,
        "meta": meta,
        "question_template": question,
        "image_path": img_path,
        "status": (meta.get("status") or "").strip().lower(),
        "verified": bool((meta.get("validation") or {}).get("verified")),
        "template_adult_role": locked,
        "allowed_adult_roles": [
            r.lower() for r in (pers.get("allowed_adult_roles") or ([locked] if locked else []))
        ],
    }


def list_ready_stems(
    *,
    topics: list[str] | None = None,
    require_verified: bool = True,
) -> list[dict]:
    """All ready stems, optionally filtered by topic folder names."""
    if not GRADE_ROOT.is_dir():
        return []
    topic_set = {t.lower() for t in topics} if topics else None
    stems: list[dict] = []
    for topic_dir in sorted(GRADE_ROOT.iterdir()):
        if not topic_dir.is_dir():
            continue
        if topic_set is not None and topic_dir.name.lower() not in topic_set:
            continue
        for stem_dir in sorted(topic_dir.iterdir()):
            if not stem_dir.is_dir() or not (stem_dir / "meta.json").is_file():
                continue
            stem = load_stem(stem_dir)
            if stem["status"] != "ready":
                continue
            if require_verified and not stem["verified"]:
                continue
            if not stem["template_adult_role"]:
                continue
            if not stem["image_path"] or not stem["image_path"].is_file():
                continue
            if not stem["question_template"]:
                continue
            stems.append(stem)
    return stems


def stems_for_available_roles(
    stems: list[dict],
    available_roles: set[str],
) -> list[dict]:
    """Keep stems whose locked adult role has an uploaded photo."""
    avail = {r.lower() for r in available_roles}
    out = []
    for stem in stems:
        role = stem["template_adult_role"]
        allowed = stem["allowed_adult_roles"] or [role]
        if role in avail and role in allowed:
            out.append(stem)
    return out


def select_stems(
    stems: list[dict],
    n: int,
    *,
    prefer_topic_spread: bool = True,
) -> list[dict]:
    """Pick up to n unique stem_ids (shuffle, optionally spread topics)."""
    if n <= 0 or not stems:
        return []
    by_id: dict[str, dict] = {}
    for s in stems:
        by_id.setdefault(s["stem_id"], s)
    unique = list(by_id.values())
    random.shuffle(unique)

    if not prefer_topic_spread or n >= len(unique):
        return unique[:n]

    # Round-robin across topics for variety
    by_topic: dict[str, list[dict]] = {}
    for s in unique:
        by_topic.setdefault(s["topic"], []).append(s)
    topics = list(by_topic.keys())
    random.shuffle(topics)
    picked: list[dict] = []
    while len(picked) < n and any(by_topic.values()):
        for t in topics:
            bucket = by_topic.get(t) or []
            if not bucket:
                continue
            picked.append(bucket.pop(0))
            if len(picked) >= n:
                break
    return picked


def display_name_for_role(role: str, family_names: dict[str, str] | None = None) -> str:
    family_names = family_names or {}
    role = role.strip().lower()
    raw = (family_names.get(role) or "").strip()
    placeholders = {role, "mother", "father", "grandmother", "grandfather", "mum", "dad", "adult"}
    if raw and raw.lower() not in placeholders:
        return raw
    return ROLE_DISPLAY.get(role, role.replace("_", " ").title())


def fill_question_text(
    template: str,
    *,
    user_name: str,
    adult_role: str,
    family_names: dict[str, str] | None = None,
) -> str:
    """Replace {user_name}, {mother_name}, … with profile names."""
    family_names = family_names or {}
    adult_name = display_name_for_role(adult_role, family_names)
    child = (user_name or "").strip() or "you"

    mapping = {
        "user_name": child,
        "adult_name": adult_name,
        "mother_name": display_name_for_role("mother", family_names),
        "father_name": display_name_for_role("father", family_names),
        "grandmother_name": display_name_for_role("grandmother", family_names),
        "grandfather_name": display_name_for_role("grandfather", family_names),
        "sibling_name": (family_names.get("sibling") or "your sibling").strip(),
    }
    # Locked stem should always use the chosen adult display name for its role token
    mapping[f"{adult_role}_name"] = adult_name

    text = template
    for key, value in mapping.items():
        text = text.replace("{" + key + "}", value)

    # Drop any leftover unknown placeholders conservatively
    text = re.sub(r"\{[a-z_]+\}", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def mcq_from_meta(meta: dict) -> dict:
    answer = meta.get("answer") or {}
    options = [str(o) for o in (answer.get("options") or [])]
    correct = str(answer.get("correct") or "")
    if correct and correct not in options:
        options = [correct] + [o for o in options if o != correct]
    return {
        "options": options[:4],
        "correct_answer": correct,
    }


def build_workbook_items(
    stems: list[dict],
    *,
    user_name: str,
    family_names: dict[str, str],
    face_paths: dict[str, str | Path],
    run_ai_finish: bool = True,
    out_dir: Path | None = None,
) -> list[dict]:
    """
    Personalize each stem and return PDF-ready items.

    face_paths keys: user/child, mother, father, grandmother, grandfather
    """
    from question_templates.personalize import personalize_stem

    out_dir = Path(out_dir) if out_dir else PIPELINE_ROOT / "_runtime" / "personalized"
    out_dir.mkdir(parents=True, exist_ok=True)

    child_photo = face_paths.get("user") or face_paths.get("child")
    if not child_photo:
        raise ValueError("Child face photo is required.")

    items: list[dict] = []
    for i, stem in enumerate(stems, start=1):
        role = stem["template_adult_role"]
        adult_photo = face_paths.get(role)
        if not adult_photo:
            raise ValueError(f"Missing face photo for locked role '{role}' ({stem['stem_id']}).")

        out_path = out_dir / f"{i:02d}_{stem['stem_id']}_{role}.png"
        personalize_stem(
            stem["stem_dir"],
            child_photo=child_photo,
            adult_photo=adult_photo,
            adult_role=role,
            out_path=out_path,
            run_ai_finish=run_ai_finish,
        )

        q_text = fill_question_text(
            stem["question_template"],
            user_name=user_name,
            adult_role=role,
            family_names=family_names,
        )
        mcq = mcq_from_meta(stem["meta"])
        items.append(
            {
                "stem_id": stem["stem_id"],
                "topic": stem["topic"],
                "topic_label": topic_label(stem["topic"]),
                "adult_role": role,
                "adult_name": display_name_for_role(role, family_names),
                "question": q_text,
                "image_path": str(out_path),
                "options": mcq,
                "correct": mcq["correct_answer"],
                "formula": (stem["meta"].get("answer") or {}).get("formula"),
            }
        )
    return items
