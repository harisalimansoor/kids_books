"""
swap_objects.py
──────────────────────────────────────────────────────────────────────────────
Replaces objects in an existing image with a new user-specified object.

USAGE:
    python template_framework/swap_objects.py <image.png> "<from_object>" "<to_object>"

EXAMPLE:
    python template_framework/swap_objects.py template_framework/kitchen_beautified_chocolate_cupcake.png "cupcake" "chocolate bar"
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


def swap_objects(input_path: Path, from_obj: str, to_obj: str) -> Path | None:
    print(f"\n🔄  Object Swap")
    print(f"    Input  : {input_path.name}")
    print(f"    Swap   : '{from_obj}' → '{to_obj}'")

    with open(input_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    prompt = f"""
    You are a professional image editor. I have an image that contains several '{from_obj}' objects.

    YOUR TASK:
    - Replace every '{from_obj}' in the image with a photorealistic '{to_obj}'.
    - Keep the EXACT same count of objects. Same positions, same sizes.
    - The characters (people), background, lighting, and scene layout must remain COMPLETELY UNCHANGED.
    - The new '{to_obj}' objects must:
      * Match the lighting and shadows of the scene
      * Look photorealistic and natural
      * Fit naturally in the hands or on the surface where the '{from_obj}' objects were

    STRICT RULES:
    - Do NOT move or resize the characters.
    - Do NOT change the background.
    - Do NOT change facial expressions or poses.
    - Do NOT add text, numbers, or labels.
    - Only change the '{from_obj}' objects to '{to_obj}'.

    Output ONLY the edited image.
    """

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

    print("⏳  Sending to AI...")
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

    to_slug = to_obj.replace(" ", "_")
    out     = input_path.parent / f"{input_path.stem}_swapped_to_{to_slug}.png"
    with open(out, "wb") as f:
        f.write(img_bytes)

    print(f"🎉  Saved → {out.name}\n")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print('Usage: python template_framework/swap_objects.py <image.png> "<from>" "<to>"')
        print('Example: python template_framework/swap_objects.py kitchen_beautified.png "cupcake" "chocolate bar"')
        sys.exit(1)

    img   = Path(sys.argv[1])
    frm   = sys.argv[2]
    to    = sys.argv[3]

    if not img.exists():
        print(f"❌  File not found: {img}")
        sys.exit(1)

    swap_objects(img, frm, to)
