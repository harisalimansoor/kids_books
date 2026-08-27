"""Shared constants for the deterministic face-swap pipeline."""

import os

# Bump when mask / landmark / warp logic changes — invalidates stale cache.
CACHE_VERSION = "9"

# Clone mode: "mixed" | "normal" | "multiband"
# MIXED_CLONE often looks less pasted-on against illustrated art.
CLONE_MODE = os.getenv("PIPELINE_CLONE_MODE", "mixed").strip().lower()

# Mask prep for blend
MASK_ERODE_PX = int(os.getenv("PIPELINE_MASK_ERODE", "5"))
MASK_BLUR_PX = float(os.getenv("PIPELINE_MASK_BLUR", "3.0"))

# Piecewise-affine uses a subsample of InsightFace 106-pt landmarks
PWA_LANDMARK_COUNT = int(os.getenv("PIPELINE_PWA_POINTS", "48"))
