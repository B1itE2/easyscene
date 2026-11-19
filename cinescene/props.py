"""Small props ("details" in the scene spec): a curated CC0 library + placement.

The spec lists details as ``{"item": "rocking_chair", "place": "porch"}``. Each
style publishes named *anchors* (spots where things can stand). Anything that
cannot be placed is reported back, never silently dropped, so the agent can
tell the user exactly what is missing.
"""

import math

import bpy
from mathutils import Vector

from . import assets
from .modeling import vegetation

# item -> Poly Haven model id, optional size cap (m), how many fit on one anchor
LIBRARY = {
    "rocking_chair": {"id": "Rockingchair_01", "zh": "摇椅"},
    "bench":         {"id": "painted_wooden_bench", "zh": "木长椅"},
    "barrel":        {"id": "wine_barrel_01", "zh": "木桶"},
    "crate":         {"id": "wooden_crate_01", "zh": "木箱"},
    "bucket":        {"id": "wooden_bucket_01", "zh": "木水桶"},
    "axe":           {"id": "wooden_axe", "zh": "斧头"},
    "lantern":       {"id": "wooden_lantern_01", "zh": "提灯", "light": (2200, 8.0, 0.35)},
    "oil_lamp":      {"id": "vintage_oil_lamp", "zh": "油灯", "light": (2100, 5.0, 0.45)},
    "basket":        {"id": "wicker_basket_01", "zh": "藤编篮"},
    "boots":         {"id": "rubber_boots", "zh": "雨靴"},
    "watering_can":  {"id": "watering_can_metal_01", "zh": "浇水壶"},
    "flowers":       {"id": "flower_gazania", "zh": "花丛", "max_size": 0.6},
    "vase":          {"id": "ceramic_vase_01", "zh": "陶瓷花瓶"},
    "table_set":     {"id": "outdoor_table_chair_set_01", "zh": "户外桌椅"},
}


def items():
    return sorted(LIBRARY)


def _load(item):
    spec = LIBRARY[item]
    objs = vegetation.load_model(spec["id"], f"prop:{item}", max_objects=1,
                                 max_size=spec.get("max_size"), join=True)
    return objs[0] if objs else None


def place_details(details, anchors: dict, collection=None):
    """details: [{"item", "place"}]; anchors: place -> [(x, y, z, yaw), ...].

    Returns a report: {"placed": [...], "skipped": [{"item", "place", "reason"}]}.
    Several props on the same anchor are spread out sideways.
    """
    report = {"placed": [], "skipped": []}
    used = {}
    col = collection or bpy.context.scene.collection
    for d in details:
        item, place = d.get("item"), d.get("place", "auto")
        if item not in LIBRARY:
            report["skipped"].append({"item": item, "place": place,
                                      "reason": f"not in the props library (available: {', '.join(items())})"})
            continue
        if place == "auto":
            place = next(iter(anchors), None)
        spots = anchors.get(place) or []
        if not spots:
            report["skipped"].append({"item": item, "place": place,
                                      "reason": f"place not available in this style (available: {', '.join(anchors) or '-'})"})
            continue
        k = used.get(place, 0)
        used[place] = k + 1
        x, y, z, yaw = spots[k % len(spots)]
        if k >= len(spots):                       # more props than spots: shift sideways
            off = 0.7 * (k // len(spots))
            x += math.cos(yaw) * off
            y += math.sin(yaw) * off
        obj = _load(item)
        if obj is None:
            report["skipped"].append({"item": item, "place": place,
                                      "reason": "model download failed (offline?)"})
            continue
        obj.name = f"Prop_{item}"
        obj.location = (x, y, z)
        obj.rotation_euler = (0, 0, yaw)
        col.objects.link(obj)
        lt = LIBRARY[item].get("light")
        if lt:
            from . import core
            L = bpy.data.lights.new(f"PropLight_{item}", "POINT")
            L.color = core.kelvin_rgb(lt[0])
            L.energy = lt[1]
            L.shadow_soft_size = 0.05
            lo = bpy.data.objects.new(f"PropLight_{item}", L)
            lo.location = (x, y, z + lt[2])
            col.objects.link(lo)
        report["placed"].append({"item": item, "place": place, "at": [round(x, 2), round(y, 2), round(z, 2)]})
    return report
