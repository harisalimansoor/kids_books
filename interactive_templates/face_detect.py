"""
face_detect.py
─────────────────────────────────────────────────────────────────────────────
Face detection + landmark-aligned face swapping for interactive templates.

The role templates are AI-generated, so every template frames its two
characters slightly differently. Hard-coded face boxes therefore land on the
right face in some templates and on hair/shoulders in others, which is why
some scenes looked swapped and others did not.

This module detects the real faces (YuNet, 227 KB ONNX) and stores the boxes
plus 5-point landmarks in the template JSON, so pasting is always aligned to
the actual face.

USAGE:
    python -m interactive_templates.face_detect            # annotate all scenes
    python -m interactive_templates.face_detect --force    # re-annotate
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

PACKAGE_DIR = Path(__file__).parent
SCENES_DIR = PACKAGE_DIR / "scenes"
MODELS_DIR = PACKAGE_DIR.parent / "models"
YUNET_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)

# Landmark order emitted by YuNet.
LANDMARK_KEYS = ("right_eye", "left_eye", "nose", "mouth_right", "mouth_left")

_detector = None


def _ensure_model() -> Path | None:
    if YUNET_PATH.exists() and YUNET_PATH.stat().st_size > 100_000:
        return YUNET_PATH
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(YUNET_URL, YUNET_PATH)
    except Exception as exc:
        print(f"  ⚠️  Could not download face detector: {exc}")
        return None
    return YUNET_PATH if YUNET_PATH.exists() else None


def _get_detector():
    """Lazy-load YuNet. Returns None when OpenCV/model are unavailable."""
    global _detector
    if _detector is not None:
        return _detector
    try:
        import cv2
    except Exception:
        return None
    if not hasattr(cv2, "FaceDetectorYN_create"):
        return None
    model = _ensure_model()
    if not model:
        return None
    try:
        _detector = cv2.FaceDetectorYN_create(str(model), "", (320, 320), 0.6, 0.3, 500)
    except Exception as exc:
        print(f"  ⚠️  Face detector init failed: {exc}")
        return None
    return _detector


def _to_bgr(source) -> "np.ndarray | None":
    try:
        import cv2
    except Exception:
        return None
    if isinstance(source, (str, Path)):
        img = Image.open(source)
    elif isinstance(source, Image.Image):
        img = source
    else:
        return None
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def detect_faces(source) -> list[dict]:
    """Detect faces, returning boxes + 5-point landmarks sorted largest first."""
    det = _get_detector()
    bgr = _to_bgr(source)
    if det is None or bgr is None:
        return []
    h, w = bgr.shape[:2]
    det.setInputSize((w, h))
    try:
        _, raw = det.detect(bgr)
    except Exception:
        return []
    if raw is None:
        return []
    faces = []
    for row in raw:
        vals = [float(v) for v in row]
        x, y, fw, fh = (int(round(v)) for v in vals[:4])
        landmarks = {
            key: [int(round(vals[4 + 2 * i])), int(round(vals[5 + 2 * i]))]
            for i, key in enumerate(LANDMARK_KEYS)
        }
        faces.append({
            "x": max(0, x),
            "y": max(0, y),
            "w": fw,
            "h": fh,
            "confidence": round(vals[-1], 3),
            "landmarks": landmarks,
        })
    faces.sort(key=lambda f: f["w"] * f["h"], reverse=True)
    return faces


def interocular(face: dict) -> float:
    """Eye-to-eye distance — a steadier scale measure than the raw box."""
    marks = face.get("landmarks") or {}
    try:
        (rx, ry), (lx, ly) = marks["right_eye"], marks["left_eye"]
    except (KeyError, TypeError, ValueError):
        return float(face.get("w", 0))
    return float(np.hypot(lx - rx, ly - ry))


def assign_roles(faces: list[dict], slots: list[str]) -> dict[str, dict]:
    """
    Map detected faces onto template face slots.

    Templates pair one adult with one child. Head size alone is a thin signal —
    in the mother and grandmother scenes the two heads are within ~20% of each
    other, close enough for a re-render to flip the assignment and land the
    adult's photo on the child. So size is combined with head height: the adult's
    head always sits higher in the frame, by a wide margin in every template.
    """
    adult_slots = [s for s in slots if s != "child"]
    if not faces:
        return {}
    if not ("child" in slots and adult_slots and len(faces) >= 2):
        return {slot: face for slot, face in zip(slots, faces)}

    first, second = faces[0], faces[1]
    eyes = (interocular(first), interocular(second))
    tops = (float(first["y"]), float(second["y"]))
    eye_total = sum(eyes) or 1.0
    top_total = sum(tops) or 1.0

    # Head height separates the two by 110+ px on every template while eye
    # spacing can be as close as 5%, so both count and neither can decide alone.
    scores = (
        0.5 * (eyes[0] / eye_total) + 0.5 * (tops[1] / top_total),
        0.5 * (eyes[1] / eye_total) + 0.5 * (tops[0] / top_total),
    )
    adult, child = (first, second) if scores[0] >= scores[1] else (second, first)

    if (eyes[0] >= eyes[1]) != (tops[0] <= tops[1]):
        print(
            "  ⚠️  Adult/child assignment is ambiguous on this template "
            f"(eye spacing {eyes[0]:.0f}px vs {eyes[1]:.0f}px, "
            f"head tops y={tops[0]:.0f} vs y={tops[1]:.0f}) — verify the render"
        )
    return {adult_slots[0]: adult, "child": child}


def pick_primary_face(faces: list[dict], image_size: tuple[int, int]) -> dict | None:
    """
    Choose the subject in an uploaded photo.

    Family snapshots often catch a second person in frame, and taking the
    largest face silently grabs the wrong one — typically a parent standing
    behind the child. Prominence is scored as size weighted by how centred the
    face is, and multi-face photos are flagged.
    """
    if not faces:
        return None
    if len(faces) == 1:
        return faces[0]

    width, height = image_size
    cx, cy = width / 2.0, height / 2.0
    diagonal = float(np.hypot(width, height)) or 1.0

    def score(face: dict) -> float:
        fx = face["x"] + face["w"] / 2.0
        fy = face["y"] + face["h"] / 2.0
        offset = float(np.hypot(fx - cx, fy - cy)) / diagonal
        area = (face["w"] * face["h"]) / float(width * height or 1)
        return area * (1.0 - min(offset, 0.9))

    best = max(faces, key=score)
    print(
        f"  ⚠️  Photo contains {len(faces)} faces — using the most prominent one. "
        "Upload a solo close-up for a reliable swap."
    )
    return best


def face_regions_for_template(png_path: Path, slots: list[str]) -> list[dict]:
    """Detected face regions for a template, in the template's slot order."""
    faces = detect_faces(png_path)
    if len(faces) > 2:
        faces = faces[:2]
    mapping = assign_roles(faces, slots)
    regions = []
    for slot in slots:
        face = mapping.get(slot)
        if not face:
            continue
        regions.append({
            "role": slot,
            "x": face["x"],
            "y": face["y"],
            "w": face["w"],
            "h": face["h"],
            "landmarks": face["landmarks"],
            "confidence": face["confidence"],
        })
    return regions


def annotate_template(png_path: Path, *, force: bool = False) -> bool:
    json_path = png_path.with_suffix(".json")
    if not json_path.exists():
        print(f"  ❌ No JSON beside {png_path.name}")
        return False

    with open(json_path, encoding="utf-8") as f:
        meta = json.load(f)

    if meta.get("face_detection") == "yunet" and not force:
        print(f"  ⏭️  {png_path.name} already detector-annotated")
        return True

    slots = meta.get("face_slots") or []
    if not slots:
        adult = next((r for r in meta.get("family", []) if r != "child"), None)
        slots = ["child"] + ([f"{adult}_name"] if adult else [])

    regions = face_regions_for_template(png_path, slots)
    if len(regions) < len(slots):
        print(
            f"  ⚠️  {png_path.name}: detected {len(regions)}/{len(slots)} faces — "
            "keeping existing regions"
        )
        return False

    meta["face_regions"] = regions
    meta["face_detection"] = "yunet"
    meta["annotation_complete"] = True
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    summary = ", ".join(f"{r['role']}@({r['x']},{r['y']},{r['w']}x{r['h']})" for r in regions)
    print(f"  ✓ {png_path.name}: {summary}")
    return True


def annotate_all(force: bool = False) -> None:
    pngs = sorted(SCENES_DIR.glob("*/*/*.png"))
    print(f"🔍 Detecting faces in {len(pngs)} interactive templates")
    ok = sum(1 for png in pngs if annotate_template(png, force=force))
    print(f"\n✅ Done: {ok}/{len(pngs)} templates annotated with real face boxes.")


if __name__ == "__main__":
    annotate_all(force="--force" in sys.argv)
