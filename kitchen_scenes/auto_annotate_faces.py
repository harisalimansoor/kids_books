"""
auto_annotate_faces.py
─────────────────────────────────────────────────────────────────────────────
Write face_regions into kitchen template JSON files.

Uses OpenCV Haar cascades when available; otherwise falls back to the
typical two-person kitchen composition layout used by these templates
(child lower-left / adult upper-right).

USAGE:
    python -m kitchen_scenes.auto_annotate_faces
    python -m kitchen_scenes.auto_annotate_faces path/to/template.png
    python -m kitchen_scenes.auto_annotate_faces --force
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

TEMPLATES_DIR = Path(__file__).parent / "direct_food_templates"


def _haar_detect_faces(png_path: Path) -> list[tuple[int, int, int, int]]:
    try:
        import cv2
    except Exception:
        return []
    if not hasattr(cv2, "CascadeClassifier"):
        return []
    img = cv2.imread(str(png_path))
    if img is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(str(cascade_path))
    faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(60, 60))
    return sorted([(int(x), int(y), int(w), int(h)) for x, y, w, h in faces], key=lambda b: (b[0], b[1]))


def _layout_fallback_faces(img_w: int, img_h: int, slots: list[str]) -> list[dict]:
    """Approximate face boxes for the standard two-person kitchen framing."""
    child_box = {
        "x": int(0.16 * img_w),
        "y": int(0.27 * img_h),
        "w": int(0.24 * img_w),
        "h": int(0.27 * img_h),
    }
    adult_box = {
        "x": int(0.52 * img_w),
        "y": int(0.10 * img_h),
        "w": int(0.25 * img_w),
        "h": int(0.30 * img_h),
    }
    regions = []
    for slot in slots:
        box = dict(child_box if slot == "child" else adult_box)
        box["role"] = slot
        regions.append(box)
    return regions


def auto_annotate_template(png_path: Path, force: bool = False) -> bool:
    json_path = png_path.with_suffix(".json")
    if not png_path.exists() or not json_path.exists():
        print(f"  ❌ Missing files for {png_path.name}")
        return False

    with open(json_path, encoding="utf-8") as f:
        meta = json.load(f)

    slots = meta.get("face_slots") or []
    existing = meta.get("face_regions") or []
    if existing and meta.get("annotation_complete") and not force:
        print(f"  ⏭️  {png_path.name} already annotated ({len(existing)} regions)")
        return True

    with Image.open(png_path) as im:
        img_w, img_h = im.size

    faces = _haar_detect_faces(png_path)
    regions: list[dict] = []

    if len(faces) >= len(slots) and slots:
        ranked = sorted(faces, key=lambda b: b[2] * b[3], reverse=True)
        role_boxes: dict[str, tuple[int, int, int, int]] = {}
        adult_slots = [s for s in slots if s != "child"]
        if adult_slots and "child" in slots and len(ranked) >= 2:
            role_boxes[adult_slots[0]] = ranked[0]
            role_boxes["child"] = ranked[1]
        else:
            for slot, box in zip(slots, ranked):
                role_boxes[slot] = box
        for slot in slots:
            if slot not in role_boxes:
                continue
            x, y, w, h = role_boxes[slot]
            pad = int(0.08 * max(w, h))
            x = max(0, x - pad)
            y = max(0, y - pad)
            w = min(img_w - x, w + 2 * pad)
            h = min(img_h - y, h + 2 * pad)
            regions.append({"role": slot, "x": x, "y": y, "w": w, "h": h})
        method = "haar"
    else:
        regions = _layout_fallback_faces(img_w, img_h, slots)
        method = "layout-fallback"

    if not regions:
        print(f"  ❌ {png_path.name}: could not create face regions")
        return False

    meta["face_regions"] = regions
    meta["annotation_complete"] = len(regions) == len(slots)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"  ✓ Annotated {png_path.name} via {method}: {[r['role'] for r in regions]}")
    return True


def annotate_all(force: bool = False) -> None:
    pngs = sorted(TEMPLATES_DIR.glob("*.png"))
    print(f"🔍 Auto-annotating {len(pngs)} templates in {TEMPLATES_DIR}")
    ok = 0
    for png in pngs:
        if auto_annotate_template(png, force=force):
            ok += 1
    print(f"\n✅ Done: {ok}/{len(pngs)} templates annotated.")


if __name__ == "__main__":
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--force"]
    if args:
        auto_annotate_template(Path(args[0]), force=force)
    else:
        annotate_all(force=force)
