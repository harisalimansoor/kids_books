"""
e2e_beautify_test.py
────────────────────
Isolated End-to-End test for the Photorealistic Template approach.
1. Loads the new interactive mother-child template.
2. Pastes REAL distinct photos (child.jpg and mother.jpg) onto the respective faces.
3. Pastes the REAL transparent football.png onto the 3 white boxes.
4. Sends the swapped image to OpenRouter with a strict "Blending" prompt
   to ensure the faces and objects look like a natural, cohesive photograph.
"""

import os
import re
import json
import base64
import requests
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
from dotenv import load_dotenv

# ── Load Env & Config ────────────────────────────────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")

TEST_DIR = Path(__file__).parent
TEMPLATE_IMG_PATH = TEST_DIR / "grade_1" / "counting" / "count_05_photo_grandfather_interactive.png"
TEMPLATE_JSON_PATH = TEST_DIR / "grade_1" / "counting" / "count_05_photo_grandfather_interactive.json"

# User's actual uploaded photos
USER_PHOTOS = {
    "child": TEST_DIR / "grade1_child.jpg",
    "grandfather_name": TEST_DIR / "grandfather.jpg"
}
HOBBY_OBJECT_PATH = TEST_DIR / "objects" / "football.png"

SWAPPED_IMG_OUTPUT = TEST_DIR / "01_swapped_intermediate.png"
FINAL_IMG_OUTPUT = TEST_DIR / "02_final_beautified.png"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4-image-2"


# ── Step 1: Face Swapping ─────────────────────────────────────────────────────
def crop_face(photo_path: str) -> Image.Image:
    """Simulate cropping a face from an uploaded photo."""
    img = Image.open(photo_path).convert("RGBA")
    width, height = img.size
    min_dim = min(width, height)
    left = (width - min_dim) / 2
    top = (height - min_dim) / 4 # crop higher for portrait
    right = left + min_dim
    bottom = top + min_dim
    return img.crop((left, top, right, bottom))


def perform_swaps() -> bytes:
    print("1️⃣  Loading template and applying swaps...")
    with open(TEMPLATE_JSON_PATH, "r") as f:
        meta = json.load(f)
    
    template_img = Image.open(TEMPLATE_IMG_PATH).convert("RGBA")

    # --- SWAP FACES ---
    face_regions = meta.get("face_regions", [])
    for region in face_regions:
        role = region["role"]
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        
        photo_path = USER_PHOTOS.get(role)
        if not photo_path or not photo_path.exists():
            print(f"⚠️ Missing photo for {role}")
            continue

        user_face = crop_face(photo_path)
        
        # Resize and create a softer mask for better blending pre-AI
        resized_face = user_face.resize((w, h), Image.Resampling.LANCZOS)
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, w, h), fill=255)
        
        # Feather the edges of the mask so the hard cut-out line is less visible
        mask = mask.filter(ImageFilter.GaussianBlur(3))
        
        template_img.paste(resized_face, (x, y), mask)
        print(f"    ✓ Pasted '{role}' face")

    # --- SWAP OBJECTS ---
    object_groups = meta.get("object_positions", [])
    if object_groups and os.path.exists(HOBBY_OBJECT_PATH):
        hobby_obj = Image.open(HOBBY_OBJECT_PATH).convert("RGBA")
        
        for group in object_groups:
            for pos in group.get("positions", []):
                x, y = pos["x"], pos["y"]
                obj_size = 180 # Size of football
                
                resized_obj = hobby_obj.resize((obj_size, obj_size), Image.Resampling.LANCZOS)
                paste_x = x - (obj_size // 2)
                paste_y = y - (obj_size // 2)
                
                template_img.paste(resized_obj, (paste_x, paste_y), resized_obj)
                print(f"    ✓ Pasted football at ({x}, {y})")

    # Save intermediate for debugging
    template_img.convert("RGB").save(SWAPPED_IMG_OUTPUT)
    print(f"    ✓ Intermediate collage saved to {SWAPPED_IMG_OUTPUT.name}")

    # Convert to base64 for API
    buffered = BytesIO()
    template_img.convert("RGB").save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


# ── Step 2: AI Beautification ─────────────────────────────────────────────────
def extract_image(data: dict) -> str | None:
    msg = data.get("choices", [{}])[0].get("message", {})
    images = msg.get("images", [])
    if images and isinstance(images, list) and images[0].get("image_url", {}).get("url"):
        return images[0]["image_url"]["url"]
    
    content = msg.get("content", "")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return part["image_url"]["url"]
    
    if isinstance(content, str):
        match = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", content)
        if match: return match.group(1)
    
    return None


def beautify_image(base64_image: str):
    print(f"2️⃣  Sending to OpenRouter ({MODEL}) for beautification...")
    
    with open(TEMPLATE_JSON_PATH, "r") as f:
        meta = json.load(f)
    count = meta.get("count", 5)
    
    # We use a much stronger prompt explicitly instructing the AI on how to handle the collage
    prompt = f"""
    You are a master digital retoucher and photographer. I am providing you with a base image that has faces and footballs digitally pasted onto it.
    Your task is to blend everything into a single, cohesive, ultra-realistic photograph.
    
    CRITICAL RULES:
    1. FACE BLENDING (MOST IMPORTANT): The faces in this image have been digitally pasted in. You MUST seamlessly blend these faces into the rest of the photograph. Adjust the lighting, shadows, and skin tones on the pasted faces so they match the ambient light of the environment perfectly. Eliminate any harsh cut-out edges.
    2. FACIAL EXPRESSIONS: Modify the facial expressions. Even if the input faces are neutral or serious, redraw their expressions so that both the child and grandfather are laughing warmly and smiling happily with joyful expressions, while still preserving their recognizable core identities.
    3. FACE PRESERVATION: While blending the lighting and adapting the expressions, you MUST preserve the recognizable core identity, age, gender, and features of the grandfather and child. Do not replace them with completely different people.
    4. EXACT COUNT & OBJECTS: There are exactly {count} footballs pasted on the blanket. Maintain EXACTLY {count} footballs. Blend them naturally into the scene by adding realistic contact shadows underneath them.
    5. STYLE: Ultra-realistic, cinematic natural lighting, highly detailed professional photography.
    
    Output ONLY the beautified image. No text.
    """

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8502"
    }

    payload = {
        "model": MODEL,
        "modalities": ["image", "text"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    
    if response.status_code != 200:
        print(f"❌ API Error {response.status_code}: {response.text[:500]}")
        return

    data = response.json()
    img_ref = extract_image(data)

    if not img_ref:
        print(f"❌ No image returned. AI response: {data.get('choices', [{}])[0].get('message', {}).get('content', '')[:500]}")
        return

    print("3️⃣  Downloading beautified final image...")
    if img_ref.startswith("data:image"):
        b64 = img_ref.split(",", 1)[1]
        img_bytes = base64.b64decode(b64)
    else:
        resp = requests.get(img_ref, timeout=60)
        img_bytes = resp.content

    with open(FINAL_IMG_OUTPUT, "wb") as f:
        f.write(img_bytes)
    
    print(f"🎉 Success! Final image saved to: {FINAL_IMG_OUTPUT.name}")


if __name__ == "__main__":
    b64_swapped = perform_swaps()
    beautify_image(b64_swapped)
