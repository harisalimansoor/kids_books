"""InsightFace buffalo_l wrapper — detection, landmarks, embeddings only.

No inswapper / generative swap models.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import cv2
import numpy as np


@dataclass
class DetectedFace:
    bbox: np.ndarray  # (4,) xyxy float
    kps: np.ndarray  # (5, 2) — right_eye, left_eye, nose, mouth_right, mouth_left
    landmark_106: Optional[np.ndarray]  # (106, 2) or None
    embedding: Optional[np.ndarray]  # (512,) or None
    det_score: float

    @property
    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bbox
        return (0.5 * (x0 + x1), 0.5 * (y0 + y1))

    @property
    def width(self) -> float:
        return float(self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return float(self.bbox[3] - self.bbox[1])


class FaceDetector:
    """Lazy singleton around insightface FaceAnalysis(buffalo_l)."""

    def __init__(self, det_size: tuple[int, int] = (640, 640), ctx_id: int = -1):
        self.det_size = det_size
        self.ctx_id = ctx_id
        self._app = None

    def _ensure(self):
        if self._app is not None:
            return
        from insightface.app import FaceAnalysis

        providers = ["CPUExecutionProvider"]
        try:
            import onnxruntime as ort

            if "CUDAExecutionProvider" in ort.get_available_providers():
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        except Exception:
            pass

        app = FaceAnalysis(name="buffalo_l", providers=providers)
        app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)
        self._app = app

    def detect(self, bgr: np.ndarray) -> list[DetectedFace]:
        self._ensure()
        faces = self._app.get(bgr)
        out: list[DetectedFace] = []
        for f in faces:
            lm106 = getattr(f, "landmark_2d_106", None)
            if lm106 is not None:
                lm106 = np.asarray(lm106, dtype=np.float32)
            emb = getattr(f, "embedding", None)
            if emb is not None:
                emb = np.asarray(emb, dtype=np.float32)
            out.append(
                DetectedFace(
                    bbox=np.asarray(f.bbox, dtype=np.float32),
                    kps=np.asarray(f.kps, dtype=np.float32),
                    landmark_106=lm106,
                    embedding=emb,
                    det_score=float(f.det_score),
                )
            )
        # left-to-right for stable role assignment when auto-detecting
        out.sort(key=lambda d: d.center[0])
        return out


@lru_cache(maxsize=1)
def get_detector() -> FaceDetector:
    return FaceDetector()


def load_bgr(path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return img


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float32).ravel()
    b = b.astype(np.float32).ravel()
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
