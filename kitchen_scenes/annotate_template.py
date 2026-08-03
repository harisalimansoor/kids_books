"""
annotate_template.py
──────────────────────────────────────────────────────────────────────────────
Face Annotation Tool for Kitchen Scenes templates.

Focuses EXCLUSIVELY on annotating face_regions bounding boxes for face swapping.

USAGE:
    python kitchen_scenes/annotate_template.py <path_to_png>

WORKFLOW:
    1. Draws the image on screen at a fixed display size.
    2. Asks you to drag a bounding box over each character's face slot (e.g. child, mother_name).
    3. Press ENTER / SPACE to confirm each box (or 'C' to skip).
    4. Automatically saves real pixel coordinates back to the matching .json file.
"""

import cv2
import json
import sys
import os
from pathlib import Path

# ── Display Configuration ────────────────────────────────────────────────────
DISPLAY_WIDTH  = 900          # fixed UI width in pixels
FACE_BOX_COLOR = (255, 165, 0)# orange – confirmed face rectangles


def _scale_roi_to_real(roi, scale: float) -> dict:
    return {
        "x": int(roi[0] / scale),
        "y": int(roi[1] / scale),
        "w": int(roi[2] / scale),
        "h": int(roi[3] / scale),
    }


def annotate_faces(image_path: str, json_path: str):
    img_original = cv2.imread(image_path)
    if img_original is None:
        print(f"❌ Could not load image: {image_path}")
        return

    if not os.path.exists(json_path):
        print(f"❌ JSON file not found: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    orig_h, orig_w = img_original.shape[:2]
    scale      = DISPLAY_WIDTH / orig_w
    display_h  = int(orig_h * scale)
    img_disp   = cv2.resize(img_original, (DISPLAY_WIDTH, display_h))

    print("\n" + "═" * 60)
    print("  🖼️   Kitchen Scenes — Face Region Annotation Tool")
    print("═" * 60)
    print(f"  Image   : {Path(image_path).name}")
    print(f"  JSON    : {Path(json_path).name}")
    print(f"  Size    : {orig_w}x{orig_h}  →  display {DISPLAY_WIDTH}x{display_h}")
    print(f"  Scale   : {scale:.4f}  (clicks × {1/scale:.2f} = real coords)")
    print("═" * 60)

    print("\n📦 Select FACE BOXES")
    print("   Drag a rectangle over each character face → ENTER/SPACE to confirm, C to skip.\n")

    face_slots  = data.get("face_slots", [])
    face_regions = []
    overlay = img_disp.copy()

    for role in face_slots:
        wname = f"Face: '{role}'  (ENTER=confirm, C=skip)"
        roi   = cv2.selectROI(wname, overlay, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow(wname)

        if roi != (0, 0, 0, 0):
            real = _scale_roi_to_real(roi, scale)
            face_regions.append({"role": role, **real})
            # Draw confirmed box on overlay so it stays visible for subsequent faces
            cv2.rectangle(overlay,
                          (roi[0], roi[1]),
                          (roi[0] + roi[2], roi[1] + roi[3]),
                          FACE_BOX_COLOR, 2)
            cv2.putText(overlay, role, (roi[0] + 4, roi[1] - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, FACE_BOX_COLOR, 1)
            print(f"  ✅ '{role}'  display=({roi[0]},{roi[1]},{roi[2]},{roi[3]})  →  real=({real['x']},{real['y']},{real['w']},{real['h']})")
        else:
            print(f"  ⏭️ '{role}' skipped.")

    # Save to JSON
    data["face_regions"] = face_regions
    data["annotation_complete"] = True

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("\n" + "═" * 60)
    print("  💾  Face regions saved successfully!")
    print(f"  📁  {json_path}")
    print("═" * 60)
    print(f"  Annotated {len(face_regions)} faces for roles: {[r['role'] for r in face_regions]}\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:   python kitchen_scenes/annotate_template.py <path_to_png>")
        print("Example: python kitchen_scenes/annotate_template.py kitchen_scenes/direct_food_templates/kitchen_baking_cookies_mother_child.png")
        sys.exit(1)

    img_path  = sys.argv[1]
    json_path = os.path.splitext(img_path)[0] + ".json"
    annotate_faces(img_path, json_path)
