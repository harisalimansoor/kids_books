"""
generate_face_photos.py
───────────────────────
Generates simple, clear, front-facing portrait photos
for use as face swap sources.
"""

import os
import re
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")

OUTPUT_DIR = Path(__file__).parent
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4-image-2"

PORTRAITS = [
    {
        "filename": "new_child.jpg",
        "prompt": (
            "A simple, clean passport-style portrait photo of a young boy aged 6. "
            "He is facing directly forward, looking straight at the camera with a small smile. "
            "Plain white background. Face fully visible, front-facing, no side profile. "
            "Shoulders visible. Natural skin, brown eyes, short neat hair. "
            "Simple casual clothing. Clear, sharp, well-lit photo."
        )
    },
    {
        "filename": "new_mother.jpg",
        "prompt": (
            "A simple, clean passport-style portrait photo of a young mother aged 30-35. "
            "She is facing directly forward, looking straight at the camera with a warm gentle smile. "
            "Plain white background. Face fully visible, front-facing, no side profile. "
            "Shoulders visible. Natural skin, shoulder-length brown hair. "
            "Simple casual blouse. Clear, sharp, well-lit photo."
        )
    }
]


def extract_image(data: dict) -> str | None:
    msg = data.get("choices", [{}])[0].get("message", {})
    images = msg.get("images", [])
    if images and isinstance(images, list):
        url = images[0].get("image_url", {}).get("url", "")
        if url: return url
    content = msg.get("content", "")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return part["image_url"]["url"]
    if isinstance(content, str):
        match = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", content)
        if match: return match.group(1)
    return None


def generate(prompt: str) -> bytes | None:
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
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        print(f"   ✗ Error: {resp.text[:200]}")
        return None
    img_ref = extract_image(resp.json())
    if not img_ref: return None
    if img_ref.startswith("data:image"):
        return base64.b64decode(img_ref.split(",", 1)[1])
    return requests.get(img_ref, timeout=60).content


def main():
    print("\n" + "═"*50)
    print("  Generating Face Photos for Swap")
    print("═"*50 + "\n")

    for p in PORTRAITS:
        print(f"→ Generating: {p['filename']}")
        img_bytes = generate(p["prompt"])
        if img_bytes:
            out_path = OUTPUT_DIR / p["filename"]
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            print(f"  ✓ Saved: {out_path}\n")
        else:
            print(f"  ✗ Failed\n")

    print("Done! Open the files to verify the faces look correct.")
    print("═"*50)

if __name__ == "__main__":
    main()
