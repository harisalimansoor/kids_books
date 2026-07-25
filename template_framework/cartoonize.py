"""
cartoonize.py
─────────────────────────────────────────────────────────────────────────────
Takes any existing beautified image and converts it to a vibrant,
child-friendly cartoon / animated illustration style.

USAGE:
    python template_framework/cartoonize.py <input_image.png> [output_image.png]

EXAMPLE:
    python template_framework/cartoonize.py template_framework/classroom_beautified.png
    python template_framework/cartoonize.py template_framework/park_beautified.png
"""
import os
import re
import sys
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL          = "openai/gpt-5.4-image-2"

CARTOON_STYLES = {
    "pixar": (
        "Convert this image to a Pixar / Disney 3D animated movie style. "
        "Smooth, rounded, expressive characters with large bright eyes. "
        "Warm, cinematic lighting. Rich, colorful, detailed background. "
        "Characters should retain their real-world identity and positions."
    ),
    "flat": (
        "Convert this image to a modern flat-design cartoon illustration. "
        "Bold clean outlines, bright solid colors, minimal shadows. "
        "Think children's educational book style — friendly and vibrant."
    ),
    "anime": (
        "Convert this image to a soft, warm anime illustration style. "
        "Large expressive eyes, clean outlines, pastel tones. "
        "Background should be beautifully detailed in anime style. "
        "Keep character positions and expressions intact."
    ),
}


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


def cartoonize(input_path: Path, style: str = "pixar") -> Path:
    style_prompt = CARTOON_STYLES.get(style, CARTOON_STYLES["pixar"])

    prompt = f"""
    {style_prompt}

    IMPORTANT RULES:
    - Keep ALL characters in the same positions and same scene layout.
    - Preserve the number and positions of all objects (cupcakes, apples, footballs, etc).
    - Faces should remain recognizable as the same people.
    - No text, no numbers, no words in the output image.
    - Make it look vibrant, warm, and visually exciting for young children aged 4-7.
    - Output size: 1024x1024 pixels.
    """

    print(f"🎨  Converting to '{style}' cartoon style...")
    print(f"    Input: {input_path.name}")

    with open(input_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "http://localhost:8502",
    }
    payload = {
        "model": MODEL,
        "modalities": ["image", "text"],
        "max_tokens": 4096,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text",      "text": prompt.strip()},
            ]
        }]
    }

    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        print(f"❌  API Error {resp.status_code}: {resp.text[:300]}")
        return None

    img_ref = extract_image_url(resp.json())
    if not img_ref:
        print("❌  No image in API response.")
        return None

    if img_ref.startswith("data:image"):
        img_bytes = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        img_bytes = requests.get(img_ref, timeout=60).content

    # Build output filename
    stem   = input_path.stem
    out    = input_path.parent / f"{stem}_cartoon_{style}.png"
    with open(out, "wb") as f:
        f.write(img_bytes)

    print(f"🎉  Cartoon saved → {out.name}\n")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python template_framework/cartoonize.py <input_image.png> [pixar|flat|anime]")
        print("       Defaults to 'pixar' style if not specified.")
        sys.exit(1)

    input_img = Path(sys.argv[1])
    style_arg = sys.argv[2] if len(sys.argv) > 2 else "pixar"

    if not input_img.exists():
        print(f"❌  File not found: {input_img}")
        sys.exit(1)

    if style_arg not in CARTOON_STYLES:
        print(f"❌  Unknown style '{style_arg}'. Choose from: {list(CARTOON_STYLES.keys())}")
        sys.exit(1)

    cartoonize(input_img, style=style_arg)
