"""
generate_chest_up_template.py
─────────────────────────────
Generates a single chest-up interactive template image
showing two characters interacting naturally.
"""

import os
import re
import base64
import json
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")

OUTPUT_DIR = Path(__file__).parent / "grade_1" / "counting"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4-image-2"

# ── Template definition ──────────────────────────────────────────────────────
TEMPLATE = {
    "filename":    "count_04_photo_mother_chestup_interactive.png",
    "json_name":   "count_04_photo_mother_chestup_interactive.json",
    "count":       4,
    "face_slots":  ["child", "mother_name"],
    "prompt": """
Create a photorealistic image of a very young child (Grade 1 student, exactly 5-6 years old) and his mother, shown from the CHEST UP only (no full body, no legs visible). They are sitting close together at a table in a cozy warmly lit indoor setting.

CHILD AGE — CRITICALLY IMPORTANT:
- The child MUST look exactly 5-6 years old. He is in Grade 1.
- He must have a small, round child's head, chubby cheeks, small nose, bright wide eyes — the face of a kindergarten/Grade 1 boy.
- He is noticeably SMALLER than his mother — his head should be visibly smaller and lower in the frame.
- He must NOT look like a teenager, pre-teen, or older than 6 years old.

COMPOSITION:
- CHEST-UP portrait frame — show faces, necks, shoulders, and upper chest only. Cut off at the waist/table edge.
- The mother is on the LEFT, the child is on the RIGHT. The child appears noticeably shorter/smaller than the mother even in the chest-up frame.
- Both characters face slightly toward each other, laughing and smiling warmly. Front-facing faces, no side profiles.
- On the table surface at the bottom of the frame, place exactly 4 clearly separated white rounded square placeholder boxes in a horizontal row. They should be the same size and evenly spaced.

STYLE:
- Ultra-realistic, warm cinematic indoor lighting, high detail, soft blurred background.
- The boy is pointing excitedly at the boxes while the mother looks on with a big warm smile.

CRITICAL:
- Child must be 5-6 years old (Grade 1). NOT older.
- Exactly 4 white placeholder boxes on the table. No text, no numbers in the image.
- Image size: 1024x1024 pixels square.
"""
}


def extract_image(data: dict) -> str | None:
    msg = data.get("choices", [{}])[0].get("message", {})
    images = msg.get("images", [])
    if images:
        url = images[0].get("image_url", {}).get("url", "")
        if url: return url
    content = msg.get("content", "")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return part["image_url"]["url"]
    if isinstance(content, str):
        m = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", content)
        if m: return m.group(1)
    return None


def generate_image(prompt: str) -> bytes | None:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "http://localhost:8502",
    }
    payload = {
        "model": MODEL,
        "modalities": ["image", "text"],
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        print(f"  ✗ API Error: {resp.text[:300]}")
        return None
    img_ref = extract_image(resp.json())
    if not img_ref:
        return None
    if img_ref.startswith("data:image"):
        return base64.b64decode(img_ref.split(",", 1)[1])
    r = requests.get(img_ref, timeout=60)
    return r.content


def save_json(t: dict, img_path: Path):
    json_path = img_path.parent / t["json_name"]
    meta = {
        "template_id":    img_path.stem,
        "question_type":  "counting",
        "count":          t["count"],
        "object":         "placeholder_box",
        "style":          "photorealistic",
        "face_slots":     t["face_slots"],
        "face_regions":   [],   # to be filled by annotate_template.py
        "object_positions": [], # to be filled by annotate_template.py
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"  ✓ JSON stub saved: {json_path.name}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    t = TEMPLATE
    img_path = OUTPUT_DIR / t["filename"]

    print(f"\n{'═'*55}")
    print(f"  Generating chest-up interactive template")
    print(f"{'═'*55}")
    print(f"  → {t['filename']}")
    print(f"  Count: {t['count']} | Roles: {t['face_slots']}")

    img_bytes = generate_image(t["prompt"])
    if img_bytes:
        with open(img_path, "wb") as f:
            f.write(img_bytes)
        print(f"  ✓ Image saved: {img_path}")
        save_json(t, img_path)
        print(f"\n✅ Done! Open the image to review, then annotate with:")
        print(f"   python template_test/annotate_template.py {img_path}")
    else:
        print("  ✗ Generation failed.")


if __name__ == "__main__":
    main()
