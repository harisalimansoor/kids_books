"""
face_swap.py
─────────────────────────────────────────────────────────────────────────────
Helpers for the simple annotate-and-paste face pipeline.

The compositor pastes a cropped upload face into each annotated template
region; an AI blend pass then removes seams and matches lighting. This module
only supplies crop / scale helpers — no Poisson or landmark warps.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from interactive_templates.face_detect import detect_faces, pick_primary_face

# Keep paste boxes at full annotated size (1.0). Previously mother was
# shrunk to 0.86 which made her face look tiny/weird.
FACE_REGION_SCALE = float(os.getenv("FACE_REGION_SCALE", "1.0"))
MOTHER_FACE_SCALE = float(os.getenv("MOTHER_FACE_SCALE", "1.0"))


def scale_region_for_role(region: dict) -> dict:
    """
    Optionally scale the paste box around its centre.

    Defaults leave the annotated box unchanged so uploaded faces keep a
    natural head size on the template body.
    """
    role = str(region.get("role") or "")
    scale = FACE_REGION_SCALE
    if role == "mother_name":
        scale *= MOTHER_FACE_SCALE
    if abs(scale - 1.0) < 0.001:
        return region

    scaled = dict(region)
    x, y, w, h = region["x"], region["y"], region["w"], region["h"]
    cx, cy = x + w / 2.0, y + h / 2.0
    new_w, new_h = w * scale, h * scale
    scaled.update({
        "x": int(round(cx - new_w / 2.0)),
        "y": int(round(cy - new_h / 2.0)),
        "w": max(8, int(round(new_w))),
        "h": max(8, int(round(new_h))),
    })
    return scaled


def crop_upload_face(photo_path: str | Path) -> Image.Image | None:
    """
    Crop the primary face from an uploaded photo.

    Uses YuNet when available so the paste contains the face, not the whole
    portrait background. Falls back to a centred square crop.

    Padding includes forehead/hair so the paste is not a floating face sticker.
    """
    photo_path = Path(photo_path)
    if not photo_path.exists():
        return None
    photo = Image.open(photo_path).convert("RGBA")
    faces = detect_faces(photo)
    primary = pick_primary_face(faces, photo.size) if faces else None
    if primary:
        x, y, w, h = primary["x"], primary["y"], primary["w"], primary["h"]
        pad = int(0.22 * max(w, h))
        pad_top = int(0.42 * h)  # hair above the forehead
        pad_bottom = int(0.28 * h)  # jaw / upper neck
        left = max(0, x - pad)
        top = max(0, y - pad_top)
        right = min(photo.width, x + w + pad)
        bottom = min(photo.height, y + h + pad_bottom)
        return photo.crop((left, top, right, bottom))

    # Fallback: centred square biased toward the upper half of the photo.
    w, h = photo.size
    side = min(w, h)
    left = (w - side) // 2
    top = max(0, int((h - side) * 0.10))
    return photo.crop((left, top, left + side, top + side))


def crop_upload_head(photo_path: str | Path) -> Image.Image | None:
    """
    Crop face + full hairstyle + neck from an uploaded photo.

    Wider/taller than crop_upload_face so identity refs keep hairstyle,
    hair colour, and skin tone from the upload (not just eyes/nose/mouth).
    """
    photo_path = Path(photo_path)
    if not photo_path.exists():
        return None
    photo = Image.open(photo_path).convert("RGBA")
    faces = detect_faces(photo)
    primary = pick_primary_face(faces, photo.size) if faces else None
    if primary:
        x, y, w, h = primary["x"], primary["y"], primary["w"], primary["h"]
        pad_x = int(0.72 * max(w, h))
        pad_top = int(1.35 * h)  # full hairstyle / bun / ponytail height
        pad_bottom = int(0.85 * h)  # neck / collarbone for skin tone
        left = max(0, x - pad_x)
        top = max(0, y - pad_top)
        right = min(photo.width, x + w + pad_x)
        bottom = min(photo.height, y + h + pad_bottom)
        return photo.crop((left, top, right, bottom))

    w, h = photo.size
    side = min(w, h)
    left = (w - side) // 2
    top = max(0, int((h - side) * 0.05))
    return photo.crop((left, top, left + side, min(h, top + side)))


def crop_upload_portrait(photo_path: str | Path) -> Image.Image | None:
    """Upper-body crop (head, hair, shoulders) for hairstyle + skin reference."""
    photo_path = Path(photo_path)
    if not photo_path.exists():
        return None
    photo = Image.open(photo_path).convert("RGBA")
    faces = detect_faces(photo)
    primary = pick_primary_face(faces, photo.size) if faces else None
    if primary:
        x, y, w, h = primary["x"], primary["y"], primary["w"], primary["h"]
        pad_x = int(1.05 * max(w, h))
        pad_top = int(1.50 * h)
        pad_bottom = int(1.80 * h)
        left = max(0, x - pad_x)
        top = max(0, y - pad_top)
        right = min(photo.width, x + w + pad_x)
        bottom = min(photo.height, y + h + pad_bottom)
        return photo.crop((left, top, right, bottom))
    return crop_upload_head(photo_path)


def resize_face_keep_aspect(
    face: Image.Image, box_w: int, box_h: int
) -> Image.Image:
    """
    Resize a face crop to fill the paste box WITHOUT stretching.

    Uses cover+centre-crop so eye/nose/mouth proportions match the upload.
    Never squashes a wide face into a tall box (or vice versa).
    """
    box_w = max(8, int(box_w))
    box_h = max(8, int(box_h))
    fw, fh = face.size
    if fw < 1 or fh < 1:
        return face.resize((box_w, box_h), Image.Resampling.LANCZOS)

    scale = max(box_w / fw, box_h / fh)
    nw = max(box_w, int(round(fw * scale)))
    nh = max(box_h, int(round(fh * scale)))
    resized = face.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - box_w) // 2)
    top = max(0, (nh - box_h) // 2)
    return resized.crop((left, top, left + box_w, top + box_h))
