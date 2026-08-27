"""Seamless compositing — eroded/blurred mask, configurable clone / multiband."""

from __future__ import annotations

import cv2
import numpy as np

from .constants import CLONE_MODE, MASK_BLUR_PX, MASK_ERODE_PX
from .masks import mask_center


def prepare_blend_mask(
    mask: np.ndarray,
    *,
    erode_px: int | None = None,
    blur_px: float | None = None,
) -> np.ndarray:
    """
    Erode landmark mask inward (seam sits on uniform skin), then soft
    distance-transform feather + Gaussian blur. Returns uint8 0–255.
    """
    erode_px = MASK_ERODE_PX if erode_px is None else erode_px
    blur_px = MASK_BLUR_PX if blur_px is None else blur_px

    m = mask.copy()
    if m.dtype != np.uint8:
        m = m.astype(np.uint8)
    _, hard = cv2.threshold(m, 8, 255, cv2.THRESH_BINARY)
    if erode_px > 0:
        k = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (erode_px * 2 + 1, erode_px * 2 + 1)
        )
        hard = cv2.erode(hard, k)
    if int((hard > 0).sum()) < 20:
        return np.zeros_like(m)

    # Distance-transform feather: 1.0 at core → 0 at boundary
    inv = cv2.bitwise_not(hard)
    dist = cv2.distanceTransform(hard, cv2.DIST_L2, 5)
    # Feather width ~ blur_px * 3 (pixels from edge)
    feather = max(2.0, float(blur_px) * 3.0)
    soft = np.clip(dist / feather, 0.0, 1.0)
    soft = (soft * 255.0).astype(np.uint8)
    soft[hard == 0] = 0
    if blur_px > 0:
        soft = cv2.GaussianBlur(soft, (0, 0), sigmaX=float(blur_px))
        soft[hard == 0] = 0
    # Never expand outside original mask support
    soft[m == 0] = 0
    return soft


def _skin_gate(warped_bgr: np.ndarray, soft: np.ndarray) -> np.ndarray:
    """Reduce alpha where warped pixels look like hair/dark outliers."""
    hsv = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2].astype(np.float32)
    ycrcb = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2YCrCb)
    _, cr, cb = cv2.split(ycrcb)
    skin = (
        (cr >= 133) & (cr <= 173) & (cb >= 77) & (cb <= 127) & (v >= 45)
    ).astype(np.float32)
    core = soft.astype(np.float32) / 255.0
    bright = (core > 0.55) & (skin > 0) & (v > 70)
    if bright.sum() >= 40:
        med = float(np.median(v[bright]))
        outlier = v < (med - 25.0)
        skin = np.where(outlier, skin * 0.05, skin)
    skin = cv2.GaussianBlur(skin, (0, 0), sigmaX=3.0)
    return np.clip(skin, 0.0, 1.0)


def multiband_blend(
    src_bgr: np.ndarray,
    dst_bgr: np.ndarray,
    mask: np.ndarray,
    levels: int = 4,
) -> np.ndarray:
    """Laplacian pyramid blend (fallback when Poisson looks pasted-on)."""
    if mask.ndim == 2 or (hasattr(mask, "dtype") and mask.max() > 1.5):
        soft = prepare_blend_mask(mask) if mask.dtype == np.uint8 and mask.max() > 1 else mask
        if soft.dtype == np.uint8:
            alpha0 = soft.astype(np.float32) / 255.0
        else:
            alpha0 = soft.astype(np.float32)
            if alpha0.max() > 1.5:
                alpha0 = alpha0 / 255.0
    else:
        alpha0 = mask.astype(np.float32)

    # Cap pyramid depth by min dimension
    min_dim = min(src_bgr.shape[0], src_bgr.shape[1])
    while levels > 1 and (min_dim >> (levels - 1)) < 8:
        levels -= 1

    gp_src = [src_bgr.astype(np.float32)]
    gp_dst = [dst_bgr.astype(np.float32)]
    gp_mask = [alpha0]
    for _ in range(levels - 1):
        gp_src.append(cv2.pyrDown(gp_src[-1]))
        gp_dst.append(cv2.pyrDown(gp_dst[-1]))
        gp_mask.append(cv2.pyrDown(gp_mask[-1]))

    lp_src: list[np.ndarray] = []
    lp_dst: list[np.ndarray] = []
    for i in range(levels - 1):
        size = (gp_src[i].shape[1], gp_src[i].shape[0])
        lp_src.append(gp_src[i] - cv2.pyrUp(gp_src[i + 1], dstsize=size))
        lp_dst.append(gp_dst[i] - cv2.pyrUp(gp_dst[i + 1], dstsize=size))
    lp_src.append(gp_src[-1])
    lp_dst.append(gp_dst[-1])

    blended_levels = []
    for ls, ld, gm in zip(lp_src, lp_dst, gp_mask):
        if gm.ndim == 2:
            gm3 = gm[..., None]
        else:
            gm3 = gm
        if gm3.shape[:2] != ls.shape[:2]:
            gm3 = cv2.resize(gm3, (ls.shape[1], ls.shape[0]), interpolation=cv2.INTER_LINEAR)
            if gm3.ndim == 2:
                gm3 = gm3[..., None]
        blended_levels.append(ls * gm3 + ld * (1.0 - gm3))

    out = blended_levels[-1]
    for i in range(levels - 2, -1, -1):
        size = (blended_levels[i].shape[1], blended_levels[i].shape[0])
        out = cv2.pyrUp(out, dstsize=size) + blended_levels[i]
    return np.clip(out, 0, 255).astype(np.uint8)


def _poisson_clone(
    src: np.ndarray,
    dst: np.ndarray,
    mask_bin: np.ndarray,
    mode: int,
) -> np.ndarray | None:
    if int((mask_bin > 0).sum()) < 20:
        return None
    center = mask_center(mask_bin)
    try:
        return cv2.seamlessClone(src, dst, mask_bin, center, mode)
    except cv2.error:
        return None


def seamless_blend(
    warped_bgr: np.ndarray,
    template_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    clone_mode: str | None = None,
) -> np.ndarray:
    """
    Blend color-matched warped face into template.

    clone_mode: "mixed" | "normal" | "multiband" (default from PIPELINE_CLONE_MODE).
    Off-mask pixels restored from template.
    """
    if warped_bgr.shape != template_bgr.shape:
        raise ValueError(
            f"Shape mismatch: warped {warped_bgr.shape} vs template {template_bgr.shape}"
        )
    if mask.shape[:2] != template_bgr.shape[:2]:
        raise ValueError("Mask size must match template")

    mode_name = (clone_mode or CLONE_MODE or "mixed").lower()
    soft = prepare_blend_mask(mask)
    if int((soft > 0).sum()) < 20:
        return template_bgr.copy()

    # Binary core for Poisson (inner high-confidence region)
    _, hard = cv2.threshold(soft, 100, 255, cv2.THRESH_BINARY)

    out: np.ndarray | None = None
    if mode_name == "multiband":
        out = multiband_blend(warped_bgr, template_bgr, soft)
    else:
        cv_mode = cv2.MIXED_CLONE if mode_name == "mixed" else cv2.NORMAL_CLONE
        cloned = _poisson_clone(warped_bgr, template_bgr, hard, cv_mode)
        if cloned is None and mode_name == "mixed":
            cloned = _poisson_clone(warped_bgr, template_bgr, hard, cv2.NORMAL_CLONE)
        if cloned is None:
            out = multiband_blend(warped_bgr, template_bgr, soft)
        else:
            # Soft rim: Poisson in core, feather to template at boundary
            alpha = soft.astype(np.float32) / 255.0
            _, core = cv2.threshold(soft, 200, 255, cv2.THRESH_BINARY)
            rim = (soft > 0) & (core == 0)
            skin = _skin_gate(warped_bgr, soft)
            if rim.any():
                alpha = alpha.copy()
                alpha[rim] = alpha[rim] * np.clip(skin[rim], 0.4, 1.0)
            alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=2.0)
            alpha[soft == 0] = 0.0
            a = alpha[..., None]
            out = np.clip(
                cloned.astype(np.float32) * a
                + template_bgr.astype(np.float32) * (1.0 - a),
                0,
                255,
            ).astype(np.uint8)

    assert out is not None
    outside = mask == 0
    out[outside] = template_bgr[outside]
    return out
