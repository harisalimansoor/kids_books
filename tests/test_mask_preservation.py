"""Validate that pixels outside the face/neck mask stay identical to the template."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.blend import seamless_blend
from pipeline.validate import MaskPreservationError, assert_mask_preserved, combined_mask


def _make_template(h=200, w=300) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic template with a unique off-mask pattern (countable 'objects')."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            img[y, x] = [(x * 3) % 256, (y * 5) % 256, (x + y) % 256]
    cv2.circle(img, (40, 160), 12, (0, 0, 255), -1)
    cv2.circle(img, (80, 160), 12, (0, 0, 255), -1)
    cv2.circle(img, (120, 160), 12, (0, 0, 255), -1)
    cv2.ellipse(img, (200, 80), (35, 45), 0, 0, 360, (180, 160, 140), -1)

    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.ellipse(mask, (200, 80), (40, 50), 0, 0, 360, 255, -1)
    return img, mask


class TestMaskPreservation(unittest.TestCase):
    def test_seamless_blend_preserves_off_mask_pixels(self):
        template, mask = _make_template()
        warped = np.full_like(template, 40)
        warped[:] = (0, 255, 0)

        out = seamless_blend(warped, template, mask)
        stats = assert_mask_preserved(
            template, out, mask, template_id="synthetic", tolerance=0
        )
        self.assertTrue(stats["ok"])
        self.assertEqual(stats["max_diff"], 0)
        self.assertTrue(np.array_equal(out[160, 40], template[160, 40]))
        self.assertTrue(np.array_equal(out[160, 80], template[160, 80]))
        self.assertTrue(np.array_equal(out[160, 120], template[160, 120]))

    def test_assert_fails_if_off_mask_changed(self):
        template, mask = _make_template()
        bad = template.copy()
        bad[160, 40] = (255, 255, 255)
        with self.assertRaises(MaskPreservationError):
            assert_mask_preserved(template, bad, mask, template_id="broken")

    def test_combined_mask_union(self):
        a = np.zeros((10, 10), dtype=np.uint8)
        b = np.zeros((10, 10), dtype=np.uint8)
        a[2:5, 2:5] = 255
        b[4:7, 4:7] = 255
        u = combined_mask([a, b])
        self.assertEqual(u[3, 3], 255)
        self.assertEqual(u[5, 5], 255)
        self.assertEqual(u[0, 0], 0)



class TestIntegration(unittest.TestCase):
    def test_real_template_roundtrip_if_cache_exists(self):
        from pipeline.cache import DEFAULT_CACHE_ROOT, is_cache_valid
        from pipeline.generate import generate_worksheet

        tid = "grade_1/addition/add_apples_3_2_user_adult"
        if not is_cache_valid(tid, DEFAULT_CACHE_ROOT):
            self.skipTest("pipeline_cache not built — run scripts/preprocess_templates.py")

        candidates = list((ROOT / "new_pipeline").rglob("*child*.jpg")) + list(
            (ROOT / "new_pipeline").rglob("*face*.png")
        )
        photo = None
        for c in candidates[:20]:
            if c.stat().st_size > 1000:
                photo = c
                break
        if photo is None:
            self.skipTest("No sample user photo found for integration test")

        out = ROOT / "pipeline_cache" / "_test_out" / "apples_swap.png"
        generate_worksheet(tid, {"child": photo}, out, validate=True)
        self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
