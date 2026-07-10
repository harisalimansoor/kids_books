"""
ai_renderer.py - Step 2 of the Blueprint-to-Render pipeline.

Sends the clean blueprint (shapes only) to OpenRouter for photorealistic
rendering using GPT-5.4 Image 2 (best reasoning + image quality).

Strategy hierarchy:
  1. GPT-5.4 Image 2 (img2img, ~$0.04–0.08/image)
  2. GPT-5.4 Image 2 (text2img fallback, coordinate-rich prompt)
  3. Fallback: blueprint itself
"""

import os
import io
import json
import re
import base64
import requests
from PIL import Image

from config import OPENROUTER_API_KEY, OPENROUTER_URL, IMAGE_STYLES

# ---------------------------------------------------------------------------
# Constants — FLUX.2 Pro as primary (best prompt adherence + img2img support)
# ---------------------------------------------------------------------------
PRIMARY_MODEL = "openai/gpt-5.4-image-2"

# Pricing (per OpenRouter):
#   Input:  $8/M tokens (text) + image input as tokens
#   Output: $15/M tokens (text) + $30/M tokens (image ≈ 1290 tokens)
#   ~1024x1024 image ≈ ~$0.04–0.08/image depending on prompt length

OBJECT_APPEARANCE = {
    "sticker": "flat colourful paper sticker shapes (stars, hearts, animals) lying flat on the surface",
    "book": "distinct rectangular hardcover books with solid bright covers",
    "notebook": "spiral-bound A4 notebooks with lined pages",
    "mango": "large realistic mangoes with yellow-green skin",
    "marble": "small round glass marbles with internal colour swirls",
    "apple": "shiny red apples with a small stem",
    "balloon": "inflated colourful latex balloons tied with string",
    "toy car": "small brightly coloured die-cast toy cars",
    "car": "small brightly coloured die-cast toy cars",
    "shell": "smooth spiral seashells in cream and pink tones",
    "sweet": "individually wrapped colourful candies",
    "candy": "individually wrapped colourful candies",
    "pencil": "standard yellow hexagonal pencils with eraser tips",
    "ball": "brightly coloured bouncy rubber balls",
    "block": "coloured wooden building blocks",
    "cube": "coloured wooden cubes",
    "flower": "brightly coloured flowers with green stems",
    "straw": "straight plastic drinking straws",
    "coin": "shiny round metallic coins",
    "button": "flat round colourful buttons with four holes",
    "bead": "small round colourful beads with a hole through the centre",
    "star": "glittery gold star shapes",
    "heart": "bright red heart shapes",
    "egg": "brown or white chicken eggs",
    "cupcake": "iced cupcakes with a cherry on top",
    "cookie": "round chocolate-chip cookies",
    "biscuit": "round English biscuits",
    "banana": "curved yellow bananas",
    "orange": "round orange citrus fruits",
    "grape": "small round purple or green grapes",
    "cherry": "small round red cherries with stems",
    "strawberry": "red strawberries with green tops",
    "pear": "green or yellow pear-shaped fruits",
    "lemon": "bright yellow oval lemons",
    "lollipop": "round swirled lollipops on a white stick",
    "chocolate": "wrapped chocolate bars",
    "sandwich": "triangular sandwiches",
    "frog": "small green toy frogs",
    "fish": "small orange toy fish",
    "bird": "small colourful toy birds",
    "butterfly": "colourful paper butterflies",
    "ladybird": "small red toy ladybirds with black spots",
    "teddy bear": "small brown teddy bears",
    "doll": "small dressed dolls",
    "robot": "small silver toy robots",
    "train": "small wooden toy trains",
    "bus": "small yellow toy buses",
    "plane": "small white toy aeroplanes",
    "boat": "small wooden toy boats",
    "bicycle": "small toy bicycles",
    "scooter": "small toy scooters",
    "hat": "colourful party hats",
    "cap": "baseball caps",
    "glove": "small knitted gloves",
    "bell": "small gold or silver bells",
    "candle": "tall coloured candles",
    "key": "small metal keys",
    "clock": "small round clocks",
    "ring": "shiny metal rings",
    "bag": "small coloured drawstring bags",
    "bottle": "small plastic water bottles",
    "cup": "coloured plastic cups",
    "plate": "small round paper plates",
    "bowl": "small round plastic bowls",
    "spoon": "small metal spoons",
    "fork": "small metal forks",
    "glass": "small clear drinking glasses",
    # Geometry / shapes
    "triangle": "flat coloured triangular shapes with three straight sides",
    "square": "flat coloured square shapes with four equal sides",
    "rectangle": "flat coloured rectangular shapes with two short and two long sides",
    "circle": "flat coloured round circular shapes",
    "diamond": "flat coloured diamond/rhombus shapes with four angled sides",
    "oval": "flat coloured oval/ellipse shapes",
    "pentagon": "flat coloured pentagon shapes with five straight sides",
    "hexagon": "flat coloured hexagon shapes with six straight sides",
    "octagon": "flat coloured octagon shapes with eight straight sides",
}

ROLE_RENDER_HINTS = {
    "grandmother_name": "an elderly woman with grey/white hair, wearing a cardigan and comfortable clothes",
    "grandfather_name": "an elderly man with grey hair, wearing a jumper and comfortable trousers",
    "mother_name": "a woman in her 30s, wearing a casual top and jeans",
    "father_name": "a man in his 30s, wearing a casual shirt and trousers",
    "sibling_name": "a child aged 7-8, wearing casual clothes",
    "user_name": "a young child aged 5-6, wearing casual clothes",
    "friend_name": "a child of similar age, wearing casual clothes",
    "teacher_name": "a kind teacher wearing smart clothes",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_image(img: Image.Image, fmt: str = "JPEG", quality: int = 92) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format=fmt, quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/{fmt.lower()};base64,{b64}"


def _build_prompt(metadata: dict, preserve_faces: bool = False,
                  gender: str = "Boy", sibling_gender: str = "Boy",
                  theme_style: str = "photorealistic",
                  fav_color: str = "", extra_context: str = "") -> str:
    """
    Build the rendering prompt.

    Parameters
    ----------
    metadata : dict
        Blueprint metadata with character/object positions.
    preserve_faces : bool
        If True, the input image has real face photos pasted at head positions.
    gender : str
        Student's gender ("Boy", "Girl", or "Other").
    sibling_gender : str
        Sibling's gender ("Boy" or "Girl").
    theme_style : str
        Key into IMAGE_STYLES for the visual theme.
    fav_color : str
        Favourite colour to prepend to object descriptions.
    extra_context : str
        Extra contextual text to inject into the scene description.
    """
    scene = metadata.get("scene_context", "a bright indoor room")
    if extra_context:
        scene = f"{scene}. {extra_context}"
    chars = metadata["characters"]
    objs = metadata["objects"]
    total_objects = sum(g["count"] for g in objs)
    theme_desc = IMAGE_STYLES.get(theme_style, IMAGE_STYLES["photorealistic"])

    child_hints = {
        "user_name": {
            "Boy": "a young boy aged 5-6, shown from the chest upward, wearing casual clothes",
            "Girl": "a young girl aged 5-6, shown from the chest upward, wearing casual clothes",
        },
        "sibling_name": {
            "Boy": "a boy aged 7-8, shown from the chest upward, wearing casual clothes",
            "Girl": "a girl aged 7-8, shown from the chest upward, wearing casual clothes",
        },
    }

    char_lines = []
    for c in chars:
        rk = c["role_key"]
        hint = ROLE_RENDER_HINTS.get(rk, "a friendly person")
        # Override role hints based on role-specific gender
        if rk in child_hints:
            role_gender = sibling_gender if rk == "sibling_name" else gender
            if role_gender in child_hints[rk]:
                hint = child_hints[rk][role_gender]
        hx, hy = c["head_center"]["x"], c["head_center"]["y"]
        bx, by = c["body_rect"]["x"], c["body_rect"]["y"]
        char_lines.append(
            f"- {c['label']}: upper body at ({bx},{by}), head at ({hx},{hy}). "
            f"Render as {hint}."
        )

    obj_lines = []
    for og in objs:
        obj_name = og["object"]
        appearance = OBJECT_APPEARANCE.get(obj_name,
                                           f"clearly recognisable {obj_name}s")
        if fav_color:
            appearance = f"{fav_color} {appearance}"
        count = og["count"]
        coords_str = ", ".join(f"({p['x']},{p['y']})" for p in og["positions"])
        obj_lines.append(
            f"- Exactly {count} {obj_name}s at positions: {coords_str}. "
            f"Render as: {appearance}. Each MUST be a DISTINCT, SEPARATE item."
        )

    people_block = "\n".join(char_lines)
    objects_block = "\n".join(obj_lines)

    crossed_match = re.search(r'(\d+)\s+of them are crossed out',
                              metadata.get("raw_question", ""))
    if crossed_match:
        crossed = int(crossed_match.group(1))
        for og in objs:
            if og["count"] >= crossed:
                objects_block += (
                    f"\n\n- IMPORTANT: {crossed} of these {og['count']} {og['object']}s "
                    f"have a LARGE RED 'X' mark drawn through them (crossed out). "
                    f"The remaining {og['count'] - crossed} are normal and untouched."
                )
                break

    mult_match = re.search(r'(\d+)\s+groups?\s+of\s+(\d+)\s+(\w+)',
                           metadata.get("raw_question", ""))
    if mult_match:
        groups = int(mult_match.group(1))
        per_group = int(mult_match.group(2))
        obj = mult_match.group(3)
        objects_block += (
            f"\n\n- IMPORTANT: Arrange these {groups * per_group} {obj}s into "
            f"{groups} clearly separated groups of {per_group} {obj}s each. "
            f"Each group must be visibly apart from the others."
        )

    fraction_info = metadata.get("fraction_info")
    if fraction_info:
        ft = fraction_info["fraction_type"]
        if ft == "half_circled":
            total_objs = sum(g["count"] for g in objs)
            half = total_objs // 2
            objects_block += (
                f"\n\n- IMPORTANT: {half} of these {total_objs} objects have a "
                f"THICK GREEN CIRCULAR OUTLINE drawn around them to show they are circled. "
                f"The remaining {total_objs - half} objects are normal with no outline."
            )
        elif ft == "equal_groups":
            grp = fraction_info["groups"]
            per = fraction_info["per_group"]
            obj_name = fraction_info["object"]
            objects_block += (
                f"\n\n- IMPORTANT: These objects are arranged into {grp} clearly "
                f"separated groups of {per} {obj_name}s each. One group has a "
                f"THICK GREEN CIRCULAR OUTLINE drawn around it to show it is circled."
            )

    if preserve_faces:
        prompt = f"""{theme_desc.upper()} EDUCATIONAL SCENE — STRICT GEOMETRY LOCK — FACE PRESERVATION MODE — CHEST-UP FRAMING

⚠️ STYLE ENFORCEMENT — CRITICAL
The ENTIRE image MUST be rendered in {theme_desc} style.
Every element — characters, objects, background, lighting, textures — MUST follow {theme_style} style strictly.
Do NOT output photorealistic. Do NOT mix styles. The style is {theme_desc} — apply it everywhere.

════════════════════════════════════════════════════════════
COLOR LEGEND — Every colored shape in the input image has a fixed meaning:
════════════════════════════════════════════════════════════
🔵 BLUE RECTANGLES  → Character upper bodies. Convert each ONE into a person's chest and shoulders in {theme_style} style.
                        The face is ALREADY PASTED at the head position — PRESERVE it.
🟢 GREEN OUTLINES   → Real face photos already pasted here. DO NOT MODIFY. Blend into {theme_style} body.
🔴 RED CIRCLES      → Countable objects. Each ONE red circle = ONE separate object rendered in {theme_style} style.
                        Exact count and position must be preserved.
⬜ WHITE BACKGROUND → Add the scene background described below in {theme_style} style.

FAILURE CONDITIONS (these will make the image USELESS for a math worksheet):
- If the pasted faces are modified, altered, or replaced → FAILED
- If red circles are merged into piles → FAILED
- If extra objects are hallucinated → FAILED
- If any object is missing → FAILED
- If the style is photorealistic instead of {theme_style} → FAILED

════════════════════════════════════════════════════════════
CHARACTERS — rendered in {theme_desc} style, preserve pasted faces
════════════════════════════════════════════════════════════
{people_block}

FACES: The faces already pasted in the image MUST be PRESERVED exactly as they appear.
Do NOT modify, alter, replace, or regenerate them. Keep every facial feature identical.
The only exception is blending the edges where the face meets the neck/generated upper body — match the blending to {theme_style} style.

════════════════════════════════════════════════════════════
BLENDING INSTRUCTION — CRITICAL
════════════════════════════════════════════════════════════
For each character:
1. The face is already pasted at the correct position — leave it untouched.
2. Generate the rest of the upper body (neck, shoulders, upper chest, clothing) below the face in {theme_style} style.
3. Blend the edges of the pasted face naturally into the generated body — smooth transition matching {theme_style} aesthetic.
4. Ensure the overall result looks like a single cohesive {theme_style} image, not a collage.

════════════════════════════════════════════════════════════
FRAMING — CHEST-UP PORTRAIT — CRITICAL
════════════════════════════════════════════════════════════
- FRAME each character from the CHEST UPWARD only. Do NOT show legs, feet, or the ground.
- Characters are seen from approximately the mid-chest level to the top of the head.
- Shoulders, neck, and head must be visible and proportioned in {theme_style} style.
- Arms and hands should be visible from the upper arm/shoulder area downward to about mid-forearm.
- Characters should face forward or be slightly angled toward each other.

════════════════════════════════════════════════════════════
OBJECTS — EXACTLY {total_objects} items total, at these exact coordinates
════════════════════════════════════════════════════════════
{objects_block}

════════════════════════════════════════════════════════════
SCENE — {theme_style.upper()} STYLE
════════════════════════════════════════════════════════════
Scene: {scene}

Style: {theme_desc}
- EVERYTHING in {theme_style} style: characters, objects, background, textures
- Lighting, shading, and linework consistent with {theme_style}
- Objects match the {theme_style} aesthetic (proportions, colours, outlines)
- Background is a {theme_style} version of the scene described above
- This is a {theme_style} illustration — NOT a photograph, NOT photorealistic

════════════════════════════════════════════════════════════
COUNT VERIFICATION — MANDATORY
════════════════════════════════════════════════════════════
Before finalizing, COUNT every single object derived from a red circle.
The total MUST be exactly {total_objects}. If not, you made an error — fix it.
Each object must be individually visible and countable by a 5-year-old child.

ABSOLUTE BANS:
❌ Do NOT modify the pasted faces in any way
❌ Do NOT add any objects not represented by red circles
❌ Do NOT draw decorative extra items around the scene
❌ Do NOT place objects in baskets, bowls, piles, or containers
❌ Do NOT show legs, feet, or the ground — chest-up framing only
❌ Do NOT give characters abnormal anatomy, missing limbs, or extra limbs
❌ Do NOT render in photorealistic — strict {theme_style} only
❌ Do NOT mix styles — every element must be {theme_style}"""
    else:
        prompt = f"""{theme_desc.upper()} EDUCATIONAL SCENE — STRICT GEOMETRY LOCK — CHEST-UP FRAMING

⚠️ STYLE ENFORCEMENT — CRITICAL
The ENTIRE image MUST be rendered in {theme_desc} style.
Every element — characters, objects, background, lighting — MUST follow {theme_style} style.
Do NOT output photorealistic. Do NOT mix styles. Strictly {theme_style} only.

════════════════════════════════════════════════════════════
COLOR LEGEND — Every colored shape in the input image has a fixed meaning:
════════════════════════════════════════════════════════════
🔵 BLUE RECTANGLES  → Character upper bodies. Convert each ONE into a person's chest and shoulders
                        in {theme_style} style, with a GENERIC {theme_style} face.
🟢 GREEN CIRCLES    → Head placeholders. REPLACE these circles with {theme_style}-style heads
                        matching each character's description.
🔴 RED CIRCLES      → Countable objects. Each ONE red circle = ONE separate object
                        rendered in {theme_style} style. Exact count and position must be preserved.
⬜ WHITE BACKGROUND → Add the scene background described below in {theme_style} style.

FAILURE CONDITIONS (these will make the image USELESS for a math worksheet):
- If red circles are merged into piles → FAILED
- If extra objects are hallucinated → FAILED
- If any object is missing → FAILED
- If the style is photorealistic instead of {theme_style} → FAILED

════════════════════════════════════════════════════════════
CHARACTERS — rendered in {theme_desc} style with GENERIC FACES
════════════════════════════════════════════════════════════
{people_block}

FACES: Generate GENERIC, ANONYMOUS {theme_style}-style faces for each character.
Do NOT attempt to match any specific identity. The heads should match the {theme_style} aesthetic.

════════════════════════════════════════════════════════════
FRAMING — CHEST-UP PORTRAIT — CRITICAL
════════════════════════════════════════════════════════════
- FRAME each character from the CHEST UPWARD only. Do NOT show legs, feet, or the ground.
- Characters are seen from approximately the mid-chest level to the top of the head.
- Shoulders, neck, and head must be visible and proportioned in {theme_style} style.
- Arms and hands should be visible from the upper arm/shoulder area downward to about mid-forearm.
- Characters should face forward or be slightly angled toward each other.

════════════════════════════════════════════════════════════
OBJECTS — EXACTLY {total_objects} items total, at these exact coordinates
════════════════════════════════════════════════════════════
{objects_block}

════════════════════════════════════════════════════════════
SCENE — {theme_style.upper()} STYLE
════════════════════════════════════════════════════════════
Scene: {scene}

Style: {theme_desc}
- EVERYTHING in {theme_style} style: characters, objects, background, textures
- Lighting, shading, and linework consistent with {theme_style}
- Objects match the {theme_style} aesthetic (proportions, colours, outlines)
- Background is a {theme_style} version of the scene described above
- This is a {theme_style} illustration — NOT a photograph, NOT photorealistic

════════════════════════════════════════════════════════════
COUNT VERIFICATION — MANDATORY
════════════════════════════════════════════════════════════
Before finalizing, COUNT every single object derived from a red circle.
The total MUST be exactly {total_objects}. If not, you made an error — fix it.
Each object must be individually visible and countable by a 5-year-old child.

ABSOLUTE BANS:
❌ Do NOT add any objects not represented by red circles
❌ Do NOT draw decorative extra items around the scene
❌ Do NOT place objects in baskets, bowls, piles, or containers
❌ Do NOT show legs, feet, or the ground — chest-up framing only
❌ Do NOT give characters abnormal anatomy, missing limbs, or extra limbs
❌ Do NOT render in photorealistic — strict {theme_style} only
❌ Do NOT mix styles — every element must be {theme_style}"""

    return prompt


def _build_text_prompt(metadata: dict, gender: str = "Boy",
                       sibling_gender: str = "Boy",
                       theme_style: str = "photorealistic",
                       fav_color: str = "", extra_context: str = "") -> str:
    """Text-only prompt for models that can't accept image input."""
    scene = metadata.get("scene_context", "a bright indoor room")
    if extra_context:
        scene = f"{scene}. {extra_context}"
    chars = metadata["characters"]
    objs = metadata["objects"]
    total = sum(g["count"] for g in objs)
    theme_desc = IMAGE_STYLES.get(theme_style, IMAGE_STYLES["photorealistic"])

    child_hints = {
        "user_name": {
            "Boy": "a young boy aged 5-6, shown from the chest upward, wearing casual clothes",
            "Girl": "a young girl aged 5-6, shown from the chest upward, wearing casual clothes",
        },
        "sibling_name": {
            "Boy": "a boy aged 7-8, shown from the chest upward, wearing casual clothes",
            "Girl": "a girl aged 7-8, shown from the chest upward, wearing casual clothes",
        },
    }

    char_lines = []
    for c in chars:
        hx, hy = c["head_center"]["x"], c["head_center"]["y"]
        bx, by = c["body_rect"]["x"], c["body_rect"]["y"]
        label = c["label"]
        hint = ROLE_RENDER_HINTS.get(c["role_key"], "a friendly person")
        if c["role_key"] in child_hints:
            role_gender = sibling_gender if c["role_key"] == "sibling_name" else gender
            if role_gender in child_hints[c["role_key"]]:
                hint = child_hints[c["role_key"]][role_gender]
        char_lines.append(
            f"{label} at position x={bx}, head at ({hx},{hy}). {hint}."
        )

    obj_lines = []
    for og in objs:
        obj_name = og["object"]
        appearance = OBJECT_APPEARANCE.get(obj_name, f"distinct {obj_name}s")
        if fav_color:
            appearance = f"{fav_color} {appearance}"
        count = og["count"]
        coords = ", ".join(f"({p['x']},{p['y']})" for p in og["positions"])
        obj_lines.append(
            f"Exactly {count} {obj_name}s at positions: {coords}. "
            f"Render as: {appearance}. Each MUST be separate and individually countable."
        )

    objects_block = "\n".join(obj_lines)

    crossed_match = re.search(r'(\d+)\s+of them are crossed out',
                              metadata.get("raw_question", ""))
    if crossed_match:
        crossed = int(crossed_match.group(1))
        for og in objs:
            if og["count"] >= crossed:
                objects_block += (
                    f"\n\n- IMPORTANT: {crossed} of these {og['count']} {og['object']}s "
                    f"have a LARGE RED 'X' mark drawn through them (crossed out). "
                    f"The remaining {og['count'] - crossed} are normal and untouched."
                )
                break

    mult_match = re.search(r'(\d+)\s+groups?\s+of\s+(\d+)\s+(\w+)',
                           metadata.get("raw_question", ""))
    if mult_match:
        groups = int(mult_match.group(1))
        per_group = int(mult_match.group(2))
        obj = mult_match.group(3)
        objects_block += (
            f"\n\n- IMPORTANT: Arrange these {groups * per_group} {obj}s into "
            f"{groups} clearly separated groups of {per_group} {obj}s each. "
            f"Each group must be visibly apart from the others."
        )

    fraction_info = metadata.get("fraction_info")
    if fraction_info:
        ft = fraction_info["fraction_type"]
        if ft == "half_circled":
            total_objs = sum(g["count"] for g in objs)
            half = total_objs // 2
            objects_block += (
                f"\n\n- IMPORTANT: {half} of these {total_objs} objects have a "
                f"THICK GREEN CIRCULAR OUTLINE drawn around them to show they are circled. "
                f"The remaining {total_objs - half} objects are normal with no outline."
            )
        elif ft == "equal_groups":
            grp = fraction_info["groups"]
            per = fraction_info["per_group"]
            obj_name = fraction_info["object"]
            objects_block += (
                f"\n\n- IMPORTANT: These objects are arranged into {grp} clearly "
                f"separated groups of {per} {obj_name}s each. One group has a "
                f"THICK GREEN CIRCULAR OUTLINE drawn around it to show it is circled."
            )

    prompt = f"""{theme_desc.upper()} EDUCATIONAL SCENE — CHEST-UP PORTRAIT — {theme_style.upper()} STYLE ONLY

⚠️ The ENTIRE image MUST be rendered in {theme_desc} style. NOT photorealistic. {theme_style} ONLY.

Scene: {scene}

CHARACTERS (evenly spaced across image, chest-up framing, in {theme_style} style):
{chr(10).join(char_lines)}

OBJECTS — EXACTLY {total} items in {theme_style} style at these coordinates:
{objects_block}

CRITICAL RULES:
- Everything must be {theme_style} style: characters, objects, background, lighting
- Place each character at their specified x-position
- Place objects in front of the corresponding character at the specified coordinates
- EXACTLY {total} objects. Each must be DISTINCT, SEPARATE, and individually countable
- Do NOT merge objects into piles, bowls, baskets, or containers
- Characters face forward, smiling, dressed in appropriate {theme_style} clothing
- FACES: Generate GENERIC, ANONYMOUS faces in {theme_style} style — no specific identity required
- FRAME each character from CHEST UPWARD only — do NOT show legs, feet, or the ground
- Shoulders, neck, and head visible with {theme_style} proportions
- Arms and hands visible from shoulder to mid-forearm
- Style: {theme_desc} — NOT photorealistic, NOT a photograph
- NO photorealistic textures, NO photo-real skin, NO camera-like lighting
- NO extra objects, NO decorative items, NO text or numbers in the image
- COUNT VERIFICATION: Scan the image. Verify exactly {total} objects. If wrong, regenerate."""

    return prompt


# ---------------------------------------------------------------------------
# OpenRouter API calls
# ---------------------------------------------------------------------------

def _call_img2img(image_data_url: str, prompt: str,
                  model: str = PRIMARY_MODEL, strength: float = 0.65) -> str | None:
    """Send image + prompt to OpenRouter for img2img. Returns image URL or None."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501",
        "X-Title": "KidsBook Math App",
    }

    payload = {
        "model": model,
        "modalities": ["image", "text"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": prompt},
            ]
        }],
    }

    try:
        print(f"  [AI] Calling {model} (img2img, strength={strength})...")
        resp = requests.post(OPENROUTER_URL, headers=headers,
                              json=payload, timeout=120)

        if resp.status_code == 200:
            data = resp.json()
            img_url = _extract_image(data)
            if img_url:
                print(f"  [AI] Success!")
                return img_url
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  [AI] No image in response: {str(content)[:200]}")
            return None

        err = resp.text[:300] if resp.text else str(resp.status_code)
        print(f"  [AI] HTTP {resp.status_code}: {err}")
        if "does not support image input" in err.lower() or \
           "cannot read" in err.lower() or resp.status_code == 400:
            return "NEEDS_TEXT"
        return None

    except Exception as e:
        print(f"  [AI] Exception: {e}")
        return "NEEDS_TEXT"


def _call_text2img(prompt: str, model: str) -> str | None:
    """Send text-only prompt to OpenRouter for text-to-image."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501",
        "X-Title": "KidsBook Math App",
    }

    payload = {
        "model": model,
        "modalities": ["image", "text"],
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        print(f"  [AI] Calling {model} (text2img)...")
        resp = requests.post(OPENROUTER_URL, headers=headers,
                              json=payload, timeout=120)

        if resp.status_code == 200:
            data = resp.json()
            img_url = _extract_image(data)
            if img_url:
                print(f"  [AI] Success!")
                return img_url
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  [AI] No image: {str(content)[:200]}")
            return None

        print(f"  [AI] HTTP {resp.status_code}: {resp.text[:300]}")
        return None

    except Exception as e:
        print(f"  [AI] Exception: {e}")
        return None


def _extract_image(data: dict) -> str | None:
    """Extract image URL or base64 from OpenRouter response."""
    message = data.get("choices", [{}])[0].get("message", {})
    images = message.get("images", [])
    if images and isinstance(images, list):
        url = images[0].get("image_url", {}).get("url")
        if url:
            return url
    content = message.get("content", "")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "image_url":
                    return block.get("image_url", {}).get("url")
                txt = block.get("text", "")
                if txt.startswith("data:image"):
                    return txt
    if isinstance(content, str) and content.startswith("data:image"):
        return content
    return None


def _download_image(image_url: str, save_path: str) -> bool:
    """Download/save image from URL or base64."""
    if image_url.startswith("data:image"):
        try:
            _, encoded = image_url.split(",", 1)
            img = Image.open(io.BytesIO(base64.b64decode(encoded)))
            img.convert("RGB").save(save_path, format="JPEG", quality=95)
            return True
        except Exception as e:
            print(f"  [AI] Base64 decode error: {e}")
            return False
    try:
        r = requests.get(image_url, timeout=60)
        if r.status_code == 200:
            img = Image.open(io.BytesIO(r.content))
            img.convert("RGB").save(save_path, format="JPEG", quality=95)
            return True
        return False
    except Exception as e:
        print(f"  [AI] Download error: {e}")
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_image(
    pre_composite: Image.Image,
    metadata: dict,
    output_path: str = "rendered_output.jpg",
    strength: float = 0.75,
    preserve_faces: bool = False,
    gender: str = "Boy",
    sibling_gender: str = "Boy",
    theme_style: str = "photorealistic",
    fav_color: str = "",
    pet_name: str = "",
    extra_context: str = "",
) -> str | None:
    """
    Full pipeline: encode → build prompt → call OpenRouter → save.

    Strategy:
      1. img2img with GPT-5.4 Image 2 (best reasoning + image quality)
      2. text2img with GPT-5.4 Image 2 (coordinate-rich prompt fallback)
      3. return None (caller uses pre-composite as fallback)

    When preserve_faces=True, the input image has real face photos pasted at
    head positions. A lower img2img strength is used to avoid altering them.

    Returns path to saved image, or None.
    """
    # Resize for API efficiency
    max_dim = 1024
    if max(pre_composite.size) > max_dim:
        ratio = max_dim / max(pre_composite.size)
        pre_composite = pre_composite.resize(
            (int(pre_composite.width * ratio), int(pre_composite.height * ratio)),
            Image.LANCZOS,
        )

    image_data_url = _encode_image(pre_composite)
    prompt = _build_prompt(metadata, preserve_faces=preserve_faces, gender=gender,
                           sibling_gender=sibling_gender, theme_style=theme_style,
                           fav_color=fav_color, extra_context=extra_context)
    text_prompt = _build_text_prompt(metadata, gender=gender, sibling_gender=sibling_gender,
                                     theme_style=theme_style, fav_color=fav_color,
                                     extra_context=extra_context)

    mode = "face-preservation" if preserve_faces else "generic"
    print(f"  [AI] Image: {pre_composite.size}, Prompt: {len(prompt)}ch [{mode}]")

    # ── Strategy 1: img2img with GPT-5.4 Image 2 ──
    # Lower strength preserves pasted faces better
    img2img_strength = strength if not preserve_faces else min(strength, 0.4)
    result_url = _call_img2img(image_data_url, prompt, model=PRIMARY_MODEL, strength=img2img_strength)

    # ── Strategy 2: text2img with GPT-5.4 Image 2 (if img2img fails) ──
    if not result_url or result_url == "NEEDS_TEXT":
        result_url = _call_text2img(text_prompt, model=PRIMARY_MODEL)

    # ── Save ──
    if result_url and result_url != "NEEDS_TEXT":
        if _download_image(result_url, output_path):
            print(f"  [AI] Saved: {output_path}")
            return output_path

    print(f"  [AI] All approaches failed.")
    return None


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from blueprint_generator import generate_blueprint
    from asset_processor import prepare_pre_composite

    test_q = ("Look at the picture! {grandmother_name} is holding 2 stickers, "
              "{mother_name} has 5 stickers on the table, "
              "and you are showing 2 stickers. How many stickers can you count altogether?")
    blueprint, meta = generate_blueprint(test_q)
    blueprint.save("test_blueprint.png")

    face_map = {}
    if os.path.exists("personalised_faces"):
        for f in os.listdir("personalised_faces"):
            if f.endswith((".png", ".jpg", ".jpeg")):
                rk = os.path.basename(f).replace("_face.png", "").replace("_face.jpg", "")
                rm = {"user": "user_name", "mother": "mother_name",
                      "grandmother": "grandmother_name", "father": "father_name",
                      "grandfather": "grandfather_name", "sibling": "sibling_name"}
                if rk in rm:
                    face_map[rm[rk]] = os.path.join("personalised_faces", f)

    pre_comp = prepare_pre_composite(blueprint, meta, face_map)
    pre_comp.save("test_pre_composite.png")

    result = render_image(pre_comp, meta, "test_rendered.jpg")
    if result:
        print(f"Rendered: {result}")
    else:
        print("All rendering failed.")
