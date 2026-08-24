"""
personalize.py
─────────────────────────────────────────────────────────────────────────────
Systematic personalization pipeline (do not mix steps):

  STEP 1 — PASTE
      Crop upload faces, STRIP photo backgrounds (flags/studio), then place
      into annotated face_regions. Soft oval + matte alpha — no sticker bg.

  STEP 2 — AI BLEND
      Smooth face/hair into the neck (matted identity refs). Retry once.
      Keep AI only if it is safe and reduces sticker edges; else soft-paste.

  STEP 3 — COUNT LOCK (image difference)
      Soft-paste is the count-locked base. Keep AI only inside face ovals;
      snap any non-face drift back to soft-paste.
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
# Legacy per-face patch path — unused by the main 3-step pipeline.
USE_AI_FACE_PATCH = os.getenv("USE_AI_FACE_PATCH", "0").strip().lower() in ("1", "true", "yes")

ROOT = TEMPLATES_ROOT

# Annotated box pad (keep close to meta — large pad caused bobbleheads)
_ANNOTATED_PAD = float(os.getenv("FACE_ANNOTATED_PAD", "1.05"))
# How much of the annotated box the face crop should fill
_FACE_FILL = float(os.getenv("FACE_FILL", "0.86"))
# After AI: snap non-face pixels back when they drift from soft-paste
_OBJECT_LOCK_THRESHOLD = float(os.getenv("OBJECT_LOCK_THRESHOLD", "12"))
_OBJECT_LOCK_FACE_PAD = float(os.getenv("OBJECT_LOCK_FACE_PAD", "0.55"))
# Reject AI blend if face grows too much vs soft-paste / annotated box
_AI_MAX_FACE_GROW = float(os.getenv("AI_MAX_FACE_GROW", "1.22"))
# Ghosting: mix of barely-changed + heavily-changed pixels inside face core
_AI_GHOST_LOW = float(os.getenv("AI_GHOST_LOW_FRAC", "0.32"))
_AI_GHOST_HIGH = float(os.getenv("AI_GHOST_HIGH_FRAC", "0.22"))

# Kept for env compatibility with older runs / docs
_REGION_EXPAND = float(os.getenv("FACE_PASTE_EXPAND", "1.0"))
_REGION_TOP_EXTRA = float(os.getenv("FACE_PASTE_TOP_EXTRA", "0.0"))
_REGION_BOTTOM_EXTRA = float(os.getenv("FACE_PASTE_BOTTOM_EXTRA", "0.0"))
_FACE_BODY_SCALE = float(os.getenv("FACE_BODY_SCALE", "1.0"))
_HEAD_VS_FACE = float(os.getenv("FACE_HEAD_VS_FACE", "1.0"))


def _soft_mask(w: int, h: int) -> Image.Image:
    """Feathered oval for paste — hides photo edges without cutting chin."""
    inset = max(2, min(w, h) // 22)
    blur = max(8, min(w, h) // 10)
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((inset, inset, w - inset, h - inset), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def _matte_face_rgba(face: Image.Image) -> Image.Image:
    """
    Strip upload photo background (flags, studio walls, scenery).

    Uses YuNet face ellipse + OpenCV GrabCut so only face/hair stay opaque.
    """
    import cv2
    import numpy as np
    from interactive_templates.face_detect import detect_faces, pick_primary_face

    rgba = face.convert("RGBA")
    rgb = np.asarray(rgba.convert("RGB"), dtype=np.uint8)
    h, w = rgb.shape[:2]
    if h < 16 or w < 16:
        return rgba

    faces = detect_faces(rgba) or []
    primary = pick_primary_face(faces, (w, h)) if faces else None

    # Soft ellipse around face (+ hair / jaw)
    Y, X = np.ogrid[:h, :w]
    if primary:
        fx, fy, fw, fh = (
            int(primary["x"]),
            int(primary["y"]),
            int(primary["w"]),
            int(primary["h"]),
        )
        cx = fx + fw / 2.0
        cy = fy + fh * 0.40
        ax = max(8.0, fw * 0.68)
        ay = max(8.0, fh * 0.82)
    else:
        cx, cy = w / 2.0, h * 0.42
        ax, ay = w * 0.38, h * 0.45

    ell = ((X - cx) / ax) ** 2 + ((Y - cy) / ay) ** 2
    ell_mask = np.clip((1.15 - ell) * 255.0, 0, 255).astype(np.uint8)

    # GrabCut: border = background, face rect = likely foreground
    gc = np.full((h, w), cv2.GC_PR_BGD, dtype=np.uint8)
    if primary:
        rx0 = max(0, fx - int(0.12 * fw))
        ry0 = max(0, fy - int(0.35 * fh))
        rx1 = min(w, fx + fw + int(0.12 * fw))
        ry1 = min(h, fy + fh + int(0.25 * fh))
    else:
        rx0, ry0 = int(0.15 * w), int(0.05 * h)
        rx1, ry1 = int(0.85 * w), int(0.90 * h)
    gc[ry0:ry1, rx0:rx1] = cv2.GC_PR_FGD
    # Force image border as background (kills flag/studio)
    border = max(2, min(w, h) // 40)
    gc[:border, :] = cv2.GC_BGD
    gc[-border:, :] = cv2.GC_BGD
    gc[:, :border] = cv2.GC_BGD
    gc[:, -border:] = cv2.GC_BGD
    try:
        bgd = np.zeros((1, 65), np.float64)
        fgd = np.zeros((1, 65), np.float64)
        cv2.grabCut(rgb, gc, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
        gc_fg = np.where(
            (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0
        ).astype(np.uint8)
    except Exception:
        gc_fg = ell_mask

    # Keep intersection of ellipse + grabcut (safe), then feather
    alpha = cv2.bitwise_and(ell_mask, gc_fg)
    # If grabcut wiped the face, fall back to ellipse only
    if int(alpha.sum()) < 0.08 * 255 * h * w:
        alpha = ell_mask
    sigma = max(2.0, min(w, h) / 35.0)
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=sigma)

    out = Image.fromarray(rgb).convert("RGBA")
    out.putalpha(Image.fromarray(alpha))
    return out


def _resize_face_contain(face: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """
    Fit the matted face inside a fraction of the annotated box.

    Transparent padding (no photo background) lets template hair/ears show.
    """
    box_w = max(8, int(box_w))
    box_h = max(8, int(box_h))
    src = _matte_face_rgba(face)
    fw, fh = src.size
    if fw < 1 or fh < 1:
        return Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))

    fill = max(0.72, min(0.92, _FACE_FILL))
    target_w = box_w * fill
    target_h = box_h * fill
    scale = min(target_w / fw, target_h / fh)
    nw = max(1, int(round(fw * scale)))
    nh = max(1, int(round(fh * scale)))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    ox = (box_w - nw) // 2
    oy = max(0, (box_h - nh) // 2 - max(0, int(0.05 * box_h)))
    out.paste(resized, (ox, oy), resized)
    return out


def _crop_upload_face_complete(photo_path: Path) -> Image.Image | None:
    """
    Face crop for STEP 1: forehead→chin with modest pad (bg stripped later).
    """
    from interactive_templates.face_detect import detect_faces, pick_primary_face
    from interactive_templates.face_swap import crop_upload_face, crop_upload_head

    photo_path = Path(photo_path)
    if not photo_path.exists():
        return None
    photo = Image.open(photo_path).convert("RGBA")
    faces = detect_faces(photo) or []
    primary = pick_primary_face(faces, photo.size) if faces else None
    if primary:
        x, y, w, h = int(primary["x"]), int(primary["y"]), int(primary["w"]), int(primary["h"])
        pad_x = int(0.28 * max(w, h))
        pad_top = int(0.45 * h)
        pad_bottom = int(0.32 * h)
        left = max(0, x - pad_x)
        top = max(0, y - pad_top)
        right = min(photo.width, x + w + pad_x)
        bottom = min(photo.height, y + h + pad_bottom)
        return photo.crop((left, top, right, bottom))
    return crop_upload_face(photo_path) or crop_upload_head(photo_path)


def _expand_region(region: dict, canvas_size: tuple[int, int], scale: float = _REGION_EXPAND) -> dict:
    """
    Fit paste box to the template face (YuNet) so head size matches the body.

    Slightly pads for hair on top and chin below; does not blow up the whole head.
    """
    cw, ch = canvas_size
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    cx, cy = x + w / 2.0, y + h / 2.0

    # First match body face size, then tiny expand + hair/chin pads
    body_scale = max(0.7, min(1.2, _FACE_BODY_SCALE)) * scale
    nw, nh = w * body_scale, h * body_scale
    extra_top = h * _REGION_TOP_EXTRA
    extra_bottom = h * _REGION_BOTTOM_EXTRA

    nx = int(round(cx - nw / 2.0))
    # Keep face centred on YuNet face; lift only for hair pad
    ny = int(round(cy - nh / 2.0 - extra_top * 0.55))
    nw = max(8, int(round(nw)))
    nh = max(8, int(round(nh + extra_top + extra_bottom)))
    nx = max(0, min(nx, cw - nw))
    ny = max(0, min(ny, ch - nh))
    nw = min(nw, cw - nx)
    nh = min(nh, ch - ny)
    out = dict(region)
    out.update({"x": nx, "y": ny, "w": nw, "h": nh})
    return out


def _match_lighting(face: Image.Image, canvas: Image.Image, region: dict) -> Image.Image:
    """
    Mild RGB shift toward template neck/cheek colour (no aggressive LAB — that
    caused green outdoor casts). Enough so the soft paste isn't a colour sticker.
    """
    try:
        import numpy as np
    except ImportError:
        return face

    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    cw, ch = canvas.size
    # Prefer neck band under chin (template skin, not foliage)
    sx0 = max(0, x + int(0.2 * w))
    sx1 = min(cw, x + int(0.8 * w))
    sy0 = min(ch - 4, y + int(0.75 * h))
    sy1 = min(ch, y + int(1.05 * h))
    if sx1 - sx0 < 6 or sy1 - sy0 < 4:
        sx0, sy0 = max(0, x), max(0, y)
        sx1, sy1 = min(cw, x + w), min(ch, y + h)

    ref = np.asarray(canvas.convert("RGB").crop((sx0, sy0, sx1, sy1)), dtype=np.float32)
    src_im = face.convert("RGB")
    fw, fh = src_im.size
    src = np.asarray(src_im, dtype=np.float32)
    if fw < 8 or fh < 8 or ref.size < 16:
        return face

    # Skin-ish ref pixels (avoid green leaves)
    flat = ref.reshape(-1, 3)
    r, g, b = flat[:, 0], flat[:, 1], flat[:, 2]
    skin = (r > 60) & (g > 40) & (b > 30) & (r >= g * 0.85) & (r > b)
    if int(skin.sum()) >= 20:
        d_mean = flat[skin].mean(0)
    else:
        d_mean = flat.mean(0)

    s_patch = src[fh // 3 : (2 * fh) // 3, fw // 3 : (2 * fw) // 3].reshape(-1, 3)
    s_mean = s_patch.mean(0)
    delta = 0.55 * (d_mean - s_mean)
    adjusted = np.clip(src + delta, 0, 255).astype(np.uint8)
    out = Image.fromarray(adjusted)
    if face.mode == "RGBA":
        out = out.convert("RGBA")
        alpha = face.split()[-1]
        if alpha.size != out.size:
            alpha = alpha.resize(out.size, Image.Resampling.LANCZOS)
        out.putalpha(alpha)
    return out


def _soft_paste_only(
    canvas: Image.Image,
    face: Image.Image,
    px: int,
    py: int,
    mask: Image.Image | None = None,
) -> Image.Image:
    """Soft oval paste — AI finish removes the remaining sticker edge."""
    base = canvas.convert("RGB")
    fw, fh = face.size
    if mask is None:
        mask = _soft_mask(fw, fh)
    elif mask.size != (fw, fh):
        mask = mask.resize((fw, fh), Image.Resampling.LANCZOS)
    out = base.convert("RGBA")
    fr = face.convert("RGBA")
    fr.putalpha(mask)
    out.paste(fr, (px, py), fr)
    return out.convert("RGB")


def _seamless_paste(
    canvas: Image.Image,
    face: Image.Image,
    px: int,
    py: int,
    mask: Image.Image | None = None,
) -> Image.Image:
    """Alias — local Poisson caused outdoor colour casts; soft paste + AI is used."""
    return _soft_paste_only(canvas, face, px, py, mask)


def _restore_lower_objects(
    original: Image.Image,
    blended: Image.Image,
    *,
    frac: float = 0.40,
    feather: float = 0.08,
) -> Image.Image:
    """
    Keep AI-blended faces on top; restore baskets/fruit from the original below.

    Soft vertical feather so the join isn't a hard horizontal cut.
    """
    import numpy as np

    a = original.convert("RGB")
    b = blended.convert("RGB")
    if b.size != a.size:
        b = b.resize(a.size, Image.Resampling.LANCZOS)
    H, W = a.height, a.width
    aa = np.asarray(a, dtype=np.float32)
    bb = np.asarray(b, dtype=np.float32)

    y_lock = int(H * (1.0 - frac))
    y_feather = max(4, int(H * feather))
    weight = np.ones((H, 1), dtype=np.float32)  # 1 = use blended
    # Below y_lock+feather → fully original (0)
    weight[y_lock + y_feather :, :] = 0.0
    # Feather band
    for i in range(y_feather):
        t = (i + 1) / (y_feather + 1)
        weight[y_lock + i, :] = 1.0 - t

    out = bb * weight[..., None] + aa * (1.0 - weight[..., None])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _face_only_composite(
    base: Image.Image,
    blended: Image.Image,
    regions: list[dict],
) -> Image.Image:
    """
    Take `blended` only inside face/hair ovals; keep `base` elsewhere.

    `base` should already be the soft-pasted scene (not the raw template with
    old faces) so the oval core doesn't ghost two different faces together.
    Objects/clothes outside the ovals stay exactly as in `base`.
    """
    import numpy as np

    a_img = base.convert("RGB")
    b_img = blended.convert("RGB")
    if b_img.size != a_img.size:
        b_img = b_img.resize(a_img.size, Image.Resampling.LANCZOS)

    W, H = a_img.size
    mask = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask)
    for region in regions:
        x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
        pad_x = int(0.32 * w)
        pad_top = int(0.50 * h)
        pad_bot = int(0.35 * h)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_top)
        x1 = min(W, x + w + pad_x)
        y1 = min(H, y + h + pad_bot)
        draw.ellipse((x0, y0, x1, y1), fill=255)

    # Soft rim only — core stays fully blended (no ghost of old face)
    blur = max(8, min(W, H) // 55)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    m = np.asarray(mask, dtype=np.float32) / 255.0
    # Boost interior so midtones aren't a 50/50 ghost
    m = np.clip(m * 1.35, 0.0, 1.0)

    a = np.asarray(a_img, dtype=np.float32)
    b = np.asarray(b_img, dtype=np.float32)
    out = a * (1.0 - m[..., None]) + b * m[..., None]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _face_allow_mask(
    size: tuple[int, int],
    regions: list[dict],
    *,
    pad_scale: float = _OBJECT_LOCK_FACE_PAD,
) -> Image.Image:
    """Soft mask (L) where AI face edits are allowed; 0 elsewhere (objects locked)."""
    W, H = size
    mask = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask)
    for region in regions:
        x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
        pad_x = int(pad_scale * w)
        pad_top = int(pad_scale * 1.15 * h)
        pad_bot = int(pad_scale * 0.75 * h)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_top)
        x1 = min(W, x + w + pad_x)
        y1 = min(H, y + h + pad_bot)
        draw.ellipse((x0, y0, x1, y1), fill=255)
    blur = max(10, min(W, H) // 45)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def _lock_objects_by_image_diff(
    locked_base: Image.Image,
    candidate: Image.Image,
    face_regions: list[dict],
    *,
    threshold: float = _OBJECT_LOCK_THRESHOLD,
    face_pad: float = _OBJECT_LOCK_FACE_PAD,
) -> tuple[Image.Image, dict]:
    """
    Keep worksheet object counts exact by restoring drifted non-face pixels.

    `locked_base` = soft-paste composite (template scene + pasted faces). Outside
    the faces this still has the template's exact fruit/toys/sandwiches.

    `candidate` = AI-blended image (may have rewritten counts).

    For every pixel outside the face allow-mask: if |candidate - locked_base|
    exceeds `threshold`, snap back to `locked_base`. Face regions keep the AI
    blend so edges stay seamless.
    """
    import numpy as np

    base = locked_base.convert("RGB")
    cand = candidate.convert("RGB")
    if cand.size != base.size:
        cand = cand.resize(base.size, Image.Resampling.LANCZOS)

    W, H = base.size
    allow = _face_allow_mask((W, H), face_regions, pad_scale=face_pad)
    allow_f = np.asarray(allow, dtype=np.float32) / 255.0  # 1 = keep AI

    a = np.asarray(base, dtype=np.float32)
    b = np.asarray(cand, dtype=np.float32)
    diff = np.abs(a - b).mean(axis=2)  # per-pixel mean RGB delta

    # Outside faces: restore wherever AI moved pixels (count / prop changes)
    restore = (diff > float(threshold)) & (allow_f < 0.35)
    # Soften restore edges so we don't get hard seams next to faces
    restore_u8 = (restore.astype(np.uint8) * 255)
    restore_img = Image.fromarray(restore_u8, mode="L").filter(
        ImageFilter.GaussianBlur(max(4, min(W, H) // 80))
    )
    restore_w = np.asarray(restore_img, dtype=np.float32) / 255.0

    # Final weight for AI: high in faces, low where we restore to base
    ai_w = np.clip(allow_f * (1.0 - restore_w), 0.0, 1.0)
    # Interior of face oval stays fully AI even if slight lighting drift
    ai_w = np.maximum(ai_w, np.clip(allow_f * 1.25, 0.0, 1.0) * (allow_f > 0.55))

    out = a * (1.0 - ai_w[..., None]) + b * ai_w[..., None]
    stats = {
        "diff_mean": float(diff.mean()),
        "diff_max": float(diff.max()),
        "restored_frac": float(restore.mean()),
        "threshold": float(threshold),
    }
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), stats


def _ai_blend_acceptable(
    soft_paste: Image.Image,
    ai: Image.Image,
    regions: list[dict],
) -> tuple[bool, str]:
    """
    Reject AI blends that enlarge heads or leave a double-face / ghost.

    Returns (ok, reason). On failure the caller should keep soft-paste.
    """
    import numpy as np
    from interactive_templates.face_detect import detect_faces

    if ai.size != soft_paste.size:
        ai = ai.resize(soft_paste.size, Image.Resampling.LANCZOS)

    soft_arr = np.asarray(soft_paste.convert("RGB"), dtype=np.float32)
    ai_arr = np.asarray(ai.convert("RGB"), dtype=np.float32)
    W, H = soft_paste.size
    max_grow = max(1.05, _AI_MAX_FACE_GROW)

    for region in regions:
        x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
        pad = int(0.35 * max(w, h))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
        crop = ai.crop((x0, y0, x1, y1))
        faces = detect_faces(crop) or []
        role = region.get("role") or "face"

        if len(faces) >= 2:
            return False, f"{role}: {len(faces)} faces in region (double-face)"

        if faces:
            f = max(faces, key=lambda ff: ff["w"] * ff["h"])
            area = float(f["w"] * f["h"])
            # AI face must not balloon past annotated box
            if area > max_grow * float(w * h):
                return False, (
                    f"{role}: AI face area {area:.0f} > "
                    f"{max_grow:.2f}× annotated {w*h}"
                )
            # Also compare to soft-paste face size in same crop
            soft_faces = detect_faces(soft_paste.crop((x0, y0, x1, y1))) or []
            if soft_faces:
                sf = max(soft_faces, key=lambda ff: ff["w"] * ff["h"])
                soft_area = max(1.0, float(sf["w"] * sf["h"]))
                if area > max_grow * soft_area:
                    return False, (
                        f"{role}: AI grew face "
                        f"{area/soft_area:.2f}× vs soft-paste"
                    )

        # Ghosting: mix of barely-changed template pixels + heavy overlay pixels
        cx0 = x + int(0.20 * w)
        cy0 = y + int(0.20 * h)
        cx1 = x + int(0.80 * w)
        cy1 = y + int(0.80 * h)
        if cx1 - cx0 < 8 or cy1 - cy0 < 8:
            continue
        core = np.abs(ai_arr[cy0:cy1, cx0:cx1] - soft_arr[cy0:cy1, cx0:cx1]).mean(axis=2)
        low = float((core < 12.0).mean())
        high = float((core > 45.0).mean())
        if low >= _AI_GHOST_LOW and high >= _AI_GHOST_HIGH:
            return False, (
                f"{role}: ghosting "
                f"(unchanged={low:.2f}, rewritten={high:.2f})"
            )

        # Grow fallback (no YuNet): changed pixels spilling far outside the box
        pad2 = int(0.55 * max(w, h))
        xx0, yy0 = max(0, x - pad2), max(0, y - pad2)
        xx1, yy1 = min(W, x + w + pad2), min(H, y + h + pad2)
        ring = np.abs(ai_arr[yy0:yy1, xx0:xx1] - soft_arr[yy0:yy1, xx0:xx1]).mean(axis=2)
        changed = ring > 20.0
        if changed.any():
            ys, xs = np.where(changed)
            bbox_area = float((ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1))
            if bbox_area > max_grow * 1.15 * float(w * h):
                return False, (
                    f"{role}: AI change footprint {bbox_area:.0f} "
                    f"too large vs annotated {w*h}"
                )

    return True, "ok"


def _sticker_edge_score(img: Image.Image, regions: list[dict]) -> float:
    """
    Higher score = more rectangular / portrait-sticker edges in face boxes.

    Used to prefer an AI blend that removes hard paste borders.
    """
    import cv2
    import numpy as np

    gray = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 70, 150)
    H, W = edges.shape
    scores = []
    for region in regions:
        x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        if x1 - x0 < 12 or y1 - y0 < 12:
            continue
        band = max(2, min(w, h) // 18)
        top = edges[y0 : min(H, y0 + band), x0:x1]
        bot = edges[max(0, y1 - band) : y1, x0:x1]
        left = edges[y0:y1, x0 : min(W, x0 + band)]
        right = edges[y0:y1, max(0, x1 - band) : x1]
        rim = float(
            (top.mean() if top.size else 0)
            + (bot.mean() if bot.size else 0)
            + (left.mean() if left.size else 0)
            + (right.mean() if right.size else 0)
        ) / 4.0
        scores.append(rim)
    return float(sum(scores) / max(1, len(scores)))


def _choose_ai_or_soft(
    soft_paste: Image.Image,
    ai: Image.Image,
    regions: list[dict],
) -> tuple[Image.Image, str]:
    """
    Keep AI only when it is safe AND improves (or at least doesn't worsen) stickers.

    Hard reject: double-face / extreme head growth.
    Soft reject (ghosting/footprint): still prefer AI if sticker edges drop a lot.
    """
    ok, reason = _ai_blend_acceptable(soft_paste, ai, regions)
    soft_sticker = _sticker_edge_score(soft_paste, regions)
    ai_sticker = _sticker_edge_score(ai, regions)

    if ok:
        return ai, f"accepted ({reason}; sticker {soft_sticker:.1f}->{ai_sticker:.1f})"

    # Never keep double-face or huge grow
    hard = ("double-face" in reason) or ("grew face" in reason) or ("face area" in reason)
    if hard:
        return soft_paste, f"rejected hard ({reason})"

    # Ghosting / footprint: accept AI if it clearly reduces rectangular sticker look
    if ai_sticker < soft_sticker * 0.72:
        return ai, (
            f"accepted despite {reason} "
            f"(sticker edges {soft_sticker:.1f}->{ai_sticker:.1f})"
        )
    return soft_paste, f"rejected ({reason}; sticker {soft_sticker:.1f}->{ai_sticker:.1f})"


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
    """
    Prepare upload face for annotated-region paste.

    Uses a complete face crop + contain-fit so chin/forehead/cheeks are not clipped.
    """
    face = _crop_upload_face_complete(photo_path)
    if face is None:
        return None
    return _resize_face_contain(face.convert("RGBA"), box_w, box_h)


def _use_annotated_region(region: dict, canvas_size: tuple[int, int]) -> dict:
    """
    STEP 1 helper: use meta.json face_regions with modest hair/chin pad.

    Does NOT re-detect faces or change body proportions beyond the pad.
    """
    cw, ch = canvas_size
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    pad = max(1.0, min(1.35, _ANNOTATED_PAD))
    if pad != 1.0:
        cx, cy = x + w / 2.0, y + h / 2.0
        nw, nh = w * pad, h * pad
        # Extra lift for hair; keep chin in frame
        x = int(round(cx - nw / 2.0))
        y = int(round(cy - nh / 2.0 - h * (pad - 1.0) * 0.45))
        w, h = int(round(nw)), int(round(nh))
    x = max(0, min(x, cw - 8))
    y = max(0, min(y, ch - 8))
    w = max(8, min(w, cw - x))
    h = max(8, min(h, ch - y))
    out = {
        "x": x,
        "y": y,
        "w": w,
        "h": h,
    }
    if region.get("role"):
        out["role"] = region["role"]
    if region.get("landmarks"):
        out["landmarks"] = region["landmarks"]
    return out


def _paste_into_annotated_region(
    canvas: Image.Image,
    region: dict,
    photo_path: Path,
) -> tuple[bool, Image.Image | None]:
    """
    STEP 1: paste a COMPLETE upload face into the annotated box.

    Contain-fit keeps forehead→chin visible; soft oval blends edges only.
    """
    return _paste_face(canvas, region, photo_path)


def _paste_face_landmark_aligned(
    canvas: Image.Image,
    region: dict,
    photo_path: Path,
) -> tuple[bool, Image.Image | None]:
    """
    LEGACY — not used by personalize_stem.

    Main pipeline uses `_paste_into_annotated_region` (exact meta boxes) instead.
    Kept for experiments / A-B tests only.
    """
    from interactive_templates.face_detect import detect_faces, pick_primary_face
    from interactive_templates.face_swap import crop_upload_face
    import math

    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    tmpl_lm = region.get("landmarks") or {}

    if not (tmpl_lm.get("left_eye") and tmpl_lm.get("right_eye")):
        faces = detect_faces(canvas) or []
        cx, cy = x + w / 2, y + h / 2
        best = None
        best_d = 1e18
        for f in faces:
            fcx = f["x"] + f["w"] / 2
            fcy = f["y"] + f["h"] / 2
            d = (fcx - cx) ** 2 + (fcy - cy) ** 2
            if d < best_d:
                best_d = d
                best = f
        if best and best.get("landmarks"):
            tmpl_lm = best["landmarks"]
            x, y, w, h = int(best["x"]), int(best["y"]), int(best["w"]), int(best["h"])

    upload = Image.open(photo_path).convert("RGBA")
    up_faces = detect_faces(upload) or []
    up_primary = pick_primary_face(up_faces, upload.size) if up_faces else None

    if not (tmpl_lm.get("left_eye") and tmpl_lm.get("right_eye") and up_primary and up_primary.get("landmarks")):
        face = _prepare_face(photo_path, w, h)
        if face is None:
            return False, None
        face = _match_lighting(face, canvas, {"x": x, "y": y, "w": w, "h": h})
        mask = _soft_mask(face.width, face.height)
        blended = _seamless_paste(canvas, face, x, y, mask)
        canvas.paste(blended.convert("RGB") if blended.mode != "RGB" else blended)
        return True, face

    t_le, t_re = tmpl_lm["left_eye"], tmpl_lm["right_eye"]
    u_lm = up_primary["landmarks"]
    u_le, u_re = u_lm["left_eye"], u_lm["right_eye"]

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    t_iod = max(8.0, dist(t_le, t_re))
    u_iod = max(8.0, dist(u_le, u_re))

    ux, uy, uw, uh = (
        int(up_primary["x"]),
        int(up_primary["y"]),
        int(up_primary["w"]),
        int(up_primary["h"]),
    )

    # Target = template face on the body (slightly under-size to avoid bobblehead)
    body_scale = max(0.70, min(1.05, _FACE_BODY_SCALE))
    head_factor = max(0.92, min(1.08, _HEAD_VS_FACE))
    tw, th = w * head_factor, h * head_factor
    scale_box = ((tw / max(8.0, uw)) + (th / max(8.0, uh))) / 2.0
    scale_iod = (t_iod / u_iod) * head_factor
    # Prefer box match to shoulders; IOD as light correction
    scale = (0.82 * scale_box + 0.18 * scale_iod) * body_scale

    # Prefer tight face crop (less bg) so soft oval ≈ face area on the body
    face_crop = crop_upload_face(photo_path)
    if face_crop is not None:
        # Map upload landmarks into face_crop coords via YuNet pad used in crop
        # crop_upload_face pads around YuNet — re-detect on crop for eye mid
        crop_faces = detect_faces(face_crop) or []
        crop_primary = pick_primary_face(crop_faces, face_crop.size) if crop_faces else None
        if crop_primary and crop_primary.get("landmarks"):
            head = face_crop.convert("RGBA")
            c_lm = crop_primary["landmarks"]
            u_mid = (
                (c_lm["left_eye"][0] + c_lm["right_eye"][0]) / 2,
                (c_lm["left_eye"][1] + c_lm["right_eye"][1]) / 2,
            )
            # Recompute scale from crop face box vs template
            cuw, cuh = int(crop_primary["w"]), int(crop_primary["h"])
            scale_box = ((tw / max(8.0, cuw)) + (th / max(8.0, cuh))) / 2.0
            c_iod = max(8.0, dist(c_lm["left_eye"], c_lm["right_eye"]))
            scale_iod = (t_iod / c_iod) * head_factor
            scale = (0.82 * scale_box + 0.18 * scale_iod) * body_scale
            # Hard clamp: pasted face width must not exceed template face width
            face_w = max(8.0, cuw * scale)
            target_w = w * head_factor
            scale *= max(0.78, min(1.0, target_w / face_w))
        else:
            head = None
    else:
        head = None

    if head is None:
        pad_x = int(0.22 * max(uw, uh))
        pad_top = int(0.40 * uh)
        pad_bot = int(0.18 * uh)
        left = max(0, ux - pad_x)
        top = max(0, uy - pad_top)
        right = min(upload.width, ux + uw + pad_x)
        bottom = min(upload.height, uy + uh + pad_bot)
        head = upload.crop((left, top, right, bottom))
        u_mid = (
            ((u_le[0] + u_re[0]) / 2 - left),
            ((u_le[1] + u_re[1]) / 2 - top),
        )

    t_mid = ((t_le[0] + t_re[0]) / 2, (t_le[1] + t_re[1]) / 2)

    nw = max(8, int(round(head.width * scale)))
    nh = max(8, int(round(head.height * scale)))
    head_s = head.resize((nw, nh), Image.Resampling.LANCZOS)
    u_mid_s = (u_mid[0] * scale, u_mid[1] * scale)

    px = int(round(t_mid[0] - u_mid_s[0]))
    py = int(round(t_mid[1] - u_mid_s[1] - 0.02 * nh))

    # Soft oval — interior stays opaque for Poisson; edge is for fallback paste
    inset = max(2, min(nw, nh) // 14)
    blur = max(6, min(nw, nh) // 11)
    mask = Image.new("L", (nw, nh), 0)
    ImageDraw.Draw(mask).ellipse((inset, inset, nw - inset, nh - inset), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))

    lit = _match_lighting(head_s, canvas, {"x": x, "y": y, "w": w, "h": h})
    blended = _seamless_paste(canvas, lit, px, py, mask)
    canvas.paste(blended.convert("RGB") if blended.mode != "RGB" else blended)
    print(
        f"  ✓ Body-fit paste scale={scale:.2f} "
        f"(box={scale_box:.2f} iod={scale_iod:.2f}) -> tmpl {w}x{h}"
    )
    return True, lit


def _paste_face(
    canvas: Image.Image,
    region: dict,
    photo_path: Path,
    *,
    prepared: Image.Image | None = None,
) -> tuple[bool, Image.Image | None]:
    """Paste matted upload face into annotated region (no photo background)."""
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    face = prepared if prepared is not None else _prepare_face(photo_path, w, h)
    if face is None:
        return False, None
    if face.size != (w, h):
        face = _resize_face_contain(face.convert("RGBA"), w, h)
    # Ensure matte even if caller passed a prepared opaque crop
    if face.mode != "RGBA" or face.split()[-1].getextrema()[0] >= 250:
        face = _matte_face_rgba(face)
        if face.size != (w, h):
            face = _resize_face_contain(face, w, h)
    face = _match_lighting(face, canvas, region)
    oval = _soft_mask(face.width, face.height)
    fa = face.split()[-1] if face.mode == "RGBA" else oval
    # Keep only intersection of soft oval AND background-stripped alpha
    import numpy as np

    mask_arr = np.minimum(np.asarray(oval, dtype=np.uint16), np.asarray(fa, dtype=np.uint16))
    mask = Image.fromarray(mask_arr.astype(np.uint8))
    blended = _seamless_paste(canvas, face, x, y, mask)
    if canvas.mode == "RGBA":
        canvas.paste(blended.convert("RGBA"))
    else:
        canvas.paste(blended)
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
5. KEEP PHOTO LOOK
   - Stay photoreal. Soften only the face/hair blend — do NOT restyle clothes or background.
"""
    else:
        style_block = """
5. KEEP PHOTO LOOK
   - Stay fully photorealistic. Only blend faces/hair into the scene.
"""

    child_ref = child_portrait or child_head or child_face
    adult_ref = adult_portrait or adult_head or adult_face

    prompt = f"""You are finishing a personalised Grade 1 worksheet photograph.

IMAGE 1 = template scene with faces already PASTED at the CORRECT size and position
          (child LEFT, {adult} RIGHT). Head size already matches the body — do not change it.
IMAGE 2 = CHILD identity photo (features + hairstyle).
IMAGE 3 = {adult.upper()} identity photo (features + hairstyle).

Do ONLY seamless face/hair blending. Strict rules:

A) IDENTITY: LEFT = IMAGE 2, RIGHT = IMAGE 3 (complete face: forehead→chin).
B) SIZE: keep head size/position EXACTLY as IMAGE 1. No enlarge, no bobblehead.
C) ONE FACE ONLY per person — erase any leftover template face under the paste
   (no double mouth, double eyes, ghosting, or semi-transparent overlay).
D) NECK/HAIR: replace template hair on the head with IMAGE 2/3 hair; blend jaw
   smoothly into the existing neck (match neck lighting/colour). Remove sticker edges.
E) SCENE LOCK: do NOT change clothes, hands, arms, body, background, or countable
   objects (fruit, toys, sandwiches, plates). Same object counts as IMAGE 1.

{gender_line}{style_block}
Output ONLY the finished photograph. No text.
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
            "Blend only the pasted face ovals into this photo. "
            "Remove cut edges and any double/ghost faces. "
            "Match jaw to neck. Keep head size. "
            "Do NOT change body, clothes, background, or objects. "
            "Output ONLY the image."
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


def _ai_blend_face_patch(
    patch: Image.Image,
    identity_ref: Image.Image,
    role_label: str,
) -> Image.Image:
    """Blend one face crop. Output is forced back to the exact input size (body proportion)."""
    if not API_KEY:
        return patch

    tw, th = patch.size
    prompt = f"""You are editing IMAGE 1 only — a face crop already pasted onto a worksheet photo.

IMAGE 1 = the exact crop to edit (keep this framing and head size).
IMAGE 2 = identity reference (who the person should look like).

CRITICAL:
- Output must be the SAME crop as IMAGE 1 (same zoom, same head size, same shoulders/background edges).
- Do NOT replace IMAGE 1 with a portrait from IMAGE 2.
- Do NOT add a circular cutout, studio background, or flag.
- Only smooth the pasted face oval into IMAGE 1 and match facial features toward IMAGE 2.
- Keep clothes/background pixels at the edges of IMAGE 1 unchanged.
- No text. Fully opaque.

Output ONLY the edited IMAGE 1 crop.
""".strip()

    content = [
        {"type": "image_url", "image_url": {"url": _image_to_data_url(patch, max_side=768)}},
        {"type": "image_url", "image_url": {"url": _image_to_data_url(identity_ref, max_side=512)}},
        {"type": "text", "text": prompt},
    ]
    blended = _post_image_chat(content)
    if blended is None:
        return patch
    if blended.size != (tw, th):
        blended = blended.resize((tw, th), Image.Resampling.LANCZOS)

    # Reject patches that rewrite the crop (e.g. tiny circular portrait)
    try:
        import numpy as np
        o = np.asarray(patch.convert("RGB"), dtype=np.float32)
        b = np.asarray(blended.convert("RGB"), dtype=np.float32)
        m = max(2, min(tw, th) // 8)
        border = np.ones((th, tw), dtype=bool)
        border[m : th - m, m : tw - m] = False
        delta = float(np.abs(o - b)[border].mean()) if border.any() else 0.0
        if delta > 55:
            print(f"  ⚠️  {role_label} patch rejected (rewrote crop, delta={delta:.0f}) — keeping paste")
            return patch
    except Exception:
        pass
    return blended


def _seamless_face_onto_template(
    template: Image.Image,
    patch: Image.Image,
    region: dict,
) -> Image.Image:
    """Poisson-blend a body-fit face patch into the original template."""
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    if patch.size != (w, h):
        patch = patch.resize((w, h), Image.Resampling.LANCZOS)
    patch = _match_lighting(patch, template, region)
    return _seamless_paste(template, patch, x, y, _soft_mask(w, h))


def _paste_face_patch_on_template(
    template: Image.Image,
    patch: Image.Image,
    region: dict,
) -> Image.Image:
    """Blend a body-fit face patch onto the original template (seamless when possible)."""
    return _seamless_face_onto_template(template, patch, region)


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
    Personalize a stem in three separate steps:

      1) Paste upload faces into annotated meta face_regions
      2) AI seamless blend (faces/hair only)
      3) Image-diff object lock vs soft-paste (template counts)
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

    regions = {r["role"]: r for r in (meta.get("face_regions") or [])}
    adult_region_meta = regions.get(role) or regions.get(locked) or regions.get("adult")
    if "child" not in regions or adult_region_meta is None:
        raise ValueError(
            f"{stem_dir}: meta.json needs face_regions for 'child' and "
            f"'{role or locked or 'adult'}' (template_adult_role)"
        )

    from interactive_templates.face_swap import (
        crop_upload_face,
        crop_upload_head,
    )

    # ── STEP 1: paste into annotated regions (exact meta boxes) ──────────
    print("  ▶ STEP 1/3 — paste into annotated face regions")
    child_region = _use_annotated_region(regions["child"], original_template.size)
    adult_region = _use_annotated_region(adult_region_meta, original_template.size)
    print(
        f"     child box {child_region['w']}x{child_region['h']} @ "
        f"({child_region['x']},{child_region['y']}); "
        f"{role} box {adult_region['w']}x{adult_region['h']} @ "
        f"({adult_region['x']},{adult_region['y']})"
    )

    work = original_template.convert("RGB")
    ok_c, child_face = _paste_into_annotated_region(work, child_region, Path(child_photo))
    ok_a, adult_face = _paste_into_annotated_region(work, adult_region, Path(adult_photo))
    if not ok_c or not ok_a:
        raise ValueError(f"{stem_dir}: face paste failed (child={ok_c}, {role}={ok_a})")
    soft_paste = work.copy()  # count-locked base: template objects + sized faces
    print("     ✓ soft-paste composite ready (objects = template)")

    # ── STEP 2: AI seamless blend (retry; prefer anti-sticker) ────────────
    result = soft_paste
    lock_regions = [child_region, adult_region]
    if run_ai_finish and API_KEY:
        print("  ▶ STEP 2/3 — AI seamless face blend")
        # Matted identity refs so AI does not copy flag/studio backgrounds
        child_face_lock = _matte_face_rgba(
            crop_upload_face(Path(child_photo)) or child_face
        )
        adult_face_lock = _matte_face_rgba(
            crop_upload_face(Path(adult_photo)) or adult_face
        )
        child_head = _matte_face_rgba(
            crop_upload_head(Path(child_photo)) or child_face_lock
        )
        adult_head = _matte_face_rgba(
            crop_upload_head(Path(adult_photo)) or adult_face_lock
        )

        chosen = None
        choose_msg = ""
        for attempt in range(1, 3):
            print(f"     blend attempt {attempt}/2…")
            ai = _ai_finish_identity_locked(
                soft_paste,
                child_face=child_face_lock,
                adult_face=adult_face_lock,
                child_head=child_head,
                adult_head=adult_head,
                child_portrait=child_head,
                adult_portrait=adult_head,
                adult_role=role,
                soft_cartoon=soft_cartoon,
                child_gender=child_gender,
            )
            if ai is None:
                choose_msg = "AI returned no image"
                continue
            chosen, choose_msg = _choose_ai_or_soft(soft_paste, ai, lock_regions)
            print(f"     {choose_msg}")
            if chosen is not soft_paste:
                break

        if chosen is None or chosen is soft_paste:
            print(f"     ⚠️  keeping STEP 1 soft-paste ({choose_msg or 'no AI'})")
            result = soft_paste
        else:
            print("  ▶ STEP 3/3 — image-diff object/count lock")
            merged = _face_only_composite(soft_paste, chosen, lock_regions)
            result, lock_stats = _lock_objects_by_image_diff(
                soft_paste,
                merged,
                lock_regions,
                threshold=_OBJECT_LOCK_THRESHOLD,
                face_pad=_OBJECT_LOCK_FACE_PAD,
            )
            print(
                f"     ✓ locked counts "
                f"(restored {lock_stats['restored_frac']*100:.1f}% non-face px, "
                f"diff_mean={lock_stats['diff_mean']:.1f})"
            )
    else:
        print("  ▶ STEP 2/3 — skipped (no AI)")
        print("  ▶ STEP 3/3 — skipped (soft-paste already has template counts)")
        result = soft_paste

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
