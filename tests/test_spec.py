import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cinescene import spec  # noqa: E402
from cinescene.spec import SpecError  # noqa: E402


def base(**kw):
    d = {"version": 1, "style": "foggy_forest_cabin"}
    d.update(kw)
    return d


class TestSpec(unittest.TestCase):
    def assertSpecError(self, raw, *needles):
        with self.assertRaises(SpecError) as cm:
            spec.validate(raw)
        msg = str(cm.exception)
        for n in needles:
            self.assertIn(n, msg)
        return msg

    def test_examples_validate(self):
        files = sorted((ROOT / "examples").glob("*.json"))
        self.assertTrue(files)
        for p in files:
            with self.subTest(p.name):
                out = spec.load(p)
                self.assertEqual(out["version"], 1)

    def test_defaults_filled(self):
        out = spec.validate(base())
        self.assertEqual(out["seed"], 1)
        self.assertEqual(out["quality"], "preview")
        self.assertEqual(out["camera"]["aspect"], "16:9")
        self.assertEqual(out["camera"]["lens_mm"], 35)
        self.assertEqual(out["name"], "scene")

    def test_auto_resolved_from_recipe(self):
        out = spec.validate({"version": 1, "style": "coastal_lighthouse",
                             "time_of_day": "auto", "motion": {"preset": "auto"}})
        self.assertEqual(out["time_of_day"], "dusk")
        self.assertEqual(out["weather"], "haze")
        self.assertEqual(out["subject"]["type"], "lighthouse")
        self.assertEqual(out["motion"]["preset"], "orbit")
        out = spec.validate(base())
        self.assertEqual(out["time_of_day"], "morning")
        self.assertEqual(out["subject"]["type"], "log_cabin")

    def test_unknown_field(self):
        self.assertSpecError(base(colour="red"), "spec.colour", "unknown field")
        self.assertSpecError(base(camera={"zoom": 2}), "spec.camera.zoom")

    def test_wrong_type(self):
        self.assertSpecError(base(seed="7"), "spec.seed", "expected integer")
        self.assertSpecError(base(camera={"lens_mm": "35"}), "spec.camera.lens_mm")

    def test_bool_rejected_for_integer(self):
        self.assertSpecError(base(seed=True), "spec.seed", "expected integer")

    def test_lens_out_of_range(self):
        self.assertSpecError(base(camera={"lens_mm": 10}), "spec.camera.lens_mm", "minimum")
        self.assertSpecError(base(camera={"lens_mm": 200}), "spec.camera.lens_mm", "maximum")

    def test_bad_enum(self):
        self.assertSpecError(base(quality="ultra"), "spec.quality")

    def test_name_pattern(self):
        self.assertSpecError(base(name="Bad Name!"), "spec.name", "does not match")

    def test_errors_collected(self):
        msg = self.assertSpecError(base(seed="x", quality="ultra", foo=1),
                                   "spec.seed", "spec.quality", "spec.foo")
        self.assertGreaterEqual(len(msg.splitlines()), 3)

    def test_cross_unsupported_weather(self):
        self.assertSpecError({"version": 1, "style": "coastal_lighthouse", "weather": "dense_fog"},
                             "spec.weather", "not supported")

    def test_cross_unsupported_motion(self):
        self.assertSpecError(base(motion={"preset": "orbit"}), "spec.motion.preset")

    def test_cross_wrong_subject(self):
        self.assertSpecError(base(subject={"type": "lighthouse"}), "spec.subject.type")


if __name__ == "__main__":
    unittest.main()
