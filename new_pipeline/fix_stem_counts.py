#!/usr/bin/env python3
"""Fix stem images so object counts match question.txt / meta.json."""
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
ONE vibrant realistic photograph, square 1:1, bright kitchen/living room.
LEFT: young child (~6), front-facing camera, smiling.
RIGHT: adult, front-facing camera, smiling.
Only these two people. Keep faces clear for face swap.
""".strip()


def headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8504",
    }


def call_images(api_key: str, prompt: str, ref_path: Path | None = None) -> tuple[Image.Image, dict]:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "resolution": "1K",
        "output_format": "png",
        "n": 1,
    }
    if ref_path and ref_path.is_file():
        b64 = base64.b64encode(ref_path.read_bytes()).decode()
        payload["input_references"] = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        ]
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


def update_faces(img_path: Path, meta: dict, adult_role: str) -> dict:
    faces = detect_faces(img_path) or []
    faces = sorted(faces, key=lambda f: -(f["w"] * f["h"]))[:2]
    ordered = sorted(faces, key=lambda f: f["x"] + f["w"] / 2)

    def region(role, f):
        o = {"role": role, "x": int(f["x"]), "y": int(f["y"]), "w": int(f["w"]), "h": int(f["h"])}
        if f.get("landmarks"):
            o["landmarks"] = f["landmarks"]
        if f.get("confidence") is not None:
            o["confidence"] = float(f["confidence"])
        return o

    if len(ordered) >= 2:
        meta["face_regions"] = [region("child", ordered[0]), region(adult_role, ordered[1])]
        meta["face_detection"] = "yunet"
        meta["status"] = "ready"
        meta["validation"]["verified"] = True
    else:
        meta["status"] = "needs_faces"
    return meta


FIXES = [
    {
        "dir": TEMPLATES / "subtraction/sub_apples_9_3_crossed_user_mother",
        "image": "mother_basket_9_apples_3_crossed.png",
        "adult_role": "mother",
        "mode": "edit",  # keep scene, fix Xs
        "prompt": f"""{STYLE}
EDIT this existing photo. Keep the same mother (right), child (left), kitchen, basket, and apple layout.

COUNT FIX (critical — Grade 1 maths must match exactly):
- There must be EXACTLY 9 red apples visible on the table near the basket.
- EXACTLY 3 of those 9 apples must have a bold red X drawn through them.
- The other 6 apples must have NO X and no marks.
- Remove any extra X marks so only 3 apples are crossed out.
- If a worksheet is visible, it must say 9 - 3 = ?
- No extra apples anywhere.
""",
        "question": None,  # keep existing
    },
    {
        "dir": TEMPLATES / "subtraction/sub_books_13_9_floor_user_mother",
        "image": "mother_shelf_13_books_9_floor.png",
        "adult_role": "mother",
        "mode": "regen",
        # High counts fail often — use clearer Grade-1 numbers and update question to match
        "rewrite": True,
        "question": "Look at the picture! {mother_name} has a bookshelf with 8 books on it, but 3 books have fallen off the shelf and are on the floor. How many books are still on {mother_name}'s bookshelf?",
        "meta_patch": {
            "stem_id": "sub_books_8_3_floor_user_mother",
            "visual_groups": [
                {"id": "shelf", "owner": "mother", "object_id": "books", "singular": "book", "plural": "books", "count": 8, "container": "shelf"},
                {"id": "floor", "owner": "floor", "object_id": "books", "singular": "book", "plural": "books", "count": 3, "container": "floor", "notes": "Fallen books"},
            ],
            "answer": {
                "type": "count_remaining",
                "correct": "5",
                "options": ["5", "8", "3", "11"],
                "formula": "8-3",
                "explanation": "8 on shelf, 3 fell off → 5 remain on shelf",
            },
        },
        "rename_to": "sub_books_8_3_floor_user_mother",
        "new_image": "mother_shelf_8_books_3_floor.png",
        "prompt": f"""{STYLE}
MOTHER (right, adult woman) stands beside a low wooden bookshelf.

COUNT OBJECTS EXACTLY (critical):
- On the shelf: EXACTLY 8 colourful children's books standing in ONE neat row, spaced so each book is separately countable. Label space clear — count them: 1 2 3 4 5 6 7 8.
- On the floor in front of the shelf: EXACTLY 3 books lying flat, separate from the shelf. Count: 1 2 3.
- No other books anywhere in the scene (no book stacks on tables, no bookcases in background).
- Child (left) looks at the books.
""",
    },
    {
        "dir": TEMPLATES / "general_math/gen_blocks_15_basket_5_table_user_mother",
        "image": "mother_basket_15_blocks_table_5_blocks.png",
        "adult_role": "mother",
        "mode": "regen",
        "rewrite": True,
        "question": "Look at the picture! There are 8 colourful blocks in {mother_name}'s basket and 4 more blocks on the table next to it, and {user_name} is helping count. How many blocks are there altogether?",
        "meta_patch": {
            "stem_id": "gen_blocks_8_basket_4_table_user_mother",
            "visual_groups": [
                {"id": "basket", "owner": "mother", "object_id": "blocks", "singular": "block", "plural": "blocks", "count": 8, "container": "basket"},
                {"id": "table", "owner": "table", "object_id": "blocks", "singular": "block", "plural": "blocks", "count": 4, "container": "table"},
            ],
            "answer": {
                "type": "count_total",
                "correct": "12",
                "options": ["12", "8", "4", "11"],
                "formula": "8+4",
                "explanation": "8 in basket + 4 on table = 12",
            },
        },
        "rename_to": "gen_blocks_8_basket_4_table_user_mother",
        "new_image": "mother_basket_8_blocks_table_4_blocks.png",
        "prompt": f"""{STYLE}
MOTHER (right) holds a shallow wicker basket.
Child (left) points at blocks on the table.

COUNT OBJECTS EXACTLY (critical):
- Inside the basket: EXACTLY 8 colourful wooden cube blocks arranged in a neat 2×4 grid, every cube fully visible and separately countable.
- On the table in a separate group (not in basket): EXACTLY 4 colourful wooden cubes in a straight row.
- No worksheet numbers that contradict counts. No extra blocks anywhere.
""",
    },
    {
        "dir": TEMPLATES / "money/money_coins_8p_2p_user_father",
        "image": "father_pocket_8p_table_2p_coins.png",
        "adult_role": "father",
        "mode": "regen",
        "prompt": f"""{STYLE}
FATHER (right, adult man) holds an open small coin purse wide open toward camera.
Child (left) points at coins on the table.

MONEY COUNTS EXACTLY (critical — UK pennies):
- Inside the open purse: EXACTLY EIGHT separate copper 1p coins, laid flat so all 8 are visible and countable (not stacked, not overlapping). Total = 8p.
- On the wooden table outside the purse: EXACTLY TWO separate copper 1p coins. Total = 2p.
- No silver coins. No extra coins anywhere. No dollar coins.
- Clear gap between purse coins and table coins.
""",
    },
]


def apply_fix(api_key: str, fix: dict) -> dict:
    stem_dir = fix["dir"]
    meta_path = stem_dir / "meta.json"
    meta = json.loads(meta_path.read_text())
    adult = fix["adult_role"]
    img_name = fix.get("new_image") or fix["image"]
    old_img = stem_dir / fix["image"]

    print(f"\n=== {stem_dir.name} ({fix['mode']}) ===")

    if fix.get("question"):
        (stem_dir / "question.txt").write_text(fix["question"].strip() + "\n")

    if fix.get("meta_patch"):
        meta.update({k: v for k, v in fix["meta_patch"].items() if k != "visual_groups" and k != "answer"})
        if "visual_groups" in fix["meta_patch"]:
            meta["visual_groups"] = fix["meta_patch"]["visual_groups"]
        if "answer" in fix["meta_patch"]:
            meta["answer"] = fix["meta_patch"]["answer"]

    ref = old_img if fix["mode"] == "edit" and old_img.is_file() else None
    im, usage = call_images(api_key, fix["prompt"], ref)
    out = stem_dir / img_name
    im.save(out)
    if fix.get("new_image") and old_img.is_file() and old_img != out:
        old_img.unlink(missing_ok=True)
    meta["image_file"] = img_name
    meta["validation"]["notes"] = f"Count-locked regen/edit with {MODEL}."
    meta = update_faces(out, meta, adult)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    # rename folder if needed
    if fix.get("rename_to") and stem_dir.name != fix["rename_to"]:
        new_dir = stem_dir.parent / fix["rename_to"]
        if new_dir.exists():
            # overwrite into new
            for p in stem_dir.iterdir():
                target = new_dir / p.name
                if target.exists():
                    target.unlink()
                p.rename(target)
            stem_dir.rmdir()
        else:
            stem_dir.rename(new_dir)
        print(f"  renamed → {fix['rename_to']}")

    cost = usage.get("cost", "?")
    print(f"  saved {img_name}  cost=${cost}  status={meta['status']}")
    return {"stem": fix.get("rename_to") or stem_dir.name, "cost": cost, "status": meta["status"]}


def main():
    load_dotenv(ROOT / ".env")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise SystemExit("no API key")
    results = []
    for i, fix in enumerate(FIXES):
        try:
            results.append(apply_fix(key, fix))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"stem": fix["dir"].name, "status": "error", "error": str(e)})
        if i < len(FIXES) - 1:
            time.sleep(2)
    cr = requests.get("https://openrouter.ai/api/v1/credits", headers=headers(key), timeout=30).json()
    rem = cr["data"]["total_credits"] - cr["data"]["total_usage"]
    print("\n=== DONE ===")
    for r in results:
        print(f"  {r}")
    print(f"  remaining ${rem:.4f}")


if __name__ == "__main__":
    main()
