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
    IMAGE_GEN_MODEL             optional; default openai/gpt-5.4-image-2
    IMAGE_GEN_MAX_ATTEMPTS      optional; default 3
"""

from __future__ import annotations

import base64
import os
import sys
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

# ── paths ──────────────────────────────────────────────────────────────────
PIPELINE_ROOT = Path(__file__).resolve().parent   # new_pipeline/
REPO_ROOT = PIPELINE_ROOT.parent                  # kids_books/
PROMPT_FILE = REPO_ROOT / "prompt.md"

if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ── .env ───────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=REPO_ROOT / ".env")
except Exception:
    pass

# ── config ──────────────────────────────────────────────────────────────────
API_KEY: str = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

IMAGE_GEN_MODEL: str = os.getenv(
    "IMAGE_GEN_MODEL",
    os.getenv("PERSONALIZE_IMAGE_MODEL", "openai/gpt-5.4-image-2"),
).strip()

IMAGE_GEN_MAX_ATTEMPTS: int = int(os.getenv("IMAGE_GEN_MAX_ATTEMPTS", "3"))

# The exact placeholder string that must appear in prompt.md
PLACEHOLDER = "[PASTE ONE QUESTION HERE]"

# Preferred order to send reference photos to the API
_PHOTO_PRIORITY = ["user", "child", "mother", "father", "grandmother", "grandfather",
                   "uncle", "aunt", "brother", "sister", "sibling"]


# ── image file helpers ──────────────────────────────────────────────────────

def _path_to_data_url(path: "str | Path") -> str:
    """
    Read an image file and return it as a base64 data-URL.

    Supports PNG, JPEG.  Used to embed reference photos in the API payload.
    """
    path = Path(path)
    ext = path.suffix.lower().lstrip(".")
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
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

def _load_prompt_template() -> str:
    """Read prompt.md and return its full contents."""
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(
            f"prompt.md not found at: {PROMPT_FILE}\n"
            "It must live in kids_books/ (the project root)."
        )
    return PROMPT_FILE.read_text(encoding="utf-8")


def _extract_image_url(data: dict) -> str | None:
    """
    Pull a generated image URL or data-URI out of varied OpenRouter / OpenAI payloads.

    Handles:
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
        url = img.get("image_url") or img.get("url") or img.get("b64_json")
        if isinstance(url, dict):
            url = url.get("url") or url.get("b64_json")
        if isinstance(url, str) and url:
            if url.startswith("data:image") or url.startswith("http"):
                return url
            if re.fullmatch(r"[A-Za-z0-9+/=\n\r]+", url) and len(url) > 200:
                return "data:image/png;base64," + url.replace("\n", "")
        return None

    # OpenAI DALL-E style response: data = [{'url': ...}]
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


def build_generation_prompt(question_text: str, character_context: "str | None" = None) -> str:
    """
    Fill prompt.md with the given question text and return the complete prompt.

    Replaces [PASTE ONE QUESTION HERE] with the filled question.
    Optionally appends character reference instructions.
    """
    template = _load_prompt_template()
    if PLACEHOLDER not in template:
        raise ValueError(
            f"The placeholder {PLACEHOLDER!r} was not found in prompt.md. "
            "Ensure it is present in the 'QUESTION TO VISUALISE' section."
        )
    prompt = template.replace(PLACEHOLDER, (question_text or "").strip())
    if character_context and character_context.strip():
        prompt += (
            f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"# CHARACTERS IN THIS SCENE AND REFERENCE PHOTOS\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{character_context.strip()}\n"
        )
    return prompt


# ── low-level API call ──────────────────────────────────────────────────────

def _call_openrouter(
    prompt: str,
    *,
    api_key: str,
    model: str,
    image_entries: "list[tuple[str, str]] | list[str] | None" = None,
    timeout: int = 180,
) -> "Image.Image | None":
    """
    POST prompt + optional reference photos to OpenRouter; return PIL Image or None.

    image_entries can be:
        - list of (label, path) tuples: e.g. [("Child (Hamdan)", path1), ("Dad", path2)]
        - list of path strings: e.g. [path1, path2]

    The content array is built as:
        [text label for photo 1,
         image_url block for photo 1,
         text label for photo 2,
         image_url block for photo 2,
         ...
         text block with the full prompt.md + question]
    """
    import requests

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://kids-books-ai.local",
        "X-Title": "Kids Books AI - Image Generator",
    }

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

    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
    except Exception as exc:
        print(f"  [ERR] Network error: {exc}")
        return None

    if resp.status_code != 200:
        snippet = (resp.text or "")[:300]
        print(f"  [ERR] OpenRouter HTTP {resp.status_code}: {snippet}")
        return None

    try:
        data = resp.json()
    except Exception:
        print("  [ERR] Could not parse JSON response from OpenRouter")
        return None

    img_ref = _extract_image_url(data)
    if not img_ref:
        err_snippet = str(data.get("error") or data)[:250]
        print(f"  [ERR] No usable image in OpenRouter response: {err_snippet}")
        return None

    if img_ref.startswith("data:image"):
        try:
            b64 = img_ref.split(",", 1)[1]
            return Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")
        except Exception as exc:
            print(f"  [ERR] Decode base64 image: {exc}")
            return None
    elif img_ref.startswith("http"):
        try:
            r = requests.get(img_ref, timeout=60)
            if r.ok:
                return Image.open(BytesIO(r.content)).convert("RGB")
            print(f"  [ERR] Image URL returned HTTP {r.status_code}")
        except Exception as exc:
            print(f"  [ERR] Download image URL: {exc}")
            return None

    return None


# ── public generation function ──────────────────────────────────────────────

def generate_image_for_question(
    question_text: str,
    out_path: "str | Path",
    *,
    face_paths: "dict[str, str] | None" = None,
    image_entries: "list[tuple[str, str]] | list[str] | None" = None,
    character_context: "str | None" = None,
    max_attempts: "int | None" = None,
    model: "str | None" = None,
    api_key: "str | None" = None,
) -> "tuple[Path | None, str]":
    """
    Generate a personalised educational scene image.

    Sends:
        prompt.md  +  question text  +  character reference photos
    to the OpenRouter AI image model and saves the result.

    The AI draws a fresh new scene using the uploaded photos as visual
    references for character appearance — no face cropping, no compositing.

    Parameters
    ----------
    question_text : str
        Fully-filled question (child / family names already substituted).
        Inserted at [PASTE ONE QUESTION HERE] in prompt.md.
    out_path : str | Path
        Destination PNG file.  Parent directories are created automatically.
    face_paths : dict[str, str] | None
        {role: file_path} of uploaded family photos.
    image_entries : list[tuple[str, str]] | list[str] | None
        Explicit list of (label, path) tuples for characters in this scene.
    character_context : str | None
        Extra text instructions mapping reference photos to character roles.
    max_attempts : int | None
        Retry limit (defaults to IMAGE_GEN_MAX_ATTEMPTS env or 3).
    model : str | None
        OpenRouter model ID (defaults to IMAGE_GEN_MODEL env).
    api_key : str | None
        OpenRouter API key (defaults to OPENROUTER_API_KEY env).

    Returns
    -------
    (Path, success_message) on success
    (None, error_message)   on failure
    """
    _key = (api_key or API_KEY or "").strip()
    if not _key:
        return None, "OPENROUTER_API_KEY is not set. Add it to .env and restart Streamlit."

    _model = (model or IMAGE_GEN_MODEL or "openai/gpt-5.4-image-2").strip()
    _attempts = max_attempts if max_attempts is not None else IMAGE_GEN_MAX_ATTEMPTS

    try:
        prompt = build_generation_prompt(question_text, character_context=character_context)
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

    for attempt in range(1, _attempts + 1):
        n_photos = len(ref_list)
        print(
            f"  [GEN] Attempt {attempt}/{_attempts}: {out_path.name} "
            f"({n_photos} reference photo(s))"
        )
        result = _call_openrouter(
            prompt,
            api_key=_key,
            model=_model,
            image_entries=ref_list or None,
        )
        if result is not None:
            result.save(str(out_path), "PNG")
            msg = (
                f"Generated on attempt {attempt} using {_model} "
                f"with {n_photos} reference photo(s)"
            )
            print(f"  [OK]  {out_path.name}: {msg}")
            return out_path, msg

        if attempt < _attempts:
            wait = 3 * attempt
            print(f"  [RETRY] Waiting {wait}s before next attempt...")
            time.sleep(wait)

    return None, f"Image generation failed after {_attempts} attempt(s) with {_model}"


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
) -> "tuple[list, list]":
    """
    Generate fresh AI images for every selected stem and return PDF-ready items.

    For each stem:
        1. Fills question text with child name, family names and pronouns.
        2. Selects only the reference photos relevant to this question (e.g. child + dad,
           or child only) and labels them clearly.
        3. Calls generate_image_for_question with:
               prompt.md  +  filled question  +  labelled family photos
        4. Saves the generated PNG to out_dir.
        5. Returns the item dict in the same format as build_workbook_items().

    This mirrors stem_pipeline.build_workbook_items() so newapp.py can switch
    between face-swap and AI-generate with a single if/else branch.

    Parameters
    ----------
    stems : list[dict]
        Selected stems from stem_pipeline.select_stems().
    user_name : str
        Child name (substituted into question text).
    family_names : dict | None
        {role: display_name} e.g. {"mother": "Sarah", "father": "James"}.
    face_paths : dict[str, str] | None
        {role: file_path} of uploaded family photos.
    child_gender : str
        "Boy" / "Girl" / "Other" (used for pronoun substitution).
    out_dir : Path | None
        Where to save generated PNGs.  Default: _runtime/ai_generated/.
    on_progress : callable | None
        Optional callback on_progress(i, total, stem_id) for Streamlit progress bars.
    max_attempts : int | None
        API retry limit per stem.
    model : str | None
        Override the image generation model for all stems.
    skip_on_error : bool
        If True (default) failed stems are logged and skipped.

    Returns
    -------
    items : list[dict]
        Generated workbook items (stem_id, topic, question, image_path, options, ...).
    skipped : list[dict]
        [{stem_id, error}] for stems that could not be generated.
    """
    from stem_pipeline import (
        display_name_for_role,
        fill_question_text,
        mcq_from_meta,
        topic_label as _topic_label,
    )

    _family_names = family_names or {}
    _out_dir = Path(out_dir) if out_dir else PIPELINE_ROOT / "_runtime" / "ai_generated"
    _out_dir.mkdir(parents=True, exist_ok=True)

    items: list = []
    skipped: list = []
    total = len(stems)

    for i, stem in enumerate(stems, start=1):
        stem_id = stem.get("stem_id", f"stem_{i}")

        if on_progress is not None:
            try:
                on_progress(i, total, stem_id)
            except Exception:
                pass

        try:
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

            # Step 2: identify characters in this question & attach matching reference photos
            stem_entries: list[tuple[str, str]] = []
            char_lines: list[str] = []

            # Child is always the primary character
            child_photo = (face_paths or {}).get("user") or (face_paths or {}).get("child")
            if child_photo and Path(child_photo).exists():
                stem_entries.append((f"Child ({user_name})", child_photo))
                char_lines.append(
                    f"- Character 1: {user_name} (Primary Child, {child_gender or 'British child'}). "
                    f"Match face, hair, and appearance to Reference Photo 1."
                )

            # Sibling or adult family member in this question
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
                        f"Match face, hair, and appearance to Reference Photo {ref_idx}."
                    )

            char_context = ""
            if char_lines:
                char_context = (
                    "Characters appearing in this scene:\n"
                    + "\n".join(char_lines)
                    + "\nAll human characters must be predominantly camera-facing and actively engaged in the learning activity."
                )

            # Step 3: generate image (prompt.md + question + character-labelled reference photos)
            out_path = _out_dir / f"{i:02d}_{stem_id}.png"
            img_path, gen_msg = generate_image_for_question(
                filled_q,
                out_path,
                face_paths=face_paths,
                image_entries=stem_entries or None,
                character_context=char_context or None,
                max_attempts=max_attempts,
                model=model,
            )

            if img_path is None:
                raise RuntimeError(gen_msg)

            # Step 4: build item dict (same schema as build_workbook_items)
            mcq = mcq_from_meta(meta)
            items.append(
                {
                    "stem_id": stem_id,
                    "topic": stem.get("topic") or "",
                    "topic_label": _topic_label(stem.get("topic") or ""),
                    "bank": stem.get("bank") or "",
                    "adult_role": role,
                    "adult_name": display_name_for_role(role, _family_names) if role else "",
                    "question": filled_q,
                    "image_path": str(img_path),
                    "options": mcq,
                    "correct": mcq.get("correct_answer", ""),
                    "formula": (meta.get("answer") or {}).get("formula"),
                }
            )

        except Exception as exc:
            skipped.append({"stem_id": stem_id, "error": str(exc)})
            print(f"  [SKIP] {stem_id}: {exc}")
            if not skip_on_error:
                raise

    # Match build_workbook_items behaviour: raise if everything failed
    if not items:
        detail = skipped[0]["error"] if skipped else "no stems processed"
        raise ValueError(f"AI image generation failed for all stems: {detail}")

    return items, skipped
