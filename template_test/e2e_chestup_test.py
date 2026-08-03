"""
e2e_chestup_test.py
───────────────────
End-to-End test specifically for the new chest-up interactive template.
Saves to 03_chestup_intermediate.png and 04_chestup_beautified.png
so existing files are never overwritten.
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
TEMPLATE_IMG     = TEST_DIR / "grade_1" / "counting" / "count_04_photo_mother_chestup_interactive.png"
TEMPLATE_JSON    = TEST_DIR / "grade_1" / "counting" / "count_04_photo_mother_chestup_interactive.json"

USER_PHOTOS = {
    "child":       TEST_DIR / "childd.png",
    "mother_name": TEST_DIR / "mother.jpg",
}
HOBBY_OBJ        = TEST_DIR / "objects" / "football.png"

INTERMEDIATE_OUT = TEST_DIR / "05_chestup_intermediate_v2.png"
FINAL_OUT        = TEST_DIR / "06_chestup_beautified_v2.png"

OPENROUTER_URL   = "https://openrouter.ai/api/v1/chat/completions"
MODEL            = "openai/gpt-5.4-image-2"


# ── Helpers ───────────────────────────────────────────────────────────────────
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
    """Creates a heavily feathered ellipse mask — much softer edges than a plain ellipse."""
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    # Draw ellipse inset from the edge so the fade starts well inside the border
    draw.ellipse((inset, inset, w - inset, h - inset), fill=255)
    # Apply heavy gaussian blur so the transition is very gradual
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


# ── Step 1: Swap faces + objects ──────────────────────────────────────────────
def perform_swaps() -> str:
    print("1️⃣  Loading template and applying swaps...")
    with open(TEMPLATE_JSON, encoding="utf-8") as f:
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
        # Use heavily feathered soft mask for natural blending
        mask = make_soft_mask(w, h, inset=14, blur=20)
        canvas.paste(face, (x, y), mask)
        print(f"   ✓ Pasted '{role}' face at ({x},{y}) size {w}x{h}")

    # Objects
    if HOBBY_OBJ.exists():
        obj_img = Image.open(HOBBY_OBJ).convert("RGBA")
        for group in meta.get("object_positions", []):
            for pos in group.get("positions", []):
                sz = 160
                obj_r = obj_img.resize((sz, sz), Image.Resampling.LANCZOS)
                canvas.paste(obj_r, (pos["x"] - sz // 2, pos["y"] - sz // 2), obj_r)
                print(f"   ✓ Pasted football at ({pos['x']},{pos['y']})")

    canvas.convert("RGB").save(INTERMEDIATE_OUT)
    print(f"   ✓ Intermediate saved → {INTERMEDIATE_OUT.name}")

    buf = BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ── Step 2: AI beautification ─────────────────────────────────────────────────
def beautify(b64: str):
    print(f"2️⃣  Sending to OpenRouter ({MODEL}) for beautification...")
    with open(TEMPLATE_JSON, encoding="utf-8") as f:
        meta = json.load(f)
    count = meta.get("count", 4)

    prompt = f"""
    You are a master digital retoucher and photographer. I am providing a base image with digitally pasted faces and footballs.
    Your job is to blend everything into a single cohesive, ultra-realistic photograph that looks like it was taken in one shot.

    CRITICAL RULES:
    1. FACE BLENDING — MOST IMPORTANT: Both faces have been digitally pasted in and may have visible edges or mismatched lighting.
       You MUST completely eliminate any visible boundary, halo, or cut-out edge around EACH face.
       Blend the neck, jaw, hairline, and skin tone of each face seamlessly into the background and clothing below it.
       Pay special attention to the MOTHER's face — ensure her skin tone and lighting perfectly matches the scene.
    2. LIGHTING MATCH: Adjust the brightness, shadows, and colour temperature of each pasted face to EXACTLY match
       the ambient light of the scene. If the scene has warm indoor lighting, the faces must look warmly lit too.
    3. FACIAL EXPRESSIONS: Even if input faces are neutral, give both the mother and child warm, joyful, laughing expressions.
    4. FACE PRESERVATION: While blending, preserve the core identity of each person. Do not replace them.
    5. CHILD AGE: The child MUST appear 5-6 years old — small head, chubby cheeks, young face.
    6. OBJECTS: Maintain EXACTLY {count} footballs, blended naturally with contact shadows.
    7. STYLE: Ultra-realistic, cinematic warm indoor lighting, professional photography.

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
    b64 = perform_swaps()
    beautify(b64)
