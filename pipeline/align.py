"""
Geometric alignment — 106-pt piecewise-affine (Delaunay) with eyes-similarity fallback.
"""

from __future__ import annotations

import cv2
import numpy as np

from .face_model import DetectedFace
from .constants import PWA_LANDMARK_COUNT

MAX_SCALE_RATIO = 3.0
MIN_SCALE_RATIO = 0.15


class AlignmentError(ValueError):
    """Source/template geometry cannot be warped safely."""


def eye_distance(kps: np.ndarray) -> float:
    return float(np.linalg.norm(kps[0] - kps[1]) + 1e-6)


def similarity_from_eyes(src_kps: np.ndarray, dst_kps: np.ndarray) -> np.ndarray:
    src = np.asarray(src_kps, dtype=np.float64).reshape(-1, 2)
    dst = np.asarray(dst_kps, dtype=np.float64).reshape(-1, 2)
    s0, s1 = src[0], src[1]
    d0, d1 = dst[0], dst[1]
    src_mid = 0.5 * (s0 + s1)
    dst_mid = 0.5 * (d0 + d1)
    src_v = s1 - s0
    dst_v = d1 - d0
    src_dist = float(np.linalg.norm(src_v) + 1e-6)
    dst_dist = float(np.linalg.norm(dst_v) + 1e-6)
    scale = dst_dist / src_dist
    if not (MIN_SCALE_RATIO <= scale <= MAX_SCALE_RATIO):
        raise AlignmentError(
            f"Eye-distance scale {scale:.3f} outside [{MIN_SCALE_RATIO}, {MAX_SCALE_RATIO}]"
        )
    ang = float(np.arctan2(dst_v[1], dst_v[0]) - np.arctan2(src_v[1], src_v[0]))
    cos_a, sin_a = np.cos(ang), np.sin(ang)
    R = scale * np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=np.float64)
    t = dst_mid - R @ src_mid
    if src.shape[0] >= 3 and dst.shape[0] >= 3:
        src_nose = R @ src[2] + t
        t[1] += 0.35 * float(dst[2, 1] - src_nose[1])
    M = np.zeros((2, 3), dtype=np.float32)
    M[0, 0], M[0, 1], M[0, 2] = R[0, 0], R[0, 1], t[0]
    M[1, 0], M[1, 1], M[1, 2] = R[1, 0], R[1, 1], t[1]
    return M


def subsample_landmarks(pts: np.ndarray, n: int) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    if len(pts) <= n:
        return pts
    idx = np.linspace(0, len(pts) - 1, n).astype(int)
    return pts[idx]


def _triangle_indices(dst_pts: np.ndarray) -> list[tuple[int, int, int]]:
    """Delaunay triangulation on landmark indices (scipy — no remapping bugs)."""
    pts = np.asarray(dst_pts, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 3:
        return []
    try:
        from scipy.spatial import Delaunay

        # Qhull can fail on near-collinear sets
        tri = Delaunay(pts)
        return [tuple(map(int, s)) for s in tri.simplices]
    except Exception:
        return _triangle_indices_subdiv(pts)


def _triangle_indices_subdiv(dst_pts: np.ndarray) -> list[tuple[int, int, int]]:
    """Fallback Subdiv2D with careful nearest remapping."""
    pts = np.asarray(dst_pts, dtype=np.float32).reshape(-1, 2)
    x0, y0 = pts.min(axis=0) - 2
    x1, y1 = pts.max(axis=0) + 2
    w = int(max(8, np.ceil(x1 - x0)))
    h = int(max(8, np.ceil(y1 - y0)))
    subdiv = cv2.Subdiv2D((0, 0, w, h))
    local = pts - np.array([x0, y0], dtype=np.float32)
    for p in local:
        try:
            subdiv.insert((float(p[0]), float(p[1])))
        except cv2.error:
            continue
    try:
        raw = subdiv.getTriangleList()
    except cv2.error:
        return []

    def nearest(px: float, py: float) -> int:
        d = (local[:, 0] - px) ** 2 + (local[:, 1] - py) ** 2
        return int(np.argmin(d))

    uniq, seen = [], set()
    for t in raw:
        i0, i1, i2 = nearest(t[0], t[1]), nearest(t[2], t[3]), nearest(t[4], t[5])
        if len({i0, i1, i2}) < 3:
            continue
        key = tuple(sorted((i0, i1, i2)))
        if key not in seen:
            seen.add(key)
            uniq.append((i0, i1, i2))
    return uniq


def _warp_triangle(
    src: np.ndarray,
    dst: np.ndarray,
    src_tri: np.ndarray,
    dst_tri: np.ndarray,
) -> None:
    """Warp one triangle from src into dst (in-place)."""
    src_tri = np.asarray(src_tri, dtype=np.float32)
    dst_tri = np.asarray(dst_tri, dtype=np.float32)
    # Skip degenerate / flipped tiny triangles
    area = cv2.contourArea(dst_tri.reshape(-1, 1, 2))
    if abs(area) < 2.0:
        return
    r1 = cv2.boundingRect(src_tri)
    r2 = cv2.boundingRect(dst_tri)
    if r1[2] <= 0 or r1[3] <= 0 or r2[2] <= 0 or r2[3] <= 0:
        return
    # Clip rects to image bounds
    sh, sw = src.shape[:2]
    dh, dw = dst.shape[:2]
    if r1[0] < 0 or r1[1] < 0 or r1[0] + r1[2] > sw or r1[1] + r1[3] > sh:
        # Still try with clipped crop
        pass
    sx0 = max(0, r1[0])
    sy0 = max(0, r1[1])
    sx1 = min(sw, r1[0] + r1[2])
    sy1 = min(sh, r1[1] + r1[3])
    if sx1 <= sx0 or sy1 <= sy0:
        return
    src_crop = src[sy0:sy1, sx0:sx1]
    if src_crop.size == 0:
        return
    # Recompute local coords relative to clipped crop
    src_off = src_tri - np.array([sx0, sy0], dtype=np.float32)
    dst_off = dst_tri - np.array([r2[0], r2[1]], dtype=np.float32)
    try:
        M = cv2.getAffineTransform(src_off, dst_off)
    except cv2.error:
        return
    warped = cv2.warpAffine(
        src_crop,
        M,
        (r2[2], r2[3]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    mask = np.zeros((r2[3], r2[2]), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.round(dst_off).astype(np.int32), 255)
    y0, x0 = r2[1], r2[0]
    y1, x1 = min(dh, y0 + r2[3]), min(dw, x0 + r2[2])
    if y1 <= y0 or x1 <= x0:
        return
    mh, mw = y1 - y0, x1 - x0
    roi = dst[y0:y1, x0:x1]
    warped = warped[:mh, :mw]
    mask = mask[:mh, :mw]
    if roi.shape[:2] != mask.shape:
        return
    np.copyto(roi, warped, where=mask[..., None].astype(bool))


def piecewise_affine_warp(
    src_bgr: np.ndarray,
    src_pts: np.ndarray,
    dst_pts: np.ndarray,
    dst_shape: tuple[int, int],
) -> np.ndarray:
    """
    Warp src → dst image space by Delaunay triangles on corresponding landmarks.

    Base layer = eyes similarity (stable), then PWA overwrites the face hull.
    Outside the destination landmark hull the canvas stays black (clone mask gates it).
    """
    h, w = dst_shape[:2]
    src_pts = np.asarray(src_pts, dtype=np.float32).reshape(-1, 2)
    dst_pts = np.asarray(dst_pts, dtype=np.float32).reshape(-1, 2)
    if len(src_pts) != len(dst_pts) or len(src_pts) < 3:
        raise AlignmentError("Need matching landmark sets (≥3) for piecewise affine")

    # Stable base: prefer trailing 5-pt kps if present
    if len(src_pts) >= 7:
        s_k, d_k = src_pts[-5:], dst_pts[-5:]
    else:
        n = min(5, len(src_pts))
        s_k, d_k = src_pts[:n], dst_pts[:n]
    try:
        M = similarity_from_eyes(s_k, d_k)
    except AlignmentError:
        M = cv2.estimateAffinePartial2D(s_k, d_k)[0]
    if M is None:
        raise AlignmentError("Could not estimate base similarity for PWA")
    base = cv2.warpAffine(
        src_bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101
    )

    out = base.copy()
    tris = _triangle_indices(dst_pts)
    for i0, i1, i2 in tris:
        _warp_triangle(src_bgr, out, src_pts[[i0, i1, i2]], dst_pts[[i0, i1, i2]])
    return out


def crop_face_padded(
    bgr: np.ndarray,
    face: DetectedFace,
    pad: float = 0.45,
) -> tuple[np.ndarray, DetectedFace, tuple[int, int]]:
    h, w = bgr.shape[:2]
    x0, y0, x1, y1 = face.bbox
    bw, bh = x1 - x0, y1 - y0
    px, py = pad * bw, pad * bh
    cx0 = int(max(0, x0 - px))
    cy0 = int(max(0, y0 - py * 1.1))
    cx1 = int(min(w, x1 + px))
    cy1 = int(min(h, y1 + py * 0.9))
    crop = bgr[cy0:cy1, cx0:cx1].copy()
    off = np.array([cx0, cy0], dtype=np.float32)
    new_face = DetectedFace(
        bbox=face.bbox - np.array([cx0, cy0, cx0, cy0], dtype=np.float32),
        kps=face.kps - off,
        landmark_106=(
            None if face.landmark_106 is None else face.landmark_106 - off
        ),
        embedding=face.embedding,
        det_score=face.det_score,
    )
    return crop, new_face, (cx0, cy0)


def warp_face(
    src_bgr: np.ndarray,
    src_face: DetectedFace,
    dst_shape: tuple[int, int],
    dst_kps: np.ndarray,
    dst_face: DetectedFace | None = None,
    *,
    use_crop: bool = True,
    n_pwa_points: int = 48,
) -> tuple[np.ndarray, np.ndarray | None]:
    """
    Prefer 106-pt piecewise-affine; fall back to eyes-focused similarity.

    Returns (warped_bgr, M_or_None).
    """
    n = n_pwa_points or PWA_LANDMARK_COUNT
    work_bgr, work_face = src_bgr, src_face
    if use_crop:
        work_bgr, work_face, _ = crop_face_padded(src_bgr, src_face)

    h, w = dst_shape[:2]
    use_pwa = (
        work_face.landmark_106 is not None
        and dst_face is not None
        and dst_face.landmark_106 is not None
        and len(work_face.landmark_106) >= 20
        and len(dst_face.landmark_106) >= 20
    )
    if use_pwa:
        src_pts = subsample_landmarks(work_face.landmark_106, n)
        dst_pts = subsample_landmarks(dst_face.landmark_106, n)
        src_pts = np.vstack([src_pts, work_face.kps])
        dst_anchor = dst_face.kps if dst_face.kps is not None else dst_kps
        dst_pts = np.vstack([dst_pts, dst_anchor])
        warped = piecewise_affine_warp(work_bgr, src_pts, dst_pts, dst_shape)
        return warped, None

    M = similarity_from_eyes(work_face.kps, dst_kps)
    warped = cv2.warpAffine(
        work_bgr,
        M,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return warped, M
