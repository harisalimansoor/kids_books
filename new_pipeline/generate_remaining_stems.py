#!/usr/bin/env python3
"""Generate remaining topic stems with low, count-locked object totals."""
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
ONE vibrant realistic photograph, square 1:1, bright kitchen/living room, more background visible.
LEFT: young child (~6), front-facing camera, smiling.
RIGHT: adult, front-facing camera, smiling.
Only these two people. Faces clear for face-swap.
They are mid-activity together (helping, pointing, pouring) — not a stiff posed portrait.
CLOTHING (modest — children's workbook): mother/adult woman must wear a high crew-neck or modest round collar top that fully covers chest and shoulders. No deep V-neck, off-shoulder, wrap cleavage, or low scoop.
CRITICAL: object counts must be exact and easily countable — spaced apart, not stacked, not overlapping.
HANDS: two per person, 5 fingers. No extra people. No text overlays except required numbers.
""".strip()


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
            "notes": "Awaiting visual count check",
        },
        "source": {
            "cluster_file": spec.get("cluster_file", ""),
            "notes": spec.get("source_notes", "Count-locked Grade 1 stem"),
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
    # --- geometry (2) ---
    {
        "stem_id": "geo_square_shape_user_mother",
        "topic": "geometry",
        "adult_role": "mother",
        "image_file": "mother_holding_square_paper.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/geometry.txt",
        "layout_pattern": "shape_identify",
        "question": "Look at the picture! Can you see the piece of paper that {mother_name} is holding? It has 4 equal sides and 4 corners. What shape is it?",
        "prompt_objects": """
MOTHER (right, adult woman) holds up ONE bright yellow paper cutout toward camera.
The cutout is a perfect SQUARE: 4 equal sides, 4 right-angle corners (not a rectangle, not a diamond).
Child (left) smiles at the square. No other shapes on the table.
""",
        "visual_groups": [{"id": "shape", "object_id": "square", "sides": 4, "equal_sides": True, "count": 1}],
        "answer": {
            "type": "shape_name",
            "correct": "square",
            "options": ["square", "circle", "triangle", "rectangle"],
            "formula": None,
            "explanation": "4 equal sides and 4 corners = square",
        },
        "expected": "1 yellow square paper",
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
On the table LEFT in front of child: EXACTLY 2 golden 5-pointed star cutouts, spaced apart.
On the table RIGHT in front of mother: EXACTLY 3 golden 5-pointed star cutouts, spaced apart.
Two clear groups. No other stars or shapes. Total = 5 stars.
""",
        "visual_groups": [
            {"id": "child_stars", "owner": "child", "object_id": "stars", "count": 2},
            {"id": "mother_stars", "owner": "mother", "object_id": "stars", "count": 3},
        ],
        "answer": {
            "type": "count_total",
            "correct": "5",
            "options": ["5", "2", "3", "6"],
            "formula": "2+3",
            "explanation": "2 stars + 3 stars = 5 shapes",
        },
        "expected": "2 stars left + 3 stars right",
    },
    # --- multiplication_and_division (2) ---
    {
        "stem_id": "mult_marbles_3x2_user_mother",
        "topic": "multiplication_and_division",
        "adult_role": "mother",
        "image_file": "mother_3_groups_2_marbles.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/multiplication_and_division.txt",
        "layout_pattern": "equal_groups",
        "question": "Look at the picture! {mother_name} has 3 groups of 2 marbles in front of her. How many marbles are there altogether?",
        "prompt_objects": """
On the table: EXACTLY 3 small clear glass bowls in a row.
Each bowl contains EXACTLY 2 colourful marbles (no more).
3 bowls × 2 marbles = 6 marbles total. Bowls spaced. No marbles outside bowls.
""",
        "visual_groups": [
            {"id": "groups", "owner": "mother", "object_id": "marbles", "groups": 3, "per_group": 2, "count": 6},
        ],
        "answer": {
            "type": "multiply",
            "correct": "6",
            "options": ["6", "5", "3", "8"],
            "formula": "3×2",
            "explanation": "3 groups of 2 marbles = 6",
        },
        "interests": {"foods": [], "hobbies": ["marbles"], "notes": ""},
        "expected": "3 bowls with 2 marbles each",
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
On the table: EXACTLY 2 separate groups of colourful wooden cubes, clearly separated by a gap.
LEFT group: EXACTLY 4 cubes in a neat 2×2 square.
RIGHT group: EXACTLY 4 cubes in a neat 2×2 square.
Total = 8 cubes. No extra blocks. FATHER (right, adult man) and child (left).
""",
        "visual_groups": [
            {"id": "groups", "owner": "father", "object_id": "blocks", "groups": 2, "per_group": 4, "count": 8},
        ],
        "answer": {
            "type": "multiply",
            "correct": "8",
            "options": ["8", "6", "4", "10"],
            "formula": "2×4",
            "explanation": "2 groups of 4 blocks = 8",
        },
        "interests": {"foods": [], "hobbies": ["lego"], "notes": ""},
        "expected": "2 groups of 4 blocks",
    },
    # --- number_and_place_value (2) ---
    {
        "stem_id": "npv_missing_block_13_user_mother",
        "topic": "number_and_place_value",
        "adult_role": "mother",
        "image_file": "number_blocks_11_12_blank_14.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/number_and_place_value.txt",
        "layout_pattern": "missing_number_sequence",
        "question": "Look at the picture! There are blocks lined up in a row with numbers on them: the first block says 11, the second block says 12, and the fourth block says 14. What number should be on the third block?",
        "prompt_objects": """
On the table: EXACTLY 4 large wooden number cubes in one left-to-right row.
Cube 1 clearly shows "11". Cube 2 clearly shows "12". Cube 3 is blank with a big "?" on it. Cube 4 clearly shows "14".
Numbers large and readable. No other number blocks.
""",
        "visual_groups": [
            {"id": "sequence", "object_id": "number_blocks", "values": [11, 12, None, 14], "missing": 13, "count": 4},
        ],
        "answer": {
            "type": "missing_number",
            "correct": "13",
            "options": ["13", "12", "14", "15"],
            "formula": None,
            "explanation": "Sequence 11, 12, ?, 14 → missing number is 13",
        },
        "expected": "4 blocks: 11, 12, ?, 14",
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
On the table: a mini garden tray / photo showing EXACTLY 3 painted stones in a row left-to-right.
Stone 1 shows big number "6". Stone 2 shows big number "7". Stone 3 shows big number "8".
Numbers large and readable. Stone 7 is immediately before stone 8.
MOTHER (right) and child (left) point at the stones. No other numbered stones.
""",
        "visual_groups": [
            {"id": "stones", "object_id": "number_stones", "values": [6, 7, 8], "highlight": 8, "before": 7, "count": 3},
        ],
        "answer": {
            "type": "number_before",
            "correct": "7",
            "options": ["7", "6", "8", "9"],
            "formula": None,
            "explanation": "Number before 8 is 7",
        },
        "expected": "stones 6, 7, 8",
    },
    # --- time (2) ---
    {
        "stem_id": "time_calendar_july_31_user_mother",
        "topic": "time",
        "adult_role": "mother",
        "image_file": "calendar_july_31_days.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/time.txt",
        "layout_pattern": "calendar_month",
        "question": "Look at the picture! Can you see the calendar that {mother_name} is holding? It shows the month of July with all the days marked. How many days are there in July?",
        "prompt_objects": """
MOTHER (right) holds a wall-calendar page clearly titled "JULY" in large letters.
A sticky note or printed badge on the calendar clearly shows "31 days".
Calendar grid with numbered days 1–31 visible (July). Child (left) looks on.
Make the month name JULY and the number 31 very readable.
""",
        "visual_groups": [{"id": "calendar", "object_id": "calendar", "month": "July", "days": 31}],
        "answer": {
            "type": "calendar_days",
            "correct": "31",
            "options": ["31", "30", "28", "29"],
            "formula": None,
            "explanation": "July has 31 days",
        },
        "expected": "July calendar with 31 days",
    },
    {
        "stem_id": "time_clock_half_hour_user_mother",
        "topic": "time",
        "adult_role": "mother",
        "image_file": "clock_30_minutes_half_hour.png",
        "cluster_file": "new_pipeline/Question clusters for grade 1/time.txt",
        "layout_pattern": "clock_duration",
        "question": "Look at the picture! There is a big clock showing 1 hour with 60 little marks. Now, look at the smaller clock showing 30 minutes. How many little marks can you count on the smaller clock?",
        "prompt_objects": """
On the table: two analog teaching clocks side by side.
LEFT large clock: labelled "1 hour" / "60 minutes", minute hand at 12.
RIGHT smaller clock: minute hand clearly at 6 (half past), with a big yellow sticky note saying "30".
MOTHER (right) and child (left). Labels 60 and 30 must be readable.
""",
        "visual_groups": [
            {"id": "big_clock", "object_id": "clock", "minutes": 60, "marks": 60},
            {"id": "small_clock", "object_id": "clock", "minutes": 30, "marks": 30},
        ],
        "answer": {
            "type": "clock_marks",
            "correct": "30",
            "options": ["30", "60", "15", "45"],
            "formula": None,
            "explanation": "30 minutes = 30 marks on the smaller clock",
        },
        "expected": "two clocks, small one labelled 30",
    },
    # --- measurement 2nd ---
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
        "visual_groups": [{"id": "jug", "object_id": "water", "volume_ml": 500, "container": "jug", "max_l": 1}],
        "answer": {
            "type": "volume_ml",
            "correct": "500",
            "options": ["500", "250", "750", "1000"],
            "formula": None,
            "explanation": "Water level at 500 ml mark on 1 L jug",
        },
        "expected": "1L jug water at 500ml",
    },
]


def run_stem(api_key: str, spec: dict) -> dict:
    adult = spec["adult_role"]
    stem_dir = TEMPLATES / spec["topic"] / spec["stem_id"]
    stem_dir.mkdir(parents=True, exist_ok=True)
    img_path = stem_dir / spec["image_file"]
    meta_path = stem_dir / "meta.json"
    q_path = stem_dir / "question.txt"

    if meta_path.exists() and img_path.is_file():
        meta = json.loads(meta_path.read_text())
        if meta.get("status") == "ready" and meta.get("validation", {}).get("verified"):
            return {"stem_id": spec["stem_id"], "status": "skipped", "cost": 0}

    q_path.write_text(spec["question"].strip() + "\n")
    meta = build_meta(spec, adult)
    adult_label = {
        "mother": "MOTHER (right, adult woman)",
        "father": "FATHER (right, adult man)",
    }.get(adult, adult)

    prompt = f"""{STYLE}
Adult role: {adult_label}

OBJECTS / SCENE (exact counts — Grade 1 maths worksheet):
{spec['prompt_objects'].strip()}
""".strip()

    print(f"\n=== {spec['stem_id']} ===")
    print(f"  expect: {spec.get('expected')}")
    im, usage = generate(api_key, prompt)
    im.save(img_path)
    cost = usage.get("cost", "?")
    print(f"  saved {img_path.name}  ${cost}")

    regions = face_regions(img_path, adult)
    if len(regions) >= 2:
        meta["face_regions"] = regions
        meta["face_detection"] = "yunet"
        meta["status"] = "ready"
        meta["validation"]["verified"] = False  # human/visual check still needed
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
