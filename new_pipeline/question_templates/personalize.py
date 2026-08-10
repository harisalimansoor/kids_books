"""
personalize.py
─────────────────────────────────────────────────────────────────────────────
Paste user/adult faces onto a question-template stem, then optionally AI-finish
the scene while locking faces to the EXACT uploaded photos.

Identity strategy:
  1. Crop upload faces (YuNet) and paste with soft oval (aspect preserved)
  2. AI finish gets the composite PLUS the two face crops as references
  3. Re-paste the same crops after AI so likeness cannot drift
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

TEMPLATES_ROOT = Path(__file__).resolve().parent
PIPELINE_ROOT = TEMPLATES_ROOT.parent  # new_pipeline/
REPO_ROOT = PIPELINE_ROOT.parent  # kids_books/

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(dotenv_path=REPO_ROOT / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
IMAGE_MODEL = "openai/gpt-5.4-image-2"

ROOT = TEMPLATES_ROOT

# Paste box slightly larger than YuNet box so forehead / jaw aren't clipped.
_REGION_EXPAND = float(os.getenv("FACE_PASTE_EXPAND", "1.18"))


def _soft_mask(w: int, h: int) -> Image.Image:
    """Feathered oval — keep most of the real face visible (light inset only)."""
    inset = max(2, min(w, h) // 18)
    blur = max(8, min(w, h) // 10)
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((inset, inset, w - inset, h - inset), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def _expand_region(region: dict, canvas_size: tuple[int, int], scale: float = _REGION_EXPAND) -> dict:
    cw, ch = canvas_size
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    cx, cy = x + w / 2.0, y + h / 2.0
    nw, nh = w * scale, h * scale
    nx = int(round(cx - nw / 2.0))
    ny = int(round(cy - nh / 2.0))
    nw = max(8, int(round(nw)))
    nh = max(8, int(round(nh)))
    nx = max(0, min(nx, cw - nw))
    ny = max(0, min(ny, ch - nh))
    nw = min(nw, cw - nx)
    nh = min(nh, ch - ny)
    out = dict(region)
    out.update({"x": nx, "y": ny, "w": nw, "h": nh})
    return out


def _match_lighting(face: Image.Image, canvas: Image.Image, region: dict) -> Image.Image:
    """Gently match face brightness to the local neck/cheek area on the canvas."""
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    # Sample a strip just below the paste box (neck) when possible
    sample_top = min(canvas.height - 1, y + h)
    sample_bot = min(canvas.height, sample_top + max(8, h // 5))
    sample_left = max(0, x + w // 4)
    sample_right = min(canvas.width, x + (3 * w) // 4)
    if sample_bot <= sample_top or sample_right <= sample_left:
        return face

    patch = canvas.crop((sample_left, sample_top, sample_right, sample_bot)).convert("RGB")
    pixels = list(patch.getdata())
    if not pixels:
        return face
    target_luma = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels) / len(pixels)

    face_rgb = face.convert("RGB")
    fp = list(face_rgb.getdata())
    face_luma = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in fp) / max(1, len(fp))
    if face_luma < 1:
        return face
    factor = max(0.85, min(1.15, target_luma / face_luma))
    adjusted = ImageEnhance.Brightness(face_rgb).enhance(factor)
    if face.mode == "RGBA":
        adjusted = adjusted.convert("RGBA")
        adjusted.putalpha(face.split()[-1])
    return adjusted


def _prepare_face(photo_path: Path, box_w: int, box_h: int) -> Image.Image | None:
    from interactive_templates.face_swap import crop_upload_face, resize_face_keep_aspect

    face = crop_upload_face(photo_path)
    if face is None:
        return None
    return resize_face_keep_aspect(face.convert("RGBA"), box_w, box_h)


def _paste_face(
    canvas: Image.Image,
    region: dict,
    photo_path: Path,
    *,
    prepared: Image.Image | None = None,
) -> tuple[bool, Image.Image | None]:
    """Paste upload face into region. Returns (ok, prepared_rgba_crop)."""
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    face = prepared if prepared is not None else _prepare_face(photo_path, w, h)
    if face is None:
        return False, None
    if face.size != (w, h):
        from interactive_templates.face_swap import resize_face_keep_aspect

        face = resize_face_keep_aspect(face.convert("RGBA"), w, h)
    face = _match_lighting(face, canvas, region)
    canvas.paste(face, (x, y), _soft_mask(face.width, face.height))
    return True, face


def _image_to_data_url(image: Image.Image, *, max_side: int = 768) -> str:
    im = image.convert("RGB")
    w, h = im.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    buf = BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _extract_image_url(data: dict) -> str | None:
    msg = data.get("choices", [{}])[0].get("message", {})
    for img in msg.get("images", []):
        url = (img.get("image_url") or {}).get("url", "")
        if url:
            return url
    content = msg.get("content", "")
    if isinstance(content, list):
        for p in content:
            if isinstance(p, dict) and p.get("type") == "image_url":
                return p["image_url"]["url"]
    if isinstance(content, str):
        m = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", content)
        if m:
            return m.group(1)
    return None


def _ai_finish_identity_locked(
    composite: Image.Image,
    *,
    child_face: Image.Image,
    adult_face: Image.Image,
    adult_role: str,
    soft_cartoon: bool,
    child_gender: str = "",
) -> Image.Image | None:
    """
    Seamless face blend into the template with face crops as identity refs.
    Also adjusts the child's hair to match gender (boy/girl).
    """
    if not API_KEY:
        return None

    adult = adult_role.replace("_", " ")
    gender = (child_gender or "").strip().lower()
    if gender in ("boy", "male", "m"):
        hair_block = """
3. CHILD HAIR (gender = boy) — required
   - Restyle the CHILD's hair to a natural short BOY haircut suitable for age 5–7
     (short sides, neat top — e.g. short crop / textured crop).
   - Keep the SAME hair colour as in the child reference / paste.
   - Hair must look grown from the scalp and blended into the head — not a wig or sticker.
   - Do NOT leave long girl-style hair, pigtails, or long fringe on a boy.
"""
    elif gender in ("girl", "female", "f"):
        hair_block = """
3. CHILD HAIR (gender = girl) — required
   - Restyle the CHILD's hair to a natural GIRL hairstyle suitable for age 5–7
     (shoulder-length or longer with soft layers, or neat tied-back / half-up if already long).
   - Keep the SAME hair colour as in the child reference / paste.
   - Hair must look grown from the scalp and blended into the head — not a wig or sticker.
   - Do NOT leave a short boy buzz-cut on a girl.
"""
    else:
        hair_block = """
3. CHILD HAIR
   - Keep the child's hair consistent with the reference face photo.
   - Blend the hairline into the head naturally (no cut-out fringe).
"""

    style_block = ""
    if soft_cartoon:
        style_block = """
4. SOFT STORYBOOK TOUCH (optional, whole scene)
   - Slightly warmer colours and gentle storybook softness on clothes/background.
   - Faces stay photoreal and recognisable as the reference people — do NOT turn faces into cartoons.
"""
    else:
        style_block = """
4. KEEP PHOTO LOOK
   - Stay fully photorealistic. Only blend faces/hair into the scene.
"""

    prompt = f"""You are finishing a personalised Grade 1 worksheet photograph.

IMAGE 1 = scene with two faces PASTED as soft ovals (child on the left, {adult} on the right).
IMAGE 2 = REFERENCE of the CHILD's real face — the left person MUST be this child.
IMAGE 3 = REFERENCE of the {adult.upper()}'s real face — the right person MUST be this adult.

GOAL: seamless photoreal face swap — NOT stickers on a template.

1. FACE IDENTITY (non-negotiable)
   - Left face = IMAGE 2 (same person, eyes, nose, mouth, skin, age).
   - Right face = IMAGE 3 (same person).
   - Do NOT replace with generic / prettier / different people.
   - Keep facial feature proportions from the references.

2. SEAMLESS BLEND (critical — this must not look pasted)
   - Completely remove oval cut edges, halos, blur rings, and tone steps.
   - Rebuild natural hairline, ears, jaw, and neck transitions for BOTH people.
   - Match face brightness, white balance, and skin tone to each person's neck/shoulders.
   - Match scene lighting (highlights/shadows under chin, beside nose, along jaw).
   - Match photo grain / sharpness so faces are not flatter or glowing vs the body.
   - The result must look like one real photograph, not collage.
{hair_block}
{style_block}
5. PRESERVE LAYOUT
   - Same poses, framing, clothes (except hair as above), object counts.
   - No text, numbers, watermarks. No extra people.

Output ONLY the finished seamless photograph.
""".strip()

    content = [
        {"type": "image_url", "image_url": {"url": _image_to_data_url(composite, max_side=1024)}},
        {"type": "image_url", "image_url": {"url": _image_to_data_url(child_face, max_side=512)}},
        {"type": "image_url", "image_url": {"url": _image_to_data_url(adult_face, max_side=512)}},
        {"type": "text", "text": prompt},
    ]

    payload = {
        "model": IMAGE_MODEL,
        "modalities": ["image", "text"],
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8504",
    }
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=200)
    except Exception as exc:
        print(f"  ⚠️  personalize request failed ({exc})")
        return None
    if resp.status_code != 200:
        print(f"  ⚠️  personalize API failed ({resp.status_code}): {resp.text[:200]}")
        return None
    img_ref = _extract_image_url(resp.json())
    if not img_ref:
        print("  ⚠️  personalize: no image returned")
        return None
    if img_ref.startswith("data:image"):
        raw = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        raw = requests.get(img_ref, timeout=60).content
    out = Image.open(BytesIO(raw)).convert("RGB")
    # Normalize size to template
    if out.size != composite.size:
        out = out.resize(composite.size, Image.Resampling.LANCZOS)
    return out


def soft_cartoon_keep_identity(image: Image.Image) -> Image.Image | None:
    """Backward-compatible wrapper (no refs) — prefer personalize_stem."""
    if not API_KEY:
        return None
    buf = BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    prompt = (
        "Blend pasted face ovals into this photo seamlessly. Do NOT change who the people are. "
        "Remove cut edges and match neck lighting. Output ONLY the image."
    )
    payload = {
        "model": IMAGE_MODEL,
        "modalities": ["image", "text"],
        "max_tokens": 1200,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8504",
    }
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    img_ref = _extract_image_url(resp.json())
    if not img_ref:
        return None
    if img_ref.startswith("data:image"):
        raw = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        raw = requests.get(img_ref, timeout=60).content
    return Image.open(BytesIO(raw)).convert("RGB")


def personalize_stem(
    stem_dir: str | Path,
    *,
    child_photo: str | Path,
    adult_photo: str | Path,
    adult_role: str = "mother",
    out_path: str | Path | None = None,
    run_ai_finish: bool = True,
    soft_cartoon: bool = True,
    child_gender: str = "",
) -> Path:
    """
    Paste upload faces onto the stem, then AI-blend them into the photo
    (identity refs + gender-appropriate child hair). No final re-paste —
    that would undo seamless blending.
    """
    stem_dir = Path(stem_dir)
    meta = json.loads((stem_dir / "meta.json").read_text(encoding="utf-8"))
    pers = meta.get("personalisation") or {}
    locked = (pers.get("template_adult_role") or "").strip().lower()
    allowed = [r.lower() for r in (pers.get("allowed_adult_roles") or [])]
    role = adult_role.strip().lower()
    if locked and role != locked:
        raise ValueError(
            f"{stem_dir}: template body is '{locked}' — refuse adult_role='{adult_role}'. "
            "Generate a separate stem PNG for each role."
        )
    if allowed and role not in allowed:
        raise ValueError(f"{stem_dir}: adult_role '{adult_role}' not in {allowed}")

    image_file = meta.get("image_file") or "template.png"
    canvas = Image.open(stem_dir / image_file).convert("RGBA")

    regions = {r["role"]: r for r in (meta.get("face_regions") or [])}
    adult_region = regions.get(role) or regions.get(locked) or regions.get("adult")
    if "child" not in regions or adult_region is None:
        raise ValueError(
            f"{stem_dir}: meta.json needs face_regions for 'child' and "
            f"'{role or locked or 'adult'}' (template_adult_role)"
        )

    child_region = _expand_region(regions["child"], canvas.size)
    adult_region = _expand_region(adult_region, canvas.size)

    ok_c, child_face = _paste_face(canvas, child_region, Path(child_photo))
    ok_a, adult_face = _paste_face(canvas, adult_region, Path(adult_photo))
    print(f"  ✓ Pasted child={ok_c} {role}={ok_a}")

    result = canvas.convert("RGB")
    # Always prefer AI blend when requested — this is what removes sticker look
    if run_ai_finish and ok_c and ok_a and child_face is not None and adult_face is not None:
        print(f"  ✨ Seamless blend (gender={child_gender or 'n/a'}, soft_cartoon={soft_cartoon})…")
        finished = _ai_finish_identity_locked(
            result,
            child_face=child_face,
            adult_face=adult_face,
            adult_role=role,
            soft_cartoon=soft_cartoon,
            child_gender=child_gender,
        )
        if finished is not None:
            result = finished
            print("  ✓ Faces blended into template (no sticker re-paste)")
        else:
            print("  ⚠️  AI blend failed — keeping paste composite")
    elif ok_c or ok_a:
        result = canvas.convert("RGB")

    if out_path is None:
        out_path = stem_dir / f"preview_{adult_role}.png"
    else:
        out_path = Path(out_path)
    result.save(out_path, format="PNG")
    print(f"  ✓ Saved {out_path}")
    return out_path


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Personalize a question-template stem")
    p.add_argument("stem_dir", type=Path)
    p.add_argument("--child", required=True, type=Path)
    p.add_argument("--adult", required=True, type=Path)
    p.add_argument("--role", default="mother")
    p.add_argument("--gender", default="", help="Boy / Girl — restyles child hair")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--no-ai", action="store_true")
    p.add_argument("--photo", action="store_true", help="Photoreal blend only (no soft cartoon)")
    args = p.parse_args()
    personalize_stem(
        args.stem_dir,
        child_photo=args.child,
        adult_photo=args.adult,
        adult_role=args.role,
        out_path=args.out,
        run_ai_finish=not args.no_ai,
        soft_cartoon=not args.photo,
        child_gender=args.gender,
    )
