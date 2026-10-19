"""
app/grade_config.py
───────────────────────────────────────────────────────────────────────────────
Centralized configuration and path resolver for the multi-grade workbook system.

All other modules (stem_pipeline, image_generator, front_cover_generator,
pdf_generator, newapp) must import path resolution from here.

DO NOT scatter path construction across the codebase.

Public API
──────────
Registry:
    list_grades(enabled_only=True)   → list[dict]
    get_grade_entry(grade_id)        → dict

Grade configuration:
    get_grade_config(grade_id)       → dict
    get_grade_features(grade_id)     → dict
    get_grade_topics(grade_id)       → list[str]

Path resolution:
    get_grade_dir(grade_id)          → Path
    get_questions_roots(grade_id)    → list[Path]
    get_prompt_path(grade_id, name)  → Path
    get_shared_prompt_path(name)     → Path
    get_fonts_dir(grade_id)          → Path
    get_icons_dir(grade_id)          → Path
    get_assets_dir(grade_id, key)    → Path

Runtime / Job:
    generate_job_id()                → str
    get_job_dir(job_id)              → Path
    get_runtime_dir(job_id, subdir)  → Path
    write_job_metadata(job_id, data) → None
    read_job_metadata(job_id)        → dict

Errors:
    GradeNotFoundError
    GradeConfigError
    PromptNotFoundError
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from datetime import datetime

# ── Root paths ────────────────────────────────────────────────────────────────
# grade_config.py lives in app/, so REPO_ROOT is one level up.
APP_DIR   = Path(__file__).resolve().parent          # .../kids books/app/
REPO_ROOT = APP_DIR.parent                           # .../kids books/

CONFIG_DIR  = REPO_ROOT / "config"
GRADES_DIR  = REPO_ROOT / "grades"
SHARED_DIR  = REPO_ROOT / "shared"
RUNTIME_DIR = REPO_ROOT / "runtime"
JOBS_DIR    = RUNTIME_DIR / "jobs"
BACKCOVER_DIR = REPO_ROOT / "backcover"

# Config file paths
_GRADES_JSON       = CONFIG_DIR / "grades.json"
_APP_CONFIG_JSON   = CONFIG_DIR / "app_config.json"
_GRADE_TOPICS_JSON = CONFIG_DIR / "grade_topics.json"

# ── Errors ────────────────────────────────────────────────────────────────────

class GradeNotFoundError(Exception):
    """Raised when a grade_id is not registered or its folder is missing."""

class GradeConfigError(Exception):
    """Raised when a grade config.json is missing or malformed."""

class PromptNotFoundError(Exception):
    """Raised when a requested prompt file cannot be found."""


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | list:
    with open(str(path), encoding="utf-8-sig") as fh:
        return json.load(fh)


def _app_config() -> dict:
    if not _APP_CONFIG_JSON.exists():
        return {
            "workbook_id_prefix": "WB",
            "workbook_id_padding": 6,
        }
    return _load_json(_APP_CONFIG_JSON)  # type: ignore[return-value]


# ── Registry ──────────────────────────────────────────────────────────────────

CANONICAL_GRADE_ORDER = [
    "PG", "NURSERY", "PREP", "KG",
    "GRADE_1", "GRADE_2", "GRADE_3", "GRADE_4", "GRADE_5",
    "GRADE_6", "GRADE_7", "GRADE_8", "GRADE_9", "GRADE_10",
]


def list_grades(*, enabled_only: bool = True) -> list[dict]:
    """
    Return grades from config/grades.json sorted in canonical ascending order.

    enabled_only=True (default) returns only grades with enabled=true.
    enabled_only=False returns all registered grades.
    """
    if not _GRADES_JSON.exists():
        raise GradeConfigError(f"grades.json not found at: {_GRADES_JSON}")
    data = _load_json(_GRADES_JSON)
    grades = data.get("grades", [])  # type: ignore[union-attr]
    if enabled_only:
        grades = [g for g in grades if g.get("enabled", False)]

    def _grade_sort_key(entry: dict) -> int:
        gid = (entry.get("id") or "").upper()
        try:
            return CANONICAL_GRADE_ORDER.index(gid)
        except ValueError:
            return 999

    grades.sort(key=_grade_sort_key)
    return grades


def get_grade_entry(grade_id: str) -> dict:
    """
    Return the grades.json registry entry for grade_id.

    Raises GradeNotFoundError if the grade_id is not registered.
    Never silently falls back to Grade_1.
    """
    all_grades = list_grades(enabled_only=False)
    for g in all_grades:
        if g.get("id") == grade_id:
            return g
    raise GradeNotFoundError(
        f"Grade '{grade_id}' is not registered in config/grades.json. "
        f"Available grades: {[g.get('id') for g in all_grades]}"
    )


# ── Grade configuration ────────────────────────────────────────────────────────

def get_grade_config(grade_id: str) -> dict:
    """
    Load and return grades/<grade_id>/config.json.

    Raises GradeNotFoundError if the grade folder does not exist.
    Raises GradeConfigError if config.json is missing or malformed.
    Does NOT fall back to Grade_1 for any reason.
    """
    grade_dir = GRADES_DIR / grade_id
    if not grade_dir.is_dir():
        raise GradeNotFoundError(
            f"Grade folder not found: {grade_dir}. "
            f"Create grades/{grade_id}/ with a config.json to register this grade."
        )
    config_path = grade_dir / "config.json"
    if not config_path.exists():
        raise GradeConfigError(
            f"config.json missing for grade '{grade_id}' at: {config_path}"
        )
    try:
        cfg = _load_json(config_path)
    except json.JSONDecodeError as exc:
        raise GradeConfigError(
            f"config.json for grade '{grade_id}' is not valid JSON: {exc}"
        ) from exc
    return cfg  # type: ignore[return-value]


def get_grade_features(grade_id: str) -> dict:
    """
    Return the 'features' dict from the grade config.

    Example return: {'ai_question_images': True, 'front_cover': True, 'last_page': False}
    Returns empty dict if features not defined (safe default — no features enabled).
    """
    cfg = get_grade_config(grade_id)
    return cfg.get("features") or {}


def get_grade_visual_policy(grade_id: str) -> dict:
    """
    Return the grade-specific visual policy defining whether this grade renders
    in-scene countable objects or overlays a structured mathematical card,
    along with clutter rules, maximum in-scene counts, and category behaviors.
    """
    try:
        cfg = get_grade_config(grade_id)
        if "visual_policy" in cfg:
            return cfg["visual_policy"]
    except Exception:
        pass

    # Default fallback derived from grade identifier
    norm = (grade_id or "").lower().replace("-", "_").replace(" ", "_")
    is_small = any(g in norm for g in ("nursery", "prep", "kg", "pg", "grade_1", "grade1"))
    if is_small:
        return {
            "mode": "in_scene",
            "max_in_scene_count": 5,
            "overlay_card_categories": [],
            "desk_clutter_policy": "show_exact_props",
            "non_counting_rules": {
                "time": "analog_clock",
                "geometry": "open_sketchpad",
                "measurement": "clear_graduations",
            },
        }
    else:
        return {
            "mode": "math_card",
            "max_in_scene_count": 0,
            "overlay_card_categories": ["counting"],
            "desk_clutter_policy": "clean_minimal",
            "non_counting_rules": {
                "time": "analog_clock",
                "geometry": "open_sketchpad",
                "measurement": "clear_graduations",
            },
        }


def get_grade_output_dir(grade_id: str) -> Path:
    """Return the dedicated test_output directory for this grade."""
    p = get_grade_dir(grade_id) / "test_output"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_grade_topics(grade_id: str) -> list[str]:
    """
    Return the list of available topic IDs for the grade.

    Returns [] if the grade has no topics configured (safe — UI shows no topic selector).
    """
    cfg = get_grade_config(grade_id)
    return list(cfg.get("available_topics") or [])


def get_topic_label(topic_id: str, grade_id: str | None = None) -> str:
    """
    Return grade-specific pedagogical topic title if configured,
    else fallback to formatted title-cased topic slug.
    """
    if grade_id and _GRADE_TOPICS_JSON.exists():
        try:
            mapping = _load_json(_GRADE_TOPICS_JSON)
            grade_map = mapping.get(grade_id)
            if not grade_map:
                for k, v in mapping.items():
                    if k.lower() == grade_id.lower():
                        grade_map = v
                        break
            if grade_map and topic_id in grade_map:
                return grade_map[topic_id]
        except Exception:
            pass
    return topic_id.replace("_", " ").title()


def is_grade_available(grade_id: str) -> bool:
    """
    True only when this grade is enabled and has its own question bank
    and its own question-image prompt.

    A missing bank, a missing prompt, or enabled=false returns False.
    This never treats another grade's questions or prompts as a substitute.
    """
    try:
        entry = get_grade_entry(grade_id)
    except GradeNotFoundError:
        return False
    if not entry.get("enabled"):
        return False
    try:
        roots = get_questions_roots(grade_id)
        cfg = get_grade_config(grade_id)
    except (GradeNotFoundError, GradeConfigError):
        return False
    if not roots:
        return False
    rel = (cfg.get("prompts") or {}).get("question_image")
    if not rel:
        return False
    prompt = get_grade_dir(grade_id) / rel
    if not prompt.is_file():
        return False
    try:
        if get_grade_dir(grade_id).resolve() not in prompt.resolve().parents:
            return False
    except OSError:
        return False
    return True


def grade_select_options() -> list[dict]:
    """
    One dropdown entry for every grade registered in config/grades.json.

    Available grades keep their display name.
    Unavailable grades stay visible and are labelled so generation can be blocked.
    """
    options: list[dict] = []
    for entry in list_grades(enabled_only=False):
        grade_id = entry.get("id") or ""
        display_name = entry.get("display_name") or grade_id
        available = is_grade_available(grade_id) if grade_id else False
        spoken_id = grade_id.replace("_", " ")
        label = display_name
        if grade_id and spoken_id not in display_name and grade_id not in display_name:
            label = f"{display_name} ({grade_id})"
        if not available:
            label = f"{label} — content not available yet"
        topic_ids = get_grade_topics(grade_id) if available else []
        topics = [{"id": t, "label": get_topic_label(t, grade_id)} for t in topic_ids]
        options.append(
            {
                "id": grade_id,
                "display_name": display_name,
                "label": label,
                "available": available,
                "topics": topics,
            }
        )
    return options


# ── Path resolution ────────────────────────────────────────────────────────────

def get_grade_dir(grade_id: str) -> Path:
    """
    Return the path to grades/<grade_id>/.

    Raises GradeNotFoundError if the folder does not exist.
    """
    d = GRADES_DIR / grade_id
    if not d.is_dir():
        raise GradeNotFoundError(f"Grade folder not found: {d}")
    return d


def get_questions_roots(grade_id: str) -> list[Path]:
    """
    Return a list of existing question bank paths for the grade,
    in priority order: [primary, fallback].
    Grade 1 uses only questions/curriculum.
    Every other grade keeps its configured primary and fallback banks.
    """
    cfg = get_grade_config(grade_id)
    banks = cfg.get("question_banks")
    if not banks:
        raise GradeConfigError(
            f"Grade '{grade_id}' config.json is missing 'question_banks' definition."
        )
    grade_dir = get_grade_dir(grade_id)
    if (grade_id or "").strip().lower() in {"grade_1", "grade 1"}:
        curriculum = grade_dir / "questions" / "curriculum"
        if curriculum.is_dir():
            return [curriculum]
    roots: list[Path] = []
    for key in ("primary", "fallback"):
        rel = banks.get(key)
        if rel:
            p = grade_dir / rel
            if p.is_dir():
                roots.append(p)
    return roots


def get_prompt_path(grade_id: str, prompt_name: str) -> Path:
    """
    Return path to grades/<grade_id>/prompts/<prompt_name>.md.

    Raises GradeNotFoundError if grade is missing.
    Raises PromptNotFoundError if the prompt file does not exist
    and there is no shared fallback.
    """
    cfg = get_grade_config(grade_id)
    prompts_cfg = cfg.get("prompts") or {}
    rel = prompts_cfg.get(prompt_name)
    if rel:
        p = get_grade_dir(grade_id) / rel
        if p.exists():
            return p
    # Try shared fallback
    try:
        return get_shared_prompt_path(prompt_name)
    except PromptNotFoundError:
        pass
    raise PromptNotFoundError(
        f"Prompt '{prompt_name}' not found for grade '{grade_id}'. "
        f"Expected at: grades/{grade_id}/prompts/{prompt_name}.md "
        f"or shared/prompts/{prompt_name}.md"
    )


def get_shared_prompt_path(prompt_name: str) -> Path:
    """
    Return path to shared/prompts/<prompt_name>.md.

    Raises PromptNotFoundError if not found.
    """
    p = SHARED_DIR / "prompts" / f"{prompt_name}.md"
    if not p.exists():
        raise PromptNotFoundError(
            f"Shared prompt '{prompt_name}' not found at: {p}"
        )
    return p


def get_fonts_dir(grade_id: str) -> Path:
    """
    Return the fonts directory for the grade.

    Resolution order:
      1. grades/<grade_id>/fonts/  — if it exists and the grade config specifies it
      2. shared/fonts/             — fallback for all grades

    Raises FileNotFoundError if neither location exists.
    """
    cfg = get_grade_config(grade_id)
    if cfg.get("fonts"):
        p = get_grade_dir(grade_id) / cfg["fonts"]
        if p.is_dir():
            return p
    # Check for implicit grade-specific fonts dir
    grade_fonts = get_grade_dir(grade_id) / "fonts"
    if grade_fonts.is_dir():
        return grade_fonts
    # Shared fallback
    shared_fonts = SHARED_DIR / "fonts"
    if shared_fonts.is_dir():
        return shared_fonts
    raise FileNotFoundError(
        f"No fonts directory found for grade '{grade_id}'. "
        f"Expected shared/fonts/ at: {shared_fonts}"
    )


def get_icons_dir(grade_id: str) -> Path:
    """
    Return the icons directory for the grade.

    Resolution order:
      1. grades/<grade_id>/icons/  — if it exists and the grade config specifies it
      2. shared/icons/             — fallback for all grades

    Raises FileNotFoundError if neither location exists.
    """
    cfg = get_grade_config(grade_id)
    if cfg.get("icons"):
        p = get_grade_dir(grade_id) / cfg["icons"]
        if p.is_dir():
            return p
    # Check for implicit grade-specific icons dir
    grade_icons = get_grade_dir(grade_id) / "icons"
    if grade_icons.is_dir():
        return grade_icons
    # Shared fallback
    shared_icons = SHARED_DIR / "icons"
    if shared_icons.is_dir():
        return shared_icons
    raise FileNotFoundError(
        f"No icons directory found for grade '{grade_id}'. "
        f"Expected shared/icons/ at: {shared_icons}"
    )


def get_assets_dir(grade_id: str, asset_key: str | None = None) -> Path:
    """
    Return grades/<grade_id>/assets/ or a specific asset subdirectory.

    If asset_key is provided, looks it up in config['assets'][asset_key].
    Raises GradeNotFoundError if grade is missing.
    Raises KeyError if asset_key is not in the grade's assets config.
    """
    grade_dir = get_grade_dir(grade_id)
    if asset_key is None:
        return grade_dir / "assets"
    cfg = get_grade_config(grade_id)
    assets_cfg = cfg.get("assets") or {}
    if asset_key not in assets_cfg:
        raise KeyError(
            f"Asset key '{asset_key}' not found in grade '{grade_id}' config. "
            f"Available keys: {list(assets_cfg.keys())}"
        )
    return grade_dir / assets_cfg[asset_key]


def get_backcover_image_path() -> Path | None:
    """
    Search for a backcover image in the 'backcover' folder.
    Looks in:
      1. REPO_ROOT / "backcover"
      2. REPO_ROOT.parent / "backcover"
      3. SHARED_DIR / "backcover"
      4. SHARED_DIR / "assets" / "backcover"

    Supports: .jpg, .jpeg, .png, .webp, .bmp.
    Returns the Path to the image file, or None if no image is found.
    If multiple candidate images exist, picks the most recently modified one
    (prioritizing files explicitly named 'backcover.*' on timestamp ties).
    """
    search_dirs = [
        REPO_ROOT / "backcover",
        REPO_ROOT.parent / "backcover",
        SHARED_DIR / "backcover",
        SHARED_DIR / "assets" / "backcover",
    ]
    supported_exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
    candidates: list[Path] = []

    for s_dir in search_dirs:
        if not s_dir.is_dir():
            continue
        try:
            for item in s_dir.iterdir():
                if item.is_file() and item.suffix.lower() in supported_exts:
                    candidates.append(item)
        except Exception:
            continue

    if not candidates:
        return None

    def _rank_candidate(p: Path) -> tuple[float, int]:
        try:
            mtime = p.stat().st_mtime
        except Exception:
            mtime = 0.0
        is_named_backcover = 1 if p.stem.lower() == "backcover" else 0
        return (mtime, is_named_backcover)

    candidates.sort(key=_rank_candidate, reverse=True)
    return candidates[0]



# ── Runtime / Job resolution ───────────────────────────────────────────────────

_job_id_lock = threading.Lock()


def generate_job_id() -> str:
    """
    Generate the next available workbook ID (WB_000001, WB_000002, ...).

    Scans existing job folders under runtime/jobs/ to determine the next ID.
    Thread-safe via a module-level lock.
    """
    app_cfg = _app_config()
    prefix  = app_cfg.get("workbook_id_prefix", "WB")
    padding = int(app_cfg.get("workbook_id_padding", 6))

    with _job_id_lock:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        existing_ids: list[int] = []
        for p in JOBS_DIR.iterdir():
            if p.is_dir() and p.name.startswith(prefix + "_"):
                try:
                    val = int(p.name[len(prefix) + 1:])
                    if val < 900000:
                        existing_ids.append(val)
                except ValueError:
                    pass
        next_id = max(existing_ids, default=0) + 1
        return f"{prefix}_{str(next_id).zfill(padding)}"



def get_job_dir(job_id: str) -> Path:
    """
    Return runtime/jobs/<job_id>/.

    Creates the directory and its standard subdirectories if they do not exist.
    """
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    # Ensure all standard subdirs exist
    for subdir in ("uploads", "generated_images", "front_cover", "last_page", "generated_pdfs"):
        (job_dir / subdir).mkdir(exist_ok=True)
    return job_dir


def get_runtime_dir(job_id: str, subdir: str) -> Path:
    """
    Return runtime/jobs/<job_id>/<subdir>/.

    Creates the directory if it does not exist.
    Valid subdirs: 'uploads', 'generated_images', 'front_cover', 'last_page', 'generated_pdfs'
    """
    _VALID_SUBDIRS = {"uploads", "generated_images", "front_cover", "last_page", "generated_pdfs"}
    if subdir not in _VALID_SUBDIRS:
        raise ValueError(
            f"Invalid runtime subdir '{subdir}'. Valid options: {sorted(_VALID_SUBDIRS)}"
        )
    job_dir = get_job_dir(job_id)
    d = job_dir / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_job_metadata(job_id: str, metadata: dict) -> None:
    """
    Write runtime/jobs/<job_id>/metadata.json.

    Merges with existing metadata if the file already exists (update semantics).
    """
    job_dir = get_job_dir(job_id)
    meta_path = job_dir / "metadata.json"
    existing: dict = {}
    if meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing.update(metadata)
    meta_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def read_job_metadata(job_id: str) -> dict:
    """
    Read runtime/jobs/<job_id>/metadata.json.

    Raises FileNotFoundError if the metadata file does not exist.
    """
    meta_path = JOBS_DIR / job_id / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(
            f"Metadata not found for job '{job_id}' at: {meta_path}"
        )
    return json.loads(meta_path.read_text(encoding="utf-8"))
