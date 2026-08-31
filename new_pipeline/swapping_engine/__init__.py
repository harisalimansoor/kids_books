"""
swapping_engine — face swap + AI blend for the Grade 1 workbook pipeline.

All swap/blend code for the new pipeline lives in this package only.
"""

from .personalize import (
    personalize_stem,
    run_child_adult_face_pipeline,
    run_child_only_face_pipeline,
    run_kitchen_face_pipeline,  # alias of run_child_adult_face_pipeline
)

__all__ = [
    "personalize_stem",
    "run_child_adult_face_pipeline",
    "run_child_only_face_pipeline",
    "run_kitchen_face_pipeline",
]
