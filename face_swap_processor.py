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

        _swapper = get_swapper("inswapper_128.onnx", download=True, download_zip=False)
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
    """Face swap is currently disabled. Returns the original image path unchanged."""
    return ai_image_path
