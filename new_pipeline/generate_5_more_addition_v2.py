#!/usr/bin/env python3
"""Generate 5 more Grade 1 addition stems."""
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
RIGHT: companion, front-facing camera, smiling, clear face for face-swap.
Only these TWO people. No extra people. No text overlays.
CLOTHING (modest children's workbook): women/girls wear high crew-neck or modest round collar.
Men/boys: casual modest shirt. Mid-activity together — not a stiff studio portrait.
CRITICAL: countable objects EXACT counts, spaced apart, not stacked, not overlapping.
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
        "stem_id": "add_waffles_2_3_user_mother",
        "adult_role": "mother",
        "food_tags": ["waffles"],
        "hobby_tags": ["cooking", "baking"],
        "interest_notes": "Making waffles with mother addition stem.",
        "image_file": "mother_3_waffles_child_2_waffles_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 2 waffles in front of {user_name}, "
            "and {mother_name} has 3 waffles in front of her. "
            "How many waffles are there altogether?"
        ),
        "prompt_objects": """
Setting: bright breakfast kitchen. ACTION: mother and child making / serving waffles.
LEFT (child): EXACTLY 2 golden waffles on a plate — spaced, fully visible, countable.
RIGHT (mother): EXACTLY 3 golden waffles on a plate — spaced, fully visible, countable.
Total countable waffles = 5. Waffle iron soft in background OK. Mother modest crew-neck. Both smiling.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "waffles", "count": 2, "container": "plate"},
            {"id": "mother", "owner": "mother", "object_id": "waffles", "count": 3, "container": "plate"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 waffles + 3 waffles = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 mother.",
    },
    {
        "stem_id": "add_pineapples_3_2_user_uncle",
        "adult_role": "uncle",
        "food_tags": ["pineapples"],
        "hobby_tags": ["cooking"],
        "interest_notes": "Cutting pineapple with uncle addition stem.",
        "image_file": "uncle_2_pineapples_child_3_pineapples_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 3 pineapple pieces in front of {user_name}, "
            "and {uncle_name} has 2 pineapple pieces in front of him. "
            "How many pineapple pieces are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen / fruit prep. ACTION: uncle and child preparing pineapple together.
LEFT (child): EXACTLY 3 yellow pineapple chunks/rings on a plate — spaced, countable.
RIGHT (uncle): EXACTLY 2 pineapple chunks/rings on a plate — spaced, countable.
Total countable pieces = 5. Whole pineapple may sit in background. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "pineapples", "count": 3, "container": "plate"},
            {"id": "uncle", "owner": "uncle", "object_id": "pineapples", "count": 2, "container": "plate"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 pineapple pieces + 2 pineapple pieces = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 uncle.",
    },
    {
        "stem_id": "add_teddy_bears_2_3_user_sister",
        "adult_role": "sister",
        "food_tags": [],
        "hobby_tags": ["toys", "teddy_bears"],
        "interest_notes": "Playing with teddy bears with sister addition stem.",
        "image_file": "sister_3_teddies_child_2_teddies_bedroom.png",
        "question": (
            "Look at the picture! {user_name} has 2 teddy bears in front of {user_name}, "
            "and {sister_name} has 3 teddy bears in front of her. "
            "How many teddy bears are there altogether?"
        ),
        "prompt_objects": """
Setting: bright child's bedroom / play corner. ACTION: sister and child playing with teddy bears.
LEFT (child): EXACTLY 2 teddy bears sitting in a row — spaced, fully visible, countable.
RIGHT (sister ~10–12): EXACTLY 3 teddy bears sitting in a row — spaced, fully visible, countable.
Total countable teddy bears = 5. No extras on the bed pile. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "teddy_bears", "count": 2},
            {"id": "sister", "owner": "sister", "object_id": "teddy_bears", "count": 3},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 teddy bears + 3 teddy bears = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 sister.",
    },
    {
        "stem_id": "add_avocados_2_3_user_aunt",
        "adult_role": "aunt",
        "food_tags": ["avocados"],
        "hobby_tags": ["cooking"],
        "interest_notes": "Making avocado toast with aunt addition stem.",
        "image_file": "aunt_3_avocados_child_2_avocados_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 2 avocados in front of {user_name}, "
            "and {aunt_name} has 3 avocados in front of her. "
            "How many avocados are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen. ACTION: aunt and child preparing avocados / avocado toast.
LEFT (child): EXACTLY 2 whole green avocados on a plate or board — spaced, countable.
RIGHT (aunt): EXACTLY 3 whole green avocados — spaced, countable.
Total countable avocados = 5. Aunt modest crew-neck. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "avocados", "count": 2},
            {"id": "aunt", "owner": "aunt", "object_id": "avocados", "count": 3},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 avocados + 3 avocados = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 aunt.",
    },
    {
        "stem_id": "add_robots_3_2_user_grandfather",
        "adult_role": "grandfather",
        "food_tags": [],
        "hobby_tags": ["toys", "robots"],
        "interest_notes": "Playing with robot toys with grandfather addition stem.",
        "image_file": "grandfather_2_robots_child_3_robots_playroom.png",
        "question": (
            "Look at the picture! {user_name} has 3 toy robots in front of {user_name}, "
            "and {grandfather_name} has 2 toy robots in front of him. "
            "How many toy robots are there altogether?"
        ),
        "prompt_objects": """
Setting: bright playroom / living room table. ACTION: grandfather and child playing with toy robots.
LEFT (child): EXACTLY 3 colourful toy robots standing in a row — spaced, fully visible, countable.
RIGHT (grandfather, elderly man): EXACTLY 2 toy robots — spaced, fully visible, countable.
Total countable robots = 5. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "robots", "count": 3},
            {"id": "grandfather", "owner": "grandfather", "object_id": "robots", "count": 2},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 robots + 2 robots = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 grandfather.",
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
        err = f" ({r.get('error')})" if r.get("error") else ""
        print(f"  {r.get('stem_id')}: {r.get('status')}{err}")


if __name__ == "__main__":
    main()
