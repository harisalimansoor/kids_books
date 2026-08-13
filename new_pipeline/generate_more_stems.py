#!/usr/bin/env python3
"""Generate additional Grade 1 stems — count-locked, modest clothing."""
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
ONE vibrant realistic photograph, square 1:1, bright kitchen/living room table.
LEFT: young child (~6), front-facing camera, smiling.
RIGHT: adult, front-facing camera, smiling. Only these two people.
CLOTHING (modest children's workbook): adult woman wears high crew-neck covering chest/shoulders. No deep V, off-shoulder, or low scoop.
Adult man: casual modest shirt.
Object counts EXACT — spaced apart, easily countable, not stacked.
""".strip()

ADULT_LABEL = {
    "mother": "MOTHER (right, adult woman)",
    "father": "FATHER (right, adult man)",
    "grandmother": "GRANDMOTHER (right, elderly woman)",
}


def headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501",
    }


def generate(api_key: str, prompt: str) -> tuple[Image.Image, dict]:
    payload = {"model": MODEL, "prompt": prompt, "aspect_ratio": "1:1", "resolution": "1K", "output_format": "png", "n": 1}
    resp = requests.post(API_URL, headers=headers(api_key), json=payload, timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:800]}")
    data = resp.json()
    b64 = next((d.get("b64_json") for d in data.get("data") or [] if d.get("b64_json")), None)
    if not b64:
        raise RuntimeError(json.dumps(data)[:800])
    im = Image.open(BytesIO(base64.b64decode(b64))).convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
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
        "layout_pattern": spec.get("layout_pattern", "visual_count"),
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
            "notes": f"Image body is {adult_role}-locked.",
        },
        "interests": {"foods": spec.get("food_tags", []), "hobbies": spec.get("hobby_tags", []), "notes": ""},
        "face_regions": [],
        "visual_groups": spec.get("visual_groups", []),
        "answer": spec["answer"],
        "validation": {
            "must_match_image_counts": True,
            "correct_must_be_in_options": True,
            "verified": False,
            "notes": "Needs visual count check",
        },
        "source": {"cluster_file": spec.get("cluster_file", ""), "notes": spec.get("source_notes", "")},
        "style": {"look": "vibrant_realistic", "interaction": True, "facing": "front_camera", "framing": "more_background"},
        "image_generation": {"model": MODEL, "api": "openrouter_images_v1"},
        "annotation": {"method": "yunet"},
    }


STEMS = [
    {
        "stem_id": "add_shells_3_4_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "hobby_tags": ["shells"],
        "image_file": "mother_bucket_3_shells_table_4_shells.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/addition.txt",
        "question": "Look at the picture! {mother_name} has 3 shells in a bucket and 4 more shells on the table next to it, and {user_name} is helping. How many shells does {mother_name} have now?",
        "prompt_objects": "Mother's bucket: EXACTLY 3 seashells. Table group: EXACTLY 4 seashells. Total 7. Beach/kitchen table.",
        "visual_groups": [
            {"id": "bucket", "owner": "mother", "object_id": "shells", "count": 3, "container": "bucket"},
            {"id": "table", "owner": "table", "object_id": "shells", "count": 4, "container": "table"},
        ],
        "answer": {"type": "count_total", "correct": "7", "options": ["7", "3", "4", "6"], "formula": "3+4", "explanation": "3 + 4 = 7 shells"},
    },
    {
        "stem_id": "add_toy_cars_4_3_user_father",
        "topic": "addition",
        "adult_role": "father",
        "hobby_tags": ["toy_cars"],
        "image_file": "father_4_cars_child_3_cars.png",
        "question": "Look at the picture! {father_name} has 4 toy cars on the table, and {user_name} has 3 toy cars in front of {user_name}. How many toy cars are there altogether?",
        "prompt_objects": "RIGHT (father): EXACTLY 4 colourful toy cars in a row. LEFT (child): EXACTLY 3 toy cars in a row. Total 8.",
        "visual_groups": [
            {"id": "father", "owner": "father", "object_id": "toy_cars", "count": 4},
            {"id": "child", "owner": "child", "object_id": "toy_cars", "count": 3},
        ],
        "answer": {"type": "count_total", "correct": "7", "options": ["7", "4", "3", "8"], "formula": "4+3", "explanation": "4 + 3 = 7 toy cars"},
    },
    {
        "stem_id": "add_pasta_2_3_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "food_tags": ["pasta"],
        "image_file": "mother_2_pasta_bowls_child_3_pasta_bowls.png",
        "question": "Look at the picture! {mother_name} has 2 bowls of pasta in front of her, and {user_name} has 3 bowls of pasta in front of {user_name}. How many bowls of pasta are there altogether?",
        "prompt_objects": "RIGHT: EXACTLY 2 small bowls of pasta. LEFT: EXACTLY 3 bowls of pasta. Total 5 bowls.",
        "visual_groups": [
            {"id": "mother", "owner": "mother", "object_id": "pasta", "count": 2},
            {"id": "child", "owner": "child", "object_id": "pasta", "count": 3},
        ],
        "answer": {"type": "count_total", "correct": "5", "options": ["5", "2", "3", "6"], "formula": "2+3", "explanation": "2 + 3 = 5 bowls"},
    },
    {
        "stem_id": "sub_cookies_7_2_crossed_user_mother",
        "topic": "subtraction",
        "adult_role": "mother",
        "food_tags": ["cookies"],
        "image_file": "mother_7_cookies_2_crossed.png",
        "question": "Look at the picture! {mother_name} has 7 cookies in front of her, and 2 of them have a big red X marked through them. How many cookies are not crossed out?",
        "prompt_objects": "EXACTLY 7 cookies on table. EXACTLY 2 have bold red X. Other 5 unmarked.",
        "visual_groups": [{"id": "all", "owner": "mother", "object_id": "cookies", "count": 7, "crossed_count": 2}],
        "answer": {"type": "count_remaining", "correct": "5", "options": ["5", "7", "2", "4"], "formula": "7-2", "explanation": "7 − 2 = 5 cookies left"},
    },
    {
        "stem_id": "sub_cupcakes_6_1_crossed_user_mother",
        "topic": "subtraction",
        "adult_role": "mother",
        "food_tags": ["cupcakes"],
        "image_file": "mother_6_cupcakes_1_crossed.png",
        "question": "Look at the picture! {mother_name} has 6 cupcakes in front of her, and 1 of them has a big red X marked through it. How many cupcakes are not crossed out?",
        "prompt_objects": "EXACTLY 6 cupcakes in a row. EXACTLY 1 has red X. Other 5 clean.",
        "visual_groups": [{"id": "all", "owner": "mother", "object_id": "cupcakes", "count": 6, "crossed_count": 1}],
        "answer": {"type": "count_remaining", "correct": "5", "options": ["5", "6", "1", "4"], "formula": "6-1", "explanation": "6 − 1 = 5 cupcakes left"},
    },
    {
        "stem_id": "money_coins_4p_3p_user_grandmother",
        "topic": "money",
        "adult_role": "grandmother",
        "image_file": "grandmother_pocket_4p_table_3p_coins.png",
        "question": "Look at the picture! {grandmother_name} is holding a pocket with 4p inside and there are 3p coins on the table next to her, and {user_name} is helping. How much money can you count that {grandmother_name} has now?",
        "prompt_objects": "GRANDMOTHER (right, elderly woman) holds open purse with EXACTLY 4 copper 1p coins visible. Table: EXACTLY 3 copper coins. UK pennies. Total 7p.",
        "visual_groups": [
            {"id": "pocket", "owner": "grandmother", "object_id": "coins", "count": 4, "value_pence": 4, "container": "pocket"},
            {"id": "table", "owner": "table", "object_id": "coins", "count": 3, "value_pence": 3, "container": "table"},
        ],
        "answer": {"type": "money_total_pence", "correct": "7p", "options": ["7p", "4p", "3p", "6p"], "formula": "4+3", "explanation": "4p + 3p = 7p"},
    },
    {
        "stem_id": "money_coins_6p_2p_user_father",
        "topic": "money",
        "adult_role": "father",
        "image_file": "father_pocket_6p_table_2p_coins.png",
        "question": "Look at the picture! {father_name} is holding a pocket with 6p inside and there are 2p coins on the table next to him, and {user_name} is helping. How much money can you count that {father_name} has now?",
        "prompt_objects": "FATHER holds open purse: EXACTLY 6 copper 1p coins (2×3 grid). Table: EXACTLY 2 coins. Total 8p.",
        "visual_groups": [
            {"id": "pocket", "owner": "father", "object_id": "coins", "count": 6, "value_pence": 6, "container": "pocket"},
            {"id": "table", "owner": "table", "object_id": "coins", "count": 2, "value_pence": 2, "container": "table"},
        ],
        "answer": {"type": "money_total_pence", "correct": "8p", "options": ["8p", "6p", "2p", "7p"], "formula": "6+2", "explanation": "6p + 2p = 8p"},
    },
    {
        "stem_id": "frac_pizza_4_half_user_father",
        "topic": "fractions",
        "adult_role": "father",
        "food_tags": ["pizza"],
        "image_file": "father_4_pizza_slices_half_circled.png",
        "question": "Look at the picture! {father_name} has 4 pizza slices in front of him, and {user_name} is helping. Half of the pizza slices are circled. How many pizza slices are circled?",
        "prompt_objects": "EXACTLY 4 triangular pizza slices on a plate. EXACTLY 2 circled with red circle (half of 4).",
        "visual_groups": [{"id": "all", "owner": "father", "object_id": "pizza", "count": 4, "circled_count": 2}],
        "answer": {"type": "half_count", "correct": "2", "options": ["2", "4", "1", "3"], "formula": "4/2", "explanation": "Half of 4 slices = 2"},
    },
    {
        "stem_id": "mult_sweets_2x3_user_father",
        "topic": "multiplication_and_division",
        "adult_role": "father",
        "food_tags": ["chocolates"],
        "image_file": "father_2_groups_3_sweets.png",
        "question": "Look at the picture! {father_name} has 2 groups of 3 sweets in front of him. How many sweets are there altogether?",
        "prompt_objects": "EXACTLY 2 groups separated by gap. Each group has EXACTLY 3 wrapped sweets. Total 6.",
        "visual_groups": [{"id": "groups", "owner": "father", "object_id": "sweets", "groups": 2, "per_group": 3, "count": 6}],
        "answer": {"type": "multiply", "correct": "6", "options": ["6", "5", "3", "8"], "formula": "2×3", "explanation": "2 groups of 3 = 6"},
    },
    {
        "stem_id": "gen_cookies_9_4_crossed_user_mother",
        "topic": "general_math",
        "adult_role": "mother",
        "food_tags": ["cookies"],
        "image_file": "mother_9_cookies_4_crossed.png",
        "question": "Look at the picture! There are 9 cookies in a basket, and 4 of them have a big red X marked through them. How many cookies are not crossed out?",
        "prompt_objects": "Basket with EXACTLY 9 cookies visible. EXACTLY 4 have red X. 5 unmarked.",
        "visual_groups": [{"id": "all", "object_id": "cookies", "count": 9, "crossed_count": 4, "container": "basket"}],
        "answer": {"type": "count_remaining", "correct": "5", "options": ["5", "9", "4", "6"], "formula": "9-4", "explanation": "9 − 4 = 5 cookies left"},
    },
    {
        "stem_id": "geo_circles_2_3_user_mother",
        "topic": "geometry",
        "adult_role": "mother",
        "image_file": "child_2_circles_mother_3_circles.png",
        "question": "Look at the picture! {user_name} has 2 circles in front of {user_name}, and {mother_name} has 3 circles in front of her. How many shapes are there altogether?",
        "prompt_objects": "LEFT: EXACTLY 2 blue paper circle cutouts. RIGHT: EXACTLY 3 blue circle cutouts. Total 5 shapes.",
        "visual_groups": [
            {"id": "child", "owner": "child", "object_id": "circles", "count": 2},
            {"id": "mother", "owner": "mother", "object_id": "circles", "count": 3},
        ],
        "answer": {"type": "count_total", "correct": "5", "options": ["5", "2", "3", "6"], "formula": "2+3", "explanation": "2 + 3 = 5 circles"},
    },
    {
        "stem_id": "npv_blocks_5_6_8_missing_user_mother",
        "topic": "number_and_place_value",
        "adult_role": "mother",
        "image_file": "number_blocks_5_6_blank_8.png",
        "question": "Look at the picture! There are blocks lined up in a row with numbers on them: the first block says 5, the second block says 6, and the fourth block says 8. What number should be on the third block?",
        "prompt_objects": "4 wooden cubes in a row: '5', '6', blank with '?', '8'. Numbers large and readable.",
        "visual_groups": [{"id": "seq", "object_id": "number_blocks", "values": [5, 6, None, 8], "missing": 7, "count": 4}],
        "answer": {"type": "missing_number", "correct": "7", "options": ["7", "6", "8", "9"], "formula": None, "explanation": "Sequence 5,6,?,8 → 7"},
    },
    {
        "stem_id": "time_clock_15_minutes_user_mother",
        "topic": "time",
        "adult_role": "mother",
        "image_file": "clock_15_minutes_quarter_hour.png",
        "question": "Look at the picture! There is a teaching clock on the table. The minute hand points to 3 and a sticky note says 15 minutes. How many minutes does the clock show?",
        "prompt_objects": "Analog teaching clock: minute hand at 3 (quarter hour). Yellow sticky note clearly says '15'.",
        "visual_groups": [{"id": "clock", "object_id": "clock", "minutes": 15}],
        "answer": {"type": "clock_marks", "correct": "15", "options": ["15", "30", "5", "60"], "formula": None, "explanation": "Quarter hour = 15 minutes"},
    },
    {
        "stem_id": "meas_ruler_pencil_6cm_user_mother",
        "topic": "measurement",
        "adult_role": "mother",
        "image_file": "ruler_pencil_6cm_mother_child.png",
        "question": "Look at the picture! Can you see the ruler next to the pencil on the table? How long is the pencil?",
        "prompt_objects": "Yellow ruler 0–10 cm. Pencil aligned from 0 to EXACTLY 6 cm. Sticky note may say '6 cm'.",
        "visual_groups": [{"id": "pencil", "object_id": "pencil", "length_cm": 6}],
        "answer": {"type": "length_cm", "correct": "6 cm", "options": ["6 cm", "5 cm", "8 cm", "4 cm"], "formula": None, "explanation": "Pencil spans 0 to 6 on ruler"},
    },
    {
        "stem_id": "add_smoothies_2_2_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "food_tags": ["smoothies"],
        "image_file": "mother_2_smoothies_child_2_smoothies.png",
        "question": "Look at the picture! {mother_name} has 2 smoothies in front of her, and {user_name} has 2 smoothies in front of {user_name}. How many smoothies are there altogether?",
        "prompt_objects": "RIGHT: EXACTLY 2 glasses of pink smoothie. LEFT: EXACTLY 2 glasses. Total 4.",
        "visual_groups": [
            {"id": "mother", "owner": "mother", "object_id": "smoothies", "count": 2},
            {"id": "child", "owner": "child", "object_id": "smoothies", "count": 2},
        ],
        "answer": {"type": "count_total", "correct": "4", "options": ["4", "2", "3", "5"], "formula": "2+2", "explanation": "2 + 2 = 4 smoothies"},
    },
]


def run_stem(api_key: str, spec: dict) -> dict:
    adult = spec["adult_role"]
    stem_dir = TEMPLATES / spec["topic"] / spec["stem_id"]
    img_path = stem_dir / spec["image_file"]
    if img_path.is_file() and (stem_dir / "meta.json").is_file():
        meta = json.loads((stem_dir / "meta.json").read_text())
        if meta.get("status") == "ready":
            return {"stem_id": spec["stem_id"], "status": "skipped"}

    stem_dir.mkdir(parents=True, exist_ok=True)
    (stem_dir / "question.txt").write_text(spec["question"].strip() + "\n")
    meta = build_meta(spec, adult)
    prompt = f"{STYLE}\nAdult role: {ADULT_LABEL.get(adult, adult)}\n\nOBJECTS:\n{spec['prompt_objects']}\n"
    print(f"\n=== {spec['stem_id']} ===")
    im, usage = generate(api_key, prompt)
    im.save(img_path)
    cost = usage.get("cost", "?")
    print(f"  saved ${cost}")

    regions = face_regions(img_path, adult)
    if len(regions) >= 2:
        meta["face_regions"] = regions
        meta["face_detection"] = "yunet"
        meta["status"] = "ready"
    else:
        meta["status"] = "needs_faces"
    (stem_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return {"stem_id": spec["stem_id"], "status": meta["status"], "cost": cost}


def main():
    load_dotenv(ROOT / ".env")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise SystemExit("no API key")
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
        print(f"  {r.get('stem_id')}: {r.get('status')}")
    print(f"  remaining ${rem:.4f}")


if __name__ == "__main__":
    main()
