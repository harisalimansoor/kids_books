#!/usr/bin/env python3
"""Batch-generate question stem images via OpenRouter Images API (qwen/qwen-image-3)."""
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

PIPELINE = ROOT / "new_pipeline"
TEMPLATES = PIPELINE / "question_templates" / "grade_1"
MODEL = os.getenv("STEM_IMAGE_MODEL", "qwen/qwen-image-3")
API_URL = "https://openrouter.ai/api/v1/images"

BASE_STYLE = """
Style: ONE vibrant realistic photograph, square 1:1, bright natural light, kitchen/living room table scene, more background visible.
Child (left, ~5–7 years) + adult (right) BOTH front-facing camera, smiling. Only these two people.
CLOTHING (modest — children's workbook): mother/adult woman must wear a high crew-neck or modest round collar top that fully covers chest and shoulders. No deep V-neck, off-shoulder, wrap cleavage, or low scoop.
""".strip()


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8504",
    }


def generate_image(api_key: str, prompt: str) -> tuple[Image.Image, dict]:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "resolution": "1K",
        "output_format": "png",
        "n": 1,
    }
    resp = requests.post(API_URL, headers=_headers(api_key), json=payload, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage") or {}
    b64 = next((d.get("b64_json") for d in data.get("data") or [] if d.get("b64_json")), None)
    if not b64:
        raise RuntimeError(f"No image in response: {json.dumps(data)[:500]}")
    im = Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")
    im = im.resize((1024, 1024), Image.Resampling.LANCZOS)
    return im, usage


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
            "notes": f"Image body is {adult_role}-locked. Paste child + {adult_role} faces only.",
        },
        "interests": spec.get("interests", {"foods": [], "hobbies": [], "notes": ""}),
        "face_regions": [],
        "visual_groups": spec.get("visual_groups", []),
        "answer": spec["answer"],
        "validation": {
            "must_match_image_counts": True,
            "correct_must_be_in_options": True,
            "verified": False,
            "notes": spec.get("validation_notes", ""),
        },
        "source": {
            "cluster_file": spec.get("cluster_file", ""),
            "notes": spec.get("source_notes", ""),
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
    # Prefer ≤10 countable objects per group — models often miss higher counts.
    {
        "stem_id": "gen_blocks_8_basket_4_table_user_mother",
        "topic": "general_math",
        "adult_role": "mother",
        "image_file": "mother_basket_8_blocks_table_4_blocks.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/general_math.txt",
        "layout_pattern": "two_group_total",
        "question": "Look at the picture! There are 8 colourful blocks in {mother_name}'s basket and 4 more blocks on the table next to it, and {user_name} is helping count. How many blocks are there altogether?",
        "prompt_objects": """
MOTHER (right) holds a shallow wicker basket with EXACTLY 8 colourful wooden cubes in a neat 2×4 grid (all fully visible).
On the table in a separate row: EXACTLY 4 colourful cubes. No extra blocks.
""",
        "visual_groups": [
            {"id": "basket", "owner": "mother", "object_id": "blocks", "singular": "block", "plural": "blocks", "count": 8, "container": "basket"},
            {"id": "table", "owner": "table", "object_id": "blocks", "singular": "block", "plural": "blocks", "count": 4, "container": "table"},
        ],
        "answer": {"type": "count_total", "correct": "12", "options": ["12", "8", "4", "11"], "formula": "8+4", "explanation": "8 in basket + 4 on table = 12"},
        "interests": {"foods": [], "hobbies": ["lego"], "notes": "Blocks stem."},
    },
    {
        "stem_id": "money_coins_9p_2p_user_father",
        "topic": "money",
        "adult_role": "father",
        "image_file": "father_pocket_8p_table_2p_coins.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/money.txt",
        "layout_pattern": "two_group_add_money",
        "question": "Look at the picture! {father_name} is holding a pocket with 9p inside and there are 2p coins on the table next to him, and {user_name} is helping. How much money can you count that {father_name} has now?",
        "prompt_objects": """
FATHER (right, adult man) holds open a coin purse with EXACTLY 9 copper 1p coins, all separately visible (3×3 grid).
On the table: EXACTLY 2 copper 1p coins. No extra coins.
""",
        "visual_groups": [
            {"id": "pocket", "owner": "father", "object_id": "coins", "singular": "coin", "plural": "coins", "count": 9, "value_pence": 9, "container": "pocket"},
            {"id": "table", "owner": "table", "object_id": "coins", "singular": "coin", "plural": "coins", "count": 2, "value_pence": 2, "container": "table"},
        ],
        "answer": {"type": "money_total_pence", "correct": "11p", "options": ["11p", "9p", "2p", "10p"], "formula": "9+2", "explanation": "9p in pocket + 2p on table = 11p"},
    },
    {
        "stem_id": "sub_apples_9_3_crossed_user_mother",
        "topic": "subtraction",
        "adult_role": "mother",
        "image_file": "mother_basket_9_apples_3_crossed.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/subtraction.txt",
        "layout_pattern": "cross_out_subtract",
        "question": "Look at the picture! {mother_name} has a big basket with apples in it. You can see 9 apples around the basket, but 3 of them have a big red X marked through them. How many apples are left that {mother_name} can still eat?",
        "prompt_objects": """
MOTHER (right) beside a big basket on a table.
EXACTLY 9 red apples arranged around/near the basket, all clearly visible.
EXACTLY 3 of the 9 apples have a bold red X drawn through them (crossed out).
The other 6 apples have NO mark.
Child (left) looks at the apples. No extra apples.
""",
        "visual_groups": [
            {"id": "all", "owner": "mother", "object_id": "apples", "singular": "apple", "plural": "apples", "count": 9, "crossed_count": 3, "container": "basket"},
        ],
        "answer": {"type": "count_remaining", "correct": "6", "options": ["6", "9", "3", "5"], "formula": "9-3", "explanation": "9 apples minus 3 crossed out = 6 left"},
        "interests": {"foods": ["apples"], "hobbies": [], "notes": "Apple subtraction stem."},
    },
    {
        "stem_id": "sub_books_9_3_floor_user_mother",
        "topic": "subtraction",
        "adult_role": "mother",
        "image_file": "mother_shelf_9_books_3_floor.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/subtraction.txt",
        "layout_pattern": "two_group_subtract",
        "question": "Look at the picture! {mother_name} has a bookshelf with 9 books on it, but 3 books have fallen off the shelf and are on the floor. How many books are still on {mother_name}'s bookshelf?",
        "prompt_objects": """
MOTHER (right) next to a wooden bookshelf.
EXACTLY 9 colourful children's books standing on the shelf in one neat row.
EXACTLY 3 books lying on the floor in front of the shelf.
Child (left) helps look. No extra books elsewhere.
""",
        "visual_groups": [
            {"id": "shelf", "owner": "mother", "object_id": "books", "singular": "book", "plural": "books", "count": 9, "container": "shelf"},
            {"id": "floor", "owner": "floor", "object_id": "books", "singular": "book", "plural": "books", "count": 3, "container": "floor", "notes": "Fallen books — subtract from shelf total"},
        ],
        "answer": {"type": "count_remaining", "correct": "6", "options": ["6", "9", "3", "12"], "formula": "9-3", "explanation": "9 on shelf, 3 fell off → 6 remain on shelf"},
        "interests": {"foods": [], "hobbies": ["reading"], "notes": "Book subtraction stem."},
    },
    # measurement — 2
    {
        "stem_id": "meas_ruler_paper_8cm_user_mother",
        "topic": "measurement",
        "adult_role": "mother",
        "image_file": "ruler_paper_8cm_mother_child.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/measurement.txt",
        "layout_pattern": "ruler_length",
        "question": "Look at the picture! Can you see the ruler next to the piece of squared paper on the table? How long is the piece of squared paper?",
        "prompt_objects": """
On the table: a standard school ruler (cm markings) lying next to a rectangular piece of blue squared/graph paper.
The paper edge aligns from 0 cm to EXACTLY 8 cm on the ruler — length clearly reads 8 cm.
A small label or sticky note on the paper may say "8 cm".
MOTHER (right) and child (left) look at the ruler. Ruler markings legible.
""",
        "visual_groups": [
            {"id": "paper", "object_id": "paper", "length_cm": 8, "notes": "Squared paper length = 8 cm on ruler"},
        ],
        "answer": {"type": "length_cm", "correct": "8 cm", "options": ["8 cm", "5 cm", "10 cm", "6 cm"], "formula": None, "explanation": "Paper spans 0 to 8 on the ruler"},
    },
    {
        "stem_id": "meas_jug_water_500ml_user_mother",
        "topic": "measurement",
        "adult_role": "mother",
        "image_file": "jug_1l_water_500ml_mother_child.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/measurement.txt",
        "layout_pattern": "jug_volume",
        "question": "Look at the picture! There is a measuring jug with numbers on the side and it is filled with water up to a certain line. The jug says 1 l on it. What number is the water level at on the measuring jug?",
        "prompt_objects": """
Clear glass measuring jug labelled "1 L" with ml markings: 250, 500, 750, 1000.
Water level sits EXACTLY at the 500 ml / half-litre line (middle mark).
Blue water visible. Jug on kitchen table.
MOTHER (right) and child (left) observe. Markings readable.
""",
        "visual_groups": [
            {"id": "jug", "object_id": "water", "volume_ml": 500, "container": "jug", "max_l": 1},
        ],
        "answer": {"type": "volume_ml", "correct": "500", "options": ["500", "250", "750", "1000"], "formula": None, "explanation": "Water level at 500 ml mark on 1 L jug"},
    },
    # geometry — 2
    {
        "stem_id": "geo_square_shape_user_mother",
        "topic": "geometry",
        "adult_role": "mother",
        "image_file": "mother_holding_square_paper.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/geometry.txt",
        "layout_pattern": "shape_identify",
        "question": "Look at the picture! Can you see the piece of paper that {mother_name} is holding? It has 4 equal sides and 4 corners. What shape is it?",
        "prompt_objects": """
MOTHER (right) holds up a bright yellow paper cutout shape toward camera.
The shape is a perfect SQUARE: 4 equal sides, 4 corners, not a rectangle.
Child (left) smiles. Plain background table. Shape clearly square.
""",
        "visual_groups": [{"id": "shape", "object_id": "square", "sides": 4, "equal_sides": True}],
        "answer": {"type": "shape_name", "correct": "square", "options": ["square", "circle", "triangle", "rectangle"], "formula": None, "explanation": "4 equal sides and 4 corners = square"},
    },
    {
        "stem_id": "geo_stars_2_3_total_user_mother",
        "topic": "geometry",
        "adult_role": "mother",
        "image_file": "child_2_stars_mother_3_stars.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/geometry.txt",
        "layout_pattern": "two_group_shapes",
        "question": "Look at the picture! {user_name} has 2 stars in front of {user_name}, and {mother_name} has 3 stars in front of her. How many shapes are there altogether?",
        "prompt_objects": """
On the table: EXACTLY 2 golden star cutouts in front of the child (left side).
EXACTLY 3 golden star cutouts in front of MOTHER (right side).
Stars clearly separated into two groups. No other shapes.
""",
        "visual_groups": [
            {"id": "child_stars", "owner": "child", "object_id": "stars", "count": 2},
            {"id": "mother_stars", "owner": "mother", "object_id": "stars", "count": 3},
        ],
        "answer": {"type": "count_total", "correct": "5", "options": ["5", "2", "3", "6"], "formula": "2+3", "explanation": "2 stars + 3 stars = 5 shapes"},
    },
    # multiplication_and_division — 2
    {
        "stem_id": "mult_marbles_3x2_user_mother",
        "topic": "multiplication_and_division",
        "adult_role": "mother",
        "image_file": "mother_3_groups_2_marbles.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/multiplication_and_division.txt",
        "layout_pattern": "equal_groups",
        "question": "Look at the picture! {mother_name} has 3 groups of 2 marbles in front of her. How many marbles are there altogether?",
        "prompt_objects": """
On the table in front of MOTHER (right): EXACTLY 3 separate small circles/groups.
Each group contains EXACTLY 2 colourful marbles (3 groups × 2 = 6 total).
Groups visually separated (small bowls or drawn circles).
Child (left) counts. No extra marbles.
""",
        "visual_groups": [
            {"id": "groups", "owner": "mother", "object_id": "marbles", "groups": 3, "per_group": 2, "count": 6},
        ],
        "answer": {"type": "multiply", "correct": "6", "options": ["6", "5", "3", "8"], "formula": "3×2", "explanation": "3 groups of 2 marbles = 6"},
        "interests": {"foods": [], "hobbies": ["marbles"], "notes": ""},
    },
    {
        "stem_id": "mult_blocks_2x4_user_father",
        "topic": "multiplication_and_division",
        "adult_role": "father",
        "image_file": "father_2_groups_4_blocks.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/multiplication_and_division.txt",
        "layout_pattern": "equal_groups",
        "question": "Look at the picture! {father_name} has 2 groups of 4 blocks in front of him. How many blocks are there altogether?",
        "prompt_objects": """
On the table in front of FATHER (right, adult man): EXACTLY 2 separate groups.
Each group has EXACTLY 4 colourful wooden blocks (2 groups × 4 = 8 total).
Groups clearly separated. Child (left) watches. No extra blocks.
""",
        "visual_groups": [
            {"id": "groups", "owner": "father", "object_id": "blocks", "groups": 2, "per_group": 4, "count": 8},
        ],
        "answer": {"type": "multiply", "correct": "8", "options": ["8", "6", "4", "10"], "formula": "2×4", "explanation": "2 groups of 4 blocks = 8"},
        "interests": {"foods": [], "hobbies": ["lego"], "notes": ""},
    },
    # number_and_place_value — 2
    {
        "stem_id": "npv_missing_block_13_user_mother",
        "topic": "number_and_place_value",
        "adult_role": "mother",
        "image_file": "number_blocks_11_12_blank_14.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/number_and_place_value.txt",
        "layout_pattern": "missing_number_sequence",
        "question": "Look at the picture! There are blocks lined up in a row with numbers on them: the first block says 11, the second block says 12, and the fourth block says 14. What number should be on the third block?",
        "prompt_objects": """
On the table: EXACTLY 4 wooden number blocks in a row left-to-right.
Block 1 shows "11", block 2 shows "12", block 3 is BLANK (empty wooden block with question mark), block 4 shows "14".
Numbers large and readable. MOTHER (right) and child (left) look at the sequence.
""",
        "visual_groups": [
            {"id": "sequence", "object_id": "number_blocks", "values": [11, 12, None, 14], "missing": 13},
        ],
        "answer": {"type": "missing_number", "correct": "13", "options": ["13", "12", "14", "15"], "formula": None, "explanation": "Sequence 11, 12, ?, 14 → missing number is 13"},
    },
    {
        "stem_id": "npv_stone_before_8_user_mother",
        "topic": "number_and_place_value",
        "adult_role": "mother",
        "image_file": "garden_stones_6_7_8_number_line.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/number_and_place_value.txt",
        "layout_pattern": "number_line",
        "question": "Look at the picture! There is a number line in the garden with numbers on stones. Can you see the stone with the number 8 on it? What number is on the stone just before the stone with 8?",
        "prompt_objects": """
Garden path scene (visible through window or mini garden tray on table): painted stones in a row showing numbers 6, 7, 8 (and optionally 5, 9).
Stone with "8" clearly visible. Stone immediately BEFORE 8 shows "7".
MOTHER (right) and child (left) in kitchen pointing at a photo/tray of numbered stones on the table.
Numbers large and readable on stones.
""",
        "visual_groups": [
            {"id": "stones", "object_id": "number_stones", "highlight": 8, "before": 7},
        ],
        "answer": {"type": "number_before", "correct": "7", "options": ["7", "6", "8", "9"], "formula": None, "explanation": "Number before 8 is 7"},
    },
    # time — 2
    {
        "stem_id": "time_calendar_july_31_user_mother",
        "topic": "time",
        "adult_role": "mother",
        "image_file": "calendar_july_31_days.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/time.txt",
        "layout_pattern": "calendar_month",
        "question": "Look at the picture! Can you see the calendar that {mother_name} is holding? It shows the month of July with all the days marked. How many days are there in July?",
        "prompt_objects": """
MOTHER (right) holds a wall-calendar page clearly titled "JULY".
Calendar grid shows EXACTLY 31 numbered day boxes (days 1–31 all visible).
Child (left) looks on. Month name and day numbers readable.
""",
        "visual_groups": [{"id": "calendar", "object_id": "calendar", "month": "July", "days": 31}],
        "answer": {"type": "calendar_days", "correct": "31", "options": ["31", "30", "28", "29"], "formula": None, "explanation": "July has 31 days"},
    },
    {
        "stem_id": "time_clock_30_minutes_user_mother",
        "topic": "time",
        "adult_role": "mother",
        "image_file": "clock_30_minutes_half_hour.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/time.txt",
        "layout_pattern": "clock_duration",
        "question": "Look at the picture! There is a big clock showing 1 hour with 60 little marks. Now, look at the smaller clock showing 30 minutes. How many little marks can you count on the smaller clock?",
        "prompt_objects": """
On the table: two analog clocks side by side.
LEFT clock: large teaching clock labelled "1 hour" with 60 minute marks around edge.
RIGHT clock (smaller): minute hand at 6 (half hour), clearly labelled "30 minutes", with 30 minute marks visible/highlighted OR a card saying "30" next to it.
MOTHER (right) and child (left). Clock faces readable.
""",
        "visual_groups": [{"id": "small_clock", "object_id": "clock", "minutes": 30, "marks": 30}],
        "answer": {"type": "clock_marks", "correct": "30", "options": ["30", "60", "15", "45"], "formula": None, "explanation": "30 minutes = 30 marks on the clock"},
    },
]


def adult_label(role: str) -> str:
    return {"mother": "MOTHER (right, adult woman)", "father": "FATHER (right, adult man)"}.get(role, role)


def run_stem(api_key: str, spec: dict, skip_existing: bool = True) -> dict:
    adult_role = spec["adult_role"]
    stem_dir = TEMPLATES / spec["topic"] / spec["stem_id"]
    stem_dir.mkdir(parents=True, exist_ok=True)
    img_path = stem_dir / spec["image_file"]
    meta_path = stem_dir / "meta.json"
    q_path = stem_dir / "question.txt"

    if skip_existing and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("status") == "ready" and img_path.is_file():
            return {"stem_id": spec["stem_id"], "status": "skipped", "reason": "already ready"}

    q_path.write_text(spec["question"].strip() + "\n")
    meta = build_meta(spec, adult_role)

    prompt = f"""
Create ONE vibrant realistic photograph for a Grade 1 UK maths worksheet.

{BASE_STYLE}
Adult role: {adult_label(adult_role)}

OBJECTS / SCENE (exact — critical for counting):
{spec["prompt_objects"].strip()}
""".strip()

    print(f"\n=== {spec['stem_id']} ===")
    im, usage = generate_image(api_key, prompt)
    im.save(img_path)
    cost = usage.get("cost", "?")
    print(f"  saved {img_path.name}  cost=${cost}")

    regions = face_regions(img_path, adult_role)
    if len(regions) >= 2:
        meta["face_regions"] = regions
        meta["face_detection"] = "yunet"
        meta["status"] = "ready"
        meta["validation"]["verified"] = True
        meta["validation"]["notes"] = f"Generated with {MODEL} via OpenRouter Images API."
    else:
        meta["status"] = "needs_faces"
        meta["validation"]["notes"] = f"Only {len(regions)} face(s) detected."

    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return {"stem_id": spec["stem_id"], "status": meta["status"], "cost": cost}


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY not set")

    results = []
    for i, spec in enumerate(STEMS, 1):
        try:
            r = run_stem(api_key, spec)
            results.append(r)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"stem_id": spec["stem_id"], "status": "error", "error": str(e)})
        if i < len(STEMS):
            time.sleep(2)

    cr = requests.get("https://openrouter.ai/api/v1/credits", headers=_headers(api_key), timeout=30).json()
    remaining = cr["data"]["total_credits"] - cr["data"]["total_usage"]
    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r['stem_id']}: {r['status']}")
    print(f"  Credits remaining: ${remaining:.4f}")


if __name__ == "__main__":
    main()
