#!/usr/bin/env python3
"""Generate 6 more Grade 1 addition stems (child + adult companion)."""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

PIPELINE = Path(__file__).resolve().parent
ROOT = PIPELINE.parent
sys.path.insert(0, str(PIPELINE))
from swapping_engine.face_detect import detect_faces  # noqa: E402

TEMPLATES = PIPELINE / "question_templates" / "grade_1"
MODEL = os.getenv("STEM_IMAGE_MODEL", "qwen/qwen-image-3")
API_URL = "https://openrouter.ai/api/v1/images"

STYLE = """
ONE vibrant realistic photograph, square 1:1, bright natural light, more background visible.
ACTION PHOTO — both people are mid-activity with the countable objects (picking, collecting,
buying, cooking, eating, pouring, cutting, packing). Hands must be touching / holding /
reaching for the objects — NOT a stiff posed portrait with objects sitting unused on a table.
LEFT: young child (~6–7), face still mostly toward camera and smiling (clear for face-swap).
RIGHT: companion, face still mostly toward camera and smiling (clear for face-swap).
Only these TWO people. No extra people. No text overlays / logos / writing.
CLOTHING (modest children's workbook): women/girls wear high crew-neck or modest round collar.
Men/boys: casual modest shirt.
CRITICAL: countable objects EXACT counts, spaced apart, not stacked, not overlapping,
each object fully visible so a child can count them.
""".strip()

ROLE_LABEL = {
    "mother": "MOTHER (right, adult woman ~30–40)",
    "father": "FATHER (right, adult man ~30–40)",
    "grandmother": "GRANDMOTHER (right, elderly woman)",
    "grandfather": "GRANDFATHER (right, elderly man)",
    "uncle": "UNCLE (right, adult man ~30–45)",
    "aunt": "AUNT (right, adult woman ~30–45)",
}


def headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501",
    }


def generate(api_key: str, prompt: str) -> tuple[Image.Image, dict]:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "resolution": "1K",
        "output_format": "png",
        "n": 1,
    }
    resp = requests.post(API_URL, headers=headers(api_key), json=payload, timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:800]}")
    data = resp.json()
    b64 = next((d.get("b64_json") for d in data.get("data") or [] if d.get("b64_json")), None)
    if not b64:
        raise RuntimeError(json.dumps(data)[:800])
    im = Image.open(BytesIO(base64.b64decode(b64))).convert("RGB").resize(
        (1024, 1024), Image.Resampling.LANCZOS
    )
    return im, data.get("usage") or {}


def face_regions(path: Path, adult_role: str) -> list[dict]:
    faces = detect_faces(Image.open(path).convert("RGB")) or []
    faces = sorted(faces, key=lambda f: -(f["w"] * f["h"]))[:2]
    ordered = sorted(faces, key=lambda f: f["x"] + f["w"] / 2)

    def region(role: str, f: dict) -> dict:
        o = {
            "role": role,
            "x": int(f["x"]),
            "y": int(f["y"]),
            "w": int(f["w"]),
            "h": int(f["h"]),
        }
        if f.get("landmarks"):
            o["landmarks"] = f["landmarks"]
        if f.get("confidence") is not None:
            o["confidence"] = float(f["confidence"])
        return o

    if len(ordered) < 2:
        return []
    return [region("child", ordered[0]), region(adult_role, ordered[1])]


def build_meta(spec: dict) -> dict:
    role = spec["adult_role"]
    name_key = f"{role}_name"
    return {
        "stem_id": spec["stem_id"],
        "grade": "grade_1",
        "topic": "addition",
        "layout_pattern": "two_group_add",
        "question_file": "question.txt",
        "image_file": spec["image_file"],
        "status": "placeholder",
        "personalisation": {
            "face_slots": ["child", role],
            "adult_role_slot": True,
            "template_adult_role": role,
            "allowed_adult_roles": [role],
            "name_placeholders": {"user_name": "child", name_key: role},
            "face_swap_friendly": True,
            "notes": f"Image body is {role}-locked. Paste child + {role} faces only.",
        },
        "interests": {
            "foods": spec.get("food_tags") or [],
            "hobbies": spec.get("hobby_tags") or [],
            "notes": spec.get("interest_notes", ""),
        },
        "face_regions": [],
        "visual_groups": spec["visual_groups"],
        "answer": spec["answer"],
        "validation": {
            "must_match_image_counts": True,
            "correct_must_be_in_options": True,
            "verified": True,
            "notes": spec["validation_notes"],
        },
        "source": {
            "cluster_file": "new_pipeline/Question clusters for grade 1/addition.txt",
            "notes": "Batch: generate_6_more_addition.py",
        },
        "style": {
            "look": "vibrant_realistic",
            "interaction": True,
            "facing": "front_camera",
            "framing": "more_background",
        },
        "image_generation": {"model": MODEL, "api": "openrouter_images_v1"},
        "annotation": {"method": "yunet", "instructions": "Tweak face_regions if needed."},
    }


STEMS = [
    {
        "stem_id": "add_raspberries_2_3_user_aunt",
        "adult_role": "aunt",
        "food_tags": ["raspberries"],
        "hobby_tags": ["cooking", "gardening"],
        "interest_notes": "Picking raspberries with aunt addition stem.",
        "image_file": "aunt_3_raspberries_child_2_raspberries_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 2 raspberries in front of {user_name}, "
            "and {aunt_name} has 3 raspberries in front of her. "
            "How many raspberries are there altogether?"
        ),
        "prompt_objects": """
Setting: sunny garden / raspberry canes or market stall. ACTIVITY: PICKING / COLLECTING raspberries together.
LEFT (child): actively placing raspberries into a small bowl — EXACTLY 2 large red raspberries
  already in / beside their bowl, spaced and fully visible to count. Child's hand mid-pick.
RIGHT (aunt): picking raspberries into her bowl — EXACTLY 3 large red raspberries in / beside
  her bowl, spaced and fully visible. Aunt's hand holding or placing a berry.
Total countable raspberries = 5. Faces toward camera, smiling. Aunt modest crew-neck.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "raspberries", "singular": "raspberry", "plural": "raspberries", "count": 2, "container": "bowl"},
            {"id": "aunt", "owner": "aunt", "object_id": "raspberries", "singular": "raspberry", "plural": "raspberries", "count": 3, "container": "bowl"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 raspberries + 3 raspberries = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 aunt.",
    },
    {
        "stem_id": "add_toast_3_2_user_mother",
        "adult_role": "mother",
        "food_tags": ["toast", "bread"],
        "hobby_tags": ["cooking", "baking"],
        "interest_notes": "Spreading jam on toast with mother addition stem.",
        "image_file": "mother_2_toast_child_3_toast_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 3 slices of toast in front of {user_name}, "
            "and {mother_name} has 2 slices of toast in front of her. "
            "How many slices of toast are there altogether?"
        ),
        "prompt_objects": """
Setting: bright breakfast kitchen. ACTIVITY: SPREADING / EATING toast together (not just posing).
LEFT (child): mid-bite or spreading jam — EXACTLY 3 golden toast slices on their plate,
  spaced flat, fully visible and countable. Hand holding a slice or knife.
RIGHT (mother): buttering toast — EXACTLY 2 golden toast slices on her plate, spaced flat,
  fully visible. Knife or hand touching a slice.
Total countable toast slices = 5. Toaster soft in background OK. Faces toward camera, smiling.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "toast", "singular": "toast slice", "plural": "toast slices", "count": 3, "container": "plate"},
            {"id": "mother", "owner": "mother", "object_id": "toast", "singular": "toast slice", "plural": "toast slices", "count": 2, "container": "plate"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 toast slices + 2 toast slices = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 mother.",
    },
    {
        "stem_id": "add_broccoli_2_4_user_father",
        "adult_role": "father",
        "food_tags": ["broccoli"],
        "hobby_tags": ["cooking"],
        "interest_notes": "Chopping / cooking broccoli with father addition stem.",
        "image_file": "father_4_broccoli_child_2_broccoli_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 2 pieces of broccoli in front of {user_name}, "
            "and {father_name} has 4 pieces of broccoli in front of him. "
            "How many pieces of broccoli are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen veg prep. ACTIVITY: WASHING / CHOPPING broccoli for cooking together.
COUNT IS CRITICAL — wrong counts make the worksheet unusable:
LEFT (child): EXACTLY 2 green broccoli florets on their board — two separate florets only,
  clearly spaced with a gap between them, fully visible. Hands touching them.
RIGHT (father): EXACTLY 4 green broccoli florets on his board — four separate florets only,
  arranged in a neat row of four (or 2×2 grid), each floret clearly separate, fully visible.
  Knife may touch ONE of the four florets; do NOT create extra pieces from cutting.
TOTAL broccoli florets in the whole image = 6 (2+4). No florets in background, sink, or fridge.
Faces toward camera, smiling. Not a stiff pose.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "broccoli", "singular": "broccoli piece", "plural": "broccoli pieces", "count": 2, "container": "board"},
            {"id": "father", "owner": "father", "object_id": "broccoli", "singular": "broccoli piece", "plural": "broccoli pieces", "count": 4, "container": "board"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "6",
            "options": ["6", "2", "4", "5"],
            "formula": "2+4",
            "explanation": "2 broccoli pieces + 4 broccoli pieces = 6",
        },
        "validation_notes": "Counts locked: 2 child + 4 father.",
    },
    {
        "stem_id": "add_juice_boxes_2_3_user_uncle",
        "adult_role": "uncle",
        "food_tags": ["juice"],
        "hobby_tags": ["shopping"],
        "interest_notes": "Buying / unpacking juice boxes with uncle addition stem.",
        "image_file": "uncle_3_juice_boxes_child_2_juice_boxes_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 2 juice boxes in front of {user_name}, "
            "and {uncle_name} has 3 juice boxes in front of him. "
            "How many juice boxes are there altogether?"
        ),
        "prompt_objects": """
Setting: supermarket checkout / kitchen unpacking shopping bags. ACTIVITY: BUYING / UNPACKING juice.
LEFT (child): taking juice boxes out of a shopping bag — EXACTLY 2 colourful juice boxes
  standing upright, spaced, fully visible, countable. Hand holding or placing a box.
RIGHT (uncle): unpacking next to child — EXACTLY 3 colourful juice boxes standing upright,
  spaced, fully visible. Hand holding a box or bag.
Total countable juice boxes = 5. Faces toward camera, smiling. No readable brand text on boxes.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "juice_boxes", "singular": "juice box", "plural": "juice boxes", "count": 2, "container": "table"},
            {"id": "uncle", "owner": "uncle", "object_id": "juice_boxes", "singular": "juice box", "plural": "juice boxes", "count": 3, "container": "table"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 juice boxes + 3 juice boxes = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 uncle.",
    },
    {
        "stem_id": "add_yogurts_2_3_user_grandmother",
        "adult_role": "grandmother",
        "food_tags": ["yogurt"],
        "hobby_tags": ["cooking"],
        "interest_notes": "Opening / eating yogurt pots with grandmother addition stem.",
        "image_file": "grandmother_3_yogurts_child_2_yogurts_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 2 yogurt pots in front of {user_name}, "
            "and {grandmother_name} has 3 yogurt pots in front of her. "
            "How many yogurt pots are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen / cafe table. ACTIVITY: OPENING / EATING yogurt together (spoons in hand).
LEFT (child): scooping yogurt — EXACTLY 2 small yogurt pots, spaced, fully visible, countable.
  Spoon in hand, mid-eat or peeling a lid.
RIGHT (grandmother): opening / stirring yogurt — EXACTLY 3 yogurt pots, spaced, fully visible.
  Spoon or hand interacting with a pot.
Total countable yogurt pots = 5. Faces toward camera, smiling. Grandmother modest crew-neck.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "yogurts", "singular": "yogurt pot", "plural": "yogurt pots", "count": 2, "container": "table"},
            {"id": "grandmother", "owner": "grandmother", "object_id": "yogurts", "singular": "yogurt pot", "plural": "yogurt pots", "count": 3, "container": "table"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 yogurt pots + 3 yogurt pots = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 grandmother.",
    },
    {
        "stem_id": "add_cucumbers_3_2_user_grandfather",
        "adult_role": "grandfather",
        "food_tags": ["cucumbers"],
        "hobby_tags": ["gardening", "cooking"],
        "interest_notes": "Harvesting cucumbers with grandfather addition stem.",
        "image_file": "grandfather_2_cucumbers_child_3_cucumbers_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 3 cucumbers in front of {user_name}, "
            "and {grandfather_name} has 2 cucumbers in front of him. "
            "How many cucumbers are there altogether?"
        ),
        "prompt_objects": """
Setting: sunny allotment / vegetable garden or garden table. ACTIVITY: PICKING / HARVESTING cucumbers.
LEFT (child): collecting cucumbers into a basket — EXACTLY 3 whole green cucumbers,
  spaced, fully visible, countable. Hands placing a cucumber into the basket.
RIGHT (grandfather): picking from the vine / arranging — EXACTLY 2 whole green cucumbers,
  spaced, fully visible. Hands holding or setting a cucumber down.
Total countable cucumbers = 5. Faces toward camera, smiling. Garden plants in background OK.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "cucumbers", "singular": "cucumber", "plural": "cucumbers", "count": 3, "container": "basket"},
            {"id": "grandfather", "owner": "grandfather", "object_id": "cucumbers", "singular": "cucumber", "plural": "cucumbers", "count": 2, "container": "basket"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 cucumbers + 2 cucumbers = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 grandfather.",
    },
]


def run_stem(api_key: str, spec: dict, *, force: bool = False) -> dict:
    role = spec["adult_role"]
    stem_dir = TEMPLATES / "addition" / spec["stem_id"]
    img_path = stem_dir / spec["image_file"]
    if (
        not force
        and img_path.is_file()
        and (stem_dir / "meta.json").is_file()
    ):
        meta = json.loads((stem_dir / "meta.json").read_text())
        if meta.get("status") == "ready" and len(meta.get("face_regions") or []) >= 2:
            return {"stem_id": spec["stem_id"], "status": "skipped"}

    stem_dir.mkdir(parents=True, exist_ok=True)
    (stem_dir / "question.txt").write_text(spec["question"].strip() + "\n")
    meta = build_meta(spec)
    prompt = (
        f"{STYLE}\n"
        f"Companion role: {ROLE_LABEL.get(role, role)}\n\n"
        f"OBJECTS (exact counts):\n{spec['prompt_objects'].strip()}\n"
    )
    print(f"\n=== {spec['stem_id']} ===")
    im, usage = generate(api_key, prompt)
    im.save(img_path)
    cost = usage.get("cost", "?")
    print(f"  saved {img_path.name} cost={cost}")

    regions = face_regions(img_path, role)
    if len(regions) >= 2:
        meta["face_regions"] = regions
        meta["face_detection"] = "yunet"
        meta["status"] = "ready"
        print(
            f"  faces: child={regions[0]['w']}x{regions[0]['h']} "
            f"{role}={regions[1]['w']}x{regions[1]['h']}"
        )
    else:
        meta["status"] = "needs_faces"
        print("  WARNING: need face regions")
    (stem_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return {"stem_id": spec["stem_id"], "status": meta["status"], "cost": cost}


def main():
    import argparse

    p = argparse.ArgumentParser(description="Generate 6 activity-rich addition stems")
    p.add_argument("--force", action="store_true", help="Regenerate even if stem already ready")
    args = p.parse_args()

    load_dotenv(ROOT / ".env")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise SystemExit("no OPENROUTER_API_KEY")
    results = []
    for i, spec in enumerate(STEMS):
        try:
            results.append(run_stem(key, spec, force=args.force))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"stem_id": spec["stem_id"], "status": "error", "error": str(e)})
        if i < len(STEMS) - 1:
            time.sleep(2)
    print("\n=== SUMMARY ===")
    for r in results:
        err = f" ({r.get('error')})" if r.get("error") else ""
        print(f"  {r.get('stem_id')}: {r.get('status')}{err}")


if __name__ == "__main__":
    main()
