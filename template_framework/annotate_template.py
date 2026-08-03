"""
annotate_template.py
──────────────────────────────────────────────────────────────────────────────
Universal annotation tool for the Template Generation Framework.

Supports BOTH the old template schema AND the new rich metadata schema.

USAGE:
    python template_framework/annotate_template.py <path_to_png>

WORKFLOW:
    1. Draws the image on screen at a fixed display size.
    2. Asks you to drag a bounding box over each face (one per family member).
    3. Asks you to click the center of each object (white placeholder box).
    4. Saves the real pixel coordinates back to the matching .json file.

CONTROLS:
    STEP 1 (Face Boxes):  Drag rectangle → ENTER to confirm, C to skip
    STEP 2 (Object Dots): Left-click each box center, Q or ESC to finish
    STEP 3 (Hand Regions, optional): Left-click to mark holding hands if visible, Q to skip
"""

import cv2
import json
import sys
import os
import numpy as np
from pathlib import Path

# ── Display Configuration ────────────────────────────────────────────────────
DISPLAY_WIDTH  = 900          # fixed UI width in pixels
DOT_COLOR      = (0, 0, 255)  # red   – object dots
HAND_COLOR     = (0, 200, 0)  # green – hand region dots
FACE_BOX_COLOR = (255, 165, 0)# orange – confirmed face rectangles
TEXT_COLOR     = (255, 255, 0) # yellow


def _scale_roi_to_real(roi, scale: float) -> dict:
    return {
        "x": int(roi[0] / scale),
        "y": int(roi[1] / scale),
        "w": int(roi[2] / scale),
        "h": int(roi[3] / scale),
    }


def annotate_image(image_path: str, json_path: str):
    img_original = cv2.imread(image_path)
    if img_original is None:
        print(f"❌  Could not load image: {image_path}")
        return

    if not os.path.exists(json_path):
        print(f"❌  JSON file not found: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    orig_h, orig_w = img_original.shape[:2]
    scale      = DISPLAY_WIDTH / orig_w
    display_h  = int(orig_h * scale)
    img_disp   = cv2.resize(img_original, (DISPLAY_WIDTH, display_h))

    print("\n" + "═" * 60)
    print("  🖼️   Template Annotation Tool")
    print("═" * 60)
    print(f"  Image   : {Path(image_path).name}")
    print(f"  JSON    : {Path(json_path).name}")
    print(f"  Size    : {orig_w}x{orig_h}  →  display {DISPLAY_WIDTH}x{display_h}")
    print(f"  Scale   : {scale:.4f}  (clicks × {1/scale:.2f} = real coords)")
    print("═" * 60)

    # ── STEP 1: Face Regions ─────────────────────────────────────────────────
    print("\n📦  STEP 1 — Select FACE BOXES")
    print("   Drag a rectangle over each face → ENTER/SPACE to confirm, C to skip.\n")

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
            print(f"  ✅  '{role}'  display=({roi[0]},{roi[1]},{roi[2]},{roi[3]})  →  real=({real['x']},{real['y']},{real['w']},{real['h']})")
        else:
            print(f"  ⏭️   '{role}' skipped.")

    data["face_regions"] = face_regions

    # ── STEP 2: Object Positions ─────────────────────────────────────────────
    # Determine expected count from schema
    expected_count = "?"
    if data.get("objects"):
        expected_count = data["objects"][0].get("count", "?")
    elif data.get("placeholder_count"):
        expected_count = data["placeholder_count"]

    print(f"\n📍  STEP 2 — Click OBJECT CENTERS  (expected: {expected_count})")
    print("   Click the center of each white placeholder box.")
    print("   Press Q or ESC when done.\n")

    obj_positions = []
    obj_overlay   = overlay.copy()

    def on_object_click(event, mx, my, flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            rx, ry = int(mx / scale), int(my / scale)
            obj_positions.append({"x": rx, "y": ry})
            cv2.circle(obj_overlay, (mx, my), 10, DOT_COLOR, -1)
            cv2.putText(obj_overlay, str(len(obj_positions)),
                        (mx + 12, my - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEXT_COLOR, 2)
            cv2.imshow(OBJ_WINDOW, obj_overlay)
            print(f"  🔴  #{len(obj_positions)}  display=({mx},{my})  →  real=({rx},{ry})")

    OBJ_WINDOW = "Objects — click centers, Q to finish"
    cv2.imshow(OBJ_WINDOW, obj_overlay)
    cv2.setMouseCallback(OBJ_WINDOW, on_object_click)

    while True:
        key = cv2.waitKey(10) & 0xFF
        if key in (ord("q"), 27):  # Q or ESC
            break

    cv2.destroyAllWindows()

    if obj_positions:
        # Save to correct schema
        if "objects" in data and isinstance(data["objects"], list) and len(data["objects"]) > 0:
            data["objects"][0]["positions"] = obj_positions
            data["objects"][0]["count"]     = len(obj_positions)
        else:
            # Fallback to old schema
            data.setdefault("object_positions", [])
            data["object_positions"] = [{
                "label":     data.get("object", "placeholder_box"),
                "count":     len(obj_positions),
                "positions": obj_positions,
            }]
        print(f"  ✅  {len(obj_positions)} objects annotated.")
    else:
        print("  ⏭️   Object selection skipped.")

    # ── STEP 3: Hand Regions (Optional) ──────────────────────────────────────
    print(f"\n🖐️   STEP 3 — Hand Regions  (optional — for natural object placement)")
    print("   If characters' hands are visible, click the center of each hand.")
    print("   Press Q or ESC to skip this step.\n")

    hand_positions = []
    hand_overlay   = obj_overlay.copy()

    def on_hand_click(event, mx, my, flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            rx, ry = int(mx / scale), int(my / scale)
            hand_positions.append({"x": rx, "y": ry})
            cv2.circle(hand_overlay, (mx, my), 10, HAND_COLOR, -1)
            cv2.putText(hand_overlay, f"H{len(hand_positions)}",
                        (mx + 12, my - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, HAND_COLOR, 2)
            cv2.imshow(HAND_WINDOW, hand_overlay)
            print(f"  🟢  Hand #{len(hand_positions)}  display=({mx},{my})  →  real=({rx},{ry})")

    HAND_WINDOW = "Hands — click each visible hand center, Q to skip"
    cv2.imshow(HAND_WINDOW, hand_overlay)
    cv2.setMouseCallback(HAND_WINDOW, on_hand_click)

    while True:
        key = cv2.waitKey(10) & 0xFF
        if key in (ord("q"), 27):
            break

    cv2.destroyAllWindows()

    if hand_positions:
        data["hand_regions"] = hand_positions
        print(f"  ✅  {len(hand_positions)} hand regions annotated.")
    else:
        print("  ⏭️   Hand annotation skipped.")

    # ── SAVE ─────────────────────────────────────────────────────────────────
    data["annotation_complete"] = True
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("\n" + "═" * 60)
    print("  💾  JSON saved successfully!")
    print(f"  📁  {json_path}")
    print("═" * 60 + "\n")

    # Summary
    print("  ANNOTATION SUMMARY:")
    print(f"    Faces annotated  : {len(face_regions)}")
    print(f"    Objects annotated: {len(obj_positions)}")
    print(f"    Hands annotated  : {len(hand_positions)}")
    if len(obj_positions) != expected_count and expected_count != "?":
        print(f"\n  ⚠️  WARNING: Expected {expected_count} objects but got {len(obj_positions)}.")
        print(f"      Re-run if needed: python template_framework/annotate_template.py {image_path}")
    print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:  python template_framework/annotate_template.py <path_to_png>")
        print("Example: python template_framework/annotate_template.py template_framework/kitchen_templates/kitchen/kitchen_mother_child_baking_cupcakes_table_row_chest_up_4_frosted_cupcake.png")
        sys.exit(1)

    img_path  = sys.argv[1]
    json_path = os.path.splitext(img_path)[0] + ".json"
    annotate_image(img_path, json_path)
