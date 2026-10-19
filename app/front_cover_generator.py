"""
app/front_cover_generator.py
-----------------------------
Generates the personalised workbook front-cover image.

Source of truth for the cover design:
    grades/<grade_id>/prompts/front_page.md

Key Design Requirements:
1. SAFE PRINT MARGINS: Generous 8-10% inset from all edges. No clipped text or badges
   at top-left (Myintelibooks), top-right (the grade tag), or bottom-right (www.myintelibooks.com).
2. MEDIUM-WIDE CAMERA DISTANCE: Un-zoomed environmental framing. Child seen from waist up,
   arms raised joyfully in the air (one waving, one fist pump). Full coaster car,
   swooping tracks, trees, carnival tents, balloons, and wooden 'Let's Learn :)' sign.
3. DYNAMIC RIGHT-SIDE TOPIC PANELS:
   - If the user selects mixed or all topics, NEVER render 'mixed'.
     Show exactly 4 topic pills, chosen at random from that grade's own topics.
   - Otherwise, show only the topics the user selected, as colorful capsule pills.
4. HEADER & FOOTER (MATCHING REFERENCE IMAGE 2):
   - Top-left: Inset red rounded rectangle with book icon: 'Myintelibooks'.
   - Top-center: 'Personalized workbook for' above child's name in giant 3D colorful letters.
   - Top-right: the grade tag only. Numbered years say 'Grade 1'.
     Playgroup, Nursery, Prep, and Kindergarten do not get the word Grade.
   - Bottom: Purple curved banner with 'Fun to learn and do!' and 'www.myintelibooks.com'.
5. MODEL: Strictly openai/gpt-image-2.
"""
from __future__ import annotations

import base64
import json
import os
import random
import re
import sys
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

# Paths
PIPELINE_ROOT = Path(__file__).resolve().parent   # app/
REPO_ROOT     = PIPELINE_ROOT.parent              # kids books/

# Environment
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=REPO_ROOT / ".env")
except Exception:
    pass

try:
    from app.grade_config import get_grade_dir, get_prompt_path, get_runtime_dir, PromptNotFoundError
except ImportError:
    from grade_config import get_grade_dir, get_prompt_path, get_runtime_dir, PromptNotFoundError  # type: ignore

OPENROUTER_API_KEY    = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_IMAGES_URL = "https://openrouter.ai/api/v1/images"
DEFAULT_MODEL         = (os.getenv("IMAGE_GEN_MODEL", "openai/gpt-image-2").strip()
                         or "openai/gpt-image-2")

# Roles allowed on the roller coaster (Section 5: child + siblings only)
_CHILD_ROLES   = {"user", "child"}
_SIBLING_ROLES = {"brother", "sister", "sibling"}


class FrontCoverError(RuntimeError):
    """Raised when front-cover image generation fails after all retries."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _path_to_data_url(path: "str | Path") -> str:
    """Read an image file and return it as a base64 data URL."""
    path = Path(path)
    ext  = path.suffix.lower().lstrip(".")
    mime = {
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
    }.get(ext, "image/png")
    with open(str(path), "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


# The images endpoint rejects prompts around 4,000 characters.
_MAX_COVER_PROMPT_CHARS = 3800


# Early years keep their own names. Numbered years always say "Grade N".
_EARLY_YEAR_LABELS = {
    "pg": "Playgroup",
    "playgroup": "Playgroup",
    "nursery": "Nursery",
    "prep": "Prep",
    "kg": "Kindergarten",
    "kindergarten": "Kindergarten",
}

# Portrait A4. Generated covers are cropped to this ratio before they are saved.
A4_MM_W = 210
A4_MM_H = 297


def cover_grade_label(grade_label: str = "", grade_id: str = "") -> str:
    """
    Top-right cover tag.

    Grade 1, Grade 2, and the other numbered years keep the word Grade.
    Playgroup, Nursery, Prep, and Kindergarten never get the word Grade.
    """
    raw = (grade_label or "").strip()
    if not raw and grade_id:
        raw = grade_id.replace("_", " ").replace("-", " ").strip()
    if not raw:
        return ""
    key = re.sub(r"\s+", " ", raw.lower().replace("_", " ").replace("-", " ")).strip()
    if key in _EARLY_YEAR_LABELS:
        return _EARLY_YEAR_LABELS[key]
    if key.startswith("grade "):
        rest = key[6:].strip()
        if rest in _EARLY_YEAR_LABELS:
            return _EARLY_YEAR_LABELS[rest]
        number = re.fullmatch(r"g?\s*(\d+)", rest)
        if number:
            return f"Grade {int(number.group(1))}"
        return f"Grade {rest.title()}" if rest else ""
    if key.startswith("year "):
        rest = key[5:].strip()
        if rest.isdigit():
            return f"Grade {int(rest)}"
    number = re.fullmatch(r"g\s*(\d+)", key) or re.fullmatch(r"(\d+)", key)
    if number:
        return f"Grade {int(number.group(1))}"
    return raw


def _grade_badge(grade_label: str, grade_id: str = "") -> str:
    """Cover tag for this workbook. Never invents a grade that was not selected."""
    return cover_grade_label(grade_label, grade_id)


def to_a4_image(img: Image.Image) -> Image.Image:
    """Center-crop any picture to the A4 portrait ratio, 210:297."""
    image = img.convert("RGB")
    width, height = image.size
    if width < 1 or height < 1:
        return image
    target = A4_MM_W / A4_MM_H
    current = width / height
    if abs(current - target) < 0.004:
        return image
    if current > target:
        new_width = int(round(height * target))
        left = max(0, (width - new_width) // 2)
        return image.crop((left, 0, left + new_width, height))
    new_height = int(round(width / target))
    top = max(0, (height - new_height) // 2)
    return image.crop((0, top, width, top + new_height))


def stamp_grade_badge(img: Image.Image, label: str) -> Image.Image:
    """Paint the exact grade tag into the top-right corner of the A4 cover."""
    if not (label or "").strip():
        return img
    from PIL import ImageDraw, ImageFont

    image = img.convert("RGB")
    width, height = image.size
    draw = ImageDraw.Draw(image)
    margin = max(18, int(width * 0.035))
    font_size = max(28, int(width * 0.042))
    font = None
    for name in ("arialbd.ttf", "arial.ttf", "segoeuib.ttf"):
        try:
            font = ImageFont.truetype(name, font_size)
            break
        except Exception:
            font = None
    if font is None:
        font = ImageFont.load_default()
    text = label.strip()
    box = font.getbbox(text) if hasattr(font, "getbbox") else (0, 0, len(text) * font_size, font_size)
    text_w = box[2] - box[0]
    text_h = box[3] - box[1]
    max_w = int(width * 0.46)
    while text_w > max_w and font_size > 18:
        font_size -= 2
        for name in ("arialbd.ttf", "arial.ttf"):
            try:
                font = ImageFont.truetype(name, font_size)
                break
            except Exception:
                continue
        box = font.getbbox(text) if hasattr(font, "getbbox") else (0, 0, len(text) * font_size, font_size)
        text_w = box[2] - box[0]
        text_h = box[3] - box[1]
    pad_x, pad_y = int(font_size * 0.55), int(font_size * 0.38)
    pill_w = text_w + pad_x * 2
    pill_h = text_h + pad_y * 2
    x1 = width - margin - pill_w
    y1 = margin
    draw.rounded_rectangle(
        (x1, y1, x1 + pill_w, y1 + pill_h),
        radius=pill_h // 2,
        fill=(18, 130, 78),
    )
    draw.text((x1 + pad_x - box[0], y1 + pad_y - box[1]), text, fill=(255, 255, 255), font=font)
    return image


def _finalize_cover(img: Image.Image, grade_label: str, grade_id: str) -> Image.Image:
    """Crop the cover to A4. The prompt file decides the grade tag."""
    del grade_label, grade_id
    return to_a4_image(img)


def _load_front_page_prompt(grade_id: str) -> str:
    """Load grades/<grade_id>/prompts/front_page.md. Never substitutes another grade."""
    if not (grade_id or "").strip():
        raise FrontCoverError(
            "grade_id is required to load the front-cover prompt."
        )
    try:
        prompt_path = get_prompt_path(grade_id, "front_page")
    except PromptNotFoundError as exc:
        raise FrontCoverError(
            f"front_page.md is not available for grade '{grade_id}'. "
            "Another grade's cover prompt will not be used."
        ) from exc
    try:
        grade_root = get_grade_dir(grade_id).resolve()
        prompt_path.resolve().relative_to(grade_root)
    except (OSError, ValueError) as exc:
        raise FrontCoverError(
            f"front_page.md for grade '{grade_id}' resolved outside "
            f"grades/{grade_id}/. Refusing to use another grade's prompt."
        ) from exc
    return prompt_path.read_text(encoding="utf-8")


def _fit_cover_prompt(grade_prompt: str, runtime_block: str) -> str:
    """Keep the runtime data and as much of the grade prompt as the API allows."""
    marker = "# FINAL ABSOLUTE INSTRUCTION"
    final = ""
    idx = grade_prompt.find(marker)
    if idx != -1:
        final = grade_prompt[idx:].strip()
    base = runtime_block.strip() + "\n\n"
    remaining = _MAX_COVER_PROMPT_CHARS - len(base)
    if remaining <= 0:
        return base[:_MAX_COVER_PROMPT_CHARS]
    if final and len(final) + 2 < remaining:
        head = grade_prompt[: remaining - len(final) - 2].rstrip()
        return base + head + "\n\n" + final
    body = grade_prompt[:remaining].rstrip()
    return base + body


_COVER_TOPIC_PICK = 4


def _unique_topics(topics: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for topic in topics:
        clean = topic.strip()
        key = clean.lower()
        if not clean or key in seen or "mix" in key:
            continue
        seen.add(key)
        unique.append(clean)
    return unique


def _topics_for_cover(selected: list[str], catalog: list[str]) -> list[str]:
    """
    Specific topics stay as chosen.
    Mixed, or a selection of every topic, becomes 4 names drawn from that grade.
    """
    chosen = _unique_topics(selected)
    pool = _unique_topics(catalog) or chosen
    mixed = any("mix" in topic.lower() for topic in selected)
    covers_everything = bool(pool) and {topic.lower() for topic in chosen} >= {topic.lower() for topic in pool}
    if mixed or (covers_everything and len(pool) > _COVER_TOPIC_PICK):
        if len(pool) <= _COVER_TOPIC_PICK:
            return pool
        return random.sample(pool, _COVER_TOPIC_PICK)
    return chosen


def build_front_cover_prompt(
    *,
    grade_id: str,
    child_name: str,
    subject: str = "MATH",
    selected_topics: "list[str] | None" = None,
    grade_label: str = "",
    face_paths: "dict[str, str] | None" = None,
    all_available_topics: "list[str] | None" = None,
    website_url: str = "myintelibooks.com",
    theme_color: str = "",
    pets: "list[dict] | None" = None,
) -> str:
    """
    Assemble the cover prompt from the selected grade's front_page.md
    plus the workbook's own name, grade, topics, and uploaded riders.
    """
    grade_prompt = _load_front_page_prompt(grade_id)
    faces = face_paths or {}
    requested = [str(t).strip() for t in (selected_topics or []) if str(t).strip()]
    catalog = [str(t).strip() for t in (all_available_topics or []) if str(t).strip()]
    cover_topics = _topics_for_cover(requested, catalog)
    has_child = any(role in faces for role in _CHILD_ROLES)
    siblings = [role for role in faces if role in _SIBLING_ROLES]
    rider_count = (1 if has_child else 0) + len(siblings)
    badge = _grade_badge(grade_label, grade_id)
    child = (child_name or "").strip()
    topic_lines = "\n".join(f"- {t}" for t in cover_topics) or "- (none)"
    sibling_line = ", ".join(siblings) if siblings else "(none)"
    runtime = (
        "RUNTIME USER DATA:\n"
        f"KID_NAME: {child}\n"
        f"SUBJECT: {(subject or '').strip()}\n"
        f"GRADE: {badge}\n"
        f"THEME_COLOR: {(theme_color or '').strip()}\n"
        f"CHILD_PHOTO_UPLOADED: {'yes' if has_child else 'no'}\n"
        f"SIBLING_ROLES_UPLOADED: {sibling_line}\n"
        f"RIDER_COUNT: {rider_count}\n"
        f"WEBSITE_URL: {website_url}\n"
        f"SELECTED_TOPICS:\n{topic_lines}\n"
        "ALL_AVAILABLE_TOPICS:\n"
    )

    if pets:
        pet_entries = []
        for p in pets:
            nm = (p.get("name") or "").strip()
            ty = (p.get("type") or "Pet").strip()
            if nm or p.get("image_path"):
                pet_entries.append(f"{nm} ({ty})" if nm else ty)
        if pet_entries:
            runtime += (
                f"PET_COMPANIONS: {', '.join(pet_entries)}\n"
                f"PET_COUNT: {len(pet_entries)}\n"
            )

    runtime += "\n"

    prompt = _fit_cover_prompt(grade_prompt, runtime)
    print(
        f"  [COVER] Built prompt: {len(prompt)} chars | "
        f"grade_id={grade_id} | child={(child_name or '').strip()}"
    )
    return prompt


def _extract_image_from_response(data: dict) -> "Image.Image | None":
    """Parse a PIL Image from an OpenRouter /api/v1/images JSON response."""
    for block in (data.get("data") or []):
        if not isinstance(block, dict):
            continue
        # b64_json (gpt-image-2 primary format)
        b64 = block.get("b64_json")
        if isinstance(b64, str) and b64:
            try:
                return Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")
            except Exception as exc:
                print(f"  [COVER WARN] b64 decode: {exc}")
        # URL fallback
        url = block.get("url")
        if isinstance(url, str) and url.startswith("http"):
            try:
                import requests as _req
                r = _req.get(url, timeout=60)
                if r.ok:
                    return Image.open(BytesIO(r.content)).convert("RGB")
            except Exception as exc:
                print(f"  [COVER WARN] URL download: {exc}")
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_front_cover(
    child_name:      str,
    category:        str | None = None,
    face_paths:      "dict[str, str] | None" = None,
    family_names:    "dict[str, str] | None" = None,
    out_path:        "str | Path | None"     = None,
    api_key:         "str | None"            = None,
    model:           str                     = "",
    max_attempts:    int                     = 2,
    subject:         str                     = "MATH",
    selected_topics: "list[str] | None"      = None,
    grade:           str                     = "",
    job_id:          str                     = "",
    grade_id:        str                     = "",
    all_available_topics: "list[str] | None" = None,
    theme_color:     str                     = "",
    pets:            "list[dict] | None"     = None,
) -> Path:
    """
    Generate a personalised workbook front-cover image.
    Uses grade_config to resolve the cover output directory from the job folder.
    """
    import requests as _req

    _faces = face_paths or {}
    _provider = "openrouter"
    _key = (api_key or OPENROUTER_API_KEY or "").strip()
    _model = (model or DEFAULT_MODEL or "openai/gpt-image-2").strip()
    try:
        from app.admin_store import get_active_image_runtime
        rt = get_active_image_runtime()
        _provider = (rt.get("provider") or "openrouter").strip().lower()
        if not (api_key or "").strip():
            _key = (rt.get("api_key") or _key).strip()
        if not (model or "").strip():
            _model = (rt.get("model") or _model).strip()
    except Exception:
        pass

    if not _key:
        raise FrontCoverError(
            f"No API key configured for {_provider}. "
            "Add it in the Admin panel (Models) or in .env and restart."
        )

    if not (grade_id or "").strip():
        raise FrontCoverError(
            "grade_id is required for the front cover. "
            "Another grade's front_page.md will not be used."
        )

    # Derive topics if not explicitly passed
    topics = list(selected_topics or [])
    if not topics and category:
        if "mix" in category.lower():
            topics = []
        else:
            topics = [t.strip() for t in category.split(",") if t.strip()]

    # Cover files stay inside this workbook's job folder.
    if out_path is None:
        if not (job_id or "").strip():
            raise FrontCoverError(
                "job_id is required so the cover is saved in "
                "runtime/jobs/<job_id>/front_cover/."
            )
        cover_dir = get_runtime_dir(job_id, "front_cover")
        safe     = "".join(c if c.isalnum() else "_" for c in child_name)
        out_path = cover_dir / f"front_cover_{safe}_{int(time.time())}.png"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = build_front_cover_prompt(
        grade_id=grade_id,
        child_name=child_name,
        subject=subject,
        selected_topics=topics,
        grade_label=grade,
        face_paths=_faces,
        all_available_topics=all_available_topics,
        theme_color=theme_color,
        pets=pets,
    )

    # Build input_references: Section 5 Case D (Child + Siblings + Pets, NO adults)
    input_references: list[dict] = []

    # 1. Main child photo
    for role_key in ("user", "child"):
        if role_key in _faces and Path(_faces[role_key]).exists():
            try:
                input_references.append({
                    "type": "image_url",
                    "image_url": {"url": _path_to_data_url(_faces[role_key])},
                })
                print(f"  [COVER REF] Main Child photo: {Path(_faces[role_key]).name}")
            except Exception as exc:
                print(f"  [COVER WARN] Child photo load failed: {exc}")
            break

    # 2. Sibling photos ONLY
    for role, img_path in _faces.items():
        if role in _CHILD_ROLES or role not in _SIBLING_ROLES:
            continue
        p = Path(img_path)
        if not p.exists():
            continue
        try:
            input_references.append({
                "type": "image_url",
                "image_url": {"url": _path_to_data_url(img_path)},
            })
            print(f"  [COVER REF] Sibling photo ({role}): {p.name}")
        except Exception as exc:
            print(f"  [COVER WARN] Sibling photo load failed: {exc}")

    # 3. Pet photos
    for pet in (pets or []):
        p_img = pet.get("image_path")
        if p_img and Path(p_img).exists():
            try:
                input_references.append({
                    "type": "image_url",
                    "image_url": {"url": _path_to_data_url(p_img)},
                })
                print(f"  [COVER REF] Pet photo ({pet.get('name') or 'pet'}): {Path(p_img).name}")
            except Exception as exc:
                print(f"  [COVER WARN] Pet photo load failed: {exc}")

    headers = {
        "Authorization": f"Bearer {_key}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://kids-books-ai.local",
        "X-Title":       "Kids Books AI - Front Cover Generator",
    }
    payload: dict = {"model": _model, "prompt": prompt, "n": 1, "size": "1024x1536"}
    if input_references:
        payload["input_references"] = input_references

    # Non-OpenRouter providers share the question-image client.
    if _provider in ("openai", "gemini"):
        from app.image_providers import ProviderImageError, generate_provider_image
        cover_entries = []
        for role_key in ("user", "child", "brother", "sister", "sibling"):
            pth = _faces.get(role_key)
            if pth and Path(pth).exists():
                cover_entries.append((role_key, pth))
        for pet in (pets or []):
            pth = pet.get("image_path")
            if pth and Path(pth).exists():
                cover_entries.append((pet.get("id") or "pet", pth))
        last_err = ""
        for attempt in range(1, max_attempts + 1):
            print(f"  [COVER] Attempt {attempt}/{max_attempts} | provider={_provider} | model={_model}")
            try:
                img = _finalize_cover(
                    generate_provider_image(
                        provider=_provider,
                        model=_model,
                        api_key=_key,
                        prompt=prompt,
                        image_entries=cover_entries or None,
                        timeout=180,
                    ),
                    grade,
                    grade_id,
                )
                img.save(str(out_path), "PNG")
                print(f"  [COVER OK] Successfully saved -> {out_path}")
                return out_path
            except (ProviderImageError, Exception) as exc:
                last_err = str(exc)
                print(f"  [COVER ERR] {last_err}")
            if attempt < max_attempts:
                time.sleep(4 * attempt)
        raise FrontCoverError(
            f"Front cover generation failed after {max_attempts} attempt(s) | {last_err}"
        )

    # Retry loop (OpenRouter images endpoint)
    last_err = ""
    for attempt in range(1, max_attempts + 1):
        print(
            f"  [COVER] Attempt {attempt}/{max_attempts} | model={_model} | "
            f"{len(input_references)} photo reference(s) | "
            f"payload={len(json.dumps(payload)):,} bytes"
        )
        try:
            resp = _req.post(
                OPENROUTER_IMAGES_URL, headers=headers, json=payload, timeout=180
            )
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}: {(resp.text or '')[:700]}"
                print(f"  [COVER ERR] {last_err}")
            else:
                data = resp.json()
                if data.get("error"):
                    last_err = f"API error: {str(data['error'])[:500]}"
                    print(f"  [COVER ERR] {last_err}")
                else:
                    img = _extract_image_from_response(data)
                    if img:
                        img = _finalize_cover(img, grade, grade_id)
                        img.save(str(out_path), "PNG")
                        print(f"  [COVER OK] Successfully saved -> {out_path}")
                        return out_path
                    last_err = f"No image in response: {str(data)[:300]}"
                    print(f"  [COVER ERR] {last_err}")
        except Exception as exc:
            last_err = f"Unexpected error: {exc}"
            print(f"  [COVER ERR] {last_err}")

        if attempt < max_attempts:
            wait = 4 * attempt
            print(f"  [COVER RETRY] Waiting {wait}s...")
            time.sleep(wait)

    raise FrontCoverError(
        f"Front cover generation failed after {max_attempts} attempt(s) | {last_err}"
    )


# ---------------------------------------------------------------------------
# CLI Standalone Execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate Kids Workbook Front Cover")
    parser.add_argument("--name", default="Ayaan", help="Child display name")
    parser.add_argument("--grade", default="", help="Grade badge label, e.g. Grade 1")
    parser.add_argument("--grade-id", required=True, help="Registered grade id, e.g. Grade_1")
    parser.add_argument("--job-id", required=True, help="Workbook job id, e.g. WB_000001")
    parser.add_argument("--category", default="", help="Topic header, optional")
    args = parser.parse_args()

    print("=" * 60)
    print("RUNNING FRONT COVER GENERATOR")
    print("=" * 60)

    output_file = generate_front_cover(
        child_name=args.name,
        category=args.category,
        grade=args.grade,
        grade_id=args.grade_id,
        job_id=args.job_id,
        face_paths={},
        model="openai/gpt-image-2",
    )
    print(f"\n[SUCCESS] COVER GENERATED: {output_file}")