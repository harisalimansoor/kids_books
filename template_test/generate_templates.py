"""
generate_templates.py
─────────────────────
Generates Photorealistic Family Interaction templates.
We use generic "small white boxes" as placeholders for the objects.
This makes it easy to paste any transparent hobby object (like a football)
over the box before AI beautification.
"""

import os
import re
import json
import base64
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# ── Load Env & Config ────────────────────────────────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")

OUTPUT_DIR = Path(__file__).parent / "grade_1" / "counting"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4-image-2"


# ── The 2 Family Interaction Scenes (Highly Interactive) ──────────────────────
TEMPLATES = [
    {
        "count": 3,
        "object": "placeholder_box",
        "scene": (
            "A warm, inviting, modern living room with soft natural sunlight. "
            "A young mother is sitting cross-legged on a cozy, fluffy rug. "
            "Her young child (age 5-6) is happily sitting on her lap. "
            "They are laughing, hugging, and playing together, looking incredibly joyful. "
            "On the rug directly in front of them, there are exactly 3 small, plain white cardboard boxes. "
            "The 3 white boxes are clearly separated from each other so they can be easily counted. "
            "Both faces are clearly visible to the camera."
        ),
        "face_slots": ["child", "mother_name"]
    },
    {
        "count": 5,
        "object": "placeholder_box",
        "scene": (
            "A beautiful grassy park on a sunny afternoon. "
            "An elderly grandfather and his young grandchild (age 5-6) are sitting very close together on a picnic blanket. "
            "The grandfather has his arm around the child's shoulder, and the child is excitedly pointing at something on the ground. "
            "They are interacting warmly. "
            "On the blanket directly in front of them, there are exactly 5 small, plain white cardboard boxes. "
            "The 5 white boxes are placed in a clear arrangement, distinct and separated from each other. "
            "Both faces are clearly visible to the camera."
        ),
        "face_slots": ["child", "grandfather_name"]
    },
]

# ── Photorealistic Style Suffix ──────────────────────────────────────────────
STYLE = (
    "\n\nART STYLE: Ultra-realistic, photorealistic photography. "
    "Shot on an 85mm portrait lens, cinematic natural lighting, highly detailed, emotional connection. "
    "NO text, NO numbers, NO labels anywhere in the image. "
    "Wide landscape composition (16:9). "
    "The white boxes must be clearly separated and easy to count. "
    "Both people must have their faces clearly visible and looking forward. "
    "Extremely high quality, professional photography."
)


def build_prompt(t: dict) -> str:
    return (
        f"Generate a photorealistic scene. {t['scene']}"
        f"\n\nCRITICAL RULE: There must be EXACTLY {t['count']} small white boxes — no more, no less. "
        f"Count them before finishing."
        f"{STYLE}"
    )


# ── API Logic ─────────────────────────────────────────────────────────────────
def extract_image(data: dict) -> str | None:
    message = data.get("choices", [{}])[0].get("message", {})
    images = message.get("images", [])
    if images and isinstance(images, list):
        url = images[0].get("image_url", {}).get("url", "")
        if url: return url
    content = message.get("content", "")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                if url: return url
    if isinstance(content, str):
        match = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", content)
        if match: return match.group(1)
    return None


def generate_image(prompt: str) -> bytes | None:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8502",
    }
    payload = {
        "model": MODEL,
        "modalities": ["image", "text"],
        "messages": [{"role": "user", "content": prompt}],
    }
    
    print(f"   → Calling {MODEL} (Photorealistic mode)...")
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    
    if resp.status_code != 200:
        print(f"   ✗ API Error: {resp.text[:200]}")
        return None

    img_ref = extract_image(resp.json())
    if not img_ref:
        return None

    if img_ref.startswith("data:image"):
        return base64.b64decode(img_ref.split(",", 1)[1])
    else:
        return requests.get(img_ref, timeout=60).content


# ── Metadata Save ─────────────────────────────────────────────────────────────
def save_metadata(t: dict, img_path: Path, prompt: str):
    prefix = "mother" if "mother_name" in t["face_slots"] else "grandfather"
    
    meta = {
        "template_id": f"counting_{t['count']:02d}_{prefix}",
        "question_type": "counting",
        "count": t["count"],
        "object": "placeholder_box",
        "style": "photorealistic",
        "face_slots": t["face_slots"],
        "face_regions": [],       # To be annotated visually
        "object_positions": [],   # To be annotated visually
    }
    
    meta_path = img_path.with_suffix(".json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"   ✓ Metadata saved to {meta_path.name}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "═" * 65)
    print("  Generating Photorealistic Family Templates (2 scenes)")
    print("═" * 65 + "\n")

    for i, t in enumerate(TEMPLATES, 1):
        prefix = "mother" if "mother_name" in t["face_slots"] else "grandfather"
        filename = f"count_{t['count']:02d}_photo_{prefix}_interactive.png"
        img_path = OUTPUT_DIR / filename
        
        print(f"[{i}/2] Generating: {filename}")
        
        prompt = build_prompt(t)
        img_bytes = generate_image(prompt)
        
        if img_bytes:
            with open(img_path, "wb") as f:
                f.write(img_bytes)
            print(f"   ✓ Saved: {filename}")
            save_metadata(t, img_path, prompt)
        else:
            print("   ✗ Failed to generate image.")
        print()
        
if __name__ == "__main__":
    main()
