"""
face_swap_processor.py - Post-AI face swapping via insightface.

After the AI renders the scene with generic faces, this module swaps
user-uploaded face photos onto the correct character positions by matching
left-to-right ordering with the blueprint metadata.

Dependencies: insightface, onnxruntime, opencv-python
"""

import os
import cv2
import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# Lazy-loaded model singleton
# ---------------------------------------------------------------------------
_detector = None
_swapper = None


def _load_models():
    global _detector, _swapper
    if _detector is not None:
        return
    try:
        from insightface.app import FaceAnalysis
        from insightface.model_zoo import get_model as get_swapper

        _detector = FaceAnalysis(name="buffalo_l", root="~/.insightface")
        _detector.prepare(ctx_id=-1, det_size=(640, 640))

        _swapper = get_swapper("inswapper_128.onnx", download=True, download_zip=True)
        print("  [FaceSwap] Models loaded successfully")
    except Exception as e:
        print(f"  [FaceSwap] Model init failed: {e}")


def _models_ready() -> bool:
    return _detector is not None and _swapper is not None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def swap_faces(
    ai_image_path: str,
    metadata: dict,
    face_map: dict[str, str],
) -> str:
    """
    Swap generic AI-generated faces with user-uploaded photos.

    Parameters
    ----------
    ai_image_path : str
        Path to the AI-generated JPEG image (generic faces).
    metadata : dict
        Blueprint metadata with character positions (sorted L-R later).
    face_map : dict[str, str]
        Mapping from role_key (e.g. 'user_name') to user photo file path.

    Returns
    -------
    str
        Path to the final image (swapped if successful, original otherwise).
    """
    _load_models()
    if not _models_ready():
        print("  [FaceSwap] Models not available, returning original")
        return ai_image_path

    img_bgr = cv2.imread(ai_image_path)
    if img_bgr is None:
        print(f"  [FaceSwap] Could not load {ai_image_path}")
        return ai_image_path

    # ---- Detect faces in AI image ----
    ai_faces = _detector.get(img_bgr)
    if not ai_faces:
        print("  [FaceSwap] No faces detected in AI image")
        return ai_image_path

    # Sort faces left-to-right by bounding-box center X
    ai_faces.sort(key=lambda f: f.bbox[0])

    # ---- Sort characters left-to-right from metadata ----
    characters = metadata.get("characters", [])
    sorted_chars = sorted(characters, key=lambda c: c["body_rect"]["x"])

    n = min(len(ai_faces), len(sorted_chars))
    if n != len(sorted_chars):
        print(f"  [FaceSwap] Face count mismatch: {len(ai_faces)} faces / {len(sorted_chars)} chars")

    swapped_any = False
    for idx in range(n):
        char = sorted_chars[idx]
        role_key = char["role_key"]
        face_path = face_map.get(role_key)

        if not face_path or not os.path.exists(face_path):
            continue

        user_img = cv2.imread(face_path)
        if user_img is None:
            continue

        user_faces = _detector.get(user_img)
        if not user_faces:
            print(f"  [FaceSwap] No face in user photo '{face_path}', skipping {role_key}")
            continue

        # Use the largest face from the user photo
        user_face = max(user_faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

        # Swap
        target_face = ai_faces[idx]
        img_bgr = _swapper.get(img_bgr, target_face, user_face, paste_back=True)
        swapped_any = True
        print(f"  [FaceSwap] Swapped '{role_key}' (L-R #{idx}, body X={char['body_rect']['x']})")

    if not swapped_any:
        print("  [FaceSwap] No swaps performed")
        return ai_image_path

    # Save result to a new path (don't overwrite original)
    base, ext = os.path.splitext(ai_image_path)
    result_path = f"{base}_swapped{ext}"
    cv2.imwrite(result_path, img_bgr)
    print(f"  [FaceSwap] Saved: {result_path}")
    return result_path


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    test_ai = "test_rendered.jpg"
    test_meta_path = "test_metadata.json"
    test_faces = "personalized_faces"

    if not os.path.exists(test_ai):
        print("No test_rendered.jpg found. Generate one with ai_renderer.py first.")
        exit(0)

    meta = {}
    if os.path.exists(test_meta_path):
        with open(test_meta_path) as f:
            meta = json.load(f)

    face_map = {}
    if os.path.isdir(test_faces):
        for fn in os.listdir(test_faces):
            if fn.endswith((".png", ".jpg", ".jpeg")):
                role = fn.replace("_face.png", "").replace("_face.jpg", "")
                rk_map = {
                    "user": "user_name", "mother": "mother_name",
                    "father": "father_name", "grandmother": "grandmother_name",
                    "grandfather": "grandfather_name", "sibling": "sibling_name",
                }
                if role in rk_map:
                    face_map[rk_map[role]] = os.path.join(test_faces, fn)

    result = swap_faces(test_ai, meta, face_map)
    print(f"Result: {result}")
