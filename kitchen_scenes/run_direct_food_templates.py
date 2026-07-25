"""
run_direct_food_templates.py
─────────────────────────────────────────────────────────────────────────────
Generates pre-rendered Direct Interaction Sample Templates for favorite foods & kitchen activities:
  - 🍕 Pizza
  - 🍦 Ice cream
  - 🍎 Apples
  - 🍔 Burgers
  - 🥖 Baking Cookies/Cupcakes
  - 🍫 Making Chocolates
  - 🥞 Making Pancakes
  - 🍓 Making Smoothies

STRICT RULE:
  Each template features EXACTLY 2 CHARACTERS: 1 Child (5-6yo, Grade 1) and 1 Adult character.
  Expressions: Gentle, genuine, warm smiles with a loving, sweet look and bright friendly eyes.

Output Folder: template_framework/direct_food_templates/
"""

import os
import re
import json
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4-image-2"

OUTPUT_DIR = Path(__file__).parent / "direct_food_templates"

DIRECT_TEMPLATES = [
    {
        "id": "kitchen_pizza_mother_child",
        "food": "Pizza",
        "item_description": "4 slices of cheesy, freshly baked pizza",
        "item_count": 4,
        "family": "mother_child",
        "face_slots": ["child", "mother_name"],
        "scene_prompt": """
Create a photorealistic image of EXACTLY TWO CHARACTERS: a young boy (Grade 1 student, exactly 5-6 years old) and his mother in a bright, spacious modern kitchen.

EXPRESSION & INTERACTION:
- They are having a fun pizza party together at the marble kitchen counter.
- Both characters have gentle, genuine, warm smiles with loving expressive eyes, sharing a sweet and happy family moment.
- They are physically holding and interacting naturally with 4 slices of cheesy, freshly baked pizza on a wooden board on the counter.

COMPOSITION & FRAMING:
- Position BOTH characters centered in the frame (medium chest-up shot showing heads, shoulders, hands, and chest).
- Generous space around them with a detailed kitchen background (cabinets, window, utensils) visible above, behind, and beside them.

STYLE & LIGHTING:
- Ultra-realistic, bright warm lighting, highly vibrant and cheerful colours for a Grade 1 storybook.
- BACKGROUND FOCUS: Crystal clear, fully sharp background focus. Absolutely NO background blur, NO bokeh blur, NO shallow depth of field. Every kitchen detail must be in crisp focus.

CRITICAL CONSTRAINTS:
- STRICTLY TWO CHARACTERS ONLY: 1 child (5-6 years old) and 1 mother. NO extra people or children.
- Gentle, warm, genuine smiles with friendly expressive eyes.
- Exactly 4 clearly separated, countable slices of pizza visible on the board and in hands.
- Both characters centered with ample visible background.
- Crisp clear focus throughout — NO background blur.
- No text, no numbers, no words.
- Image size: 1024x1024 pixels square.
""".strip()
    },
    {
        "id": "kitchen_ice_cream_father_child",
        "food": "Ice cream",
        "item_description": "3 colourful waffle cone ice creams with scoops of strawberry and vanilla",
        "item_count": 3,
        "family": "father_child",
        "face_slots": ["child", "father_name"],
        "scene_prompt": """
Create a photorealistic image of EXACTLY TWO CHARACTERS: a young boy (Grade 1 student, exactly 5-6 years old) and his father in a sunlit modern kitchen.

EXPRESSION & INTERACTION:
- They are cheerfully enjoying colourful ice cream waffle cones together.
- Gentle, genuine, warm smiles with a loving, joyful look and sparkling, friendly eyes.
- There are exactly 3 colourful ice cream waffle cones being held in their hands and on a stand on the counter.

COMPOSITION & FRAMING:
- Position BOTH characters centered in the frame (medium chest-up shot).
- Ample breathing room and a detailed kitchen background (wooden cabinets, window light, kitchen plants) visible all around them.

STYLE & LIGHTING:
- Ultra-realistic, bright, warm, colourful and cheerful.
- BACKGROUND FOCUS: Crystal clear, fully sharp focus. NO background blur, NO bokeh blur. Every kitchen detail is sharp.

CRITICAL CONSTRAINTS:
- STRICTLY TWO CHARACTERS ONLY: 1 child (5-6 years old) and 1 father. NO extra people.
- Gentle, genuine, warm smiles with expressive eyes.
- Exactly 3 distinct, countable ice cream cones held clearly.
- Characters centered in frame.
- Crisp clear background focus — NO blur.
- No text, no numbers.
- Image size: 1024x1024 pixels square.
""".strip()
    },
    {
        "id": "kitchen_apples_mother_child",
        "food": "Apples",
        "item_description": "4 shiny, bright red fresh apples",
        "item_count": 4,
        "family": "mother_child",
        "face_slots": ["child", "mother_name"],
        "scene_prompt": """
Create a photorealistic image of EXACTLY TWO CHARACTERS: a young boy (Grade 1 student, exactly 5-6 years old) and his mother in a bright modern kitchen.

EXPRESSION & INTERACTION:
- They are preparing fresh healthy fruit snacks at the kitchen counter.
- Both characters have soft, genuine, warm smiles with a loving, caring look and bright happy eyes.
- They are physically holding and arranging 4 shiny, bright red fresh apples on the counter and in a wooden bowl.

COMPOSITION & FRAMING:
- Centered medium chest-up shot showing both characters in the middle of the frame.
- Spacious composition with detailed kitchen background (cabinets, window, kitchen accessories) visible all around.

STYLE & LIGHTING:
- Ultra-realistic, vibrant bright colours, warm friendly lighting.
- BACKGROUND FOCUS: Completely crisp, sharp background focus. NO background blur, NO bokeh.

CRITICAL CONSTRAINTS:
- STRICTLY TWO CHARACTERS ONLY: 1 child (5-6 years old) and 1 mother. NO extra people.
- Gentle, warm smiles with loving, friendly eyes.
- Exactly 4 shiny red apples clearly visible and countable on counter and in hands.
- Characters centered in frame.
- Sharp clear background throughout — NO blur.
- No text, no words.
- Image size: 1024x1024 pixels square.
""".strip()
    },
    {
        "id": "kitchen_burgers_father_child",
        "food": "Burgers",
        "item_description": "3 delicious mini burgers with cheese and lettuce on wooden plates",
        "item_count": 3,
        "family": "father_child",
        "face_slots": ["child", "father_name"],
        "scene_prompt": """
Create a photorealistic image of EXACTLY TWO CHARACTERS: a young boy (Grade 1 student, exactly 5-6 years old) and his father gathered at the kitchen counter.

EXPRESSION & INTERACTION:
- They are enjoying freshly prepared mini burgers together.
- Genuine, gentle, warm smiles with a sweet loving look and bright expressive eyes.
- Holding and interacting with 3 delicious mini burgers on wooden plates on the kitchen island.

COMPOSITION & FRAMING:
- Centered medium chest-up composition showing both characters in the middle of the frame.
- Ample room around them showing the detailed, vibrant kitchen background.

STYLE & LIGHTING:
- Ultra-realistic, bright warm lighting, highly colourful.
- BACKGROUND FOCUS: Fully sharp, crystal clear background focus. NO background blur, NO bokeh.

CRITICAL CONSTRAINTS:
- STRICTLY TWO CHARACTERS ONLY: 1 child (5-6 years old) and 1 father. NO extra people.
- Soft, gentle, warm smiles with friendly eyes.
- Exactly 3 mini burgers clearly visible on plates and held in hands.
- Characters centered in frame with spacious background.
- Crisp sharp background focus — NO blur.
- No text, no numbers.
- Image size: 1024x1024 pixels square.
""".strip()
    },
    {
        "id": "kitchen_baking_cookies_mother_child",
        "food": "Cookies",
        "item_description": "4 freshly baked chocolate chip cookies on a baking sheet",
        "item_count": 4,
        "family": "mother_child",
        "face_slots": ["child", "mother_name"],
        "scene_prompt": """
Create a photorealistic image of EXACTLY TWO CHARACTERS: a young boy (Grade 1 student, exactly 5-6 years old) and his mother in a flour-dusted, bright modern kitchen.

OUTFITS & WARM EXPRESSIONS:
- They are wearing matching cute white chef hats and aprons, baking cookies together.
- Gentle, warm smiles with a loving, sweet look and bright happy eyes.
- They are physically holding and placing 4 freshly baked golden chocolate chip cookies on a baking sheet on the counter.

COMPOSITION & FRAMING:
- Position BOTH characters centered in the frame (medium chest-up shot).
- Generous space around them with detailed kitchen background (cabinets, oven, rolling pin, mixing bowl) visible in sharp focus.

STYLE & LIGHTING:
- Ultra-realistic, bright cheerful lighting, vibrant colours.
- BACKGROUND FOCUS: Crystal clear, fully sharp background focus. NO background blur, NO bokeh.

CRITICAL CONSTRAINTS:
- STRICTLY TWO CHARACTERS ONLY: 1 child (5-6 years old) and 1 mother.
- Soft, gentle, warm smiles with loving eyes.
- Exactly 4 clearly separated, countable chocolate chip cookies visible on the sheet and in hands.
- Characters centered in frame.
- Crisp clear focus throughout — NO blur.
- No text, no words.
- Image size: 1024x1024 pixels square.
""".strip()
    },
    {
        "id": "kitchen_making_chocolates_father_child",
        "food": "Chocolates",
        "item_description": "4 delicious gourmet chocolate truffles on a decorative plate",
        "item_count": 4,
        "family": "father_child",
        "face_slots": ["child", "father_name"],
        "scene_prompt": """
Create a photorealistic image of EXACTLY TWO CHARACTERS: a young boy (Grade 1 student, exactly 5-6 years old) and his father in a warm, modern kitchen.

OUTFITS & WARM EXPRESSIONS:
- They are wearing chef aprons, making homemade chocolate treats together.
- Genuine, warm smiles with a loving look and friendly, happy eyes.
- Holding and arranging 4 delicious, glossy chocolate truffles on a marble serving tray on the counter.

COMPOSITION & FRAMING:
- Position BOTH characters centered in the frame (medium chest-up shot).
- Spacious composition with rich kitchen background details (cabinets, chocolate bowls, window light) visible all around.

STYLE & LIGHTING:
- Ultra-realistic, warm vibrant lighting, rich colourful details.
- BACKGROUND FOCUS: Crystal clear, sharp background focus. NO background blur, NO bokeh.

CRITICAL CONSTRAINTS:
- STRICTLY TWO CHARACTERS ONLY: 1 child (5-6 years old) and 1 father.
- Gentle, warm, genuine smiles with friendly eyes.
- Exactly 4 distinct, countable chocolate truffles visible on tray and in hands.
- Characters centered in frame.
- Crisp clear background focus — NO blur.
- No text, no numbers.
- Image size: 1024x1024 pixels square.
""".strip()
    },
    {
        "id": "kitchen_pancake_breakfast_grandfather_child",
        "food": "Pancakes",
        "item_description": "3 fluffy pancake stacks drizzled with maple syrup",
        "item_count": 3,
        "family": "grandfather_child",
        "face_slots": ["child", "grandfather_name"],
        "scene_prompt": """
Create a photorealistic image of EXACTLY TWO CHARACTERS: a young boy (Grade 1 student, exactly 5-6 years old) and his grandfather in a sunlit kitchen.

WARM EXPRESSION & INTERACTION:
- They are preparing morning breakfast pancakes together.
- Warm, gentle, loving smiles with affectionate friendly eyes.
- Holding and serving 3 fluffy pancake stacks drizzled with maple syrup on ceramic plates.

COMPOSITION & FRAMING:
- Centered medium chest-up composition showing grandfather and child in the middle of the shot.
- Ample space around them showing bright kitchen background (cabinets, toaster, fruit basket, window sunshine).

STYLE & LIGHTING:
- Ultra-realistic, bright warm morning sunshine, vibrant colours.
- BACKGROUND FOCUS: Crystal clear, fully sharp focus. NO background blur, NO bokeh.

CRITICAL CONSTRAINTS:
- STRICTLY TWO CHARACTERS ONLY: 1 child (5-6 years old) and 1 grandfather.
- Gentle, warm, affectionate smiles with friendly eyes.
- Exactly 3 pancake stacks clearly visible on plates/counter.
- Characters centered in frame.
- Sharp clear background focus — NO blur.
- No text, no words.
- Image size: 1024x1024 pixels square.
""".strip()
    },
    {
        "id": "kitchen_making_smoothies_grandmother_child",
        "food": "Smoothies",
        "item_description": "4 vibrant colourful fruit smoothie glasses with straws",
        "item_count": 4,
        "family": "grandmother_child",
        "face_slots": ["child", "grandmother_name"],
        "scene_prompt": """
Create a photorealistic image of EXACTLY TWO CHARACTERS: a young boy (Grade 1 student, exactly 5-6 years old) and his grandmother in a bright modern kitchen.

WARM EXPRESSION & INTERACTION:
- They are making fresh fruit smoothies at the kitchen island counter.
- Soft, gentle, warm smiles with loving, caring eyes.
- Holding and arranging 4 vibrant, colourful fruit smoothie glasses with colourful straws next to fresh berries and fruit slices.

COMPOSITION & FRAMING:
- Centered medium chest-up shot showing grandmother and child in the middle of the frame.
- Generous space showing detailed kitchen background (cabinets, blender, fruit bowl, window).

STYLE & LIGHTING:
- Ultra-realistic, highly vibrant bright colours, warm friendly lighting.
- BACKGROUND FOCUS: Completely crisp, sharp background focus. NO background blur, NO bokeh.

CRITICAL CONSTRAINTS:
- STRICTLY TWO CHARACTERS ONLY: 1 child (5-6 years old) and 1 grandmother.
- Gentle, warm smiles with loving eyes.
- Exactly 4 colourful smoothie glasses clearly visible and countable on counter and in hands.
- Characters centered in frame.
- Crisp clear background focus — NO blur.
- No text, no words.
- Image size: 1024x1024 pixels square.
""".strip()
    }
]

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

def generate_direct_template(tmpl_cfg: dict):
    tmpl_id = tmpl_cfg["id"]
    png_path = OUTPUT_DIR / f"{tmpl_id}.png"
    json_path = OUTPUT_DIR / f"{tmpl_id}.json"

    if png_path.exists() and json_path.exists():
        print(f"  ⏭️ Skipping {tmpl_id} (already exists)")
        return

    print(f"  🎨 Generating warm-smile 2-character direct interaction template for '{tmpl_cfg['food']}' ({tmpl_id})...")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "http://localhost:8502",
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
        return

    img_ref = extract_image_url(resp.json())
    if not img_ref:
        print(f"  ❌ Failed to extract image URL for {tmpl_id}")
        return

    if img_ref.startswith("data:image"):
        img_bytes = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        img_bytes = requests.get(img_ref, timeout=60).content

    with open(png_path, "wb") as f:
        f.write(img_bytes)

    meta = {
        "template_id": tmpl_id,
        "image_file": png_path.name,
        "scene": "kitchen",
        "favorite_food": tmpl_cfg["food"],
        "family": tmpl_cfg["family"].split("_"),
        "face_slots": tmpl_cfg["face_slots"],
        "face_regions": [],
        "objects": [
            {
                "id": 1,
                "type": tmpl_cfg["food"].lower(),
                "count": tmpl_cfg["item_count"],
                "description": tmpl_cfg["item_description"],
                "positions": []
            }
        ],
        "supported_question_types": [
            "counting",
            "positions",
            "visual_search",
            "family_recognition",
            "action_recognition"
        ],
        "prompt": tmpl_cfg["scene_prompt"]
    }

    with open(json_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  ✓ Saved {png_path.name} and {json_path.name}")

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("🚀 Starting Direct Sample Templates Generation (Warm smiling expressions & friendly eyes)...\n")
    
    for tmpl in DIRECT_TEMPLATES:
        generate_direct_template(tmpl)

    print("\n✅ Direct Food & Activity Templates generation finished! Check 'kitchen_scenes/direct_food_templates/'.")

if __name__ == "__main__":
    main()
