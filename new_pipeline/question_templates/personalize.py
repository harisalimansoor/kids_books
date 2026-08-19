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
from PIL import Image, ImageChops, ImageDraw, ImageFilter

TEMPLATES_ROOT = Path(__file__).resolve().parent
PIPELINE_ROOT = TEMPLATES_ROOT.parent  # new_pipeline/
REPO_ROOT = PIPELINE_ROOT.parent  # kids_books/

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(dotenv_path=REPO_ROOT / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
IMAGE_MODEL = os.getenv("PERSONALIZE_IMAGE_MODEL", "openai/gpt-5-image-mini").strip() or "openai/gpt-5-image-mini"
USE_AI_HEAD_PATCH = os.getenv("USE_AI_HEAD_PATCH", "").strip().lower() in ("1", "true", "yes")

ROOT = TEMPLATES_ROOT

# Paste box larger than YuNet so forehead/hair aren't clipped. Extra lift on top
# so short cuts (bob) cover template hair instead of sitting as a face sticker.
_REGION_EXPAND = float(os.getenv("FACE_PASTE_EXPAND", "1.38"))
_REGION_TOP_EXTRA = float(os.getenv("FACE_PASTE_TOP_EXTRA", "0.36"))


def _soft_mask(w: int, h: int) -> Image.Image:
    """Feathered oval — soft edge for paste, strong centre for identity."""
    inset = max(2, min(w, h) // 22)
    blur = max(10, min(w, h) // 8)
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


def _seamless_paste_face(
    canvas: Image.Image,
    region: dict,
    face_rgba: Image.Image,
) -> Image.Image:
    """Poisson seamless clone — merges uploaded face into the template naturally."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
        if face_rgba.size != (w, h):
            from interactive_templates.face_swap import resize_face_keep_aspect

            face_rgba = resize_face_keep_aspect(face_rgba.convert("RGBA"), w, h)
        out = canvas.convert("RGBA")
        out.paste(face_rgba, (x, y), _soft_mask(w, h))
        return out.convert("RGB")

    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    if face_rgba.size != (w, h):
        from interactive_templates.face_swap import resize_face_keep_aspect

        face_rgba = resize_face_keep_aspect(face_rgba.convert("RGBA"), w, h)

    mask = np.asarray(_soft_mask(w, h))
    src = cv2.cvtColor(np.asarray(face_rgba.convert("RGB")), cv2.COLOR_RGB2BGR)
    dst = cv2.cvtColor(np.asarray(canvas.convert("RGB")), cv2.COLOR_RGB2BGR)
    full_mask = np.zeros(dst.shape[:2], dtype=np.uint8)
    full_mask[y : y + h, x : x + w] = mask
    center = (x + w // 2, y + h // 2)
    try:
        merged = cv2.seamlessClone(src, dst, full_mask, center, cv2.NORMAL_CLONE)
    except cv2.error:
        out = canvas.convert("RGBA")
        out.paste(face_rgba, (x, y), Image.fromarray(mask))
        return out.convert("RGB")
    return Image.fromarray(cv2.cvtColor(merged, cv2.COLOR_BGR2RGB))


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


def _patch_crop_box(region: dict, canvas_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Crop box around one person's head/neck with a little context."""
    w, h = canvas_size
    zone = _head_neck_blend_region(region, (w, h))
    pad = int(max(zone["w"], zone["h"]) * 0.14)
    x0 = max(0, zone["x"] - pad)
    y0 = max(0, zone["y"] - pad)
    x1 = min(w, zone["x"] + zone["w"] + pad)
    y1 = min(h, zone["y"] + zone["h"] + pad)
    return x0, y0, x1, y1


def _paste_blended_patch(
    base: Image.Image,
    patch: Image.Image,
    box: tuple[int, int, int, int],
    region: dict,
    *,
    feather: int = 18,
) -> Image.Image:
    """Paste an AI-blended head patch back onto the scene."""
    x0, y0, x1, y1 = box
    pw, ph = x1 - x0, y1 - y0
    if patch.size != (pw, ph):
        patch = patch.resize((pw, ph), Image.Resampling.LANCZOS)

    zone = _head_neck_blend_region(region, base.size)
    rel_zone = {
        "x": zone["x"] - x0,
        "y": zone["y"] - y0,
        "w": zone["w"],
        "h": zone["h"],
    }
    mask = _head_neck_mask((pw, ph), rel_zone, feather=feather)

    out = base.copy()
    out.paste(patch, (x0, y0), mask)
    return out


def _patch_quality_ok(original: Image.Image, blended: Image.Image, *, max_border_delta: float = 42.0) -> bool:
    """Reject AI patches that drift too far from the input crop (ghosting / scene rewrite)."""
    try:
        import numpy as np
    except ImportError:
        return True

    if blended.size != original.size:
        blended = blended.resize(original.size, Image.Resampling.LANCZOS)
    o = np.asarray(original.convert("RGB"), dtype=np.float32)
    b = np.asarray(blended.convert("RGB"), dtype=np.float32)
    h, w = o.shape[:2]
    margin = max(4, min(h, w) // 7)
    border = np.ones((h, w), dtype=bool)
    border[margin : h - margin, margin : w - margin] = False
    if not border.any():
        return True
    delta = float(np.abs(o - b)[border].mean())
    return delta <= max_border_delta


def _ai_blend_head_patch(
    base: Image.Image,
    region: dict,
    identity_ref: Image.Image,
    role_label: str,
) -> Image.Image:
    """Blend one pasted face locally — avoids full-scene drift and ghosting."""
    if not API_KEY:
        return base

    box = _patch_crop_box(region, base.size)
    patch = base.crop(box)

    prompt = f"""You are blending a pasted face into a photo crop for a children's workbook.

IMAGE 1 = photo crop showing {role_label} with a pasted face oval.
IMAGE 2 = reference photo of this same person (face + hairstyle + skin).

TASK: make face, hair, and neck look seamless and natural in IMAGE 1.

RULES:
- The person MUST look exactly like IMAGE 2 (same face, hair, skin tone, age).
- Edit ONLY face, hair, and neck. Do NOT change shirt/clothes below the collar, arms, hands, or background.
- Remove oval cut edges and neck seams.
- Keep the same pose, camera angle, and crop framing as IMAGE 1.
- Do NOT move, shrink, or shift the head.
- Fully opaque realistic photo — no transparency, no see-through hair, no holes, no sky showing through the head.
- No text. Output ONLY the finished crop at the same framing as IMAGE 1.
""".strip()

    content = [
        {"type": "image_url", "image_url": {"url": _image_to_data_url(patch, max_side=768)}},
        {"type": "image_url", "image_url": {"url": _image_to_data_url(identity_ref, max_side=512)}},
        {"type": "text", "text": prompt},
    ]
    blended = _post_image_chat(content)
    if blended is None or not _patch_quality_ok(patch, blended):
        if blended is not None:
            print(f"  ⚠️  Patch rejected for {role_label} (too much drift) — keeping paste")
        return base
    return _paste_blended_patch(base, blended, box, region)


def _blend_all_heads(
    paste_base: Image.Image,
    original_template: Image.Image,
    child_region: dict,
    adult_region: dict,
    *,
    child_ref: Image.Image,
    adult_ref: Image.Image,
    adult_role: str,
) -> Image.Image:
    """Per-person head patch blends, then lock foreground objects to template."""
    result = paste_base.copy()
    print("  ✨ Head patch blend (child)…")
    result = _ai_blend_head_patch(result, child_region, child_ref, "child")
    adult_label = adult_role.replace("_", " ")
    print(f"  ✨ Head patch blend ({adult_label})…")
    result = _ai_blend_head_patch(result, adult_region, adult_ref, adult_label)

    w, h = result.size
    protect = _foreground_protect_mask((w, h))
    return Image.composite(original_template, result, protect)


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


def _head_neck_blend_region(region: dict, canvas_size: tuple[int, int]) -> dict:
    """Face + hair + neck only — not torso, arms, hands, or clothes."""
    cw, ch = canvas_size
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    pad_x = int(w * 0.20)
    top_lift = int(h * 0.10)
    neck_down = int(h * 0.52)
    nx = max(0, x - pad_x)
    ny = max(0, y - top_lift)
    nx2 = min(cw, x + w + pad_x)
    ny2 = min(ch, y + h + neck_down)
    return {"x": nx, "y": ny, "w": max(8, nx2 - nx), "h": max(8, ny2 - ny)}


def _head_neck_mask(size: tuple[int, int], region: dict, *, feather: int) -> Image.Image:
    """Soft oval mask for face + hair + neck."""
    w, h = size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    x, y, rw, rh = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    inset = max(2, min(rw, rh) // 24)
    draw.ellipse((x + inset, y + inset, x + rw - inset, y + rh - inset), fill=255)
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    return mask


def _foreground_protect_mask(canvas_size: tuple[int, int], *, bottom_frac: float = 0.24) -> Image.Image:
    """Protect the ground/table strip where countable objects usually sit."""
    w, h = canvas_size
    mask = Image.new("L", (w, h), 0)
    y0 = int(h * (1.0 - bottom_frac))
    draw = ImageDraw.Draw(mask)
    draw.rectangle((0, y0, w, h), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(max(12, h // 40)))


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
    original_template = Image.open(stem_dir / image_file).convert("RGB")
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

    # Seamless clone for natural face/body merge (replaces sticker-like paste)
    seamless_base = Image.open(stem_dir / image_file).convert("RGB")
    if child_skin:
        seamless_base = _recolor_body_skin(seamless_base.convert("RGBA"), child_region, child_skin).convert("RGB")
    if adult_skin:
        seamless_base = _recolor_body_skin(seamless_base.convert("RGBA"), adult_region, adult_skin).convert("RGB")
    if ok_c and child_face is not None:
        seamless_base = _seamless_paste_face(seamless_base, child_region, child_face)
        print("  ✓ Seamless merge (child)")
    if ok_a and adult_face is not None:
        seamless_base = _seamless_paste_face(seamless_base, adult_region, adult_face)
        print(f"  ✓ Seamless merge ({role})")

    child_head = crop_upload_head(Path(child_photo)) or child_face
    adult_head = crop_upload_head(Path(adult_photo)) or adult_face
    child_portrait = crop_upload_portrait(Path(child_photo)) or child_head
    adult_portrait = crop_upload_portrait(Path(adult_photo)) or adult_head
    child_face_lock = crop_upload_face(Path(child_photo)) or child_face
    adult_face_lock = crop_upload_face(Path(adult_photo)) or adult_face

    paste_base = seamless_base
    if USE_AI_HEAD_PATCH and run_ai_finish and ok_c and ok_a and child_face is not None and adult_face is not None:
        child_ref = child_portrait or child_head or child_face_lock
        adult_ref = adult_portrait or adult_head or adult_face_lock
        print(f"  ✨ Per-person head blend via {IMAGE_MODEL}…")
        result = _blend_all_heads(
            paste_base,
            original_template,
            child_region,
            adult_region,
            child_ref=child_ref,
            adult_ref=adult_ref,
            adult_role=role,
        )
        print("  ✓ Seamless face swap complete (objects locked to template)")
    else:
        w, h = paste_base.size
        protect = _foreground_protect_mask((w, h))
        result = Image.composite(original_template, paste_base, protect)
        print("  ✓ Seamless face swap complete (objects locked to template)")

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
