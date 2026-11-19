"""Style recipes: the machine-readable half of a recipe card.

``recipes/<style>.json`` holds every tuned number for a style; the matching
``.md`` card explains them to humans and AIs. Code reads only the JSON.
"""

import json
from pathlib import Path

RECIPE_DIR = Path(__file__).resolve().parent.parent / "recipes"


def load(style: str) -> dict:
    path = RECIPE_DIR / f"{style}.json"
    if not path.exists():
        raise FileNotFoundError(f"no recipe for style {style!r} ({path})")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(node, rng):
    """Turn variable recipe values into concrete ones, drawn from ``rng``.

    A recipe value may be a plain value, ``{"between": [lo, hi]}`` (uniform
    float), ``{"int_between": [lo, hi]}`` or ``{"choice": [a, b, ...]}``.
    Ranges are the *safe* zone: every combination inside should look good.
    Keys are visited in sorted order so the draw sequence is stable.
    """
    if isinstance(node, dict):
        if set(node) == {"between"}:
            lo, hi = node["between"]
            return lo + (hi - lo) * rng.random()
        if set(node) == {"int_between"}:
            lo, hi = node["int_between"]
            return rng.randint(lo, hi)
        if set(node) == {"choice"}:
            return resolve(rng.choice(node["choice"]), rng)
        return {k: resolve(node[k], rng) for k in sorted(node)}
    if isinstance(node, list):
        return [resolve(v, rng) for v in node]
    return node


def available():
    return sorted(p.stem for p in RECIPE_DIR.glob("*.json"))


_FALLBACK = {"time_of_day": "morning", "weather": "fog"}


def apply_defaults(spec: dict):
    """Replace "auto" values with the style's defaults (recipe ``defaults`` block)."""
    try:
        d = load(spec["style"]).get("defaults", {})
    except FileNotFoundError:
        return spec
    for key in ("time_of_day", "weather"):
        if spec.get(key) == "auto":
            spec[key] = d.get(key, _FALLBACK[key])
    if spec.get("subject", {}).get("type") == "auto":
        spec["subject"]["type"] = d.get("subject", {}).get("type", "log_cabin")
    if spec.get("motion", {}).get("preset") == "auto":
        spec["motion"]["preset"] = d.get("motion", {}).get("preset", "none")
    return spec


def check_spec_against_recipe(spec: dict):
    """Cross-field checks the schema cannot express. Returns a list of errors."""
    try:
        r = load(spec["style"])
    except FileNotFoundError as e:
        return [str(e)]
    errs = []
    sup = r.get("supports", {})
    for key in ("time_of_day", "weather"):
        if key in sup and spec.get(key) not in sup[key]:
            errs.append(f"spec.{key}: {spec.get(key)!r} not supported by style "
                        f"{spec['style']!r} (choose from {sup[key]})")
    st = spec.get("subject", {}).get("type")
    if "subject" in sup and st not in sup["subject"]:
        errs.append(f"spec.subject.type: {st!r} not available in style {spec['style']!r} "
                    f"(choose from {sup['subject']})")
    preset = spec.get("motion", {}).get("preset")
    if "motion" in sup and preset not in sup["motion"]:
        errs.append(f"spec.motion.preset: {preset!r} not implemented yet for this style "
                    f"(choose from {sup['motion']})")
    return errs
