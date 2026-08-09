"""
run_direct_pipeline.py
─────────────────────────────────────────────────────────────────────────────
End-to-End Personalisation & Quiz Pipeline for Kitchen Scenes.

WORKFLOW:
  1. Accepts user profile: child name, age, grade, favourite food, relation photos
     (child_photo, mother_photo, father_photo, grandmother_photo, grandfather_photo),
     and an optional image_style ('realistic' [default] or 'cartoon').
  2. Searches template library for matching 'favorite_food'.
  3. If template found:
     - If the user supplied any relation photos, swaps faces for the required
       character slots and blends them seamlessly using AI (`gpt-5.4-image-2`),
       adapting expressions & preserving pose.
       If NO photos were supplied, the template image is used as-is — no
       swap, no AI blend call.
     - If image_style == 'cartoon', converts the resulting image into a
       children's-storybook cartoon style, preserving composition, identity,
       and the exact item count.
     - Generates 5 personalized Grade 1 educational questions using GPT-4o vision,
       grounded in the FINAL (post-style) image so questions always match what's
       printed in the worksheet.
     - Returns the final image as an in-memory PIL.Image and the question set
       as a list of dicts. NOTHING is written to disk — the caller (e.g. the
       Streamlit app) is responsible for embedding the image/questions into
       the worksheet output (PDF) and nowhere else.
  4. If template not found:
     - Displays list of available food templates in the library.

USAGE:
    python -m kitchen_scenes.run_direct_pipeline
    (CLI mode saves a copy to ./pipeline_output/ for manual inspection only —
    this saving happens in main(), never inside run_pipeline() itself.)
"""

import os
import re
import json
import base64
import argparse
import requests
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw, ImageFilter
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TEXT_MODEL  = "openai/gpt-4o"         # for vision question generation
IMAGE_MODEL = "openai/gpt-5.4-image-2"  # for AI face blending / scene finish

DIRECT_TEMPLATES_DIR = Path(__file__).parent / "direct_food_templates"
USER_PHOTOS_DIR = Path(__file__).parent / "sample_characters"

# Only used by the CLI entry point (main()) for optional manual-inspection
# saves. run_pipeline() itself never touches this directory.
CLI_DEBUG_OUTPUT_DIR = Path(__file__).parent / "pipeline_output"

# Keys in a user profile dict that may contain a relation photo path.
_PHOTO_KEYS = (
    "child_photo", "mother_photo", "father_photo",
    "grandmother_photo", "grandfather_photo", "adult_photo",
)

# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT USER SETTINGS — Profile & Relation Photos (CLI/demo use only)
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_USER_SETTINGS = {
    "child_name": "Ali",
    "child_age": 6,
    "grade": 1,
    "favorite_food": "Smoothies",   # E.g. Smoothies, Cookies, Ice cream, Pizza, Apples, Burgers, Chocolates, Pancakes
    "child_photo": USER_PHOTOS_DIR / "new_child.jpg",
    "mother_photo": USER_PHOTOS_DIR / "new_mother.jpg",
    "father_photo": USER_PHOTOS_DIR / "new_father.jpg",
    "grandmother_photo": USER_PHOTOS_DIR / "new_grandmother.jpg",
    "grandfather_photo": USER_PHOTOS_DIR / "grandfather.jpg",
    # Fallback photo if specific relation photo is not specified
    "adult_photo": USER_PHOTOS_DIR / "new_mother.jpg",
}


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE SEARCH & HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _adult_role_from_meta(meta: dict) -> str | None:
    """Extract the adult family role from template metadata (e.g. mother, grandmother)."""
    family = [str(x).strip().lower() for x in (meta.get("family") or []) if str(x).strip().lower() != "child"]
    if family:
        return family[0]
    for slot in meta.get("face_slots") or []:
        slot_l = str(slot).strip().lower()
        if slot_l != "child" and slot_l.endswith("_name"):
            return slot_l.replace("_name", "")
        if slot_l in {"mother", "father", "grandmother", "grandfather"}:
            return slot_l
    return None


def find_template_for_food(
    food: str,
    family_role: str | None = None,
    *,
    require_annotated: bool = True,
) -> tuple[Path, dict] | tuple[None, None]:
    """
    Find a direct food template for a given food name.

    If family_role is provided (e.g. 'mother', 'grandmother'), only templates
    whose adult character matches that role are considered. Prefer annotated
    templates when require_annotated is True.
    """
    if not DIRECT_TEMPLATES_DIR.exists():
        return None, None

    food_l = food.strip().lower()
    role_l = (family_role or "").strip().lower() or None
    candidates: list[tuple[Path, dict, bool]] = []

    for json_path in DIRECT_TEMPLATES_DIR.glob("*.json"):
        try:
            with open(json_path, encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("favorite_food", "").strip().lower() != food_l:
                continue
            png_path = DIRECT_TEMPLATES_DIR / meta["image_file"]
            if not png_path.exists():
                continue
            adult = _adult_role_from_meta(meta)
            if role_l and adult != role_l:
                continue
            annotated = bool(meta.get("annotation_complete")) or len(meta.get("face_regions") or []) > 0
            candidates.append((png_path, meta, annotated))
        except Exception:
            continue

    if not candidates:
        return None, None

    if require_annotated:
        annotated = [c for c in candidates if c[2]]
        if annotated:
            return annotated[0][0], annotated[0][1]
        return None, None

    # Prefer annotated when available, else first match
    candidates.sort(key=lambda c: (not c[2], c[0].name))
    return candidates[0][0], candidates[0][1]


def find_template_for_food_and_role(
    food: str,
    family_role: str,
    *,
    require_annotated: bool = True,
) -> tuple[Path, dict] | tuple[None, None]:
    """Strict food + adult-role template lookup."""
    return find_template_for_food(food, family_role=family_role, require_annotated=require_annotated)


def list_available_templates() -> list[dict]:
    """List all available templates in the direct_food_templates library."""
    available = []
    if not DIRECT_TEMPLATES_DIR.exists():
        return available

    for json_path in sorted(DIRECT_TEMPLATES_DIR.glob("*.json")):
        try:
            with open(json_path, encoding="utf-8") as f:
                meta = json.load(f)
            if "favorite_food" not in meta:
                continue  # skip non-template JSON files that may live in this folder
            adult = _adult_role_from_meta(meta)
            available.append({
                "template_id": meta.get("template_id"),
                "food": meta.get("favorite_food"),
                "family": ", ".join(meta.get("family", [])),
                "adult_role": adult,
                "annotated": meta.get("annotation_complete", False) or len(meta.get("face_regions", [])) > 0,
            })
        except Exception:
            continue
    return available


def list_roles_for_food(food: str, *, annotated_only: bool = True) -> list[str]:
    """Return adult roles available for a food in the template library."""
    roles = []
    for t in list_available_templates():
        if t["food"].strip().lower() != food.strip().lower():
            continue
        if annotated_only and not t.get("annotated"):
            continue
        if t.get("adult_role") and t["adult_role"] not in roles:
            roles.append(t["adult_role"])
    return roles


def crop_face(path: Path) -> Image.Image:
    """
    Portrait-optimised crop: takes a square from the TOP-CENTRE of the image
    (where the face usually sits in portrait photos).
    """
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    s = min(w, h)
    left = (w - s) // 2
    top = max(0, int((h - s) * 0.10))   # 10% bias from top
    return img.crop((left, top, left + s, top + s))


def soft_mask(w: int, h: int, inset: int = 14, blur: int = 22) -> Image.Image:
    """Soft feathered elliptical mask for seamless face insertion."""
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((inset, inset, w - inset, h - inset), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def match_brightness(face: Image.Image, region: Image.Image) -> Image.Image:
    """Adjust face brightness/contrast to match the template region lighting."""
    import numpy as np
    face_arr   = np.array(face.convert("RGB")).astype(float)
    region_arr = np.array(region.convert("RGB")).astype(float)

    for c in range(3):
        f_mean = face_arr[:, :, c].mean() + 1e-5
        r_mean = region_arr[:, :, c].mean() + 1e-5
        face_arr[:, :, c] = face_arr[:, :, c] * (r_mean / f_mean)

    face_arr = np.clip(face_arr, 0, 255).astype(np.uint8)
    result = Image.fromarray(face_arr).convert("RGBA")
    result.putalpha(face.split()[3])
    return result


def has_user_supplied_faces(user_settings: dict) -> bool:
    """
    True only if the caller actually supplied at least one real relation
    photo that exists on disk. Callers (e.g. the Streamlit app) should only
    populate _PHOTO_KEYS with paths the user actually uploaded — no silent
    fallback to sample/demo photos — so this check reflects real intent.
    """
    for key in _PHOTO_KEYS:
        path = user_settings.get(key)
        if path and Path(path).exists():
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# CORE PIPELINE STEPS
# ─────────────────────────────────────────────────────────────────────────────

def swap_faces(template_png: Path, meta: dict, user_settings: dict) -> Image.Image:
    """
    Paste user and relation faces onto annotated template face_regions in memory.
    Dynamically maps relation photos based on template face_slots.
    Only pastes a face for a role if a real photo was supplied for it — roles
    without a supplied photo keep the template's original face untouched.
    """
    canvas = Image.open(template_png).convert("RGBA")
    face_regions = meta.get("face_regions", [])

    if not face_regions:
        print("  ⚠️  No face_regions annotated for this template yet!")
        return canvas

    # Map relation photos flexibly based on slot name — no fallback to
    # sample/demo photos here; only what the caller explicitly supplied.
    photo_map = {
        "child":            user_settings.get("child_photo"),
        "mother_name":      user_settings.get("mother_photo") or user_settings.get("adult_photo"),
        "father_name":      user_settings.get("father_photo") or user_settings.get("adult_photo"),
        "grandfather_name": user_settings.get("grandfather_photo") or user_settings.get("adult_photo"),
        "grandmother_name": user_settings.get("grandmother_photo") or user_settings.get("adult_photo"),
    }

    for region in face_regions:
        role = region["role"]
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        photo_path = photo_map.get(role)

        if not photo_path or not Path(photo_path).exists():
            print(f"  ⏭️  No photo supplied for role '{role}' — keeping template face.")
            continue

        photo_path = Path(photo_path)
        face = crop_face(photo_path).resize((w, h), Image.Resampling.LANCZOS)
        template_region = canvas.crop((x, y, x + w, y + h))
        face = match_brightness(face, template_region)
        mask = soft_mask(w, h)
        canvas.paste(face, (x, y), mask)
        print(f"  ✓ Swapped '{role}' using {photo_path.name} at ({x},{y}) size {w}×{h}")

    return canvas


def stylize_image(image: Image.Image, meta: dict, style: str = "cartoon") -> Image.Image:
    """
    Optional style pass. `soft_cartoon` keeps a mostly-realistic look with a
    mild storybook touch; `cartoon` is a fuller children's picture-book style.

    Preserves composition, identity, and exact food count. On API failure,
    returns the original image unchanged.
    """
    food = meta["favorite_food"]
    count = meta["objects"][0]["count"]
    item_desc = meta["objects"][0]["description"]
    style = (style or "cartoon").strip().lower()

    if style in ("soft_cartoon", "soft", "semi_realistic", "storybook_soft"):
        style_prompt = f"""Restyle this photo into a REALISTIC but gently illustrated look —
like a premium children's storybook cover that still feels almost photographic.

GOAL: mostly realistic, with a mild cartoon / storybook touch. NOT a flat cartoon.

DO:
- Keep natural faces, skin texture, and recognisable identity of both people.
- Soften slightly: warmer cheerful colours, gentle painterly light, mild rounded
  shapes, a touch of storybook charm.
- Keep depth, shadows, and realistic materials (just a bit cleaner / softer).

DO NOT:
- Do NOT turn this into a flat cartoon, clip-art, or bold-outline animation.
- Do NOT Pixar-ify or heavily simplify faces into cartoon characters.
- Do NOT change who the people are, their ages, poses, framing, or background layout.
- Do NOT add or remove objects: keep EXACTLY {count} {item_desc} ({food}) clearly countable.
- No text, numbers, watermarks, or speech bubbles. Square 1024x1024.

Output ONLY the restyled image."""
    else:
        style_prompt = f"""Convert this image into a warm, friendly children's-storybook CARTOON illustration — soft flat colours, clean bold outlines, simplified rounded shapes, gentle shading, like a Grade 1 picture-book illustration. Not photorealistic.

ABSOLUTE CONSTRAINTS:
1. PRESERVE COMPOSITION: Keep the exact same character poses, positions, camera framing, and background layout.
2. PRESERVE IDENTITY: Keep the same two characters — their relative age, hair colour/style, and general appearance — just render them in cartoon style instead of photorealistic.
3. PRESERVE OBJECT COUNT EXACTLY: There must be EXACTLY {count} {item_desc} ({food}) visible and clearly countable in the cartoon version — do not add or remove any.
4. PRESERVE EXPRESSIONS: Keep the same warm, happy smiles and joyful mood.
5. Square 1024x1024. No text, no numbers, no watermarks, no speech bubbles."""

    buffered = BytesIO()
    image.convert("RGB").save(buffered, format="PNG")
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
                {"type": "text", "text": style_prompt},
            ]
        }]
    }

    print(f"  🎨 Converting image to '{style}' style...")
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
        if resp.status_code == 200:
            img_ref = extract_image_url(resp.json())
            if img_ref:
                if img_ref.startswith("data:image"):
                    img_bytes = base64.b64decode(img_ref.split(",", 1)[1])
                else:
                    img_bytes = requests.get(img_ref, timeout=60).content
                print(f"  ✓ '{style}' style image received (in-memory).")
                return Image.open(BytesIO(img_bytes)).convert("RGB")

        print(f"  ⚠️  Stylization response issue ({resp.status_code}). Using realistic image instead.")
    except Exception as e:
        print(f"  ⚠️  Stylization error ({e}). Using realistic image instead.")

    return image.convert("RGB")


def ai_blend_faces(intermediate_image: Image.Image, meta: dict, user_settings: dict) -> Image.Image:
    """
    Pass the face-pasted image to AI image model (`gpt-5.4-image-2`).
    Harmonises lighting & skin tones while adapting facial expressions to
    match the joyful template scene.

    Returns an in-memory PIL.Image — nothing is written to disk here.
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
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
        if resp.status_code == 200:
            img_ref = extract_image_url(resp.json())
            if img_ref:
                if img_ref.startswith("data:image"):
                    img_bytes = base64.b64decode(img_ref.split(",", 1)[1])
                else:
                    img_bytes = requests.get(img_ref, timeout=60).content
                print("  ✓ AI-blended image received (in-memory).")
                return Image.open(BytesIO(img_bytes)).convert("RGB")

        print(f"  ⚠️  AI blend response issue ({resp.status_code}). Using un-blended swapped image.")
    except Exception as e:
        print(f"  ⚠️  AI blend error ({e}). Using un-blended swapped image.")

    return intermediate_image.convert("RGB")


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


def generate_questions(meta: dict, user_settings: dict, image: Image.Image) -> list[dict]:
    """
    Use GPT-4o Vision to generate Grade 1 educational questions for the given
    in-memory image (either the raw template or the face-blended version).
    """
    food = meta["favorite_food"]
    count = meta["objects"][0]["count"]
    item_desc = meta["objects"][0]["description"]
    child_name = user_settings["child_name"]
    adult_roles = [s for s in meta["face_slots"] if s != "child"]
    family_member = adult_roles[0].replace("_name", "").capitalize() if adult_roles else "family member"

    buffered = BytesIO()
    image.convert("RGB").save(buffered, format="PNG")
    b64 = base64.b64encode(buffered.getvalue()).decode()

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

    payload = {
        "model": TEXT_MODEL,
        "max_tokens": 800,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }

    print("  🤖 Calling GPT-4o Vision for question generation...")
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            print(f"  ⚠️  Vision API failed ({resp.status_code}), falling back to text prompt...")
            payload["messages"] = [{"role": "user", "content": prompt}]
            payload["model"] = "openai/gpt-4o-mini"
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)

        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
    except Exception as e:
        print(f"  ❌ Question generation error: {e}")

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


# ─────────────────────────────────────────────────────────────────────────────
# MAIN EXECUTOR & CLI INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(user_profile: dict) -> dict | None:
    """
    Main entry point for running the end-to-end personalization pipeline:
      1. Receives user profile & (optional) relation photos + favorite food.
      2. Finds matching template in direct_food_templates.
      3. Swaps + AI-blends faces ONLY if the user actually supplied photos;
         otherwise uses the template image as-is.
      4. Generates aligned Grade 1 questions for the resulting image.

    Nothing is written to disk. The returned "final_image" is an in-memory
    PIL.Image.Image — the caller decides where it ends up (e.g. embedded
    directly into a worksheet PDF) and it is never persisted as a file
    inside this codebase.
    """
    child_name = user_profile.get("child_name", "Child")
    food = user_profile.get("favorite_food", "").strip()
    family_role = (user_profile.get("family_role") or "").strip().lower() or None

    print("=" * 60)
    print(f"  🚀  KITCHEN SCENES PERSONALISATION PIPELINE")
    role_label = family_role or "any"
    print(f"  👦  Child: {child_name}  |  Favourite Food: {food}  |  Role: {role_label}")
    print("=" * 60)

    # ── STEP 1: Find template for favourite food (+ optional adult role) ─────
    print(f"\n📁 STEP 1 — Searching template library for '{food}'"
          + (f" + '{family_role}'" if family_role else "") + "...")
    tmpl_png, meta = find_template_for_food(food, family_role=family_role)

    if not tmpl_png or not meta:
        print(f"\n  ❌ No annotated template found for favourite food: '{food}'"
              + (f" with role '{family_role}'" if family_role else ""))
        available = list_available_templates()
        if available:
            print(f"  📋 Available templates in library ({len(available)}):")
            for t in available:
                status = "✅ Ready" if t["annotated"] else "⚠️ Needs Annotation"
                print(f"     • {t['food']} ({t['family']}) — {status}")
            if family_role:
                roles = list_roles_for_food(food, annotated_only=False)
                print(f"  💡 Roles present for '{food}' (any annotation state): {roles or 'none'}")
        else:
            print("  ⚠️  Template library is empty.")
        print("\n  💡 Tip: You can generate a template for this food using `run_direct_food_templates.py`.")
        return None

    print(f"  ✓ Found matching template: {tmpl_png.name}")
    print(f"  ✓ Template ID: {meta['template_id']} | Required slots: {meta['face_slots']}")

    # Check annotation status
    face_regions = meta.get("face_regions", [])
    if not face_regions:
        print(f"\n  ⚠️  Template '{tmpl_png.name}' face regions have not been annotated yet.")
        print(f"  💡 Please run annotation tool first:")
        print(f"     python kitchen_scenes/annotate_template.py {tmpl_png}")
        return None

    # ── STEP 2 & 3: Swap + AI-blend faces, ONLY if the user supplied photos ──
    if has_user_supplied_faces(user_profile):
        print(f"\n👤 STEP 2 — Pasting user & relation faces onto template...")
        swapped_image = swap_faces(tmpl_png, meta, user_profile)

        print(f"\n🎨 STEP 3 — AI seamless face blending & expression adaptation...")
        final_image = ai_blend_faces(swapped_image, meta, user_profile)
    else:
        print(f"\n👤 STEP 2/3 — No user photos supplied; using template image as-is (no face swap/blend).")
        final_image = Image.open(tmpl_png).convert("RGB")

    # ── STEP 4: Optional stylization ──────────────────────────────────────────
    image_style = (user_profile.get("image_style") or "realistic").strip().lower()
    if image_style in ("cartoon", "soft_cartoon", "soft", "semi_realistic", "storybook_soft"):
        print(f"\n🖍️  STEP 4 — Converting to '{image_style}' style...")
        final_image = stylize_image(final_image, meta, style=image_style)

    # ── STEP 5: Generate Grade 1 vision-grounded questions ────────────────────
    # Generated from the FINAL image (post style-conversion, if any) so the
    # questions always match exactly what's printed in the worksheet.
    print(f"\n📝 STEP 5 — Generating Grade 1 educational questions for image...")
    questions = generate_questions(meta, user_profile, final_image)

    if questions:
        print_question_report(questions, user_profile, food)

    print(f"\n✅  Pipeline execution completed successfully! (nothing written to disk)")

    return {
        "final_image": final_image,   # PIL.Image.Image — in-memory only
        "questions": questions,
        "metadata": meta,
    }


def main():
    """
    CLI entry point. Unlike run_pipeline(), this DOES save a copy of the
    result to CLI_DEBUG_OUTPUT_DIR for manual inspection — that saving is
    deliberately kept out of run_pipeline() so app-driven runs never persist
    files to disk.
    """
    parser = argparse.ArgumentParser(description="Run Kitchen Scenes Personalisation Pipeline")
    parser.add_argument("--food", type=str, help="Favourite food name (e.g. Smoothies, Cookies, Pizza)")
    parser.add_argument("--name", type=str, help="Child's name")
    parser.add_argument(
        "--style",
        type=str,
        choices=["realistic", "soft_cartoon", "cartoon"],
        default="realistic",
        help="Illustration style: realistic, soft_cartoon (mild storybook), or cartoon",
    )
    args = parser.parse_args()

    user_profile = dict(DEFAULT_USER_SETTINGS)
    if args.food:
        user_profile["favorite_food"] = args.food
    if args.name:
        user_profile["child_name"] = args.name
    user_profile["image_style"] = args.style

    result = run_pipeline(user_profile)
    if not result:
        return

    CLI_DEBUG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    child = user_profile["child_name"].lower()
    tmpl_id = result["metadata"]["template_id"]

    img_path = CLI_DEBUG_OUTPUT_DIR / f"{child}_{tmpl_id}_debug.png"
    result["final_image"].save(img_path)
    print(f"  💾 [CLI debug only] Saved image → {img_path}")

    if result["questions"]:
        q_path = CLI_DEBUG_OUTPUT_DIR / f"{child}_{tmpl_id}_debug_questions.json"
        with open(q_path, "w", encoding="utf-8") as f:
            json.dump(result["questions"], f, indent=2)
        print(f"  💾 [CLI debug only] Saved questions → {q_path}")


if __name__ == "__main__":
    main()