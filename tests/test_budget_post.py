import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cinescene import budget, post  # noqa: E402


class TestBudget(unittest.TestCase):
    def test_resolution_even_and_aspect(self):
        for aspect, a in budget.ASPECTS.items():
            for q in budget.QUALITY:
                with self.subTest(aspect=aspect, quality=q):
                    w, h = budget.resolution(aspect, q)
                    self.assertIsInstance(w, int)
                    self.assertIsInstance(h, int)
                    self.assertEqual(w % 2, 0)
                    self.assertEqual(h % 2, 0)
                    self.assertAlmostEqual(w / h, a, delta=0.02)
                    self.assertEqual(min(w, h), budget.QUALITY[q]["short_side"])

    def test_memory_grows_with_tris(self):
        f = lambda t: budget.estimate_memory_gb(t, 100, 10**6, 0, 1920, 1080)  # noqa: E731
        self.assertLess(f(10**5), f(10**7))
        self.assertGreater(budget.estimate_memory_gb(0, 0, 0, 0, 0, 0), 0.0)

    def test_quality_keys_match_schema(self):
        schema = json.loads((ROOT / "schema" / "scene_spec.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(budget.QUALITY), set(schema["properties"]["quality"]["enum"]))
        self.assertEqual(set(budget.ASPECTS),
                         set(schema["properties"]["camera"]["properties"]["aspect"]["enum"]))


class TestFilterChain(unittest.TestCase):
    POST = {"contrast": 1.1, "saturation": 1.2, "gamma": 1.0, "shadows_rgb": [-0.03, 0, 0.04],
            "highlights_rgb": [0.07, 0.02, -0.05], "vignette_angle": 0.45, "grain": 4}

    def test_contains_core_filters(self):
        fc = post.filter_chain(self.POST, 7)
        for f in ("colorbalance=", "eq=", "vignette="):
            self.assertIn(f, fc)
        self.assertIn("contrast=1.1", fc)

    def test_noise_seed(self):
        fc = post.filter_chain(self.POST, 12345)
        self.assertIn("noise=", fc)
        self.assertIn("all_seed=12345", fc)
        self.assertIn("all_seed=1", post.filter_chain(self.POST, 2147483648))

    def test_temporal_only_when_animated(self):
        self.assertIn("allf=u:", post.filter_chain(self.POST, 1))
        self.assertNotIn("t+u", post.filter_chain(self.POST, 1))
        self.assertIn("allf=t+u", post.filter_chain(self.POST, 1, animated=True))

    def test_no_grain_no_noise(self):
        p = dict(self.POST, grain=0)
        self.assertNotIn("noise", post.filter_chain(p, 1, animated=True))
        self.assertNotIn("noise", post.filter_chain({}, 1))


if __name__ == "__main__":
    unittest.main()
