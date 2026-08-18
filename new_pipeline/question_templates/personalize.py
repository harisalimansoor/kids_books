"""
personalize.py
─────────────────────────────────────────────────────────────────────────────
Paste user/adult faces onto a question-template stem, then optionally AI-finish
the scene while locking faces to the EXACT uploaded photos.

Identity strategy:
  1. Crop upload faces (YuNet) including hair/forehead and paste with soft oval
  2. Recolour template neck/arms/hands to the uploaded face skin tone
  3. AI finish gets the composite PLUS head + portrait crops so hairstyle
     and whole-body skin lock to the uploaded photos
  4. No final re-paste — that would undo seamless blending
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
from PIL import Image, ImageDraw, ImageFilter

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
_REGION_EXPAND = float(os.getenv("FACE_PASTE_EXPAND", "1.38"))
_REGION_TOP_EXTRA = float(os.getenv("FACE_PASTE_TOP_EXTRA", "0.36"))


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
    """Keep uploaded complexion. Do not pull the face toward the template body."""
    return face


def _median_skin_rgb(im: Image.Image) -> tuple[int, int, int] | None:
    """Sample face-skin colour from the inner crop (skip hair/highlights)."""
    try:
        import numpy as np
    except ImportError:
        return None
    rgb = np.asarray(im.convert("RGB"))
    h, w = rgb.shape[:2]
    if h < 8 or w < 8:
        return None
    patch = rgb[h // 4 : (3 * h) // 4, w // 4 : (3 * w) // 4].reshape(-1, 3)
    luma = 0.299 * patch[:, 0] + 0.587 * patch[:, 1] + 0.114 * patch[:, 2]
    patch = patch[(luma > 45) & (luma < 245)]
    if patch.size < 30:
        patch = rgb.reshape(-1, 3)
    med = patch.mean(axis=0) if patch.shape[0] < 8 else np.median(patch, axis=0)
    return int(med[0]), int(med[1]), int(med[2])


def _recolor_body_skin(canvas: Image.Image, region: dict, target_rgb: tuple[int, int, int]) -> Image.Image:
    """
    Shift template neck / arms / hands toward the uploaded face complexion.

    Clothes in the torso centre are left alone; the neck band and lower
    limbs (where hands show) are the usual mismatch.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return canvas

    arr = np.asarray(canvas.convert("RGB")).copy()
    H, W = arr.shape[:2]
    x, y, fw, fh = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    # Start at the chin / below the paste oval so we sample TEMPLATE skin, not the upload face.
    bx0 = max(0, x - int(1.25 * fw))
    by0 = min(H - 12, y + int(0.72 * fh))
    bx1 = min(W, x + fw + int(1.25 * fw))
    by1 = min(H, y + int(5.0 * fh))
    if bx1 - bx0 < 12 or by1 - by0 < 12:
        return canvas

    roi = arr[by0:by1, bx0:bx1]
    rh, rw = roi.shape[:2]
    lab = cv2.cvtColor(roi, cv2.COLOR_RGB2LAB).astype(np.float32)

    ny0, ny1 = int(0.02 * rh), max(8, int(0.30 * rh))
    nx0, nx1 = int(0.22 * rw), int(0.78 * rw)
    neck = lab[ny0:ny1, nx0:nx1].reshape(-1, 3)
    if neck.size < 12:
        return canvas
    src_mean = np.median(neck, axis=0)
    target = np.array([[list(target_rgb)]], dtype=np.uint8)
    tgt_lab = cv2.cvtColor(target, cv2.COLOR_RGB2LAB)[0, 0].astype(np.float32)
    delta = tgt_lab - src_mean

    dist = np.sqrt(((lab - src_mean) ** 2).sum(axis=2))
    rgb_f = roi.astype(np.float32)
    mx = rgb_f.max(axis=2)
    mn = rgb_f.min(axis=2)
    sat = (mx - mn) / (mx + 1.0)
    skin = (dist < 26) & (sat < 0.58) & (lab[:, :, 0] > 28) & (lab[:, :, 0] < 248)

    yy, xx = np.ogrid[:rh, :rw]
    neck_band = yy < int(0.38 * rh)
    hands_band = yy > int(0.52 * rh)
    apply = skin & (neck_band | hands_band)
    if int(apply.sum()) < 40:
        apply = skin

    mask = cv2.GaussianBlur(apply.astype(np.float32), (21, 21), 0)
    lab_new = lab + delta * mask[..., None]
    lab_new[:, :, 0] = np.clip(lab_new[:, :, 0], 0, 255)
    lab_new[:, :, 1] = np.clip(lab_new[:, :, 1], 0, 255)
    lab_new[:, :, 2] = np.clip(lab_new[:, :, 2], 0, 255)
    arr[by0:by1, bx0:bx1] = cv2.cvtColor(lab_new.astype(np.uint8), cv2.COLOR_LAB2RGB)
    out = Image.fromarray(arr)
    if canvas.mode == "RGBA":
        out = out.convert("RGBA")
        out.putalpha(canvas.split()[-1])
    return out


def _prepare_face(photo_path: Path, box_w: int, box_h: int) -> Image.Image | None:
    from interactive_templates.face_swap import crop_upload_head, resize_face_keep_aspect

    # Head crop (face + hair + neck) so the paste already carries hairstyle.
    face = crop_upload_head(photo_path)
    if face is None:
        from interactive_templates.face_swap import crop_upload_face

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


def _image_to_data_url(image: Image.Image, *, max_side: int = 768, fmt: str = "JPEG") -> str:
    im = image.convert("RGB")
    w, h = im.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    buf = BytesIO()
    kind = (fmt or "JPEG").upper()
    if kind == "PNG":
        im.save(buf, format="PNG")
        mime = "image/png"
    else:
        im.save(buf, format="JPEG", quality=88, optimize=True)
        mime = "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()


def _extract_image_url(data: dict) -> str | None:
    """Pull a generated image URL out of varied OpenRouter / OpenAI payloads."""
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

    for block in data.get("data") or []:
        got = from_image_obj(block)
        if got:
            return got

    choices = data.get("choices") or [{}]
    msg = (choices[0] or {}).get("message") or {}
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
    if isinstance(content, str):
        m = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", content)
        if m:
            return m.group(1)
    return None


def _response_hint(data: dict) -> str:
    try:
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            texts = [p.get("text", "") for p in content if isinstance(p, dict)]
            content = " ".join(texts)
        err = data.get("error") or content or ""
        return str(err)[:280].replace("\n", " ")
    except Exception:
        return ""


def _post_image_chat(content: list) -> Image.Image | None:
    payload = {
        "model": IMAGE_MODEL,
        "modalities": ["image", "text"],
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501",
    }
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=200)
    except Exception as exc:
        print(f"  ⚠️  personalize request failed ({exc})")
        return None
    if resp.status_code != 200:
        print(f"  ⚠️  personalize API failed ({resp.status_code}): {resp.text[:300]}")
        return None
    try:
        data = resp.json()
    except Exception as exc:
        print(f"  ⚠️  personalize: bad JSON ({exc})")
        return None
    img_ref = _extract_image_url(data)
    if not img_ref:
        print(f"  ⚠️  personalize: no image returned — {_response_hint(data)}")
        return None
    if img_ref.startswith("data:image"):
        raw = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        raw = requests.get(img_ref, timeout=60).content
    return Image.open(BytesIO(raw)).convert("RGB")


def _ai_finish_identity_locked(
    composite: Image.Image,
    *,
    child_face: Image.Image,
    adult_face: Image.Image,
    child_head: Image.Image,
    adult_head: Image.Image,
    child_portrait: Image.Image,
    adult_portrait: Image.Image,
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

    child_ref = child_portrait or child_head or child_face
    adult_ref = adult_portrait or adult_head or adult_face

    prompt = f"""You are finishing a personalised Grade 1 worksheet photograph.

IMAGE 1 = scene with two faces PASTED as soft ovals (child LEFT, {adult} RIGHT).
IMAGE 2 = CHILD photo (face + hairstyle + skin).
IMAGE 3 = {adult.upper()} photo (face + hairstyle + skin).

GOAL: one seamless photograph. Each person looks like their uploaded photo.

1. FACE: LEFT = IMAGE 2. RIGHT = IMAGE 3. Same eyes, nose, mouth, age. No generic faces.
2. HAIR: copy IMAGE 2 / IMAGE 3 exactly (cut, length, colour). Erase leftover template hair (ponytails, buns, long hair).
{gender_line}3. BODY SKIN: neck, arms, hands, fingers must match the FACE skin in IMAGE 2 / IMAGE 3. No two-tone people.
4. BLEND: remove oval cut edges, halos, and neck seams so it looks like one real photo.
{style_block}
6. Keep poses, clothes, object counts. No extra people. No text.

Output ONLY the finished photograph.
""".strip()

    content3 = [
        {"type": "image_url", "image_url": {"url": _image_to_data_url(composite, max_side=1024)}},
        {"type": "image_url", "image_url": {"url": _image_to_data_url(child_ref, max_side=512)}},
        {"type": "image_url", "image_url": {"url": _image_to_data_url(adult_ref, max_side=512)}},
        {"type": "text", "text": prompt},
    ]
    print("  ✨ Blend pass (scene + 2 identity photos)…")
    out = _post_image_chat(content3)
    if out is None:
        simple = (
            "Blend the pasted face ovals into this photo so the people look natural. "
            "Remove cut edges and match neck/hand skin to each pasted face. "
            "Keep the same two people, poses, clothes, and objects. Output ONLY the image."
        )
        content1 = [
            {"type": "image_url", "image_url": {"url": _image_to_data_url(composite, max_side=1024)}},
            {"type": "text", "text": simple},
        ]
        print("  ✨ Blend fallback (scene only)…")
        out = _post_image_chat(content1)
    if out is None:
        return None
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
    Hairstyle is copied from each upload. Body skin (neck, arms, hands) is
    recoloured to match that person's uploaded face. No final re-paste.
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

    from interactive_templates.face_swap import (
        crop_upload_face,
        crop_upload_head,
        crop_upload_portrait,
    )

    ok_c, child_face = _paste_face(canvas, child_region, Path(child_photo))
    ok_a, adult_face = _paste_face(canvas, adult_region, Path(adult_photo))
    print(f"  ✓ Pasted child={ok_c} {role}={ok_a}")

    child_skin = _median_skin_rgb(child_face) if child_face is not None else None
    adult_skin = _median_skin_rgb(adult_face) if adult_face is not None else None
    if child_skin:
        canvas = _recolor_body_skin(canvas, child_region, child_skin)
        print(f"  ✓ Child body skin → upload face {child_skin}")
    if adult_skin:
        canvas = _recolor_body_skin(canvas, adult_region, adult_skin)
        print(f"  ✓ {role} body skin → upload face {adult_skin}")

    child_head = crop_upload_head(Path(child_photo)) or child_face
    adult_head = crop_upload_head(Path(adult_photo)) or adult_face
    child_portrait = crop_upload_portrait(Path(child_photo)) or child_head
    adult_portrait = crop_upload_portrait(Path(adult_photo)) or adult_head
    child_face_lock = crop_upload_face(Path(child_photo)) or child_face
    adult_face_lock = crop_upload_face(Path(adult_photo)) or adult_face

    result = canvas.convert("RGB")
    # Always prefer AI blend when requested — this is what removes sticker look
    if run_ai_finish and ok_c and ok_a and child_face is not None and adult_face is not None:
        print(f"  ✨ Seamless blend via {IMAGE_MODEL} (hair+skin from uploads, gender hint={child_gender or 'n/a'})…")
        finished = _ai_finish_identity_locked(
            result,
            child_face=child_face_lock,
            adult_face=adult_face_lock,
            child_head=child_head,
            adult_head=adult_head,
            child_portrait=child_portrait,
            adult_portrait=adult_portrait,
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
