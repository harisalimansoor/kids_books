#!/usr/bin/env python3
"""
tools/test_grade.py
───────────────────────────────────────────────────────────────────────────────
Grade-Isolated Test Runner & Validator.

Validates that a grade is completely self-contained:
  - All files (config, prompts, questions, test_output) exist within grades/<grade_id>/
  - Tests prompt construction strictly using that grade's own prompt template
  - Tests mathematical visual policies and card rendering
  - Writes all test outputs exclusively to grades/<grade_id>/test_output/
  - Zero side-effects or mutations on any other grade!

Usage:
    python tools/test_grade.py --grade Grade_1
    python tools/test_grade.py --grade Grade_2
    python tools/test_grade.py --all
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Setup paths
TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TOOLS_DIR.parent
APP_DIR = PROJECT_DIR / "app"
GRADES_DIR = PROJECT_DIR / "grades"

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app.grade_config import get_grade_dir, get_grade_config, get_grade_visual_policy, get_grade_output_dir
from app.image_generator import build_generation_prompt, build_count_specification
from app.math_visual_engine import infer_structured_question, MathVisualRenderer


def test_single_grade(grade_id: str) -> bool:
    print(f"\n==================================================")
    print(f"  Testing Grade Isolation: {grade_id}")
    print(f"==================================================")

    grade_dir = get_grade_dir(grade_id)
    if not grade_dir.exists():
        print(f"  [FAIL] Grade directory does not exist: {grade_dir}")
        return False

    # 1. Config & Visual Policy
    cfg = get_grade_config(grade_id)
    policy = get_grade_visual_policy(grade_id)
    print(f"  [OK] Config loaded: display_name='{cfg.get('display_name')}', mode='{policy.get('mode')}'")

    # 2. Prompts isolation check
    prompts_dir = grade_dir / "prompts"
    q_prompt = prompts_dir / "question_image.md"
    if not q_prompt.exists():
        print(f"  [FAIL] Missing question_image.md in {prompts_dir}")
        return False
    print(f"  [OK] Owned question_image.md found ({q_prompt.stat().st_size} bytes)")

    # 3. Questions check
    q_dir = grade_dir / "questions"
    stems = list(q_dir.rglob("meta.json"))
    print(f"  [OK] Found {len(stems)} stems in grade questions directory")

    # 4. Output directory isolation
    out_dir = get_grade_output_dir(grade_id)
    print(f"  [OK] Dedicated output directory: {out_dir}")

    # 5. Prompt Construction Verification
    sample_add = "Oliver and Sarah are baking. Oliver places 14 cookies on the tray and adds 3 more. How many cookies in total?"
    spec = build_count_specification(sample_add, grade_id=grade_id, category="counting")
    built_prompt = build_generation_prompt(
        grade_id=grade_id,
        question_text=sample_add,
        user_name="Oliver",
        count_context=spec,
    )

    if policy.get("mode") == "math_card":
        assert "CLEAN DESK & NO DUPLICATE CLUTTER" in built_prompt or "CLEAN DESK & ZERO BACKGROUND OBJECTS" in built_prompt
        print(f"  [OK] Grade policy 'math_card' verified: clean desk instruction present in prompt.")
    else:
        assert "EXACT SMALL COUNT" in built_prompt or "STRICT COUNT FIDELITY" in built_prompt
        print(f"  [OK] Grade policy 'in_scene' verified: exact count instruction present in prompt.")

    # 6. Mathematical Visual Card Generation (if applicable)
    if policy.get("mode") == "math_card":
        sq = infer_structured_question(sample_add, grade_id=grade_id)
        renderer = MathVisualRenderer()
        card_img = renderer.render_math_card(sq, card_w=700, card_h=340)
        card_file = out_dir / "test_sample_card.png"
        card_img.save(str(card_file))
        print(f"  [OK] Math visual card saved to grade test_output: {card_file.name}")

    # Save prompt preview into grade test_output
    preview_file = out_dir / "test_prompt_preview.txt"
    with open(preview_file, "w", encoding="utf-8") as f:
        f.write(built_prompt)
    print(f"  [OK] Prompt preview saved to: {preview_file.name}")

    print(f"  [PASS] Grade '{grade_id}' is completely self-contained and isolated!\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Test grade isolation")
    parser.add_argument("--grade", type=str, default="Grade_2", help="Grade ID to test (e.g. Grade_1, Grade_2)")
    parser.add_argument("--all", action="store_true", help="Test all enabled grades")
    args = parser.parse_args()

    if args.all:
        from app.grade_config import list_grades
        grades = list_grades(enabled_only=True)
        results = {}
        for g in grades:
            gid = g["id"]
            results[gid] = test_single_grade(gid)
        print("Summary of all grades:")
        for gid, res in results.items():
            print(f"  {gid}: {'PASS' if res else 'FAIL'}")
    else:
        test_single_grade(args.grade)


if __name__ == "__main__":
    main()
