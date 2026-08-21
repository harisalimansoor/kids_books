#!/usr/bin/env python3
"""Generate 5 new Grade 1 addition stems."""
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
        "stem_id": "add_blueberries_3_2_user_aunt",
        "adult_role": "aunt",
        "food_tags": ["blueberries"],
        "hobby_tags": ["cooking"],
        "interest_notes": "Sharing blueberries with aunt addition stem.",
        "image_file": "aunt_2_blueberries_child_3_blueberries_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 3 blueberries in front of {user_name}, "
            "and {aunt_name} has 2 blueberries in front of her. "
            "How many blueberries are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen table. ACTION: aunt and child sorting blueberries from a small bowl.
LEFT (child): EXACTLY 3 large blueberries on a white plate — spaced apart, countable.
RIGHT (aunt): EXACTLY 2 large blueberries on a white plate — spaced apart, countable.
Total on plates = 5. Extra blueberries may stay inside a bowl (not countable on plates).
Aunt modest crew-neck. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "blueberries", "count": 3, "container": "plate"},
            {"id": "aunt", "owner": "aunt", "object_id": "blueberries", "count": 2, "container": "plate"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 blueberries + 2 blueberries = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 aunt.",
    },
    {
        "stem_id": "add_sandwiches_2_3_user_father",
        "adult_role": "father",
        "food_tags": ["sandwiches"],
        "hobby_tags": ["cooking"],
        "interest_notes": "Making sandwiches with father addition stem.",
        "image_file": "father_3_sandwiches_child_2_sandwiches_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 2 sandwiches in front of {user_name}, "
            "and {father_name} has 3 sandwiches in front of him. "
            "How many sandwiches are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen counter / lunch prep. ACTION: father and child making sandwiches together.
LEFT (child): EXACTLY 2 triangular sandwich halves (or small sandwiches) on a plate — spaced, countable.
RIGHT (father): EXACTLY 3 sandwiches / halves on a plate — spaced, countable.
Total countable sandwiches = 5. No extra sandwiches. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "sandwiches", "count": 2, "container": "plate"},
            {"id": "father", "owner": "father", "object_id": "sandwiches", "count": 3, "container": "plate"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 sandwiches + 3 sandwiches = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 father.",
    },
    {
        "stem_id": "add_peaches_2_4_user_grandmother",
        "adult_role": "grandmother",
        "food_tags": ["peaches"],
        "hobby_tags": ["gardening", "cooking"],
        "interest_notes": "Sharing peaches with grandmother addition stem.",
        "image_file": "grandmother_4_peaches_child_2_peaches_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 2 peaches in front of {user_name}, "
            "and {grandmother_name} has 4 peaches in front of her. "
            "How many peaches are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen / fruit table. ACTION: grandmother and child sharing peaches from a basket.
LEFT (child): EXACTLY 2 whole peaches on a plate — spaced, fully visible, countable.
RIGHT (grandmother): EXACTLY 4 whole peaches on a plate or low tray — spaced, fully visible, countable.
Total countable peaches = 6. Basket may hold extras that stay inside. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "peaches", "count": 2, "container": "plate"},
            {
                "id": "grandmother",
                "owner": "grandmother",
                "object_id": "peaches",
                "count": 4,
                "container": "plate",
            },
        ],
        "answer": {
            "type": "count_total",
            "correct": "6",
            "options": ["6", "2", "4", "5"],
            "formula": "2+4",
            "explanation": "2 peaches + 4 peaches = 6",
        },
        "validation_notes": "Counts locked: 2 child + 4 grandmother.",
    },
    {
        "stem_id": "add_dinosaurs_3_2_user_brother",
        "adult_role": "brother",
        "food_tags": [],
        "hobby_tags": ["toys", "dinosaurs"],
        "interest_notes": "Playing with dinosaur toys with brother addition stem.",
        "image_file": "brother_2_dinosaurs_child_3_dinosaurs_playroom.png",
        "question": (
            "Look at the picture! {user_name} has 3 toy dinosaurs in front of {user_name}, "
            "and {brother_name} has 2 toy dinosaurs in front of him. "
            "How many toy dinosaurs are there altogether?"
        ),
        "prompt_objects": """
Setting: bright playroom / living room floor. ACTION: brother and child playing with toy dinosaurs.
LEFT (child): EXACTLY 3 colourful plastic toy dinosaurs in a row — spaced, fully visible, countable.
RIGHT (brother ~10–12): EXACTLY 2 toy dinosaurs — spaced, fully visible, countable.
Total countable dinosaurs = 5. No extras in a pile. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "dinosaurs", "count": 3},
            {"id": "brother", "owner": "brother", "object_id": "dinosaurs", "count": 2},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 dinosaurs + 2 dinosaurs = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 brother.",
    },
    {
        "stem_id": "add_muffins_2_3_user_sister",
        "adult_role": "sister",
        "food_tags": ["muffins"],
        "hobby_tags": ["baking"],
        "interest_notes": "Baking muffins with sister addition stem.",
        "image_file": "sister_3_muffins_child_2_muffins_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 2 muffins in front of {user_name}, "
            "and {sister_name} has 3 muffins in front of her. "
            "How many muffins are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen after baking. ACTION: sister and child placing muffins on plates.
LEFT (child): EXACTLY 2 muffins on a plate — spaced, countable (not stacked).
RIGHT (sister ~10–12): EXACTLY 3 muffins on a plate — spaced, countable.
Total countable muffins = 5. Baking tray may be empty or in soft background. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "muffins", "count": 2, "container": "plate"},
            {"id": "sister", "owner": "sister", "object_id": "muffins", "count": 3, "container": "plate"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 muffins + 3 muffins = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 sister.",
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
