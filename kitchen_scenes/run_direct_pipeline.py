"""
run_direct_pipeline.py
─────────────────────────────────────────────────────────────────────────────
End-to-End Demo Pipeline for the Direct Food Interaction Template approach.

Pipeline Steps:
  1. Load a direct food template (e.g. kitchen_pizza_mother_child)
  2. Swap in user face photos (child + adult)
  3. Generate Grade 1 questions aligned to the image (counting, family, action)
  4. Display a clean summary of the question set

USAGE:
    python -m kitchen_scenes.run_direct_pipeline

Configure USER_SETTINGS below to simulate different users.
"""

import os
import re
import json
import base64
import requests
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw, ImageFilter
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TEXT_MODEL  = "openai/gpt-4o"         # for question generation
IMAGE_MODEL = "openai/gpt-5.4-image-2"  # for AI face blending

DIRECT_TEMPLATES_DIR = Path(__file__).parent / "direct_food_templates"
OUTPUT_DIR = Path(__file__).parent / "pipeline_output"
USER_PHOTOS_DIR = Path(__file__).parent / "sample_characters"

# ─────────────────────────────────────────────────────────────────────────────
# USER SETTINGS — simulating a child's personalised profile
# ─────────────────────────────────────────────────────────────────────────────
USER_SETTINGS = {
    "child_name": "Ali",
    "child_age": 6,
    "grade": 1,
    "favorite_food": "Smoothies",   # Selects kitchen_making_smoothies_grandmother_child template
    "mother_name": "Sara",
    "father_name": "Ahmed",
    "grandmother_name": "Fatima",
    "child_photo": USER_PHOTOS_DIR / "new_child.jpg",
    "adult_photo": USER_PHOTOS_DIR / "new_grandmother.jpg",  # used for grandmother slot
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def find_template_for_food(food: str) -> tuple[Path, dict] | None:
    """Find the best matching direct food template for a given food."""
    for json_path in DIRECT_TEMPLATES_DIR.glob("*.json"):
        with open(json_path) as f:
            meta = json.load(f)
        if meta.get("favorite_food", "").lower() == food.lower():
            png_path = DIRECT_TEMPLATES_DIR / meta["image_file"]
            if png_path.exists():
                return png_path, meta
    return None, None


def crop_face(path: Path) -> Image.Image:
    """
    Portrait-optimised crop: takes a square from the TOP-CENTRE of the image
    (where the face usually sits in portrait photos), then resizes to target.
    """
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    s = min(w, h)
    # Bias upward — top-centre crop captures face + forehead better
    left   = (w - s) // 2
    top    = max(0, int((h - s) * 0.10))   # 10% from top instead of 25%
    return img.crop((left, top, left + s, top + s))


def soft_mask(w: int, h: int, inset: int = 14, blur: int = 22) -> Image.Image:
    """
    Soft feathered elliptical mask — larger ellipse, tighter inset,
    heavy Gaussian blur for invisible edges.
    """
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((inset, inset, w - inset, h - inset), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def match_brightness(face: Image.Image, region: Image.Image) -> Image.Image:
    """
    Adjust face brightness/contrast to roughly match the template region
    so the pasted face doesn't look too dark or washed out.
    """
    import numpy as np
    face_arr   = np.array(face.convert("RGB")).astype(float)
    region_arr = np.array(region.convert("RGB")).astype(float)

    # Per-channel mean normalisation
    for c in range(3):
        f_mean = face_arr[:, :, c].mean() + 1e-5
        r_mean = region_arr[:, :, c].mean() + 1e-5
        face_arr[:, :, c] = face_arr[:, :, c] * (r_mean / f_mean)

    face_arr = np.clip(face_arr, 0, 255).astype(np.uint8)
    result = Image.fromarray(face_arr).convert("RGBA")
    # Restore original alpha
    result.putalpha(face.split()[3])
    return result


def swap_faces(template_png: Path, meta: dict, user_settings: dict, out_path: Path) -> bool:
    """Paste user faces carefully into annotated face_regions with brightness matching."""
    canvas = Image.open(template_png).convert("RGBA")
    face_regions = meta.get("face_regions", [])

    if not face_regions:
        print("  ⚠️  No face_regions annotated yet — saving template as-is.")
        canvas.convert("RGB").save(out_path)
        return True

    photo_map = {
        "child":           Path(user_settings["child_photo"]),
        "mother_name":     Path(user_settings["adult_photo"]),
        "father_name":     Path(user_settings["adult_photo"]),
        "grandfather_name": Path(user_settings["adult_photo"]),
        "grandmother_name": Path(user_settings["adult_photo"]),
    }

    for region in face_regions:
        role = region["role"]
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        photo = photo_map.get(role)

        if not photo or not photo.exists():
            print(f"  ⚠️  No photo found for '{role}' at {photo}")
            continue

        # 1. Crop face from user photo
        face = crop_face(photo).resize((w, h), Image.Resampling.LANCZOS)

        # 2. Sample the template region for brightness reference
        template_region = canvas.crop((x, y, x + w, y + h))

        # 3. Normalise face brightness to blend naturally
        face = match_brightness(face, template_region)

        # 4. Build a soft feathered elliptical mask
        mask = soft_mask(w, h)

        # 5. Paste with mask
        canvas.paste(face, (x, y), mask)
        print(f"  ✓ Swapped '{role}' face at ({x},{y}) size {w}×{h} — brightness matched")

    return canvas


def image_to_base64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def ai_blend_faces(intermediate_image: Image.Image, meta: dict, user_settings: dict, blended_path: Path) -> Path | None:
    """
    Send the intermediate face-pasted image to the AI image model.
    Ask it to seamlessly integrate the pasted faces into the scene
    so they look naturally lit, blended, and photorealistic.
    """
    food = meta["favorite_food"]
    family_desc = ", ".join(meta.get("family", []))

    blend_prompt = f"""This image shows a kitchen scene with {family_desc} enjoying {food} together. The faces have just been swapped.

CRITICAL TASK: Blend the new faces seamlessly into the scene AND adapt their facial expressions to be extremely happy and joyful.

ABSOLUTE CONSTRAINTS:
1. ADAPT EXPRESSIONS: Change the facial expressions of the new faces to match the huge, laughing, candid, warm smiles and expressive eyes expected in this joyful scene. The characters should look incredibly happy and delighted.
2. PRESERVE FACE ANGLES: Keep the exact head pose, rotation, and chin positioning.
3. SEAMLESS BLENDING: Harmonise the skin tones, lighting, and edges so the faces look naturally attached to the bodies. Fix any harsh cut-lines around the chin and forehead.
4. PRESERVE IDENTITY: While making them smile and laugh, maintain the recognizable facial identity of the pasted faces.
5. PRESERVE EVERYTHING ELSE: Do not alter the background, clothes, food, or any other part of the image. Keep it 1024x1024 photorealistic."""

    buffered = BytesIO()
    intermediate_image.convert("RGB").save(buffered, format="PNG")
    b64 = base64.b64encode(buffered.getvalue()).decode()

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8502",
    }
    payload = {
        "model": IMAGE_MODEL,
        "modalities": ["image", "text"],
        "max_tokens": 1200,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": blend_prompt},
            ]
        }]
    }

    print("  🎨 Sending to AI image model for seamless face blending...")
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)

    if resp.status_code != 200:
        print(f"  ❌ AI blend failed ({resp.status_code}): {resp.text[:200]}")
        print("  ⚠️  Using intermediate (unblended) image instead.")
        intermediate_image.convert("RGB").save(blended_path)
        return blended_path

    img_ref = extract_image_url(resp.json())
    if not img_ref:
        print("  ❌ No image returned from AI blend.")
        intermediate_image.convert("RGB").save(blended_path)
        return blended_path

    if img_ref.startswith("data:image"):
        img_bytes = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        img_bytes = requests.get(img_ref, timeout=60).content

    with open(blended_path, "wb") as f:
        f.write(img_bytes)

    print(f"  ✓ AI-blended image saved → {blended_path.name}")
    return blended_path


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


def generate_questions(meta: dict, user_settings: dict, image_path: Path) -> list[dict]:
    """Use GPT-4o to generate Grade 1 questions from the image and metadata."""
    food = meta["favorite_food"]
    count = meta["objects"][0]["count"]
    item_desc = meta["objects"][0]["description"]
    child_name = user_settings["child_name"]
    adult_roles = [s for s in meta["face_slots"] if s != "child"]
    family_member = adult_roles[0].replace("_name", "").capitalize() if adult_roles else "adult"

    b64 = image_to_base64(image_path)

    prompt = f"""You are a Grade 1 teacher creating personalised educational questions for a 5-6 year old child named {child_name}.

The image shows {child_name} and his {family_member} in a kitchen together with {item_desc}.

Generate EXACTLY 5 different Grade 1 questions for this image. Each question must:
- Be very simple, age-appropriate, and friendly for a 5-6 year old
- Use {child_name}'s name in the question to make it personal
- Be based on what is visible in the image

Generate these 5 question types in order:
1. COUNTING: How many {food.lower()} can you count?
2. FAMILY RECOGNITION: Who is with {child_name} in the kitchen?
3. ACTION RECOGNITION: What are {child_name} and his {family_member} doing?
4. COMPARISON: Are there more than 2 {food.lower()} in the picture?
5. FAVOURITE FOOD: What is {child_name}'s favourite food in the picture?

Return ONLY a valid JSON array like this:
[
  {{
    "question_type": "counting",
    "question": "...",
    "correct_answer": "...",
    "options": ["...", "...", "...", "..."]
  }},
  ...
]

Use count={count} as the correct answer for the counting question.
"""

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8502",
    }

    # Try vision model first for image-grounded questions
    payload = {
        "model": TEXT_MODEL,
        "max_tokens": 800,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
    }

    print("  🤖 Calling GPT-4o for question generation...")
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)

    if resp.status_code != 200:
        print(f"  ⚠️  Vision API failed ({resp.status_code}), falling back to text-only...")
        payload["messages"] = [{"role": "user", "content": prompt}]
        payload["model"] = "openai/gpt-4o-mini"
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)

    if resp.status_code != 200:
        print(f"  ❌ Question generation failed: {resp.text[:200]}")
        return []

    content = resp.json()["choices"][0]["message"]["content"]
    # Extract JSON from the response
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if not match:
        print("  ❌ Could not parse JSON from response.")
        print("  Raw response:", content[:400])
        return []

    try:
        questions = json.loads(match.group(0))
        return questions
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parse error: {e}")
        return []


def print_question_report(questions: list[dict], user_settings: dict, food: str):
    """Pretty-print the generated question set."""
    child = user_settings["child_name"]
    print("\n" + "═" * 60)
    print(f"  📚  GRADE 1 QUESTION SET FOR {child.upper()}")
    print(f"  🍽️   Template: {food} Kitchen Scene")
    print("═" * 60)
    for i, q in enumerate(questions, 1):
        print(f"\n  Q{i}. [{q.get('question_type', '').upper()}]")
        print(f"     ❓ {q.get('question', '')}")
        if q.get("options"):
            for j, opt in enumerate(q["options"], 1):
                marker = "✅" if opt == q.get("correct_answer") else "  "
                print(f"     {marker} {chr(64+j)}) {opt}")
        else:
            print(f"     ✅ Answer: {q.get('correct_answer', '')}")
    print("\n" + "═" * 60)


def save_question_set(questions: list[dict], user_settings: dict, meta: dict, out_path: Path):
    """Save the questions as a JSON file."""
    output = {
        "child_name": user_settings["child_name"],
        "grade": user_settings["grade"],
        "favorite_food": meta["favorite_food"],
        "template_id": meta["template_id"],
        "object_count": meta["objects"][0]["count"],
        "questions": questions
    }
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  💾 Saved question set → {out_path.name}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    user = USER_SETTINGS
    food = user["favorite_food"]

    print("=" * 60)
    print(f"  🚀  DIRECT FOOD TEMPLATE PIPELINE")
    print(f"  👦  Child: {user['child_name']}  |  Food: {food}")
    print("=" * 60)

    # ── STEP 1: Find matching template ────────────────────────────────────────
    print(f"\n📁 STEP 1 — Finding template for '{food}'...")
    tmpl_png, meta = find_template_for_food(food)
    if not tmpl_png:
        print(f"  ❌ No template found for '{food}'. Please generate one first.")
        return
    print(f"  ✓ Found template: {tmpl_png.name}")

    # ── STEP 2: Face swapping (paste) ─────────────────────────────────────────
    print(f"\n👤 STEP 2 — Pasting faces onto template...")
    swapped_image = swap_faces(tmpl_png, meta, user, None)

    # ── STEP 2b: AI face blending ─────────────────────────────────────────────
    print(f"\n🎨 STEP 2b — AI seamless face blending...")
    final_img_path = OUTPUT_DIR / f"{user['child_name'].lower()}_{meta['template_id']}_blended.png"
    final_img_path = ai_blend_faces(swapped_image, meta, user, final_img_path)

    print(f"\n✅  Pipeline complete!")
    print(f"   ✨  AI-blended final image     → {final_img_path}")


if __name__ == "__main__":
    main()
