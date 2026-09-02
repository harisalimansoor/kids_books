#!/usr/bin/env python3
"""Generate 5 more Grade 1 addition stems (child + adult, activity-rich scenes)."""
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
buying, cooking, eating, pouring, cutting, packing, baking, planting). Hands must be
touching / holding / reaching for the objects — NOT a stiff posed portrait.
LEFT: young child (~6–7), face mostly toward camera and smiling (clear for face-swap).
RIGHT: companion, face mostly toward camera and smiling (clear for face-swap).
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
            "notes": "Batch: generate_5_more_addition.py",
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
        "stem_id": "add_biscuits_3_2_user_grandmother",
        "adult_role": "grandmother",
        "food_tags": ["biscuits"],
        "hobby_tags": ["baking", "cooking"],
        "interest_notes": "Baking biscuits with grandmother addition stem.",
        "image_file": "grandmother_2_biscuits_child_3_biscuits_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 3 biscuits in front of {user_name}, "
            "and {grandmother_name} has 2 biscuits in front of her. "
            "How many biscuits are there altogether?"
        ),
        "prompt_objects": """
Setting: cosy kitchen with oven / baking tray. ACTIVITY: BAKING / ICING biscuits together.
COUNT IS CRITICAL:
LEFT (child): EXACTLY 3 round golden biscuits on a cooling rack or plate — three separate
  biscuits, spaced with gaps, fully visible. Hand reaching to pick one up or spread icing.
RIGHT (grandmother): EXACTLY 2 round golden biscuits on her plate/rack — two separate biscuits,
  spaced, fully visible. Hand holding icing bag or placing a biscuit.
TOTAL biscuits = 5 (3+2). No extra biscuits in background. Faces toward camera, smiling.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "biscuits", "singular": "biscuit", "plural": "biscuits", "count": 3, "container": "rack"},
            {"id": "grandmother", "owner": "grandmother", "object_id": "biscuits", "singular": "biscuit", "plural": "biscuits", "count": 2, "container": "rack"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 biscuits + 2 biscuits = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 grandmother.",
    },
    {
        "stem_id": "add_sweetcorn_2_3_user_uncle",
        "adult_role": "uncle",
        "food_tags": ["corn"],
        "hobby_tags": ["farming", "cooking"],
        "interest_notes": "Shucking sweetcorn with uncle at a farm stand.",
        "image_file": "uncle_3_sweetcorn_child_2_sweetcorn_farm.png",
        "question": (
            "Look at the picture! {user_name} has 2 ears of sweetcorn in front of {user_name}, "
            "and {uncle_name} has 3 ears of sweetcorn in front of him. "
            "How many ears of sweetcorn are there altogether?"
        ),
        "prompt_objects": """
Setting: sunny farm stand / vegetable patch. ACTIVITY: SHUCKING / PICKING sweetcorn cobs.
COUNT IS CRITICAL:
LEFT (child): EXACTLY 2 yellow sweetcorn cobs (ears) on the table — two separate cobs,
  spaced, fully visible. Hands peeling husk off one cob.
RIGHT (uncle): EXACTLY 3 yellow sweetcorn cobs on his side — three separate cobs, spaced,
  fully visible. Hand holding a cob or husks.
TOTAL cobs = 5 (2+3). Faces toward camera, smiling. Corn plants in background OK.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "sweetcorn", "singular": "ear of sweetcorn", "plural": "ears of sweetcorn", "count": 2, "container": "table"},
            {"id": "uncle", "owner": "uncle", "object_id": "sweetcorn", "singular": "ear of sweetcorn", "plural": "ears of sweetcorn", "count": 3, "container": "table"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 ears + 3 ears = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 uncle.",
    },
    {
        "stem_id": "add_potatoes_3_2_user_father",
        "adult_role": "father",
        "food_tags": ["potatoes"],
        "hobby_tags": ["cooking", "gardening"],
        "interest_notes": "Washing / peeling potatoes with father.",
        "image_file": "father_2_potatoes_child_3_potatoes_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 3 potatoes in front of {user_name}, "
            "and {father_name} has 2 potatoes in front of him. "
            "How many potatoes are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen sink area. ACTIVITY: WASHING / PEELING potatoes together.
COUNT IS CRITICAL:
LEFT (child): EXACTLY 3 brown potatoes on a board or in a bowl — three separate potatoes,
  spaced, fully visible. Hands scrubbing or holding a peeler on one potato.
RIGHT (father): EXACTLY 2 brown potatoes on his board — two separate potatoes, spaced,
  fully visible. Hand peeling or rinsing a potato.
TOTAL potatoes = 5 (3+2). No extra potatoes in sink pile. Faces toward camera, smiling.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "potatoes", "singular": "potato", "plural": "potatoes", "count": 3, "container": "board"},
            {"id": "father", "owner": "father", "object_id": "potatoes", "singular": "potato", "plural": "potatoes", "count": 2, "container": "board"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 potatoes + 2 potatoes = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 father.",
    },
    {
        "stem_id": "add_blackberries_2_4_user_aunt",
        "adult_role": "aunt",
        "food_tags": ["blackberries"],
        "hobby_tags": ["gardening", "nature"],
        "interest_notes": "Picking blackberries with aunt in a garden.",
        "image_file": "aunt_4_blackberries_child_2_blackberries_garden.png",
        "question": (
            "Look at the picture! {user_name} has 2 blackberries in front of {user_name}, "
            "and {aunt_name} has 4 blackberries in front of her. "
            "How many blackberries are there altogether?"
        ),
        "prompt_objects": """
Setting: sunny berry garden / hedgerow. ACTIVITY: PICKING blackberries into small bowls.
COUNT IS CRITICAL:
LEFT (child): EXACTLY 2 large dark purple blackberries in their bowl — two separate berries,
  spaced, fully visible. Hand reaching to pick from a bush or placing a berry.
RIGHT (aunt): EXACTLY 4 large dark purple blackberries in her bowl — four separate berries,
  arranged in a small cluster with gaps, fully visible. Hand picking a berry.
TOTAL blackberries = 6 (2+4). Faces toward camera, smiling. Berry bushes in background OK.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "blackberries", "singular": "blackberry", "plural": "blackberries", "count": 2, "container": "bowl"},
            {"id": "aunt", "owner": "aunt", "object_id": "blackberries", "singular": "blackberry", "plural": "blackberries", "count": 4, "container": "bowl"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "6",
            "options": ["6", "2", "4", "5"],
            "formula": "2+4",
            "explanation": "2 blackberries + 4 blackberries = 6",
        },
        "validation_notes": "Counts locked: 2 child + 4 aunt.",
    },
    {
        "stem_id": "add_breadsticks_3_2_user_mother",
        "adult_role": "mother",
        "food_tags": ["breadsticks"],
        "hobby_tags": ["cooking", "baking"],
        "interest_notes": "Dipping breadsticks with mother at the table.",
        "image_file": "mother_2_breadsticks_child_3_breadsticks_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 3 breadsticks in front of {user_name}, "
            "and {mother_name} has 2 breadsticks in front of her. "
            "How many breadsticks are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen / dining table with small dip bowl. ACTIVITY: DIPPING / EATING breadsticks.
COUNT IS CRITICAL:
LEFT (child): EXACTLY 3 long golden breadsticks standing in a jar or on a plate — three separate
  breadsticks, spaced, fully visible. Hand dipping one into hummus or sauce.
RIGHT (mother): EXACTLY 2 long golden breadsticks on her plate — two separate breadsticks,
  spaced, fully visible. Hand holding a breadstick mid-dip.
TOTAL breadsticks = 5 (3+2). Faces toward camera, smiling. Oven or bread basket in background OK.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "breadsticks", "singular": "breadstick", "plural": "breadsticks", "count": 3, "container": "plate"},
            {"id": "mother", "owner": "mother", "object_id": "breadsticks", "singular": "breadstick", "plural": "breadsticks", "count": 2, "container": "plate"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 breadsticks + 2 breadsticks = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 mother.",
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

    p = argparse.ArgumentParser(description="Generate 5 activity-rich addition stems")
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
