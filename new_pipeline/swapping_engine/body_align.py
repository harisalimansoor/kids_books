"""
body_align.py
─────────────────────────────────────────────────────────────────────────────
Body-aware head placement for face swap:

  • Face detection (YuNet landmarks) — scale + eye-line tilt
  • Torso skin segmentation + MediaPipe selfie mask — neck / collar anchor
  • OpenCV HOG person detector — body width / head-to-body proportion
  • Optional MediaPipe pose — shoulder line when available
  • Post-blend position guard — reject AI face drift off the body
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from PIL import Image

from swapping_engine.face_detect import detect_faces, interocular


def face_eye_tilt_deg(face: dict) -> float:
    """Eye-line angle in degrees (positive = clockwise in image coords)."""
    lm = face.get("landmarks") or {}
    re, le = lm.get("right_eye"), lm.get("left_eye")
    if not re or not le or len(re) < 2 or len(le) < 2:
        return 0.0
    dx = float(le[0]) - float(re[0])
    dy = float(le[1]) - float(re[1])
    if abs(dx) < 1e-3:
        return 0.0
    return math.degrees(math.atan2(dy, dx))


def _skin_mask_rgb(arr: np.ndarray) -> np.ndarray:
    """Rough skin segmentation (HSV + RGB heuristics)."""
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx = np.maximum(np.maximum(r, g), b).astype(np.float32)
    mn = np.minimum(np.minimum(r, g), b).astype(np.float32)
    sat = mx - mn
    return (
        (r > 55)
        & (g > 30)
        & (b > 20)
        & (r >= g)
        & ((r.astype(np.int16) - g.astype(np.int16)) >= 5)
        & (sat < 110)
        & (mx > 45)
    )


def _body_width_from_segmentation(
    arr: np.ndarray,
    face: dict,
    *,
    canvas_w: int,
    canvas_h: int,
) -> dict[str, float] | None:
    """
    Estimate torso width from skin segmentation below the chin (no ML model required).
    """
    fx = int(face["x"])
    fy = int(face["y"])
    fw = max(8, int(face["w"]))
    fh = max(8, int(face["h"]))
    y0 = min(canvas_h - 1, fy + int(0.55 * fh))
    y1 = min(canvas_h, fy + fh + int(1.35 * fh))
    x0 = max(0, fx - int(0.85 * fw))
    x1 = min(canvas_w, fx + fw + int(0.85 * fw))
    if y1 - y0 < 8 or x1 - x0 < 8:
        return None

    band = arr[y0:y1, x0:x1]
    skin = _skin_mask_rgb(band)
    if int(skin.sum()) < 60:
        return None

    row_counts = skin.sum(axis=1)
    if row_counts.max() < 8:
        return None
    shoulder_row = int(np.argmax(row_counts))
    row = skin[shoulder_row]
    xs = np.where(row)[0]
    if len(xs) < 10:
        return None
    bw = float(xs[-1] - xs[0] + 1)
    return {
        "x": float(x0 + xs[0]),
        "y": float(y0 + shoulder_row),
        "w": bw,
        "h": float(y1 - y0),
        "shoulder_y": float(y0 + shoulder_row),
        "shoulder_w": bw,
    }


def _hog_person_bbox(
    arr: np.ndarray,
    face: dict,
    *,
    canvas_w: int,
    canvas_h: int,
) -> dict[str, float] | None:
    """
    OpenCV HOG person detector — torso bbox for head/body proportion checks.
    Crops around the annotated face and picks the detection best overlapping it.
    """
    try:
        import cv2
        if not hasattr(cv2, "HOGDescriptor"):
            return None
    except ImportError:
        return None

    fx = int(face["x"])
    fy = int(face["y"])
    fw = max(8, int(face["w"]))
    fh = max(8, int(face["h"]))
    pad_x = int(max(fw, fh) * 1.6)
    pad_y_top = int(max(fw, fh) * 0.5)
    pad_y_bot = int(max(fw, fh) * 3.2)
    x0 = max(0, fx - pad_x)
    y0 = max(0, fy - pad_y_top)
    x1 = min(canvas_w, fx + fw + pad_x)
    y1 = min(canvas_h, fy + fh + pad_y_bot)
    crop = arr[y0:y1, x0:x1]
    if crop.size < 400:
        return None

    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    rects, weights = hog.detectMultiScale(
        gray,
        winStride=(8, 8),
        padding=(8, 8),
        scale=1.05,
    )
    if len(rects) == 0:
        return None

    face_cx = fx + fw / 2.0
    face_cy = fy + fh / 2.0
    best = None
    best_score = -1.0
    for (rx, ry, rw, rh), wt in zip(rects, weights):
        bx0 = x0 + rx
        by0 = y0 + ry
        bx1 = bx0 + rw
        by1 = by0 + rh
        if not (bx0 <= face_cx <= bx1 and by0 <= face_cy <= by1 + 0.15 * rh):
            continue
        head_band = by0 + 0.42 * rh
        if face_cy > head_band:
            continue
        score = float(wt) * rw * rh
        if score > best_score:
            best_score = score
            best = {
                "x": float(bx0),
                "y": float(by0),
                "w": float(rw),
                "h": float(rh),
                "shoulder_y": float(by0 + 0.38 * rh),
                "shoulder_w": float(rw),
            }
    return best


def _selfie_segment_neck(
    image: Image.Image,
    face: dict,
) -> tuple[float, float] | None:
    """MediaPipe selfie segmentation → neck point below chin (when installed)."""
    try:
        import mediapipe as mp
    except ImportError:
        return None

    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    fx = int(face["x"])
    fy = int(face["y"])
    fw = max(8, int(face["w"]))
    fh = max(8, int(face["h"]))
    with mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1) as seg:
        mask = seg.process(rgb).segmentation_mask
    if mask is None:
        return None

    y0 = min(h - 1, fy + int(0.65 * fh))
    y1 = min(h, fy + fh + int(0.70 * fh))
    x0 = max(0, fx - int(0.20 * fw))
    x1 = min(w, fx + fw + int(0.20 * fw))
    if y1 - y0 < 4:
        return None

    band = mask[y0:y1, x0:x1] > 0.55
    if int(band.sum()) < 30:
        return None
    ys, xs = np.where(band)
    cut = int(len(ys) * 0.50)
    ys_l = ys[cut:] if cut > 0 else ys
    xs_l = xs[cut:] if cut > 0 else xs
    if len(xs_l) < 8:
        ys_l, xs_l = ys, xs
    return float(x0 + xs_l.mean()), float(y0 + ys_l.mean())


def _segment_neck_from_skin(
    arr: np.ndarray,
    face: dict,
    *,
    canvas_w: int,
    canvas_h: int,
) -> tuple[float, float] | None:
    """
    Find neck anchor as skin centroid in a band just below the YuNet face box.
    Returns (neck_x, neck_y) in canvas coordinates.
    """
    fx = int(face["x"])
    fy = int(face["y"])
    fw = max(8, int(face["w"]))
    fh = max(8, int(face["h"]))
    y0 = min(canvas_h - 1, fy + int(0.72 * fh))
    y1 = min(canvas_h, fy + fh + int(0.55 * fh))
    x0 = max(0, fx - int(0.12 * fw))
    x1 = min(canvas_w, fx + fw + int(0.12 * fw))
    if y1 - y0 < 6 or x1 - x0 < 6:
        return None

    band = arr[y0:y1, x0:x1]
    skin = _skin_mask_rgb(band)
    if int(skin.sum()) < 40:
        return None

    ys, xs = np.where(skin)
    # Neck = lower third of skin band (collar area, not cheeks)
    cut = int(len(ys) * 0.55)
    if cut < 5:
        cut = max(1, len(ys) // 2)
    ys_l = ys[cut:]
    xs_l = xs[cut:]
    if len(xs_l) < 5:
        ys_l, xs_l = ys, xs
    return float(x0 + xs_l.mean()), float(y0 + ys_l.mean())


def _pose_shoulder_line(image: Image.Image, face: dict) -> tuple[float, float, float] | None:
    """
    MediaPipe pose → shoulder midpoint + line angle (degrees).
    Returns (mid_x, mid_y, angle_deg) or None.
    """
    try:
        import mediapipe as mp
    except ImportError:
        return None

    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    fx = int(face["x"])
    fy = int(face["y"])
    fw = max(8, int(face["w"]))
    fh = max(8, int(face["h"]))
    # Crop around person for speed
    pad = int(max(fw, fh) * 1.8)
    x0 = max(0, fx - pad)
    y0 = max(0, fy - int(0.3 * fh))
    x1 = min(w, fx + fw + pad)
    y1 = min(h, fy + fh + int(2.2 * fh))
    crop = rgb[y0:y1, x0:x1]
    if crop.size < 100:
        return None

    with mp.solutions.pose.Pose(
        static_image_mode=True,
        model_complexity=0,
        min_detection_confidence=0.45,
    ) as pose:
        res = pose.process(crop)
    if not res.pose_landmarks:
        return None

    lm = res.pose_landmarks.landmark
    ch, cw = crop.shape[:2]

    def pt(idx: int) -> tuple[float, float]:
        p = lm[idx]
        return x0 + p.x * cw, y0 + p.y * ch

    # MediaPipe pose indices: 11=left shoulder, 12=right shoulder
    ls, rs = pt(11), pt(12)
    mid_x = 0.5 * (ls[0] + rs[0])
    mid_y = 0.5 * (ls[1] + rs[1])
    angle = math.degrees(math.atan2(rs[1] - ls[1], rs[0] - ls[0]))
    return mid_x, mid_y, angle


def estimate_body_anchor(
    canvas: Image.Image,
    face_region: dict,
) -> dict[str, Any]:
    """
    Neck / shoulder anchor for seating a swapped head on the template body.

    Combines object (HOG person) + pose + segmentation for neck/shoulder seating.
    Coordinates are absolute canvas pixels.
    """
    arr = np.asarray(canvas.convert("RGB"))
    ch, cw = arr.shape[:2]
    face = {
        "x": int(face_region["x"]),
        "y": int(face_region["y"]),
        "w": max(8, int(face_region["w"])),
        "h": max(8, int(face_region["h"])),
        "landmarks": face_region.get("landmarks") or {},
    }

    fx, fy, fw, fh = face["x"], face["y"], face["w"], face["h"]
    chin_y = fy + int(0.92 * fh)
    chin_x = fx + fw // 2

    lm = face.get("landmarks") or {}
    if lm.get("nose") and lm.get("mouth_right") and lm.get("mouth_left"):
        chin_y = int(0.55 * lm["nose"][1] + 0.45 * 0.5 * (lm["mouth_right"][1] + lm["mouth_left"][1]))
    if lm.get("right_eye") and lm.get("left_eye"):
        chin_x = int(0.5 * (lm["right_eye"][0] + lm["left_eye"][0]))

    neck = _segment_neck_from_skin(arr, face, canvas_w=cw, canvas_h=ch)
    try:
        seg_neck = _selfie_segment_neck(canvas, face)
    except Exception:
        seg_neck = None
    try:
        person = _hog_person_bbox(arr, face, canvas_w=cw, canvas_h=ch)
    except Exception:
        person = None
    if person is None:
        try:
            person = _body_width_from_segmentation(arr, face, canvas_w=cw, canvas_h=ch)
        except Exception:
            person = None
    try:
        pose = _pose_shoulder_line(canvas, face)
    except Exception:
        pose = None

    neck_x, neck_y = float(chin_x), float(chin_y + 0.08 * fh)
    shoulder_angle = face_eye_tilt_deg(face) * 0.35
    method = "face_heuristic"
    body_w = float(fw) * 1.65
    head_to_body = float(fw) / max(body_w, 1.0)

    if neck:
        neck_x, neck_y = neck
        method = "segment"

    if seg_neck:
        sx, sy = seg_neck
        neck_x = 0.55 * neck_x + 0.45 * sx
        neck_y = 0.50 * neck_y + 0.50 * sy
        method = "segment+selfie" if neck else "selfie"

    if person:
        body_w = max(person["shoulder_w"], person["w"] * 0.92)
        head_to_body = float(fw) / max(body_w, 1.0)
        if person.get("shoulder_y"):
            neck_y = 0.55 * neck_y + 0.45 * float(person["shoulder_y"])
        method = f"{method}+body" if method != "face_heuristic" else "body"

    if pose:
        _, shoulder_y, shoulder_angle = pose
        neck_y = 0.65 * neck_y + 0.35 * (shoulder_y - 0.12 * fh)
        method = "pose+" + method if method != "face_heuristic" else "pose"

    return {
        "neck_x": neck_x,
        "neck_y": neck_y,
        "chin_x": float(chin_x),
        "chin_y": float(chin_y),
        "shoulder_angle_deg": float(shoulder_angle),
        "face_tilt_deg": face_eye_tilt_deg(face),
        "interocular": interocular(face),
        "body_width": body_w,
        "head_to_body": head_to_body,
        "method": method,
    }


def rel_anchor_in_paste(anchor: dict[str, Any], paste_x: int, paste_y: int) -> dict[str, Any]:
    """Convert canvas-absolute body anchor to paste-box-relative coords."""
    out = dict(anchor)
    for key in ("neck_x", "neck_y", "chin_x", "chin_y"):
        if key in out:
            if key.endswith("_x"):
                out[key] = float(out[key]) - paste_x
            else:
                out[key] = float(out[key]) - paste_y
    return out


def _face_box_in_rgba(src: Image.Image) -> dict | None:
    faces = detect_faces(src.convert("RGB")) or []
    if not faces:
        return None
    f = max(faces, key=lambda ff: ff["w"] * ff["h"])
    return {
        "x": int(f["x"]),
        "y": int(f["y"]),
        "w": int(f["w"]),
        "h": int(f["h"]),
        "landmarks": f.get("landmarks") or {},
    }


def _rotate_rgba(img: Image.Image, angle_deg: float) -> Image.Image:
    if abs(angle_deg) < 0.35:
        return img
    return img.rotate(
        -angle_deg,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(0, 0, 0, 0),
    )


def align_head_in_box(
    src: Image.Image,
    box_w: int,
    box_h: int,
    target_face: dict,
    *,
    body_anchor: dict[str, Any] | None = None,
    max_tilt_deg: float = 10.0,
) -> Image.Image:
    """
    Place upload head so face landmarks + neck anchor match the template body.

    Uses eye-line rotation (pose/landmarks), scale from interocular distance,
    and vertical seat from neck/collar anchor when available.
    """
    src = src.convert("RGBA")
    sw, sh = src.size
    if sw < 1 or sh < 1 or box_w < 8 or box_h < 8:
        return Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))

    tx = max(0, min(int(target_face["x"]), box_w - 8))
    ty = max(0, min(int(target_face["y"]), box_h - 8))
    tw = max(8, min(int(target_face["w"]), box_w - tx))
    th = max(8, min(int(target_face["h"]), box_h - ty))

    target_rel = {
        "x": tx,
        "y": ty,
        "w": tw,
        "h": th,
        "landmarks": target_face.get("landmarks") or {},
    }

    src_face = _face_box_in_rgba(src)
    if src_face is None:
        src_face = {
            "x": int(0.22 * sw),
            "y": int(0.38 * sh),
            "w": max(8, int(0.56 * sw)),
            "h": max(8, int(0.42 * sh)),
        }

    # Match eye-line tilt (small rotation only)
    tilt_t = face_eye_tilt_deg(target_rel)
    tilt_s = face_eye_tilt_deg(src_face)
    delta_tilt = max(-max_tilt_deg, min(max_tilt_deg, tilt_t - tilt_s))
    if abs(delta_tilt) > 0.4:
        # Rotate about source face center before scaling
        scx0 = src_face["x"] + src_face["w"] / 2.0
        scy0 = src_face["y"] + src_face["h"] / 2.0
        rotated = _rotate_rgba(src, delta_tilt)
        # Map face center through rotation (approximate: re-detect)
        src = rotated
        sw, sh = src.size
        src_face = _face_box_in_rgba(src) or src_face

    sfw = max(8, int(src_face["w"]))
    sfh = max(8, int(src_face["h"]))
    scx = src_face["x"] + sfw / 2.0
    scy = src_face["y"] + sfh / 2.0

    t_iod = max(8.0, interocular(target_rel))
    s_iod = max(8.0, interocular(src_face) if src_face.get("landmarks") else sfw * 0.55)
    scale_iod = (t_iod / s_iod) * 0.97
    scale_box = 0.5 * (tw / sfw + th / sfh) * 0.96
    scale_face = tw / sfw
    scale = 0.48 * scale_iod + 0.32 * scale_box + 0.20 * scale_face
    scale = max(scale, max(box_w / sw, box_h / sh) * 0.52)
    scale = min(scale, max(box_w / sw, box_h / sh) * 1.12)
    # Keep head width proportional to template body (HOG / annotated box)
    scale = max(scale_face * 0.86, min(scale, scale_face * 1.08))
    if body_anchor and body_anchor.get("head_to_body"):
        htb = float(body_anchor["head_to_body"])
        htb = max(0.26, min(0.55, htb))
        bw = float(body_anchor.get("body_width") or tw / max(htb, 0.26))
        target_fw = htb * bw
        if target_fw > 8:
            scale_body = target_fw / sfw
            scale = 0.70 * scale + 0.30 * scale_body
            scale = max(scale_face * 0.84, min(scale, scale_face * 1.10))

    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)

    # Target anchor: eye midpoint for X, mouth/nose for Y; neck pulls chin down
    t_lm = target_rel.get("landmarks") or {}
    if t_lm.get("right_eye") and t_lm.get("left_eye"):
        tcx = 0.5 * (float(t_lm["right_eye"][0]) + float(t_lm["left_eye"][0]))
    else:
        tcx = tx + tw / 2.0
    if t_lm.get("nose"):
        ny = float(t_lm["nose"][1])
        if t_lm.get("mouth_right") and t_lm.get("mouth_left"):
            my = 0.5 * (float(t_lm["mouth_right"][1]) + float(t_lm["mouth_left"][1]))
            tcy = 0.52 * ny + 0.48 * my
        else:
            tcy = ny
    else:
        tcy = ty + th * 0.58

    if body_anchor:
        if "neck_x" in body_anchor:
            tcx = 0.72 * tcx + 0.28 * float(body_anchor["neck_x"])
        if "neck_y" in body_anchor:
            tcy = 0.55 * tcy + 0.45 * float(body_anchor["neck_y"])

    s_lm = src_face.get("landmarks") or {}
    if s_lm.get("right_eye") and s_lm.get("left_eye"):
        scx = 0.5 * (float(s_lm["right_eye"][0]) + float(s_lm["left_eye"][0]))
    else:
        scx = src_face["x"] + sfw / 2.0
    if s_lm.get("nose"):
        ny = float(s_lm["nose"][1])
        if s_lm.get("mouth_right") and s_lm.get("mouth_left"):
            my = 0.5 * (float(s_lm["mouth_right"][1]) + float(s_lm["mouth_left"][1]))
            scy = 0.52 * ny + 0.48 * my
        else:
            scy = ny

    scx_s = scx * scale
    scy_s = scy * scale
    ox = int(round(tcx - scx_s))
    oy = int(round(tcy - scy_s)) + max(1, int(0.04 * th))

    out = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    out.paste(resized, (ox, oy), resized)
    return out


def face_centroid(face: dict) -> tuple[float, float]:
    lm = face.get("landmarks") or {}
    if lm.get("right_eye") and lm.get("left_eye"):
        cx = 0.5 * (float(lm["right_eye"][0]) + float(lm["left_eye"][0]))
        cy = 0.5 * (float(lm["right_eye"][1]) + float(lm["left_eye"][1]))
        return cx, cy
    return float(face["x"]) + float(face["w"]) / 2.0, float(face["y"]) + float(face["h"]) / 2.0


def snap_ai_faces_to_reference(
    reference: Image.Image,
    ai: Image.Image,
    face_regions: list[dict],
    *,
    max_shift_frac: float = 0.10,
    max_tilt_drift_deg: float = 8.0,
) -> Image.Image:
    """
    If AI shifted/tilted a face off the body, re-seat the AI face patch.

    Critical: never alpha-blend the repositioned AI face over an intact soft-paste
    face with a wide Gaussian mask — that creates temple/double-face ghosting.
    Old face footprint is erased first; paste uses a near-binary feather.
    If the result still looks like 2 faces, fall back to soft-paste for that region.
    """
    from PIL import ImageDraw, ImageFilter

    if ai.size != reference.size:
        ai = ai.resize(reference.size, Image.Resampling.LANCZOS)

    out = ai.convert("RGB").copy()
    ref = reference.convert("RGB")
    W, H = ref.size

    for region in face_regions:
        x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
        pad = int(0.40 * max(w, h))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
        if x1 - x0 < 16 or y1 - y0 < 16:
            continue

        ref_crop = ref.crop((x0, y0, x1, y1))
        ai_crop = out.crop((x0, y0, x1, y1))
        rf = detect_faces(ref_crop) or []
        af = detect_faces(ai_crop) or []
        if not rf or not af:
            continue
        r = max(rf, key=lambda f: f["w"] * f["h"])
        a = max(af, key=lambda f: f["w"] * f["h"])

        rcx, rcy = face_centroid(r)
        acx, acy = face_centroid(a)
        dx = acx - rcx
        dy = acy - rcy
        max_shift = max_shift_frac * max(w, h)
        tilt_drift = abs(face_eye_tilt_deg(a) - face_eye_tilt_deg(r))

        area_r = max(1.0, float(r["w"] * r["h"]))
        area_a = float(a["w"] * a["h"])
        grow = (area_a / area_r) ** 0.5

        needs_snap = (
            abs(dx) > max_shift
            or abs(dy) > max_shift
            or grow > 1.12
            or grow < 0.88
            or tilt_drift > max_tilt_drift_deg
        )
        if not needs_snap:
            continue

        role = region.get("role") or "face"

        # Large structural drift: keep soft-paste — snapping would fight the AI
        # and often ghosts. Mild drift still gets a clean reseat below.
        severe = (
            abs(dx) > 1.6 * max_shift
            or abs(dy) > 1.6 * max_shift
            or grow > 1.22
            or grow < 0.80
            or tilt_drift > 1.5 * max_tilt_drift_deg
        )
        if severe:
            out.paste(ref_crop, (x0, y0))
            print(
                f"     ↳ body-lock {role}: severe drift "
                f"shift=({dx:.0f},{dy:.0f}) grow={grow:.2f} tiltΔ={tilt_drift:.1f}° "
                f"→ kept soft-paste (no ghost composite)"
            )
            continue

        shrink = 1.0 / max(grow, 1e-3)
        shrink = max(0.82, min(1.18, shrink))
        aw, ah = ai_crop.size
        nw = max(8, int(round(aw * shrink)))
        nh = max(8, int(round(ah * shrink)))
        scaled = ai_crop.resize((nw, nh), Image.Resampling.LANCZOS)
        acx_s = acx * shrink
        acy_s = acy * shrink
        ox = int(round(rcx - acx_s))
        oy = int(round(rcy - acy_s))

        canvas = ref_crop.copy()
        # Erase old soft-paste face so it cannot show through fractional alpha
        erase = Image.new("L", canvas.size, 0)
        ex0 = max(0, int(r["x"] - 0.18 * r["w"]))
        ey0 = max(0, int(r["y"] - 0.22 * r["h"]))
        ex1 = min(canvas.size[0], int(r["x"] + 1.18 * r["w"]))
        ey1 = min(canvas.size[1], int(r["y"] + 1.20 * r["h"]))
        ImageDraw.Draw(erase).ellipse((ex0, ey0, ex1, ey1), fill=255)
        # Fill erased footprint from the *aligned* AI patch (opaque), not soft face
        fill_patch = Image.new("RGB", canvas.size, (0, 0, 0))
        fill_patch.paste(scaled, (ox, oy))
        canvas.paste(fill_patch, (0, 0), erase)

        # Near-binary paste mask — tiny feather only (no wide ghost band)
        mask = Image.new("L", (nw, nh), 0)
        inset = max(1, min(nw, nh) // 28)
        ImageDraw.Draw(mask).ellipse((inset, inset, nw - inset, nh - inset), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(2))
        canvas.paste(scaled, (ox, oy), mask)

        # Safety: if snap still yields 2 faces, fall back to soft-paste
        check = detect_faces(canvas) or []
        if len(check) >= 2:
            out.paste(ref_crop, (x0, y0))
            print(
                f"     ↳ body-lock {role}: post-snap double-face "
                f"→ kept soft-paste"
            )
            continue

        out.paste(canvas, (x0, y0))
        print(
            f"     ↳ body-lock {role}: shift=({dx:.0f},{dy:.0f})px "
            f"grow={grow:.2f} tiltΔ={tilt_drift:.1f}° → snapped (erased old face)"
        )

    return out
