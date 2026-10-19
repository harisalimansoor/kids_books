"""
image_generator.py
Generate personalised educational scene images from scratch — no face swapping, no template PNG.

HOW IT WORKS (AI Generate mode)
────────────────────────────────
    Like sending a message to ChatGPT / Gemini with:
        - A text prompt  : full prompt.md instructions + the filled question text
        - Reference photos: the uploaded family photos (child, dad, mum, etc.)

    The AI draws a completely NEW scene from scratch, but uses the uploaded photos
    as VISUAL REFERENCES for the characters' appearance (face, hair, skin tone, etc).

    Prompt.md already contains the instruction:
        "If a reference image is provided, use it ONLY as visual reference for the
         requested character appearance, clothing, proportions ..."

    So the flow is:
        prompt.md  +  [PASTE ONE QUESTION HERE] -> question text
        +  uploaded photos (child, adult, ...)
        ──────────────────────────────────────────────────────
                        OpenRouter API call
        ──────────────────────────────────────────────────────
             Fresh generated image  (saved as PNG)

DIFFERENCE FROM FACE SWAPPING
    Face Swap  : load template.png  ->  crop face from upload  ->  paste  ->  AI blend seams
    AI Generate: NO template.png  ->  pass uploads as visual reference  ->  AI draws fresh scene

PHOTOS ARE STILL REQUIRED
    The user must upload photos for the child and any family member
    that appears in the question (same roles as face-swap mode).
    The photos are sent to the API as image_url content blocks.
    Priority order: child first, then adult / sibling.

ENVIRONMENT VARIABLES
    OPENROUTER_API_KEY          required
    IMAGE_GEN_MODEL             optional; default openai/gpt-image-2
    IMAGE_GEN_MAX_ATTEMPTS      optional; default 3
"""

from __future__ import annotations

import base64
import os
import sys
import re
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

# ── paths ──────────────────────────────────────────────────────────────────
PIPELINE_ROOT = Path(__file__).resolve().parent   # app/
REPO_ROOT = PIPELINE_ROOT.parent                  # kids_books/

if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from app.grade_config import get_grade_dir, get_prompt_path, PromptNotFoundError
except ImportError:
    from grade_config import get_grade_dir, get_prompt_path, PromptNotFoundError  # type: ignore

# ── .env ───────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=REPO_ROOT / ".env")
except Exception:
    pass

# ── config ──────────────────────────────────────────────────────────────────
API_KEY: str = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL        = "https://openrouter.ai/api/v1/chat/completions"  # legacy / vision models
OPENROUTER_IMAGES_URL = "https://openrouter.ai/api/v1/images"            # dedicated image-gen models (gpt-image-2, etc.)

# Models that must use the /images endpoint instead of /chat/completions
_IMAGE_ENDPOINT_PREFIXES = ("openai/gpt-image",)

def _uses_image_endpoint(model: str) -> bool:
    """Return True when the model requires the /api/v1/images endpoint."""
    m = model.strip().lower()
    return any(m.startswith(p) for p in _IMAGE_ENDPOINT_PREFIXES)

IMAGE_GEN_MODEL: str = os.getenv(
    "IMAGE_GEN_MODEL",
    os.getenv("PERSONALIZE_IMAGE_MODEL", "openai/gpt-image-2"),
).strip()

IMAGE_GEN_MAX_ATTEMPTS: int = int(os.getenv("IMAGE_GEN_MAX_ATTEMPTS", "3"))


def _active_runtime(model: "str | None" = None, api_key: "str | None" = None) -> dict:
    """Resolve provider/model/key from the admin panel, with env fallback."""
    try:
        from app.admin_store import get_active_image_runtime
        rt = get_active_image_runtime()
        return {
            "provider": rt.get("provider") or "openrouter",
            "model": (model or rt.get("model") or IMAGE_GEN_MODEL).strip(),
            "api_key": (api_key or rt.get("api_key") or API_KEY).strip(),
            "endpoint": rt.get("endpoint") or "images",
        }
    except Exception:
        chosen = (model or IMAGE_GEN_MODEL or "openai/gpt-image-2").strip()
        return {
            "provider": "openrouter",
            "model": chosen,
            "api_key": (api_key or API_KEY).strip(),
            "endpoint": "images" if _uses_image_endpoint(chosen) else "chat",
        }

# The exact placeholder string that must appear in prompt.md
PLACEHOLDER = "[PASTE ONE QUESTION HERE]"

# Preferred order to send reference photos to the API
_PHOTO_PRIORITY = ["user", "child", "mother", "father", "grandmother", "grandfather",
                   "uncle", "aunt", "brother", "sister", "sibling"]

# Last API error – set by _do_post_and_decode so the UI can show the real reason
_last_gen_error: str = ""


class ImageGenError(RuntimeError):
    """Raised by _do_post_and_decode with the full API error detail."""



# ── image file helpers ──────────────────────────────────────────────────────

def _path_to_data_url(path: "str | Path") -> str:
    """
    Read an image file and return it as a base64 data-URL.
    Supports PNG, JPEG, WEBP, GIF, BMP, TIFF, HEIC, AVIF, SVG.
    """
    path = Path(path)
    ext = path.suffix.lower().lstrip(".")
    mime_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
        "tif": "image/tiff",
        "heic": "image/heic",
        "heif": "image/heif",
        "avif": "image/avif",
        "svg": "image/svg+xml",
    }
    mime = mime_map.get(ext, "image/png")
    with open(str(path), "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _ordered_photo_paths(face_paths: "dict | None") -> list[str]:
    """
    Return face photo paths in preferred order (child first, then adults).

    face_paths keys: user, child, mother, father, grandmother, grandfather,
                     uncle, aunt, brother, sister, sibling
    """
    if not face_paths:
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    # Priority roles first
    for role in _PHOTO_PRIORITY:
        p = face_paths.get(role)
        if p and p not in seen and Path(p).exists():
            ordered.append(p)
            seen.add(p)
    # Any remaining roles not in priority list
    for p in face_paths.values():
        if p and p not in seen and Path(p).exists():
            ordered.append(p)
            seen.add(p)
    return ordered


# ── prompt helpers ──────────────────────────────────────────────────────────

def _prompt_is_owned_by_grade(grade_id: str, prompt_path: Path) -> bool:
    """True when the resolved prompt file lives inside grades/<grade_id>/."""
    try:
        grade_root = get_grade_dir(grade_id).resolve()
        prompt_path.resolve().relative_to(grade_root)
        return True
    except (OSError, ValueError, Exception):
        return False


def _load_prompt_template(grade_id: str) -> str:
    """Read question_image.md for the given grade and return its contents.

    grade_id is required. A missing prompt raises. A prompt that resolves
    outside grades/<grade_id>/ is refused so another grade is never substituted.
    """
    if not (grade_id or "").strip():
        raise FileNotFoundError(
            "grade_id is required to load question_image.md. "
            "Refusing to guess a grade."
        )
    try:
        prompt_path = get_prompt_path(grade_id, "question_image")
    except PromptNotFoundError as exc:
        raise FileNotFoundError(
            f"question_image.md not found for grade '{grade_id}'. "
            f"Expected at grades/{grade_id}/prompts/question_image.md. Detail: {exc}"
        ) from exc
    if not _prompt_is_owned_by_grade(grade_id, prompt_path):
        raise FileNotFoundError(
            f"question_image.md for grade '{grade_id}' resolved outside "
            f"grades/{grade_id}/. Refusing to use another grade's prompt."
        )
    return prompt_path.read_text(encoding="utf-8")


def _extract_image_url(data: dict) -> str | None:
    """
    Pull a generated image URL or data-URI out of varied OpenRouter / OpenAI payloads.

    Handles:
      - /api/v1/images response: data[0]['b64_json'] + optional 'media_type'
      - data['data'][0]['url'] / ['b64_json']
      - choices[0]['message']['images'] (OpenRouter standard for OpenAI image models)
      - choices[0]['message']['content'] list with type == 'image_url' or 'image'
      - choices[0]['message']['content'] text/string with embedded data-URI, markdown, or raw b64
    """
    import re

    if not isinstance(data, dict):
        return None

    def from_image_obj(img) -> str | None:
        if not img:
            return None
        if isinstance(img, str) and img.startswith("data:image"):
            return img
        if not isinstance(img, dict):
            return None
        # /api/v1/images endpoint: {b64_json: "...", media_type: "image/png"}
        b64 = img.get("b64_json")
        if isinstance(b64, str) and b64:
            mime = img.get("media_type") or "image/png"
            if not b64.startswith("data:"):
                return f"data:{mime};base64," + b64.replace("\n", "")
            return b64
        url = img.get("image_url") or img.get("url")
        if isinstance(url, dict):
            url = url.get("url")
        if isinstance(url, str) and url:
            if url.startswith("data:image") or url.startswith("http"):
                return url
            if re.fullmatch(r"[A-Za-z0-9+/=\n\r]+", url) and len(url) > 200:
                return "data:image/png;base64," + url.replace("\n", "")
        return None

    # /api/v1/images and DALL-E style: data = [{b64_json/url/media_type ...}]
    for block in data.get("data") or []:
        got = from_image_obj(block)
        if got:
            return got

    choices = data.get("choices") or [{}]
    msg = (choices[0] or {}).get("message") or {}

    # OpenRouter multimodal image output: message['images'] = [{'type': 'image_url', 'image_url': {'url': ...}}]
    for img in msg.get("images") or []:
        got = from_image_obj(img)
        if got:
            return got

    content = msg.get("content", "")
    if isinstance(content, list):
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") in ("image_url", "image"):
                got = from_image_obj(p) or from_image_obj(p.get("image_url"))
                if got:
                    return got
            if isinstance(p.get("text"), str):
                m = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", p["text"])
                if m:
                    return m.group(1)
                m2 = re.search(r"https?://[^\s\"')]+", p["text"])
                if m2 and any(ext in m2.group(0).lower() for ext in (".png", ".jpg", ".jpeg", ".webp")):
                    return m2.group(0)

    if isinstance(content, str):
        m = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", content)
        if m:
            return m.group(1)
        m2 = re.search(r"https?://[^\s\"')]+", content)
        if m2 and any(ext in m2.group(0).lower() for ext in (".png", ".jpg", ".jpeg", ".webp")):
            return m2.group(0)
        if len(content) > 200 and re.fullmatch(r"[A-Za-z0-9+/=\n\r]+", content):
            return "data:image/png;base64," + content.replace("\n", "")

    return None


def extract_measurement_specification(question_text: str, meta: dict | None = None) -> str:
    """
    Detects if the question involves measuring instruments (ruler, measuring jug, water bottle, scale, thermometer)
    and returns a mandatory accuracy mandate with exact target readings, alignment,
    and crystal-clear, readable markings.
    """
    import re
    q_lower = str(question_text or "").lower()
    specs = []

    # 1. Ruler / Length Measurement (pencil, ribbon, paper, straw, eraser, etc.)
    if any(k in q_lower for k in ("ruler", "centimetre", "centimeter", "cm", "lines a pencil", "pencil is placed against a", "wooden pencil")):
        m_reach = re.search(r'(?:reaching|to|at)\s+(?:exactly\s+)?(?:the\s+)?(\d+(?:\.\d+)?)\s*(?:cm|centimetres?|centimeters?)', q_lower)
        m_mark = re.search(r'(\d+(?:\.\d+)?)\s*(?:cm|centimetres?|centimeters?)\s*(?:mark|line)?', q_lower)
        target_val = m_reach.group(1) if m_reach else (m_mark.group(1) if m_mark else "")

        specs.append(
            "MANDATORY RULER MEASUREMENT SPECIFICATION (CRITICAL — EXACT READABLE READING):\n"
            "- A centimetre ruler MUST be placed flat and prominently in the foreground on the table, facing the camera.\n"
            "- The ruler MUST have sharp, distinct, high-contrast black graduation tick marks and clearly printed, 100% READABLE NUMBERS (0, 1, 2, 3, 4, 5... up to at least 20 cm) along its edge.\n"
            + (f"- The object being measured (e.g. pencil) MUST start with its left edge aligned EXACTLY at the 0 cm mark and extend straight until its right tip terminates PRECISELY at the {target_val} cm mark.\n" if target_val else "- The object being measured MUST start with its left edge aligned EXACTLY at the 0 cm mark.\n")
            + (f"- The graduation reading '{target_val} cm' on the ruler MUST be sharp, crisp, and 100% easily readable so a young student can clearly read '{target_val} cm' from the picture!\n" if target_val else "- The ruler graduation numbers and marks must be sharp, clear, and fully legible.\n")
            + "- NEVER blur, distort, or omit the graduation markings or numbers on the ruler."
        )

    # 2. Capacity / Volume: Measuring jug, water bottle, beaker, cylinder
    if any(k in q_lower for k in ("jug", "bottle", "measuring jug", "water jug", "litre", "litres", "liter", "liters", "millilitre", "millilitres", "ml", "capacity")):
        m_vol = re.search(r'(\d+(?:\.\d+)?)\s*(litres?|liters?|l\b|ml\b|millilitres?|milliliters?)', q_lower)
        target_vol = m_vol.group(1) if m_vol else ""
        target_unit = m_vol.group(2) if m_vol else "litres"

        specs.append(
            "MANDATORY MEASURING JUG / WATER BOTTLE SPECIFICATION (CRITICAL — EXACT READABLE READING):\n"
            "- The measuring jug or water bottle MUST be made of clear, transparent glass or plastic, standing upright in the foreground facing the camera.\n"
            "- The container MUST feature clear, sharp, crisp printed measurement graduation lines and readable volume markings on its side (e.g. graduation lines labeled with units like 1 L, 2 L or 100 ml, 200 ml, 500 ml, 1000 ml).\n"
            + (f"- The water/liquid level inside the container MUST reach PRECISELY and flatly to the '{target_vol} {target_unit}' graduation line.\n" if target_vol else "- The water/liquid level inside must clearly align with a distinct graduation mark.\n")
            + (f"- The volume scale markings and the water level line at '{target_vol} {target_unit}' MUST be 100% sharp, distinct, and clearly readable by a child solving the question!\n" if target_vol else "- The scale numbers and liquid line must be sharp and legible.\n")
            + "- The container must NOT be opaque or unmarked. The graduation scale and liquid reading must be completely obvious, legible, and mathematically accurate."
        )

    # 3. Mass / Weight: Scales, balance
    if any(k in q_lower for k in ("scale", "scales", "weigh", "weighing", "mass", "kg", "kilogram", "grams")):
        m_mass = re.search(r'(\d+(?:\.\d+)?)\s*(kg|kilograms?|g\b|grams?)', q_lower)
        target_mass = m_mass.group(1) if m_mass else ""
        target_unit = m_mass.group(2) if m_mass else "kg"
        specs.append(
            "MANDATORY WEIGHING SCALE SPECIFICATION (CRITICAL — READABLE READING):\n"
            "- The weighing scale must have a clear, legible dial or digital readout facing the camera.\n"
            + (f"- The readout needle or display MUST point precisely to '{target_mass} {target_unit}'.\n" if target_mass else "- The scale dial must show clear readable markings.\n")
            + "- The reading must be crisp, sharp, and easy for a student to read."
        )

def extract_clock_time_specification(question_text: str, meta: dict | None = None) -> str:
    """
    Detects time/clock questions and mandates an authentic, clearly visible analog clock
    with numbers 1-12 and sharp hands showing the exact time mentioned in the question.
    """
    import re
    q_low = str(question_text or "").lower()
    m_oclock = re.search(r'(\d{1,2})\s*o[\'’]clock', q_low)
    m_half = re.search(r'half past\s*(\d{1,2})', q_low)
    m_qtr_past = re.search(r'quarter past\s*(\d{1,2})', q_low)
    m_qtr_to = re.search(r'quarter to\s*(\d{1,2})', q_low)
    m_digital = re.search(r'(\d{1,2}):(\d{2})', q_low)

    if m_oclock:
        h = m_oclock.group(1)
        time_desc = f"{h} o'clock (short hour hand pointing directly at {h}, long minute hand pointing straight up at 12)"
    elif m_half:
        h = m_half.group(1)
        next_h = (int(h) % 12) + 1
        time_desc = f"half past {h} (short hour hand halfway between {h} and {next_h}, long minute hand pointing straight down at 6)"
    elif m_qtr_past:
        h = m_qtr_past.group(1)
        time_desc = f"quarter past {h} (short hour hand just past {h}, long minute hand pointing horizontally right at 3)"
    elif m_qtr_to:
        h = m_qtr_to.group(1)
        time_desc = f"quarter to {h} (short hour hand approaching {h}, long minute hand pointing horizontally left at 9)"
    elif m_digital:
        time_desc = f"{m_digital.group(0)}"
    else:
        time_desc = "the exact time mentioned in the question"

    return (
        "MANDATORY ANALOG CLOCK SPECIFICATION (CRITICAL — READABLE CLOCK FACE):\n"
        "- A classic, high-contrast analog clock (wall clock or sturdy desk clock) MUST be prominently placed in the scene, facing the camera.\n"
        "- The clock face MUST have clear, legible numbers 1 to 12 arranged neatly in a circle around the dial.\n"
        f"- The clock hands MUST clearly indicate {time_desc}.\n"
        "- The clock face must be crisp, sharp, and easy for a student to read. Do NOT blur, distort, or omit the clock hands."
    )


def extract_angle_geometry_specification(question_text: str, meta: dict | None = None) -> str:
    """
    Detects angle and geometry questions and mandates an open workbook or drawing page
    flat on the desk showing the geometric angle or shape clearly illustrated.
    """
    q_low = str(question_text or "").lower()
    if "right angle" in q_low or "90 degree" in q_low:
        angle_type = "a crisp 90-degree right angle with a distinct square corner marker symbol in the vertex"
    elif "acute" in q_low:
        angle_type = "a sharp acute angle (less than 90 degrees) with an arc mark between the two rays"
    elif "obtuse" in q_low:
        angle_type = "a wide obtuse angle (greater than 90 degrees) with a curved arc mark indicating the wide angle"
    elif "reflex" in q_low:
        angle_type = "a reflex angle (greater than 180 degrees)"
    elif "triangle" in q_low:
        angle_type = "a geometric triangle with clear straight sides and marked angles"
    else:
        angle_type = "clean geometric angles and shapes with crisp straight lines"

    return (
        "MANDATORY GEOMETRY & ANGLE SPECIFICATION (CRITICAL — CLEAR DIAGRAM IN OPEN BOOK):\n"
        "- An open textbook, drawing pad, or workbook MUST be placed flat on the desk in front of the characters, facing the camera.\n"
        f"- On the open pages of the book, {angle_type} MUST be clearly drawn in crisp black ink with ruler-straight lines.\n"
        "- A student math protractor or ruler is resting neatly beside the drawing in the open book.\n"
        "- The characters are pointing to or examining this angle diagram in the book. The angle diagram must be completely sharp, legible, and mathematically clear."
    )


def extract_pattern_specification(question_text: str, meta: "dict | None" = None) -> str:
    """
    Extract exact repeating pattern sequence for early years mathematics (KG/EYFS).
    Ensures the image depicts alternating items (e.g. apple, apple, banana...) neatly side-by-side.
    """
    q = question_text or ""
    seq_match = re.search(r"pattern:\s*([^\.\?]+)", q, flags=re.IGNORECASE)
    seq_str = seq_match.group(1).strip() if seq_match else ""
    if not seq_str:
        parts = [p.strip() for p in q.split(",") if len(p.strip()) > 1]
        if len(parts) >= 3:
            seq_str = ", ".join(parts[:6])
    if not seq_str:
        seq_str = "alternating pattern sequence from the question"

    return (
        "MANDATORY MATHEMATICAL REPEATING PATTERN SPECIFICATION:\n"
        f"- EXACT ALTERNATING SEQUENCE: The tabletop in front of the characters MUST clearly display the alternating sequence: '{seq_str}'.\n"
        "- HORIZONTAL LEFT-TO-RIGHT ORDER: The pattern items must be arranged neatly in a single horizontal row from left to right.\n"
        "- DISTINCT ALTERNATING ITEMS: Every distinct item in the pattern must look clearly distinct and distinguishable (e.g., contrasting shapes, colors, or objects) so the child can easily see and continue the pattern.\n"
        "- ZERO UNIFORM CLONES: DO NOT render all identical items! The sequence MUST alternate according to the pattern.\n"
        "- ZERO TEXT OR LABELS: Do not print words or answers on the scene."
    )


def build_count_specification(
    meta: dict | None,
    question_text: str = "",
    grade_id: str = "",
    category: str = "counting",
) -> str:
    """
    Build an unambiguous mathematical count and scene specification adhering strictly to the
    separation between AI storytelling and the deterministic visual renderer.
    """
    if isinstance(meta, str):
        if not question_text:
            question_text = meta
        meta = None
    elif not isinstance(meta, dict):
        meta = None

    if not meta and not question_text:
        return ""
    if isinstance(question_text, dict):
        question_text = question_text.get("question", "") or question_text.get("stem", "")
    question_text = str(question_text or "")
    cat_lower = (category or "").strip().lower()

    # 1. Dedicated category specifications
    if cat_lower == "patterns" or "repeating pattern" in question_text.lower() or "pattern:" in question_text.lower():
        return extract_pattern_specification(question_text, meta)

    if cat_lower == "time" or any(k in question_text.lower() for k in ("clock", "o'clock", "half past", "quarter past", "quarter to", "minutes past")):
        return extract_clock_time_specification(question_text, meta)

    if cat_lower == "geometry" or any(k in question_text.lower() for k in ("angle", "right angle", "acute", "obtuse", "degrees", "protractor")):
        return extract_angle_geometry_specification(question_text, meta)

    meas_spec = extract_measurement_specification(question_text, meta)
    if meas_spec or cat_lower == "measurement":
        spec_text = meas_spec or extract_measurement_specification(question_text, meta)
        lines = []
        if spec_text:
            lines.append(spec_text)
        lines.append("- EXCEPTION FOR MEASURING INSTRUMENTS: Rulers, measuring jugs, water bottles, and scales MUST have clear, sharp, readable numbers and graduation marks showing the correct measurement from the question. Do NOT omit or blur markings on measuring tools.")
        return "\n".join(lines)

    # Dedicated handling for Playgroup (PG) and Nursery early years curriculum
    if (grade_id or "").upper() in ("PG", "NURSERY"):
        topic_lower = ((meta or {}).get("topic") or "").lower()
        visual_groups = (meta or {}).get("visual_groups") or []
        q_low = question_text.lower()
        grade_name = "NURSERY" if (grade_id or "").upper() == "NURSERY" else "PLAYGROUP"

        # 1. Colours and matching
        if topic_lower == "colours_and_matching" or "what colour" in q_low:
            vg = visual_groups[0] if visual_groups else {}
            item_name = vg.get("singular") or vg.get("plural") or "toy"
            col = vg.get("colour") or (meta.get("answer", {}).get("correct") if meta else "") or "colourful"
            return (
                f"MATHEMATICAL SCENE & STORYTELLING GUIDELINES ({grade_name} - COLOURS & MATCHING):\n"
                f"- ACTIVE MUTUAL INTERACTION: The characters must be actively playing and interacting together with the {item_name} "
                f"(e.g. in the water basin splashing and floating the duck together, in the apple orchard picking the apple, sailing the boat together). NO static table posing!\n"
                f"- EXACT OBJECT COUNT (PRECISELY 1): The scene must show PRECISELY ONE {item_name} visible in total, rendered in its vibrant {col} colour.\n"
                f"- ABSOLUTE BAN ON COUNTERS & DUPLICATES: ZERO extra duplicate items, ZERO stray ducks/balls, and ZERO plastic tokens/counters or circular disks anywhere on tables, floors, or in the background!\n"
                f"- ZERO TEXT OR LABELS: Never draw any colour words, letters, numbers, or labels anywhere in the scene."
            )

        # 2. Size, length, and comparison
        if topic_lower in ("size_and_comparison", "comparison") or any(k in q_low for k in ("big", "small", "tall", "short", "long", "which toy", "who has", "which one", "which tower", "which ball", "which ribbon")):
            return (
                f"MATHEMATICAL SCENE & STORYTELLING GUIDELINES ({grade_name} - SIZE & COMPARISON):\n"
                f"- ACTIVE CHARACTER INTERACTION & VISUAL CONTRAST: The characters are actively holding, twirling, building, or playing with the two items described in the question "
                f"(e.g. holding a tall block tower vs a short block tower, twirling a long ribbon vs a short ribbon on the gym floor, holding a big ball vs a small ball). "
                f"Both characters are enthusiastically showing and comparing their items together. NO static posing behind a table, NO pointing index fingers at empty paper!\n"
                f"- EXACT OBJECTS: PRECISELY the 2 objects mentioned in the question. Zero extra duplicate objects.\n"
                f"- ABSOLUTE BAN ON COUNTERS & DISKS: Do NOT draw any decorative rows of plastic counters, circular disks, or stray tokens anywhere on tables or rugs!\n"
                f"- ZERO TEXT OR LABELS: Never draw 'Big', 'Small', 'Tall', 'Short', letters, or numbers anywhere in the scene."
            )

        # 3. Spatial and position
        if topic_lower in ("spatial_and_position", "shapes_and_space") and any(k in q_low for k in ("where is", "where are", "under", "on the", "in the", "searching", "lost", "looking for")):
            vg = visual_groups[0] if visual_groups else {}
            item_name = vg.get("object_id") or vg.get("singular") or "item"
            pos_corr = (meta.get("answer", {}).get("correct") if meta else "") or ""
            return (
                f"MATHEMATICAL SCENE & STORYTELLING GUIDELINES ({grade_name} - SPATIAL & POSITION):\n"
                f"- ACTIVE CHARACTER INTERACTION: The characters are actively engaged together in the scene searching for, pointing towards, or reaching for the {item_name} in its natural location "
                f"(e.g. peeking down to find the toy car under the table, looking at the teddy bear on the armchair, or seeing the duck floating in the bath water).\n"
                f"- EXACT POSITION: The {item_name} must be clearly visible {pos_corr.lower() if pos_corr else 'in its designated position'} in the scene.\n"
                f"- EXACT OBJECTS: Only the exact item(s) described in the question. Zero extra clutter.\n"
                f"- ABSOLUTE BAN ON COUNTERS: ZERO decorative counters, disks, or stray duplicate items.\n"
                f"- ZERO TEXT OR LABELS: Never draw location labels, arrows, checkmarks, letters, or numbers anywhere in the scene."
            )

        # 4. Shapes
        if topic_lower == "shapes" or "what shape" in q_low or "shape is" in q_low:
            vg = visual_groups[0] if visual_groups else {}
            item_name = vg.get("object_id") or "object"
            shape_corr = vg.get("shape") or (meta.get("answer", {}).get("correct") if meta else "") or "shape"
            return (
                f"MATHEMATICAL SCENE & STORYTELLING GUIDELINES ({grade_name} - SHAPES):\n"
                f"- ACTIVE CHARACTER INTERACTION: The characters are actively handling, looking at, or sharing the real-world object described in the question "
                f"(e.g. holding a slice of pizza at the table, looking at the wall clock, reading the square book, or looking at the party flag).\n"
                f"- CLEAR GEOMETRIC PROPORTION: The {item_name} must be clearly and distinctly formed like a recognizable {shape_corr.lower()} (e.g. perfectly circular clock/plate, square book/block face, triangular pizza slice/bunting flag).\n"
                f"- ZERO TEXT OR LABELS: Never draw the words 'Circle', 'Square', 'Triangle', letters, or numbers anywhere on or near the item."
            )

        # 5. More or fewer
        if topic_lower == "more_or_fewer" or "more" in q_low or "fewer" in q_low:
            return (
                f"MATHEMATICAL SCENE & STORYTELLING GUIDELINES ({grade_name} - MORE OR FEWER):\n"
                f"- ACTIVE CHARACTER INTERACTION: Both characters are actively engaged together comparing their groups "
                f"(e.g. the child holding a basket with 4 apples, and the companion holding a basket with 1 apple). Both are happily interacting and looking at each other's items.\n"
                f"- EXACT COUNT FIDELITY: PRECISELY the distinct counts in each character's group. ZERO stray items anywhere else!\n"
                f"- ABSOLUTE BAN ON COUNTERS: Do NOT draw extra decorative counters, disks, or duplicate objects.\n"
                f"- ZERO TEXT OR LABELS: Never draw numbers, digits, words, or equations anywhere in the scene."
            )

        # 6. Patterns
        if topic_lower == "patterns" or "pattern" in q_low:
            return (
                f"MATHEMATICAL SCENE & STORYTELLING GUIDELINES ({grade_name} - PATTERNS):\n"
                f"- ACTIVE CHARACTER INTERACTION: Both characters are actively creating or completing the repeating pattern together "
                f"(e.g. stringing beads, arranging fruit on a platter, or decorating with balloons).\n"
                f"- CLEAR PATTERN SEQUENCE: The repeating sequence from the question must be clearly visible and organized in a neat, clear row.\n"
                f"- ABSOLUTE BAN ON COUNTERS: ZERO stray unrelated objects.\n"
                f"- ZERO TEXT OR LABELS: Never write numbers, letters, or answer words anywhere."
            )

        # 7. Measurement (heavy/light, full/empty)
        if topic_lower == "measurement" or any(k in q_low for k in ("heavy", "light", "full", "empty")):
            return (
                f"MATHEMATICAL SCENE & STORYTELLING GUIDELINES ({grade_name} - MEASUREMENT):\n"
                f"- ACTIVE CHARACTER INTERACTION & PHYSICAL REALISM: The characters are actively holding or carrying the items "
                f"(e.g. carrying a wooden toy chest vs holding a light balloon, or pouring from a full jug vs holding an empty jug).\n"
                f"- CLEAR VISUAL STATE: Full containers are visibly filled with liquid/items to the top; empty containers are completely clean and dry.\n"
                f"- ZERO TEXT OR LABELS: Never draw the words 'Full', 'Empty', 'Heavy', 'Light', or any labels."
            )

        # 8. Counting within 1 to 5
        cnt = 1
        if visual_groups and visual_groups[0].get("count"):
            cnt = int(visual_groups[0]["count"])
        elif meta and str(meta.get("answer", {}).get("correct")) in ("1", "2", "3", "4", "5"):
            cnt = int(meta["answer"]["correct"])
        else:
            found = re.findall(r"\b\d+\b", question_text)
            cnt = int(found[0]) if found else 2
        cnt = min(max(cnt, 1), 5)

        obj = "objects"
        if visual_groups and (visual_groups[0].get("plural") or visual_groups[0].get("singular")):
            obj = visual_groups[0].get("plural") or visual_groups[0].get("singular")

        return (
            f"MATHEMATICAL SCENE & STORYTELLING GUIDELINES ({grade_name} - COUNTING 1 TO 5):\n"
            f"- ACTIVE MUTUAL INTERACTION: The characters are actively interacting together with the items in their authentic setting "
            f"(e.g. twirling {cnt} gymnastics ribbons together in the dance studio, racing {cnt} toy cars on the carpet track, "
            f"picking {cnt} apples into their basket in the orchard, floating {cnt} toy ducks in the water tray, or stacking {cnt} blocks on the rug). "
            f"NO static table posing, NO pointing index fingers at a blank piece of paper!\n"
            f"- EXACT COUNT (PRECISELY {cnt} {obj}): The scene must show PRECISELY {cnt} {obj} in total in the active area, distinct, unobstructed, and clearly countable by a young child (1, 2...). ZERO extra or missing items!\n"
            f"- ABSOLUTE BAN ON EXTRA CLUTTER: Do NOT add any rows of plastic counters, circular disks, or stray duplicate items anywhere on tables or floors!\n"
            f"- ZERO TEXT OR NUMBERS: Never draw digits (1, 2, 3, 4, 5), numbers, or words anywhere in the scene."
        )

    # 2. Counting / Arithmetic Category
    try:
        from app.math_visual_engine import count_prompt_for_image
    except ImportError:
        from math_visual_engine import count_prompt_for_image  # type: ignore
    brief = count_prompt_for_image(question_text, meta)
    if not brief:
        return ""
    return (
        "MATHEMATICAL SCENE & STORYTELLING GUIDELINES:\n"
        f"{brief}\n"
        "- ZERO TEXT OR ANSWERS DRAWN: Never print numbers, formulas, or the answer in the scene."
    )


def derive_thematic_environment_and_attire(
    meta: "dict | None" = None,
    question_text: str = "",
    stem: "dict | None" = None,
    thematic_override: "dict | None" = None,
) -> dict[str, str]:
    """
    Derive an authentic real-world background environment and matching character uniforms/attire
    based on the objects, activities, and story described in the question.
    """
    if thematic_override and isinstance(thematic_override, dict) and thematic_override.get("prompt_block"):
        return thematic_override

    q_lower = (question_text or "").lower()

    # Collect all object names from meta visual_groups and question
    object_names = []
    if meta:
        for g in (meta.get("visual_groups") or []):
            for key in ("object_id", "singular", "plural", "item"):
                val = g.get(key)
                if val and isinstance(val, str):
                    object_names.append(val.lower())

    topic = ((stem or {}).get("topic") or "").lower()
    all_text = f"{q_lower} {' '.join(object_names)} {topic}"

    # -1.5. Gymnastics / Dance / Rhythmic Ribbons
    if any(k in all_text for k in ("ribbon", "ribbons", "gymnastic", "gymnastics", "dance", "ballet", "rhythmic")):
        return {
            "theme": "Vibrant Gymnastics Hall & Dance Studio",
            "environment": (
                "A bright, spacious, sunlit gymnastics hall and dance studio with polished sprung wooden flooring, "
                "colorful padded floor exercise mats, soft mirrored background wall reflecting warm daylight, "
                "and clean athletic training equipment. "
                "The atmosphere is joyful, open, and energetic. "
                "Both characters are actively twirling long, swirling colourful gymnastics ribbons on lightweight wands through the air with graceful, dancing expressions."
            ),
            "attire": (
                "The characters wear clean, colorful gymnastics training leotards, athletic dance t-shirts, "
                "stretchy leggings, and soft gymnastics slippers or barefoot on the mats, looking like graceful, enthusiastic young gymnasts."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A sunlit, vibrant gymnastics hall and dance studio with colorful exercise mats and wooden dance floor.\n"
                "- CHARACTER ATTIRE: Comfortable, sporty gymnastics training wear, athletic dance clothing, and gymnastics slippers.\n"
                "- ACTIVE INTERACTION: The characters are actively holding and twirling their long, swirling gymnastics ribbons on wands through the air with joyful, dynamic movement! NO sitting statically behind a table or pointing at paper!"
            )
        }

    # -1.2. Toy Cars / Race Track / Carpet Track
    if any(k in all_text for k in ("toy car", "toy cars", "racetrack", "race track", "carpet track", "road track")):
        return {
            "theme": "Playroom Carpet Racetrack & Toy Garage",
            "environment": (
                "A vibrant, cheerful children's playroom with a colourful racetrack rug laid out on the floor. "
                "The background features wooden toy garages, ramps, and low toy shelves under warm, natural room lighting. "
                "Both characters are down on the playroom rug or floor, actively rolling, racing, and driving toy cars along the painted road tracks with laughing, playful expressions."
            ),
            "attire": (
                "The characters wear colourful, comfortable toddler/child playwear (bright cotton t-shirts, hoodies, joggers, and socks or sneakers)."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A cheerful playroom with a colourful road-track play rug on the floor.\n"
                "- CHARACTER ATTIRE & PLAY: Both characters are down on the play rug actively racing and rolling their toy cars together along the tracks with joyful expressions! NO static posing behind a dining desk!"
            )
        }

    # -1. Gardening / Flower Pots / Plants / Garden Equipment
    if any(k in all_text for k in ("flower pot", "flowerpot", "flower pots", "watering can", "gardening", "garden", "sunflower", "tulip", "seed packet", "planting", "plant pot")):
        return {
            "theme": "Sunny Flower Garden & Potting Bench",
            "environment": (
                "A bright, sunny home flower garden with colorful blooming flowerbeds, terracotta pots, "
                "a charming wooden garden shed, green lawn, and sunlit outdoor atmosphere. "
                "The foreground features a clean wooden garden potting bench or lawn area where flower pots and gardening tools are neatly placed."
            ),
            "attire": (
                "The characters wear cute, colorful gardening aprons, casual gardening clothes, sun hats, "
                "or cheerful denim overalls, looking like happy young gardeners."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A bright, authentic sunny home flower garden. "
                "The background features blooming flowerbeds, green lawns, terracotta flower pots, and a garden shed.\n"
                "- CHARACTER ATTIRE: The characters wear cute gardening aprons or cheerful outdoor gardening clothes."
            )
        }

    # -0.5. Sports / Football / Tennis / Basketball / Pitch
    if any(k in all_text for k in ("football", "footballs", "soccer", "goal net", "pitch", "tennis", "basketball", "swimming", "sports")):
        return {
            "theme": "Vibrant Sports Ground & Athletic Field",
            "environment": (
                "A sunny, pristine green sports pitch or outdoor athletic court with white boundary markings, "
                "open park skies, and sports training markers. The sports balls and equipment are neatly positioned in the foreground."
            ),
            "attire": (
                "The characters wear clean, colorful athletic sports jerseys, shorts/tracksuits, and sporty trainers, looking energetic and ready to play."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A sunny, vibrant outdoor sports ground / pitch with green turf and sports equipment neatly in foreground.\n"
                "- CHARACTER ATTIRE: The characters wear athletic sports training jerseys and trainers."
            )
        }

    # 0. Noodles / Pasta / Soup / Meals / Kitchen Dining Table
    if any(k in all_text for k in ("noodle", "noodles", "pasta", "spaghetti", "soup", "broth", "ramen", "cereal", "porridge", "stew", "dinner", "lunch", "meal", "supper", "eating", "eat")):
        return {
            "theme": "Cozy Kitchen Dining Table & Meal Time",
            "environment": (
                "A warm, bright, authentic family kitchen and dining room. "
                "In the foreground is a clean wooden dining table neatly set for a meal. "
                "The background features a charming home kitchen with warm wood cabinetry, soft morning or afternoon window sunlight, "
                "and subtle homely kitchen accessories on shelves with gentle cinematic depth of field. "
                "The setting is clean, cozy, and unmistakably an authentic kitchen dining scene."
            ),
            "attire": (
                "The characters wear clean, comfortable, cheerful everyday casual clothing suitable for mealtime at home "
                "(e.g. neat colorful sweaters, casual shirts, or cute home aprons), looking cheerful and ready to enjoy their food."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A warm, authentic family kitchen and dining room. "
                "The foreground features a clean wooden dining table neatly set. The background shows cozy kitchen cabinets, "
                "warm window light, and homely kitchen decor with soft depth of field.\n"
                "- CHARACTER ATTIRE: Characters wear comfortable casual home attire or neat cooking/dining clothes."
            )
        }

    # 1. Bakery / Baking / Bread / Cakes / Pastries
    if any(k in all_text for k in ("bread", "loaf", "loaves", "baguette", "bake", "baking", "baker", "bakery", "cake", "cupcake", "muffin", "cookie", "biscuit", "croissant", "pastry", "pastries", "dough", "pie", "doughnut", "flour")):
        return {
            "theme": "Artisan Bakery & Pastry Kitchen",
            "environment": (
                "A warm, bustling, authentic artisan bakery and pastry shop kitchen. "
                "The background features rustic wooden shelving stocked with freshly baked golden bread loaves, "
                "baguettes, and pastries in woven wicker baskets, a clean flour-dusted wooden prep counter with baking tools, "
                "and the warm golden glow of a traditional brick baking oven in the background. "
                "The lighting is warm, inviting, and atmospheric, making it unmistakably a delightful authentic bakery."
            ),
            "attire": (
                "The characters MUST wear authentic bakery uniforms: clean white or striped baker's aprons, "
                "cute white baker or chef hats, and comfortable shirts with rolled-up sleeves, looking like cheerful, "
                "authentic professional bakers enthusiastically making their baked goods."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A warm, authentic artisan bakery and pastry kitchen. "
                "The background features rustic wooden bread racks holding fresh loaves, flour-dusted prep tables, "
                "and warm stone ovens with a golden glow.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear authentic bakery uniforms: "
                "baker's aprons, white/striped chef or baker hats, and rolled-up sleeves, looking like real proud bakers."
            )
        }

    # 2. Apples / Orchard / Fruit Picking / Fruit Garden
    if any(k in all_text for k in ("apple", "apples", "orchard", "pear", "pears", "peach", "peaches", "plum", "orange", "oranges", "cherry", "cherries", "berry", "berries", "strawberry", "fruit")):
        return {
            "theme": "Sunny Apple Orchard & Fruit Garden",
            "environment": (
                "A sunlit, picturesque apple garden and fruit orchard. "
                "The background features healthy, leafy green apple trees brimming with ripe red apples, "
                "rustic wooden harvesting crates filled with fresh fruit, soft dappled golden sunlight filtering through the branches, "
                "and manicured green grass under a bright sunny sky. The atmosphere is fresh, vibrant, and natural."
            ),
            "attire": (
                "The characters MUST wear authentic fruit-picker / gardening attire: cute denim dungarees / overalls, "
                "sun hats or neat flat caps, gardening aprons, and outdoor boots, looking like happy gardeners gathering delicious fruit."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A lush, sun-drenched outdoor apple orchard and fruit garden. "
                "The background features leafy apple trees laden with ripe apples, wooden harvesting crates, and green lawn.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear authentic gardening/fruit-picker attire: "
                "cute denim overalls/dungarees, sun hats or gardening aprons, and practical outdoor clothes."
            )
        }

    # 3. Vegetables / Planting / Allotment / Greenhouse
    if any(k in all_text for k in ("carrot", "carrots", "potato", "potatoes", "tomato", "tomatoes", "vegetable", "vegetables", "plant", "planting", "seed", "seeds", "greenhouse", "allotment", "garden", "gardening", "flower", "flowers", "sunflower", "blossom", "pot", "watering can")):
        return {
            "theme": "Lush Vegetable Garden & Greenhouse",
            "environment": (
                "A thriving, vibrant vegetable garden and glasshouse nursery. "
                "The background features raised wooden planting beds with healthy green vegetable tops, terracotta pots with flowers, "
                "a vintage metal watering can, wooden trellises, and sunny garden greenery under bright natural daylight."
            ),
            "attire": (
                "The characters MUST wear authentic gardening outfits: sturdy denim dungarees, gardening gloves in pockets, "
                "sun hats, and comfortable earth-toned garden shirts, looking like enthusiastic young gardeners."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A flourishing vegetable garden and sunlit greenhouse with raised planting beds, "
                "terracotta pots, and lush garden foliage.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear cute gardening attire: denim overalls/dungarees, "
                "sun hats, and practical gardening shirts."
            )
        }

    # 4. Beach / Seaside / Ocean / Shells / Marine
    if any(k in all_text for k in ("shell", "shells", "seashell", "starfish", "crab", "crabs", "beach", "seaside", "sand", "sandcastle", "ocean", "sea", "wave", "waves", "fish", "pebble", "pebbles", "tide")):
        return {
            "theme": "Sunny Seaside Beach & Ocean Shore",
            "environment": (
                "A bright, beautiful seaside beach with clean golden sand. "
                "The background features gentle turquoise ocean waves washing onto the shore under a clear blue sky, "
                "coastal sand dunes, and gentle ocean spray in natural sunny coastal daylight."
            ),
            "attire": (
                "The characters MUST wear cheerful summer seaside outfits: light breezy t-shirts, sun hats, shorts, "
                "and beach sandals, dressed perfectly for a warm day exploring the seashore."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A sunlit coastal beach with golden sand, soft turquoise ocean waves, "
                "and clear blue sky in the background.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear summer beachwear: light t-shirts, sun hats, "
                "and comfortable sunny day beach clothes."
            )
        }

    # 5. Farm / Barnyard / Farm Animals / Countryside
    if any(k in all_text for k in ("farm", "barn", "sheep", "lamb", "cow", "cows", "horse", "horses", "pig", "pigs", "chicken", "chickens", "hen", "hens", "egg", "eggs", "tractor", "hay", "pasture", "meadow", "pen")):
        return {
            "theme": "Picturesque Countryside Farm & Barn",
            "environment": (
                "A charming British countryside farm and barnyard. "
                "The background features a traditional rustic red timber barn, post-and-rail wooden farm fences, "
                "green rolling pastures, and golden hay bales under a bright countryside sky."
            ),
            "attire": (
                "The characters MUST wear authentic country farm clothing: checked flannel shirts, denim jeans or overalls, "
                "and classic countryside farm boots."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A picturesque countryside farm with a rustic red barn, wooden fences, "
                "and green pastures in the background.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear country farm outfits: plaid/flannel shirts, "
                "denim jeans or overalls, and farm boots."
            )
        }

    # 5.5. Lego / Building Blocks / Brick Workshop
    if any(k in all_text for k in ("lego", "brick", "bricks", "building block", "building blocks", "block tower")):
        return {
            "theme": "Vibrant Lego & Block Construction Workshop",
            "environment": (
                "A bright, cheerful children's Lego and construction playroom workshop. "
                "The background features organized sorting bins with colourful building bricks, Lego creations displayed on low wooden shelves, "
                "and a soft, clean play rug. Both characters are actively sitting or kneeling together on the play rug, "
                "cooperatively building a colourful Lego block tower together (one character placing a brick on top while the other holds the structure)."
            ),
            "attire": (
                "The characters wear colourful, playful, comfortable casual clothes (bright t-shirts, hoodies, sneakers), "
                "looking like enthusiastic young builders."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A cheerful Lego and block construction playroom with brick organizers and play rug.\n"
                "- CHARACTER ATTIRE & COOPERATIVE PLAY: Characters wear bright casual clothes and are actively building a Lego block tower together on the rug."
            )
        }

    # 5.6. Wall Clock / Analog Clock / Time
    if any(k in all_text for k in ("clock", "wall clock", "time", "o'clock", "half past", "quarter past", "quarter to")):
        return {
            "theme": "Cozy Room with Analog Wall Clock",
            "environment": (
                "A warm, beautifully lit living room or study corner with a large, clear, prominent analog wall clock mounted on the wall. "
                "Both characters are standing together looking up towards the wall clock, one character gesturing towards the clock face and hands "
                "while the other looks attentively at the time, sharing a moment of curiosity."
            ),
            "attire": (
                "The characters wear neat, comfortable casual everyday clothes (sweaters, cardigans, or collared shirts)."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A cozy room with a clear analog wall clock mounted prominently on the wall.\n"
                "- CHARACTER ATTIRE & INTERACTION: Characters are looking up at the wall clock together, pointing at the clock hands."
            )
        }

    # 5.7. Angles / Geometric Play / Ramp & Incline Slide
    if any(k in all_text for k in ("angle", "angles", "ramp", "perpendicular", "incline", "geometry", "geometric")):
        return {
            "theme": "Playful Geometric Movement & Activity Zone",
            "environment": (
                "A vibrant, playful children's movement and geometry exploratory play space with soft colourful geometric foam modules: "
                "a triangular incline ramp/slide, perpendicular climbing blocks, cylinders, and cubes on a padded colourful play floor. "
                "The characters are actively interacting with the shapes (e.g. one sliding down the triangular incline ramp while the other climbs the perpendicular side or holds matching shape cutouts)."
            ),
            "attire": (
                "The characters wear sporty, flexible playwear (bright cotton t-shirts, joggers/tracksuits, and sneakers) suited for active movement."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A playful children's geometric activity zone with colourful triangular ramps and soft foam shapes.\n"
                "- CHARACTER ATTIRE & INTERACTION: Characters actively interact with the shapes (one sliding down the triangular ramp, the other climbing the perpendicular side)."
            )
        }

    # 6. Toys / Playroom / Workshop
    if any(k in all_text for k in ("toy", "toys", "block", "blocks", "train", "trains", "car", "cars", "doll", "dolls", "teddy", "robot", "robots", "playroom", "puzzle")):
        return {
            "theme": "Vibrant Playroom & Toy Workshop",
            "environment": (
                "A cheerful, bright children's playroom and wooden toy workshop. "
                "The background features colorful wooden storage cubbies neatly holding toys, building block stations, "
                "playful wall decor, and soft play mats under warm, friendly lighting."
            ),
            "attire": (
                "The characters MUST wear colorful, playful, comfortable casual children's clothes (bright t-shirts, hoodies, sneakers)."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A cheerful children's playroom with colorful wooden toy cubbies and play areas.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear bright, playful, casual children's clothing."
            )
        }

    # 7. Hands-on Science & Practical Measurement Workbench (ruler, measuring jug, water bottle, scale)
    if any(k in all_text for k in ("measure", "measurement", "ruler", "capacity", "jug", "water jug", "litre", "litres", "millilitre", "millilitres", "scale", "weigh")):
        return {
            "theme": "Bright Hands-On Science & Measurement Workbench",
            "environment": (
                "A bright, sunlit practical measurement workstation or school science table. "
                "In the foreground is a clear, uncluttered wooden workbench where the measuring instruments (centimetre ruler, clear transparent measuring jug, water bottle, or scale) "
                "are placed flat and upright facing forward with complete clarity and perfect visibility. "
                "The background features a cheerful learning space or home science corner with gentle warm lighting and soft cinematic depth of field."
            ),
            "attire": (
                "The characters wear neat, comfortable practical learning attire (such as smart collared shirts, school jumpers, or practical activity aprons with rolled-up sleeves)."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A bright, clean measurement workstation with tools placed clearly in the foreground.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters wear neat practical student/activity attire with rolled-up sleeves."
            )
        }

    # 8. Library / Study / Books / School
    if any(k in all_text for k in ("book", "books", "library", "reading", "read", "pencil", "pencils", "crayon", "crayons", "desk", "stationery")):
        return {
            "theme": "Charming Library & Study Corner",
            "environment": (
                "A cozy, beautiful children's library or bright study room. "
                "The background features tall, warm oak bookshelves lined with colorful storybooks, arched sunny windows, "
                "and polished wooden study tables."
            ),
            "attire": (
                "The characters MUST wear smart-casual student attire: neat collared shirts, knit cardigans or school jumpers."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A cozy library with warm oak bookshelves packed with colorful books.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear neat student attire: collared shirts or cozy cardigans."
            )
        }

    # 8. Sports / Playground / Athletics
    if any(k in all_text for k in ("ball", "balls", "football", "basketball", "tennis", "race", "running", "playground", "swing", "slide", "pitch", "goal", "sport", "sports")):
        return {
            "theme": "Sunny Sports Field & Playground",
            "environment": (
                "A vibrant outdoor sports field or school playground. "
                "The background features lush green playing turf, running tracks, sports nets, and playground equipment under a bright blue sky."
            ),
            "attire": (
                "The characters MUST wear athletic sports kits: sports jerseys, shorts, sweatbands, and running trainers."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A sunny green sports field and playground with turf and track in the background.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear athletic sports jerseys, shorts, and trainers."
            )
        }

    # 9. Supermarket / Grocery / Market Stall / Shopping
    if any(k in all_text for k in ("shop", "shopping", "supermarket", "market", "stall", "coin", "coins", "money", "penny", "pence", "pound", "pounds", "cash", "buy", "price")):
        return {
            "theme": "Farmers Market Stall & Village Grocery",
            "environment": (
                "A bustling, charming village farmers' market stall and grocery shop. "
                "The background features wooden market crates, striped fabric awnings, chalkboard price signs, and wicker shopping baskets."
            ),
            "attire": (
                "The characters MUST wear market-stall aprons or neat shopper coats with canvas tote bags."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A colorful farmers market stall with wooden crates and striped awnings.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear market aprons or neat shopping outfits."
            )
        }

    # 10. Space / Science / Astronomy
    if any(k in all_text for k in ("star", "stars", "planet", "planets", "space", "rocket", "telescope", "science", "lab", "magnet", "experiment")):
        return {
            "theme": "Starlit Observatory & Science Discovery Room",
            "environment": (
                "An inspiring astronomy observatory or science discovery room with brass telescopes, star charts, glowing globes, and deep blue starry cosmos."
            ),
            "attire": (
                "The characters MUST wear white science lab coats, astronomer jumpers, or science explorer vests."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: An atmospheric astronomy observatory with brass telescopes and star maps.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear science lab coats or astronomer vests."
            )
        }

    # 11. Picnic / Park / Outdoor Lunch
    if any(k in all_text for k in ("picnic", "sandwich", "sandwiches", "lemonade", "juice", "park", "blanket")):
        return {
            "theme": "Sunny Park Picnic",
            "environment": (
                "A picturesque sunny public park under graceful shady trees, with a red checkered picnic blanket, wicker basket, and lush green lawn."
            ),
            "attire": (
                "The characters MUST wear sunny casual picnic clothes: polo shirts, sundresses, or light summer attire."
            ),
            "prompt_block": (
                "- ENVIRONMENT & BACKGROUND: A sunny park meadow under leafy trees with a picnic blanket.\n"
                "- CHARACTER ATTIRE & UNIFORM: The characters MUST wear casual summer picnic attire."
            )
        }

    # Fallback to intelligent extraction from question text
    extracted_obj = object_names[0] if object_names else "items"
    return {
        "theme": f"Real-World Setting for {extracted_obj.title()}",
        "environment": (
            f"A vibrant, authentic, photorealistic real-world setting specifically matching the {extracted_obj} "
            f"and activity described in the question. Render a complete, richly detailed background (never a blank wall or empty studio) "
            f"with natural environmental context and atmospheric lighting."
        ),
        "attire": (
            f"The characters MUST wear authentic clothing and uniforms that naturally and realistically belong to this setting "
            f"and the activity of working with {extracted_obj}."
        ),
        "prompt_block": (
            f"- ENVIRONMENT & BACKGROUND: An authentic real-world environment matching {extracted_obj}.\n"
            f"- CHARACTER ATTIRE & UNIFORM: The characters MUST wear clothing/uniforms appropriate for this activity."
        )
    }


def build_generation_prompt(
    question_text: str,
    character_context: "str | None" = None,
    count_context: "str | None" = None,
    thematic_context: "str | None" = None,
    grade_id: str = "",
    favourite_colour: str = "",
    child_gender: str = "",
    user_name: str = "",
) -> str:
    """
    Use the grade's question_image.md as the prompt.

    The file does not need [PASTE ONE QUESTION HERE]. If it contains
    {question} or the old placeholder, those are filled. Otherwise the
    selected question is added at the end.
    """
    del character_context, count_context, thematic_context, favourite_colour, child_gender
    template = _load_prompt_template(grade_id)
    question = (question_text or "").strip()
    grade = (grade_id or "").replace("_", " ").strip()
    child = (user_name or "").strip()
    prompt = template.replace(PLACEHOLDER, question)
    prompt = prompt.replace("{question}", question)
    prompt = prompt.replace("{grade}", grade)
    prompt = prompt.replace("{uploaded_person_images}", "attached reference photos")
    if question and question not in prompt:
        prompt = f"{prompt.rstrip()}\n\nSELECTED QUESTION:\n{question}\n"
    if child and "{child_name}" in prompt:
        prompt = prompt.replace("{child_name}", child)
    return prompt




# ── low-level API call ──────────────────────────────────────────────────────

def _call_image_provider(
    prompt: str,
    *,
    provider: str,
    api_key: str,
    model: str,
    image_entries: "list[tuple[str, str]] | list[str] | None" = None,
    count_context: "str | None" = None,
    thematic_context: "str | None" = None,
    character_context: "str | None" = None,
    child_gender: str = "",
    user_name: str = "",
    favourite_colour: str = "",
    timeout: int = 180,
) -> "Image.Image | None":
    """Route a generation request to OpenRouter, OpenAI, or Gemini."""
    pid = (provider or "openrouter").strip().lower()
    if pid in ("openai", "gemini"):
        from app.image_providers import ProviderImageError, generate_provider_image
        try:
            compact = _build_compact_prompt(
                prompt,
                count_context=count_context,
                thematic_context=thematic_context,
                character_context=character_context,
                child_gender=child_gender,
                user_name=user_name,
                favourite_colour=favourite_colour,
            )
        except Exception:
            compact = prompt
        try:
            return generate_provider_image(
                provider=pid,
                model=model,
                api_key=api_key,
                prompt=compact,
                image_entries=image_entries,
                timeout=timeout,
            )
        except ProviderImageError as exc:
            raise ImageGenError(str(exc)) from exc
    return _call_openrouter(
        prompt,
        api_key=api_key,
        model=model,
        image_entries=image_entries,
        count_context=count_context,
        thematic_context=thematic_context,
        character_context=character_context,
        child_gender=child_gender,
        user_name=user_name,
        favourite_colour=favourite_colour,
        timeout=timeout,
    )


def _call_openrouter(
    prompt: str,
    *,
    api_key: str,
    model: str,
    image_entries: "list[tuple[str, str]] | list[str] | None" = None,
    count_context: "str | None" = None,
    thematic_context: "str | None" = None,
    character_context: "str | None" = None,
    child_gender: str = "",
    user_name: str = "",
    favourite_colour: str = "",
    timeout: int = 180,
) -> "Image.Image | None":
    """
    POST prompt + optional reference photos to OpenRouter; return PIL Image or None.

    Automatically routes the request to the correct OpenRouter endpoint:
      - openai/gpt-image-* models  →  POST /api/v1/images  (dedicated image generation)
      - all other models           →  POST /api/v1/chat/completions  (legacy / vision path)
    """
    import requests

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://kids-books-ai.local",
        "X-Title": "Kids Books AI - Image Generator",
    }

    # ── Dedicated /images endpoint (gpt-image-2 and family) ──────────────────
    if _uses_image_endpoint(model):
        return _call_openrouter_images(
            prompt,
            api_key=api_key,
            model=model,
            image_entries=image_entries,
            count_context=count_context,
            thematic_context=thematic_context,
            character_context=character_context,
            child_gender=child_gender,
            user_name=user_name,
            favourite_colour=favourite_colour,
            timeout=timeout,
            headers=headers,
        )

    # ── Legacy /chat/completions endpoint ────────────────────────────────────
    content_items: list[dict] = []

    if image_entries:
        for entry in image_entries:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                label, img_path = entry[0], entry[1]
            else:
                label, img_path = "", entry

            try:
                data_url = _path_to_data_url(img_path)
                if label:
                    content_items.append({"type": "text", "text": f"Reference photo for {label}:"})
                content_items.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    }
                )
                print(f"    [REF] Added reference photo: {Path(img_path).name} ({label or 'reference'})")
            except Exception as exc:
                print(f"    [WARN] Could not load reference photo {img_path}: {exc}")

    # Text prompt is always last (so the model sees context after images)
    content_items.append({"type": "text", "text": prompt})

    payload: dict = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": content_items,
            }
        ],
    }

    return _do_post_and_decode(OPENROUTER_URL, headers, payload, timeout)


def _extract_question_clean(full_prompt: str) -> str:
    """Extract the question text between the question marker and the next section."""
    for marker in ("# QUESTION TO VISUALISE", "QUESTION TO VISUALISE", "# QUESTION"):
        idx = full_prompt.find(marker)
        if idx != -1:
            after = full_prompt[idx + len(marker):]
            lines = after.split("\n")
            clean_lines = []
            started = False
            for line in lines:
                s = line.strip()
                if not started:
                    if s.startswith("━") or not s:
                        continue
                    started = True
                if s.startswith("━") or s.startswith("# GENERATE") or s.startswith("# CHARACTERS") or s.startswith("# MANDATORY"):
                    break
                clean_lines.append(line)
            res = "\n".join(clean_lines).strip()
            if res:
                return res
    return ""


def _build_compact_prompt(
    full_prompt: str,
    *,
    count_context: "str | None" = None,
    thematic_context: "str | None" = None,
    character_context: "str | None" = None,
    child_gender: str = "",
    user_name: str = "",
    favourite_colour: str = "",
    max_chars: int = 3500,
) -> str:
    """Send the grade prompt as written. Do not add system rules or cut the text."""
    del count_context, thematic_context, character_context, child_gender, user_name, favourite_colour, max_chars
    text = (full_prompt or "").strip()
    print(f"  [INFO] Prompt sent: {len(text)} chars")
    return text


def _call_openrouter_images(
    prompt: str,
    *,
    api_key: str,
    model: str,
    image_entries: "list[tuple[str, str]] | list[str] | None" = None,
    count_context: "str | None" = None,
    thematic_context: "str | None" = None,
    character_context: "str | None" = None,
    child_gender: str = "",
    user_name: str = "",
    favourite_colour: str = "",
    timeout: int = 180,
    headers: "dict | None" = None,
) -> "Image.Image":
    """
    Call the OpenRouter /api/v1/images endpoint used by gpt-image-2 and similar.

    The /api/v1/images endpoint has a strict ~4,000 character prompt limit.
    Our full prompt.md is ~26,000 characters. This function automatically
    builds a compact prompt (≤3,500 chars) that prioritizes child gender,
    exclusivity, thematic background, and exact quantities.

    Reference photos are passed via input_references for character personalisation.
    """
    if headers is None:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://kids-books-ai.local",
            "X-Title": "Kids Books AI - Image Generator",
        }

    # ── Condense the prompt to fit the /images endpoint character limit ─────
    compact_prompt = _build_compact_prompt(
        prompt,
        count_context=count_context,
        thematic_context=thematic_context,
        character_context=character_context,
        child_gender=child_gender,
        user_name=user_name,
        favourite_colour=favourite_colour,
    )

    # ── Build input_references from photo entries ────────────────────────────
    # OpenRouter /api/v1/images schema:
    #   { "type": "image_url", "image_url": { "url": "data:image/...;base64,..." } }
    input_references: list[dict] = []
    if image_entries:
        for entry in image_entries:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                label, img_path = entry[0], entry[1]
            else:
                label, img_path = "", entry
            try:
                data_url = _path_to_data_url(img_path)
                input_references.append({
                    "type": "image_url",
                    "image_url": {"url": data_url},
                })
                print(f"    [REF] Added reference photo: {Path(img_path).name} ({label or 'reference'})")
            except Exception as exc:
                print(f"    [WARN] Could not load reference photo {img_path}: {exc}")

    try:
        from app.workbook_layout import IMAGE_PX_H, IMAGE_PX_W
    except ImportError:
        from workbook_layout import IMAGE_PX_H, IMAGE_PX_W  # type: ignore

    payload: dict = {
        "model": model,
        "prompt": compact_prompt,
        "n": 1,
        "size": f"{IMAGE_PX_W}x{IMAGE_PX_H}",
    }
    if input_references:
        payload["input_references"] = input_references

    return _do_post_and_decode(OPENROUTER_IMAGES_URL, headers, payload, timeout)


def _do_post_and_decode(
    url: str,
    headers: dict,
    payload: dict,
    timeout: int,
) -> "Image.Image":
    """
    POST payload to url, parse the response, and return a PIL Image.
    Raises ImageGenError with the full API error message on any failure
    so the error surfaces directly in the UI.
    """
    import requests, json as _json

    # Log payload size for diagnosis
    try:
        payload_size = len(_json.dumps(payload))
        print(f"  [INFO] POST {url}  |  payload {payload_size:,} bytes")
    except Exception:
        pass

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except Exception as exc:
        raise ImageGenError(f"Network error: {exc}") from exc

    if resp.status_code != 200:
        # Full response text so the real reason is visible
        full_text = (resp.text or "")[:1000]
        raise ImageGenError(f"HTTP {resp.status_code}: {full_text}")

    try:
        data = resp.json()
    except Exception as exc:
        raise ImageGenError(f"Could not parse JSON response: {resp.text[:300]}") from exc

    # API-level error embedded inside a 200 response
    if data.get("error"):
        raise ImageGenError(f"API error: {str(data['error'])[:600]}")

    img_ref = _extract_image_url(data)
    if not img_ref:
        raise ImageGenError(f"No image in response: {str(data)[:500]}")

    if img_ref.startswith("data:image"):
        try:
            b64 = img_ref.split(",", 1)[1]
            return Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")
        except Exception as exc:
            raise ImageGenError(f"base64 decode failed: {exc}") from exc

    if img_ref.startswith("http"):
        try:
            import requests as _req
            r = _req.get(img_ref, timeout=60)
            if r.ok:
                return Image.open(BytesIO(r.content)).convert("RGB")
            raise ImageGenError(f"Image URL returned HTTP {r.status_code}")
        except ImageGenError:
            raise
        except Exception as exc:
            raise ImageGenError(f"Download image URL failed: {exc}") from exc

    raise ImageGenError(f"Unknown image reference format: {img_ref[:100]}")


# ── public generation function ──────────────────────────────────────────────

def generate_image_for_question(
    question_text: str,
    out_path: "str | Path",
    *,
    face_paths: "dict[str, str] | None" = None,
    image_entries: "list[tuple[str, str]] | list[str] | None" = None,
    character_context: "str | None" = None,
    count_context: "str | None" = None,
    thematic_context: "str | None" = None,
    max_attempts: "int | None" = None,
    model: "str | None" = None,
    api_key: "str | None" = None,
    grade_id: str = "",
    favourite_colour: str = "",
    child_gender: str = "",
    user_name: str = "",
    category: str = "counting",
    meta: "dict | None" = None,
) -> "tuple[Path | None, str]":
    """
    Generate a personalised educational scene image.

    Sends:
        prompt.md  +  question text  +  thematic environment/attire  +  count specification  +  character reference photos
    to the OpenRouter AI image model and saves the result.
    """
    rt = _active_runtime(model, api_key)
    _key = (rt.get("api_key") or "").strip()
    _model = (rt.get("model") or IMAGE_GEN_MODEL or "openai/gpt-image-2").strip()
    _provider = (rt.get("provider") or "openrouter").strip().lower()
    if not _key:
        return None, (
            f"No API key configured for {_provider}. "
            "Add it in the Admin panel (Models) or in .env and restart."
        )
    _attempts = max_attempts if max_attempts is not None else IMAGE_GEN_MAX_ATTEMPTS

    try:
        prompt = build_generation_prompt(
            question_text,
            character_context=character_context,
            count_context=count_context,
            thematic_context=thematic_context,
            grade_id=grade_id,
            favourite_colour=favourite_colour,
            child_gender=child_gender,
            user_name=user_name,
        )
    except Exception as exc:
        return None, f"Prompt build error: {exc}"

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Build reference photo entries if not explicitly provided
    if image_entries is None and face_paths:
        ordered_paths = _ordered_photo_paths(face_paths)
        path_to_role = {str(Path(v)): k for k, v in face_paths.items() if v}
        image_entries = []
        for p in ordered_paths:
            role = path_to_role.get(str(Path(p)), "reference")
            label = "Child" if role in ("user", "child") else role.title()
            image_entries.append((label, p))

    ref_list = image_entries or []
    last_err = ""

    for attempt in range(1, _attempts + 1):
        n_photos = len(ref_list)
        print(
            f"  [GEN] Attempt {attempt}/{_attempts}: {out_path.name} "
            f"({n_photos} reference photo(s))"
        )
        try:
            result = _call_image_provider(
                prompt,
                provider=_provider,
                api_key=_key,
                model=_model,
                image_entries=ref_list or None,
                count_context=count_context,
                thematic_context=thematic_context,
                character_context=character_context,
                child_gender=child_gender,
                user_name=user_name,
                favourite_colour=favourite_colour,
            )
            try:
                from app.workbook_layout import to_question_image
            except ImportError:
                from workbook_layout import to_question_image  # type: ignore
            result = to_question_image(result)
            result.save(str(out_path), "PNG")
            # More than 10 objects go on the counting board in front of the picture.
            skip_board = (category or "").strip().lower() in ("time", "measurement", "geometry", "patterns")
            if not skip_board:
                try:
                    from app.math_visual_engine import prepare_question_board, composite_math_card_into_image
                except ImportError:
                    from math_visual_engine import prepare_question_board, composite_math_card_into_image  # type: ignore
                try:
                    board = prepare_question_board(question_text, meta=meta, grade_id=grade_id)
                    if board is not None:
                        composite_math_card_into_image(out_path, out_path, board)
                except Exception as comp_err:
                    print(f"  [MATH-COMPOSITE WARN] {comp_err}")
            msg = (
                f"Generated on attempt {attempt} using {_model} "
                f"with {n_photos} reference photo(s)"
            )
            print(f"  [OK]  {out_path.name}: {msg}")
            return out_path, msg
        except ImageGenError as exc:
            last_err = str(exc)
            print(f"  [ERR] Attempt {attempt} failed: {last_err}")
        except Exception as exc:
            last_err = f"Unexpected error: {exc}"
            print(f"  [ERR] Attempt {attempt} unexpected: {last_err}")

        if attempt < _attempts:
            wait = 3 * attempt
            print(f"  [RETRY] Waiting {wait}s before next attempt...")
            time.sleep(wait)

    return None, f"Image generation failed after {_attempts} attempt(s) with {_model} | {last_err}"


# ── workbook-level batch builder ────────────────────────────────────────────

def build_workbook_items_ai_generated(
    stems: list,
    *,
    user_name: str,
    family_names: "dict | None" = None,
    face_paths: "dict[str, str] | None" = None,
    child_gender: str = "",
    out_dir: "str | Path | None" = None,
    on_progress=None,
    max_attempts: "int | None" = None,
    model: "str | None" = None,
    skip_on_error: bool = True,
    grade_id: str = "",
    max_workers: int = 4,
    fav_color: str = "",
    favourite_colour: str = "",
    favourite_foods: "list | None" = None,
    favourite_sports: "list | None" = None,
    favourite_hobbies: "list | None" = None,
    favourite_characters: "list | None" = None,
    favourite_cartoons: "list | None" = None,
) -> "tuple[list, list]":
    """
    Generate fresh AI images for every selected stem concurrently and return PDF-ready items.
    """
    import concurrent.futures
    import threading

    try:
        from app.stem_pipeline import (
            display_name_for_role,
            fill_question_text,
            mcq_from_meta,
            topic_label as _topic_label,
        )
    except ImportError:
        from stem_pipeline import (  # type: ignore
            display_name_for_role,
            fill_question_text,
            mcq_from_meta,
            topic_label as _topic_label,
        )

    if not (grade_id or "").strip():
        raise ValueError(
            "grade_id is required for image generation. "
            "Refusing to load another grade's question prompt."
        )
    _family_names = family_names or {}
    if not out_dir:
        raise ValueError(
            "out_dir is required. Generated images must be written to "
            "runtime/jobs/<job_id>/generated_images/."
        )
    _out_dir = Path(out_dir)
    _out_dir.mkdir(parents=True, exist_ok=True)

    total = len(stems)
    task_items = []

    for i, stem in enumerate(stems, start=1):
        stem_id = stem.get("stem_id", f"stem_{i}")
        meta = stem.get("meta") or {}
        role = (stem.get("template_adult_role") or "").strip().lower()

        # Step 1: fill question placeholders (child name, family names, pronouns)
        raw_q = stem.get("question_template") or ""
        filled_q = fill_question_text(
            raw_q,
            user_name=user_name,
            adult_role=role or "mother",
            family_names=_family_names,
            child_gender=child_gender,
        )

        # Question text stays as written in the bank. Favourites do not rename the objects.
        thematic_override = None

        # Step 2: identify characters in this question & attach matching reference photos
        stem_entries: list[tuple[str, str]] = []
        char_lines: list[str] = []

        is_girl = (child_gender or "").strip().lower() in ("girl", "female", "f")
        gender_desc = "female girl with feminine facial features and long hair" if is_girl else "male boy" if (child_gender or "").strip().lower() in ("boy", "male", "m") else (child_gender or "British child")

        # Child is always the primary character
        child_photo = (face_paths or {}).get("user") or (face_paths or {}).get("child")
        if child_photo and Path(child_photo).exists():
            stem_entries.append((f"Child ({user_name})", child_photo))
            char_lines.append(
                f"- Character 1: {user_name} (Primary Child, strictly a {gender_desc}). "
                f"CRITICAL IDENTITY MATCH: Facial features, eyes, smile, skin tone, hair length, ethnicity, and gender "
                f"MUST 100% faithfully match Reference Photo 1. The child must be the exact same person as on the front cover."
            )
        else:
            char_lines.append(
                f"- Character 1: {user_name} (Primary Child, strictly a {gender_desc})."
            )

        # Sibling or adult family member in this question
        adult_display = ""
        if role:
            adult_display = display_name_for_role(role, _family_names)
            # Look up role photo or fallback to sibling mappings
            role_photo = (face_paths or {}).get(role)
            if not role_photo and role in ("sibling", "brother", "sister"):
                for alt in ("sister", "brother", "sibling"):
                    if (face_paths or {}).get(alt):
                        role_photo = (face_paths or {})[alt]
                        break
            if role_photo and Path(role_photo).exists():
                ref_idx = len(stem_entries) + 1
                stem_entries.append((f"{role.title()} ({adult_display})", role_photo))
                char_lines.append(
                    f"- Character {ref_idx}: {adult_display} ({role.title()}). "
                    f"CRITICAL IDENTITY MATCH: Facial features, eyes, skin tone, hair, age, and appearance "
                    f"MUST 100% faithfully match Reference Photo {ref_idx}."
                )
            elif adult_display:
                ref_idx = len(stem_entries) + 1
                char_lines.append(
                    f"- Character {ref_idx}: {adult_display} ({role.title()})."
                )

        char_context = ""
        if char_lines:
            char_context = (
                "Characters appearing in this scene:\n"
                + "\n".join(char_lines)
                + "\nAll human characters must be predominantly camera-facing and actively engaged in the learning activity."
                + "\nSTRICT EXCLUSIVITY: ONLY these characters may appear. ZERO other people, ZERO extra boys, ZERO bystanders, ZERO original template characters."
            )

        # Step 3: compute exact category & mathematical count context from meta.json
        cat = (stem.get("category") or (meta.get("category") or "")).strip().lower()
        if not cat:
            try:
                from app.stem_pipeline import infer_stem_category
                cat = infer_stem_category(meta, topic=stem.get("topic") or "", question=filled_q)
            except Exception:
                cat = "counting"

        count_context = build_count_specification(meta, filled_q, grade_id=grade_id, category=cat)
        out_path = _out_dir / f"{i:02d}_{stem_id}.png"

        # Step 4: derive authentic thematic background environment & matching character uniforms/attire
        thematic_info = derive_thematic_environment_and_attire(meta, filled_q, stem, thematic_override=thematic_override)
        thematic_context = thematic_info.get("prompt_block")

        task_items.append({
            "index": i,
            "stem": stem,
            "stem_id": stem_id,
            "meta": meta,
            "category": cat,
            "role": role,
            "adult_display": adult_display,
            "filled_q": filled_q,
            "out_path": out_path,
            "stem_entries": stem_entries,
            "char_context": char_context,
            "count_context": count_context,
            "thematic_context": thematic_context,
        })

    items: list = []
    skipped: list = []
    completed_count = 0
    progress_lock = threading.Lock()

    def _worker(task: dict) -> dict:
        nonlocal completed_count
        i = task["index"]
        stem_id = task["stem_id"]
        try:
            img_path, gen_msg = generate_image_for_question(
                task["filled_q"],
                task["out_path"],
                face_paths=face_paths,
                image_entries=task["stem_entries"] or None,
                character_context=task["char_context"] or None,
                count_context=task["count_context"] or None,
                thematic_context=task.get("thematic_context") or None,
                max_attempts=max_attempts,
                model=model,
                grade_id=grade_id,
                favourite_colour=(fav_color or favourite_colour or "").strip(),
                child_gender=child_gender,
                user_name=user_name,
                category=task.get("category", "counting"),
                meta=task.get("meta"),
            )

            with progress_lock:
                completed_count += 1
                curr_c = completed_count
            if on_progress is not None:
                try:
                    on_progress(curr_c, total, stem_id)
                except Exception:
                    pass

            if img_path is None:
                return {"success": False, "index": i, "stem_id": stem_id, "error": gen_msg}

            mcq = mcq_from_meta(task["meta"], question=task["filled_q"])
            sq_dict = None
            try:
                from app.math_visual_engine import infer_structured_question
                sq_dict = infer_structured_question(
                    task["filled_q"],
                    meta=task["meta"],
                    grade_id=grade_id,
                    stem_id=stem_id,
                ).to_dict()
            except Exception:
                pass

            item = {
                "stem_id": stem_id,
                "topic": task["stem"].get("topic") or "",
                "topic_label": _topic_label(task["stem"].get("topic") or ""),
                "category": task.get("category", "counting"),
                "bank": task["stem"].get("bank") or "",
                "adult_role": task["role"],
                "adult_name": task["adult_display"] if task["role"] else "",
                "question": task["filled_q"],
                "image_path": str(img_path),
                "options": mcq,
                "correct": mcq.get("correct_answer", ""),
                "formula": (task["meta"].get("answer") or {}).get("formula"),
                "structured_math": sq_dict,
                "_index": i,
            }
            return {"success": True, "index": i, "stem_id": stem_id, "item": item}
        except Exception as exc:
            with progress_lock:
                completed_count += 1
                curr_c = completed_count
            if on_progress is not None:
                try:
                    on_progress(curr_c, total, stem_id)
                except Exception:
                    pass
            return {"success": False, "index": i, "stem_id": stem_id, "error": str(exc)}

    # Parallel generation with ThreadPoolExecutor
    n_workers = min(max_workers, total) if total > 0 else 1
    print(f"  [AI-BATCH] Launching {total} image generations across {n_workers} worker threads...")
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(_worker, t) for t in task_items]
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            results.append(res)
            if not res["success"]:
                skipped.append({"stem_id": res["stem_id"], "error": res["error"]})
                print(f"  [SKIP] {res['stem_id']}: {res['error']}")
                if not skip_on_error:
                    raise RuntimeError(res["error"])

    successful = [r["item"] for r in results if r["success"]]
    items = sorted(successful, key=lambda x: x["_index"])

    # Match build_workbook_items behaviour: raise if everything failed
    if not items:
        detail = skipped[0]["error"] if skipped else "no stems processed"
        raise ValueError(f"AI image generation failed for all stems: {detail}")

    return items, skipped
