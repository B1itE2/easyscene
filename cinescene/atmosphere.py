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
    # high cloud bank (used by the cloud-descent move): gaussian layer. With
    # center_xy/radius_m it is a *local* bank over the opening shot only, so it
    # does not shade the low sun that lights the subject.
    cl = fog["cloud_layer"]
    g = nb.math("DIVIDE", nb.math("SUBTRACT", z, cl["center_m"]), cl["thickness_m"])
    cloud = nb.math("MULTIPLY", cl["density"],
                    nb.math("EXPONENT", nb.math("MULTIPLY", nb.math("MULTIPLY", g, g), -1.0)))
    if cl.get("radius_m"):
        x, y, _ = nb.sep(p)
        cx, cy = cl["center_xy"]
        dx, dy = nb.math("SUBTRACT", x, cx), nb.math("SUBTRACT", y, cy)
        rr = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", dx, dx), nb.math("MULTIPLY", dy, dy)))
        wob = nb.math("MULTIPLY", nb.noise(p, scale=0.05, detail=2.0), cl["radius_m"] * 0.5)
        cloud = nb.math("MULTIPLY", cloud,
                        nb.maprange(nb.math("ADD", rr, wob), cl["radius_m"] * 1.2,
                                    cl["radius_m"] * 0.5, interp="SMOOTHSTEP"))
    # breakup: slow drifting 4D noise so fog has banks and holes, not a flat wall
    n = nb.noise(p, scale=1.0 / fog["breakup_scale_m"], detail=3.0, rough=0.5,
                 dims="4D", w=nb.math("MULTIPLY", t, 0.03))
    amt = fog["breakup_amount"]
    breakup = nb.maprange(n, 0.3, 0.7, 1.0 - amt, 1.0 + amt)
    dens = nb.math("MAXIMUM", nb.math("MULTIPLY", ground, breakup), 0.0)
    # fade out over the outer 30% of the box: a hard box face lit from behind
    # (sun near the horizon) shows up as a bright rectangle
    x, y, _ = nb.sep(p)
    rxy = nb.math("MAXIMUM", nb.math("ABSOLUTE", x), nb.math("ABSOLUTE", y))
    dens = nb.math("MULTIPLY", dens, nb.maprange(rxy, h, h * 0.7, interp="SMOOTHSTEP"))
    dens = nb.math("MULTIPLY", dens, nb.maprange(z, top, top * 0.75, interp="SMOOTHSTEP"))
    vol = nb.new("ShaderNodeVolumePrincipled", inputs={
        "Color": tuple(c * k for c, k in zip(fog["color"], tint)),
        "Anisotropy": fog["anisotropy"]})
    nb.set(vol, "Density", dens)
    # the cloud bank is its own shader: whiter and nearly isotropic, so it reads as
    # bright cloud from inside instead of the dark grey that strong forward scattering gives
    cvol = nb.new("ShaderNodeVolumePrincipled", inputs={"Color": (0.93, 0.95, 0.97),
                                                        "Anisotropy": 0.15})
    nb.set(cvol, "Density", nb.math("MAXIMUM", nb.math("MULTIPLY", cloud, breakup), 0.0))
    add = nb.new("ShaderNodeAddShader")
    nb.links.new(vol.outputs[0], add.inputs[0])
    nb.links.new(cvol.outputs[0], add.inputs[1])
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(add.outputs[0], nb.i(out, "Volume"))
    obj.data.materials.append(mat)
    return obj


def PLUME_WIDTH(z):
    """Gaussian radius of the plume at height z (metres)."""
    return 0.28 + 0.16 * z


def cloud_bank(center_xy, center_z, thickness, radius, density, fog: dict):
    """A local cloud bank as its *own* tight volume box (for the cloud-descent opening).

    Why separate from the fog box: Cycles estimates volume density bounds per
    object; inside a 250 m fog box a 15 m thin layer was under-sampled and
    simply did not render. The box sits *above* the fog box (no overlap, so no
    seams) and does not cast shadows, so it glows sun-lit white from inside
    instead of going dark, and never darkens the scene below.
    Returns (box object, bottom z) - the fog box must end at that bottom.
    """
    cx, cy = center_xy
    z0, z1 = center_z - 2.2 * thickness, center_z + 2.2 * thickness
    r = radius * 1.3
    obj = _box("CloudBank", cx - r, cx + r, cy - r, cy + r, z0, z1)
    mat, nb = new_material("CloudVolume")
    p = nb.coord("Object")
    x, y, z = nb.sep(p)
    t = _time_node(nb)
    g = nb.math("DIVIDE", nb.math("SUBTRACT", z, center_z), thickness)
    layer = nb.math("EXPONENT", nb.math("MULTIPLY", nb.math("MULTIPLY", g, g), -1.0))
    dx, dy = nb.math("SUBTRACT", x, cx), nb.math("SUBTRACT", y, cy)
    rr = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", dx, dx), nb.math("MULTIPLY", dy, dy)))
    wob = nb.math("MULTIPLY", nb.noise(p, scale=0.05, detail=2.0), radius * 0.5)
    edge = nb.maprange(nb.math("ADD", rr, wob), radius * 0.5, radius * 1.2, 1.0, 0.0)
    puff = nb.maprange(nb.noise(p, scale=1.0 / 14.0, detail=4.0, rough=0.55, dims="4D",
                                w=nb.math("MULTIPLY", t, 0.04)), 0.35, 0.7, 0.25, 1.4)
    # fade to zero before the box faces so they never show
    walls = None
    for coord, lo, hi in ((x, cx - r, cx + r), (y, cy - r, cy + r), (z, z0, z1)):
        dmin = nb.math("MINIMUM", nb.math("SUBTRACT", coord, lo), nb.math("SUBTRACT", hi, coord))
        f = nb.maprange(dmin, 0.0, 3.0)
        walls = f if walls is None else nb.math("MULTIPLY", walls, f)
    dens = nb.math("MULTIPLY", nb.math("MULTIPLY", layer, edge),
                   nb.math("MULTIPLY", nb.math("MULTIPLY", puff, walls), density))
    vol = nb.new("ShaderNodeVolumePrincipled", inputs={"Color": (0.93, 0.95, 0.97),
                                                       "Anisotropy": 0.2})
    nb.set(vol, "Density", dens)
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(vol.outputs[0], nb.i(out, "Volume"))
    obj.data.materials.append(mat)
    obj.visible_shadow = False
    return obj, z0


def smoke_bounds(top_pos, smoke: dict):
    """World-space XY rectangle (x0, x1, y0, y1) of the smoke domain.

    The builder keeps tree crowns out of this area so the plume is seen against
    open sky / distant fog, not lost inside a crown.
    """
    H = smoke["height_m"]
    wx, wy = smoke["wind"]
    dx, dy = wx * 0.25 * H ** 1.3, wy * 0.25 * H ** 1.3
    pad = 2.2 * PLUME_WIDTH(H) + 0.6 * H          # plume width + room for the warp meander
    return (top_pos[0] + min(0, dx) - pad, top_pos[0] + max(0, dx) + pad,
            top_pos[1] + min(0, dy) - pad, top_pos[1] + max(0, dy) + pad)


def chimney_smoke(fog_obj, top_pos, smoke: dict, seed: int):
    """Soft rising plume above ``top_pos`` bending with the wind.

    Added *into the fog material* instead of a separate box: two overlapping
    volume objects made visible straight seams at the box faces (Cycles'
    step sampling restarts at every volume boundary).
    """
    H = smoke["height_m"]
    wx, wy = smoke["wind"]
    x0, x1, y0, y1 = smoke_bounds((0, 0, 0), smoke)
    mat = fog_obj.data.materials[0]
    nb = NB(mat.node_tree, clear=False)
    p = nb.vmath("SUBTRACT", nb.coord("Object"), tuple(top_pos))   # plume-local coords
    x, y, z = nb.sep(p)
    t = mat.node_tree.nodes["cinescene_time"].outputs[0]
    rise = nb.math("MULTIPLY", t, -smoke["rise_speed"])
    off = (seed % 97, seed % 89, seed % 83)
    # domain warp: a slow 3D noise pushes the plume sideways, more the higher it gets,
    # so it curls and meanders instead of standing like a straight light beam
    wq = nb.mapping(nb.comb(x, y, nb.math("ADD", z, rise)), scale=(0.35, 0.35, 0.35), loc=off)
    warp = nb.noise(wq, scale=1.0, detail=2.0, dims="4D", w=nb.math("MULTIPLY", t, 0.05),
                    out="Color")
    wx_, wy_, _ = nb.sep(warp)
    amp = nb.math("MULTIPLY", nb.math("MAXIMUM", z, 0.0), 0.4)
    bend = nb.math("POWER", nb.math("MAXIMUM", z, 0.0), 1.3)
    qx = nb.math("SUBTRACT", nb.math("SUBTRACT", x, nb.math("MULTIPLY", bend, wx * 0.25)),
                 nb.math("MULTIPLY", nb.math("SUBTRACT", wx_, 0.5), amp))
    qy = nb.math("SUBTRACT", nb.math("SUBTRACT", y, nb.math("MULTIPLY", bend, wy * 0.25)),
                 nb.math("MULTIPLY", nb.math("SUBTRACT", wy_, 0.5), amp))
    r = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", qx, qx), nb.math("MULTIPLY", qy, qy)))
    w = nb.math("ADD", PLUME_WIDTH(0), nb.math("MULTIPLY", z, PLUME_WIDTH(1) - PLUME_WIDTH(0)))
    rr = nb.math("DIVIDE", r, w)
    radial = nb.math("EXPONENT", nb.math("MULTIPLY", nb.math("MULTIPLY", rr, rr), -1.0))
    # puffs: contrasty noise scrolling upward (noise moves down in object space)
    q = nb.comb(qx, qy, nb.math("ADD", z, rise))
    n = nb.noise(nb.mapping(q, loc=off), scale=1.1, detail=6.0, rough=0.62,
                 dims="4D", w=nb.math("MULTIPLY", t, 0.12))
    shape = nb.math("POWER", nb.maprange(n, 0.38, 0.68), 1.6)
    # dense right at the chimney mouth, thinning out with height
    vert = nb.math("MULTIPLY", nb.maprange(z, 0.0, 0.1),
                   nb.math("EXPONENT", nb.math("DIVIDE", z, -H * 0.22)))
    core_ = nb.math("ADD", shape, nb.math("MULTIPLY", 0.8, nb.maprange(z, 1.5, 0.0)))  # solid start
    # fade to zero 1.5 m before every wall and the lid: the box must never show
    walls = None
    for coord, lo, hi in ((x, x0, x1), (y, y0, y1), (z, -10.0, H)):
        dmin = nb.math("MINIMUM", nb.math("SUBTRACT", coord, lo), nb.math("SUBTRACT", hi, coord))
        f = nb.maprange(dmin, 0.0, 1.5)
        walls = f if walls is None else nb.math("MULTIPLY", walls, f)
    dens = nb.math("MULTIPLY", nb.math("MULTIPLY", radial, core_),
                   nb.math("MULTIPLY", nb.math("MULTIPLY", vert, smoke["density"]), walls))
    # low anisotropy: a forward-scattering plume glows like a searchlight in backlight
    svol = nb.new("ShaderNodeVolumePrincipled", inputs={"Color": (0.55, 0.57, 0.6),
                                                        "Absorption Color": (0.25, 0.25, 0.27),
                                                        "Anisotropy": 0.05})
    nb.set(svol, "Density", dens)
    out = [n for n in nb.nodes if n.bl_idname == "ShaderNodeOutputMaterial"][0]
    prev = out.inputs["Volume"].links[0].from_socket
    add = nb.new("ShaderNodeAddShader")
    nb.links.new(prev, add.inputs[0])
    nb.links.new(svol.outputs[0], add.inputs[1])
    nb.links.new(add.outputs[0], out.inputs["Volume"])
    return fog_obj


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
