"""Public API: generate_worksheet / generate_worksheet_batch."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

import cv2
import numpy as np

from .align import AlignmentError, crop_face_padded, warp_face
from .blend import prepare_blend_mask, seamless_blend
from .cache import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_TEMPLATES_ROOT,
    load_template_cache,
    resolve_template_image,
)
from .color_match import match_lab_stats
from .constants import CLONE_MODE, PWA_LANDMARK_COUNT
from .debug import debug_dir, dump_role_stages
from .face_model import DetectedFace, cosine_similarity, get_detector, load_bgr
from .masks import kps_from_landmarks_dict
from .validate import assert_mask_preserved, combined_mask

PhotoMap = Mapping[str, Union[str, Path]]
MIN_DET_SCORE = 0.5
MIN_IDENTITY_SIM = 0.25  # soft QA warning threshold


class FacePrepError(ValueError):
    """User photo failed face detection / QA checks."""


def _prepare_user_face(photo_path: Path | str, *, role: str) -> tuple[np.ndarray, DetectedFace]:
    bgr = load_bgr(photo_path)
    faces = get_detector().detect(bgr)
    if not faces:
        raise FacePrepError(f"{role}: no face detected in {photo_path}")
    if len(faces) > 1:
        warnings.warn(
            f"{role}: {len(faces)} faces in {photo_path}; using largest",
            stacklevel=2,
        )
        faces = sorted(faces, key=lambda f: f.width * f.height, reverse=True)
    face = faces[0]
    if face.det_score < MIN_DET_SCORE:
        raise FacePrepError(
            f"{role}: face confidence {face.det_score:.2f} below {MIN_DET_SCORE} in {photo_path}"
        )
    eye_dist = float(np.linalg.norm(face.kps[0] - face.kps[1]))
    if eye_dist < 8:
        warnings.warn(f"{role}: eyes very close — possible occlusion/angle", stacklevel=2)
    return bgr, face


def _cached_face_as_detected(entry: dict) -> DetectedFace:
    bbox = np.asarray(entry["bbox"], dtype=np.float32)
    kps = kps_from_landmarks_dict(entry["landmarks"])
    lm106 = None
    if entry.get("landmarks_106"):
        lm106 = np.asarray(entry["landmarks_106"], dtype=np.float32)
    return DetectedFace(
        bbox=bbox,
        kps=kps,
        landmark_106=lm106,
        embedding=None,
        det_score=float(entry.get("det_score", 1.0)),
    )


def _swap_one_role(
    template_bgr: np.ndarray,
    role_entry: dict,
    user_bgr: np.ndarray,
    user_face: DetectedFace,
    *,
    clone_mode: str | None = None,
    debug_out: Path | None = None,
    template_id: str = "",
) -> np.ndarray:
    dst_face = _cached_face_as_detected(role_entry)
    dst_kps = dst_face.kps
    mask = role_entry["mask"]
    role = role_entry["role"]

    source_crop, _, _ = crop_face_padded(user_bgr, user_face)

    try:
        warped, _ = warp_face(
            user_bgr,
            user_face,
            template_bgr.shape,
            dst_kps,
            dst_face=dst_face,
            use_crop=True,
            n_pwa_points=PWA_LANDMARK_COUNT,
        )
    except AlignmentError as e:
        raise FacePrepError(f"{role}: alignment failed — {e}") from e

    # Color match BEFORE clone; dump confirms this array is what clone receives
    color_matched = match_lab_stats(warped, template_bgr, mask, strength=1.0)
    blend_mask = prepare_blend_mask(mask)
    blended = seamless_blend(
        color_matched, template_bgr, mask, clone_mode=clone_mode or CLONE_MODE
    )

    if debug_out is not None:
        d = debug_dir(debug_out, template_id, role)
        dump_role_stages(
            d,
            source_face_bgr=source_crop,
            warped_bgr=warped,
            template_bgr=template_bgr,
            mask=blend_mask,
            color_matched_bgr=color_matched,
            final_bgr=blended,
        )

    if user_face.embedding is not None:
        try:
            x0, y0, x1, y1 = dst_face.bbox.astype(int)
            h, w = blended.shape[:2]
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(w, x1), min(h, y1)
            crop = blended[y0:y1, x0:x1]
            if crop.size > 0:
                det = get_detector().detect(crop)
                if det and det[0].embedding is not None:
                    sim = cosine_similarity(user_face.embedding, det[0].embedding)
                    if sim < MIN_IDENTITY_SIM:
                        warnings.warn(
                            f"{role}: low identity similarity {sim:.2f} "
                            f"after blend (threshold {MIN_IDENTITY_SIM})",
                            stacklevel=2,
                        )
        except Exception:
            pass

    return blended


def generate_worksheet(
    template_id: str,
    user_photos: PhotoMap | str | Path,
    output_path: str | Path,
    *,
    cache_root: Path | str = DEFAULT_CACHE_ROOT,
    templates_root: Path | str = DEFAULT_TEMPLATES_ROOT,
    validate: bool = True,
    debug: bool = False,
    debug_dir_path: Path | str | None = None,
    clone_mode: str | None = None,
) -> Path:
    """
    Swap faces into one template (CV warp + color match + soft mask blend).

    user_photos: mapping role → photo path. Missing roles keep template art.
    When debug=True, writes 01_…05_ stage images under debug_dir_path.
    """
    cache_root = Path(cache_root)
    templates_root = Path(templates_root)
    output_path = Path(output_path)

    if isinstance(user_photos, (str, Path)):
        user_photos = {"child": user_photos}

    cached = load_template_cache(template_id, cache_root=cache_root)
    stem_dir = templates_root / template_id
    image_path = stem_dir / cached["image_file"]
    if not image_path.exists():
        import json

        meta = json.loads((stem_dir / "meta.json").read_text(encoding="utf-8"))
        image_path = resolve_template_image(stem_dir, meta)

    template_bgr = load_bgr(image_path)
    if image_path.suffix.lower() in {".jpg", ".jpeg"}:
        warnings.warn(
            f"{template_id}: template is JPEG; prefer PNG for exact off-mask identity",
            stacklevel=2,
        )

    dbg_root: Path | None = None
    if debug:
        dbg_root = Path(debug_dir_path) if debug_dir_path else output_path.parent / "debug"
        dbg_root.mkdir(parents=True, exist_ok=True)

    result = template_bgr.copy()
    used_masks: list[np.ndarray] = []
    mode = clone_mode or CLONE_MODE

    print(f"  ▶ CV PWA + LAB match + {mode} blend")
    for role_entry in cached["faces"]:
        role = role_entry["role"]
        if role not in user_photos:
            continue
        user_bgr, user_face = _prepare_user_face(user_photos[role], role=role)
        role_entry = {**role_entry, "mask": np.asarray(role_entry["mask"]).copy()}
        result = _swap_one_role(
            result,
            role_entry,
            user_bgr,
            user_face,
            clone_mode=mode,
            debug_out=dbg_root,
            template_id=template_id,
        )
        used_masks.append(role_entry["mask"].copy())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() != ".png":
        output_path = output_path.with_suffix(".png")
    cv2.imwrite(str(output_path), result)

    if validate and used_masks:
        mask = combined_mask(used_masks)
        assert_mask_preserved(
            template_bgr, result, mask, template_id=template_id, tolerance=0
        )
    elif validate and not used_masks:
        if not np.array_equal(template_bgr, result):
            raise AssertionError(f"{template_id}: no swaps but output differs from template")

    return output_path


def generate_worksheet_batch(
    jobs: Sequence[tuple[str, PhotoMap]],
    output_dir: str | Path,
    *,
    cache_root: Path | str = DEFAULT_CACHE_ROOT,
    templates_root: Path | str = DEFAULT_TEMPLATES_ROOT,
    validate: bool = True,
    debug: bool = False,
    clone_mode: str | None = None,
) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for template_id, photos in jobs:
        safe = template_id.replace("/", "__")
        out = output_dir / f"{safe}.png"
        paths.append(
            generate_worksheet(
                template_id,
                photos,
                out,
                cache_root=cache_root,
                templates_root=templates_root,
                validate=validate,
                debug=debug,
                debug_dir_path=output_dir / "debug" if debug else None,
                clone_mode=clone_mode,
            )
        )
    return paths


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Deterministic CV face-swap for worksheets")
    p.add_argument("--template-id", required=True)
    p.add_argument("--child", type=Path, default=None)
    p.add_argument("--mother", type=Path, default=None)
    p.add_argument("--father", type=Path, default=None)
    p.add_argument("--grandmother", type=Path, default=None)
    p.add_argument("--grandfather", type=Path, default=None)
    p.add_argument("--aunt", type=Path, default=None)
    p.add_argument("--uncle", type=Path, default=None)
    p.add_argument("--role", action="append", nargs=2, metavar=("ROLE", "PHOTO"), default=[])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    p.add_argument("--templates-root", type=Path, default=DEFAULT_TEMPLATES_ROOT)
    p.add_argument("--no-validate", action="store_true")
    p.add_argument(
        "--debug",
        action="store_true",
        help="Write 01_source_face … 05_final stage dumps next to --out",
    )
    p.add_argument(
        "--debug-dir",
        type=Path,
        default=None,
        help="Override debug dump root (default: <out.parent>/debug)",
    )
    p.add_argument(
        "--clone-mode",
        choices=("mixed", "normal", "multiband"),
        default=None,
        help="seamlessClone / pyramid blend mode (default: PIPELINE_CLONE_MODE or mixed)",
    )
    args = p.parse_args(argv)

    photos: dict[str, Path] = {}
    for key in (
        "child",
        "mother",
        "father",
        "grandmother",
        "grandfather",
        "aunt",
        "uncle",
    ):
        val = getattr(args, key)
        if val is not None:
            photos[key] = val
    for role, path in args.role:
        photos[role] = Path(path)

    if not photos:
        p.error("Provide at least one photo (--child, --mother, or --role ROLE PATH)")

    out = generate_worksheet(
        args.template_id,
        photos,
        args.out,
        cache_root=args.cache_root,
        templates_root=args.templates_root,
        validate=not args.no_validate,
        debug=args.debug,
        debug_dir_path=args.debug_dir,
        clone_mode=args.clone_mode,
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
