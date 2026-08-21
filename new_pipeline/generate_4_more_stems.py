#!/usr/bin/env python3
"""Generate 4 new Grade 1 addition stems — count-locked, face-swap ready."""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from interactive_templates.face_detect import detect_faces  # noqa: E402

TEMPLATES = ROOT / "new_pipeline" / "question_templates" / "grade_1"
MODEL = os.getenv("STEM_IMAGE_MODEL", "qwen/qwen-image-3")
API_URL = "https://openrouter.ai/api/v1/images"

STYLE = """
ONE vibrant realistic photograph, square 1:1, bright natural light, more background visible.
LEFT: young child (~6–7), front-facing camera, smiling, clear face for face-swap.
RIGHT: companion person, front-facing camera, smiling, clear face for face-swap.
Only these TWO people. No extra people. No text overlays.
CLOTHING (modest children's workbook): women/girls wear high crew-neck or modest round collar covering chest/shoulders. No deep V, off-shoulder, or low scoop. Men: casual modest shirt.
CRITICAL: countable objects must be EXACT counts, spaced apart, not stacked, not overlapping, easy for Grade 1 to count.
Both people mid-activity together (helping, holding, pointing) — not a stiff studio portrait.
""".strip()

ROLE_LABEL = {
    "mother": "MOTHER (right, adult woman ~30–40)",
    "father": "FATHER (right, adult man ~30–40)",
    "grandmother": "GRANDMOTHER (right, elderly woman)",
    "grandfather": "GRANDFATHER (right, elderly man)",
    "uncle": "UNCLE (right, adult man ~30–45)",
    "aunt": "AUNT (right, adult woman ~30–45)",
    "brother": "BROTHER (right, older boy ~10–12)",
    "sister": "SISTER (right, older girl ~10–12)",
}


def headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8504",
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
    faces = detect_faces(path) or []
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
    foods = spec.get("food_tags") or []
    hobbies = spec.get("hobby_tags") or []
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
            "foods": foods,
            "hobbies": hobbies,
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
            "notes": "",
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
        "stem_id": "add_grapes_3_2_user_aunt",
        "adult_role": "aunt",
        "food_tags": ["grapes"],
        "hobby_tags": ["cooking"],
        "interest_notes": "Sharing grapes with aunt addition stem.",
        "image_file": "aunt_2_grapes_child_3_grapes_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 3 grapes in front of {user_name}, "
            "and {aunt_name} has 2 grapes in front of her. "
            "How many grapes are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen table with a bowl of fruit nearby (background only — not countable).
LEFT (child): EXACTLY 3 purple grapes in a small clear row on a plate — spaced apart, countable.
RIGHT (aunt): EXACTLY 2 purple grapes on a plate — spaced apart, countable.
Total visible countable grapes = 5. No extra grapes on the table.
Aunt wears modest crew-neck top. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "grapes", "count": 3, "container": "plate"},
            {"id": "aunt", "owner": "aunt", "object_id": "grapes", "count": 2, "container": "plate"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 grapes + 2 grapes = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 aunt.",
    },
    {
        "stem_id": "add_blocks_2_4_user_brother",
        "adult_role": "brother",
        "food_tags": [],
        "hobby_tags": ["building", "blocks"],
        "interest_notes": "Building with brother addition stem.",
        "image_file": "brother_4_blocks_child_2_blocks_playroom.png",
        "question": (
            "Look at the picture! {user_name} has 2 building blocks in front of {user_name}, "
            "and {brother_name} has 4 building blocks in front of him. "
            "How many building blocks are there altogether?"
        ),
        "prompt_objects": """
Setting: bright playroom / living room floor or low table.
LEFT (child ~6): EXACTLY 2 colourful wooden building blocks in a row — spaced, countable.
RIGHT (older brother ~10–12): EXACTLY 4 colourful wooden building blocks in a row — spaced, countable.
Total countable blocks = 6. No extra blocks in a tower or pile.
Both boys smiling at camera, playing together.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "blocks", "count": 2},
            {"id": "brother", "owner": "brother", "object_id": "blocks", "count": 4},
        ],
        "answer": {
            "type": "count_total",
            "correct": "6",
            "options": ["6", "2", "4", "5"],
            "formula": "2+4",
            "explanation": "2 blocks + 4 blocks = 6",
        },
        "validation_notes": "Counts locked: 2 child + 4 brother.",
    },
    {
        "stem_id": "add_pears_2_3_user_grandfather",
        "adult_role": "grandfather",
        "food_tags": ["pears"],
        "hobby_tags": ["gardening"],
        "interest_notes": "Picking pears with grandfather addition stem.",
        "image_file": "grandfather_3_pears_child_2_pears_garden.png",
        "question": (
            "Look at the picture! {user_name} has 2 pears in front of {user_name}, "
            "and {grandfather_name} has 3 pears in front of him. "
            "How many pears are there altogether?"
        ),
        "prompt_objects": """
Setting: sunny garden / orchard with pear tree leaves in soft background.
LEFT (child): EXACTLY 2 yellow-green pears in a small basket — spaced, fully visible, countable.
RIGHT (grandfather, elderly man): EXACTLY 3 yellow-green pears in a basket — spaced, fully visible, countable.
Total countable pears = 5. No extra pears on the ground or tree in the countable foreground.
Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "pears", "count": 2, "container": "basket"},
            {
                "id": "grandfather",
                "owner": "grandfather",
                "object_id": "pears",
                "count": 3,
                "container": "basket",
            },
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 pears + 3 pears = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 grandfather.",
    },
    {
        "stem_id": "add_donuts_3_2_user_uncle",
        "adult_role": "uncle",
        "food_tags": ["donuts", "doughnuts"],
        "hobby_tags": ["baking"],
        "interest_notes": "Sharing donuts with uncle addition stem.",
        "image_file": "uncle_2_donuts_child_3_donuts_bakery.png",
        "question": (
            "Look at the picture! {user_name} has 3 donuts in front of {user_name}, "
            "and {uncle_name} has 2 donuts in front of him. "
            "How many donuts are there altogether?"
        ),
        "prompt_objects": """
Setting: bright bakery / kitchen counter.
LEFT (child): EXACTLY 3 iced ring donuts on a plate — spaced apart, countable (not stacked).
RIGHT (uncle, adult man): EXACTLY 2 iced ring donuts on a plate — spaced apart, countable.
Total countable donuts = 5. No extra donuts in a box or on the counter.
Both smiling at camera. Uncle in modest casual shirt.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "donuts", "count": 3, "container": "plate"},
            {"id": "uncle", "owner": "uncle", "object_id": "donuts", "count": 2, "container": "plate"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 donuts + 2 donuts = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 uncle.",
    },
]


def run_stem(api_key: str, spec: dict) -> dict:
    role = spec["adult_role"]
    stem_dir = TEMPLATES / "addition" / spec["stem_id"]
    img_path = stem_dir / spec["image_file"]
    if img_path.is_file() and (stem_dir / "meta.json").is_file():
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
        print(f"  faces: child={regions[0]['w']}x{regions[0]['h']} {role}={regions[1]['w']}x{regions[1]['h']}")
    else:
        meta["status"] = "needs_faces"
        print("  WARNING: need face regions")
    (stem_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return {"stem_id": spec["stem_id"], "status": meta["status"], "cost": cost}


def main():
    load_dotenv(ROOT / ".env")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise SystemExit("no OPENROUTER_API_KEY")
    results = []
    for i, spec in enumerate(STEMS):
        try:
            results.append(run_stem(key, spec))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"stem_id": spec["stem_id"], "status": "error", "error": str(e)})
        if i < len(STEMS) - 1:
            time.sleep(2)
    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r.get('stem_id')}: {r.get('status')}" + (f" ({r.get('error')})" if r.get("error") else ""))


if __name__ == "__main__":
    main()
