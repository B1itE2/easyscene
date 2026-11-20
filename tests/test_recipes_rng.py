import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from easyscene import recipes, rng  # noqa: E402


class TestResolve(unittest.TestCase):
    def test_plain_passthrough(self):
        node = {"a": 1, "b": "x", "c": [1, 2, {"d": True}], "e": None}
        self.assertEqual(recipes.resolve(node, random.Random(0)), node)

    def test_between_and_int_between(self):
        r = random.Random(1)
        for _ in range(200):
            v = recipes.resolve({"between": [2.0, 3.0]}, r)
            self.assertTrue(2.0 <= v <= 3.0)
            i = recipes.resolve({"int_between": [1, 4]}, r)
            self.assertIsInstance(i, int)
            self.assertIn(i, (1, 2, 3, 4))

    def test_choice_and_nested(self):
        r = random.Random(2)
        for _ in range(100):
            self.assertIn(recipes.resolve({"choice": ["a", "b"]}, r), ("a", "b"))
            v = recipes.resolve({"choice": [{"between": [-2, -1]}, {"choice": [10, 20]}]}, r)
            self.assertTrue(-2 <= v <= -1 or v in (10, 20))

    def test_same_seed_identical(self):
        rec = recipes.load("coastal_lighthouse")
        a = recipes.resolve(rec, rng.stream(5, "recipe"))
        b = recipes.resolve(rec, rng.stream(5, "recipe"))
        self.assertEqual(a, b)
        self.assertNotIn("between", json.dumps(a))

    def test_different_seeds_differ(self):
        rec = recipes.load("coastal_lighthouse")
        a = recipes.resolve(rec, rng.stream(1, "recipe"))
        b = recipes.resolve(rec, rng.stream(2, "recipe"))
        self.assertNotEqual(a, b)

    def test_recipe_files_structure(self):
        files = sorted(recipes.RECIPE_DIR.glob("*.json"))
        self.assertTrue(files)
        for p in files:
            with self.subTest(p.name):
                r = json.loads(p.read_text(encoding="utf-8"))
                for k in ("id", "title", "supports", "rubric", "checks", "assets"):
                    self.assertIn(k, r)
                self.assertEqual(r["id"], p.stem)
                self.assertTrue(r["rubric"])
                for item in r["rubric"]:
                    self.assertGreater(item["weight"], 0)


class TestRng(unittest.TestCase):
    def test_stream_reproducible(self):
        s1, s2 = rng.stream(42, "trees"), rng.stream(42, "trees")
        self.assertEqual([s1.random() for _ in range(5)], [s2.random() for _ in range(5)])

    def test_stream_independent(self):
        a = [rng.stream(42, "trees").random() for _ in range(3)]
        b = [rng.stream(42, "rocks").random() for _ in range(3)]
        c = [rng.stream(43, "trees").random() for _ in range(3)]
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)

    def _pts(self, seed=3, **kw):
        return rng.poisson_disk(rng.stream(seed, "pd"), 40.0, 20.0, 2.0, origin=(5.0, -3.0), **kw)

    def test_poisson_min_distance_and_bounds(self):
        pts = self._pts()
        self.assertGreater(len(pts), 20)
        for x, y in pts:
            self.assertTrue(-15.0 <= x < 25.0 and -13.0 <= y < 7.0)
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                d2 = (pts[i][0] - pts[j][0]) ** 2 + (pts[i][1] - pts[j][1]) ** 2
                self.assertGreaterEqual(d2, 4.0 - 1e-9)

    def test_poisson_deterministic(self):
        self.assertEqual(self._pts(), self._pts())
        self.assertNotEqual(self._pts(3), self._pts(4))

    def test_poisson_accept(self):
        allp = self._pts()
        right = self._pts(accept=lambda x, y: x > 5.0)
        self.assertTrue(right)
        self.assertTrue(all(x > 5.0 for x, _ in right))
        self.assertEqual(right, [p for p in allp if p[0] > 5.0])


if __name__ == "__main__":
    unittest.main()
