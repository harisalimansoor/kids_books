"""
template_engine.py
──────────────────
Core engine for the template-first approach.
1. Selects the correct template image based on question type and count.
2. Performs face-swapping for MULTIPLE family members.
3. Performs object swapping for hobbies.
"""

import os
import json
from pathlib import Path
from PIL import Image, ImageDraw

# Root directory of our templates
TEMPLATE_DIR = Path(__file__).parent / "template_test" / "grade_1"


def get_template(question_type: str, count: int, prefix: str = "") -> dict | None:
    """Finds the appropriate template JSON for a given type and count."""
    type_dir = TEMPLATE_DIR / question_type
    if not type_dir.exists():
        return None

    for json_file in type_dir.glob("*.json"):
        with open(json_file, 'r') as f:
            data = json.load(f)
            if data.get("count") == count and (not prefix or prefix in data.get("template_id", "")):
                return data
    return None


def extract_face_from_photo(photo_path: str) -> Image.Image | None:
    """Simulates cropping a face from a photo."""
    if not photo_path or not os.path.exists(photo_path):
        return None
        
    img = Image.open(photo_path).convert("RGBA")
    width, height = img.size
    min_dim = min(width, height)
    left = (width - min_dim) / 2
    top = (height - min_dim) / 4 # crop higher up for portrait
    right = left + min_dim
    bottom = top + min_dim
    return img.crop((left, top, right, bottom))


def apply_swaps(template_data: dict, user_photos: dict, hobby_object_path: str) -> Image.Image | None:
    """
    Pastes the user's family faces AND the hobby objects onto the template.
    """
    img_path = TEMPLATE_DIR / template_data["question_type"] / template_data["image_file"]
    
    if not img_path.exists():
        print(f"❌ Template image not found: {img_path}")
        return None
        
    template_img = Image.open(img_path).convert("RGBA")
    
    # ── 1. FACE SWAPPING ──
    face_regions = template_data.get("face_regions", [])
    for region in face_regions:
        role = region.get("role")
        x, y = region["x"], region["y"]
        w, h = region["w"], region["h"]
        
        photo_path = user_photos.get(role)
        user_face = extract_face_from_photo(photo_path)
        
        if user_face:
            resized_face = user_face.resize((w, h), Image.Resampling.LANCZOS)
            mask = Image.new("L", (w, h), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, w, h), fill=255)
            
            template_img.paste(resized_face, (x, y), mask)
            print(f"✅ Swapped face for role '{role}'")
        else:
            print(f"⚠️ Missing photo for role '{role}'")

    # ── 2. OBJECT SWAPPING ──
    object_data = template_data.get("object_positions", [])
    if object_data and os.path.exists(hobby_object_path):
        hobby_obj = Image.open(hobby_object_path).convert("RGBA")
        
        for group in object_data:
            for pos in group.get("positions", []):
                x, y = pos["x"], pos["y"]
                
                # We want the objects to be big enough to cover the white boxes (e.g. 150x150)
                obj_size = 150 
                resized_obj = hobby_obj.resize((obj_size, obj_size), Image.Resampling.LANCZOS)
                
                # Center paste on the clicked point
                paste_x = x - (obj_size // 2)
                paste_y = y - (obj_size // 2)
                
                # Paste using the image's own alpha transparency
                template_img.paste(resized_obj, (paste_x, paste_y), resized_obj)
                print(f"🏈 Pasted hobby object at x={x}, y={y}")

    return template_img


# ── Quick Test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test grabbing the mother template (Count: 3)
    test_count = 3
    question_type = "counting"
    
    print(f"\n🚀 Testing Template Engine for Photorealistic Mother Scene...")
    
    template_data = get_template(question_type, test_count, "mother")
    
    if template_data:
        # Define photos for each role
        user_photos = {
            "child": "template_test/sample_kid.jpg",
            "mother_name": "template_test/sample_kid.jpg" # Reusing for test
        }
        
        # Define the hobby object to swap in (e.g., a football)
        hobby_obj = "template_test/objects/football.png"
        
        print("📸 Applying face swaps and object swaps...")
        final_img = apply_swaps(template_data, user_photos, hobby_obj)
        
        if final_img:
            output_path = f"template_test/swapped_photorealistic_count_{test_count}.png"
            final_img.convert("RGB").save(output_path)
            print(f"🎉 Success! Raw Swapped image saved to: {output_path}\n")
    else:
        print("❌ Could not load template. Make sure it generated successfully.")
