"""Style registry. Each style module exposes ``build(spec, R, q, mats, tex, hdri)``.

Adding a style = one recipe JSON + one recipe card + one module here.
Shared pieces (terrain, fog, lighting, camera, motion, scatter) live in the
core library so styles stay short.
"""

import importlib

STYLES = {
    "foggy_forest_cabin": "foggy_forest_cabin",
    "coastal_lighthouse": "coastal_lighthouse",
    "lakeside_dock": "lakeside_dock",
    "greenhouse": "greenhouse",
    "rainforest_waterfall": "rainforest_waterfall",
}


def get(name):
    if name not in STYLES:
        raise KeyError(f"unknown style {name!r}; available: {sorted(STYLES)}")
    return importlib.import_module(f"{__name__}.{STYLES[name]}")
