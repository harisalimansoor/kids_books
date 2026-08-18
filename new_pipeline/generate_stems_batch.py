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
Don't add more than two hands for a person.
Style: ONE vibrant realistic photograph, square 1:1, bright natural light, more background visible.
Child (left, ~5–7 years) + adult (right) BOTH look at the CAMERA with clear front-facing smiles (for face swap). Only these two people.
They are mid-activity together (helping, pointing, pouring, building, or playing) — not a stiff posed portrait.
CLOTHING (modest — children's workbook): mother/adult woman must wear a high crew-neck or modest round collar top that fully covers chest and shoulders. No deep V-neck, off-shoulder, wrap cleavage, or low scoop. Adult man: casual modest shirt.
Don't add more than two hands for a person.
HANDS: two per person, 5 normal fingers, simple activity pose. No extra people.
No text overlays except numbers/labels that MUST be readable for the maths.
Don't add more than two hands for a person.
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
Don't add more than two hands for a person.
ACTIVITY: they are PLAYING and BUILDING with wooden cubes on a play-table, not standing still posing with a basket.
Freeze-frame: child LEFT is placing a cube onto a small build. Mother RIGHT steadies her basket and points at the build. Both look at the CAMERA and smile WHILE building.
Don't add more than two hands for a person.

BLOCK COUNTS (Grade 1 — exact, rigid grids):
- Mother RIGHT: a shallow wicker basket with EXACTLY 8 colourful wooden cubes in a neat 2×4 grid, all fully visible from above. NEVER 7. NEVER 9.
- Child LEFT on the table: EXACTLY 4 colourful cubes being built into a tiny 2×2 square wall/house (two on the bottom, two on top), ALL four cube faces fully visible, not hiding each other. NEVER 5. NEVER 3.
- Clear gap between the basket and the 2×2 build
- TOTAL cubes in the WHOLE image: EXACTLY 12 (8 + 4). Zero extra cubes on the floor, sofa, or in hands.
- Any cube being touched is already one of the 12
Don't add more than two hands for a person.
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
        "question": "Look at the picture! {mother_name} has a carton of apples. You can see 9 apples around the carton, but 3 of them have a big red X marked through them. How many apples are left that {mother_name} can still eat?",
        "prompt_objects": """
Don't add more than two hands for a person.
ACTIVITY: they are PACKING apples into a cardboard fruit CARTON (produce box), mid-action, not using a wicker basket.
Freeze-frame: child LEFT is placing an unmarked apple into the carton. Mother RIGHT steadies the carton. Both look at the CAMERA and smile WHILE packing.
Don't add more than two hands for a person.

APPLE COUNTS (Grade 1 subtraction — exact 3x3):
- Around / in front of ONE open cardboard fruit carton: EXACTLY 9 red apples in a neat 3x3 grid, all fully visible, not stacked. NEVER 8. NEVER 10.
- EXACTLY 3 of those 9 apples have a bold red X drawn through them. The other 6 have NO X and no marks.
- Hands EMPTY of extra apples. Any apple being touched is already one of the 9.
- Zero extra apples. No wicker basket.
- No chalkboard, no equation, no numbers that give away 6
Don't add more than two hands for a person.
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
ACTIVITY: joyful kitchen baking — they are measuring water together for a recipe (pouring into a jug), not just posing beside it.
Bright kitchen with more background: window, shelves, mixing bowl, wooden spoon, recipe card as props (props must NOT look like extra jugs).
Child (left) helps hold the jug or points at the water line. Mother (right) pours from a small kettle/tap jug. Front-facing smiles.

COUNT / MEASURE (exact):
- ONE clear glass measuring jug on the table, labelled "1 L" in large readable letters
- Readable side marks: 250, 500, 750, 1000
- Blue water filled EXACTLY to the 500 ml mid line (half the jug)
- A small yellow sticky note beside the jug may say "500"
- TOTAL measuring jugs in the whole image: EXACTLY 1
- Zero extra jugs, glasses of water that look like measuring jugs, or other water levels
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
Don't add more than two hands for a person.
ACTIVITY: they are PLAYING marbles in a GARDEN, sitting on the grass, not posing at an indoor table.
Freeze-frame: both sit on a picnic blanket / grass. Child LEFT is flicking/rolling a marble. Mother RIGHT is pointing at the groups. Both look at the CAMERA and smile WHILE playing.
BACKGROUND: sunny garden — green lawn, flower beds, trees, maybe a fence. No kitchen, no sofa.
Don't add more than two hands for a person.

MARBLE GROUPS (Grade 1 multiplication — exact):
- On the blanket/grass in a neat row: EXACTLY 3 small chalk circles (or 3 tiny bowls), clearly separated.
- Each circle/bowl contains EXACTLY 2 colourful glass marbles. NEVER 1. NEVER 3.
- 3 groups × 2 = EXACTLY 6 marbles in the WHOLE image.
- Any marble being touched is already one of those 6.
- Zero extra marbles on the grass, in pockets, or in hands besides the 6.
Don't add more than two hands for a person.
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
Don't add more than two hands for a person.
ACTIVITY: they are PLAYING and BUILDING two small block towers, not sitting still behind a posed 2x2 layout.
Freeze-frame: child LEFT is placing a cube on THEIR tower. Father RIGHT is placing a cube on HIS tower. Both look at the CAMERA and smile WHILE building.
Don't add more than two hands for a person.

BLOCK GROUPS (Grade 1 multiplication — exact):
- EXACTLY 2 separate builds on the table, with a clear empty gap between them.
- LEFT build (child): EXACTLY 4 colourful wooden cubes as a tiny 2x2 tower (2 on the bottom, 2 on top), ALL four cube faces fully visible. NEVER 5.
- RIGHT build (father): EXACTLY 4 colourful wooden cubes as a matching tiny 2x2 tower, ALL four cube faces fully visible. NEVER 5.
- TOTAL cubes in the WHOLE image: EXACTLY 8 (2 groups of 4). Zero extra cubes on the floor, sofa, or in hands.
- Any cube being touched is already one of that group's 4.
Don't add more than two hands for a person.
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
ACTIVITY: joyful time-learning at a kitchen table — they are practising "half an hour" together (child pointing at the smaller clock, mother helping), not a stiff posed lineup of clocks.
Soft kitchen/living-room background: window, lamp, maybe a baking tray of cookies as a "waiting 30 minutes" cue (cookies must NOT look like extra clocks).

CLOCKS (exact — Grade 1):
- EXACTLY 2 analog teaching clocks on the table, side by side, faces fully visible
- LEFT large clock: labelled "1 hour", minute hand at 12, 60 little marks around the edge; a card/sticky may say "60"
- RIGHT smaller clock: minute hand clearly at 6 (half past), labelled "30 minutes"; a big yellow sticky note says "30"
- TOTAL clocks in the whole image: EXACTLY 2
- Zero extra clocks on walls or shelves that a child might count
- Numbers 60 and 30 must be readable. No other people.
""",
        "visual_groups": [{"id": "small_clock", "object_id": "clock", "minutes": 30, "marks": 30}],
        "answer": {"type": "clock_marks", "correct": "30", "options": ["30", "60", "15", "45"], "formula": None, "explanation": "30 minutes = 30 marks on the clock"},
    },
    # addition — 2 new activity stems
    {
        "stem_id": "add_books_2_1_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "image_file": "mother_2_books_child_1_book_reading.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/addition.txt",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {mother_name} has 2 books in front of her, and {user_name} has 1 book in front of {user_name}. How many books are there altogether?",
        "prompt_objects": """
Don't add more than two hands for a person.
ACTIVITY (must look mid-action, NOT a posed portrait): they are READING together.
Freeze-frame of a reading nook: child's 1 book is OPEN and the child is turning a page with both hands.
Mother is opening / turning a page of one of HER 2 books with one hand; her other hand rests on her second closed book.
Both still look at the CAMERA and smile WHILE reading — caught in the act, not sitting still with hands on the table edge.
NOT allowed: stiff studio pose, both hands flat on the table, just pointing at closed books.
Bright living-room: sofa, lamp, cushions; blurry bookshelf spines in the background (background books must NOT look like extra countable picture books on the table).
Don't add more than two hands for a person.

BOOK COUNTS (Grade 1 — exact, neat layout):
- Child LEFT: EXACTLY 1 children's picture book in front of the child, cover still fully visible (slightly open while turning a page)
- Mother RIGHT: EXACTLY 2 children's picture books in front of the mother (one being opened, one closed), small gap between them
- Clear gap between the child's 1 book and the mother's 2 books
- TOTAL picture books on the table in the WHOLE image: EXACTLY 3
- Zero extra books in laps, on the sofa, or held besides those 3
- Optional small numbers 1, 2, 3 on the three covers — no other text
Don't add more than two hands for a person.
""",
        "visual_groups": [
            {"id": "mother", "owner": "mother", "object_id": "books", "count": 2},
            {"id": "child", "owner": "child", "object_id": "books", "count": 1},
        ],
        "answer": {"type": "count_total", "correct": "3", "options": ["3", "2", "1", "4"], "formula": "2+1", "explanation": "2 books + 1 book = 3"},
        "interests": {"foods": [], "hobbies": ["reading"], "notes": "Reading activity addition stem."},
    },
    {
        "stem_id": "add_mangoes_2_5_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "image_file": "mother_5_mangoes_child_2_mangoes_bowl.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/addition.txt",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {mother_name} has 5 mangoes in a bowl in front of her, and {user_name} has 2 mangoes in a basket in front of {user_name}. How many mangoes are there altogether?",
        "prompt_objects": """
Don't add more than two hands for a person.
ACTIVITY (must look mid-action, NOT a posed portrait): they are PICKING mangoes in a garden, SITTING ON THE GROUND (grass), not standing at a kitchen counter.
Freeze-frame: both sit cross-legged on the grass under mango trees. Child (left) rests both empty hands on the rim of THEIR small basket. Mother (right) points at a mango tree with one empty hand; her other empty hand rests on the rim of HER wide bowl. Both look at the CAMERA and smile WHILE sitting in the garden.
HANDS ARE EMPTY: zero mangoes in anyone's hands, zero mangoes in mid-air, zero mangoes being held up.
BACKGROUND: mango trees with yellow-orange fruit on the branches; green grass; a few fallen mangoes on the grass BEHIND them (soft focus scenery, not in the basket or bowl).
Don't add more than two hands for a person.

MANGO COUNTS (Grade 1 — exact, neat layout — rigid grids):
- Child LEFT: EXACTLY 2 whole yellow-orange mangoes already inside a small open basket, both fully visible side by side, not stacked. NEVER 3. Never a mango in the child's hands.
- Mother RIGHT: EXACTLY 5 whole mangoes already inside ONE wide bowl, in a neat 2+3 grid (front row of 2, back row of 3) with small gaps so a child can count 1-2-3-4-5. NEVER 6. Never a mango in the mother's hands.
- Clear gap between the child's basket and the mother's bowl
- TOTAL mangoes in the basket + bowl: EXACTLY 7 (2 + 5). Forbidden: 6 in the bowl, 3 in the basket, extra fruit held.
- Extra mangoes ONLY on distant trees and on the grass behind them, slightly out of focus
- No chalkboard, no equation, no numbers
Don't add more than two hands for a person.
""",
        "visual_groups": [
            {"id": "mother", "owner": "mother", "object_id": "mangoes", "count": 5, "container": "bowl"},
            {"id": "child", "owner": "child", "object_id": "mangoes", "count": 2, "container": "basket"},
        ],
        "answer": {"type": "count_total", "correct": "7", "options": ["7", "5", "2", "6"], "formula": "5+2", "explanation": "5 mangoes + 2 mangoes = 7"},
        "interests": {"foods": ["mangoes"], "hobbies": [], "notes": "Fruit-sharing addition stem."},
    },
    {
        "stem_id": "add_stickers_2_3_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "image_file": "mother_3_stickers_child_2_stickers_decorating.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/addition.txt",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {mother_name} has 3 stickers in front of her, and {user_name} has 2 stickers in front of {user_name}. How many stickers are there altogether?",
        "prompt_objects": """
Don't add more than two hands for a person.
ACTIVITY (must look mid-action, NOT a posed portrait): they are DECORATING greeting cards with stickers.
Freeze-frame of a craft table: child is peeling / pressing down one of THEIR 2 stickers onto a small blank card.
Mother is pressing one of HER 3 stickers onto her card. Hands busy sticking, not resting on the table.
Both look at the CAMERA and smile WHILE decorating.
NOT allowed: stiff studio pose; a sticker sheet full of extra stickers; numbers that give away the answer.
Bright living-room craft corner: paper, glue stick as props (props must NOT look like extra stickers).
Don't add more than two hands for a person.

STICKER COUNTS (Grade 1 — exact, neat layout):
- Child LEFT: EXACTLY 2 large colourful stickers (star + heart), fully visible, in front of the child on/near their small card
- Mother RIGHT: EXACTLY 3 large colourful stickers (star, heart, flower), fully visible, in a small row in front of the mother on/near her card
- Clear gap between the child's 2 stickers and the mother's 3 stickers
- TOTAL stickers in the WHOLE image: EXACTLY 5
- Zero extra stickers on leftover backing sheets, walls, or clothes
Don't add more than two hands for a person.
""",
        "visual_groups": [
            {"id": "mother", "owner": "mother", "object_id": "stickers", "count": 3},
            {"id": "child", "owner": "child", "object_id": "stickers", "count": 2},
        ],
        "answer": {"type": "count_total", "correct": "5", "options": ["5", "3", "2", "4"], "formula": "3+2", "explanation": "3 stickers + 2 stickers = 5"},
        "interests": {"foods": [], "hobbies": ["crafts"], "notes": "Sticker-decorating addition stem."},
    },
    {
        "stem_id": "add_sweets_2_4_user_mother",
        "topic": "addition",
        "adult_role": "mother",
        "image_file": "mother_4_sweets_child_2_sweets_jar.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/addition.txt",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {mother_name} has 4 sweets in a jar in front of her, and {user_name} has 2 sweets in a bowl in front of {user_name}. How many sweets are there altogether?",
        "prompt_objects": """
Don't add more than two hands for a person.
ACTIVITY (must look mid-action, NOT a posed portrait): they are PACKING colourful wrapped sweets together.
Freeze-frame: child is placing a wrapped sweet into THEIR small bowl (the other sweet already sits in the bowl).
Mother is placing wrapped sweets into HER clear glass jar — fingers mid-place, not just holding the jar still.
Both look at the CAMERA and smile WHILE packing sweets.
NOT allowed: stiff posed lineup; chalkboard; written equation; numbers that give away the answer.
Bright kitchen: window, empty wrapping paper as props (props must NOT look like extra sweets).
Don't add more than two hands for a person.

SWEET COUNTS (Grade 1 — exact, neat layout):
- Child LEFT: EXACTLY 2 colourful foil-wrapped sweets in a small open bowl in front of the child, both fully visible side by side, not stacked
- Mother RIGHT: EXACTLY 4 colourful foil-wrapped sweets in ONE clear glass jar in front of the mother, in a neat 2×2 grid, all fully visible through the glass
- Clear gap between the child's bowl and the mother's jar
- TOTAL sweets in the WHOLE image: EXACTLY 6
- Zero extra sweets on the counter, in bags, or in the air — any sweet being touched is already one of the 6
Don't add more than two hands for a person.
""",
        "visual_groups": [
            {"id": "mother", "owner": "mother", "object_id": "sweets", "count": 4, "container": "jar"},
            {"id": "child", "owner": "child", "object_id": "sweets", "count": 2, "container": "bowl"},
        ],
        "answer": {"type": "count_total", "correct": "6", "options": ["6", "4", "2", "5"], "formula": "4+2", "explanation": "4 sweets + 2 sweets = 6"},
        "interests": {"foods": ["sweets"], "hobbies": [], "notes": "Sweet-packing addition stem."},
    },
    {
        "stem_id": "sub_pencils_6_2_case_user_mother",
        "topic": "subtraction",
        "adult_role": "mother",
        "image_file": "mother_6_pencils_child_puts_2_in_case.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/subtraction.txt",
        "layout_pattern": "take_away_remain",
        "question": "Look at the picture! {mother_name} has 6 pencils on the table. {user_name} is putting 2 of them into a pencil case. How many pencils are left on the table?",
        "prompt_objects": """
Don't add more than two hands for a person.
ACTIVITY (must look mid-action, NOT a posed portrait): they are PACKING a school pencil case together.
Freeze-frame: child (left) is sliding a colourful pencil INTO an open pencil case. Mother (right) is arranging the pencils still on the table.
Both look at the CAMERA and smile WHILE packing.
NOT allowed: stiff posed lineup; chalkboard; written equation; numbers that give away the answer.
Bright living-room / homework table: lamp, notebook as props (props must NOT look like extra pencils).
Don't add more than two hands for a person.

PENCIL COUNTS (Grade 1 — exact, neat layout):
- On the wooden table in front of mother: EXACTLY 4 colourful pencils left in ONE straight row, spaced apart, fully visible
- Inside / going into the open pencil case in front of the child: EXACTLY 2 colourful pencils, fully visible
- TOTAL pencils in the WHOLE image: EXACTLY 6
- The pencil the child is touching is already one of the 2 in the case — do not add a 7th pencil in the air
- Zero extra pencils in cups, on notebooks, or behind them
Don't add more than two hands for a person.
""",
        "visual_groups": [
            {"id": "all", "owner": "mother", "object_id": "pencils", "count": 6},
            {"id": "taken", "owner": "child", "object_id": "pencils", "count": 2, "container": "pencil_case"},
            {"id": "remaining", "owner": "table", "object_id": "pencils", "count": 4, "notes": "left on the table"},
        ],
        "answer": {"type": "count_remaining", "correct": "4", "options": ["4", "6", "2", "3"], "formula": "6-2", "explanation": "6 pencils − 2 in the case = 4 left on the table"},
        "interests": {"foods": [], "hobbies": ["drawing"], "notes": "Pencil-case packing subtraction stem."},
    },
    {
        "stem_id": "sub_shells_5_2_bucket_user_mother",
        "topic": "subtraction",
        "adult_role": "mother",
        "image_file": "mother_5_shells_child_takes_2.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/subtraction.txt",
        "layout_pattern": "take_away_remain",
        "question": "Look at the picture! {mother_name} has 5 shells in her bucket. {user_name} is taking 2 shells out to look at them. How many shells are left in the bucket?",
        "prompt_objects": """
Don't add more than two hands for a person.
ACTIVITY (must look mid-action, NOT a posed portrait): they are SORTING seashells from a beach bucket.
Freeze-frame: child (left) is picking up / examining 2 shells on a small towel. Mother (right) is looking into the bucket, hands at the remaining shells.
Both look at the CAMERA and smile WHILE sorting shells.
NOT allowed: stiff posed lineup; chalkboard; written equation; numbers that give away the answer.
Bright living-room beach-play corner or sunny patio: towel, bucket, plant as props (props must NOT look like extra shells).
Don't add more than two hands for a person.

SHELL COUNTS (Grade 1 — exact, neat layout):
- Inside mother's open bucket: EXACTLY 3 seashells remaining, spaced apart, fully visible
- On the child's small towel in front of the child: EXACTLY 2 seashells taken out, side by side, fully visible
- TOTAL shells in the WHOLE image: EXACTLY 5
- Any shell being held is already one of these 5
- Zero extra shells on the floor, in the background, or in the air
Don't add more than two hands for a person.
""",
        "visual_groups": [
            {"id": "all", "owner": "mother", "object_id": "shells", "count": 5, "container": "bucket"},
            {"id": "taken", "owner": "child", "object_id": "shells", "count": 2, "notes": "taken out to look at"},
            {"id": "remaining", "owner": "mother", "object_id": "shells", "count": 3, "container": "bucket", "notes": "left in the bucket"},
        ],
        "answer": {"type": "count_remaining", "correct": "3", "options": ["3", "5", "2", "4"], "formula": "5-2", "explanation": "5 shells − 2 taken out = 3 left in the bucket"},
        "interests": {"foods": [], "hobbies": ["beach"], "notes": "Shell-sorting subtraction stem."},
    },
    {
        "stem_id": "add_apples_3_2_user_grandfather",
        "topic": "addition",
        "adult_role": "grandfather",
        "image_file": "grandfather_3_apples_child_2_apples_picking.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/addition.txt",
        "layout_pattern": "two_group_add",
        "question": "Look at the picture! {grandfather_name} has 3 apples in his basket, and {user_name} has 2 apples in front of {user_name}. How many apples are there altogether?",
        "prompt_objects": """
Don't add more than two hands for a person.
ACTIVITY (must look mid-action, NOT a posed portrait): they are PICKING apples together in a sunny garden.
Freeze-frame: child (left) is placing an apple into THEIR small pile / holding one of THEIR 2 apples. Grandfather (right) is putting apples into HIS wicker basket.
Both look at the CAMERA and smile WHILE picking fruit.
NOT allowed: stiff posed lineup; chalkboard; written equation; numbers that give away the answer.
Garden orchard: apple TREES clearly visible in the background with red apples on the branches. A few fallen red apples on the grass in the BACKGROUND (soft focus, behind the people — NOT on the table, NOT countable with the maths groups).
Don't add more than two hands for a person.

APPLE COUNTS (Grade 1 — exact foreground layout):
- Child LEFT: EXACTLY 2 red apples on the table in front of the child, both fully visible side by side, not stacked
- Grandfather RIGHT: EXACTLY 3 red apples in ONE open wicker basket, spaced apart so a child can count 1-2-3
- Clear gap between the child's 2 apples and the grandfather's basket
- Foreground table+basket apples: EXACTLY 5
- Extra apples ONLY on distant trees and on the grass behind them, slightly out of focus
Don't add more than two hands for a person.
""",
        "visual_groups": [
            {"id": "grandfather", "owner": "grandfather", "object_id": "apples", "count": 3, "container": "basket"},
            {"id": "child", "owner": "child", "object_id": "apples", "count": 2},
        ],
        "answer": {"type": "count_total", "correct": "5", "options": ["5", "3", "2", "4"], "formula": "3+2", "explanation": "3 apples + 2 apples = 5"},
        "interests": {"foods": ["apples"], "hobbies": ["gardening"], "notes": "Apple-picking with grandfather addition stem."},
    },
    {
        "stem_id": "sub_marbles_7_2_bowl_user_grandfather",
        "topic": "subtraction",
        "adult_role": "grandfather",
        "image_file": "grandfather_7_marbles_child_takes_2.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/subtraction.txt",
        "layout_pattern": "take_away_remain",
        "question": "Look at the picture! {grandfather_name} has 7 marbles in a bowl. {user_name} is taking 2 marbles out to play. How many marbles are left in the bowl?",
        "prompt_objects": """
Don't add more than two hands for a person.
ACTIVITY (must look mid-action, NOT a posed portrait): they are PLAYING a game of marbles.
Freeze-frame: a small chalk circle on the table. Child (left) is Flicking / rolling one of THEIR 2 marbles toward the circle with a finger — caught mid-shot, not sitting still.
Grandfather (right) leans in, one hand on his bowl of remaining marbles, the other hand ready to play / pointing at the circle.
Both look at the CAMERA and smile WHILE playing.
NOT allowed: stiff posed lineup; both hands just holding a bowl; numbers that give away the answer.
Don't add more than two hands for a person.

MARBLE COUNTS — rigid layout, Grade 1:
- White shallow bowl in front of grandfather: EXACTLY 5 colourful glass marbles, all fully visible, not stacked, small gaps.
- On the table in/near the chalk circle in front of the child: EXACTLY 2 colourful glass marbles (one may be under the child's flicking finger).
- TOTAL marbles in the WHOLE image: EXACTLY 7. Count them: 5 in bowl + 2 in play.
- Zero marbles in bags, on the floor, in laps, or in the air besides those 7.
- No chalkboard, no numbers, no equation.
Don't add more than two hands for a person.
""",
        "visual_groups": [
            {"id": "all", "owner": "grandfather", "object_id": "marbles", "count": 7, "container": "bowl"},
            {"id": "taken", "owner": "child", "object_id": "marbles", "count": 2, "notes": "taken out to play"},
            {"id": "remaining", "owner": "grandfather", "object_id": "marbles", "count": 5, "container": "bowl", "notes": "left in the bowl"},
        ],
        "answer": {"type": "count_remaining", "correct": "5", "options": ["5", "7", "2", "4"], "formula": "7-2", "explanation": "7 marbles − 2 taken out = 5 left in the bowl"},
        "interests": {"foods": [], "hobbies": ["marbles"], "notes": "Marbles with grandfather subtraction stem."},
    },
]


def adult_label(role: str) -> str:
    return {
        "mother": "MOTHER (right, adult woman)",
        "father": "FATHER (right, adult man)",
        "grandfather": "GRANDFATHER (right, older adult man, grey/white hair, casual modest shirt or jumper)",
        "grandmother": "GRANDMOTHER (right, older adult woman, modest crew-neck top)",
    }.get(role, role)


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
