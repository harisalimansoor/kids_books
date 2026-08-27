#!/usr/bin/env python3
"""
Annotated face_regions → soft-paste → AI seamless blend.

This is the preferred personalization path (not the CV warp/clone pipeline).

Usage:
  python scripts/run_ai_blend.py \\
    --stem grade_1/addition/add_apples_3_2_user_adult \\
    --child kitchen_scenes/sample_characters/new_child.jpg \\
    --adult kitchen_scenes/sample_characters/new_mother.jpg \\
    --role mother

Requires OPENROUTER_API_KEY in .env. Templates must have face_regions in meta.json
(use kitchen_scenes/annotate_template.py or YuNet backfill if missing).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from new_pipeline.question_templates.personalize import personalize_stem  # noqa: E402

TEMPLATES = ROOT / "new_pipeline" / "question_templates"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--stem",
        required=True,
        help="Template id under question_templates/, e.g. grade_1/addition/add_apples_3_2_user_adult",
    )
    ap.add_argument("--child", type=Path, required=True)
    ap.add_argument("--adult", type=Path, required=True)
    ap.add_argument("--role", default="mother", help="Adult role matching face_regions / template_adult_role")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-ai", action="store_true", help="Soft-paste only (skip OpenRouter blend)")
    ap.add_argument("--cartoon", action="store_true", help="Soft cartoon blend (default: photoreal)")
    ap.add_argument("--gender", default="", help="Optional boy/girl hint")
    args = ap.parse_args(argv)

    stem_dir = TEMPLATES / args.stem
    if not (stem_dir / "meta.json").exists():
        print(f"Missing stem: {stem_dir}", file=sys.stderr)
        return 1

    out = args.out
    if out is None:
        out = ROOT / "pipeline_cache" / "_test_out" / f"{args.stem.replace('/', '__')}_ai_blend.png"

    path = personalize_stem(
        stem_dir,
        child_photo=args.child,
        adult_photo=args.adult,
        adult_role=args.role,
        out_path=out,
        run_ai_finish=not args.no_ai,
        soft_cartoon=args.cartoon,
        child_gender=args.gender,
    )
    print(f"Done: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
