"""
compositor.py
─────────────────────────────────────────────────────────────────────────────
Compose a final worksheet image from:
  - a kitchen/hobby ROLE template (white placeholder boxes + face regions)
  - user face photos via the shared kitchen face pipeline
    (paste → AI adult blend → AI child blend → degreen) — same as new_pipeline
  - an OBJECT spec (food/hobby/pet) that defines hand interaction style

Pipeline: kitchen faces → paste objects → AI finish (objects + style)
"""

from __future__ import annotations

import base64
import json
import os
import re
from io import BytesIO
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFilter

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
IMAGE_MODEL = (
    os.getenv("PERSONALIZE_IMAGE_MODEL", "openai/gpt-5.4-image-2").strip()
    or "openai/gpt-5.4-image-2"
)


# Second image call per scene. Costs extra credits, so it can be turned off
# with FACE_BLEND_PASS=0 without changing anything else in the pipeline.
FACE_BLEND_PASS = os.getenv("FACE_BLEND_PASS", "1").strip().lower() not in {"0", "false", "no"}

PACKAGE_DIR = Path(__file__).parent
SCENES_DIR = PACKAGE_DIR / "scenes"
OBJECTS_DIR = PACKAGE_DIR / "objects"
ASSETS_DIR = PACKAGE_DIR / "assets"


def load_object_spec(object_id: str, category: str | None = None) -> dict:
    """Load object interaction JSON by id, optionally scoped to a category."""
    categories = [category] if category else ["food", "hobby", "pet"]
    for cat in categories:
        path = OBJECTS_DIR / cat / f"{object_id}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                spec = json.load(f)
            spec["_category"] = cat
            spec["_spec_path"] = str(path)
            return spec
    # fuzzy: pizza_slice -> pizza, ice-cream -> ice_cream
    normalized = object_id.strip().lower().replace("-", "_").replace(" ", "_")
    for cat in categories:
        for path in (OBJECTS_DIR / cat).glob("*.json"):
            if path.stem == normalized or normalized.startswith(path.stem) or path.stem in normalized:
                with open(path, encoding="utf-8") as f:
                    spec = json.load(f)
                spec["_category"] = cat
                spec["_spec_path"] = str(path)
                return spec
    raise FileNotFoundError(f"No object interaction spec found for '{object_id}'")


def find_role_template(scene_family: str, adult_role: str) -> tuple[Path, dict]:
    role_dir = SCENES_DIR / scene_family / f"{adult_role}_child"
    if not role_dir.exists():
        raise FileNotFoundError(f"No role template directory: {role_dir}")
    jsons = sorted(role_dir.glob("*_interactive.json"))
    if not jsons:
        jsons = sorted(role_dir.glob("*.json"))
    if not jsons:
        raise FileNotFoundError(f"No template JSON in {role_dir}")
    meta_path = jsons[0]
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    png = role_dir / meta.get("image_file", meta_path.with_suffix(".png").name)
    if not png.exists():
        raise FileNotFoundError(f"Template image missing: {png}")
    return png, meta


def list_role_templates(scene_family: str = "kitchen") -> list[dict]:
    family_dir = SCENES_DIR / scene_family
    out = []
    if not family_dir.exists():
        return out
    for role_dir in sorted(family_dir.iterdir()):
        if not role_dir.is_dir():
            continue
        for jp in role_dir.glob("*.json"):
            with open(jp, encoding="utf-8") as f:
                meta = json.load(f)
            out.append({
                "scene_family": scene_family,
                "role_dir": role_dir.name,
                "template_id": meta.get("template_id"),
                "adult_role": next((x for x in meta.get("family", []) if x != "child"), None),
                "annotated": bool(meta.get("face_regions")),
                "path": str(jp),
            })
    return out


def crop_face(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    s = min(w, h)
    left = (w - s) // 2
    top = max(0, int((h - s) * 0.10))
    return img.crop((left, top, left + s, top + s))


def soft_mask(w: int, h: int, inset: int = 14, blur: int = 22) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((inset, inset, w - inset, h - inset), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def _resolve_object_asset(spec: dict) -> Path | None:
    cat = spec.get("_category", "food")
    asset_name = spec.get("asset_file") or f"{spec.get('object_id')}.png"
    candidates = [
        ASSETS_DIR / cat / asset_name,
        ASSETS_DIR / asset_name,
        PACKAGE_DIR.parent / "kitchen_scenes" / "sample_characters" / asset_name,
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _detected_face_regions(meta: dict, template_png: Path | None) -> list[dict]:
    """
    Face regions for the template, detected on demand.

    Templates are AI-generated so each frames its characters differently;
    trusting the generator's approximate boxes made the swap land off-face on
    some templates. Detected boxes are cached back into the JSON.
    """
    regions = meta.get("face_regions") or []
    if meta.get("face_detection") == "yunet" and regions:
        return regions
    if not template_png or not template_png.exists():
        return regions

    try:
        from interactive_templates.face_detect import face_regions_for_template
    except Exception:
        return regions

    slots = meta.get("face_slots") or [r.get("role") for r in regions if r.get("role")]
    detected = face_regions_for_template(template_png, slots)
    if len(detected) < len(slots):
        print(
            f"  ⚠️  Face detection found {len(detected)}/{len(slots)} faces on "
            f"{template_png.name} — using stored regions"
        )
        return regions

    meta["face_regions"] = detected
    meta["face_detection"] = "yunet"
    json_path = template_png.with_suffix(".json")
    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as f:
                stored = json.load(f)
            stored["face_regions"] = detected
            stored["face_detection"] = "yunet"
            stored["annotation_complete"] = True
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(stored, f, indent=2)
        except Exception:
            pass
    return detected


def _resolve_face_photos(photos: dict, adult_role: str) -> tuple[Path | None, Path | None]:
    """Return (child_photo, adult_photo) paths from compositor photos dict."""
    child = (
        photos.get("child")
        or photos.get("child_photo")
        or photos.get("user")
    )
    adult = (
        photos.get(adult_role)
        or photos.get(f"{adult_role}_photo")
        or photos.get("mother")
        or photos.get("father")
        or photos.get("grandmother")
        or photos.get("grandfather")
    )
    child_p = Path(child) if child and Path(child).exists() else None
    adult_p = Path(adult) if adult and Path(adult).exists() else None
    return child_p, adult_p


def _pick_face_regions(meta: dict, adult_role: str, template_png: Path | None) -> tuple[dict | None, dict | None]:
    """Pick child + adult face region dicts from template meta."""
    regions = _detected_face_regions(meta, template_png)
    if not regions:
        return None, None
    by_role = {str(r.get("role") or "").lower(): r for r in regions}
    child = by_role.get("child")
    adult = (
        by_role.get(adult_role)
        or by_role.get(f"{adult_role}_name")
        or by_role.get("adult")
        or by_role.get("mother")
        or by_role.get("father")
    )
    # fallback: any non-child region
    if adult is None:
        for r in regions:
            if str(r.get("role") or "").lower() != "child":
                adult = r
                break
    return child, adult


def paste_faces(
    canvas: Image.Image, meta: dict, photos: dict, template_png: Path | None = None
) -> Image.Image:
    """
    Paste uploaded faces into annotated template regions.

    This is only placement: crop the face from the upload, soft-oval paste into
    the annotated box. Seamless lighting / edge removal is done by the AI blend
    pass that follows.
    """
    photo_map = {
        "child": photos.get("child") or photos.get("child_photo") or photos.get("user"),
        "mother_name": photos.get("mother") or photos.get("mother_photo"),
        "father_name": photos.get("father") or photos.get("father_photo"),
        "grandmother_name": photos.get("grandmother") or photos.get("grandmother_photo"),
        "grandfather_name": photos.get("grandfather") or photos.get("grandfather_photo"),
    }
    regions = _detected_face_regions(meta, template_png)
    if not regions:
        print("  ⚠️  No face regions on template — skipping face swap")
        return canvas

    try:
        from interactive_templates.face_swap import (
            crop_upload_face,
            resize_face_keep_aspect,
            scale_region_for_role,
        )
    except Exception:
        crop_upload_face = None
        resize_face_keep_aspect = None
        scale_region_for_role = lambda r: r  # noqa: E731

    for region in regions:
        role = region["role"]
        path = photo_map.get(role)
        if not path or not Path(path).exists():
            print(f"  ⚠️  No photo uploaded for '{role}' — template face kept")
            continue

        region = scale_region_for_role({**region, "role": role})
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]

        if crop_upload_face is not None:
            face = crop_upload_face(path)
        else:
            face = crop_face(Path(path))
        if face is None:
            print(f"  ⚠️  Could not crop face for '{role}' from {Path(path).name}")
            continue

        # Keep upload feature ratios — never stretch to the box aspect ratio.
        if resize_face_keep_aspect is not None:
            face = resize_face_keep_aspect(face, w, h)
        else:
            face = face.resize((w, h), Image.Resampling.LANCZOS)
        if face.mode != "RGBA":
            face = face.convert("RGBA")
        canvas.paste(face, (x, y), soft_mask(w, h))
        print(f"  ✓ Pasted '{role}' aspect-preserved into region ({w}x{h})")
    return canvas


def placeholder_count_from_meta(meta: dict) -> int:
    """Authoritative visible count = number of object placeholders on the template."""
    groups = meta.get("object_positions") or []
    n_pos = sum(len(g.get("positions") or []) for g in groups)
    if n_pos > 0:
        return n_pos
    return int(meta.get("count") or 0)


def paste_objects(canvas: Image.Image, meta: dict, object_asset: Path, count: int | None = None) -> Image.Image:
    """Paste one object into each placeholder slot (up to count)."""
    obj = Image.open(object_asset).convert("RGBA")
    groups = meta.get("object_positions") or []
    placed = 0
    # Always respect placeholder slots: never paste more than available positions
    max_slots = placeholder_count_from_meta(meta) or 0
    target = count if count is not None else max_slots
    if max_slots:
        target = min(int(target), max_slots)
    for group in groups:
        positions = group.get("positions") or []
        for pos in positions:
            if target and placed >= target:
                break
            sz = int(group.get("size") or 150)
            piece = obj.resize((sz, sz), Image.Resampling.LANCZOS)
            canvas.paste(piece, (int(pos["x"]) - sz // 2, int(pos["y"]) - sz // 2), piece)
            placed += 1
    print(f"  ✓ Placed {placed} object(s) into placeholder slots (target={target})")
    return canvas


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


def _request_image_edit(image: Image.Image, prompt: str, *, label: str) -> Image.Image | None:
    """Send one image + instruction to the image model. None when it fails."""
    if not API_KEY:
        print(f"  ⚠️  {label}: no API key")
        return None

    buf = BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8504",
    }
    payload = {
        "model": IMAGE_MODEL,
        "modalities": ["image", "text"],
        "max_tokens": 1200,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
    }
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    except Exception as exc:
        print(f"  ⚠️  {label} request failed ({exc})")
        return None

    raw = (resp.text or "").strip()
    if resp.status_code != 200:
        hint = raw[:220].replace("\n", " ")
        print(f"  ⚠️  {label} API failed ({resp.status_code}): {hint}")
        if resp.status_code == 402:
            print("  💡 OpenRouter credits are empty — top up at https://openrouter.ai/settings/credits")
        return None

    if not raw:
        print(f"  ⚠️  {label}: empty API response body")
        return None

    try:
        data = resp.json()
    except Exception as exc:
        print(
            f"  ⚠️  {label}: could not parse API JSON ({exc}); "
            f"body starts with: {raw[:160]!r}"
        )
        return None

    img_ref = extract_image_url(data)
    if not img_ref:
        err = ""
        try:
            err = str(
                data.get("error")
                or data.get("choices", [{}])[0].get("message", {}).get("content")
                or ""
            )[:200]
        except Exception:
            pass
        print(f"  ⚠️  {label}: no image returned{(' — ' + err) if err else ''}")
        return None

    try:
        if img_ref.startswith("data:image"):
            img_bytes = base64.b64decode(img_ref.split(",", 1)[1])
        else:
            img_bytes = requests.get(img_ref, timeout=60).content
        return Image.open(BytesIO(img_bytes)).convert("RGB")
    except Exception as exc:
        print(f"  ⚠️  {label}: could not decode image ({exc})")
        return None


def beautify_with_object_interaction(
    image: Image.Image,
    meta: dict,
    object_spec: dict,
    *,
    adult_role: str,
    count: int,
    scene_family: str = "kitchen",
) -> Image.Image:
    """
    AI pass for object interaction and joyful expressions.

    Faces are already blended and identity-locked before this call — this pass
    must not redraw or resize them.
    """
    if not API_KEY:
        print("  ⚠️  No API key — returning intermediate composite without interaction beautify")
        return image.convert("RGB")

    singular = object_spec.get("singular", "item")
    plural = object_spec.get("plural", "items")
    adult = adult_role.replace("_", " ")
    family = (scene_family or meta.get("scene_family") or "kitchen").strip().lower()

    if family == "hobby":
        setting_line = (
            f"The base image shows a child and his {adult} in a bright sunny park "
            "at a picnic table / bench."
        )
        mood_line = "like a happy family playtime / hobby moment outdoors"
        engage_line = "keep both engaged with the hobby objects"
        quality_line = (
            "Sharp park background (grass, trees, soft daylight), natural outdoor lighting, "
            "soft contact shadows on the picnic table."
        )
        photo_kind = "park / hobby worksheet photograph"
    else:
        setting_line = (
            f"The base image shows a child and his {adult} in a bright modern kitchen."
        )
        mood_line = "like a happy family kitchen moment"
        engage_line = "keep both engaged with the food"
        quality_line = (
            "Sharp kitchen background, warm bright lighting, soft contact shadows on the counter."
        )
        photo_kind = "kitchen worksheet photograph"

    prompt = f"""You are finishing a personalised Grade 1 {photo_kind}.

{setting_line}
The two faces have ALREADY been blended into the photograph — they are the correct
people at the correct size. White placeholder boxes / temporary props mark where
the {plural} belong.

YOUR JOB — finish the objects and expressions only:

1. FACES ARE FINAL (do not redo them)
   - Keep BOTH faces exactly as they are: same identity, face shape, eye/nose/mouth
     shape and spacing, age, gender, hairstyle, hair colour, skin tone, and head size
     relative to the neck and shoulders.
   - Preserve the pasted facial feature proportions from the uploaded photos —
     do NOT squash, stretch, slim, widen, or shrink either face.
   - Do NOT redraw, replace, enlarge, shrink, move, or swap the faces.
   - Do NOT restyle hair (no leftover ponytails) or leave template-body skin on arms/hands.
   - You may only gently match leftover seam lighting at the hairline / jaw if needed.
   - Child must stay clearly 5-6 years old; the {adult} must stay the same {adult}.

2. WARM JOYOUS LOOK (critical)
   - Both characters must look warmly joyful: natural open smiles, smiling eyes,
     relaxed cheeks and soft loving expressions, {mood_line}.
   - Adjust expression muscles only — never change who the people are.
   - Mood should feel warm, cheerful, and affectionate — never stiff or neutral.

3. DIRECT OBJECT INTERACTION (critical)
   - There are exactly {count} white placeholder boxes / temporary props in the image.
   - Replace EVERY placeholder with a real {singular}.
   - HARD TOTAL COUNT: the finished photograph must contain EXACTLY {count}
     clearly countable {plural} in the WHOLE image — including anything held in hands,
     offered, or resting on {('the picnic table' if family == 'hobby' else 'the counter')}.
   - If someone holds a {singular}, that held item COUNTS as one of the {count}.
     Do NOT keep {count} on the surface AND also hold an extra one (that would make {count + 1}).
   - Prefer touching, pointing at, or steadying one of the {count} surface {plural}
     rather than inventing a new held {singular}.
   - Do not add a {count + 1}th {singular}. Do not remove any of the {count}.
   - Characters must physically interact with the {plural} — not just stand near them.
   - Object type: {plural}
   - Hold style: {object_spec.get('hold_style', '')}
   - Hand action: {object_spec.get('hand_action', '')}
   - Surface action: {object_spec.get('surface_action', '')}
   - Extra guidance: {object_spec.get('interaction_prompt', '')}
   - Hands, fingers, and wrists must look natural for THIS object specifically.
   - ABSOLUTE COUNT RULE: a Year 1 child counting every visible {singular} must get {count}.

4. SCENE QUALITY
   - {quality_line}
   - No text, numbers, watermarks, or leftover white placeholder boxes.

Output ONLY the final photorealistic image.
"""

    return _request_image_edit(image, prompt, label="Beautify") or image.convert("RGB")


def blend_faces_seamlessly(
    image: Image.Image, *, adult_role: str, scene_family: str = "kitchen"
) -> Image.Image:
    """
    AI pass that turns annotated oval pastes into a seamless photograph.

    Faces are already the correct people in the correct annotated positions.
    This pass only removes cut lines and matches lighting — it is the quality
    step of the face swap.
    """
    if not API_KEY:
        print("  ⚠️  No API key — skipping AI face blend")
        return image.convert("RGB")

    adult = adult_role.replace("_", " ")
    setting = (
        "a sunny outdoor park at a picnic table"
        if (scene_family or "").strip().lower() == "hobby"
        else "a bright modern kitchen"
    )

    prompt = f"""This photograph shows a child and their {adult} in {setting}.

Two faces have been pasted as soft ovals onto the annotated head regions.
They are the CORRECT people in the CORRECT positions and at the CORRECT size.
Their facial feature proportions (eyes, nose, mouth spacing, face width/height)
already match the uploaded photos — keep those ratios EXACTLY.
Your ONLY job is to make those pasted faces look native to this photograph.

DO EXACTLY THIS:
1. REMOVE EVERY HARSH LINE
   - Erase cut-out edges, oval outlines, halos, blur rings, and tone steps
     around the faces — especially at the hairline, ears, jawline, chin and neck.
   - The transition from face skin to neck / ears / hair must be invisible.
2. MATCH LIGHTING AND COLOUR
   - Apply the scene's light direction (highlights and shadows under the chin,
     beside the nose, along the jaw and brow).
   - Keep each pasted person's SKIN TONE from the upload (undertone + depth) on the
     WHOLE body: face, neck, ears, arms, hands, fingers, chest. If the upload is fair,
     the entire body is fair — never a fair face on tanned template arms.
     Recolour limbs to the uploaded face. Do NOT fade the face toward the template body.
   - Faces must not look flatter, brighter, or more glowing than the rest of the photo.
3. MATCH TEXTURE AND HAIR
   - Match the photo's sharpness, film grain and depth of field on the faces.
   - Remove any airbrushed or sticker-like look.
   - Keep each person's hairstyle, hair length, and hair colour from the paste/upload.
     Rebuild the full head silhouette. ERASE leftover template hair (ponytails, pigtails,
     long hair down the back) that is not in the upload. A bob must not keep a ponytail
     behind. Do not restyle into a generic cut.

ABSOLUTELY FORBIDDEN:
   - Do NOT change facial identity, bone structure, face shape, eye shape,
     nose, mouth, eyebrows, age, gender, ethnicity or complexion of either person.
   - Do NOT squash, stretch, slim, widen, or warp facial feature proportions.
   - Do NOT replace either face with a different or generic face.
   - Do NOT swap the two faces with each other.
   - Do NOT move, resize, enlarge or shrink either face — keep the EXACT same
     head size and feature scale as the pasted ovals (no smaller heads).
   - Do NOT beautify, slim, de-age or smooth the faces.
   - Do NOT change clothing, objects, hands, background or composition.

Keep both people looking warmly happy with the smiles they already have.
Output ONLY the corrected photograph.
"""
    result = _request_image_edit(image, prompt, label="Face blend")
    if result is None:
        print("  ⚠️  AI face blend failed — keeping simple paste")
        return image.convert("RGB")
    print("  ✓ Faces AI-blended into the scene")
    return result


def stylize_scene(
    image: Image.Image,
    *,
    style: str,
    object_spec: dict,
    count: int,
) -> Image.Image:
    """
    Optional final style pass.

    - soft_cartoon: gentle storybook soft-cartoon (illustrated, not photoreal)
    - cartoon: fuller children's picture-book cartoon (not photoreal)
    - realistic / anything else: unchanged
    """
    style = (style or "realistic").strip().lower()
    if style in ("", "realistic", "photo", "photorealistic"):
        return image.convert("RGB")

    plural = object_spec.get("plural") or "objects"
    singular = object_spec.get("singular") or "object"
    item_word = plural if count != 1 else singular

    if style in ("soft_cartoon", "soft", "semi_realistic", "storybook_soft"):
        style_prompt = f"""Restyle this into a SOFT CARTOON children's storybook illustration
with a gentle illustrated touch — NOT a real photograph.

GOAL: clearly illustrated Grade 1 storybook art (soft cartoon), while faces stay
recognisable as the same two people. Midway between photo and flat cartoon.

MUST DO:
- Remove photoreal camera look: no harsh pores, no lens noise, no documentary photo feel.
- Soft painterly shading, warm cheerful colours, gentle rounded forms, creamy light.
- Light clean outlines / edge softness (storybook), soft blended backgrounds.
- Keep who each person is (age, hair, facial features, proportions) — just illustrated.

MUST NOT:
- Do NOT leave it looking like a real photo or stock photograph.
- Do NOT use flat clip-art, thick comic ink outlines, or heavy Pixar 3D CGI.
- Do NOT change poses, framing, background layout, or object count.
- Keep EXACTLY {count} clearly countable {item_word}.
- No text, numbers, watermarks, or speech bubbles. Square 1024x1024.

Output ONLY the soft-cartoon storybook illustration."""
        label = "Soft cartoon stylize"
    else:
        # Full cartoon / cartoonish
        style_prompt = f"""Convert this image into a warm children's-storybook CARTOON
illustration — soft flat colours, clean bold outlines, simplified rounded shapes,
gentle shading, like a Grade 1 picture-book. Not photorealistic.

ABSOLUTE CONSTRAINTS:
1. Keep the same poses, positions, camera framing, and background layout.
2. Keep the same two characters (age, hair, general look) — just in cartoon style.
3. Keep EXACTLY {count} clearly countable {item_word} — do not add or remove any.
4. Keep warm happy expressions.
5. Square 1024x1024. No text, numbers, watermarks, or speech bubbles.

Output ONLY the cartoon image."""
        label = "Cartoon stylize"

    print(f"  🖍️  Applying '{style}' illustration style...")
    result = _request_image_edit(image, style_prompt, label=label)
    if result is None:
        print(f"  ⚠️  Style pass failed — keeping previous image")
        return image.convert("RGB")
    print(f"  ✓ Style '{style}' applied")
    return result


def finish_scene_single_pass(
    image: Image.Image,
    meta: dict,
    object_spec: dict,
    *,
    adult_role: str,
    count: int,
    scene_family: str = "kitchen",
    image_style: str = "soft_cartoon",
    has_pasted_faces: bool = True,
) -> Image.Image:
    """
    One image API call that:
      1. blends pasted faces into the scene (if present)
      2. replaces placeholders with interactive objects
      3. applies soft cartoon / storybook look (default)

    Replaces the former separate face-blend + beautify + stylize calls.
    """
    if not API_KEY:
        print("  ⚠️  No API key — returning pasted composite without AI finish")
        return image.convert("RGB")

    singular = object_spec.get("singular", "item")
    plural = object_spec.get("plural", "items")
    adult = adult_role.replace("_", " ")
    family = (scene_family or meta.get("scene_family") or "kitchen").strip().lower()
    style = (image_style or "soft_cartoon").strip().lower()
    item_word = plural if count != 1 else singular

    if family == "hobby":
        setting_line = (
            f"The base image shows a child and his {adult} in a bright sunny park "
            "at a picnic table / bench."
        )
        mood_line = "like a happy family playtime / hobby moment outdoors"
        surface = "the picnic table"
        quality_line = (
            "Soft storybook park background (grass, trees, creamy daylight), "
            "warm illustrated light, gentle contact shadows on the picnic table."
        )
    else:
        setting_line = (
            f"The base image shows a child and his {adult} in a bright modern kitchen."
        )
        mood_line = "like a happy family kitchen moment"
        surface = "the counter"
        quality_line = (
            "Soft storybook kitchen background, warm cheerful illustrated light, "
            f"gentle contact shadows on {surface}."
        )

    if has_pasted_faces:
        face_block = f"""
1. FACE BLEND (pasted ovals → native faces)
   - Two faces have been pasted as soft ovals onto the head regions.
   - They are the CORRECT people at the CORRECT size and feature proportions.
   - Erase cut-out edges, oval outlines, halos and tone steps at hairline, jaw, chin, neck.
   - Match face lighting / colour / texture to each person's neck, ears and chest.
   - Do NOT change identity, bone structure, face shape, eye/nose/mouth shape, age,
     gender or ethnicity. Do NOT squash, stretch, slim, widen, enlarge or shrink faces.
   - Do NOT swap the two faces. Do NOT replace them with generic faces.
"""
    else:
        face_block = f"""
1. FACES
   - Keep both faces as they are (identity, size, proportions).
   - You may gently warm expressions only.
"""

    if style in ("cartoon", "cartoonish", "full_cartoon"):
        style_block = f"""
4. STYLE — children's storybook CARTOON (required final look)
   - Soft flat colours, clean bold outlines, simplified rounded shapes, gentle shading.
   - Grade 1 picture-book look. Not a photograph.
   - Keep the same poses, framing, and layout.
"""
        out_kind = "cartoon storybook illustration"
        style_priority = (
            "PRIMARY REQUIREMENT: the finished image MUST be a children's cartoon "
            "illustration — never a real photograph."
        )
    else:
        style_block = f"""
4. STYLE — SOFT CARTOON / gentle storybook (required final look)
   - The output MUST look illustrated, not like a camera photo.
   - Soft cartoon storybook: warm cheerful colours, painterly soft shading,
     gently rounded shapes, creamy friendly light, light soft edges.
   - Faces stay recognisable (same people, ages, proportions) but rendered as
     soft illustration — smooth skin, simplified lighting, storybook charm.
   - NOT photoreal, NOT documentary photo, NOT stock photography.
   - NOT flat clip-art, NOT thick comic ink, NOT heavy Pixar 3D CGI.
"""
        out_kind = "soft-cartoon storybook illustration"
        style_priority = (
            "PRIMARY REQUIREMENT: finished image MUST be a soft-cartoon storybook "
            "illustration (gentle illustrated look). It must NOT look like a real photograph."
        )

    prompt = f"""You are finishing ONE personalised Grade 1 worksheet image in a single edit.

{style_priority}

{setting_line}
White placeholder boxes / temporary props mark where the {plural} belong.
{"Faces are pasted ovals that need seamless blending." if has_pasted_faces else ""}

Do ALL of the following in this one output:

{face_block}
2. WARM JOYOUS LOOK
   - Both characters look warmly joyful: natural open smiles, smiling eyes,
     relaxed cheeks, {mood_line}.
   - Adjust expression muscles only — never change who they are.
   - Child stays clearly 5-6 years old; the {adult} stays the same {adult}.

3. OBJECT INTERACTION (critical)
   - Replace EVERY white placeholder / temporary prop with a real {singular}.
   - HARD TOTAL COUNT: EXACTLY {count} clearly countable {plural} in the WHOLE image
     (including anything held). A Year 1 child counting must get {count}.
   - If someone holds a {singular}, that held item COUNTS as one of the {count}.
     Do NOT keep {count} on {surface} AND also hold an extra one.
   - Prefer touching / pointing / steadying one of the {count} surface {plural}.
   - Hold style: {object_spec.get('hold_style', '')}
   - Hand action: {object_spec.get('hand_action', '')}
   - Surface action: {object_spec.get('surface_action', '')}
   - Extra: {object_spec.get('interaction_prompt', '')}
   - Hands must look natural for this object. No leftover white boxes.

{style_block}
5. SCENE QUALITY
   - {quality_line}
   - Keep composition and camera framing. No text, numbers, watermarks, speech bubbles.
   - Square 1024x1024.

ABSOLUTELY FORBIDDEN:
- Do NOT invent a different person for either face.
- Do NOT leave the final image looking photorealistic / like a real photo.
- Do NOT add or remove {item_word} beyond the count {count}.
- Do NOT invent classroom props, charts, or extra people.

Output ONLY the final {out_kind}.
"""

    print("  ✨ Single AI finish: face blend + objects + soft cartoon...")
    result = _request_image_edit(image, prompt, label="Scene finish")
    if result is None:
        print("  ⚠️  Single finish pass failed — trying dedicated style pass on paste")
        # Still attempt soft-cartoon stylize so worksheets don't ship as raw photos
        if style in ("soft_cartoon", "soft", "semi_realistic", "storybook_soft",
                     "cartoon", "cartoonish", "full_cartoon"):
            return stylize_scene(
                image,
                style=style,
                object_spec=object_spec,
                count=count,
            )
        print("  ⚠️  Keeping pasted composite")
        return image.convert("RGB")
    print("  ✓ Scene finished in one image call")
    return result


def compose_interactive_scene(
    *,
    adult_role: str,
    object_id: str,
    photos: dict | None = None,
    scene_family: str = "kitchen",
    category: str | None = None,
    count: int | None = None,
    beautify: bool = True,
    image_style: str = "soft_cartoon",
) -> dict:
    """
    End-to-end compose for final worksheets:
      1. kitchen-style face paste + two-pass AI blend (same as new_pipeline)
      2. paste objects into placeholders (local)
      3. AI finish: object interaction + style (faces already blended)
    """
    photos = photos or {}
    object_spec = load_object_spec(object_id, category=category)
    png_path, meta = find_role_template(scene_family, adult_role)

    slot_count = placeholder_count_from_meta(meta)
    final_count = slot_count or int(
        count or object_spec.get("default_count") or meta.get("count") or 4
    )
    if slot_count and count and int(count) != slot_count:
        print(
            f"  ℹ️  Requested count={count} overridden by template placeholders={slot_count}"
        )

    print(f"  🎭 Role template: {png_path.name}")
    print(f"  🧁 Object: {object_spec.get('plural')} × {final_count} (placeholder-locked)")

    canvas = Image.open(png_path).convert("RGBA")
    child_photo, adult_photo = _resolve_face_photos(photos, adult_role)
    child_region, adult_region = _pick_face_regions(meta, adult_role, png_path)
    kitchen_faces_done = False

    if child_photo and adult_photo and child_region and adult_region:
        try:
            import sys
            from pathlib import Path as _P

            repo = _P(__file__).resolve().parents[1]
            np_root = repo / "new_pipeline"
            if str(np_root) not in sys.path:
                sys.path.insert(0, str(np_root))
            from question_templates.personalize import run_kitchen_face_pipeline

            style_key_early = (image_style or "soft_cartoon").strip().lower()
            soft = style_key_early in (
                "soft_cartoon", "soft", "semi_realistic", "storybook_soft",
                "cartoon", "cartoonish", "full_cartoon",
            )
            canvas = run_kitchen_face_pipeline(
                canvas.convert("RGB"),
                child_region=child_region,
                adult_region=adult_region,
                child_photo=child_photo,
                adult_photo=adult_photo,
                adult_role=adult_role,
                soft_cartoon=soft,
                run_ai_finish=FACE_BLEND_PASS and bool(API_KEY),
                require_ai=False,  # finish_scene can still help if AI fails
                expand_adult_hair=True,
                label=f"{scene_family}/{adult_role}",
            )
            kitchen_faces_done = True
            print("  ✓ Kitchen face pipeline applied (paste → adult AI → child AI)")
        except Exception as exc:
            print(f"  ⚠️  Kitchen face pipeline failed ({exc}) — falling back to simple paste")
            canvas = paste_faces(canvas.convert("RGBA"), meta, photos, template_png=png_path)
    else:
        canvas = paste_faces(canvas, meta, photos, template_png=png_path)

    has_pasted_faces = bool(child_photo and adult_photo) or any(
        photos.get(k)
        for k in (
            "child", "user", adult_role, f"{adult_role}_photo",
            "mother", "father", "grandmother", "grandfather",
        )
    )

    asset = _resolve_object_asset(object_spec)
    if asset:
        canvas = paste_objects(
            canvas.convert("RGBA") if canvas.mode != "RGBA" else canvas,
            meta,
            asset,
            count=final_count,
        )
        print(f"  ✓ Pasted object asset: {asset.name}")
    else:
        print(
            f"  ⚠️  No asset PNG for '{object_id}' — "
            f"AI finish will create real {object_spec.get('plural')} in place of placeholders"
        )

    style_key = (image_style or "soft_cartoon").strip().lower() or "soft_cartoon"

    if beautify:
        final = finish_scene_single_pass(
            canvas,
            meta,
            object_spec,
            adult_role=adult_role,
            count=final_count,
            scene_family=scene_family,
            image_style=style_key,
            # If kitchen faces already blended, only ask finish for objects/style
            has_pasted_faces=has_pasted_faces and not kitchen_faces_done,
        )
    else:
        final = canvas.convert("RGB")

    sync_meta = {
        "template_id": meta.get("template_id"),
        "scene_family": scene_family,
        "family": [adult_role, "child"],
        "face_slots": meta.get("face_slots") or ["child", f"{adult_role}_name"],
        "objects": [{
            "id": 1,
            "type": object_spec.get("object_id") or object_id,
            "count": final_count,
            "singular": object_spec.get("singular"),
            "plural": object_spec.get("plural"),
            "description": f"{final_count} {object_spec.get('plural', object_id)}",
        }],
        "interactive": True,
        "singular": object_spec.get("singular"),
        "plural": object_spec.get("plural"),
        "image_style": style_key,
        "kitchen_face_pipeline": kitchen_faces_done,
    }

    return {
        "final_image": final,
        "metadata": sync_meta,
        "template_meta": meta,
        "object_spec": object_spec,
        "adult_role": adult_role,
        "count": final_count,
        "scene_family": scene_family,
        "singular": object_spec.get("singular"),
        "plural": object_spec.get("plural"),
    }


def _list_object_labels(category: str) -> list[str]:
    labels = []
    cat_dir = OBJECTS_DIR / category
    if not cat_dir.exists():
        return labels
    for path in sorted(cat_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            spec = json.load(f)
        label = (spec.get("object_id") or path.stem).replace("_", " ").title()
        if label.lower() == "ice cream":
            label = "Ice cream"
        labels.append(label)
    return labels


def list_interactive_foods() -> list[str]:
    """Favourite-food labels available via interactive object specs."""
    return _list_object_labels("food")


def list_interactive_hobbies() -> list[str]:
    """Favourite-hobby labels available via interactive object specs."""
    return _list_object_labels("hobby")


def food_label_to_object_id(food_label: str) -> str:
    """Map UI favourite-food label to objects/food/<id>.json stem."""
    raw = (food_label or "").strip().lower().replace("-", " ")
    aliases = {
        "ice cream": "ice_cream",
        "pizza": "pizza",
        "pizza slices": "pizza",
        "cupcakes": "cupcakes",
        "cupcake": "cupcakes",
        "cookies": "cookies",
        "cookie": "cookies",
        "chocolates": "chocolates",
        "chocolate": "chocolates",
        "apples": "apples",
        "apple": "apples",
        "smoothies": "smoothies",
        "smoothie": "smoothies",
        "burgers": "burgers",
        "burger": "burgers",
        "noodles": "noodles",
        "noodle": "noodles",
        "pasta": "pasta",
        "pancakes": "pancakes",
        "pancake": "pancakes",
        "kiwis": "kiwis",
        "kiwi": "kiwis",
        "crackers": "crackers",
        "cracker": "crackers",
        "plums": "plums",
        "plum": "plums",
        "peppers": "peppers",
        "pepper": "peppers",
        "croissants": "croissants",
        "croissant": "croissants",
        "pretzels": "pretzels",
        "pretzel": "pretzels",
        "bagels": "bagels",
        "bagel": "bagels",
        "breadsticks": "breadsticks",
        "breadstick": "breadsticks",
        "biscuits": "biscuits",
        "biscuit": "biscuits",
        "ice lollies": "ice_lollies",
        "ice lolly": "ice_lollies",
        "ice-lollies": "ice_lollies",
    }
    if raw in aliases:
        return aliases[raw]
    return raw.replace(" ", "_")


def hobby_label_to_object_id(hobby_label: str) -> str:
    """Map UI favourite-hobby label to objects/hobby/<id>.json stem."""
    raw = (hobby_label or "").strip().lower().replace("-", " ")
    aliases = {
        "football": "football",
        "soccer": "football",
        "soccer ball": "football",
        "ball": "football",
        "crayons": "crayons",
        "crayon": "crayons",
        "colouring": "crayons",
        "coloring": "crayons",
        "drawing": "crayons",
        "painting": "painting",
        "paint": "painting",
        "paintbrush": "painting",
        "paintbrushes": "painting",
        "art": "painting",
        "kite": "kite",
        "kites": "kite",
        "frisbee": "frisbee",
        "frisbees": "frisbee",
        "bubbles": "bubbles",
        "bubble": "bubbles",
        "bubble wand": "bubbles",
        "bubble wands": "bubbles",
        "trains": "trains",
        "train": "trains",
        "toy trains": "trains",
        "toy train": "trains",
        "playground": "playground",
        "playland": "playground",
        "toy cars": "toy_cars",
        "toy car": "toy_cars",
        "cars": "toy_cars",
        "car": "toy_cars",
        "crafts": "crafts",
        "stickers": "stickers",
        "sticker": "stickers",
        "notebooks": "crafts",
        "notebook": "crafts",
        "pencils": "pencils",
        "pencil": "pencils",
        "marbles": "marbles",
        "marble": "marbles",
        "lego": "lego",
        "blocks": "lego",
        "block": "lego",
        "building": "lego",
        "building blocks": "lego",
        "reading": "reading",
        "books": "reading",
        "book": "reading",
        "parties": "parties",
        "candles": "parties",
        "candle": "parties",
        "gardening": "gardening",
        "flowers": "gardening",
        "flower": "gardening",
        "collecting": "collecting",
        "gemstones": "collecting",
        "gemstone": "collecting",
        "beach": "beach",
        "seashells": "beach",
        "seashell": "beach",
        "shells": "shells",
        "shell": "shells",
    }
    if raw in aliases:
        return aliases[raw]
    return raw.replace(" ", "_")


def list_interactive_roles(scene_family: str = "kitchen") -> list[str]:
    """Adult roles that have an interactive role template ready."""
    roles = []
    for t in list_role_templates(scene_family):
        role = t.get("adult_role")
        if role and role not in roles and t.get("annotated"):
            roles.append(role)
    return roles
