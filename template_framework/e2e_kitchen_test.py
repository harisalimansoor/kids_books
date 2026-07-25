"""
e2e_kitchen_test.py
End-to-End PERSONALIZED test for a kitchen template.
Demonstrates the two-phase object injection:
  Phase 1: Template has white placeholder boxes
  Phase 2: AI replaces boxes with the user's chosen object (fav food / hobby)
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

# Import the new centralized beautify prompt builder
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from template_framework.prompt_builder import build_beautify_prompt
from template_framework.config import TemplateCombination
from template_framework.definitions import get_scene, get_family, get_activity, get_camera, get_layout

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")

TEST_DIR = Path(__file__).parent

# ─── Template to use ────────────────────────────────────────────────────────────
SCENE    = "kitchen"
FAMILY   = "mother_child"
ACTIVITY = "baking_cupcakes"
CAMERA   = "chest_up"
LAYOUT   = "table_row"
COUNT    = 4

TEMPLATE_IMG  = TEST_DIR / "kitchen_templates" / "kitchen" / f"kitchen_{FAMILY}_{ACTIVITY}_{LAYOUT}_{CAMERA}_{COUNT}_white_placeholder_box.png"
TEMPLATE_JSON = TEST_DIR / "kitchen_templates" / "kitchen" / f"kitchen_{FAMILY}_{ACTIVITY}_{LAYOUT}_{CAMERA}_{COUNT}_white_placeholder_box.json"

# ─── USER INPUTS (simulating app.py user profile) ────────────────────────────────
USER_PHOTOS = {
    "child":       Path(__file__).parent.parent / "template_test" / "new_child.jpg",
    "mother_name": Path(__file__).parent.parent / "template_test" / "new_mother.jpg",
}

# This would come from app.py user profile:
# hobbies → map_hobby_to_object() → e.g. "football"
# fav_food → e.g. "pizza slice"
USER_OBJECT = "chocolate cupcake"  # <── Swap this to anything! "apple", "football", "teddy bear"

INTERMEDIATE_OUT = TEST_DIR / f"kitchen_intermediate.png"
FINAL_OUT        = TEST_DIR / f"kitchen_beautified_{USER_OBJECT.replace(' ', '_')}.png"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL          = "openai/gpt-5.4-image-2"


def crop_face(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    s = min(w, h)
    return img.crop(((w - s) / 2, (h - s) / 4, (w - s) / 2 + s, (h - s) / 4 + s))

def make_soft_mask(w: int, h: int, inset: int = 25, blur: int = 35) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((inset, inset, w - inset, h - inset), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))

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
    print("1️⃣  Loading template and applying face swaps...")
    with open(TEMPLATE_JSON) as f:
        meta = json.load(f)

    canvas = Image.open(TEMPLATE_IMG).convert("RGBA")

    for region in meta.get("face_regions", []):
        role = region["role"]
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        photo = USER_PHOTOS.get(role)
        if not photo or not photo.exists():
            print(f"   ⚠️  No photo for '{role}'")
            continue
        face = crop_face(photo).resize((w, h), Image.Resampling.LANCZOS)
        mask = make_soft_mask(w, h)
        canvas.paste(face, (x, y), mask)
        print(f"   ✓ Pasted '{role}' face at ({x},{y}) size {w}x{h}")

    canvas.convert("RGB").save(INTERMEDIATE_OUT)
    print(f"   ✓ Intermediate saved → {INTERMEDIATE_OUT.name}")

    buf = BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def beautify(b64: str):
    print(f"2️⃣  Sending to OpenRouter for beautification...")
    print(f"   💡 Personalizing with object: '{USER_OBJECT}'")

    # Build combo just for the prompt metadata
    combo = TemplateCombination(
        get_scene(SCENE), get_family(FAMILY),
        get_activity(ACTIVITY), get_camera(CAMERA),
        get_layout(LAYOUT), COUNT,
    )
    # Use the centralized beautify prompt — just change USER_OBJECT at the top!
    prompt = build_beautify_prompt(combo, personalized_object=USER_OBJECT)

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "http://localhost:8502",
    }
    payload = {
        "model": MODEL,
        "modalities": ["image", "text"],
        "max_tokens": 1200,
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
    with open(TEMPLATE_JSON) as f:
        meta = json.load(f)
    if not meta.get("face_regions"):
        print("❌ ERROR: Template not annotated yet! Run:")
        print(f"   python template_test/annotate_template.py {TEMPLATE_IMG}")
        exit(1)
    print(f"\n🔄 Kitchen E2E Test | Object: '{USER_OBJECT}'\n")
    b64 = perform_swaps()
    beautify(b64)
