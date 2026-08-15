"""
personalize.py
─────────────────────────────────────────────────────────────────────────────
Paste user/adult faces onto a question-template stem, then optionally AI-finish
the scene while locking faces to the EXACT uploaded photos.

Identity strategy:
  1. Crop upload faces (YuNet) and paste with soft oval (aspect preserved)
  2. AI finish gets the composite PLUS head crops (face + hair + neck)
     so hairstyle and skin tone lock to the uploaded photos
  3. No final re-paste — that would undo seamless blending
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
IMAGE_MODEL = os.getenv("PERSONALIZE_IMAGE_MODEL", "openai/gpt-5-image-mini").strip() or "openai/gpt-5-image-mini"

ROOT = TEMPLATES_ROOT

# Paste box larger than YuNet so forehead/hair aren't clipped. Extra lift on top
# so short cuts (bob) cover template hair instead of sitting as a face sticker.
_REGION_EXPAND = float(os.getenv("FACE_PASTE_EXPAND", "1.28"))
_REGION_TOP_EXTRA = float(os.getenv("FACE_PASTE_TOP_EXTRA", "0.22"))


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
    extra_top = h * _REGION_TOP_EXTRA
    nx = int(round(cx - nw / 2.0))
    ny = int(round(cy - nh / 2.0 - extra_top / 2.0))
    nw = max(8, int(round(nw)))
    nh = max(8, int(round(nh + extra_top)))
    nx = max(0, min(nx, cw - nw))
    ny = max(0, min(ny, ch - nh))
    nw = min(nw, cw - nx)
    nh = min(nh, ch - ny)
    out = dict(region)
    out.update({"x": nx, "y": ny, "w": nw, "h": nh})
    return out


def _match_lighting(face: Image.Image, canvas: Image.Image, region: dict) -> Image.Image:
    """Gently match face brightness to the scene. Keep upload skin colour (no hue shift)."""
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
    child_head: Image.Image,
    adult_head: Image.Image,
    adult_role: str,
    soft_cartoon: bool,
    child_gender: str = "",
) -> Image.Image | None:
    """
    Seamless face blend with identity refs that include hair + skin.

    Hairstyle, hair colour, and skin tone must come from the uploaded photos
    for each role — not from the template body or a generic boy/girl restyle.
    """
    if not API_KEY:
        return None

    adult = adult_role.replace("_", " ")
    gender_hint = (child_gender or "").strip().lower()
    gender_line = ""
    if gender_hint in ("boy", "male", "m", "girl", "female", "f"):
        gender_line = (
            f"   - Child gender hint from the form: {child_gender}. "
            "Use this only if the hair in IMAGE 2 is cropped and unclear. "
            "The uploaded photo always wins over this hint.\n"
        )

    if soft_cartoon:
        style_block = """
5. SOFT STORYBOOK TOUCH (optional, whole scene)
   - Slightly warmer colours and gentle storybook softness on clothes/background.
   - Faces, hair, and skin stay photoreal and match the reference people — do NOT cartoon the faces.
"""
    else:
        style_block = """
5. KEEP PHOTO LOOK
   - Stay fully photorealistic. Only blend faces/hair/skin into the scene.
"""

    prompt = f"""You are finishing a personalised Grade 1 worksheet photograph.

IMAGE 1 = scene with two faces PASTED as soft ovals (child LEFT, {adult} RIGHT).
IMAGE 2 = CHILD head reference (face + hair + neck) — the LEFT person MUST be this child.
IMAGE 3 = {adult.upper()} head reference (face + hair + neck) — the RIGHT person MUST be this adult.
IMAGE 4 = CHILD face crop (eyes, nose, mouth lock).
IMAGE 5 = {adult.upper()} face crop (eyes, nose, mouth lock).

GOAL: seamless photoreal swap. Each person must look like their uploaded photo — same face, same hairstyle, same skin tone.

1. FACE IDENTITY (non-negotiable)
   - Left person = IMAGE 2 / IMAGE 4 (same child: eyes, nose, mouth, age).
   - Right person = IMAGE 3 / IMAGE 5 (same adult).
   - Do NOT replace with generic / prettier / different people.
   - Keep facial feature proportions from the references.

2. FULL HAIR REPLACEMENT — copy from the UPLOADS (non-negotiable)
   - Rebuild EACH person's ENTIRE hair, including the back of the head, sides, nape, and
     anything hanging over shoulders. The silhouette of the head+hair must match IMAGE 2 / IMAGE 3.
   - LEFT hair = IMAGE 2 exactly: same cut, length, parting, volume, texture, colour.
     Example: if IMAGE 2 is a bob (chin-length, no tail), the child MUST have a bob only.
   - RIGHT hair = IMAGE 3 exactly: same cut, length, parting, volume, texture, colour.
   - ERASE leftover TEMPLATE hair completely: ponytails, pigtails, buns, long hair down the
     back, hair over the shoulders, clips, ribbons, flyaways that are NOT in the upload.
   - Where you remove long template hair (e.g. ponytails behind a bob), fill that area with
     the real background / clothing / neck — do not leave a ghost tail or extra hair mass.
   - Hair must look grown from the scalp (not a wig or sticker pasted on top of old hair).
   - Do NOT restyle into a generic boy/girl haircut. Do not keep template hair "from behind".
{gender_line}
3. WHOLE-BODY SKIN TONE — copy from the UPLOADS (non-negotiable)
   - LEFT person: EVERY visible patch of skin must match IMAGE 2 (fair/olive/brown/deep —
     same undertone AND same depth). That includes face, ears, neck, chest/collarbone,
     both arms, wrists, hands, fingers, and any legs/ankles showing.
   - RIGHT person: EVERY visible patch of skin must match IMAGE 3 the same way.
   - If the upload is fair, the WHOLE body is fair — not a fair face on tanned template arms.
   - If the upload is darker, the WHOLE body is that darker tone — not a dark face on pale arms.
   - Recolour template limbs/neck to the upload. Do NOT fade the uploaded face toward the
     template body. No two-tone people (face one colour, hands another).
   - Keep natural scene lighting (highlights/shadows) but complexion must stay the upload.

4. SEAMLESS BLEND
   - Remove oval cut edges, halos, blur rings, and tone steps.
   - Rebuild natural hairline, ears, jaw, and neck transitions for BOTH people.
   - Match photo grain / sharpness so faces are not flatter or glowing vs the body.
   - Result must look like one real photograph, not a collage.
{style_block}
6. PRESERVE LAYOUT
   - Same poses, framing, clothes (except hair + whole-body skin as above), object counts.
   - No leftover ponytails or template hair behind a shorter cut.
   - No text, numbers, watermarks. No extra people.

Output ONLY the finished seamless photograph.
""".strip()

    content = [
        {"type": "image_url", "image_url": {"url": _image_to_data_url(composite, max_side=1024)}},
        {"type": "image_url", "image_url": {"url": _image_to_data_url(child_head, max_side=640)}},
        {"type": "image_url", "image_url": {"url": _image_to_data_url(adult_head, max_side=640)}},
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
    Paste upload faces onto the stem, then AI-blend them into the photo.
    Hairstyle and skin tone lock to each role's uploaded photo. No final
    re-paste — that would undo seamless blending.
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

    from interactive_templates.face_swap import crop_upload_head

    ok_c, child_face = _paste_face(canvas, child_region, Path(child_photo))
    ok_a, adult_face = _paste_face(canvas, adult_region, Path(adult_photo))
    print(f"  ✓ Pasted child={ok_c} {role}={ok_a}")

    child_head = crop_upload_head(Path(child_photo)) or child_face
    adult_head = crop_upload_head(Path(adult_photo)) or adult_face

    result = canvas.convert("RGB")
    # Always prefer AI blend when requested — this is what removes sticker look
    if run_ai_finish and ok_c and ok_a and child_face is not None and adult_face is not None:
        print(f"  ✨ Seamless blend via {IMAGE_MODEL} (hair+skin from uploads, gender hint={child_gender or 'n/a'})…")
        finished = _ai_finish_identity_locked(
            result,
            child_face=child_face,
            adult_face=adult_face,
            child_head=child_head,
            adult_head=adult_head,
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
    p.add_argument("--gender", default="", help="Boy / Girl — used only if upload hair is unclear")
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
