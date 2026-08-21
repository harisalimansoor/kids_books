#!/usr/bin/env python3
"""Generate 5 new Grade 1 addition stems — count-locked, face-swap ready."""
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
        "stem_id": "add_icecream_2_3_user_mother",
        "adult_role": "mother",
        "food_tags": ["ice_cream"],
        "hobby_tags": [],
        "interest_notes": "Sharing ice cream with mother addition stem.",
        "image_file": "mother_3_icecream_child_2_icecream_park.png",
        "question": (
            "Look at the picture! {user_name} has 2 ice cream cones in front of {user_name}, "
            "and {mother_name} has 3 ice cream cones in front of her. "
            "How many ice cream cones are there altogether?"
        ),
        "prompt_objects": """
Setting: sunny outdoor park picnic table / ice cream stand nearby in soft background.
ACTION: mother and child sharing / choosing ice cream together, mid-activity.
LEFT (child): EXACTLY 2 ice cream cones standing in a small holder or on the table — spaced, countable.
RIGHT (mother): EXACTLY 3 ice cream cones — spaced, countable.
Total countable cones = 5. No extra cones in hands or background.
Mother: modest crew-neck top. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "ice_cream", "count": 2},
            {"id": "mother", "owner": "mother", "object_id": "ice_cream", "count": 3},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 ice cream cones + 3 ice cream cones = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 mother.",
    },
    {
        "stem_id": "add_popcorn_3_2_user_sister",
        "adult_role": "sister",
        "food_tags": ["popcorn"],
        "hobby_tags": ["parties", "movies"],
        "interest_notes": "Movie night popcorn with sister addition stem.",
        "image_file": "sister_2_popcorn_child_3_popcorn_livingroom.png",
        "question": (
            "Look at the picture! {user_name} has 3 bowls of popcorn in front of {user_name}, "
            "and {sister_name} has 2 bowls of popcorn in front of her. "
            "How many bowls of popcorn are there altogether?"
        ),
        "prompt_objects": """
Setting: cozy living room movie night — soft blankets, TV soft-blurred in background.
ACTION: sister and child sharing popcorn for a movie, mid-activity.
LEFT (child): EXACTLY 3 small clear bowls of popcorn in a row — spaced, countable.
RIGHT (sister, older girl ~10–12): EXACTLY 2 small bowls of popcorn — spaced, countable.
Total countable bowls = 5. No extra bowls. Modest clothing. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "popcorn", "count": 3, "container": "bowl"},
            {"id": "sister", "owner": "sister", "object_id": "popcorn", "count": 2, "container": "bowl"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 bowls + 2 bowls = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 sister.",
    },
    {
        "stem_id": "add_balls_2_3_user_father",
        "adult_role": "father",
        "food_tags": [],
        "hobby_tags": ["football", "sports"],
        "interest_notes": "Playing with balls with father addition stem.",
        "image_file": "father_3_balls_child_2_balls_garden.png",
        "question": (
            "Look at the picture! {user_name} has 2 balls in front of {user_name}, "
            "and {father_name} has 3 balls in front of him. "
            "How many balls are there altogether?"
        ),
        "prompt_objects": """
Setting: sunny garden / backyard grass.
ACTION: father and child playing / practising with balls, mid-activity.
LEFT (child): EXACTLY 2 colourful balls on the grass in front — spaced, fully visible, countable.
RIGHT (father): EXACTLY 3 colourful balls on the grass in front — spaced, fully visible, countable.
Total countable balls = 5. No extra balls. Both smiling at camera. Modest casual clothes.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "balls", "count": 2},
            {"id": "father", "owner": "father", "object_id": "balls", "count": 3},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "4"],
            "formula": "2+3",
            "explanation": "2 balls + 3 balls = 5",
        },
        "validation_notes": "Counts locked: 2 child + 3 father.",
    },
    {
        "stem_id": "add_cherries_4_2_user_grandmother",
        "adult_role": "grandmother",
        "food_tags": ["cherries"],
        "hobby_tags": ["cooking", "gardening"],
        "interest_notes": "Picking cherries with grandmother addition stem.",
        "image_file": "grandmother_2_cherries_child_4_cherries_kitchen.png",
        "question": (
            "Look at the picture! {user_name} has 4 cherries in front of {user_name}, "
            "and {grandmother_name} has 2 cherries in front of her. "
            "How many cherries are there altogether?"
        ),
        "prompt_objects": """
Setting: bright kitchen table; small bowl or basket of cherries nearby for activity context.
ACTION: grandmother and child sorting / sharing cherries from a basket, mid-activity.
LEFT (child): EXACTLY 4 bright red cherries on a white plate — spaced apart, countable (not a pile).
RIGHT (grandmother): EXACTLY 2 red cherries on a white plate — spaced, countable.
Total countable cherries on plates = 6. Basket may hold extra cherries that stay inside the basket.
Both smiling at camera. Grandmother modest clothing.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "cherries", "count": 4, "container": "plate"},
            {
                "id": "grandmother",
                "owner": "grandmother",
                "object_id": "cherries",
                "count": 2,
                "container": "plate",
            },
        ],
        "answer": {
            "type": "count_total",
            "correct": "6",
            "options": ["6", "4", "2", "5"],
            "formula": "4+2",
            "explanation": "4 cherries + 2 cherries = 6",
        },
        "validation_notes": "Counts locked: 4 child + 2 grandmother.",
    },
    {
        "stem_id": "add_bubbles_3_2_user_brother",
        "adult_role": "brother",
        "food_tags": [],
        "hobby_tags": ["bubbles", "play"],
        "interest_notes": "Blowing bubbles with brother addition stem.",
        "image_file": "brother_2_bubbles_child_3_bubbles_garden.png",
        "question": (
            "Look at the picture! {user_name} has 3 bubble bottles in front of {user_name}, "
            "and {brother_name} has 2 bubble bottles in front of him. "
            "How many bubble bottles are there altogether?"
        ),
        "prompt_objects": """
Setting: sunny garden / patio.
ACTION: brother and child blowing bubbles / playing with bubble wands, mid-activity.
Some soap bubbles floating in the air is fine (not countable).
LEFT (child): EXACTLY 3 small colourful bubble bottles standing on a low table or grass — spaced, countable.
RIGHT (brother ~10–12): EXACTLY 2 bubble bottles — spaced, countable.
Total countable bottles = 5. No extra bottles. Both smiling at camera.
""",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "bubbles", "count": 3, "container": "bottle"},
            {"id": "brother", "owner": "brother", "object_id": "bubbles", "count": 2, "container": "bottle"},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "3", "2", "4"],
            "formula": "3+2",
            "explanation": "3 bubble bottles + 2 bubble bottles = 5",
        },
        "validation_notes": "Counts locked: 3 child + 2 brother.",
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
