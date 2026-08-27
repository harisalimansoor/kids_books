"""Face + neck mask construction from InsightFace landmarks."""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from .face_model import DetectedFace

_JAW_106 = list(range(0, 33))


def face_neck_mask(
    image_shape: tuple[int, int],
    face: DetectedFace,
    *,
    neck_extend: float = 0.18,
    feather_frac: float = 0.24,
) -> np.ndarray:
    """
    Soft uint8 mask (0–255) for face + short neck.

    - Inset from hairline/ears to avoid dark hair smudges
    - Wider neck taper so jaw→neck blends instead of a cut chin
    - Distance-transform feather (smooth falloff, not a hard sticker edge)
    """
    h, w = image_shape[:2]
    hard = np.zeros((h, w), dtype=np.uint8)

    poly = _mask_polygon(face, neck_extend=neck_extend)
    if poly is None or len(poly) < 3:
        x0, y0, x1, y1 = face.bbox
        cx = 0.5 * (x0 + x1)
        cy = y0 + 0.52 * (y1 - y0)
        ax = 0.34 * (x1 - x0)
        ay = 0.48 * (y1 - y0) * (1.0 + neck_extend * 0.35)
        cv2.ellipse(
            hard,
            (int(cx), int(cy)),
            (max(4, int(ax)), max(4, int(ay))),
            0,
            0,
            360,
            255,
            -1,
        )
    else:
        cv2.fillConvexPoly(hard, poly.astype(np.int32), 255)

    # Stronger inset at the top (hairline) than the bottom (keep neck)
    face_min = max(24.0, float(min(face.width, face.height)))
    k_side = max(3, int(face_min * 0.045) | 1)
    hard = cv2.erode(hard, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_side, k_side)))

    # Soft hairline fade (avoid hard forehead seam)
    x0, y0, x1, y1 = [int(v) for v in face.bbox]
    hair_band = int(0.28 * max(1, y1 - y0))
    y_start = max(0, y0)
    y_end = min(h, y0 + hair_band)
    if y_end > y_start:
        for i, y in enumerate(range(y_start, y_end)):
            # 0 at top of band → 1 at bottom
            t = (i + 1) / max(1, y_end - y_start)
            hard[y, :] = (hard[y, :].astype(np.float32) * t).astype(np.uint8)
        _, hard = cv2.threshold(hard, 40, 255, cv2.THRESH_BINARY)

    # Keep mask off the body/shirt: clamp below chin + small neck only
    chin_limit = int(min(h - 1, y1 + 0.12 * max(1, y1 - y0)))
    if chin_limit + 1 < h:
        hard[chin_limit + 1 :, :] = 0

    # Smooth the binary silhouette before feathering
    hard = cv2.GaussianBlur(hard, (0, 0), sigmaX=1.2)
    _, hard = cv2.threshold(hard, 127, 255, cv2.THRESH_BINARY)

    feather_px = max(8.0, face_min * feather_frac)
    dilate_px = int(max(5, round(feather_px * 1.35))) | 1
    outer = cv2.dilate(
        hard,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px, dilate_px)),
    )
    # Distance from outside → high in center, 0 at outer rim
    dt = cv2.distanceTransform(outer, cv2.DIST_L2, 5)
    soft = np.clip(dt / feather_px, 0.0, 1.0)
    # Cosine ease for a gentler cheek/hairline rim
    soft = 0.5 - 0.5 * np.cos(np.pi * soft)
    soft_u8 = (soft * 255.0).astype(np.uint8)
    soft_u8[outer == 0] = 0
    return soft_u8


def blend_masks(soft_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    soft = soft_mask.copy()
    if soft.dtype != np.uint8:
        soft = soft.astype(np.uint8)
    _, hard = cv2.threshold(soft, 8, 255, cv2.THRESH_BINARY)
    return hard, soft


def _mask_polygon(face: DetectedFace, neck_extend: float) -> Optional[np.ndarray]:
    """Oval-ish face hull: drop temples/hair, keep cheeks + tapered neck."""
    if face.landmark_106 is not None and face.landmark_106.shape[0] >= 33:
        lm = face.landmark_106
        try:
            jaw = lm[_JAW_106]
        except Exception:
            jaw = lm
        ys = jaw[:, 1]
        # Drop upper temple/hair points more aggressively
        y_cut = float(np.quantile(ys, 0.28))
        jaw = jaw[ys >= y_cut]
        # Shrink cheeks inward toward nose (away from ears)
        cx = float(face.center[0])
        jaw = jaw.copy()
        jaw[:, 0] = cx + 0.82 * (jaw[:, 0] - cx)
        pts = np.vstack([jaw, face.kps])
    else:
        kps = face.kps
        x0, y0, x1, y1 = face.bbox
        chin = np.array([[0.5 * (x0 + x1), y1 - 0.04 * (y1 - y0)]], dtype=np.float32)
        left_cheek = np.array(
            [[x0 + 0.18 * (x1 - x0), 0.58 * (y0 + y1)]], dtype=np.float32
        )
        right_cheek = np.array(
            [[x1 - 0.18 * (x1 - x0), 0.58 * (y0 + y1)]], dtype=np.float32
        )
        # Forehead well below hairline
        forehead = np.array(
            [[0.5 * (x0 + x1), y0 + 0.30 * (y1 - y0)]], dtype=np.float32
        )
        pts = np.vstack([kps, chin, left_cheek, right_cheek, forehead])

    if pts is None or len(pts) < 3:
        return None

    hull = cv2.convexHull(pts.astype(np.float32)).reshape(-1, 2)
    y_max = float(hull[:, 1].max())
    x_mid = float(hull[:, 0].mean())
    face_h = float(face.height)
    face_w = float(face.width)
    neck_dy = neck_extend * face_h
    # Tapered neck — wider at jaw, narrower lower (looks less like a stamp)
    neck_pts = np.array(
        [
            [x_mid - 0.22 * face_w, y_max + neck_dy * 0.15],
            [x_mid - 0.16 * face_w, y_max + neck_dy * 0.55],
            [x_mid, y_max + neck_dy],
            [x_mid + 0.16 * face_w, y_max + neck_dy * 0.55],
            [x_mid + 0.22 * face_w, y_max + neck_dy * 0.15],
        ],
        dtype=np.float32,
    )
    return cv2.convexHull(np.vstack([hull, neck_pts])).reshape(-1, 2)


def mask_center(mask: np.ndarray) -> tuple[int, int]:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        h, w = mask.shape[:2]
        return (w // 2, h // 2)
    return (int(xs.mean()), int(ys.mean()))


def landmarks_dict_from_kps(kps: np.ndarray) -> dict:
    return {
        "right_eye": [float(kps[0, 0]), float(kps[0, 1])],
        "left_eye": [float(kps[1, 0]), float(kps[1, 1])],
        "nose": [float(kps[2, 0]), float(kps[2, 1])],
        "mouth_right": [float(kps[3, 0]), float(kps[3, 1])],
        "mouth_left": [float(kps[4, 0]), float(kps[4, 1])],
    }


def kps_from_landmarks_dict(d: dict) -> np.ndarray:
    return np.array(
        [
            d["right_eye"],
            d["left_eye"],
            d["nose"],
            d["mouth_right"],
            d["mouth_left"],
        ],
        dtype=np.float32,
    )
