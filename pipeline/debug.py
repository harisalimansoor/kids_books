"""Debug dumps for per-stage visual QA."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def debug_dir(base: Path, template_id: str, role: str) -> Path:
    safe = template_id.replace("/", "__")
    d = Path(base) / safe / role
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_bgr(path: Path, bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), bgr)


def overlay_mask_on_template(template_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Cyan overlay where mask > 0; red contour at mask boundary."""
    out = template_bgr.copy()
    m = mask.astype(np.float32) / 255.0
    if m.ndim == 2:
        tint = out.astype(np.float32)
        tint[:, :, 0] = tint[:, :, 0] * (1 - 0.45 * m) + 255 * 0.45 * m  # B
        tint[:, :, 1] = tint[:, :, 1] * (1 - 0.45 * m) + 200 * 0.45 * m  # G
        out = np.clip(tint, 0, 255).astype(np.uint8)
    hard = (mask > 32).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(hard, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, cnts, -1, (0, 0, 255), 1)
    return out


def dump_role_stages(
    out_dir: Path,
    *,
    source_face_bgr: np.ndarray,
    warped_bgr: np.ndarray,
    template_bgr: np.ndarray,
    mask: np.ndarray,
    color_matched_bgr: np.ndarray,
    final_bgr: np.ndarray | None = None,
) -> None:
    save_bgr(out_dir / "01_source_face.png", source_face_bgr)
    # Show warp/color in template space (mask region only; skip empty/black warp px)
    warped_vis = template_bgr.copy()
    matched_vis = template_bgr.copy()
    m = mask > 0
    valid = m & np.any(warped_bgr > 8, axis=2)
    if valid.any():
        warped_vis[valid] = warped_bgr[valid]
    valid_c = m & np.any(color_matched_bgr > 8, axis=2)
    if valid_c.any():
        matched_vis[valid_c] = color_matched_bgr[valid_c]
    save_bgr(out_dir / "02_warped_face.png", warped_vis)
    save_bgr(out_dir / "02_warped_face_raw.png", warped_bgr)
    save_bgr(out_dir / "03_mask.png", overlay_mask_on_template(template_bgr, mask))
    save_bgr(
        out_dir / "03_mask_raw.png",
        cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) if mask.ndim == 2 else mask,
    )
    save_bgr(out_dir / "04_color_matched.png", matched_vis)
    save_bgr(out_dir / "04_color_matched_raw.png", color_matched_bgr)
    if final_bgr is not None:
        save_bgr(out_dir / "05_final.png", final_bgr)
