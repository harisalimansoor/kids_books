"""Automated validation: off-mask pixels must match the template byte-for-byte."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np


class MaskPreservationError(AssertionError):
    """Output differs from template outside the face/neck mask."""


def combined_mask(masks: list[np.ndarray]) -> np.ndarray:
    if not masks:
        raise ValueError("Need at least one mask")
    out = np.zeros_like(masks[0])
    for m in masks:
        out = np.maximum(out, m)
    return out


def assert_mask_preserved(
    template_bgr: np.ndarray,
    output_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    template_id: str = "",
    tolerance: int = 0,
) -> dict:
    """
    Assert pixels where mask==0 are identical (or within tolerance).

    tolerance: allow tiny diffs (e.g. 0 for PNG; 1–2 if JPEG was involved).
    Prefer PNG end-to-end so tolerance stays 0.
    """
    if template_bgr.shape != output_bgr.shape:
        raise MaskPreservationError(
            f"{template_id}: shape mismatch {template_bgr.shape} vs {output_bgr.shape}"
        )
    outside = mask == 0
    if not np.any(outside):
        return {"ok": True, "max_diff": 0, "changed_pixels": 0, "template_id": template_id}

    # Soft masks: only require exact identity where mask is exactly 0
    diff = np.abs(
        template_bgr.astype(np.int16)[outside] - output_bgr.astype(np.int16)[outside]
    )
    max_diff = int(diff.max()) if diff.size else 0
    changed = int(np.any(diff > tolerance, axis=-1).sum()) if diff.ndim == 2 else int(
        (diff > tolerance).sum()
    )

    if max_diff > tolerance:
        raise MaskPreservationError(
            f"{template_id}: off-mask pixels changed "
            f"(max_diff={max_diff}, changed≈{changed}, tolerance={tolerance})"
        )
    return {
        "ok": True,
        "max_diff": max_diff,
        "changed_pixels": changed,
        "template_id": template_id,
    }


def assert_files_preserved(
    template_path: Path | str,
    output_path: Path | str,
    mask: np.ndarray,
    *,
    template_id: str = "",
    tolerance: int = 0,
) -> dict:
    t = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    o = cv2.imread(str(output_path), cv2.IMREAD_COLOR)
    if t is None or o is None:
        raise FileNotFoundError("Could not load template/output for validation")
    return assert_mask_preserved(
        t, o, mask, template_id=template_id, tolerance=tolerance
    )
