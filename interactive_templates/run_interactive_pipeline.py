"""
run_interactive_pipeline.py
─────────────────────────────────────────────────────────────────────────────
CLI helper to compose an interactive kitchen worksheet image.

Example:
  python -m interactive_templates.run_interactive_pipeline \\
      --role mother --object cupcakes \\
      --child path/to/child.jpg --mother path/to/mum.jpg
"""

from __future__ import annotations

import argparse
from pathlib import Path

from interactive_templates.compositor import compose_interactive_scene, list_role_templates


def main():
    parser = argparse.ArgumentParser(description="Compose interactive kitchen worksheet image")
    parser.add_argument("--role", required=True, choices=["mother", "father", "grandmother", "grandfather"])
    parser.add_argument("--object", required=True, help="Object id, e.g. cupcakes, chocolates, pizza")
    parser.add_argument("--category", default="", help="Optional: food | hobby | pet")
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--child", default="")
    parser.add_argument("--mother", default="")
    parser.add_argument("--father", default="")
    parser.add_argument("--grandmother", default="")
    parser.add_argument("--grandfather", default="")
    parser.add_argument("--no-beautify", action="store_true")
    parser.add_argument("--out", default="interactive_output.png")
    parser.add_argument("--list", action="store_true", help="List available kitchen role templates")
    args = parser.parse_args()

    if args.list:
        for t in list_role_templates("kitchen"):
            print(f"  • {t['adult_role']}: {t['template_id']} ({'ready' if t['annotated'] else 'missing faces'})")
        return

    photos = {
        "child": args.child or None,
        "mother": args.mother or None,
        "father": args.father or None,
        "grandmother": args.grandmother or None,
        "grandfather": args.grandfather or None,
    }
    result = compose_interactive_scene(
        adult_role=args.role,
        object_id=args.object,
        photos=photos,
        category=args.category or None,
        count=args.count or None,
        beautify=not args.no_beautify,
    )
    out = Path(args.out)
    result["final_image"].save(out)
    print(f"✅ Saved {out}")
    print(f"   role={result['adult_role']} object={result['plural']} count={result['count']}")


if __name__ == "__main__":
    main()
