"""Lighthouse with gallery, lantern room, keeper's cottage and rotating beams.

Tower stands at the origin on the plateau (ground height ``z0``). Beams are
emissive volume cones (no lighting cost) parented to a pivot that the
animation rotates; a point light in the lantern gives the warm local glow.
"""

import math

import bpy
from mathutils import Matrix, Vector

from .. import core
from ..nodes import new_material
from .mesh import MeshBuilder, frame


def _ring(mb, z, r_in, r_out, h, segs=32, mat=0):
    """Flat annulus slab (gallery deck)."""
    for k in range(segs):
        a0, a1 = k / segs * math.tau, (k + 1) / segs * math.tau
        pts = []
        for zz in (z, z + h):
            for r in (r_in, r_out):
                pts += [(math.cos(a0) * r, math.sin(a0) * r, zz), (math.cos(a1) * r, math.sin(a1) * r, zz)]
        b = mb.add_verts(pts)
        # indices: z0: in0 in1 out0 out1 ; z1: +4
        for q in ((b + 2, b + 3, b + 7, b + 6), (b + 1, b + 0, b + 4, b + 5),
                  (b + 4, b + 6, b + 7, b + 5), (b + 0, b + 1, b + 3, b + 2)):
            mb.add_face(q, ((0, 0), (1, 0), (1, 1), (0, 1)), mat)


def beam_material(color, strength, length):
    mat, nb = new_material("BeamVolume")
    p = nb.coord("Object")
    x, y, z = nb.sep(p)                       # beam axis = local +X
    along = nb.math("DIVIDE", x, length)
    fade = nb.math("MULTIPLY", nb.maprange(along, 0.0, 0.03),
                   nb.math("POWER", nb.maprange(along, 0.0, 1.0, 1.0, 0.0), 2.0))
    r = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", y, y), nb.math("MULTIPLY", z, z)))
    w = nb.math("ADD", 0.5, nb.math("MULTIPLY", x, 0.06))   # cone half-width at x
    core_ = nb.math("EXPONENT", nb.math("MULTIPLY", nb.math("POWER", nb.math("DIVIDE", r, w), 2.0), -2.0))
    vol = nb.new("ShaderNodeVolumePrincipled", inputs={"Density": 0.0, "Emission Color": color})
    nb.set(vol, "Emission Strength", nb.math("MULTIPLY", nb.math("MULTIPLY", fade, core_), strength))
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(vol.outputs[0], nb.i(out, "Volume"))
    return mat


def build(rng, cfg: dict, mats: dict, z0: float, practical_scale=1.0, beam=True):
    H = cfg["tower_height"] * rng.uniform(0.92, 1.08)
    r0, r1 = cfg["base_radius"], cfg["top_radius"]
    col = core.collection("Lighthouse")

    # ---- tower body: horizontal colour bands via material index -------------
    tower = MeshBuilder()
    bands = cfg["bands"]
    segs, rings = 40, 24
    for i in range(rings):
        za, zb = H * i / rings, H * (i + 1) / rings
        ra = r0 + (r1 - r0) * i / rings
        rb = r0 + (r1 - r0) * (i + 1) / rings
        band = int((i + 0.5) / rings * bands) % 2 if bands else 0
        tower.cylinder(zb - za, ra, rb, segs=segs, m=frame((0, 0, z0 + za), (0, 0, 1), up=(1, 0, 0)),
                       mat=band, caps=False, uv_scale=1.0)
    # plinth
    tower.cylinder(1.0, r0 + 0.6, r0 + 0.5, segs=8, m=frame((0, 0, z0 - 0.6), (0, 0, 1), up=(1, 0, 0)), mat=2)
    zt = z0 + H
    # gallery deck + railing
    _ring(tower, zt, 0.0, r1 + 0.9, 0.22, mat=3)
    for k in range(28):
        a = k / 28 * math.tau
        p = (math.cos(a) * (r1 + 0.82), math.sin(a) * (r1 + 0.82), zt + 0.22)
        tower.cylinder(1.0, 0.025, segs=4, m=frame(p, (0, 0, 1), up=(1, 0, 0)), mat=3, caps=False)
    _ring(tower, zt + 1.18, r1 + 0.76, r1 + 0.9, 0.06, mat=3)
    # lantern room: frame bars (glass separate), roof cone + vent ball
    lr, lh = r1 * 0.72, 2.3
    zl = zt + 0.22
    tower.cylinder(0.5, lr + 0.05, segs=24, m=frame((0, 0, zl), (0, 0, 1), up=(1, 0, 0)), mat=3)
    for k in range(10):
        a = k / 10 * math.tau
        p = (math.cos(a) * lr, math.sin(a) * lr, zl + 0.5)
        tower.cylinder(lh - 0.5, 0.04, segs=4, m=frame(p, (0, 0, 1), up=(1, 0, 0)), mat=3)
    tower.cylinder(1.3, lr + 0.25, 0.08, segs=24, rings=3, m=frame((0, 0, zl + lh), (0, 0, 1), up=(1, 0, 0)),
                   mat=3, bend=None)
    tower.cylinder(0.35, 0.18, 0.18, segs=10, m=frame((0, 0, zl + lh + 1.25), (0, 0, 1), up=(1, 0, 0)), mat=3)
    # door + small windows (dark recesses as thin boxes on the surface)
    for zz, w_, h_, a in ((0.0, 1.0, 2.1, -math.pi / 2), (H * 0.35, 0.45, 0.8, -math.pi / 2 + 0.6),
                          (H * 0.62, 0.45, 0.8, -math.pi / 2 - 0.5)):
        rr = r0 + (r1 - r0) * (zz + h_ / 2) / H
        p = Vector((math.cos(a) * (rr - 0.02), math.sin(a) * (rr - 0.02), z0 + zz + h_ / 2))
        tower.box((w_, 0.12, h_), m=frame(p, (-math.sin(a), math.cos(a), 0)), mat=4)
    pal = cfg.get("palette")
    if pal:                                   # seed-chosen colour scheme
        from .. import materials as M
        mats = dict(mats)
        mats["tower_white"] = M.painted(mats.get("_tower_maps"), "TowerWhite", tuple(pal["white"]))
        mats["tower_band"] = M.painted(mats.get("_tower_maps"), "TowerBand", tuple(pal["band"]))
    tower_obj = tower.build("Lighthouse_Tower",
                            [mats["tower_white"], mats["tower_band"], mats["stone"], mats["metal"],
                             mats["dark"]], smooth=True)
    glass = MeshBuilder()
    glass.cylinder(lh - 0.5, lr - 0.03, segs=24, m=frame((0, 0, zl + 0.5), (0, 0, 1), up=(1, 0, 0)), caps=False)
    glass_obj = glass.build("Lighthouse_Glass", [mats["glass"]])
    glass_obj.visible_shadow = False

    # ---- keeper's cottage ------------------------------------------------------
    ca = rng.uniform(0.6, 1.2) * rng.choice((-1, 1)) + math.pi / 2     # beside, slightly inland
    cd = r0 + 4.2
    cx, cy = math.cos(ca) * cd, math.sin(ca) * cd
    cw, cdp, chh = 6.0, 4.5, 2.8
    cot = MeshBuilder()
    m_c = Matrix.Translation((cx, cy, z0)) @ Matrix.Rotation(ca + math.pi / 2, 4, "Z")
    cot.box((cw, cdp, chh + 0.6), m=m_c @ Matrix.Translation((0, 0, (chh - 0.6) / 2)), mat=0)
    pitch = math.radians(32)
    L = (cdp / 2 + 0.35) / math.cos(pitch)
    for sgn in (-1, 1):
        d = Vector((0, sgn * math.cos(pitch), -math.sin(pitch)))
        c = Vector((0, 0, chh + (cdp / 2) * math.tan(pitch))) + d * (L / 2) + Vector((0, 0, 0.08))
        cot.box((L, cw + 0.5, 0.12), m=m_c @ frame(c, d), mat=1)
    # gable triangles
    for sx in (-1, 1):
        b = cot.add_verts([m_c @ Vector((sx * cw / 2, -cdp / 2, chh)), m_c @ Vector((sx * cw / 2, cdp / 2, chh)),
                           m_c @ Vector((sx * cw / 2, 0, chh + (cdp / 2) * math.tan(pitch)))])
        cot.add_face((b, b + 1, b + 2) if sx > 0 else (b + 2, b + 1, b), ((0, 0), (1, 0), (0.5, 1)), 0)
    wins = []
    for wx in (-1.6, 1.4):
        p = m_c @ Vector((wx, -cdp / 2 - 0.01, 1.4))
        cot.box((0.9, 0.04, 1.0), m=Matrix.Translation(p) @ Matrix.Rotation(ca + math.pi / 2, 4, "Z"), mat=2)
        wins.append(p)
    cot_obj = cot.build("Lighthouse_Cottage", [mats["cottage"], mats["slate"], mats["window_glow"]],
                        smooth=False)
    if not cfg.get("cottage", True):
        bpy.data.objects.remove(cot_obj)
        cot_obj, wins = None, []
        cx = cy = 0.0

    for o in [o for o in (tower_obj, glass_obj, cot_obj) if o is not None]:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)

    # ---- lights -------------------------------------------------------------------
    warm = core.kelvin_rgb(cfg["lamp_kelvin"])
    lamp = bpy.data.lights.new("LanternLamp", "POINT")
    lamp.energy = cfg["lamp_watts"] * practical_scale
    lamp.color = warm
    lamp.shadow_soft_size = 0.3
    lo = bpy.data.objects.new("LanternLamp", lamp)
    lo.location = (0, 0, zl + 1.3)
    col.objects.link(lo)
    for i, p in enumerate(wins):
        L_ = bpy.data.lights.new(f"CottageLight{i}", "POINT")
        L_.energy = 60 * practical_scale
        L_.color = core.kelvin_rgb(2600)
        o = bpy.data.objects.new(f"CottageLight{i}", L_)
        inward = (Vector((cx, cy, p.z)) - p).normalized()
        o.location = p + inward * 1.2
        col.objects.link(o)

    pivot = None
    if beam:
        pivot = bpy.data.objects.new("BeamPivot", None)
        pivot.location = (0, 0, zl + 1.3)
        col.objects.link(pivot)
        bl = cfg["beam_length"]
        bmat = beam_material(core.kelvin_rgb(cfg["beam_kelvin"]), cfg["beam_strength"], bl)
        for k, ang in enumerate((0.0, math.pi)):
            mb = MeshBuilder()
            mb.cylinder(bl, 0.4, 0.5 + bl * 0.06 * 2.2, segs=12, rings=1,
                        m=Matrix.Rotation(ang, 4, "Z") @ frame((0.3, 0, 0), (1, 0, -0.012)))
            o = mb.build(f"Beam{k}", [bmat], link=False)
            o.parent = pivot
            col.objects.link(o)
            o.visible_shadow = False

    top = zl + lh + 1.6
    pts = [(x, y, z) for x in (-r0 - 0.6, r0 + 0.6) for y in (-r0 - 0.6, r0 + 0.6) for z in (z0, top)]
    pts += [(cx, cy, z0), (cx, cy, z0 + chh + 1.4)]
    return {
        "objects": [o for o in (tower_obj, glass_obj, cot_obj) if o], "collection": "Lighthouse",
        "bbox_points": pts, "center": (0.0, 0.0, z0 + (top - z0) * 0.5), "height": top - z0,
        "base_z": z0, "top": top, "lantern": (0, 0, zl + 1.3), "pivot": pivot,
        "footprint": (min(-r0 - 1, cx - 4.5), max(r0 + 1, cx + 4.5),
                      min(-r0 - 1, cy - 4.5), max(r0 + 1, cy + 4.5)),
    }
