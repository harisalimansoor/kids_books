"""LAB color / lighting match — sample target stats from mask margin on template."""

from __future__ import annotations

import cv2
import numpy as np


def _ycrcb_skin_bool(bgr: np.ndarray) -> np.ndarray:
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    return (
        (cr >= 133)
        & (cr <= 173)
        & (cb >= 77)
        & (cb <= 127)
        & (y >= 60)
        & (y <= 230)
    )


def _mask_margin_bool(mask: np.ndarray, inner_erode: int = 2, outer_dilate: int = 16) -> np.ndarray:
    """
    Ring around the face mask on the template: local lighting context.
    Prefer lower half (jaw/neck) over hairline.
    """
    m = np.asarray(mask)
    if m.dtype != np.uint8:
        m = m.astype(np.uint8)
    _, hard = cv2.threshold(m, 32, 255, cv2.THRESH_BINARY)
    k_in = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (inner_erode * 2 + 1, inner_erode * 2 + 1)
    )
    k_out = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (outer_dilate * 2 + 1, outer_dilate * 2 + 1)
    )
    inner = cv2.erode(hard, k_in)
    outer = cv2.dilate(hard, k_out)
    # Outside ring + thin inner band (illustrated cheek)
    ring = cv2.subtract(outer, hard)
    band_in = cv2.subtract(hard, inner)
    sample = (ring > 0) | (band_in > 0)

    ys, _ = np.where(hard > 0)
    if len(ys) > 0:
        y_cut = float(np.percentile(ys, 40))  # keep lower ~60% of face height
        Y = np.arange(hard.shape[0])[:, None]
        lower = sample & (Y >= y_cut)
        if lower.sum() >= 50:
            sample = lower
    return sample


def _pick_target_pixels(template_bgr: np.ndarray, candidate: np.ndarray) -> np.ndarray:
    """
    From margin candidates, keep bright skin-like pixels so hair/shadow
    don't drag LAB means too dark or too yellow.
    """
    lab = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2LAB)
    L = lab[:, :, 0]
    skin = _ycrcb_skin_bool(template_bgr)
    base = candidate & skin & (L >= 95) & (L <= 220)
    if base.sum() >= 40:
        # Drop extreme outliers via IQR on L
        vals = L[base].astype(np.float32)
        q1, q3 = np.percentile(vals, [25, 75])
        iqr = max(8.0, float(q3 - q1))
        lo, hi = q1 - 0.8 * iqr, q3 + 0.8 * iqr
        refined = base & (L >= lo) & (L <= hi)
        if refined.sum() >= 30:
            return refined
        return base
    # Fallbacks: any bright candidate, then any skin under candidate bbox
    bright = candidate & (L >= 110)
    if bright.sum() >= 40:
        return bright
    if (candidate & skin).sum() >= 20:
        return candidate & skin
    return candidate


def match_lab_stats(
    warped_bgr: np.ndarray,
    template_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    strength: float = 1.0,
) -> np.ndarray:
    """
    Mean/std transfer in LAB on warped face, matching a *margin around the mask*
    in the template (local lighting), applied to all mask>0 pixels.
    """
    mask_u8 = np.asarray(mask)
    if mask_u8.dtype != np.uint8:
        mask_u8 = mask_u8.astype(np.uint8)

    apply_bool = mask_u8 > 0
    if apply_bool.sum() < 50:
        return warped_bgr.copy()

    _, hard = cv2.threshold(mask_u8, 40, 255, cv2.THRESH_BINARY)
    k = max(3, int(round(np.sqrt(max(1, (hard > 0).sum())) * 0.06)) | 1)
    core = cv2.erode(hard, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    if (core > 0).sum() < 40:
        core = hard
    src_skin = _ycrcb_skin_bool(warped_bgr)
    src_bool = (core > 0) & src_skin
    if src_bool.sum() < 40:
        src_bool = core > 0

    tgt_bool = _pick_target_pixels(template_bgr, _mask_margin_bool(mask_u8))
    if tgt_bool.sum() < 30:
        # Last resort: lower third inside mask on template, bright skin
        ys, _ = np.where(hard > 0)
        if len(ys) > 0:
            y_lo = float(np.percentile(ys, 55))
            Y = np.arange(hard.shape[0])[:, None]
            tgt_bool = _pick_target_pixels(template_bgr, (hard > 0) & (Y >= y_lo))

    src_lab = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    dst_lab = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    out = src_lab.copy()
    strength = float(np.clip(strength, 0.0, 1.0))

    for c in range(3):
        s = src_lab[:, :, c][src_bool]
        t = dst_lab[:, :, c][tgt_bool]
        if s.size < 20 or t.size < 20:
            continue
        s_mean, s_std = float(s.mean()), float(s.std() + 1e-5)
        t_mean, t_std = float(t.mean()), float(t.std() + 1e-5)
        if c == 0:
            # Don't crush brightness toward dark outliers
            ratio = float(np.clip(t_std / s_std, 0.7, 1.35))
            ch_strength = min(1.0, strength)
        else:
            ratio = float(np.clip(t_std / s_std, 0.65, 1.4))
            ch_strength = min(1.0, strength)
        channel = src_lab[:, :, c]
        matched = (channel - s_mean) * ratio + t_mean
        blended = channel * (1.0 - ch_strength) + matched * ch_strength
        channel_out = channel.copy()
        channel_out[apply_bool] = blended[apply_bool]
        out[:, :, c] = np.clip(channel_out, 0, 255)

    return cv2.cvtColor(out.astype(np.uint8), cv2.COLOR_LAB2BGR)
