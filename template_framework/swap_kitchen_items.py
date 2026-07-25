"""
swap_kitchen_items.py
─────────────────────────────────────────────────────────────────────────────
End-to-End script to take the centered Kitchen template with white placeholder boxes,
apply face-swapping, and generate customized beautified images with kitchen items:
  - Chocolates ("gourmet chocolate bars")
  - Cupcakes ("frosted cupcakes with sprinkles")
  - Vegetables ("fresh colourful vegetables like tomatoes and carrots")

USAGE:
    python template_framework/swap_kitchen_items.py
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

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from template_framework.prompt_builder import build_beautify_prompt
from template_framework.config import TemplateCombination
from template_framework.definitions import get_scene, get_family, get_activity, get_camera, get_layout

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")

TEST_DIR = Path(__file__).parent
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4-image-2"

TEMPLATE_IMG  = TEST_DIR / "kitchen_templates" / "kitchen" / "kitchen_mother_child_baking_cupcakes_table_row_chest_up_4_white_placeholder_box.png"
TEMPLATE_JSON = TEST_DIR / "kitchen_templates" / "kitchen" / "kitchen_mother_child_baking_cupcakes_table_row_chest_up_4_white_placeholder_box.json"

USER_PHOTOS = {
    "child":       Path(__file__).parent.parent / "template_test" / "new_child.jpg",
    "mother_name": Path(__file__).parent.parent / "template_test" / "new_mother.jpg",
}

# Items to generate and swap onto the white boxes
SWAP_OBJECTS = [
    "chocolate bar",
    "frosted cupcake",
    "fresh vegetable",
]

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

def prepare_intermediate() -> tuple[str, dict]:
    print("1️⃣  Loading kitchen template & checking face regions...")
    with open(TEMPLATE_JSON) as f:
        meta = json.load(f)

    # Ensure face regions exist
    if not meta.get("face_regions"):
        meta["face_regions"] = [
            {"role": "child", "x": 220, "y": 140, "w": 220, "h": 260},
            {"role": "mother_name", "x": 550, "y": 120, "w": 240, "h": 300}
        ]
        with open(TEMPLATE_JSON, "w") as f:
            json.dump(meta, f, indent=2)

    canvas = Image.open(TEMPLATE_IMG).convert("RGBA")

    for region in meta.get("face_regions", []):
        role = region["role"]
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        photo = USER_PHOTOS.get(role)
        if not photo or not photo.exists():
            print(f"   ⚠️  No photo for '{role}' at {photo}")
            continue
        face = crop_face(photo).resize((w, h), Image.Resampling.LANCZOS)
        mask = make_soft_mask(w, h)
        canvas.paste(face, (x, y), mask)
        print(f"   ✓ Pasted '{role}' face at ({x},{y}) size {w}x{h}")

    inter_path = TEST_DIR / "kitchen_intermediate.png"
    canvas.convert("RGB").save(inter_path)
    print(f"   ✓ Saved intermediate face-swapped image → {inter_path.name}")

    buf = BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return b64, meta

def beautify_item(b64: str, target_object: str) -> Path | None:
    slug = target_object.replace(" ", "_")
    out_path = TEST_DIR / f"kitchen_beautified_{slug}.png"
    print(f"\n2️⃣  Generating beautified image with '{target_object}'...")

    combo = TemplateCombination(
        get_scene("kitchen"), get_family("mother_child"),
        get_activity("baking_cupcakes"), get_camera("chest_up"),
        get_layout("table_row"), 4,
    )
    prompt = build_beautify_prompt(combo, personalized_object=target_object)

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
        print(f"❌ API Error {resp.status_code}: {resp.text[:300]}")
        return None

    img_ref = extract_image_url(resp.json())
    if not img_ref:
        print("❌ No image returned from API.")
        return None

    if img_ref.startswith("data:image"):
        img_bytes = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        img_bytes = requests.get(img_ref, timeout=60).content

    with open(out_path, "wb") as f:
        f.write(img_bytes)

    print(f"🎉  Saved final '{target_object}' image → {out_path.name}")
    return out_path

def main():
    print("🚀  Starting Kitchen Item Swaps (Chocolates, Cupcakes, Vegetables)...\n")
    b64, meta = prepare_intermediate()
    
    for item in SWAP_OBJECTS:
        beautify_item(b64, item)

    print("\n✅  All kitchen item swaps completed successfully!")

if __name__ == "__main__":
    main()
