"""Water: reusable sea / lake surfaces.

* ``ocean(...)``      - Blender Ocean modifier tiles (seeded, animated by time)
                         plus a flat far plane out to the horizon.
* ``calm_water(...)`` - flat lake/pond surface with gentle ripple bump.
* ``shore_mask(...)`` - foam mask image baked from any terrain height
                         function: white water where land meets the sea.

All share one water shader (``water_material``) so every style gets the
same tuned look: dark absorbing body, Fresnel sky reflection, foam on top.
"""

import math

import bpy

from .nodes import NB, new_material


def shore_mask(height_fn, extent, res=512, reach=30.0, name="ShoreMask"):
    """Distance-to-coast field over [-extent/2, extent/2]^2, normalised 0..1 by ``reach``.

    Stored as closeness: 1 at the waterline (and on land), 0 at ``reach`` metres or more.
    The water shader turns it into surf bands that run parallel to the coast.
    """
    import numpy as np
    xs = np.linspace(-extent / 2, extent / 2, res)
    h = np.array([[height_fn(x, y) for x in xs] for y in xs], dtype=np.float32)
    land = h > 0.0
    px = extent / (res - 1)
    steps = int(reach / px) + 1
    dist = np.full((res, res), float(steps), dtype=np.float32)
    front = land.copy()
    dist[land] = 0.0
    for i in range(1, steps + 1):          # chessboard dilation = cheap distance transform
        p = np.pad(front, 1, mode="edge")
        grown = np.logical_or.reduce([p[a:a + res, b:b + res] for a in range(3) for b in range(3)])
        new = grown & ~front
        dist[new] = i
        front = grown
    # stored as closeness (1 at the waterline, 0 far out): outside the image the
    # CLIP extension returns 0 = "far out", never "at the rocks"
    m = (1.0 - np.clip(dist / steps, 0.0, 1.0)).astype(np.float32)
    m[land] = 1.0
    img = bpy.data.images.new(name, res, res, alpha=False, float_buffer=True)
    # colour space and file format first: changing them afterwards regenerates the
    # (generated) image buffer and silently wipes the pixels
    img.colorspace_settings.name = "Non-Color"
    img.file_format = "OPEN_EXR"
    img.pixels.foreach_set(np.dstack([m, m, m, np.ones_like(m)]).ravel())
    img.update()
    img.pack()                               # keep it inside the .blend
    return img, extent, reach


def water_material(name="Water", deep=(0.004, 0.018, 0.024), rough=0.035, foam_attr=None,
                   shore=None, ripple=0.15, ripple_scale=2.2, far_rough=None):
    mat, nb = new_material(name)
    world = nb.o(nb.new("ShaderNodeNewGeometry"), "Position")   # world space: tiles are offset
    t = nb.new("ShaderNodeValue")
    t.name = t.label = "easyscene_time"
    # small capillary ripples on top of the big waves
    rip = nb.noise(world, scale=ripple_scale, detail=8.0, rough=0.65, dims="4D",
                   w=nb.math("MULTIPLY", t.outputs[0], 0.4))
    bump = nb.new("ShaderNodeBump", inputs={"Strength": ripple, "Distance": 0.05})
    nb.set(bump, "Height", rip)
    foam = None
    if foam_attr:
        a = nb.new("ShaderNodeAttribute", attribute_name=foam_attr)
        foam = nb.maprange(nb.o(a, "Fac"), 0.55, 1.0)       # only real crests
    if shore is not None:
        img, ext, reach = shore
        tex = nb.new("ShaderNodeTexImage", interpolation="Linear", extension="CLIP")
        tex.image = img
        x, y, _ = nb.sep(world)
        uv = nb.comb(nb.math("ADD", nb.math("DIVIDE", x, ext), 0.5),
                     nb.math("ADD", nb.math("DIVIDE", y, ext), 0.5), 0.0)
        nb.set(tex, "Vector", uv)
        d = nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, nb.o(tex, "Color")), reach)   # metres out
        tt = t.outputs[0]
        # surf bands: crests every ~7 m rolling toward the shore, wobbly along the coast
        wob = nb.math("MULTIPLY", nb.noise(world, scale=0.06, detail=2.0), 9.0)
        phase = nb.math("ADD", nb.math("ADD", nb.math("MULTIPLY", d, 0.9), wob),
                        nb.math("MULTIPLY", tt, 1.4))
        band = nb.math("POWER", nb.maprange(nb.math("SINE", phase), 0.35, 1.0), 1.5)
        # crests break up along their length: long gaps and thicker patches
        brk = nb.maprange(nb.noise(world, scale=0.09, detail=3.0, dims="4D",
                                   w=nb.math("MULTIPLY", tt, 0.05)), 0.38, 0.62)
        band = nb.math("MULTIPLY", band, brk)
        # white water right at the rocks (always), bands fading out to ~reach
        edge = nb.maprange(nb.math("ADD", d, nb.math("MULTIPLY", nb.noise(world, scale=0.3), 3.0)),
                           1.0, 7.0, 1.0, 0.0, interp="SMOOTHSTEP")
        fade = nb.maprange(d, 2.0, reach * 0.9, 1.0, 0.0, interp="SMOOTHSTEP")
        churn = nb.maprange(nb.noise(world, scale=0.5, detail=5.0, dims="4D",
                                     w=nb.math("MULTIPLY", tt, 0.3)), 0.3, 0.7, 0.4, 1.0)
        sf = nb.math("MAXIMUM", edge, nb.math("MULTIPLY", band, fade))
        sf = nb.math("MULTIPLY", sf, churn)
        foam = sf if foam is None else nb.math("MAXIMUM", foam, sf)
    # foam is lacy, never a flat white sheet
    if foam is not None:
        lace = nb.maprange(nb.noise(world, scale=2.2, detail=10.0, rough=0.7), 0.32, 0.58)
        vor = nb.new("ShaderNodeTexVoronoi", inputs={"Scale": 1.6})
        nb.set(vor, "Vector", world)
        holes = nb.maprange(vor.outputs[0], 0.05, 0.35)
        foam = nb.math("MULTIPLY", foam, nb.math("MULTIPLY", lace, nb.math("ADD", 0.35, holes)), clamp=True)
    if foam is not None:                      # foam stands up from the water: bump it
        nb.set(bump, "Height", nb.math("ADD", rip, nb.math("MULTIPLY", foam, 0.6)))
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    nb.set(bsdf, "Base Color", deep if foam is None else nb.mix(foam, deep, (0.85, 0.87, 0.88)))
    r = rough if foam is None else nb.mixf(foam, rough, 0.6)
    if far_rough:
        # waves too small to resolve far away act as roughness: match the far plane
        cam = nb.o(nb.new("ShaderNodeCameraData"), "View Distance")
        r = nb.mixf(nb.maprange(cam, far_rough[0] * 0.5, far_rough[0]), r, far_rough[1])
    nb.set(bsdf, "Roughness", r)
    nb.set(bsdf, "IOR", 1.333)
    nb.set(bsdf, "Normal", bump.outputs[0])
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(bsdf.outputs[0], nb.i(out, "Surface"))
    return mat


def ocean(seed, cfg: dict, shore=None, center=(0.0, 0.0)):
    """Animated ocean: modifier tiles around ``center`` + far plane to the horizon."""
    me = bpy.data.meshes.new("Ocean")
    obj = bpy.data.objects.new("Ocean", me)
    bpy.context.scene.collection.objects.link(obj)
    m = obj.modifiers.new("Ocean", "OCEAN")
    m.geometry_mode = "GENERATE"
    m.resolution = cfg.get("resolution", 12)
    m.viewport_resolution = 6
    m.spatial_size = int(cfg["tile_m"])
    m.repeat_x = m.repeat_y = cfg.get("tiles", 4)
    m.wave_scale = cfg["wave_scale"]
    m.choppiness = cfg["choppiness"]
    m.wind_velocity = cfg["wind_m_s"]
    m.wave_alignment = cfg.get("alignment", 0.4)
    m.wave_direction = math.radians(cfg.get("direction_deg", 30))
    m.random_seed = seed % 2147483647
    m.use_normals = True
    m.use_foam = True
    m.foam_layer_name = "foam"
    m.foam_coverage = cfg.get("foam_coverage", 0.2)
    m.time = 0.0
    span = cfg["tile_m"] * m.repeat_x
    obj.location = (center[0] - span / 2 + cfg["tile_m"] / 2, center[1] - span / 2 + cfg["tile_m"] / 2,
                    cfg.get("level_m", 0.0))
    mat = water_material("Ocean", deep=tuple(cfg["deep_color"]), rough=0.07, foam_attr="foam",
                         shore=shore, ripple=0.35, far_rough=(cfg["tile_m"] * cfg.get("tiles", 4) * 0.3, 0.35))
    obj.data.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    # far plane: flat, slightly below the tiles so they win where they overlap
    R = cfg.get("far_m", 6000.0)
    far = bpy.data.meshes.new("OceanFar")
    far.from_pydata([(-R, -R, 0), (R, -R, 0), (R, R, 0), (-R, R, 0)], [], [(0, 1, 2, 3)])
    fobj = bpy.data.objects.new("OceanFar", far)
    fobj.location = (center[0], center[1], cfg.get("level_m", 0.0) - 0.25)
    # far sea: swell-sized bumps + higher roughness, otherwise the flat plane mirrors the
    # low sun as one solid white block at the horizon
    fobj.data.materials.append(water_material("OceanFar", deep=tuple(cfg["deep_color"]),
                                              rough=0.35, ripple=0.6, ripple_scale=0.12))
    bpy.context.scene.collection.objects.link(fobj)
    return obj, fobj


def set_time(obj, seconds, speed=1.0):
    obj.modifiers["Ocean"].time = seconds * speed


def key_time(obj, fps, frame_start, frame_end, speed=1.0):
    m = obj.modifiers["Ocean"]
    for f in (frame_start, frame_end):
        m.time = f / fps * speed
        m.keyframe_insert("time", frame=f)
    from .atmosphere import _fcurves
    if obj.animation_data and obj.animation_data.action:
        for fc in _fcurves(obj.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"


def calm_water(name, size, level=0.0, deep=(0.01, 0.025, 0.02), ripple=0.05):
    """Flat lake surface (mirror-like reflections); ripples only in the shader."""
    h = size / 2
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new(name, me)
    obj.location.z = level
    obj.data.materials.append(water_material(name, deep=deep, rough=0.01, ripple=ripple))
    bpy.context.scene.collection.objects.link(obj)
    return obj
