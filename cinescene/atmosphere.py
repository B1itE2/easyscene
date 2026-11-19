"""Atmosphere: layered height fog and chimney smoke, both as cheap shader volumes.

No simulations: everything is an analytic density field (exponential height
falloff + noise breakup), so it is deterministic, needs no bake, and its
cost is controlled by the Cycles volume step rate of the quality preset.
A shared "time" Value node drives drift so animation just keys one number.
"""

import bpy

from .nodes import NB, new_material


def _box(name, xmin, xmax, ymin, ymax, zmin, zmax, origin=(0, 0, 0)):
    """Axis-aligned box mesh object, vertices in world units relative to origin."""
    ox, oy, oz = origin
    v = [(x - ox, y - oy, z - oz) for z in (zmin, zmax) for y in (ymin, ymax) for x in (xmin, xmax)]
    # outward-facing winding: Cycles needs correct normals to know the camera is inside
    f = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(v, [], f)
    obj = bpy.data.objects.new(name, me)
    obj.location = origin
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _time_node(nb):
    t = nb.new("ShaderNodeValue")
    t.name = t.label = "cinescene_time"
    t.outputs[0].default_value = 0.0
    return t.outputs[0]


def height_fog(extent, top, fog: dict, density: float, tint=(1, 1, 1)):
    """Fog domain box covering the whole set; object coords == world coords.

    A box (not a world volume) because it renders ~5x faster in Cycles: the
    ray march stops at the box instead of running to the far clip.
    """
    h = extent / 2
    obj = _box("Fog", -h, h, -h, h, -6.0, top)
    mat, nb = new_material("FogVolume")
    p = nb.coord("Object")
    _, _, z = nb.sep(p)
    t = _time_node(nb)
    # ground fog: d0 * exp(-z/H)
    ground = nb.math("MULTIPLY", density,
                     nb.math("EXPONENT", nb.math("DIVIDE", nb.math("MAXIMUM", z, 0.0),
                                                 -fog["height_falloff_m"])))
    # high cloud bank (used by the cloud-descent move): gaussian layer
    cl = fog["cloud_layer"]
    g = nb.math("DIVIDE", nb.math("SUBTRACT", z, cl["center_m"]), cl["thickness_m"])
    cloud = nb.math("MULTIPLY", cl["density"],
                    nb.math("EXPONENT", nb.math("MULTIPLY", nb.math("MULTIPLY", g, g), -1.0)))
    # breakup: slow drifting 4D noise so fog has banks and holes, not a flat wall
    n = nb.noise(p, scale=1.0 / fog["breakup_scale_m"], detail=3.0, rough=0.5,
                 dims="4D", w=nb.math("MULTIPLY", t, 0.03))
    amt = fog["breakup_amount"]
    breakup = nb.maprange(n, 0.3, 0.7, 1.0 - amt, 1.0 + amt)
    dens = nb.math("MULTIPLY", nb.math("ADD", ground, cloud), breakup)
    dens = nb.math("MAXIMUM", dens, 0.0)
    vol = nb.new("ShaderNodeVolumePrincipled", inputs={
        "Color": tuple(c * k for c, k in zip(fog["color"], tint)),
        "Anisotropy": fog["anisotropy"]})
    nb.set(vol, "Density", dens)
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(vol.outputs[0], nb.i(out, "Volume"))
    obj.data.materials.append(mat)
    return obj


def smoke_bounds(top_pos, smoke: dict):
    """World-space XY rectangle (x0, x1, y0, y1) of the smoke domain.

    The builder keeps tree crowns out of this area so the plume is seen against
    open sky / distant fog, not lost inside a crown.
    """
    H = smoke["height_m"]
    wx, wy = smoke["wind"]
    dx, dy = wx * 0.25 * H ** 1.3, wy * 0.25 * H ** 1.3
    pad = 0.6 + 0.2 * H
    return (top_pos[0] + min(0, dx) - pad, top_pos[0] + max(0, dx) + pad,
            top_pos[1] + min(0, dy) - pad, top_pos[1] + max(0, dy) + pad)


def chimney_smoke(top_pos, smoke: dict, seed: int):
    """Soft rising plume above ``top_pos`` bending with the wind."""
    H = smoke["height_m"]
    wx, wy = smoke["wind"]
    # tight domain that follows the wind bend: small domains get fine ray-march steps
    x0, x1, y0, y1 = smoke_bounds((0, 0, 0), smoke)
    obj = _box("Smoke", x0, x1, y0, y1, 0.0, H, origin=(0, 0, 0))
    obj.location = top_pos
    mat, nb = new_material("SmokeVolume")
    p = nb.coord("Object")
    x, y, z = nb.sep(p)
    t = _time_node(nb)
    bend = nb.math("POWER", nb.math("MAXIMUM", z, 0.0), 1.3)
    qx = nb.math("SUBTRACT", x, nb.math("MULTIPLY", bend, wx * 0.25))
    qy = nb.math("SUBTRACT", y, nb.math("MULTIPLY", bend, wy * 0.25))
    r = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", qx, qx), nb.math("MULTIPLY", qy, qy)))
    w = nb.math("ADD", 0.35, nb.math("MULTIPLY", z, 0.22))
    rr = nb.math("DIVIDE", r, w)
    radial = nb.math("EXPONENT", nb.math("MULTIPLY", nb.math("MULTIPLY", rr, rr), -1.0))
    # noise scrolls downward in object space = smoke rises
    rise = nb.math("MULTIPLY", t, -smoke["rise_speed"])
    q = nb.comb(qx, qy, nb.math("ADD", z, rise))
    n = nb.noise(nb.mapping(q, loc=(seed % 97, seed % 89, 0)), scale=1.3, detail=5.0,
                 rough=0.6, dims="4D", w=nb.math("MULTIPLY", t, 0.15))
    shape = nb.maprange(n, 0.3, 0.62)
    vert = nb.math("MULTIPLY", nb.maprange(z, 0.0, 0.15),
                   nb.math("EXPONENT", nb.math("DIVIDE", z, -H * 0.3)))
    dens = nb.math("MULTIPLY", nb.math("MULTIPLY", radial, shape),
                   nb.math("MULTIPLY", vert, smoke["density"]))
    vol = nb.new("ShaderNodeVolumePrincipled", inputs={"Color": (0.92, 0.93, 0.95),
                                                        "Anisotropy": 0.25})
    nb.set(vol, "Density", dens)
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(vol.outputs[0], nb.i(out, "Volume"))
    obj.data.materials.append(mat)
    try:
        mat.cycles.volume_step_rate = 0.2     # finer steps than the fog: the plume is thin
    except AttributeError:
        pass
    return obj


def _time_owners():
    return list(bpy.data.materials) + list(bpy.data.worlds)


def key_time(fps: int, frame_start: int, frame_end: int):
    """Key every 'cinescene_time' node linearly in seconds over the shot."""
    for mat in _time_owners():
        if not mat.node_tree:
            continue
        node = mat.node_tree.nodes.get("cinescene_time")
        if node is None:
            continue
        sock = node.outputs[0]
        for f in (frame_start, frame_end):
            sock.default_value = f / fps
            sock.keyframe_insert("default_value", frame=f)
        anim = mat.node_tree.animation_data
        if anim and anim.action:
            for fc in _fcurves(anim.action):
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"


def _fcurves(action):
    """F-curves of an action across Blender 4.x (flat) and 5.x (layered) APIs."""
    if hasattr(action, "fcurves") and len(getattr(action, "fcurves", [])):
        return list(action.fcurves)
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out += list(bag.fcurves)
    return out


def set_time(seconds: float):
    """For stills: freeze every drift at a given time."""
    for mat in _time_owners():
        if mat.node_tree and (n := mat.node_tree.nodes.get("cinescene_time")):
            n.outputs[0].default_value = seconds
