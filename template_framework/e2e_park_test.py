"""
e2e_classroom_test.py
End-to-End test specifically for the new generated classroom template.
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

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")

TEST_DIR         = Path(__file__).parent
TEMPLATE_IMG     = TEST_DIR / "generated" / "park" / "park_grandfather_child_playing_ground_scattered_eye_level_3.png"
TEMPLATE_JSON    = TEST_DIR / "generated" / "park" / "park_grandfather_child_playing_ground_scattered_eye_level_3.json"

USER_PHOTOS = {
    "child":            Path(__file__).parent.parent / "template_test" / "new_child.jpg",
    "grandfather_name": Path(__file__).parent.parent / "template_test" / "grandfather.jpg",
}
HOBBY_OBJ        = Path(__file__).parent.parent / "template_test" / "objects" / "toy_car.png"

INTERMEDIATE_OUT = TEST_DIR / "park_intermediate.png"
FINAL_OUT        = TEST_DIR / "park_beautified.png"

OPENROUTER_URL   = "https://openrouter.ai/api/v1/chat/completions"
MODEL            = "openai/gpt-5.4-image-2"


def crop_face(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    s = min(w, h)
    return img.crop((
        (w - s) / 2,
        (h - s) / 4,   # bias upward to capture face not torso
        (w - s) / 2 + s,
        (h - s) / 4 + s,
    ))

def make_soft_mask(w: int, h: int, inset: int = 12, blur: int = 18) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((inset, inset, w - inset, h - inset), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    return mask

def extract_image_url(data: dict) -> str | None:
    msg = data.get("choices", [{}])[0].get("message", {})
    for img in msg.get("images", []):
        url = img.get("image_url", {}).get("url", "")
        if url: return url
    content = msg.get("content", "")
    if isinstance(content, list):
        for p in content:
            if isinstance(p, dict) and p.get("type") == "image_url":
                return p["image_url"]["url"]
    if isinstance(content, str):
        m = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", content)
        if m: return m.group(1)
    return None

def perform_swaps() -> str:
    print("1️⃣  Loading template and applying swaps...")
    with open(TEMPLATE_JSON) as f:
        meta = json.load(f)

    canvas = Image.open(TEMPLATE_IMG).convert("RGBA")

    # Faces
    for region in meta.get("face_regions", []):
        role = region["role"]
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        photo = USER_PHOTOS.get(role)
        if not photo or not photo.exists():
            print(f"   ⚠️  No photo for '{role}'")
            continue
            
        face = crop_face(photo).resize((w, h), Image.Resampling.LANCZOS)
        # HUGE feathering: force the AI to reconstruct the jaw and neck seamlessly
        mask = make_soft_mask(w, h, inset=25, blur=35)
        canvas.paste(face, (x, y), mask)
        print(f"   ✓ Pasted '{role}' face at ({x},{y}) size {w}x{h}")

    # Objects
    objects_data = meta.get("objects", [])
    if not objects_data:
        # fallback to old schema if needed
        objects_data = meta.get("object_positions", [])
        
    if HOBBY_OBJ.exists() and objects_data:
        obj_img = Image.open(HOBBY_OBJ).convert("RGBA")
        for group in objects_data:
            for pos in group.get("positions", []):
                sz = 200 # Increased from 160 to fully cover the white placeholder boxes
                obj_r = obj_img.resize((sz, sz), Image.Resampling.LANCZOS)
                canvas.paste(obj_r, (pos["x"] - sz // 2, pos["y"] - sz // 2), obj_r)
                print(f"   ✓ Pasted toy car at ({pos['x']},{pos['y']})")

    canvas.convert("RGB").save(INTERMEDIATE_OUT)
    print(f"   ✓ Intermediate saved → {INTERMEDIATE_OUT.name}")

    buf = BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def beautify(b64: str):
    print(f"2️⃣  Sending to OpenRouter ({MODEL}) for beautification...")
    with open(TEMPLATE_JSON) as f:
        meta = json.load(f)
        
    count = 3
    if meta.get("objects"):
        count = meta["objects"][0].get("count", 3)

    prompt = f"""
    You are a master digital retoucher and photographer. I am providing a base image with digitally pasted faces and object markers.
    Your job is to blend everything into a single cohesive, ultra-realistic photograph that looks like it was taken in one shot.

    CRITICAL RULES:
    1. ANATOMICAL ALIGNMENT — MOST IMPORTANT: Both faces have been digitally pasted with highly blurred edges. 
       You MUST structurally reconstruct the jawline, chin, and neck so the pasted faces align perfectly with the bodies beneath them.
       If the pasted face looks misaligned, tilted, or out of proportion with the shoulders, FIX IT anatomically.
       Blend the skin tone of the face flawlessly into the neck and chest. NO floating faces.
    2. LIGHTING MATCH: Adjust the brightness, shadows, and colour temperature of each pasted face to EXACTLY match the ambient light of the outdoor park scene.
    3. FACIAL EXPRESSIONS: Give both the grandfather and child warm, joyful, interacting expressions.
    4. FACE PRESERVATION: Preserve the core identity of each person, but seamlessly attach them to the bodies. DO NOT hallucinate accessories. If a face does NOT have glasses, DO NOT add glasses to them. The grandfather must NOT have glasses.
    5. CHILD AGE: The child MUST appear 5-6 years old — small head, chubby cheeks, young face.
    6. OBJECTS: Transform the pasted object markers into EXACTLY {count} shiny toy cars, blended naturally with contact shadows scattered on the ground. No white boxes should be visible.
    7. STYLE: Ultra-realistic, cinematic lighting, professional photography.

    Output ONLY the beautified image. No text.
    """

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "http://localhost:8502",
    }
    payload = {
        "model": MODEL,
        "modalities": ["image", "text"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text",      "text": prompt},
            ]
        }]
    }

    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        print(f"❌ API Error {resp.status_code}: {resp.text[:400]}")
        return

    img_ref = extract_image_url(resp.json())
    if not img_ref:
        print("❌ No image in response.")
        return

    print("3️⃣  Downloading final image...")
    if img_ref.startswith("data:image"):
        img_bytes = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        img_bytes = requests.get(img_ref, timeout=60).content

    with open(FINAL_OUT, "wb") as f:
        f.write(img_bytes)
    print(f"🎉 Final image saved → {FINAL_OUT.name}")


if __name__ == "__main__":
    # Check if face_regions exist first!
    with open(TEMPLATE_JSON) as f:
        meta = json.load(f)
    if not meta.get("face_regions"):
        print("❌ ERROR: The template has not been annotated yet! Please run annotate_template.py first.")
        exit(1)
        
    b64 = perform_swaps()
    beautify(b64)
