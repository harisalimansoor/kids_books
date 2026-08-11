#!/usr/bin/env python3
"""Generate 10 food-named Grade 1 stems via qwen/qwen-image-3 (count-locked)."""
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
MODEL = "qwen/qwen-image-3"
API_URL = "https://openrouter.ai/api/v1/images"

STYLE = """
ONE vibrant realistic photograph, square 1:1, bright kitchen table scene.
LEFT: young child (~6), front-facing camera, smiling.
RIGHT: adult, front-facing camera, smiling.
Only these two people. Faces clear for face-swap.
CLOTHING (modest — children's workbook): mother/adult woman must wear a high crew-neck or modest round collar top that fully covers chest and shoulders. No deep V-neck, off-shoulder, wrap cleavage, or low scoop.
CRITICAL: food objects must be EXACT counts, spaced apart, not stacked, not overlapping, easily countable.
""".strip()


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
    faces = detect_faces(path) or []
    faces = sorted(faces, key=lambda f: -(f["w"] * f["h"]))[:2]
    ordered = sorted(faces, key=lambda f: f["x"] + f["w"] / 2)

    def region(role: str, f: dict) -> dict:
        o = {"role": role, "x": int(f["x"]), "y": int(f["y"]), "w": int(f["w"]), "h": int(f["h"])}
        if f.get("landmarks"):
            o["landmarks"] = f["landmarks"]
        if f.get("confidence") is not None:
            o["confidence"] = float(f["confidence"])
        return o

    if len(ordered) < 2:
        return []
    return [region("child", ordered[0]), region(adult_role, ordered[1])]


def build_meta(spec: dict, adult_role: str) -> dict:
    name_key = f"{adult_role}_name"
    return {
        "stem_id": spec["stem_id"],
        "grade": "grade_1",
        "topic": spec["topic"],
        "layout_pattern": spec.get("layout_pattern", "two_group_add"),
        "question_file": "question.txt",
        "image_file": spec["image_file"],
        "status": "placeholder",
        "personalisation": {
            "face_slots": ["child", adult_role],
            "adult_role_slot": True,
            "template_adult_role": adult_role,
            "allowed_adult_roles": [adult_role],
            "name_placeholders": {"user_name": "child", name_key: adult_role},
            "face_swap_friendly": True,
            "notes": f"Image body is {adult_role}-locked. Paste child + {adult_role} faces only.",
        },
        "interests": {
            "foods": spec.get("food_tags", []),
            "hobbies": [],
            "notes": "Food-named stem for favourite-food preference.",
        },
        "face_regions": [],
        "visual_groups": spec.get("visual_groups", []),
        "answer": spec["answer"],
        "validation": {
            "must_match_image_counts": True,
            "correct_must_be_in_options": True,
            "verified": False,
            "notes": "Awaiting visual count check",
        },
        "source": {
            "cluster_file": spec.get("cluster_file", ""),
            "notes": spec.get("source_notes", "Food-named Grade 1 stem"),
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
        "stem_id": "add_cookies_4_3_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "food_tags": ["cookies"],
        "image_file": "mother_4_cookies_child_3_cookies.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/addition.txt",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {mother_name} has 4 cookies in front of her, and {user_name} has 3 cookies in front of {user_name}. How many cookies are there altogether?",
        "prompt_objects": """
On the table RIGHT in front of mother: EXACTLY 4 round chocolate-chip cookies in a neat row.
On the table LEFT in front of child: EXACTLY 3 round chocolate-chip cookies in a neat row.
Clear gap between the two groups. No extra cookies. Total = 7.
""",
        "visual_groups": [
            {"id": "mother", "owner": "mother", "object_id": "cookies", "count": 4},
            {"id": "child", "owner": "child", "object_id": "cookies", "count": 3},
        ],
        "answer": {"type": "count_total", "correct": "7", "options": ["7", "4", "3", "6"], "formula": "4+3", "explanation": "4 cookies + 3 cookies = 7"},
        "expected": "4 cookies + 3 cookies",
    },
    {
        "stem_id": "add_cupcakes_3_2_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "food_tags": ["cupcakes"],
        "image_file": "mother_3_cupcakes_child_2_cupcakes.png",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {mother_name} has 3 cupcakes in front of her, and {user_name} has 2 cupcakes in front of {user_name}. How many cupcakes are there altogether?",
        "prompt_objects": """
RIGHT of table (mother): EXACTLY 3 frosted cupcakes with colourful icing, spaced apart.
LEFT of table (child): EXACTLY 2 frosted cupcakes, spaced apart.
No extra cupcakes. Total = 5.
""",
        "visual_groups": [
            {"id": "mother", "owner": "mother", "object_id": "cupcakes", "count": 3},
            {"id": "child", "owner": "child", "object_id": "cupcakes", "count": 2},
        ],
        "answer": {"type": "count_total", "correct": "5", "options": ["5", "3", "2", "4"], "formula": "3+2", "explanation": "3 cupcakes + 2 cupcakes = 5"},
        "expected": "3 + 2 cupcakes",
    },
    {
        "stem_id": "add_pizza_2_3_user_father",
        "topic": "addition",
        "adult_role": "father",
        "food_tags": ["pizza"],
        "image_file": "father_2_pizza_child_3_pizza.png",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {father_name} has 2 pizza slices in front of him, and {user_name} has 3 pizza slices in front of {user_name}. How many pizza slices are there altogether?",
        "prompt_objects": """
RIGHT (father): EXACTLY 2 triangular pizza slices on a plate.
LEFT (child): EXACTLY 3 triangular pizza slices on a plate.
Slices clearly separated into two groups. No whole pizza. Total = 5 slices.
""",
        "visual_groups": [
            {"id": "father", "owner": "father", "object_id": "pizza", "count": 2},
            {"id": "child", "owner": "child", "object_id": "pizza", "count": 3},
        ],
        "answer": {"type": "count_total", "correct": "5", "options": ["5", "2", "3", "6"], "formula": "2+3", "explanation": "2 pizza slices + 3 pizza slices = 5"},
        "expected": "2 + 3 pizza slices",
    },
    {
        "stem_id": "add_pancakes_4_2_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "food_tags": ["pancakes"],
        "image_file": "mother_4_pancakes_child_2_pancakes.png",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {mother_name} has 4 pancakes in front of her, and {user_name} has 2 pancakes in front of {user_name}. How many pancakes are there altogether?",
        "prompt_objects": """
RIGHT (mother): EXACTLY 4 golden pancakes laid flat in a 2×2 grid (not one tall stack — each pancake separately visible).
LEFT (child): EXACTLY 2 golden pancakes side by side, separately visible.
No extra pancakes. Total = 6.
""",
        "visual_groups": [
            {"id": "mother", "owner": "mother", "object_id": "pancakes", "count": 4},
            {"id": "child", "owner": "child", "object_id": "pancakes", "count": 2},
        ],
        "answer": {"type": "count_total", "correct": "6", "options": ["6", "4", "2", "5"], "formula": "4+2", "explanation": "4 pancakes + 2 pancakes = 6"},
        "expected": "4 + 2 pancakes",
    },
    {
        "stem_id": "add_burgers_3_2_user_father",
        "topic": "addition",
        "adult_role": "father",
        "food_tags": ["burgers"],
        "image_file": "father_3_burgers_child_2_burgers.png",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {father_name} has 3 burgers in front of him, and {user_name} has 2 burgers in front of {user_name}. How many burgers are there altogether?",
        "prompt_objects": """
RIGHT (father): EXACTLY 3 small hamburgers/burgers in a row, each fully visible.
LEFT (child): EXACTLY 2 burgers in a row.
No extra burgers. Total = 5.
""",
        "visual_groups": [
            {"id": "father", "owner": "father", "object_id": "burgers", "count": 3},
            {"id": "child", "owner": "child", "object_id": "burgers", "count": 2},
        ],
        "answer": {"type": "count_total", "correct": "5", "options": ["5", "3", "2", "4"], "formula": "3+2", "explanation": "3 burgers + 2 burgers = 5"},
        "expected": "3 + 2 burgers",
    },
    {
        "stem_id": "sub_chocolates_8_3_crossed_user_mother",
        "topic": "subtraction",
        "adult_role": "mother",
        "food_tags": ["chocolates"],
        "image_file": "mother_8_chocolates_3_crossed.png",
        "layout_pattern": "cross_out_subtract",
        "question": "Look at the picture! {mother_name} has 8 chocolates in front of her, and 3 of them have a big red X marked through them. How many chocolates are not crossed out?",
        "prompt_objects": """
On the table: EXACTLY 8 chocolate squares / chocolate pieces in a neat 2×4 grid.
EXACTLY 3 of them have a bold red X drawn through them.
The other 5 have no marks. No extra chocolates.
""",
        "visual_groups": [
            {"id": "all", "owner": "mother", "object_id": "chocolates", "count": 8, "crossed_count": 3},
        ],
        "answer": {"type": "count_remaining", "correct": "5", "options": ["5", "8", "3", "4"], "formula": "8-3", "explanation": "8 chocolates − 3 crossed = 5 left"},
        "expected": "8 chocolates, 3 crossed",
    },
    {
        "stem_id": "sub_mangoes_6_2_crossed_user_mother",
        "topic": "subtraction",
        "adult_role": "mother",
        "food_tags": ["mangoes"],
        "image_file": "mother_6_mangoes_2_crossed.png",
        "layout_pattern": "cross_out_subtract",
        "question": "Look at the picture! {mother_name} has 6 mangoes in front of her, and 2 of them have a big red X marked through them. How many mangoes are not crossed out?",
        "prompt_objects": """
On the table: EXACTLY 6 yellow-orange mangoes in a neat arrangement.
EXACTLY 2 mangoes have a bold red X through them.
The other 4 are unmarked. No extra mangoes.
""",
        "visual_groups": [
            {"id": "all", "owner": "mother", "object_id": "mangoes", "count": 6, "crossed_count": 2},
        ],
        "answer": {"type": "count_remaining", "correct": "4", "options": ["4", "6", "2", "5"], "formula": "6-2", "explanation": "6 mangoes − 2 crossed = 4 left"},
        "expected": "6 mangoes, 2 crossed",
    },
    {
        "stem_id": "frac_ice_cream_6_half_user_mother",
        "topic": "fractions",
        "adult_role": "mother",
        "food_tags": ["ice_cream"],
        "image_file": "mother_6_ice_cream_half_circled.png",
        "layout_pattern": "half_of_set_circled",
        "question": "Look at the picture! {mother_name} has 6 ice creams in front of her, and {user_name} is helping. Half of the ice creams are circled. How many ice creams are circled?",
        "prompt_objects": """
On the table: EXACTLY 6 ice cream cones (or cups) in a neat row/grid, all clearly visible.
EXACTLY 3 of them are circled with a bold red circle (half of 6).
The other 3 are not circled. No extra ice creams.
""",
        "visual_groups": [
            {"id": "all", "owner": "mother", "object_id": "ice_cream", "count": 6, "circled_count": 3},
        ],
        "answer": {"type": "half_count", "correct": "3", "options": ["3", "6", "2", "4"], "formula": "6/2", "explanation": "Half of 6 ice creams circled = 3"},
        "expected": "6 ice creams, 3 circled",
    },
    {
        "stem_id": "mult_cookies_4x2_user_mother",
        "topic": "multiplication_and_division",
        "adult_role": "mother",
        "food_tags": ["cookies"],
        "image_file": "mother_4_groups_2_cookies.png",
        "layout_pattern": "equal_groups",
        "question": "Look at the picture! {mother_name} has 4 groups of 2 cookies in front of her. How many cookies are there altogether?",
        "prompt_objects": """
On the table: EXACTLY 4 small plates in a row.
Each plate has EXACTLY 2 cookies on it (4 groups × 2 = 8 cookies total).
Plates spaced apart. No extra cookies.
""",
        "visual_groups": [
            {"id": "groups", "owner": "mother", "object_id": "cookies", "groups": 4, "per_group": 2, "count": 8},
        ],
        "answer": {"type": "multiply", "correct": "8", "options": ["8", "6", "4", "10"], "formula": "4×2", "explanation": "4 groups of 2 cookies = 8"},
        "expected": "4 plates × 2 cookies",
    },
    {
        "stem_id": "add_noodles_3_2_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "food_tags": ["noodles"],
        "image_file": "mother_3_noodle_bowls_child_2_noodle_bowls.png",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {mother_name} has 3 bowls of noodles in front of her, and {user_name} has 2 bowls of noodles in front of {user_name}. How many bowls of noodles are there altogether?",
        "prompt_objects": """
RIGHT (mother): EXACTLY 3 small bowls filled with noodles, each bowl separately countable.
LEFT (child): EXACTLY 2 small bowls filled with noodles.
Clear gap between groups. No extra bowls. Total = 5 bowls.
""",
        "visual_groups": [
            {"id": "mother", "owner": "mother", "object_id": "noodles", "count": 3},
            {"id": "child", "owner": "child", "object_id": "noodles", "count": 2},
        ],
        "answer": {"type": "count_total", "correct": "5", "options": ["5", "3", "2", "4"], "formula": "3+2", "explanation": "3 noodle bowls + 2 noodle bowls = 5"},
        "expected": "3 + 2 noodle bowls",
    },
]


def adult_label(role: str) -> str:
    return {"mother": "MOTHER (right, adult woman)", "father": "FATHER (right, adult man)"}.get(role, role)


def run_stem(api_key: str, spec: dict) -> dict:
    adult = spec["adult_role"]
    stem_dir = TEMPLATES / spec["topic"] / spec["stem_id"]
    stem_dir.mkdir(parents=True, exist_ok=True)
    img_path = stem_dir / spec["image_file"]
    meta_path = stem_dir / "meta.json"
    q_path = stem_dir / "question.txt"

    if meta_path.exists() and img_path.is_file():
        meta = json.loads(meta_path.read_text())
        if meta.get("status") == "ready":
            return {"stem_id": spec["stem_id"], "status": "skipped", "cost": 0}

    q_path.write_text(spec["question"].strip() + "\n")
    meta = build_meta(spec, adult)
    prompt = f"""{STYLE}
Adult role: {adult_label(adult)}

FOOD OBJECTS (exact counts — Grade 1 maths worksheet):
{spec['prompt_objects'].strip()}
""".strip()

    print(f"\n=== {spec['stem_id']} ===")
    print(f"  food={spec.get('food_tags')} expect={spec.get('expected')}")
    im, usage = generate(api_key, prompt)
    im.save(img_path)
    cost = usage.get("cost", "?")
    print(f"  saved {img_path.name}  ${cost}")

    regions = face_regions(img_path, adult)
    if len(regions) >= 2:
        meta["face_regions"] = regions
        meta["face_detection"] = "yunet"
        meta["status"] = "ready"
        meta["validation"]["notes"] = f"Generated with {MODEL}; needs visual count check."
    else:
        meta["status"] = "needs_faces"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return {"stem_id": spec["stem_id"], "status": meta["status"], "cost": cost, "path": str(img_path)}


def main():
    load_dotenv(ROOT / ".env")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise SystemExit("OPENROUTER_API_KEY missing")
    results = []
    for i, spec in enumerate(STEMS):
        try:
            results.append(run_stem(key, spec))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"stem_id": spec["stem_id"], "status": "error", "error": str(e)})
        if i < len(STEMS) - 1:
            time.sleep(2)
    cr = requests.get("https://openrouter.ai/api/v1/credits", headers=headers(key), timeout=30).json()
    rem = cr["data"]["total_credits"] - cr["data"]["total_usage"]
    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r.get('stem_id')}: {r.get('status')} cost={r.get('cost')}")
    print(f"  remaining ${rem:.4f}")


if __name__ == "__main__":
    main()
