#!/usr/bin/env python3
"""
Manually annotate face_regions for a Grade 1 stem and write them into meta.json.

Usage:
  # Interactive (drag boxes, ENTER confirm, C skip)
  python scripts/annotate_stem_faces.py grade_1/addition/add_apples_3_2_user_adult

  # Annotate then soft-paste compare (old YuNet boxes vs your new boxes)
  python scripts/annotate_stem_faces.py grade_1/addition/add_apples_3_2_user_adult \\
    --compare \\
    --child kitchen_scenes/sample_characters/new_child.jpg \\
    --adult kitchen_scenes/sample_characters/new_mother.jpg

  # Soft-paste only (no OpenRouter) after annotate:
  python scripts/annotate_stem_faces.py ... --compare --no-ai

Controls per role:
  Drag rectangle → ENTER/SPACE confirm · C / empty skip (keeps previous box for that role)
  After all roles: meta.json is updated; previous boxes kept as face_regions_previous.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "new_pipeline" / "question_templates"
DISPLAY_WIDTH = 900
BOX_COLOR = (0, 165, 255)  # orange (BGR)
OLD_COLOR = (180, 180, 180)


def _scale_roi_to_real(roi: tuple, scale: float) -> dict:
    return {
        "x": int(roi[0] / scale),
        "y": int(roi[1] / scale),
        "w": int(roi[2] / scale),
        "h": int(roi[3] / scale),
    }


def _roles_from_meta(meta: dict) -> list[str]:
    pers = meta.get("personalisation") or {}
    slots = list(pers.get("face_slots") or [])
    if slots:
        return slots
    # Fallback from existing regions / adult role
    roles = [r.get("role") for r in (meta.get("face_regions") or []) if r.get("role")]
    if roles:
        return roles
    adult = (pers.get("template_adult_role") or "adult").strip().lower()
    return ["child", adult]


def _draw_regions(img, regions: list[dict], scale: float, color, label_prefix: str = "") -> None:
    for r in regions:
        x = int(r["x"] * scale)
        y = int(r["y"] * scale)
        w = int(r["w"] * scale)
        h = int(r["h"] * scale)
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        role = f"{label_prefix}{r.get('role', '?')}"
        cv2.putText(
            img, role, (x + 4, max(14, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA,
        )


def _maybe_keep_landmarks(old: dict | None, new_box: dict) -> dict:
    """Keep landmarks if they still fall inside the new box; else drop them."""
    out = dict(new_box)
    if not old:
        return out
    lm = old.get("landmarks")
    if not lm:
        return out
    x, y, w, h = out["x"], out["y"], out["w"], out["h"]
    ok = True
    for pt in lm.values():
        if not (isinstance(pt, (list, tuple)) and len(pt) >= 2):
            ok = False
            break
        px, py = float(pt[0]), float(pt[1])
        if not (x <= px <= x + w and y <= py <= y + h):
            ok = False
            break
    if ok:
        out["landmarks"] = lm
    if old.get("confidence") is not None and ok:
        out["confidence"] = old["confidence"]
    return out


def annotate_stem(stem_id: str, *, show_old: bool = True) -> Path:
    stem_dir = TEMPLATES / stem_id
    meta_path = stem_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"No meta.json at {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    image_file = meta.get("image_file") or "template.png"
    img_path = stem_dir / image_file
    if not img_path.exists():
        raise FileNotFoundError(f"Template image missing: {img_path}")

    img = cv2.imread(str(img_path))
    if img is None:
        raise RuntimeError(f"Could not read {img_path}")

    orig_h, orig_w = img.shape[:2]
    scale = DISPLAY_WIDTH / orig_w
    display_h = int(orig_h * scale)
    base = cv2.resize(img, (DISPLAY_WIDTH, display_h))

    old_regions = list(meta.get("face_regions") or [])
    old_by_role = {r["role"]: r for r in old_regions if r.get("role")}
    roles = _roles_from_meta(meta)

    print("\n" + "═" * 60)
    print("  Manual face_regions annotation → meta.json")
    print("═" * 60)
    print(f"  stem    : {stem_id}")
    print(f"  image   : {image_file}  ({orig_w}x{orig_h})")
    print(f"  roles   : {roles}")
    print(f"  old     : {len(old_regions)} region(s)")
    print("  Drag box → ENTER/SPACE confirm · empty/C keeps previous for that role")
    print("═" * 60)

    overlay = base.copy()
    if show_old and old_regions:
        _draw_regions(overlay, old_regions, scale, OLD_COLOR, label_prefix="old:")

    new_regions: list[dict] = []
    for role in roles:
        wname = f"Annotate '{role}'  (ENTER=ok, empty/C=keep old)"
        roi = cv2.selectROI(wname, overlay, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow(wname)

        if roi != (0, 0, 0, 0) and roi[2] > 4 and roi[3] > 4:
            real = _scale_roi_to_real(roi, scale)
            real["role"] = role
            real = _maybe_keep_landmarks(old_by_role.get(role), real)
            new_regions.append(real)
            _draw_regions(overlay, [real], scale, BOX_COLOR)
            print(f"  ✅ {role}: x={real['x']} y={real['y']} w={real['w']} h={real['h']}")
        elif role in old_by_role:
            kept = deepcopy(old_by_role[role])
            new_regions.append(kept)
            _draw_regions(overlay, [kept], scale, BOX_COLOR)
            print(f"  ↩  {role}: kept previous box")
        else:
            print(f"  ⏭️  {role}: skipped (no previous box)")

    if not new_regions:
        print("No regions saved — meta.json unchanged.")
        return meta_path

    # Backup previous annotations for before/after compare
    meta["face_regions_previous"] = old_regions
    meta["face_regions"] = new_regions
    ann = dict(meta.get("annotation") or {})
    ann["method"] = "manual"
    ann["instructions"] = "Manually dragged face boxes; previous YuNet/manual kept in face_regions_previous."
    meta["annotation"] = ann

    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print("\n💾 Updated", meta_path)
    print(f"   face_regions ({len(new_regions)}) written; old copy → face_regions_previous")
    return meta_path


def _run_paste_compare(
    stem_id: str,
    *,
    child: Path,
    adult: Path,
    role: str,
    out_dir: Path,
    run_ai: bool,
) -> None:
    """Soft-paste (and optional AI) with previous vs current face_regions."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from PIL import Image

    from new_pipeline.question_templates.personalize import (
        _paste_into_annotated_region,
        _use_annotated_region,
        personalize_stem,
    )

    stem_dir = TEMPLATES / stem_id
    meta_path = stem_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    img_path = stem_dir / (meta.get("image_file") or "template.png")
    template = Image.open(img_path).convert("RGB")

    out_dir.mkdir(parents=True, exist_ok=True)
    safe = stem_id.replace("/", "__")

    def soft_paste_with(regions: list[dict], tag: str) -> Path | None:
        by_role = {r["role"]: r for r in regions}
        adult_r = by_role.get(role) or by_role.get("adult")
        child_r = by_role.get("child")
        if not child_r or not adult_r:
            print(f"  skip {tag}: need child + {role} boxes")
            return None
        work = template.copy()
        ok_c, _ = _paste_into_annotated_region(
            work, _use_annotated_region(child_r, work.size), child
        )
        ok_a, _ = _paste_into_annotated_region(
            work, _use_annotated_region(adult_r, work.size), adult
        )
        if not ok_c or not ok_a:
            print(f"  skip {tag}: paste failed")
            return None
        path = out_dir / f"{safe}_{tag}_soft_paste.png"
        work.save(path)
        print(f"  wrote {path}")
        return path

    prev = meta.get("face_regions_previous") or []
    curr = meta.get("face_regions") or []
    print("\n▶ Soft-paste compare (no AI)…")
    p_old = soft_paste_with(prev, "before_boxes") if prev else None
    p_new = soft_paste_with(curr, "after_boxes")

    if p_old and p_new:
        import numpy as np

        a = cv2.imread(str(p_old))
        b = cv2.imread(str(p_new))
        if a is not None and b is not None:
            h = min(a.shape[0], b.shape[0])
            a = cv2.resize(a, (int(a.shape[1] * h / a.shape[0]), h))
            b = cv2.resize(b, (int(b.shape[1] * h / b.shape[0]), h))
            combo = np.hstack([a, b])
            cv2.putText(combo, "BEFORE (old boxes)", (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.putText(
                combo, "AFTER (manual)", (a.shape[1] + 12, 36),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2,
            )
            side = out_dir / f"{safe}_boxes_before_after.png"
            cv2.imwrite(str(side), combo)
            print(f"  wrote {side}")

    if run_ai:
        print("\n▶ Full AI blend with NEW boxes…")
        ai_out = out_dir / f"{safe}_after_ai_blend.png"
        personalize_stem(
            stem_dir,
            child_photo=child,
            adult_photo=adult,
            adult_role=role,
            out_path=ai_out,
            run_ai_finish=True,
            soft_cartoon=False,
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stem", help="e.g. grade_1/addition/add_apples_3_2_user_adult")
    ap.add_argument("--hide-old", action="store_true", help="Don't draw previous boxes as guides")
    ap.add_argument("--compare", action="store_true", help="After annotate, soft-paste before vs after")
    ap.add_argument("--child", type=Path, default=ROOT / "kitchen_scenes/sample_characters/new_child.jpg")
    ap.add_argument("--adult", type=Path, default=ROOT / "kitchen_scenes/sample_characters/new_mother.jpg")
    ap.add_argument("--role", default=None, help="Adult role (default: template_adult_role from meta)")
    ap.add_argument("--no-ai", action="store_true", help="With --compare, skip OpenRouter AI blend")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "pipeline_cache" / "_annotate_compare",
    )
    args = ap.parse_args(argv)

    meta_path = annotate_stem(args.stem, show_old=not args.hide_old)

    if args.compare:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        role = (args.role or (meta.get("personalisation") or {}).get("template_adult_role") or "mother")
        role = str(role).strip().lower()
        if not args.child.exists() or not args.adult.exists():
            print("Missing --child/--adult photos for compare", file=sys.stderr)
            return 1
        _run_paste_compare(
            args.stem,
            child=args.child,
            adult=args.adult,
            role=role,
            out_dir=args.out_dir,
            run_ai=not args.no_ai,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
