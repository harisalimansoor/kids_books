"""
personalize.py
─────────────────────────────────────────────────────────────────────────────
Kitchen-scenes–style personalization for Grade 1 stems (used by Streamlit):

  STEP 1 — PASTE
      Child: YuNet box + soft ellipse (upload skin tone preserved).
      Adult: hair-expanded box + jaw-soft mask (upload skin tone preserved).

  STEP 2a — AI blend adult (jaw/hairline; upload skin → body)
  STEP 2b — AI blend child (sticker removal; adult locked)
  STEP 3 — BODY SKIN RECOLOUR + COUNT LOCK
      Recolour template neck/arms toward upload skin; lock object counts.
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

ENGINE_ROOT = Path(__file__).resolve().parent  # new_pipeline/swapping_engine/
PIPELINE_ROOT = ENGINE_ROOT.parent  # new_pipeline/
REPO_ROOT = PIPELINE_ROOT.parent  # kids_books/
TEMPLATES_ROOT = PIPELINE_ROOT / "question_templates"

if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(dotenv_path=REPO_ROOT / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Match kitchen_scenes default; override with PERSONALIZE_IMAGE_MODEL if needed
IMAGE_MODEL = (
    os.getenv("PERSONALIZE_IMAGE_MODEL", "openai/gpt-5.4-image-2").strip()
    or "openai/gpt-5.4-image-2"
)

ROOT = TEMPLATES_ROOT

# Exact YuNet boxes by default (kitchen does not pad)
_ANNOTATED_PAD = float(os.getenv("FACE_ANNOTATED_PAD", "1.0"))
_OBJECT_LOCK_THRESHOLD = float(os.getenv("OBJECT_LOCK_THRESHOLD", "12"))
_OBJECT_LOCK_FACE_PAD = float(os.getenv("OBJECT_LOCK_FACE_PAD", "0.55"))
_AI_MAX_FACE_GROW = float(os.getenv("AI_MAX_FACE_GROW", "1.55"))
_AI_MAX_FACE_SHIFT = float(os.getenv("AI_MAX_FACE_SHIFT", "0.18"))
_AI_GHOST_LOW = float(os.getenv("AI_GHOST_LOW_FRAC", "0.32"))
_AI_GHOST_HIGH = float(os.getenv("AI_GHOST_HIGH_FRAC", "0.22"))
# Moderate-diff ghost band — kept high so legitimate AI blends are not rejected;
# body-lock + face-only composite handle residual overlap.
_AI_GHOST_MID_FRAC = float(os.getenv("AI_GHOST_MID_FRAC", "0.55"))
_AI_GHOST_MID_MIN_LOW = float(os.getenv("AI_GHOST_MID_MIN_LOW_FRAC", "0.22"))
_AI_MAX_TILT_DEG = float(os.getenv("AI_MAX_TILT_DEG", "8.0"))
# Stubs for unused legacy landmark paste helpers still in this file
_FACE_FILL = 1.0
_FACE_BODY_SCALE = 1.0
_HEAD_VS_FACE = 1.0
_REGION_EXPAND = 1.0
_REGION_TOP_EXTRA = 0.0
_REGION_BOTTOM_EXTRA = 0.0


def _soft_mask(w: int, h: int, inset: int = 14, blur: int = 22) -> Image.Image:
    """Kitchen-scenes soft elliptical mask (same defaults as swap_faces)."""
    inset = min(inset, max(2, min(w, h) // 8))
    blur = max(8, min(blur, min(w, h) // 6))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((inset, inset, w - inset, h - inset), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def _head_paste_mask(w: int, h: int, *, adult: bool = False) -> Image.Image:
    """
    Soft elliptical paste mask with a gentler jaw fade into the collar/shoulders.

    Core stays fully opaque (no ghosting of the template face). Bottom rim fades
    so template neck/shoulders stay registered under the chin.
    """
    import numpy as np

    inset = max(4, min(w, h) // 18)
    blur = max(14, min(w, h) // 8) if adult else max(12, min(w, h) // 10)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((inset, inset, w - inset, h - inset), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    # Soften bottom rim (jaw → collar) for everyone — stops floating heads
    arr = np.asarray(mask, dtype=np.float32)
    yy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    # Start fading earlier; leave ~35% opacity at the very bottom so shoulders show
    bot_fade = np.clip((0.78 - yy) / 0.30, 0.32, 1.0)
    arr = arr * bot_fade
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L")


def _kitchen_crop_face(path: Path) -> Image.Image:
    """Top-centre square crop — same as kitchen_scenes.crop_face."""
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    s = min(w, h)
    left = (w - s) // 2
    top = max(0, int((h - s) * 0.10))
    return img.crop((left, top, left + s, top + s))


def _cover_fit_rgba(src: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """Cover-fit RGBA into box (centred, slight upward bias for hair)."""
    src = src.convert("RGBA")
    fw, fh = src.size
    if fw < 1 or fh < 1:
        return Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    scale = max(box_w / fw, box_h / fh)
    nw = max(1, int(round(fw * scale)))
    nh = max(1, int(round(fh * scale)))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    ox = (box_w - nw) // 2
    oy = (box_h - nh) // 2 - max(0, int(0.04 * box_h))
    out.paste(resized, (ox, oy), resized)
    return out


def _face_box_in_rgba(src: Image.Image) -> dict | None:
    """YuNet face box (+ landmarks) inside an RGBA head crop, or None."""
    from swapping_engine.face_detect import detect_faces, pick_primary_face

    faces = detect_faces(src.convert("RGB")) or []
    if not faces:
        return None
    primary = pick_primary_face(faces, src.size)
    if not primary:
        return None
    out = {
        "x": int(primary["x"]),
        "y": int(primary["y"]),
        "w": max(8, int(primary["w"])),
        "h": max(8, int(primary["h"])),
    }
    if primary.get("landmarks"):
        out["landmarks"] = primary["landmarks"]
    return out


def _face_anchor(face: dict) -> tuple[float, float]:
    """
    Head-on-body anchor: eyes for X (shoulders), nose→mouth for Y (neck seat).
    """
    lm = face.get("landmarks") or {}
    re, le = lm.get("right_eye"), lm.get("left_eye")
    nose = lm.get("nose")
    mr, ml = lm.get("mouth_right"), lm.get("mouth_left")

    if re and le and len(re) >= 2 and len(le) >= 2:
        ax = 0.5 * (float(re[0]) + float(le[0]))
    elif nose and len(nose) >= 2:
        ax = float(nose[0])
    else:
        ax = float(face["x"]) + float(face["w"]) / 2.0

    if nose and len(nose) >= 2:
        ny = float(nose[1])
        if mr and ml and len(mr) >= 2 and len(ml) >= 2:
            my = 0.5 * (float(mr[1]) + float(ml[1]))
            ay = 0.55 * ny + 0.45 * my
        else:
            ay = ny
    elif re and le and len(re) >= 2 and len(le) >= 2:
        ay = 0.5 * (float(re[1]) + float(le[1])) + float(face["h"]) * 0.18
    else:
        ay = float(face["y"]) + float(face["h"]) * 0.58

    return ax, ay



def _rel_face_in_paste(face: dict, paste_x: int, paste_y: int) -> dict:
    """Convert a canvas-absolute face region to paste-box-relative coords."""
    out = {
        "x": int(face["x"]) - paste_x,
        "y": int(face["y"]) - paste_y,
        "w": int(face["w"]),
        "h": int(face["h"]),
    }
    lm = face.get("landmarks") or {}
    if lm:
        out["landmarks"] = {
            k: [float(pt[0]) - paste_x, float(pt[1]) - paste_y]
            for k, pt in lm.items()
            if pt and len(pt) >= 2
        }
    return out


def _cover_fit_face_aligned(
    src: Image.Image,
    box_w: int,
    box_h: int,
    target_face: dict,
    *,
    body_anchor: dict | None = None,
    canvas: Image.Image | None = None,
    canvas_face_abs: dict | None = None,
) -> Image.Image:
    """
    Place a head crop so its face lands on the template YuNet face + body anchor.

    Uses pose/segmentation (body_align) when canvas + face box are provided.
    """
    if canvas is not None and canvas_face_abs is not None:
        try:
            from swapping_engine.body_align import (
                estimate_body_anchor,
                rel_anchor_in_paste,
            )

            abs_anchor = estimate_body_anchor(canvas, canvas_face_abs)
            paste_x = int(target_face.get("_paste_x", 0))
            paste_y = int(target_face.get("_paste_y", 0))
            if paste_x or paste_y:
                body_anchor = rel_anchor_in_paste(abs_anchor, paste_x, paste_y)
            elif body_anchor is None:
                body_anchor = abs_anchor
            if abs_anchor.get("method") and abs_anchor["method"] != "face_heuristic":
                print(f"     body anchor: {abs_anchor['method']}")
        except Exception as exc:
            print(f"     ⚠️  body anchor skipped: {exc}")

    try:
        from swapping_engine.body_align import align_head_in_box

        return align_head_in_box(
            src,
            box_w,
            box_h,
            target_face,
            body_anchor=body_anchor,
        )
    except Exception:
        pass

    # Fallback (legacy path)
    src = src.convert("RGBA")
    sw, sh = src.size
    if sw < 1 or sh < 1 or box_w < 8 or box_h < 8:
        return Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))

    tx = int(target_face["x"])
    ty = int(target_face["y"])
    tw = max(8, int(target_face["w"]))
    th = max(8, int(target_face["h"]))
    tx = max(0, min(tx, box_w - 8))
    ty = max(0, min(ty, box_h - 8))
    tw = max(8, min(tw, box_w - tx))
    th = max(8, min(th, box_h - ty))

    target_rel = {
        "x": tx,
        "y": ty,
        "w": tw,
        "h": th,
        "landmarks": target_face.get("landmarks") or {},
    }
    tcx, tcy = _face_anchor(target_rel)

    src_face = _face_box_in_rgba(src)
    if src_face is None:
        src_face = {
            "x": int(0.22 * sw),
            "y": int(0.38 * sh),
            "w": max(8, int(0.56 * sw)),
            "h": max(8, int(0.42 * sh)),
        }

    sfw = max(8, int(src_face["w"]))
    sfh = max(8, int(src_face["h"]))
    scx, scy = _face_anchor(src_face)

    # Exact face-size match — slightly under-size so chin sits on the body
    # instead of floating above the collar/shoulders
    scale = 0.5 * (tw / sfw + th / sfh) * 0.96
    scale = max(scale, max(box_w / sw, box_h / sh) * 0.52)
    scale = min(scale, max(box_w / sw, box_h / sh) * 1.18)

    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)

    # Seat onto upper body: nudge DOWN so chin lands on the collar/neck
    # (upward placement is what makes heads look detached from shoulders)
    ox = int(round(tcx - scx * scale))
    oy = int(round(tcy - scy * scale)) + max(2, int(0.05 * th))

    out = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    out.paste(resized, (ox, oy), resized)
    return out


def _kitchen_match_brightness(
    face: Image.Image,
    region: Image.Image,
    *,
    skin_only: bool = False,
    luma_only: bool = False,
) -> Image.Image:
    """
    Match face brightness to the template region.

    skin_only: use skin-like pixels only (avoids green shirt/grass).
    luma_only: scale all channels by the same luminance ratio (no chroma shift).
    """
    import numpy as np

    face_arr = np.array(face.convert("RGB")).astype(np.float32)
    region_arr = np.array(region.convert("RGB")).astype(np.float32)
    flat = region_arr.reshape(-1, 3)

    def _luma(arr3: np.ndarray) -> float:
        return float(
            (0.299 * arr3[..., 0] + 0.587 * arr3[..., 1] + 0.114 * arr3[..., 2]).mean()
        )

    if luma_only or skin_only:
        if skin_only and not luma_only:
            r, g, b = flat[:, 0], flat[:, 1], flat[:, 2]
            skin = (r > 70) & (g > 40) & (b > 30) & (r >= g) & ((r - g) >= 4)
            ref = flat[skin] if int(skin.sum()) >= 25 else flat
        else:
            ref = flat
        src_l = _luma(face_arr)
        tgt_l = float(
            (0.299 * ref[:, 0] + 0.587 * ref[:, 1] + 0.114 * ref[:, 2]).mean()
        )
        scale = float(np.clip(tgt_l / max(src_l, 1e-5), 0.88, 1.28))
        face_arr = np.clip(face_arr * scale, 0, 255).astype(np.uint8)
        result = Image.fromarray(face_arr).convert("RGBA")
        if face.mode == "RGBA":
            result.putalpha(face.split()[3])
        else:
            result.putalpha(255)
        return result

    target = flat.mean(axis=0)
    src = face_arr.reshape(-1, 3).mean(axis=0) + 1e-5
    scale = (target + 1e-5) / src
    scale = np.clip(scale, 0.85, 1.40)
    if scale[1] > scale[0]:
        scale[1] = scale[0]
    face_arr = np.clip(face_arr * scale, 0, 255).astype(np.uint8)
    result = Image.fromarray(face_arr).convert("RGBA")
    if face.mode == "RGBA":
        result.putalpha(face.split()[3])
    else:
        result.putalpha(255)
    return result


def _lighting_ref_for_region(
    canvas: Image.Image,
    region: dict,
    *,
    prefer_neck: bool = False,
) -> Image.Image:
    """
    Crop a lighting/colour reference for the paste.

    For child, prefer the neck/chest band below the YuNet box so the face
    picks up warm sunlit skin instead of cool studio tones.
    """
    cw, ch = canvas.size
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    if prefer_neck:
        ny0 = min(ch - 4, y + int(0.85 * h))
        ny1 = min(ch, y + int(1.40 * h))
        nx0 = max(0, x + int(0.15 * w))
        nx1 = min(cw, x + int(0.85 * w))
        if ny1 - ny0 >= 8 and nx1 - nx0 >= 8:
            return canvas.crop((nx0, ny0, nx1, ny1))
    return canvas.crop((x, y, x + w, y + h))


def _expand_region_for_hair(
    region: dict,
    canvas_size: tuple[int, int],
    *,
    top_frac: float = 0.55,
    side_frac: float = 0.22,
    bottom_frac: float = 0.12,
) -> dict:
    """Expand YuNet face box upward/sideways so upload hairstyle can be pasted."""
    cw, ch = canvas_size
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    top = int(top_frac * h)
    side = int(side_frac * w)
    bot = int(bottom_frac * h)
    nx = max(0, x - side)
    ny = max(0, y - top)
    nx1 = min(cw, x + w + side)
    ny1 = min(ch, y + h + bot)
    out = {
        "x": nx,
        "y": ny,
        "w": max(8, nx1 - nx),
        "h": max(8, ny1 - ny),
    }
    if region.get("role"):
        out["role"] = region["role"]
    if region.get("landmarks"):
        out["landmarks"] = region["landmarks"]
    return out


def _crop_to_opaque(face: Image.Image, pad_frac: float = 0.04) -> Image.Image:
    """Tighten RGBA to the opaque content so cover-fit fills the box with real face."""
    import numpy as np

    rgba = face.convert("RGBA")
    alpha = np.asarray(rgba.split()[-1])
    ys, xs = np.where(alpha > 24)
    if len(xs) < 20:
        return rgba
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    bw, bh = x1 - x0, y1 - y0
    px = int(pad_frac * bw)
    py = int(pad_frac * bh)
    x0 = max(0, x0 - px)
    y0 = max(0, y0 - py)
    x1 = min(rgba.width, x1 + px)
    y1 = min(rgba.height, y1 + py)
    return rgba.crop((x0, y0, x1, y1))


def _resize_face_to_box(face: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """
    Cover-fit the matted face into the annotated box so it fills the slot.

    Crops transparent padding first — otherwise cover-fit only enlarges empty alpha.
    """
    box_w = max(8, int(box_w))
    box_h = max(8, int(box_h))
    src = _matte_face_rgba(face)
    src = _crop_to_opaque(src)
    fw, fh = src.size
    if fw < 1 or fh < 1:
        return Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))

    fill = max(0.98, min(1.12, _FACE_FILL))
    scale = max((box_w * fill) / fw, (box_h * fill) / fh)
    nw = max(1, int(round(fw * scale)))
    nh = max(1, int(round(fh * scale)))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)

    out = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    ox = (box_w - nw) // 2
    oy = (box_h - nh) // 2 - max(0, int(0.03 * box_h))
    out.paste(resized, (ox, oy), resized)
    return out


def _resize_face_contain(face: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """Backward-compatible alias — now cover-fills the annotated box."""
    return _resize_face_to_box(face, box_w, box_h)


def _matte_face_rgba(face: Image.Image) -> Image.Image:
    """
    Strip upload photo background (flags, studio walls, scenery).

    Uses YuNet face ellipse + OpenCV GrabCut so only face/hair stay opaque.
    """
    import cv2
    import numpy as np
    from swapping_engine.face_detect import detect_faces, pick_primary_face

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


def _crop_upload_face_complete(photo_path: Path) -> Image.Image | None:
    """
    Face crop for STEP 1: forehead→chin with modest pad (bg stripped later).
    """
    from swapping_engine.face_detect import detect_faces, pick_primary_face
    from swapping_engine.face_swap import crop_upload_face, crop_upload_head

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
    *,
    pad_x_frac: float = 0.32,
    pad_top_frac: float = 0.50,
    pad_bot_frac: float = 0.35,
    core_boost: float = 1.55,
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
        pad_x = int(pad_x_frac * w)
        pad_top = int(pad_top_frac * h)
        pad_bot = int(pad_bot_frac * h)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_top)
        x1 = min(W, x + w + pad_x)
        y1 = min(H, y + h + pad_bot)
        draw.ellipse((x0, y0, x1, y1), fill=255)

    # Narrow soft rim — keep AI hair/jaw (not soft-paste seams) in the core
    blur = max(5, min(W, H) // 80)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    m = np.asarray(mask, dtype=np.float32) / 255.0
    m = np.clip(m * core_boost, 0.0, 1.0)

    a = np.asarray(a_img, dtype=np.float32)
    b = np.asarray(b_img, dtype=np.float32)
    out = a * (1.0 - m[..., None]) + b * m[..., None]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _harmonize_skin_to_neck(canvas: Image.Image, region: dict) -> Image.Image:
    """
    DEPRECATED — kept as alias. Use _recolor_body_to_upload with an upload photo.
    """
    return canvas


def _ycrcb_skin_mask_rgb(arr) -> "np.ndarray":
    """Boolean skin mask on an RGB uint8 array."""
    import cv2
    import numpy as np

    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    return (
        (cr >= 133)
        & (cr <= 173)
        & (cb >= 77)
        & (cb <= 127)
        & (y >= 60)
        & (y <= 230)
    )


def _sample_skin_lab_from_upload(photo: str | Path | Image.Image):
    """Mean LAB skin stats from an upload photo (identity reference)."""
    import cv2
    import numpy as np

    if isinstance(photo, Image.Image):
        img = photo.convert("RGB")
    else:
        img = Image.open(photo).convert("RGB")
    arr = np.array(img, dtype=np.uint8)
    h, w = arr.shape[:2]
    skin = _ycrcb_skin_mask_rgb(arr)
    cy, cx = h // 2, w // 2
    yy, xx = np.ogrid[:h, :w]
    center = ((xx - cx) / max(w * 0.36, 1)) ** 2 + ((yy - cy) / max(h * 0.42, 1)) ** 2 < 1.0
    sample = skin & center
    if int(sample.sum()) < 40:
        sample = skin
    if int(sample.sum()) < 20:
        return None
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).astype(np.float32)
    return lab[sample].mean(axis=0)


def _recolor_body_to_upload(
    canvas: Image.Image,
    region: dict,
    upload_photo: str | Path | Image.Image,
    *,
    strength: float = 0.82,
) -> Image.Image:
    """
    Recolour template neck / upper-body skin toward the upload photo.

    Upload skin tone is the source of truth — never pull the face toward the
    fair template body (old harmonize direction).
    """
    import cv2
    import numpy as np

    ref_lab = _sample_skin_lab_from_upload(upload_photo)
    if ref_lab is None:
        return canvas

    arr = np.array(canvas.convert("RGB"), dtype=np.uint8)
    h, w_img = arr.shape[:2]
    x, y, rw, rh = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    if rw < 8 or rh < 8:
        return canvas

    lab_full = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).astype(np.float32)

    # (y0, y1, x0, x1, zone_weight)
    zones: list[tuple[int, int, int, int, float]] = []
    ny0 = min(h - 4, y + int(0.82 * rh))
    ny1 = min(h, y + int(1.55 * rh))
    nx0 = max(0, x + int(0.12 * rw))
    nx1 = min(w_img, x + int(0.88 * rw))
    if ny1 - ny0 >= 6 and nx1 - nx0 >= 6:
        zones.append((ny0, ny1, nx0, nx1, 1.0))

    for sx0, sx1, wt in (
        (max(0, x - int(0.06 * rw)), x + int(0.24 * rw), 0.6),
        (x + int(0.76 * rw), min(w_img, x + rw + int(0.06 * rw)), 0.6),
    ):
        ey0 = max(0, y + int(0.30 * rh))
        ey1 = min(h, y + int(1.05 * rh))
        if ey1 - ey0 >= 6 and sx1 - sx0 >= 6:
            zones.append((ey0, ey1, sx0, sx1, wt))

    for zy0, zy1, zx0, zx1, zone_wt in zones:
        patch_rgb = arr[zy0:zy1, zx0:zx1]
        skin = _ycrcb_skin_mask_rgb(patch_rgb)
        if int(skin.sum()) < 12:
            continue

        lab_patch = lab_full[zy0:zy1, zx0:zx1].copy()
        cur = lab_patch[skin].mean(axis=0)
        delta = ref_lab - cur
        delta[0] = float(np.clip(delta[0], -38.0, 38.0))
        delta[1] = float(np.clip(delta[1], -20.0, 20.0))
        delta[2] = float(np.clip(delta[2], -20.0, 20.0))

        zh, zw = zy1 - zy0, zx1 - zx0
        zyy, zxx = np.ogrid[:zh, :zw]
        feather = np.clip(
            1.0
            - 0.32
            * (
                ((zxx - zw / 2) / max(zw / 2, 1)) ** 2
                + ((zyy - zh / 2) / max(zh / 2, 1)) ** 2
            ),
            0.12,
            1.0,
        ).astype(np.float32)
        mask = skin.astype(np.float32) * feather * float(strength) * float(zone_wt)
        mask = np.clip(mask, 0.0, 1.0)
        for c in range(3):
            lab_patch[:, :, c] = lab_patch[:, :, c] + delta[c] * mask
        lab_full[zy0:zy1, zx0:zx1] = np.clip(lab_patch, 0, 255)

    out = cv2.cvtColor(lab_full.astype(np.uint8), cv2.COLOR_LAB2RGB)
    return Image.fromarray(out)


def _degreen_face(canvas: Image.Image, region: dict) -> Image.Image:
    """
    Remove green / yellow-olive cast from the child face oval after AI blend.
    """
    import cv2
    import numpy as np

    out = canvas.convert("RGB")
    arr = np.array(out, dtype=np.uint8)
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    if w < 8 or h < 8:
        return out

    yy, xx = np.ogrid[:h, :w]
    ell = ((xx - w / 2) / (0.46 * w)) ** 2 + ((yy - h / 2) / (0.50 * h)) ** 2
    m = np.clip(1.15 - ell, 0, 1).astype(np.float32)

    patch = arr[y : y + h, x : x + w].astype(np.float32)
    r, g, b = patch[:, :, 0], patch[:, :, 1], patch[:, :, 2]

    # How olive/yellow vs natural skin (natural kids' faces usually have more B)
    olive = np.clip(((r + g) * 0.5 - b) - 75.0, 0, 35)
    # Also when G is close to R (greenish midtones)
    green_push = np.clip((g - 0.92 * r) + 8.0, 0, 20)
    strength = m * 0.85

    g = g - (0.45 * olive + 0.55 * green_push) * strength
    b = b + (0.50 * olive) * strength
    r = r + (0.12 * green_push) * strength - (0.05 * olive) * strength

    patch[:, :, 0] = np.clip(r, 0, 255)
    patch[:, :, 1] = np.clip(g, 0, 255)
    patch[:, :, 2] = np.clip(b, 0, 255)

    lab = cv2.cvtColor(patch.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    # OpenCV a↑ = less green; b↓ = less yellow
    lab[:, :, 1] = np.clip(lab[:, :, 1] + 3.5 * strength, 0, 255)
    lab[:, :, 2] = np.clip(lab[:, :, 2] - 2.5 * strength, 0, 255)
    patch = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2RGB)

    arr[y : y + h, x : x + w] = patch
    return Image.fromarray(arr)


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
    from swapping_engine.face_detect import detect_faces

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
            annotated_area = float(max(1, w * h))
            # Primary: face must stay near the annotated box (source of truth)
            if area > 1.55 * annotated_area:
                return False, (
                    f"{role}: AI face area {area:.0f} > "
                    f"1.55× annotated {w*h}"
                )
            soft_faces = detect_faces(soft_paste.crop((x0, y0, x1, y1))) or []
            if soft_faces:
                sf = max(soft_faces, key=lambda ff: ff["w"] * ff["h"])
                soft_area = max(1.0, float(sf["w"] * sf["h"]))
                # Soft-paste YuNet can under-read cover-fill; allow more slack
                if area > max_grow * 1.25 * soft_area and area > 1.2 * annotated_area:
                    return False, (
                        f"{role}: AI grew face "
                        f"{area/soft_area:.2f}× vs soft-paste"
                    )
                # Reject if AI shifted the face off the neck/shoulder axis
                try:
                    from swapping_engine.body_align import face_centroid, face_eye_tilt_deg
                    import math

                    sfc = face_centroid(sf)
                    afc = face_centroid(f)
                    shift = math.hypot(afc[0] - sfc[0], afc[1] - sfc[1])
                    if shift > _AI_MAX_FACE_SHIFT * max(w, h):
                        return False, (
                            f"{role}: AI shifted face {shift:.0f}px off body "
                            f"(max {_AI_MAX_FACE_SHIFT:.0%} of box)"
                        )
                    tilt_drift = abs(face_eye_tilt_deg(f) - face_eye_tilt_deg(sf))
                    if tilt_drift > _AI_MAX_TILT_DEG:
                        return False, (
                            f"{role}: AI tilt drift {tilt_drift:.1f}° "
                            f"(max {_AI_MAX_TILT_DEG:.0f}°)"
                        )
                except Exception:
                    pass

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
        mid = float(((core >= 12.0) & (core <= 45.0)).mean())
        if low >= _AI_GHOST_LOW and high >= _AI_GHOST_HIGH:
            return False, (
                f"{role}: ghosting "
                f"(unchanged={low:.2f}, rewritten={high:.2f})"
            )
        # Broad moderate-diff band with a bit of unchanged pixel too = classic
        # soft alpha double-exposure (two different faces partially overlaid),
        # not a clean full-strength repaint. Catch it even though it isn't
        # the bimodal low/high pattern above.
        if mid >= _AI_GHOST_MID_FRAC and low >= _AI_GHOST_MID_MIN_LOW:
            return False, (
                f"{role}: ghosting "
                f"(moderate-diff band={mid:.2f}, unchanged={low:.2f}) — "
                "likely a partial alpha double-exposure"
            )

        # Footprint check removed — edge softening legitimately touches a wide ring;
        # annotated-box face area (above) is the size gate that matters.

    return True, "ok"


def _body_lock_faces(
    reference: Image.Image,
    ai: Image.Image,
    face_boxes: list[dict],
) -> Image.Image:
    """Snap AI faces back onto template body if detection shows drift."""
    try:
        from swapping_engine.body_align import snap_ai_faces_to_reference

        return snap_ai_faces_to_reference(
            reference,
            ai,
            face_boxes,
            max_shift_frac=_AI_MAX_FACE_SHIFT,
        )
    except Exception as exc:
        print(f"     ⚠️  body-lock skipped: {exc}")
        return ai


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


def _rescale_overgrown_ai_faces(
    soft_paste: Image.Image,
    ai: Image.Image,
    regions: list[dict],
    *,
    max_grow: float = 1.08,
) -> Image.Image:
    """
    If AI enlarged a face vs soft-paste, shrink that face patch back toward
    soft-paste size (keeps identity blend but restores body proportions).
    """
    import numpy as np
    from swapping_engine.face_detect import detect_faces

    if ai.size != soft_paste.size:
        ai = ai.resize(soft_paste.size, Image.Resampling.LANCZOS)

    out = ai.convert("RGB").copy()
    soft = soft_paste.convert("RGB")
    W, H = soft.size

    for region in regions:
        x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
        pad = int(0.45 * max(w, h))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
        if x1 - x0 < 16 or y1 - y0 < 16:
            continue

        soft_crop = soft.crop((x0, y0, x1, y1))
        ai_crop = out.crop((x0, y0, x1, y1))
        sf = detect_faces(soft_crop) or []
        af = detect_faces(ai_crop) or []
        if not sf or not af:
            continue
        s = max(sf, key=lambda f: f["w"] * f["h"])
        a = max(af, key=lambda f: f["w"] * f["h"])
        soft_area = max(1.0, float(s["w"] * s["h"]))
        ai_area = max(1.0, float(a["w"] * a["h"]))
        grow = (ai_area / soft_area) ** 0.5  # linear scale factor
        if grow <= max_grow:
            continue

        shrink = 1.0 / grow
        # Scale AI crop about AI face center, then composite over soft in this window
        acx = a["x"] + a["w"] / 2.0
        acy = a["y"] + a["h"] / 2.0
        aw, ah = ai_crop.size
        nw = max(8, int(round(aw * shrink)))
        nh = max(8, int(round(ah * shrink)))
        scaled = ai_crop.resize((nw, nh), Image.Resampling.LANCZOS)
        # Place so face center maps to soft face center
        scx = s["x"] + s["w"] / 2.0
        scy = s["y"] + s["h"] / 2.0
        # After shrink, AI face center in scaled coords:
        acx_s = acx * shrink
        acy_s = acy * shrink
        ox = int(round(scx - acx_s))
        oy = int(round(scy - acy_s))

        canvas = soft_crop.copy()
        # Soft oval over the soft face box for blend
        mask = Image.new("L", (nw, nh), 0)
        inset = max(2, min(nw, nh) // 20)
        ImageDraw.Draw(mask).ellipse((inset, inset, nw - inset, nh - inset), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(max(4, min(nw, nh) // 16)))
        canvas.paste(scaled, (ox, oy), mask)

        out.paste(canvas, (x0, y0))
        role = region.get("role") or "face"
        print(f"     ↳ scale-locked {role}: AI face shrink ×{shrink:.2f} (was {grow:.2f}× soft)")

    return out


def _correct_ai_drift(
    soft_paste: Image.Image,
    ai: Image.Image,
    regions: list[dict],
    face_boxes: list[dict] | None = None,
) -> Image.Image:
    """Rescale + body-lock AI faces toward soft-paste before accept/reject."""
    boxes = face_boxes or regions
    out = _rescale_overgrown_ai_faces(soft_paste, ai, regions)
    return _body_lock_faces(soft_paste, out, boxes)


def _composite_ai_face(
    base: Image.Image,
    soft_paste: Image.Image,
    ai_face: Image.Image,
    region: dict,
    face_box: dict,
    *,
    pad_x_frac: float = 0.32,
    pad_top_frac: float = 0.50,
    pad_bot_frac: float = 0.35,
    core_boost: float = 1.55,
) -> Image.Image:
    """Merge drift-corrected AI into base at one face oval, then body-lock."""
    corrected = _correct_ai_drift(soft_paste, ai_face, [region], [face_box])
    merged = _face_only_composite(
        base,
        corrected,
        [region],
        pad_x_frac=pad_x_frac,
        pad_top_frac=pad_top_frac,
        pad_bot_frac=pad_bot_frac,
        core_boost=core_boost,
    )
    return _body_lock_faces(soft_paste, merged, [face_box])


def _choose_ai_or_soft(
    soft_paste: Image.Image,
    ai: Image.Image,
    regions: list[dict],
    *,
    face_boxes: list[dict] | None = None,
) -> tuple[Image.Image, str]:
    """
    Prefer AI for seamless swap. Drift is corrected via body-lock first.
    Workbook pages always ship with AI when it removes sticker edges — QA
    ghost/shift flags are advisory, not a reason to keep template faces visible.
    """
    ai_work = _correct_ai_drift(soft_paste, ai, regions, face_boxes)
    ok, reason = _ai_blend_acceptable(soft_paste, ai_work, regions)
    soft_sticker = _sticker_edge_score(soft_paste, regions)
    ai_sticker = _sticker_edge_score(ai_work, regions)

    if ok:
        return ai_work, f"accepted ({reason}; sticker {soft_sticker:.1f}->{ai_sticker:.1f})"

    # AI removes sticker edges → use it (real face swap beats visible paste oval)
    if ai_sticker <= soft_sticker * 1.08:
        return ai_work, (
            f"accepted ({reason}; sticker {soft_sticker:.1f}->{ai_sticker:.1f})"
        )

    # Only keep soft-paste when AI is clearly worse on edges
    return soft_paste, f"rejected ({reason}; sticker {soft_sticker:.1f}->{ai_sticker:.1f})"


def _sticker_may_override(reason: str) -> bool:
    """False when forcing AI would risk double-face / temple ghosting."""
    r = (reason or "").lower()
    return not any(
        k in r
        for k in ("double-face", "shifted face", "tilt drift", "ghosting")
    )

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
    *,
    align_to: dict | None = None,
) -> tuple[bool, Image.Image | None]:
    """
    Kitchen-style paste into YuNet box.

    Child: upload head → soft ellipse (skin tone preserved).
    Adult: upload head into hair-expanded box + jaw-soft mask.
    align_to: original YuNet face (canvas coords) — adults align face→body.
    """
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    photo_path = Path(photo_path)
    if not photo_path.exists() or w < 8 or h < 8:
        return False, None

    was_rgb = canvas.mode == "RGB"
    base = canvas.convert("RGBA") if was_rgb else canvas
    role = (region.get("role") or "").lower()
    adult = role not in ("child", "")

    if adult:
        try:
            from swapping_engine.face_swap import crop_upload_head

            head = crop_upload_head(photo_path)
        except Exception:
            head = None
        if head is None:
            head = _kitchen_crop_face(photo_path)
        head = _matte_face_rgba(head)
        # Align upload face onto template YuNet face (not box centre) so
        # shoulders/neck stay registered when the paste box is hair-expanded.
        face_target = align_to or region
        rel = _rel_face_in_paste(face_target, x, y)
        rel["_paste_x"] = x
        rel["_paste_y"] = y
        face = _cover_fit_face_aligned(
            head,
            w,
            h,
            rel,
            canvas=base,
            canvas_face_abs=face_target,
        )
        mask = _head_paste_mask(w, h, adult=True)
        src_a = face.split()[3]
        mask = Image.composite(mask, Image.new("L", (w, h), 0), src_a)
    else:
        # Landmark + body-anchor alignment (segmentation / pose when available)
        try:
            from swapping_engine.face_swap import crop_upload_head

            head = crop_upload_head(photo_path)
        except Exception:
            head = None
        if head is None:
            head = _kitchen_crop_face(photo_path)
        head = _matte_face_rgba(head)
        face_target = align_to or region
        rel = _rel_face_in_paste(face_target, x, y)
        rel["_paste_x"] = x
        rel["_paste_y"] = y
        face = _cover_fit_face_aligned(
            head,
            w,
            h,
            rel,
            canvas=base,
            canvas_face_abs=face_target,
        )
        mask = _head_paste_mask(w, h, adult=False)
        src_a = face.split()[3]
        mask = Image.composite(mask, Image.new("L", (w, h), 0), src_a)

    # Do not match paste colour to template neck — that pulls upload faces toward
    # the template body's skin tone. Scene lighting is handled in the AI blend pass.
    base.paste(face, (x, y), mask)

    if was_rgb:
        canvas.paste(base.convert("RGB"))
    else:
        canvas.paste(base)

    tag = "upload skin preserved" if adult else "child paste"
    print(f"  ✓ Kitchen-style paste '{role or 'face'}' → {w}x{h} @ ({x},{y}) [{tag}]")
    return True, face


def _paste_face(
    canvas: Image.Image,
    region: dict,
    photo_path: Path,
    *,
    prepared: Image.Image | None = None,
) -> tuple[bool, Image.Image | None]:
    """Alias — kitchen-style paste (prepared arg ignored; matches kitchen API)."""
    return _paste_into_annotated_region(canvas, region, photo_path)


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
    from swapping_engine.face_detect import detect_faces, pick_primary_face
    from swapping_engine.face_swap import crop_upload_face
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

    # Target = fill the annotated template face box (not under-size stickers)
    body_scale = max(0.95, min(1.12, _FACE_BODY_SCALE if _FACE_BODY_SCALE != 1.0 else 1.02))
    head_factor = max(0.98, min(1.08, _HEAD_VS_FACE if _HEAD_VS_FACE != 1.0 else 1.02))
    tw, th = w * head_factor, h * head_factor
    scale_box = ((tw / max(8.0, uw)) + (th / max(8.0, uh))) / 2.0
    scale_iod = (t_iod / u_iod) * head_factor
    # Prefer filling the annotated box; IOD keeps eye spacing honest
    scale = max(scale_box, scale_iod * 0.95) * body_scale

    # Prefer tight face crop (less bg) so soft oval ≈ face area on the body
    face_crop = crop_upload_face(photo_path)
    if face_crop is not None:
        crop_faces = detect_faces(face_crop) or []
        crop_primary = pick_primary_face(crop_faces, face_crop.size) if crop_faces else None
        if crop_primary and crop_primary.get("landmarks"):
            head = face_crop.convert("RGBA")
            c_lm = crop_primary["landmarks"]
            u_mid = (
                (c_lm["left_eye"][0] + c_lm["right_eye"][0]) / 2,
                (c_lm["left_eye"][1] + c_lm["right_eye"][1]) / 2,
            )
            cuw, cuh = int(crop_primary["w"]), int(crop_primary["h"])
            scale_box = ((tw / max(8.0, cuw)) + (th / max(8.0, cuh))) / 2.0
            c_iod = max(8.0, dist(c_lm["left_eye"], c_lm["right_eye"]))
            scale_iod = (t_iod / c_iod) * head_factor
            scale = max(scale_box, scale_iod * 0.95) * body_scale
            # Clamp: stay near annotated box size (no tiny stickers, no giant heads)
            face_w = max(8.0, cuw * scale)
            target_w = float(w)
            scale *= float(max(0.95, min(1.12, target_w / face_w)))
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


def _post_image_chat(content: list, *, retries: int = 3) -> Image.Image | None:
    """Call OpenRouter image model; retry on 502/503/overload."""
    import time

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
    last_err = ""
    for attempt in range(max(1, retries)):
        try:
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=200)
        except Exception as exc:
            last_err = str(exc)
            print(f"  ⚠️  personalize request failed ({exc})")
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
                continue
            return None
        if resp.status_code in (429, 500, 502, 503):
            last_err = f"{resp.status_code}: {resp.text[:200]}"
            print(f"  ⚠️  personalize API {resp.status_code} (attempt {attempt + 1}/{retries})")
            if attempt + 1 < retries:
                time.sleep(2 ** attempt + 1)
                continue
            print(f"  ⚠️  personalize API failed after retries: {last_err}")
            return None
        if resp.status_code != 200:
            print(f"  ⚠️  personalize API failed ({resp.status_code}): {resp.text[:300]}")
            return None
        try:
            data = resp.json()
        except Exception as exc:
            print(f"  ⚠️  personalize: bad JSON ({exc})")
            return None
        # Some providers return 200 with an error / overload message and no image
        err_hint = _response_hint(data).lower()
        img_ref = _extract_image_url(data)
        if not img_ref and any(k in err_hint for k in ("overload", "try again", "502", "503")):
            last_err = err_hint[:200]
            print(f"  ⚠️  personalize overloaded (attempt {attempt + 1}/{retries})")
            if attempt + 1 < retries:
                time.sleep(2 ** attempt + 1)
                continue
            print(f"  ⚠️  personalize: no image returned — {last_err}")
            return None
        if not img_ref:
            print(f"  ⚠️  personalize: no image returned — {_response_hint(data)}")
            return None
        if img_ref.startswith("data:image"):
            raw = base64.b64decode(img_ref.split(",", 1)[1])
        else:
            raw = requests.get(img_ref, timeout=60).content
        return Image.open(BytesIO(raw)).convert("RGB")
    return None


_SKIN_TONE_RULES = """
SKIN TONE (CRITICAL):
- Keep the exact skin tone, undertone, and depth from the upload identity photo (IMAGE 2 / IMAGE 3).
- Recolour visible template neck, ears, arms, and hands to match the upload — never lighten a dark
  upload face to match a fair template body, and never darken a fair upload to match a tan body.
- The upload photo is the skin reference for the whole visible body.

NECK / SHOULDERS (CRITICAL):
- The head must sit ON the body — chin attached to the collar, neck centred between the shoulders.
- Do NOT float the head above the shoulders or shift it left/right off the torso axis.
- Preserve the template shirt collar and shoulder line; only soften the jaw→neck seam.
""".strip()


def _ai_blend_kitchen_style(
    intermediate: Image.Image,
    *,
    adult_role: str,
    soft_cartoon: bool = False,
    child_head: Image.Image | None = None,
    adult_head: Image.Image | None = None,
    focus: str = "both",
) -> Image.Image | None:
    """
    Kitchen-style AI blend.

    focus:
      - "adult" — fix adult jaw/hairline only (keep child as pasted)
      - "child" — fix child sticker only (keep adult exactly)
      - "both"  — blend both faces
    """
    if not API_KEY:
        return None

    adult = adult_role.replace("_", " ")
    style_line = (
        "Keep a soft storybook look."
        if soft_cartoon
        else "Stay photorealistic."
    )
    focus = (focus or "both").strip().lower()
    has_refs = child_head is not None and adult_head is not None

    if focus == "child":
        prompt = f"""IMAGE 1 = worksheet scene. The {adult} on the RIGHT is already perfectly blended — do NOT change them at all.
IMAGE 2 = CHILD upload identity (face + skin tone reference).
IMAGE 3 = {adult.upper()} reference only.

The CHILD on the LEFT still looks like a pasted sticker (hard oval edge).

Fix ONLY the LEFT child to the SAME blend quality as the {adult} on the RIGHT:
1. Completely erase the hard oval / cutout edge — jaw and hairline must melt into the head.
2. Attach the head to the body: chin sits on the collar; neck centred on the shoulders.
   Recolour visible neck/ears to match IMAGE 2 skin. Do NOT float or slide the head.
3. Keep IMAGE 2 facial identity and skin tone; keep exact head size and position from IMAGE 1.
4. Do NOT touch the {adult} on the RIGHT.
5. Do not change clothes, countable objects, or background.
6. {style_line}
{_SKIN_TONE_RULES}
Output ONLY the finished image."""
    elif focus == "adult":
        prompt = f"""IMAGE 1 = worksheet scene with child (LEFT) and {adult} (RIGHT) faces pasted.
IMAGE 2 = CHILD reference — keep the LEFT child size/position; light edge soften only if needed.
IMAGE 3 = {adult.upper()} upload (face + hairstyle + skin tone for the RIGHT person).

Fix ONLY the {adult} on the RIGHT:
1. Seamless jaw→neck and hairline (no mask/sticker edge); chin attached to the collar.
2. Prefer IMAGE 3 hairstyle over leftover template hair.
3. Keep IMAGE 3 skin tone on face, neck, ears, and visible arms/hands — recolour template body
   skin toward IMAGE 3; do not lighten or darken the face toward the old template body.
4. Keep head size/pose from IMAGE 1. Do not enlarge faces or float the head off the shoulders.
5. Do not change clothes, countable objects, or background.
6. {style_line}
{_SKIN_TONE_RULES}
Output ONLY the finished image."""
    else:
        prompt = f"""IMAGE 1 = worksheet scene with child (LEFT) and {adult} (RIGHT) faces pasted.
IMAGE 2 = CHILD upload (identity + hairstyle + skin tone).
IMAGE 3 = {adult.upper()} upload (identity + hairstyle + skin tone).

Blend BOTH faces seamlessly (no sticker/oval edges):
1. LEFT = IMAGE 2 identity; RIGHT = IMAGE 3 identity.
2. Recolour each person's visible neck/arms/hands to match their upload skin tone.
3. Prefer upload hairstyles over template hair.
4. Keep exact head sizes/positions from IMAGE 1 — do not enlarge.
5. Do not change clothes, countable objects, or background.
6. {style_line}
{_SKIN_TONE_RULES}
Output ONLY the finished image."""

    if has_refs:
        content = [
            {"type": "image_url", "image_url": {"url": _image_to_data_url(intermediate, max_side=1024, fmt="PNG")}},
            {"type": "image_url", "image_url": {"url": _image_to_data_url(child_head, max_side=512)}},
            {"type": "image_url", "image_url": {"url": _image_to_data_url(adult_head, max_side=512)}},
            {"type": "text", "text": prompt},
        ]
    else:
        content = [
            {"type": "image_url", "image_url": {"url": _image_to_data_url(intermediate, max_side=1024, fmt="PNG")}},
            {"type": "text", "text": prompt},
        ]

    print(f"  🎨 Kitchen AI blend focus={focus} ({IMAGE_MODEL})…")
    out = _post_image_chat(content)
    if out is None:
        return None
    if out.size != intermediate.size:
        out = out.resize(intermediate.size, Image.Resampling.LANCZOS)
    return out


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
B) SIZE (CRITICAL): Keep EXACT head size from IMAGE 1. Do NOT zoom, enlarge,
   or crop-in on either face. If unsure, leave size identical to IMAGE 1 and
   only soften the oval edges. No bobbleheads.
C) ONE FACE ONLY per person — erase any leftover template face under the paste
   (no double mouth, double eyes, ghosting, or semi-transparent overlay).
D) NECK/HAIR: blend jaw smoothly; recolour visible template neck/ears/arms/hands to match
   the upload skin tone (IMAGE 2 / IMAGE 3). Never pull upload faces toward template body colour.
   Prefer upload hairstyle; remove sticker edges.
E) SCENE LOCK: do NOT change clothes, countable objects, or background composition.
   Same object counts as IMAGE 1.

{_SKIN_TONE_RULES}
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
            "Keep upload skin tone; recolour template neck/arms to match uploads. "
            "Keep head size. Do NOT change body clothes, background, or objects. "
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



def run_child_adult_face_pipeline(
    canvas: Image.Image,
    *,
    child_region: dict,
    adult_region: dict,
    child_photo: str | Path,
    adult_photo: str | Path,
    adult_role: str,
    soft_cartoon: bool = False,
    run_ai_finish: bool = True,
    require_ai: bool = True,
    expand_adult_hair: bool = True,
    label: str = "scene",
) -> Image.Image:
    """
    Child + adult face pipeline (lives entirely in swapping_engine):

      1) paste child (YuNet) + adult (optional hair box)
      2a) AI blend adult  2b) AI blend child
      3) count/object lock + child degreen

    Returns RGB image with faces personalized.
    """
    child_photo = Path(child_photo)
    adult_photo = Path(adult_photo)
    role = (adult_role or "mother").strip().lower()
    size = canvas.convert("RGB").size

    # Keep raw YuNet boxes for landmark seating; expand only for hair room
    child_face_box = _use_annotated_region(child_region, size)
    adult_face_box = _use_annotated_region(adult_region, size)
    # Child: small hair lift, almost no bottom expand (protects shoulders/collar)
    child_region = _expand_region_for_hair(
        child_face_box, size, top_frac=0.30, side_frac=0.14, bottom_frac=0.02
    )
    if expand_adult_hair:
        # Prefer top/side hair pad; keep bottom tight so shoulders stay put
        adult_region = _expand_region_for_hair(
            adult_face_box, size, top_frac=0.55, side_frac=0.26, bottom_frac=0.04
        )
    else:
        adult_region = adult_face_box
    if not adult_region.get("role"):
        adult_region = {**adult_region, "role": role}
    if not child_region.get("role"):
        child_region = {**child_region, "role": "child"}

    print(f"  ▶ Child+adult face pipeline ({label})")
    print(
        f"     child {child_region['w']}x{child_region['h']} @ "
        f"({child_region['x']},{child_region['y']}) "
        f"(face {child_face_box['w']}x{child_face_box['h']} @ "
        f"{child_face_box['x']},{child_face_box['y']}); "
        f"{role} {adult_region['w']}x{adult_region['h']} @ "
        f"({adult_region['x']},{adult_region['y']}) "
        f"(face {adult_face_box['w']}x{adult_face_box['h']} @ "
        f"{adult_face_box['x']},{adult_face_box['y']})"
    )

    work = canvas.convert("RGB")
    ok_c, _ = _paste_into_annotated_region(
        work, child_region, child_photo, align_to=child_face_box
    )
    ok_a, _ = _paste_into_annotated_region(
        work, adult_region, adult_photo, align_to=adult_face_box
    )
    if not ok_c or not ok_a:
        raise ValueError(f"face paste failed (child={ok_c}, {role}={ok_a})")
    soft_paste = work.copy()
    print("     ✓ soft paste ready")

    result = soft_paste
    lock_regions = [child_region, adult_region]
    adult_ai_ok = False
    child_ai_ok = False

    if run_ai_finish and API_KEY:
        from swapping_engine.face_swap import crop_upload_head

        child_head = _matte_face_rgba(
            crop_upload_head(child_photo) or _kitchen_crop_face(child_photo)
        )
        adult_head = _matte_face_rgba(
            crop_upload_head(adult_photo) or _kitchen_crop_face(adult_photo)
        )
        work_img = soft_paste

        print(f"  ▶ AI blend ({role} seam)")
        ai_adult = _ai_blend_kitchen_style(
            work_img,
            adult_role=role,
            soft_cartoon=soft_cartoon,
            child_head=child_head,
            adult_head=adult_head,
            focus="adult",
        )
        if ai_adult is not None:
            chosen_a, msg_a = _choose_ai_or_soft(
                work_img, ai_adult, [adult_region], face_boxes=[adult_face_box]
            )
            print(f"     {msg_a}")
            if chosen_a is not work_img:
                work_img = _composite_ai_face(
                    work_img, soft_paste, chosen_a, adult_region, adult_face_box
                )
            adult_ai_ok = True
        else:
            print(f"     ⚠️  AI {role} pass empty — keeping paste adult")
            adult_ai_ok = True

        print("  ▶ AI blend (child sticker fix)")
        ai_child = _ai_blend_kitchen_style(
            work_img,
            adult_role=role,
            soft_cartoon=soft_cartoon,
            child_head=child_head,
            adult_head=adult_head,
            focus="child",
        )
        if ai_child is None:
            print("     ⚠️  AI child pass empty — keeping current")
            result = work_img
            child_ai_ok = True
        else:
            chosen_c, msg_c = _choose_ai_or_soft(
                work_img, ai_child, [child_region], face_boxes=[child_face_box]
            )
            print(f"     {msg_c}")
            if chosen_c is not work_img:
                print("  ▶ composite + count lock + degreen")
                merged = _composite_ai_face(
                    work_img,
                    soft_paste,
                    chosen_c,
                    child_region,
                    child_face_box,
                    pad_x_frac=0.55,
                    pad_top_frac=0.70,
                    pad_bot_frac=0.22,
                    core_boost=1.85,
                )
                merged = _face_only_composite(merged, work_img, [adult_region])
                try:
                    merged = _degreen_face(merged, child_region)
                except Exception as exc:
                    print(f"     ⚠️  degreen skipped: {exc}")
                result, lock_stats = _lock_objects_by_image_diff(
                    soft_paste,
                    merged,
                    lock_regions,
                    threshold=_OBJECT_LOCK_THRESHOLD,
                    face_pad=max(_OBJECT_LOCK_FACE_PAD, 0.85),
                )
                result = _body_lock_faces(
                    soft_paste, result, [child_face_box, adult_face_box]
                )
                print(
                    f"     ✓ locked counts "
                    f"(restored {lock_stats['restored_frac']*100:.1f}% non-face px, "
                    f"diff_mean={lock_stats['diff_mean']:.1f})"
                )
            else:
                result = work_img
            child_ai_ok = True

        # Fallback: either face still looks like a sticker → one combined AI pass
        need_child = _sticker_edge_score(result, [child_region]) > 20.0
        need_adult = _sticker_edge_score(result, [adult_region]) > 20.0
        if need_child or need_adult:
            print(
                f"  ▶ AI blend fallback (both faces; sticker child={need_child}, {role}={need_adult})"
            )
            ai_both = _ai_blend_kitchen_style(
                result,
                adult_role=role,
                soft_cartoon=soft_cartoon,
                child_head=child_head,
                adult_head=adult_head,
                focus="both",
            )
            if ai_both is not None:
                chosen_b, msg_b = _choose_ai_or_soft(
                    soft_paste, ai_both, lock_regions,
                    face_boxes=[child_face_box, adult_face_box],
                )
                print(f"     {msg_b}")
                if chosen_b is not soft_paste:
                    merged = _face_only_composite(
                        soft_paste, chosen_b, lock_regions, core_boost=1.75
                    )
                    merged = _body_lock_faces(
                        soft_paste, merged, [child_face_box, adult_face_box]
                    )
                    try:
                        merged = _degreen_face(merged, child_region)
                    except Exception:
                        pass
                    result, lock_stats = _lock_objects_by_image_diff(
                        soft_paste,
                        merged,
                        lock_regions,
                        threshold=_OBJECT_LOCK_THRESHOLD,
                        face_pad=max(_OBJECT_LOCK_FACE_PAD, 0.85),
                    )
                    result = _body_lock_faces(
                        soft_paste, result, [child_face_box, adult_face_box]
                    )
                    print(
                        f"     ✓ both-face fallback locked "
                        f"(restored {lock_stats['restored_frac']*100:.1f}% non-face px)"
                    )

        if require_ai and not (adult_ai_ok and child_ai_ok):
            print(
                f"     ⚠️  AI incomplete for {label} "
                f"(adult_ok={adult_ai_ok}, child_ok={child_ai_ok}) — using best available"
            )
    elif run_ai_finish and not API_KEY:
        if require_ai:
            raise RuntimeError(
                "OPENROUTER_API_KEY is missing — cannot AI-blend faces for the workbook."
            )
        result = soft_paste
    else:
        result = soft_paste

    # Pull template neck/upper-body skin toward each upload (upload = source of truth)
    try:
        result = _recolor_body_to_upload(result, child_region, child_photo)
        result = _recolor_body_to_upload(result, adult_region, adult_photo)
        print("     ✓ body skin recoloured toward uploads")
    except Exception as exc:
        print(f"     ⚠️  body skin recolor skipped: {exc}")

    return result.convert("RGB")


# Back-compat alias (older callers / compositor). Prefer run_child_adult_face_pipeline.
run_kitchen_face_pipeline = run_child_adult_face_pipeline


def run_child_only_face_pipeline(
    canvas: Image.Image,
    *,
    child_region: dict,
    child_photo: str | Path,
    soft_cartoon: bool = False,
    run_ai_finish: bool = True,
    require_ai: bool = True,
    label: str = "scene",
) -> Image.Image:
    """Personalise only the child face (Hamdan child-only / no-adult templates)."""
    child_photo = Path(child_photo)
    size = canvas.convert("RGB").size
    child_face_box = _use_annotated_region(child_region, size)
    child_region = _expand_region_for_hair(
        child_face_box, size, top_frac=0.30, side_frac=0.14, bottom_frac=0.02
    )
    if not child_region.get("role"):
        child_region = {**child_region, "role": "child"}

    print(f"  ▶ Child-only face pipeline ({label})")
    print(
        f"     child {child_region['w']}x{child_region['h']} @ "
        f"({child_region['x']},{child_region['y']}) "
        f"(face {child_face_box['w']}x{child_face_box['h']} @ "
        f"{child_face_box['x']},{child_face_box['y']})"
    )

    work = canvas.convert("RGB")
    ok_c, _ = _paste_into_annotated_region(
        work, child_region, child_photo, align_to=child_face_box
    )
    if not ok_c:
        raise ValueError("face paste failed (child)")
    soft_paste = work.copy()
    print("     ✓ child paste ready")

    result = soft_paste
    if run_ai_finish and API_KEY:
        from swapping_engine.face_swap import crop_upload_head

        child_head = _matte_face_rgba(
            crop_upload_head(child_photo) or _kitchen_crop_face(child_photo)
        )
        print("  ▶ AI blend (child sticker fix)")
        ai_child = _ai_blend_kitchen_style(
            soft_paste,
            adult_role="child",
            soft_cartoon=soft_cartoon,
            child_head=child_head,
            adult_head=child_head,
            focus="child",
        )
        if ai_child is None:
            print("     ⚠️  AI child pass empty — keeping paste")
            result = soft_paste
        else:
            chosen_c, msg_c = _choose_ai_or_soft(
                soft_paste, ai_child, [child_region], face_boxes=[child_face_box]
            )
            print(f"     {msg_c}")
            if chosen_c is not soft_paste:
                merged = _composite_ai_face(
                    soft_paste,
                    soft_paste,
                    chosen_c,
                    child_region,
                    child_face_box,
                    pad_x_frac=0.55,
                    pad_top_frac=0.70,
                    pad_bot_frac=0.22,
                    core_boost=1.85,
                )
                try:
                    merged = _degreen_face(merged, child_region)
                except Exception as exc:
                    print(f"     ⚠️  degreen skipped: {exc}")
                result, _ = _lock_objects_by_image_diff(
                    soft_paste,
                    merged,
                    [child_region],
                    threshold=_OBJECT_LOCK_THRESHOLD,
                    face_pad=max(_OBJECT_LOCK_FACE_PAD, 0.85),
                )
                result = _body_lock_faces(soft_paste, result, [child_face_box])
            else:
                result = soft_paste
                print(f"     → keep soft-paste child ({msg_c})")
                if _sticker_edge_score(result, [child_region]) > 20.0:
                    print("  ▶ AI blend fallback (child sticker still high)")
                    ai_retry = _ai_blend_kitchen_style(
                        soft_paste,
                        adult_role="child",
                        soft_cartoon=soft_cartoon,
                        child_head=child_head,
                        adult_head=child_head,
                        focus="child",
                    )
                    if ai_retry is not None:
                        chosen_r, msg_r = _choose_ai_or_soft(
                            soft_paste, ai_retry, [child_region],
                            face_boxes=[child_face_box],
                        )
                        print(f"     {msg_r}")
                        if chosen_r is not soft_paste:
                            result = _composite_ai_face(
                                soft_paste, soft_paste, chosen_r,
                                child_region, child_face_box,
                                pad_x_frac=0.55, pad_top_frac=0.70,
                                pad_bot_frac=0.22, core_boost=1.85,
                            )
                            result = _body_lock_faces(
                                soft_paste, result, [child_face_box]
                            )
    elif run_ai_finish and require_ai and not API_KEY:
        raise RuntimeError(f"{label}: OPENROUTER_API_KEY missing for AI finish")

    try:
        result = _recolor_body_to_upload(result, child_region, child_photo)
    except Exception as exc:
        print(f"     ⚠️  child recolor skipped: {exc}")
    return result.convert("RGB")


def personalize_stem(
    stem_dir: str | Path,
    *,
    child_photo: str | Path,
    adult_photo: str | Path | None = None,
    adult_role: str = "mother",
    out_path: str | Path | None = None,
    run_ai_finish: bool = True,
    soft_cartoon: bool = False,
    child_gender: str = "",
    require_ai: bool = True,
    sibling_photo: str | Path | None = None,
) -> Path:
    """
    Personalize a stem via swapping_engine (child+adult or child-only), then save.

    require_ai: if True (default) and run_ai_finish, raise when AI blend fails
    so Streamlit does not ship sticker-quality soft-paste into the PDF.

    adult_photo may be omitted for child-only (or child+sibling) Hamdan stems.
    """
    del child_gender  # reserved for future prompt hints
    stem_dir = Path(stem_dir)
    meta = json.loads((stem_dir / "meta.json").read_text(encoding="utf-8"))
    pers = meta.get("personalisation") or {}
    locked = (pers.get("template_adult_role") or "").strip().lower()
    allowed = [r.lower() for r in (pers.get("allowed_adult_roles") or [])]
    role = (adult_role or "").strip().lower()
    if locked and role and role != locked and role != "child":
        raise ValueError(
            f"{stem_dir}: template body is '{locked}' — refuse adult_role='{adult_role}'. "
            "Generate a separate stem PNG for each role."
        )
    if locked and allowed and role and role not in allowed and role != "child":
        raise ValueError(f"{stem_dir}: adult_role '{adult_role}' not in {allowed}")

    image_file = meta.get("image_file") or "template.png"
    original_template = Image.open(stem_dir / image_file).convert("RGB")

    regions = {r["role"]: r for r in (meta.get("face_regions") or [])}
    child_region = regions.get("child") or regions.get("user")
    if child_region is None:
        raise ValueError(f"{stem_dir}: meta.json needs a face_region for 'child'")

    adult_region_meta = None
    if locked or (role and role not in ("child", "user", "sibling")):
        adult_region_meta = regions.get(role) or regions.get(locked) or regions.get("adult")
        if adult_region_meta is None and adult_photo:
            raise ValueError(
                f"{stem_dir}: meta.json needs face_regions for "
                f"'{role or locked or 'adult'}' (template_adult_role)"
            )
        if adult_region_meta is not None and not adult_photo:
            raise ValueError(
                f"{stem_dir}: adult photo required for role '{locked or role}'"
            )

    if out_path is None:
        out_resolved = stem_dir / f"preview_{role or locked or 'child'}.png"
    else:
        out_resolved = Path(out_path)
    out_resolved.parent.mkdir(parents=True, exist_ok=True)

    if adult_region_meta is not None and adult_photo is not None:
        result = run_child_adult_face_pipeline(
            original_template,
            child_region=child_region,
            adult_region=adult_region_meta,
            child_photo=child_photo,
            adult_photo=adult_photo,
            adult_role=role or locked or "mother",
            soft_cartoon=soft_cartoon,
            run_ai_finish=run_ai_finish,
            require_ai=require_ai,
            expand_adult_hair=True,
            label=stem_dir.name,
        )
    else:
        result = run_child_only_face_pipeline(
            original_template,
            child_region=child_region,
            child_photo=child_photo,
            soft_cartoon=soft_cartoon,
            run_ai_finish=run_ai_finish,
            require_ai=require_ai,
            label=stem_dir.name,
        )

    # Optional sibling face (Hamdan child+sibling scenes)
    sib_region = regions.get("sibling")
    if sib_region is not None and sibling_photo is not None:
        work = result.convert("RGB")
        ok_s, _ = _paste_into_annotated_region(work, sib_region, sibling_photo)
        if ok_s:
            result = work

    result.save(out_resolved, format="PNG")
    print(f"  ✓ Saved {out_resolved}")
    return out_resolved


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
