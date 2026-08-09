"""
run_direct_food_templates.py
─────────────────────────────────────────────────────────────────────────────
Generates pre-rendered Direct Interaction Sample Templates for favorite foods.

STRICT RULE:
  Each template features EXACTLY 2 CHARACTERS: 1 Child (5-6yo, Grade 1) and
  1 Adult character (mother / father / grandmother / grandfather).

For every food base, this script expands all adult-role variants so worksheet
questions and images can be matched by favourite food + family role.
"""

from __future__ import annotations

import os
import re
import json
import base64
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4-image-2"

OUTPUT_DIR = Path(__file__).parent / "direct_food_templates"

ADULT_ROLES = ("mother", "father", "grandmother", "grandfather")

# Base food scenes — each expands into one template per adult role.
FOOD_BASES = [
    {
        "slug": "pizza",
        "food": "Pizza",
        "item_description": "4 slices of cheesy, freshly baked pizza",
        "item_count": 4,
        "item_type": "pizza",
        "activity": "having a fun pizza party together at the marble kitchen counter",
        "holding": "physically holding and interacting naturally with 4 slices of cheesy, freshly baked pizza on a wooden board on the counter",
    },
    {
        "slug": "ice_cream",
        "food": "Ice cream",
        "item_description": "3 colourful waffle cone ice creams with scoops of strawberry and vanilla",
        "item_count": 3,
        "item_type": "ice cream",
        "activity": "cheerfully enjoying colourful ice cream waffle cones together",
        "holding": "holding exactly 3 colourful ice cream waffle cones in their hands and on a stand on the counter",
    },
    {
        "slug": "apples",
        "food": "Apples",
        "item_description": "4 shiny, bright red fresh apples",
        "item_count": 4,
        "item_type": "apples",
        "activity": "preparing fresh healthy fruit snacks at the kitchen counter",
        "holding": "physically holding and arranging 4 shiny, bright red fresh apples on the counter and in a wooden bowl",
    },
    {
        "slug": "burgers",
        "food": "Burgers",
        "item_description": "3 delicious mini burgers with cheese and lettuce on wooden plates",
        "item_count": 3,
        "item_type": "burgers",
        "activity": "enjoying freshly prepared mini burgers together",
        "holding": "holding and interacting with 3 delicious mini burgers on wooden plates on the kitchen island",
    },
    {
        "slug": "baking_cookies",
        "food": "Cookies",
        "item_description": "4 freshly baked chocolate chip cookies on a baking sheet",
        "item_count": 4,
        "item_type": "cookies",
        "activity": "wearing matching cute white chef hats and aprons, baking cookies together",
        "holding": "physically holding and placing 4 freshly baked golden chocolate chip cookies on a baking sheet on the counter",
    },
    {
        "slug": "making_chocolates",
        "food": "Chocolates",
        "item_description": "4 delicious gourmet chocolate truffles on a decorative plate",
        "item_count": 4,
        "item_type": "chocolates",
        "activity": "wearing chef aprons, making homemade chocolate treats",
        "holding": "holding and arranging 4 delicious, glossy chocolate truffles on a marble serving tray on the counter",
    },
    {
        "slug": "cupcakes",
        "food": "Cupcakes",
        "item_description": "4 colourful decorated cupcakes on a stand",
        "item_count": 4,
        "item_type": "cupcakes",
        "activity": "enjoying decorated cupcakes in the kitchen",
        "holding": "holding and interacting with exactly 4 colourful decorated cupcakes on a stand on the counter",
    },
    {
        "slug": "noodles",
        "food": "Noodles",
        "item_description": "2 bowls of delicious steaming noodles with chopsticks",
        "item_count": 2,
        "item_type": "noodles",
        "activity": "getting ready to eat some tasty noodles",
        "holding": "interacting with exactly 2 bowls of delicious steaming noodles with chopsticks on the counter",
    },
    {
        "slug": "pasta",
        "food": "Pasta",
        "item_description": "2 large plates of delicious pasta with tomato sauce",
        "item_count": 2,
        "item_type": "pasta",
        "activity": "enjoying a family pasta dinner",
        "holding": "interacting with exactly 2 large plates of delicious pasta with tomato sauce on the counter",
    },
    {
        "slug": "pancake_breakfast",
        "food": "Pancakes",
        "item_description": "3 fluffy pancake stacks drizzled with maple syrup",
        "item_count": 3,
        "item_type": "pancakes",
        "activity": "preparing morning breakfast pancakes together",
        "holding": "holding and serving 3 fluffy pancake stacks drizzled with maple syrup on ceramic plates",
    },
    {
        "slug": "making_smoothies",
        "food": "Smoothies",
        "item_description": "4 vibrant colourful fruit smoothie glasses with straws",
        "item_count": 4,
        "item_type": "smoothies",
        "activity": "making fresh fruit smoothies at the kitchen island counter",
        "holding": "holding and arranging 4 vibrant, colourful fruit smoothie glasses with colourful straws next to fresh berries and fruit slices",
    },
]


def _scene_prompt(food_base: dict, adult_role: str) -> str:
    adult_label = adult_role.replace("_", " ")
    count = food_base["item_count"]
    desc = food_base["item_description"]
    return f"""
Create a photorealistic image of EXACTLY TWO CHARACTERS: a young boy (Grade 1 student, exactly 5-6 years old) and his {adult_label} in a bright modern kitchen.

CRITICAL POSING REQUIREMENT:
- DIRECT FRONT-FACING HEADSHOTS: Both characters MUST be looking directly at the camera with their heads facing perfectly straight forward.
- NO SIDE PROFILES. NO LOOKING AT EACH OTHER. Head pose must be front-facing to allow for easy face-swapping.

EXPRESSION & INTERACTION:
- They are {food_base["activity"]}.
- Both characters have gentle, genuine, warm smiles with loving expressive eyes, sharing a sweet and happy family moment.
- They are {food_base["holding"]}.

COMPOSITION & FRAMING:
- Position BOTH characters centered in the frame (medium chest-up shot showing heads, shoulders, hands, and chest).
- Generous space around them with a detailed kitchen background (cabinets, window, utensils) visible above, behind, and beside them.

STYLE & LIGHTING:
- Ultra-realistic, bright warm lighting, highly vibrant and cheerful colours for a Grade 1 storybook.
- BACKGROUND FOCUS: Crystal clear, fully sharp background focus. Absolutely NO background blur, NO bokeh blur, NO shallow depth of field.

CRITICAL CONSTRAINTS:
- STRICTLY TWO CHARACTERS ONLY: 1 child (5-6 years old) and 1 {adult_label}. NO extra people or children.
- Gentle, warm, genuine smiles with friendly expressive eyes.
- Exactly {count} clearly separated, countable items matching: {desc}.
- Both characters centered with ample visible background.
- Crisp clear focus throughout — NO background blur.
- No text, no numbers, no words.
- Image size: 1024x1024 pixels square.
""".strip()


def build_template_cfg(food_base: dict, adult_role: str) -> dict:
    tmpl_id = f"kitchen_{food_base['slug']}_{adult_role}_child"
    return {
        "id": tmpl_id,
        "food": food_base["food"],
        "item_description": food_base["item_description"],
        "item_count": food_base["item_count"],
        "item_type": food_base["item_type"],
        "family": f"{adult_role}_child",
        "face_slots": ["child", f"{adult_role}_name"],
        "scene_prompt": _scene_prompt(food_base, adult_role),
    }


def all_template_cfgs(roles: tuple[str, ...] = ADULT_ROLES) -> list[dict]:
    cfgs = []
    for base in FOOD_BASES:
        for role in roles:
            cfgs.append(build_template_cfg(base, role))
    return cfgs


# Backward-compatible name used by older callers
DIRECT_TEMPLATES = all_template_cfgs()


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


def generate_direct_template(tmpl_cfg: dict, *, force: bool = False) -> bool:
    tmpl_id = tmpl_cfg["id"]
    png_path = OUTPUT_DIR / f"{tmpl_id}.png"
    json_path = OUTPUT_DIR / f"{tmpl_id}.json"

    if png_path.exists() and json_path.exists() and not force:
        print(f"  ⏭️ Skipping {tmpl_id} (already exists)")
        return True

    if not API_KEY:
        print(f"  ❌ OPENROUTER_API_KEY missing — cannot generate {tmpl_id}")
        return False

    print(f"  🎨 Generating '{tmpl_cfg['food']}' + {tmpl_cfg['family']} ({tmpl_id})...")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8502",
    }
    payload = {
        "model": MODEL,
        "modalities": ["image", "text"],
        "max_tokens": 600,
        "messages": [{"role": "user", "content": tmpl_cfg["scene_prompt"]}],
    }

    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        print(f"  ❌ API Error {resp.status_code}: {resp.text[:300]}")
        return False

    img_ref = extract_image_url(resp.json())
    if not img_ref:
        print(f"  ❌ Failed to extract image URL for {tmpl_id}")
        return False

    if img_ref.startswith("data:image"):
        img_bytes = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        img_bytes = requests.get(img_ref, timeout=60).content

    with open(png_path, "wb") as f:
        f.write(img_bytes)

    family_parts = tmpl_cfg["family"].split("_")
    meta = {
        "template_id": tmpl_id,
        "image_file": png_path.name,
        "scene": "kitchen",
        "favorite_food": tmpl_cfg["food"],
        "family": family_parts,
        "face_slots": tmpl_cfg["face_slots"],
        "face_regions": [],
        "objects": [
            {
                "id": 1,
                "type": tmpl_cfg.get("item_type", tmpl_cfg["food"].lower()),
                "count": tmpl_cfg["item_count"],
                "description": tmpl_cfg["item_description"],
                "positions": [],
            }
        ],
        "supported_question_types": [
            "counting",
            "positions",
            "visual_search",
            "family_recognition",
            "action_recognition",
        ],
        "prompt": tmpl_cfg["scene_prompt"],
        "annotation_complete": False,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"  ✓ Saved {png_path.name} and {json_path.name}")

    try:
        from kitchen_scenes.auto_annotate_faces import auto_annotate_template
        auto_annotate_template(png_path, force=True)
    except Exception as exc:
        print(f"  ⚠️  Auto-annotate skipped for {tmpl_id}: {exc}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Generate kitchen food+role templates")
    parser.add_argument("--force", action="store_true", help="Regenerate even if files exist")
    parser.add_argument("--food", default="", help="Only generate for this favourite food")
    parser.add_argument("--role", default="", help="Only generate for this adult role")
    parser.add_argument("--annotate", action="store_true", help="Auto-annotate faces after generation")
    parser.add_argument("--missing-only", action="store_true", help="Only generate templates that do not exist yet")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    roles = (args.role.strip().lower(),) if args.role.strip() else ADULT_ROLES
    food_filter = args.food.strip().lower()

    cfgs = []
    for cfg in all_template_cfgs(roles):
        if food_filter and cfg["food"].strip().lower() != food_filter:
            continue
        if args.missing_only:
            png = OUTPUT_DIR / f"{cfg['id']}.png"
            js = OUTPUT_DIR / f"{cfg['id']}.json"
            if png.exists() and js.exists():
                continue
        cfgs.append(cfg)

    print(f"🚀 Generating {len(cfgs)} food+role kitchen templates...\n")
    ok = 0
    for tmpl in cfgs:
        if generate_direct_template(tmpl, force=args.force):
            ok += 1

    print(f"\n✅ Template generation finished: {ok}/{len(cfgs)} succeeded.")

    if args.annotate:
        from kitchen_scenes.auto_annotate_faces import annotate_all
        annotate_all(force=False)


if __name__ == "__main__":
    main()
