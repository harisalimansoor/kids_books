import cv2
import json
import sys
import os
import numpy as np

# Force the display image to exactly this width — coordinates will be scaled back automatically
DISPLAY_WIDTH = 900

def annotate_image(image_path, json_path):
    img_original = cv2.imread(image_path)
    if img_original is None:
        print(f"❌ Could not load image {image_path}")
        return

    if not os.path.exists(json_path):
        print(f"❌ JSON file not found: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    orig_h, orig_w = img_original.shape[:2]
    
    # Scale image to a fixed display width so coordinates are consistent
    scale = DISPLAY_WIDTH / orig_w
    display_h = int(orig_h * scale)
    img_display = cv2.resize(img_original, (DISPLAY_WIDTH, display_h))
    
    print(f"\n📐 Image actual size: {orig_w}x{orig_h}")
    print(f"📺 Display size:      {DISPLAY_WIDTH}x{display_h}")
    print(f"🔢 Scale factor:      {scale:.4f}  (clicks will be multiplied by {1/scale:.2f} to get real coords)")

    # --- 1. Select Face Regions ---
    print("\n" + "="*50)
    print("🖼️  STEP 1: Select the Faces")
    print("="*50)
    print("1. Click and drag a rectangle over the requested face.")
    print("2. Press ENTER or SPACE to confirm your selection.")
    print("3. Press 'c' if you want to skip that specific face.")

    face_slots = data.get("face_slots", ["child"])
    face_regions = []

    for role in face_slots:
        window_name = f"Select '{role}' face (ENTER=confirm, C=skip)"
        roi = cv2.selectROI(window_name, img_display, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow(window_name)

        if roi != (0, 0, 0, 0):
            # Scale coords back to original image space
            x = int(roi[0] / scale)
            y = int(roi[1] / scale)
            w = int(roi[2] / scale)
            h = int(roi[3] / scale)
            face_regions.append({"role": role, "x": x, "y": y, "w": w, "h": h})
            print(f"✅ '{role}': display=({roi[0]},{roi[1]},{roi[2]},{roi[3]})  →  real=({x},{y},{w},{h})")
        else:
            print(f"⏭️  '{role}' skipped.")

    data["face_regions"] = face_regions

    # --- 2. Select Objects ---
    print("\n" + "="*50)
    print(f"📍 STEP 2: Select the {data.get('count', '?')} objects")
    print("="*50)
    print("1. Click exactly in the center of each object.")
    print("2. A red dot will appear where you click.")
    print("3. Press 'q' or ESC when finished.")

    positions = []
    display_img = img_display.copy()

    def mouse_callback(event, mx, my, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            # Scale back to original coords
            real_x = int(mx / scale)
            real_y = int(my / scale)
            positions.append({"x": real_x, "y": real_y})
            cv2.circle(display_img, (mx, my), 8, (0, 0, 255), -1)
            cv2.imshow("Select Objects (click each, Q to finish)", display_img)
            print(f"   Point: display=({mx},{my})  →  real=({real_x},{real_y})")

    cv2.imshow("Select Objects (click each, Q to finish)", display_img)
    cv2.setMouseCallback("Select Objects (click each, Q to finish)", mouse_callback)

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

    cv2.destroyAllWindows()

    if positions:
        # Check if new schema (objects array)
        if "objects" in data and isinstance(data["objects"], list) and len(data["objects"]) > 0:
            data["objects"][0]["positions"] = positions
            data["objects"][0]["count"] = len(positions)
        else:
            # Fallback to old schema
            data["object_positions"] = [{
                "label": data.get("object", "object"),
                "count": len(positions),
                "positions": positions
            }]
        print(f"✅ {len(positions)} objects selected.")
    else:
        print("⏭️  Object selection skipped.")

    # --- 3. Save JSON ---
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print("\n💾 JSON saved successfully!\n")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python annotate_template.py <path_to_png>")
        sys.exit(1)

    img_path = sys.argv[1]
    json_path = os.path.splitext(img_path)[0] + ".json"
    annotate_image(img_path, json_path)
