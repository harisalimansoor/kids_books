"""
Deterministic face-swap pipeline for worksheet templates.

Compositing is warp + color match + cv2.seamlessClone only.
No generative image-editing models are used on the pixel path.
"""

from .constants import CACHE_VERSION

__all__ = ["generate_worksheet", "generate_worksheet_batch", "CACHE_VERSION"]


def __getattr__(name: str):
    if name in ("generate_worksheet", "generate_worksheet_batch"):
        from . import generate as _generate

        return getattr(_generate, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
