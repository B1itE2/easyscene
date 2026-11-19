"""Material library with tuned parameters.

Each material accepts Poly Haven texture maps (``{"diff","rough","nor"}``
paths) and falls back to a procedural version of the same look when the
maps are missing, so a build never fails because of the network.
All parameters here were tuned for AgX + foggy, low-contrast light.
"""

import bpy

from .nodes import NB, new_material

WOOD_GREY = (0.30, 0.25, 0.20)


# ---------------------------------------------------------------- helpers ---
def _image(nb, path, vec, noncolor=False, box=False):
    n = nb.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(path, check_existing=True)
    if noncolor:
        n.image.colorspace_settings.name = "Non-Color"
    if box:
        n.projection = "BOX"
        n.projection_blend = 0.3
    nb.set(n, "Vector", vec)
    return n


def _pbr_maps(nb, maps, vec, box=False, tint=(1, 1, 1), rough_default=0.75,
              rough_mul=1.0, bump=0.6):
    """Colour / roughness / normal sockets from image maps."""
    col = _image(nb, maps["diff"], vec, box=box).outputs["Color"]
    col = nb.mix(1.0, col, tint, "MULTIPLY")
    if "rough" in maps:
        r = _image(nb, maps["rough"], vec, noncolor=True, box=box).outputs["Color"]
        rough = nb.math("MULTIPLY", r, rough_mul, clamp=True)
    else:
        rough = rough_default
    if "nor" in maps and not box:
        nm = nb.new("ShaderNodeNormalMap", inputs={"Strength": 1.0})
        nb.set(nm, "Color", _image(nb, maps["nor"], vec, noncolor=True).outputs["Color"])
        normal = nm.outputs[0]
    else:
        # tangent-space normal maps are wrong under box projection: bump instead
        b = nb.new("ShaderNodeBump", inputs={"Strength": bump, "Distance": 0.02})
        nb.set(b, "Height", nb.math("MULTIPLY", col, 1.0))
        normal = b.outputs[0]
    return col, rough, normal


def _variation(nb, col, vec, scale=0.35, amount=0.18):
    """Large-scale value/hue drift to hide texture tiling."""
    n = nb.noise(vec, scale=scale, detail=2.0)
    f = nb.maprange(n, 0.3, 0.7, 1 - amount, 1 + amount)
    return nb.mix(1.0, col, nb.comb(f, f, nb.math("MULTIPLY", f, 0.97)), "MULTIPLY")


def _moss(nb, col, rough, amount=0.4, scale=1.4, up_only=True):
    """Blend moss onto upward-facing, noisy areas. amount 0..1."""
    world = nb.coord("Object")
    n = nb.noise(world, scale=scale, detail=6.0, rough=0.62)
    mask = nb.maprange(n, 1.0 - amount * 0.75, 1.0 - amount * 0.55 + 0.15, 0.0, 1.0)
    if up_only:
        geo = nb.new("ShaderNodeNewGeometry")
        _, _, nz = nb.sep(nb.o(geo, "Normal"))
        mask = nb.math("MULTIPLY", mask, nb.maprange(nz, 0.15, 0.75))
    tone = nb.noise(world, scale=9.0, detail=3.0)
    moss_col = nb.ramp(tone, [(0.25, (0.035, 0.05, 0.012)), (0.75, (0.10, 0.12, 0.03))])
    return nb.mix(mask, col, moss_col), nb.mixf(mask, rough, 0.9)


def _finish(nb, col, rough, normal=None, extra=None):
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    nb.set(bsdf, "Base Color", col)
    nb.set(bsdf, "Roughness", rough)
    if normal is not None:
        nb.set(bsdf, "Normal", normal)
    for k, v in (extra or {}).items():
        nb.set(bsdf, k, v)
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(bsdf.outputs[0], nb.i(out, "Surface"))
    return bsdf


def _uv(nb, scale=(1, 1, 1)):
    return nb.mapping(nb.coord("UV"), scale=scale)


# ------------------------------------------------------------ procedural ---
def _proc_wood(nb, vec, base=WOOD_GREY):
    """Weathered silver-brown timber with grain along U (x)."""
    warp = nb.noise(vec, scale=3.0, detail=4.0)
    wv = nb.new("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y",
                inputs={"Scale": 18.0, "Distortion": 6.0, "Detail": 3.0})
    nb.set(wv, "Vector", nb.vmath("ADD", vec, nb.comb(warp, warp, 0)))
    grain = nb.math("MULTIPLY", nb.o(wv, "Fac"), nb.noise(vec, scale=25, detail=2))
    col = nb.ramp(grain, [(0.0, tuple(c * 0.55 for c in base)), (0.6, base),
                          (1.0, tuple(min(1, c * 1.35) for c in base))])
    b = nb.new("ShaderNodeBump", inputs={"Strength": 0.35, "Distance": 0.01})
    nb.set(b, "Height", grain)
    return col, nb.maprange(grain, 0, 1, 0.85, 0.6), b.outputs[0]


def _proc_stone(nb, vec):
    vor = nb.new("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE", inputs={"Scale": 3.2})
    nb.set(vor, "Vector", vec)
    edge = nb.maprange(nb.o(vor, "Distance"), 0.0, 0.06)  # mortar gaps
    tone = nb.noise(vec, scale=8.0, detail=5.0)
    col = nb.ramp(tone, [(0.3, (0.13, 0.13, 0.12)), (0.7, (0.26, 0.25, 0.22))])
    col = nb.mix(1.0, col, nb.comb(edge, edge, edge), "MULTIPLY")
    b = nb.new("ShaderNodeBump", inputs={"Strength": 0.8, "Distance": 0.05})
    nb.set(b, "Height", nb.math("ADD", edge, nb.math("MULTIPLY", tone, 0.3)))
    return col, 0.82, b.outputs[0]


def _proc_ground(nb, vec):
    n1 = nb.noise(vec, scale=0.6, detail=6.0)
    n2 = nb.noise(vec, scale=7.0, detail=8.0, rough=0.7)
    col = nb.ramp(n1, [(0.35, (0.05, 0.035, 0.02)), (0.55, (0.09, 0.06, 0.035)),
                       (0.7, (0.06, 0.07, 0.025))])
    col = nb.mix(0.5, col, nb.ramp(n2, [(0.2, (0.03, 0.02, 0.012)),
                                        (0.8, (0.14, 0.09, 0.05))]), "OVERLAY")
    b = nb.new("ShaderNodeBump", inputs={"Strength": 0.5, "Distance": 0.03})
    nb.set(b, "Height", n2)
    return col, 0.8, b.outputs[0]


def _proc_bark(nb, vec):
    stretched = nb.mapping(vec, scale=(1.0, 0.18, 1.0))
    vor = nb.new("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE", inputs={"Scale": 6.0})
    nb.set(vor, "Vector", stretched)
    cracks = nb.maprange(nb.o(vor, "Distance"), 0.0, 0.08)
    tone = nb.noise(vec, scale=4.0, detail=6.0)
    col = nb.ramp(tone, [(0.3, (0.05, 0.035, 0.025)), (0.7, (0.13, 0.09, 0.065))])
    col = nb.mix(1.0, col, nb.comb(cracks, cracks, cracks), "MULTIPLY")
    b = nb.new("ShaderNodeBump", inputs={"Strength": 1.0, "Distance": 0.03})
    nb.set(b, "Height", cracks)
    return col, 0.9, b.outputs[0]


# ------------------------------------------------------------ materials ---
def log_wood(maps, name="Log", tint=(0.85, 0.78, 0.70), moss=0.25):
    mat, nb = new_material(name)
    vec = _uv(nb, scale=(0.6, 0.6, 1))
    if maps:
        col, rough, nor = _pbr_maps(nb, maps, vec, tint=tint, rough_mul=1.1)
    else:
        col, rough, nor = _proc_wood(nb, vec)
    col = _variation(nb, col, nb.coord("Object"), scale=0.8, amount=0.12)
    if moss:
        col, rough = _moss(nb, col, rough, amount=moss, scale=1.6)
    _finish(nb, col, rough, nor)
    return mat


def roof(maps):
    mat, nb = new_material("Roof")
    vec = _uv(nb, scale=(0.45, 0.45, 1))
    if maps:
        col, rough, nor = _pbr_maps(nb, maps, vec, tint=(0.22, 0.21, 0.2))
        hsv = nb.new("ShaderNodeHueSaturation", inputs={"Saturation": 0.55})
        nb.set(hsv, "Color", col)
        col = hsv.outputs[0]
    else:
        col, rough, nor = _proc_wood(nb, vec, base=(0.16, 0.13, 0.11))
    col, rough = _moss(nb, col, rough, amount=0.5, scale=0.9)
    # weathered boards are matte: a glossy roof reads as a white panel from above
    _finish(nb, col, nb.math("MAXIMUM", rough, 0.8), nor, extra={"Specular IOR Level": 0.2})
    return mat


def stone(maps, name="Stone", moss=0.35):
    mat, nb = new_material(name)
    vec = nb.mapping(nb.coord("Object"), scale=(0.6, 0.6, 0.6))
    if maps:
        col, rough, nor = _pbr_maps(nb, maps, vec, box=True, tint=(0.8, 0.8, 0.78), bump=0.8)
    else:
        col, rough, nor = _proc_stone(nb, vec)
    col, rough = _moss(nb, col, rough, amount=moss, scale=2.0)
    _finish(nb, col, rough, nor)
    return mat


def _path_distance(nb, pos, points):
    """Shader-side distance from ``pos`` (xy) to a polyline, min over segments."""
    best = None
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        a = (x0, y0, 0.0)
        ab = (x1 - x0, y1 - y0, 0.0)
        ap = nb.vmath("SUBTRACT", pos, a)
        t = nb.math("DIVIDE", nb.vmath("DOT_PRODUCT", ap, ab, out="Value"),
                    ab[0] ** 2 + ab[1] ** 2, clamp=False)
        t = nb.math("MINIMUM", nb.math("MAXIMUM", t, 0.0), 1.0)
        proj = nb.vmath("SCALE", nb.comb(ab[0], ab[1], 0.0), None)
        sc = proj.node
        nb.set(sc, "Scale", t)
        d = nb.vmath("DISTANCE", ap, proj, out="Value")
        best = d if best is None else nb.math("MINIMUM", best, d)
    return best


def ground(maps_a, maps_b, path=None, maps_path=None, clearing=12.0):
    """Forest floor.

    maps_a: clearing cover (mossy, green); maps_b: needle litter under the trees.
    The two blend by distance from the subject (broken up by noise), then moss
    carpets, dew-wet patches and the trodden footpath (maps_path) go on top.
    """
    mat, nb = new_material("Ground")
    world = nb.coord("Object")
    vec = nb.mapping(world, scale=(0.65, 0.65, 0.65))
    if maps_a:
        col, rough, nor = _pbr_maps(nb, maps_a, vec, box=True, tint=(0.3, 0.4, 0.27), bump=0.6)
        if maps_b:
            vb = nb.mapping(world, scale=(0.6, 0.6, 0.6), rot=(0, 0, 0.7))
            cb, rb, _ = _pbr_maps(nb, maps_b, vb, box=True, tint=(0.7, 0.68, 0.64))
            x, y, _ = nb.sep(world)
            r = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", x, x), nb.math("MULTIPLY", y, y)))
            wob = nb.math("MULTIPLY", nb.noise(world, scale=0.12, detail=3.0), 14.0)
            m = nb.maprange(nb.math("ADD", r, wob), clearing + 2.0, clearing + 12.0)
            col = nb.mix(m, col, cb)
            rough = nb.mixf(m, rough, rb)
    else:
        col, rough, nor = _proc_ground(nb, vec)
    hsv = nb.new("ShaderNodeHueSaturation", inputs={"Saturation": 0.75})   # damp = less vivid
    nb.set(hsv, "Color", col)
    col = _variation(nb, hsv.outputs[0], world, scale=0.05, amount=0.2)
    col, rough = _moss(nb, col, rough, amount=0.5, scale=0.15)     # big moss carpets
    # wet patches: darker and smoother (dew / last night's rain)
    wet = nb.maprange(nb.noise(world, scale=0.15, detail=4.0), 0.58, 0.7)
    col = nb.mix(nb.math("MULTIPLY", wet, 0.35), col, (0.0, 0.0, 0.0))
    rough = nb.math("MAXIMUM", nb.mixf(wet, rough, 0.5), 0.5)
    if path is not None:
        d = _path_distance(nb, world, path.points)
        edge = nb.math("MULTIPLY", nb.noise(world, scale=2.5, detail=3.0), path.width * 0.5)
        m = nb.maprange(nb.math("ADD", d, edge), path.width * 0.45, path.width * 0.95, 1.0, 0.0)
        if maps_path:
            vp = nb.mapping(world, scale=(0.8, 0.8, 0.8))
            mud, mr, _ = _pbr_maps(nb, maps_path, vp, box=True, tint=(0.8, 0.78, 0.75))
        else:
            mud = nb.ramp(nb.noise(world, scale=6.0, detail=5.0),
                          [(0.3, (0.035, 0.026, 0.018)), (0.7, (0.075, 0.058, 0.04))])
            mr = 0.5
        col = nb.mix(m, col, mud)
        rough = nb.mixf(m, rough, nb.math("MULTIPLY", mr, 0.8))     # damp, compacted
    _finish(nb, col, rough, nor, extra={"Specular IOR Level": 0.3})
    return mat


def bark(maps):
    mat, nb = new_material("Bark")
    # trunk UVs run u=along the trunk; bark furrows are vertical in the image: rotate 90°
    vec = nb.mapping(nb.coord("UV"), scale=(1.2, 1.2, 1), rot=(0, 0, 1.5708))
    if maps:
        col, rough, nor = _pbr_maps(nb, maps, vec, tint=(0.7, 0.68, 0.66))
    else:
        col, rough, nor = _proc_bark(nb, vec)
    rnd = nb.o(nb.new("ShaderNodeObjectInfo"), "Random")
    col = nb.mix(1.0, col, nb.comb(*(nb.maprange(rnd, 0, 1, 0.8, 1.15),) * 3), "MULTIPLY")
    col, rough = _moss(nb, col, rough, amount=0.3, scale=3.0, up_only=False)
    _finish(nb, col, rough, nor)
    return mat


def needles():
    """Spruce frond: alpha-cut needle pattern on a UV strip (u across, v along)."""
    mat, nb = new_material("Needles")
    uv = nb.coord("UV")
    u, v, _ = nb.sep(uv)
    x = nb.math("ABSOLUTE", nb.math("MULTIPLY", nb.math("SUBTRACT", u, 0.5), 2.0))
    # ragged outline: width profile (fat middle, thin tip) jittered by noise
    prof = nb.math("POWER", nb.math("SINE", nb.math("MULTIPLY",
                   nb.maprange(v, 0.0, 1.0, 0.25, 1.0), 3.1416)), 0.5)
    rag = nb.maprange(nb.noise(nb.mapping(uv, scale=(4.0, 14.0, 1.0)), detail=3.0), 0.3, 0.7, 0.55, 1.05)
    inside = nb.math("LESS_THAN", x, nb.math("MULTIPLY", prof, rag))
    # needle fishbone near the edges: diagonal stripes
    # fuzzy needle clumps (not a regular fishbone: that reads as a feather)
    clump = nb.noise(nb.mapping(uv, scale=(14.0, 40.0, 1.0)), detail=10.0, rough=0.75)
    fine = nb.noise(nb.mapping(uv, scale=(70.0, 160.0, 1.0)), detail=2.0)
    needle = nb.math("GREATER_THAN", nb.math("ADD", clump, nb.math("MULTIPLY", fine, 0.35)),
                     nb.math("ADD", 0.5, nb.math("MULTIPLY", x, 0.25)))
    needle = nb.math("MAXIMUM", needle, nb.math("LESS_THAN", x, 0.06))
    alpha = nb.math("MULTIPLY", inside, needle)

    rnd = nb.o(nb.new("ShaderNodeObjectInfo"), "Random")
    base = nb.ramp(rnd, [(0.0, (0.016, 0.028, 0.02)), (1.0, (0.03, 0.045, 0.028))])
    tip = (0.045, 0.065, 0.04)                      # fresh growth at twig tips
    col = nb.mix(nb.math("POWER", v, 3.0), base, tip)
    shade = nb.maprange(nb.noise(nb.mapping(uv, scale=(5.0, 12.0, 1.0)), detail=2.0), 0.35, 0.65, 0.55, 1.1)
    col = nb.mix(1.0, col, nb.comb(shade, shade, shade), "MULTIPLY")
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    nb.set(bsdf, "Base Color", col)
    nb.set(bsdf, "Roughness", 0.55)
    nb.set(bsdf, "Alpha", alpha)
    tr = nb.new("ShaderNodeBsdfTranslucent")
    nb.set(tr, "Color", nb.mix(1.0, col, (1.6, 2.2, 1.2), "MULTIPLY"))
    ms = nb.new("ShaderNodeMixShader", inputs={0: 0.25})
    nb.links.new(bsdf.outputs[0], ms.inputs[1])
    nb.links.new(tr.outputs[0], ms.inputs[2])
    # translucent part must also respect the alpha cut-out
    tp = nb.new("ShaderNodeBsdfTransparent")
    ma = nb.new("ShaderNodeMixShader")
    nb.set(ma, 0, alpha)
    nb.links.new(tp.outputs[0], ma.inputs[1])
    nb.links.new(ms.outputs[0], ma.inputs[2])
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(ma.outputs[0], nb.i(out, "Surface"))
    return mat


def grass():
    mat, nb = new_material("Grass")
    _, v, _ = nb.sep(nb.coord("UV"))
    rnd = nb.o(nb.new("ShaderNodeObjectInfo"), "Random")
    # per-instance: mostly green, some autumn-dry clumps
    base = nb.ramp(rnd, [(0.0, (0.025, 0.04, 0.012)), (0.55, (0.045, 0.06, 0.016)),
                         (0.8, (0.07, 0.068, 0.025)), (1.0, (0.11, 0.09, 0.045))])
    col = nb.mix(nb.math("POWER", v, 1.5), nb.mix(1.0, base, (0.4, 0.4, 0.4), "MULTIPLY"), base)
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    nb.set(bsdf, "Base Color", col)
    nb.set(bsdf, "Roughness", 0.5)
    tr = nb.new("ShaderNodeBsdfTranslucent")
    nb.set(tr, "Color", nb.mix(1.0, col, (1.5, 1.8, 0.9), "MULTIPLY"))
    ms = nb.new("ShaderNodeMixShader", inputs={0: 0.3})
    nb.links.new(bsdf.outputs[0], ms.inputs[1])
    nb.links.new(tr.outputs[0], ms.inputs[2])
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(ms.outputs[0], nb.i(out, "Surface"))
    return mat


def fern_proc():
    """Procedural fern frond: leaflet comb cut out with alpha."""
    mat, nb = new_material("FernProc")
    u, v, _ = nb.sep(nb.coord("UV"))
    x = nb.math("ABSOLUTE", nb.math("MULTIPLY", nb.math("SUBTRACT", u, 0.5), 2.0))
    prof = nb.math("SINE", nb.math("MULTIPLY", nb.maprange(v, 0, 1, 0.08, 1.0), 3.1416))
    comb = nb.math("ADD", 0.25, nb.math("MULTIPLY", 0.75, nb.math("ABSOLUTE",
                   nb.math("SINE", nb.math("MULTIPLY", v, 75.0)))))
    alpha = nb.math("LESS_THAN", x, nb.math("MULTIPLY", prof, comb))
    alpha = nb.math("MAXIMUM", alpha, nb.math("LESS_THAN", x, 0.06))
    rnd = nb.o(nb.new("ShaderNodeObjectInfo"), "Random")
    col = nb.ramp(rnd, [(0.0, (0.03, 0.06, 0.015)), (1.0, (0.08, 0.10, 0.02))])
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    nb.set(bsdf, "Base Color", col)
    nb.set(bsdf, "Roughness", 0.5)
    nb.set(bsdf, "Alpha", alpha)
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(bsdf.outputs[0], nb.i(out, "Surface"))
    return mat


def leaf_cover():
    """Low ground-cover leaves (sorrel / bilberry-like): oval alpha cut-outs."""
    mat, nb = new_material("LeafCover")
    u, v, _ = nb.sep(nb.coord("UV"))
    du = nb.math("MULTIPLY", nb.math("SUBTRACT", u, 0.5), 2.0)
    dv = nb.math("MULTIPLY", nb.math("SUBTRACT", v, 0.5), 2.0)
    r2 = nb.math("ADD", nb.math("MULTIPLY", du, du), nb.math("MULTIPLY", dv, dv))
    alpha = nb.math("LESS_THAN", r2, 0.9)
    rnd = nb.o(nb.new("ShaderNodeObjectInfo"), "Random")
    col = nb.ramp(rnd, [(0.0, (0.008, 0.02, 0.006)), (0.7, (0.02, 0.036, 0.01)),
                        (1.0, (0.045, 0.026, 0.01))])
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    nb.set(bsdf, "Base Color", col)
    nb.set(bsdf, "Roughness", 0.75)
    nb.set(bsdf, "Specular IOR Level", 0.2)   # matte: glossy leaves read as paper in backlight
    nb.set(bsdf, "Alpha", alpha)
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(bsdf.outputs[0], nb.i(out, "Surface"))
    return mat


def moss_cushion():
    """Thick cushion moss: velvety green, very rough, fine bump."""
    mat, nb = new_material("MossCushion")
    p = nb.coord("Object")
    tone = nb.noise(p, scale=6.0, detail=4.0)
    col = nb.ramp(tone, [(0.3, (0.02, 0.04, 0.008)), (0.7, (0.06, 0.085, 0.015))])
    b = nb.new("ShaderNodeBump", inputs={"Strength": 0.6, "Distance": 0.01})
    nb.set(b, "Height", nb.noise(p, scale=60.0, detail=3.0))
    _finish(nb, col, 0.95, b.outputs[0], extra={"Sheen Weight": 0.6, "Specular IOR Level": 0.15})
    return mat


def glass():
    mat, nb = new_material("WindowGlass")
    dirt = nb.noise(nb.coord("Object"), scale=30.0, detail=4.0)
    _finish(nb, (0.9, 0.92, 0.9), nb.maprange(dirt, 0.4, 0.8, 0.02, 0.25),
            extra={"Transmission Weight": 1.0, "IOR": 1.45})
    return mat


def emission(name, rgb, strength):
    mat, nb = new_material(name)
    em = nb.new("ShaderNodeEmission", inputs={"Color": rgb, "Strength": strength})
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(em.outputs[0], nb.i(out, "Surface"))
    return mat


def fabric(rgb=(0.35, 0.12, 0.06)):
    """Curtain: warm translucent cloth, glows when lit from inside."""
    mat, nb = new_material("Curtain")
    bsdf = _finish(nb, rgb, 0.8)
    tr = nb.new("ShaderNodeBsdfTranslucent", inputs={"Color": (0.9, 0.55, 0.3)})
    ms = nb.new("ShaderNodeMixShader", inputs={0: 0.6})
    out = nb.nodes["Material Output"]
    nb.links.new(bsdf.outputs[0], ms.inputs[1])
    nb.links.new(tr.outputs[0], ms.inputs[2])
    nb.links.new(ms.outputs[0], nb.i(out, "Surface"))
    return mat


def painted(maps, name, rgb, rough=0.6, streaks=0.25):
    """Painted masonry (lighthouse tower): plaster texture tinted, with rain streaks."""
    mat, nb = new_material(name)
    obj = nb.coord("Object")
    vec = nb.mapping(obj, scale=(0.5, 0.5, 0.5))
    if maps:
        col, r, nor = _pbr_maps(nb, maps, vec, box=True, tint=(1, 1, 1), bump=0.3)
        col = nb.mix(0.85, col, rgb, "MULTIPLY")
        col = nb.mix(0.55, col, rgb)
    else:
        col, r, nor = rgb, rough, None
    # vertical dirt streaks: noise stretched along z
    st = nb.noise(nb.mapping(obj, scale=(6.0, 6.0, 0.25)), detail=3.0)
    dirt = nb.maprange(st, 0.5, 0.75, 0.0, streaks)
    col = nb.mix(dirt, col, (0.25, 0.22, 0.18), "MULTIPLY")
    _finish(nb, col, rough, nor)
    return mat


def metal(name="Metal", rgb=(0.04, 0.045, 0.05)):
    mat, nb = new_material(name)
    rust = nb.maprange(nb.noise(nb.coord("Object"), scale=4.0, detail=6.0), 0.55, 0.75)
    col = nb.mix(rust, rgb, (0.12, 0.05, 0.02))
    _finish(nb, col, nb.mixf(rust, 0.35, 0.8), extra={"Metallic": nb.mixf(rust, 0.8, 0.1)})
    return mat


def coast_ground(maps_grass, maps_rock, top_z):
    """Grass on the plateau, raw rock on steep faces, dark wet band at the waterline."""
    mat, nb = new_material("CoastGround")
    world = nb.coord("Object")
    _, _, z = nb.sep(world)
    geo = nb.new("ShaderNodeNewGeometry")
    _, _, nz = nb.sep(nb.o(geo, "Normal"))
    vg = nb.mapping(world, scale=(0.5, 0.5, 0.5))
    vr = nb.mapping(world, scale=(0.18, 0.18, 0.18))
    if maps_grass:
        cg, rg, _ = _pbr_maps(nb, maps_grass, vg, box=True, tint=(0.38, 0.5, 0.24))
    else:
        cg, rg = (0.08, 0.1, 0.03), 0.8
    if maps_rock:
        cr, rr, nr = _pbr_maps(nb, maps_rock, vr, box=True, tint=(0.8, 0.76, 0.7), bump=1.0)
    else:
        cr, rr, nr = _proc_stone(nb, vr)
    wob = nb.math("MULTIPLY", nb.noise(world, scale=0.4, detail=4.0), 0.25)
    gmask = nb.maprange(nb.math("ADD", nz, wob), 0.72, 0.86)
    col = nb.mix(gmask, cr, cg)
    rough = nb.mixf(gmask, rr, rg)
    # wet rock and algae near the waterline
    wet = nb.maprange(z, 2.0, 0.2)
    col = nb.mix(nb.math("MULTIPLY", wet, 0.7), col, (0.02, 0.025, 0.015))
    rough = nb.mixf(wet, rough, 0.25)
    col = _variation(nb, col, world, scale=0.03, amount=0.2)
    _finish(nb, col, rough, nr)
    return mat


def autumn_leaf(palette):
    """Alpha-cut leaf card; colour = per-instance + per-clump random over an autumn palette."""
    mat, nb = new_material("AutumnLeaf")
    u, v, _ = nb.sep(nb.coord("UV"))
    du = nb.math("MULTIPLY", nb.math("SUBTRACT", u, 0.5), 2.0)
    dv = nb.math("MULTIPLY", nb.math("SUBTRACT", v, 0.45), 2.0)
    # lobed leaf: radius modulated by angle (5 lobes), small stem notch
    ang = nb.math("ARCTAN2", dv, du)
    lobes = nb.math("ADD", 0.72, nb.math("MULTIPLY", 0.22, nb.math("ABSOLUTE", nb.math("SINE",
                    nb.math("MULTIPLY", ang, 2.5)))))
    r = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", du, du), nb.math("MULTIPLY", dv, dv)))
    alpha = nb.math("LESS_THAN", r, lobes)
    rnd = nb.o(nb.new("ShaderNodeObjectInfo"), "Random")
    clump = nb.noise(nb.coord("Object"), scale=0.8, detail=1.0)
    k = nb.math("FRACT", nb.math("ADD", rnd, nb.math("MULTIPLY", clump, 1.7)))
    stops = [(i / max(1, len(palette) - 1), tuple(c)) for i, c in enumerate(palette)]
    col = nb.ramp(k, stops)
    vein = nb.math("MULTIPLY", nb.maprange(r, 0.0, 0.8, 0.75, 1.0), 1.0)
    col = nb.mix(1.0, col, nb.comb(vein, vein, vein), "MULTIPLY")
    # per-leaf brightness jitter + crown self-shadow (inner/lower leaves darker, less saturated)
    jit = nb.maprange(nb.noise(nb.coord("Object"), scale=9.0, detail=1.0), 0.3, 0.7, 0.55, 1.15)
    ao = nb.o(nb.new("ShaderNodeAmbientOcclusion", inputs={"Distance": 1.2}), "AO")
    shade = nb.math("MULTIPLY", jit, nb.maprange(ao, 0.0, 1.0, 0.35, 1.0))
    col = nb.mix(1.0, col, nb.comb(shade, shade, shade), "MULTIPLY")
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    nb.set(bsdf, "Base Color", col)
    nb.set(bsdf, "Roughness", 0.55)
    nb.set(bsdf, "Specular IOR Level", 0.3)
    tr = nb.new("ShaderNodeBsdfTranslucent")
    nb.set(tr, "Color", nb.mix(1.0, col, (1.6, 1.3, 0.8), "MULTIPLY"))
    ms = nb.new("ShaderNodeMixShader", inputs={0: 0.35})
    nb.links.new(bsdf.outputs[0], ms.inputs[1])
    nb.links.new(tr.outputs[0], ms.inputs[2])
    tp = nb.new("ShaderNodeBsdfTransparent")
    ma = nb.new("ShaderNodeMixShader")
    nb.set(ma, 0, alpha)
    nb.links.new(tp.outputs[0], ma.inputs[1])
    nb.links.new(ms.outputs[0], ma.inputs[2])
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(ma.outputs[0], nb.i(out, "Surface"))
    return mat


def lake_ground(maps_land, maps_shore):
    """Leaf-litter banks, dark wet mud + pebbles at the waterline, silt below it."""
    mat, nb = new_material("LakeGround")
    world = nb.coord("Object")
    _, _, z = nb.sep(world)
    v = nb.mapping(world, scale=(0.5, 0.5, 0.5))
    if maps_land:
        cl, rl, nl = _pbr_maps(nb, maps_land, v, box=True, tint=(0.45, 0.4, 0.34), bump=0.6)
    else:
        cl, rl, nl = _proc_ground(nb, v)
    if maps_shore:
        cs, rs, _ = _pbr_maps(nb, maps_shore, nb.mapping(world, scale=(0.7, 0.7, 0.7)), box=True,
                              tint=(0.55, 0.53, 0.5))
    else:
        cs, rs = (0.05, 0.045, 0.04), 0.6
    wob = nb.math("MULTIPLY", nb.noise(world, scale=0.5, detail=3.0), 0.3)
    m = nb.maprange(nb.math("ADD", z, wob), 0.9, 0.35)
    col = nb.mix(m, cl, cs)
    rough = nb.mixf(m, rl, rs)
    wet = nb.maprange(z, 0.35, 0.0)
    col = nb.mix(nb.math("MULTIPLY", wet, 0.6), col, (0.0, 0.0, 0.0))
    rough = nb.mixf(wet, rough, 0.2)
    col = _variation(nb, col, world, scale=0.06, amount=0.2)
    _finish(nb, col, rough, nl)
    return mat


def boat_paint():
    mat, nb = new_material("BoatPaint")
    obj = nb.coord("Object")
    _, _, z = nb.sep(obj)
    band = nb.maprange(z, 0.38, 0.42)
    col = nb.mix(band, (0.03, 0.07, 0.09), (0.55, 0.52, 0.45))
    worn = nb.maprange(nb.noise(obj, scale=6.0, detail=6.0), 0.6, 0.75)
    col = nb.mix(worn, col, (0.12, 0.09, 0.06))
    _finish(nb, col, 0.55)
    return mat


def jungle_leaf():
    """Large tropical leaf: smooth oval blade with a pale midrib, glossy, translucent."""
    mat, nb = new_material("JungleLeaf")
    u, v, _ = nb.sep(nb.coord("UV"))
    x = nb.math("ABSOLUTE", nb.math("MULTIPLY", nb.math("SUBTRACT", u, 0.5), 2.0))
    prof = nb.math("POWER", nb.math("SINE", nb.math("MULTIPLY", nb.maprange(v, 0, 1, 0.05, 1.0), 3.1416)), 0.6)
    alpha = nb.math("LESS_THAN", x, prof)
    rnd = nb.o(nb.new("ShaderNodeObjectInfo"), "Random")
    col = nb.ramp(rnd, [(0.0, (0.02, 0.07, 0.012)), (1.0, (0.05, 0.12, 0.02))])
    rib = nb.maprange(x, 0.0, 0.05, 1.0, 0.0)
    col = nb.mix(nb.math("MULTIPLY", rib, 0.6), col, (0.15, 0.22, 0.06))
    veins = nb.maprange(nb.math("SINE", nb.math("SUBTRACT", nb.math("MULTIPLY", v, 40.0),
                                                  nb.math("MULTIPLY", x, 12.0))), 0.85, 1.0, 1.0, 0.8)
    col = nb.mix(1.0, col, nb.comb(veins, veins, veins), "MULTIPLY")
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    nb.set(bsdf, "Base Color", col)
    nb.set(bsdf, "Roughness", 0.35)
    nb.set(bsdf, "Alpha", alpha)
    tr = nb.new("ShaderNodeBsdfTranslucent")
    nb.set(tr, "Color", nb.mix(1.0, col, (1.4, 2.0, 0.9), "MULTIPLY"))
    ms = nb.new("ShaderNodeMixShader", inputs={0: 0.3})
    nb.links.new(bsdf.outputs[0], ms.inputs[1])
    nb.links.new(tr.outputs[0], ms.inputs[2])
    tp = nb.new("ShaderNodeBsdfTransparent")
    ma = nb.new("ShaderNodeMixShader")
    nb.set(ma, 0, alpha)
    nb.links.new(tp.outputs[0], ma.inputs[1])
    nb.links.new(ms.outputs[0], ma.inputs[2])
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(ma.outputs[0], nb.i(out, "Surface"))
    return mat


def jungle_ground(maps_rock, maps_moss):
    """Wet dark rock on steep faces, thick moss on anything not vertical, slick near water."""
    mat, nb = new_material("JungleGround")
    world = nb.coord("Object")
    _, _, z = nb.sep(world)
    geo = nb.new("ShaderNodeNewGeometry")
    _, _, nz = nb.sep(nb.o(geo, "Normal"))
    vr = nb.mapping(world, scale=(0.3, 0.3, 0.3))
    if maps_rock:
        cr, rr, nr = _pbr_maps(nb, maps_rock, vr, box=True, tint=(0.35, 0.36, 0.34), bump=1.0)
    else:
        cr, rr, nr = _proc_stone(nb, vr)
    if maps_moss:
        cm, rm, _ = _pbr_maps(nb, maps_moss, nb.mapping(world, scale=(0.6, 0.6, 0.6)), box=True,
                              tint=(0.07, 0.13, 0.035))
    else:
        cm, rm = (0.03, 0.06, 0.01), 0.9
    # horizontal strata on the rock: bands along z, warped so they are not ruler-straight
    warp = nb.math("MULTIPLY", nb.noise(world, scale=0.15, detail=3.0), 2.5)
    strata = nb.math("SINE", nb.math("MULTIPLY", nb.math("ADD", z, warp), 2.2))
    band = nb.maprange(strata, -1.0, 1.0, 0.65, 1.15)
    cr = nb.mix(1.0, cr, nb.comb(band, band, band), "MULTIPLY")
    ledge = nb.maprange(strata, 0.75, 0.95)                    # thin moss-filled ledges
    wob = nb.math("MULTIPLY", nb.noise(world, scale=0.8, detail=5.0), 0.5)
    m = nb.math("MAXIMUM", nb.maprange(nb.math("ADD", nz, wob), 0.35, 0.65),
                nb.math("MULTIPLY", ledge, 0.8))
    col = nb.mix(m, cr, cm)
    hsv = nb.new("ShaderNodeHueSaturation", inputs={"Hue": 0.54, "Saturation": 0.9, "Value": 0.7})
    nb.set(hsv, "Color", col)                     # shift the ground away from yellow toward moss green
    col = hsv.outputs[0]
    rough = nb.mixf(m, nb.math("MULTIPLY", rr, 0.5), rm)          # wet rock is glossy
    col, rough = _moss(nb, col, rough, amount=0.5, scale=1.5, up_only=False)
    _finish(nb, col, rough, nr)
    return mat


def library(tex: dict):
    """Build every material once. ``tex`` maps role -> maps-dict or None."""
    if tex.get("_style") == "rainforest_waterfall":
        return {
            "bark": bark(tex.get("bark")), "bark_birch": bark(tex.get("bark")),
            "autumn_leaf": autumn_leaf(tex.get("_leaf_palette") or
                                       [(0.02, 0.07, 0.01), (0.04, 0.11, 0.015), (0.07, 0.15, 0.02)]),
            "fern": fern_proc(), "grass": grass(), "leafcover": leaf_cover(),
            "rock": stone(tex.get("rock"), name="WetRock", moss=0.6), "moss": moss_cushion(),
            "jungle_leaf": jungle_leaf(),
        }
    if tex.get("_style") == "greenhouse":
        return {
            "frame": painted(None, "WhiteSteel", (0.75, 0.76, 0.74), rough=0.4, streaks=0.15),
            "glass": glass(),
            "tiles": stone(tex.get("tiles"), name="AisleTiles", moss=0.12),
            "gravel": stone(tex.get("gravel"), name="Gravel", moss=0.2),
            "bench_wood": log_wood(tex.get("wood"), name="BenchWood", tint=(0.55, 0.5, 0.45), moss=0.05),
            "terracotta": stone(tex.get("terracotta"), name="Terracotta", moss=0.1),
            "soil": stone(None, name="Soil", moss=0.5),
            "lawn": stone(tex.get("lawn"), name="Lawn", moss=0.0),
            "bark": bark(None), "autumn_leaf": autumn_leaf([(0.05, 0.12, 0.02), (0.1, 0.2, 0.03),
                                                            (0.08, 0.15, 0.04)]),
            "fern": fern_proc(), "grass": grass(), "leafcover": leaf_cover(),
        }
    if tex.get("_style") == "lakeside_dock":
        return {
            "deck": log_wood(tex.get("deck"), name="Deck", tint=(0.55, 0.5, 0.45), moss=0.2),
            "log": log_wood(tex.get("deck"), name="Posts", tint=(0.32, 0.28, 0.24), moss=0.35),
            "bark": bark(tex.get("bark")),
            "bark_birch": bark(tex.get("bark")),
            "needles": needles(),
            "autumn_leaf": autumn_leaf(tex.get("_leaf_palette") or
                                       [(0.35, 0.03, 0.01), (0.55, 0.12, 0.01), (0.7, 0.3, 0.02),
                                        (0.6, 0.45, 0.05), (0.15, 0.2, 0.03)]),
            "boat": boat_paint(),
            "lantern_glow": emission("LanternGlow", (1.0, 0.55, 0.22), 2.5),
            "grass": grass(), "rock": stone(tex.get("rock"), name="ShoreRock", moss=0.4),
            "leafcover": leaf_cover(), "moss": moss_cushion(),
        }
    if tex.get("_style") == "coastal_lighthouse":
        return {
            "_tower_maps": tex.get("tower"),
            "tower_white": painted(tex.get("tower"), "TowerWhite", (0.78, 0.77, 0.73)),
            "tower_band": painted(tex.get("tower"), "TowerRed", (0.42, 0.05, 0.035)),
            "stone": stone(tex.get("rock"), name="Plinth", moss=0.2),
            "metal": metal(), "dark": emission("DarkRecess", (0.0, 0.0, 0.0), 0.0),
            "cottage": painted(tex.get("cottage"), "CottageWall", (0.72, 0.71, 0.68), streaks=0.15),
            "slate": metal("Slate", (0.025, 0.028, 0.032)),
            "window_glow": emission("CottageWindow", (1.0, 0.62, 0.3), 6.0),
            "glass": glass(),
            "rock": stone(tex.get("rock"), name="SeaRock", moss=0.1),
            "grass": grass(),
        }
    return {
        "log": log_wood(tex.get("log")),
        "plank": log_wood(tex.get("log"), name="Plank", tint=(0.55, 0.47, 0.40), moss=0.0),
        "deck": log_wood(tex.get("log"), name="Deck", tint=(0.6, 0.55, 0.5), moss=0.35),
        "firewood": log_wood(None, name="Firewood", moss=0.0),
        "roof": roof(tex.get("roof")),
        "stone": stone(tex.get("stone")),
        "rock": stone(tex.get("rock"), name="Rock", moss=0.55),
        "ground": ground(tex.get("ground"), tex.get("ground_b")),
        "bark": bark(tex.get("bark")),
        "needles": needles(),
        "grass": grass(),
        "fern": fern_proc(),
        "leafcover": leaf_cover(),
        "moss": moss_cushion(),
        "glass": glass(),
        "curtain": fabric(),
    }
