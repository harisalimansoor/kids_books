"""
personalize.py
─────────────────────────────────────────────────────────────────────────────
Paste user/adult faces onto a question-template stem, then run ONE soft-cartoon
finish that keeps uploaded identity (likeness) — only storybook stylisation.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFilter

TEMPLATES_ROOT = Path(__file__).resolve().parent
PIPELINE_ROOT = TEMPLATES_ROOT.parent  # new_pipeline/
REPO_ROOT = PIPELINE_ROOT.parent  # kids_books/

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(dotenv_path=REPO_ROOT / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
IMAGE_MODEL = "openai/gpt-5.4-image-2"

ROOT = TEMPLATES_ROOT


def _soft_mask(w: int, h: int, inset: int = 14, blur: int = 22) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((inset, inset, w - inset, h - inset), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def _paste_face(canvas: Image.Image, region: dict, photo_path: Path) -> bool:
    from interactive_templates.face_swap import crop_upload_face, resize_face_keep_aspect

    face = crop_upload_face(photo_path)
    if face is None:
        return False
    x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    face = resize_face_keep_aspect(face.convert("RGBA"), w, h)
    mask = _soft_mask(face.width, face.height)
    canvas.paste(face, (x, y), mask)
    return True


def _extract_image_url(data: dict) -> str | None:
    msg = data.get("choices", [{}])[0].get("message", {})
    for img in msg.get("images", []):
        url = (img.get("image_url") or {}).get("url", "")
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


def soft_cartoon_keep_identity(image: Image.Image) -> Image.Image | None:
    """
    Soft-cartoon stylise while locking faces to the pasted uploads.
    Returns None on API failure (caller keeps the paste composite).
    """
    if not API_KEY:
        return None

    buf = BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    prompt = """
This image already has the CORRECT people's faces pasted onto the heads
(soft oval pastes). Your job is ONLY:

1. FACE IDENTITY (absolute — most important)
   - Keep each pasted face looking like THAT exact person from the upload.
   - Same bone structure, eye shape, nose, mouth, skin tone, age, gender, hairline.
   - Do NOT replace with a generic cartoon character or a different person.
   - Do NOT beautify into someone prettier/younger/different.
   - Only remove hard oval cut edges and gently match lighting to the neck.

2. SOFT CARTOON / STORYBOOK LOOK (whole image)
   - Soft storybook illustration: warmer colours, gentle painterly shading,
     soft edges — NOT a camera photo, NOT flat clip-art, NOT heavy Pixar CGI.
   - Bodies, clothes, kitchen, and apples may be more illustrated.
   - Faces stay recognisably the pasted people, just softly illustrated.

3. PRESERVE LAYOUT
   - Same two people, poses, framing.
   - Keep EXACT apple counts and the two separate groups (do not add/remove apples).
   - No text, numbers, watermarks. Square 1024x1024.

Output ONLY the final soft-cartoon image with the real uploaded likenesses.
""".strip()

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
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8504",
    }
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    except Exception as exc:
        print(f"  ⚠️  personalize request failed ({exc})")
        return None
    if resp.status_code != 200:
        print(f"  ⚠️  personalize API failed ({resp.status_code}): {resp.text[:200]}")
        return None
    img_ref = _extract_image_url(resp.json())
    if not img_ref:
        print("  ⚠️  personalize: no image returned")
        return None
    if img_ref.startswith("data:image"):
        raw = base64.b64decode(img_ref.split(",", 1)[1])
    else:
        raw = requests.get(img_ref, timeout=60).content
    return Image.open(BytesIO(raw)).convert("RGB")


def personalize_stem(
    stem_dir: str | Path,
    *,
    child_photo: str | Path,
    adult_photo: str | Path,
    adult_role: str = "mother",
    out_path: str | Path | None = None,
    run_ai_finish: bool = True,
) -> Path:
    """
    Load stem template → paste child + adult faces → optional identity-locked
    soft-cartoon finish → save PNG.
    """
    stem_dir = Path(stem_dir)
    meta = json.loads((stem_dir / "meta.json").read_text(encoding="utf-8"))
    pers = meta.get("personalisation") or {}
    locked = (pers.get("template_adult_role") or "").strip().lower()
    allowed = [r.lower() for r in (pers.get("allowed_adult_roles") or [])]
    role = adult_role.strip().lower()
    if locked and role != locked:
        raise ValueError(
            f"{stem_dir}: template body is '{locked}' — refuse adult_role='{adult_role}'. "
            "Generate a separate stem PNG for each role."
        )
    if allowed and role not in allowed:
        raise ValueError(f"{stem_dir}: adult_role '{adult_role}' not in {allowed}")

    image_file = meta.get("image_file") or "template.png"
    canvas = Image.open(stem_dir / image_file).convert("RGBA")

    regions = {r["role"]: r for r in (meta.get("face_regions") or [])}
    # Prefer role-named box (father/mother/…); fall back to legacy "adult" slot.
    adult_region = regions.get(role) or regions.get(locked) or regions.get("adult")
    if "child" not in regions or adult_region is None:
        raise ValueError(
            f"{stem_dir}: meta.json needs face_regions for 'child' and "
            f"'{role or locked or 'adult'}' (template_adult_role)"
        )

    ok_c = _paste_face(canvas, regions["child"], Path(child_photo))
    ok_a = _paste_face(canvas, adult_region, Path(adult_photo))
    print(f"  ✓ Pasted child={ok_c} {role}={ok_a}")

    result = canvas.convert("RGB")
    if run_ai_finish and (ok_c or ok_a):
        print("  ✨ Soft cartoon finish (identity-locked)…")
        finished = soft_cartoon_keep_identity(result)
        if finished is not None:
            result = finished
            print("  ✓ Soft cartoon applied (faces locked to uploads)")
        else:
            print("  ⚠️  AI finish failed — keeping pasted composite")

    if out_path is None:
        out_path = stem_dir / f"preview_{adult_role}.png"
    else:
        out_path = Path(out_path)
    result.save(out_path, format="PNG")
    print(f"  ✓ Saved {out_path}")
    return out_path


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Personalize a question-template stem")
    p.add_argument("stem_dir", type=Path)
    p.add_argument("--child", required=True, type=Path)
    p.add_argument("--adult", required=True, type=Path)
    p.add_argument("--role", default="mother")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--no-ai", action="store_true")
    args = p.parse_args()
    personalize_stem(
        args.stem_dir,
        child_photo=args.child,
        adult_photo=args.adult,
        adult_role=args.role,
        out_path=args.out,
        run_ai_finish=not args.no_ai,
    )
