#!/usr/bin/env python3
"""
One-time / incremental template preprocessing for the deterministic face-swap pipeline.

Usage:
  python scripts/preprocess_templates.py
  python scripts/preprocess_templates.py --rebuild
  python scripts/preprocess_templates.py --only grade_1/addition/add_apples_3_2_user_adult

Cache is versioned (pipeline.CACHE_VERSION). Stale entries are skipped unless --rebuild.
Only stems missing from cache (or with wrong version) are processed — safe to re-run
as you backfill face_regions on the remaining templates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.constants import CACHE_VERSION  # noqa: E402
from pipeline.cache import (  # noqa: E402
    DEFAULT_CACHE_ROOT,
    DEFAULT_TEMPLATES_ROOT,
    discover_stems,
    file_sha1,
    is_cache_valid,
    resolve_template_image,
    save_template_cache,
    stem_id_from_path,
)
from pipeline.face_model import DetectedFace, get_detector, load_bgr  # noqa: E402
from pipeline.masks import (  # noqa: E402
    face_neck_mask,
    landmarks_dict_from_kps,
)


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    return float(inter / (area_a + area_b - inter + 1e-8))


def _meta_region_to_xyxy(region: dict) -> np.ndarray:
    """meta.json stores x,y,w,h."""
    x, y, w, h = float(region["x"]), float(region["y"]), float(region["w"]), float(region["h"])
    return np.array([x, y, x + w, y + h], dtype=np.float32)


def _pick_face_in_box(
    faces: list[DetectedFace], box: np.ndarray, pad: float = 0.15
) -> DetectedFace | None:
    x0, y0, x1, y1 = box
    pw, ph = pad * (x1 - x0), pad * (y1 - y0)
    expanded = np.array([x0 - pw, y0 - ph, x1 + pw, y1 + ph], dtype=np.float32)
    best = None
    best_iou = 0.0
    for f in faces:
        # Prefer faces whose center lies in the seed box
        cx, cy = f.center
        if expanded[0] <= cx <= expanded[2] and expanded[1] <= cy <= expanded[3]:
            score = _iou(f.bbox, box) + 0.5
        else:
            score = _iou(f.bbox, box)
        if score > best_iou:
            best_iou = score
            best = f
    if best is None or best_iou < 0.05:
        return None
    return best


def _face_entry(role: str, face: DetectedFace, image_shape) -> dict:
    mask = face_neck_mask(image_shape, face)
    entry = {
        "role": role,
        "bbox": face.bbox.tolist(),
        "landmarks": landmarks_dict_from_kps(face.kps),
        "det_score": face.det_score,
        "mask": mask,
        "mask_file": f"mask_{role}.png",
    }
    if face.landmark_106 is not None:
        entry["landmarks_106"] = face.landmark_106.astype(float).tolist()
    return entry


def process_stem(
    stem_dir: Path,
    templates_root: Path,
    cache_root: Path,
    *,
    rebuild: bool = False,
    force_auto_detect: bool = False,
) -> dict:
    template_id = stem_id_from_path(stem_dir, templates_root)
    if not rebuild and is_cache_valid(template_id, cache_root):
        return {
            "template_id": template_id,
            "status": "skipped",
            "reason": "cache_valid",
        }

    meta_path = stem_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    image_path = resolve_template_image(stem_dir, meta)
    bgr = load_bgr(image_path)
    detected = get_detector().detect(bgr)

    face_regions = [] if force_auto_detect else (meta.get("face_regions") or [])
    faces_out: list[dict] = []
    source = "auto_detect"
    confidence = "low"
    notes = "force_auto_detect; " if force_auto_detect else ""

    if face_regions:
        source = "meta_seeded"
        confidence = "high"
        missing = []
        for region in face_regions:
            role = region.get("role") or "unknown"
            box = _meta_region_to_xyxy(region)
            face = _pick_face_in_box(detected, box)
            if face is None:
                # Fallback: synthesize DetectedFace from meta landmarks if present
                lm = region.get("landmarks")
                if lm and all(
                    k in lm
                    for k in ("right_eye", "left_eye", "nose", "mouth_right", "mouth_left")
                ):
                    kps = np.array(
                        [
                            lm["right_eye"],
                            lm["left_eye"],
                            lm["nose"],
                            lm["mouth_right"],
                            lm["mouth_left"],
                        ],
                        dtype=np.float32,
                    )
                    face = DetectedFace(
                        bbox=box,
                        kps=kps,
                        landmark_106=None,
                        embedding=None,
                        det_score=float(region.get("confidence") or 0.5),
                    )
                    notes += f" role={role} used meta landmarks (no IF face in box);"
                else:
                    missing.append(role)
                    continue
            faces_out.append(_face_entry(role, face, bgr.shape))
        if missing:
            notes += f" missing_roles={missing};"
            confidence = "low"
            # If nothing resolved, fall through to auto
            if not faces_out:
                source = "auto_detect"
                confidence = "low"
                notes += " fell_back_to_auto;"
    if not faces_out:
        source = "auto_detect"
        confidence = "low"
        notes += " no face_regions or seeding failed — auto InsightFace;"
        # Assign roles left-to-right: child, adult (generic)
        roles_guess = ["child", "adult"]
        pers = meta.get("personalisation") or {}
        adult = (pers.get("template_adult_role") or "adult").strip().lower()
        if len(detected) >= 2:
            roles_guess = ["child", adult]
        elif len(detected) == 1:
            roles_guess = ["child"]
        for i, face in enumerate(detected[:2]):
            role = roles_guess[i] if i < len(roles_guess) else f"face_{i}"
            faces_out.append(_face_entry(role, face, bgr.shape))

    if not faces_out:
        return {
            "template_id": template_id,
            "status": "failed",
            "reason": "no_faces_detected",
            "confidence": "low",
        }

    save_template_cache(
        template_id,
        image_file=image_path.name,
        image_sha1=file_sha1(image_path),
        faces=faces_out,
        source=source,
        confidence=confidence,
        notes=notes.strip(),
        cache_root=cache_root,
    )

    # Write a quick debug overlay for low-confidence stems
    if confidence == "low":
        dbg = bgr.copy()
        for f in faces_out:
            m = f["mask"]
            tint = dbg.copy()
            tint[m > 0] = (0, 255, 0)
            dbg = cv2.addWeighted(dbg, 0.65, tint, 0.35, 0)
            x0, y0, x1, y1 = [int(v) for v in f["bbox"]]
            cv2.rectangle(dbg, (x0, y0), (x1, y1), (0, 255, 255), 2)
            cv2.putText(
                dbg,
                f["role"],
                (x0, max(12, y0 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 255),
                1,
                cv2.LINE_AA,
            )
        overlay_path = cache_root / template_id / "review_overlay.png"
        cv2.imwrite(str(overlay_path), dbg)

    return {
        "template_id": template_id,
        "status": "ok",
        "source": source,
        "confidence": confidence,
        "n_faces": len(faces_out),
        "notes": notes.strip(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Preprocess worksheet templates into pipeline_cache/")
    ap.add_argument(
        "--templates-root",
        type=Path,
        default=DEFAULT_TEMPLATES_ROOT,
        help="Root of stem dirs (default: new_pipeline/question_templates)",
    )
    ap.add_argument(
        "--cache-root",
        type=Path,
        default=DEFAULT_CACHE_ROOT,
        help="Cache output root (default: pipeline_cache/)",
    )
    ap.add_argument(
        "--rebuild",
        action="store_true",
        help="Ignore existing cache and regenerate all selected stems",
    )
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        help="Process only this template_id (repeatable). Incremental-friendly.",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of stems to process (after skip filter)",
    )
    args = ap.parse_args(argv)

    templates_root = args.templates_root.resolve()
    cache_root = args.cache_root.resolve()
    cache_root.mkdir(parents=True, exist_ok=True)

    print(f"CACHE_VERSION={CACHE_VERSION}")
    print(f"templates_root={templates_root}")
    print(f"cache_root={cache_root}")

    stems = discover_stems(templates_root)
    if args.only:
        wanted = set(args.only)
        stems = [s for s in stems if stem_id_from_path(s, templates_root) in wanted]
        missing = wanted - {stem_id_from_path(s, templates_root) for s in stems}
        if missing:
            print(f"WARNING: --only not found: {sorted(missing)}")

    results = []
    processed = 0
    for stem in stems:
        tid = stem_id_from_path(stem, templates_root)
        if not args.rebuild and is_cache_valid(tid, cache_root):
            results.append({"template_id": tid, "status": "skipped", "reason": "cache_valid"})
            continue
        if args.limit and processed >= args.limit:
            break
        print(f"… {tid}")
        r = process_stem(stem, templates_root, cache_root, rebuild=args.rebuild)
        results.append(r)
        processed += 1
        flag = ""
        if r.get("confidence") == "low":
            flag = " ⚠ LOW-CONFIDENCE (review overlay written)"
        print(f"  → {r.get('status')} source={r.get('source')} conf={r.get('confidence')}{flag}")

    # Summary log
    summary_path = cache_root / "preprocess_summary.json"
    low = [r for r in results if r.get("confidence") == "low" and r.get("status") == "ok"]
    failed = [r for r in results if r.get("status") == "failed"]
    ok = [r for r in results if r.get("status") == "ok"]
    skipped = [r for r in results if r.get("status") == "skipped"]
    summary = {
        "cache_version": CACHE_VERSION,
        "total_seen": len(results),
        "ok": len(ok),
        "skipped": len(skipped),
        "failed": len(failed),
        "low_confidence": [r["template_id"] for r in low],
        "failed_ids": [r["template_id"] for r in failed],
        "results": results,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("\n=== summary ===")
    print(f"ok={len(ok)} skipped={len(skipped)} failed={len(failed)}")
    print(f"low_confidence={len(low)} (see {summary_path})")
    if low:
        print("Low-confidence template_ids (spot-check review_overlay.png):")
        for r in low[:30]:
            print(f"  - {r['template_id']}")
        if len(low) > 30:
            print(f"  … and {len(low) - 30} more")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
