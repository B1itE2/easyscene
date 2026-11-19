import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from cinescene import checks  # noqa: E402

LIMITS = {"mean_luma": [0.15, 0.6], "clipped_highlights_max": 0.02,
          "crushed_shadows_max": 0.06, "subject_area": [0.015, 0.4]}


class TestHull(unittest.TestCase):
    def test_unit_square(self):
        pts = [(0, 0), (1, 0), (1, 1), (0, 1), (0.5, 0.5)]
        self.assertAlmostEqual(checks._hull_area(pts), 1.0)

    def test_triangle(self):
        self.assertAlmostEqual(checks._hull_area([(0, 0), (1, 0), (0, 1)]), 0.5)

    def test_degenerate(self):
        self.assertEqual(checks._hull_area([(0, 0), (1, 1)]), 0.0)
        self.assertEqual(checks._hull_area([(0, 0), (0, 0), (0, 0)]), 0.0)
        self.assertAlmostEqual(checks._hull_area([(0, 0), (1, 1), (2, 2)]), 0.0)


class TestRenderChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def png(self, arr):
        path = os.path.join(self.tmp.name, f"img{id(arr)}.png")
        a = np.asarray(arr, dtype=np.uint8)
        if a.ndim == 2:
            a = np.stack([a] * 3, axis=-1)
        Image.fromarray(a, "RGB").save(path)
        return path

    def run_checks(self, arr, **kw):
        return {c["id"]: c for c in checks.render_checks(self.png(arr), LIMITS, **kw)}

    @staticmethod
    def gradient(lo, hi):
        return np.tile(np.linspace(lo, hi, 64).astype(np.uint8), (32, 1))

    def test_load_luma(self):
        y = checks.load_luma(self.png(np.full((4, 4, 3), [255, 0, 0])))
        self.assertEqual(y.shape, (4, 4))
        self.assertAlmostEqual(float(y.mean()), 0.2126, places=4)

    def test_mid_grey_gradient_passes(self):
        c = self.run_checks(self.gradient(40, 180))
        for k in ("exposure_mean", "clipped_highlights", "crushed_shadows", "tonal_range"):
            self.assertTrue(c[k]["ok"], c[k])
            self.assertEqual(c[k]["hint"], "")

    def test_near_black_fails(self):
        c = self.run_checks(np.full((32, 32), 2))
        self.assertFalse(c["exposure_mean"]["ok"])
        self.assertFalse(c["crushed_shadows"]["ok"])
        self.assertTrue(c["exposure_mean"]["hint"])

    def test_white_fails_clipping(self):
        c = self.run_checks(np.full((32, 32), 255))
        self.assertFalse(c["clipped_highlights"]["ok"])
        self.assertFalse(c["exposure_mean"]["ok"])

    def test_flat_fails_tonal_range(self):
        c = self.run_checks(np.full((32, 32), 100))
        self.assertTrue(c["exposure_mean"]["ok"])
        self.assertFalse(c["tonal_range"]["ok"])

    def test_subject_area(self):
        img = self.gradient(40, 180)
        self.assertNotIn("subject_area", self.run_checks(img))
        self.assertTrue(self.run_checks(img, subject_area=0.1)["subject_area"]["ok"])
        self.assertFalse(self.run_checks(img, subject_area=0.005)["subject_area"]["ok"])
        self.assertFalse(self.run_checks(img, subject_area=0.6)["subject_area"]["ok"])


if __name__ == "__main__":
    unittest.main()
