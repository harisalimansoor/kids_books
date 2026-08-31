"""
generate_role_templates.py
─────────────────────────────────────────────────────────────────────────────
Generate kitchen ROLE templates with white object placeholders.

Reference style: kitchen_scenes direct food templates
  - bright modern kitchen
  - exactly 2 characters (child + one adult)
  - warm smiles, front-facing heads for face swap
  - countable WHITE placeholder boxes on the counter (object-agnostic)

Object identity is filled later by the compositor using objects/<category>/*.json
and object-specific hand-interaction prompts.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4-image-2"

SCENES_DIR = Path(__file__).parent / "scenes" / "kitchen"
DEFAULT_COUNT = 4
ADULT_ROLES = ("mother", "father", "grandmother", "grandfather")


def _role_prompt(adult_role: str, count: int = DEFAULT_COUNT) -> str:
    adult = adult_role.replace("_", " ")
    return f"""
Create a photorealistic image of EXACTLY TWO CHARACTERS: a young boy (Grade 1 student, exactly 5-6 years old) and his {adult} in a bright, spacious modern kitchen.

CRITICAL POSING REQUIREMENT:
- DIRECT FRONT-FACING HEADSHOTS: Both characters MUST look directly at the camera with heads facing straight forward.
- NO side profiles. NO looking only at each other. Front-facing faces for easy face-swapping.

NATURAL INTERACTION:
- They stand/sit together at a marble kitchen counter.
- Warm, joyful, candid smiles with bright friendly eyes.
- Their hands are near the counter, ready to interact with objects on the counter
  (reaching, offering, or gently resting near the placeholders).

OBJECT PLACEHOLDERS (VERY IMPORTANT):
- On the kitchen counter in the foreground, place EXACTLY {count} clearly separated
  white rounded square placeholder boxes in a horizontal row.
- Same size, evenly spaced, easy to count.
- These boxes are empty placeholders — NOT food items yet.
- Leave space so hands can naturally hold or touch items that will replace the boxes later.

COMPOSITION & FRAMING:
- Medium chest-up shot showing heads, shoulders, hands, and the counter surface.
- Both characters centered with detailed kitchen background (cabinets, window, utensils).
- BACKGROUND FOCUS: completely sharp. NO blur, NO bokeh.

STYLE:
- Ultra-realistic, bright warm kitchen lighting, vibrant cheerful colours.
- Grade 1 storybook friendly mood.

CRITICAL CONSTRAINTS:
- STRICTLY TWO CHARACTERS ONLY: 1 child (5-6 years old) and 1 {adult}.
- Exactly {count} white rounded placeholder boxes on the counter.
- No real food yet, no text, no numbers, no watermarks.
- Image size: 1024x1024 pixels square.
""".strip()


def extract_image_url(data: dict) -> str | None:
    msg = data.get("choices", [{}])[0].get("message", {})
    for img in msg.get("images", []):
        url = img.get("image_url", {}).get("url", "")
        if url:
            return url
    content = msg.get("content", "")
    if isinstance(content, list):
        for p in content:
            if isinstance(p, dict) and p.get("type") == "image_url":
                return p["image_url"]["url"]
    if isinstance(content, str):
        m = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", content)
        if m:
            return m.group(1)
    return None


def _default_face_regions(adult_role: str) -> list[dict]:
    """Approximate face boxes for 1024x1024 kitchen two-person framing."""
    return [
        {"role": "child", "x": 180, "y": 280, "w": 230, "h": 250},
        {"role": f"{adult_role}_name", "x": 540, "y": 120, "w": 250, "h": 290},
    ]


def _default_object_positions(count: int = DEFAULT_COUNT) -> list[dict]:
    """Evenly spaced placeholder centres along the counter foreground."""
    # Tuned for 1024-wide kitchen counter row
    xs = [180, 380, 580, 780][:count]
    if count == 3:
        xs = [250, 512, 774]
    if count == 2:
        xs = [340, 684]
    return [{
        "label": "placeholder_box",
        "count": count,
        "positions": [{"x": x, "y": 860} for x in xs],
    }]


def generate_role_template(adult_role: str, *, force: bool = False, count: int = DEFAULT_COUNT) -> bool:
    out_dir = SCENES_DIR / f"{adult_role}_child"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl_id = f"kitchen_{adult_role}_child_interactive"
    png_path = out_dir / f"{tmpl_id}.png"
    json_path = out_dir / f"{tmpl_id}.json"

    if png_path.exists() and json_path.exists() and not force:
        print(f"  ⏭️  Skipping {tmpl_id} (already exists)")
        return True

    if not API_KEY:
        print(f"  ❌ OPENROUTER_API_KEY missing — cannot generate {tmpl_id}")
        return False

    print(f"  🎨 Generating kitchen interactive role template: {adult_role}_child ...")
    prompt = _role_prompt(adult_role, count=count)
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8502",
    }
    payload = {
        "model": MODEL,
        "modalities": ["image", "text"],
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        print(f"  ❌ API Error {resp.status_code}: {resp.text[:300]}")
        return False

    img_ref = extract_image_url(resp.json())
    if not img_ref:
        print(f"  ❌ No image returned for {tmpl_id}")
        return False

    if img_ref.startswith("data:image"):
        img_bytes = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        img_bytes = requests.get(img_ref, timeout=60).content

    png_path.write_bytes(img_bytes)

    meta = {
        "template_id": tmpl_id,
        "image_file": png_path.name,
        "scene_family": "kitchen",
        "scene": "kitchen",
        "family": [adult_role, "child"],
        "face_slots": ["child", f"{adult_role}_name"],
        "face_regions": _default_face_regions(adult_role),
        "count": count,
        "object": "placeholder_box",
        "object_positions": _default_object_positions(count),
        "style": "photorealistic",
        "interactive": True,
        "annotation_complete": True,
        "prompt": prompt,
        "notes": (
            "White placeholder boxes are object-agnostic. "
            "Compositor fills them with the chosen food/hobby/pet asset, "
            "then AI-beautifies hands to match that object's interaction style."
        ),
    }
    json_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"  ✓ Saved {png_path.relative_to(Path(__file__).parent)} and JSON metadata")

    # Every render frames the characters differently, so replace the approximate
    # boxes with detected ones — otherwise face swaps land off-face.
    try:
        import sys
        from pathlib import Path as _P

        _np = _P(__file__).resolve().parents[1] / "new_pipeline"
        if str(_np) not in sys.path:
            sys.path.insert(0, str(_np))
        from swapping_engine.face_detect import annotate_template
        annotate_template(png_path, force=True)
    except Exception as exc:
        print(f"  ⚠️  Face auto-annotation skipped: {exc}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate interactive kitchen role templates")
    parser.add_argument("--role", default="", help="Only one adult role")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    args = parser.parse_args()

    roles = (args.role.strip().lower(),) if args.role.strip() else ADULT_ROLES
    print(f"🚀 Generating {len(roles)} kitchen interactive role template(s)...\n")
    ok = 0
    for role in roles:
        if role not in ADULT_ROLES:
            print(f"  ⚠️  Unknown role '{role}', skipping")
            continue
        if generate_role_template(role, force=args.force, count=args.count):
            ok += 1
    print(f"\n✅ Done: {ok}/{len(roles)} role templates ready.")


if __name__ == "__main__":
    main()
