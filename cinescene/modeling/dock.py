"""Wooden lake dock (jetty) with posts, a moored rowboat and a lantern post.

The dock starts on the bank at ``root`` and runs ``length`` metres out over
the water along -Y. Water level is z = 0; deck sits ``deck_z`` above it.
"""

import math

import bpy
from mathutils import Matrix, Vector

from .. import core
from .mesh import MeshBuilder, frame


def _boat(mb, length=3.6, beam=1.25, depth=0.5, mat=0, seat_mat=0):
    """Simple lofted rowboat hull, bow toward +X, sitting with gunwale at z=depth."""
    stations = 9
    secs = []
    for i in range(stations):
        t = i / (stations - 1)
        x = (t - 0.5) * length
        w = beam / 2 * (math.sin(math.pi * t) ** 0.55) * (0.6 + 0.4 * (1 - t))   # pointier bow
        d = depth * (0.75 + 0.25 * math.sin(math.pi * t))
        rise = 0.12 * (2 * t - 1) ** 4                                         # sheer
        sec = []
        for k in range(7):
            a = math.pi * k / 6                                                 # -w .. bottom .. +w
            sec.append((x, -math.cos(a) * w, depth + rise - math.sin(a) * d))
        secs.append(sec)
    mb.strip(secs, mat=mat)
    # inner surface (thin hull): same loft slightly inset, reversed winding
    inner = [[(p[0], p[1] * 0.92, p[2] + 0.03) for p in reversed(sec)] for sec in secs]
    mb.strip(inner, mat=mat)
    for xs in (-0.6, 0.5):                                                      # thwarts
        mb.box((0.22, beam * 0.8, 0.04), m=Matrix.Translation((xs, 0, depth * 0.65)), mat=seat_mat)


def build(rng, cfg: dict, mats: dict, root, shore_fn=None, practical_scale=1.0, lantern=True):
    L = cfg["length"]
    W = cfg["width"]
    dz = cfg["deck_z"]
    rx, ry, rz = root
    col = core.collection("Dock")

    wood = MeshBuilder()
    # deck planks across the dock, slightly irregular, a few missing/short
    y = ry + 1.5
    while y > ry - L:
        pw = rng.uniform(0.17, 0.22)
        if rng.random() > 0.03:
            sag = rng.uniform(-0.012, 0.0)
            wl = W * rng.uniform(0.97, 1.03)
            wood.box((wl, pw - 0.015, 0.05),
                     m=Matrix.Translation((rx + rng.uniform(-0.02, 0.02), y - pw / 2, dz + sag))
                     @ Matrix.Rotation(rng.uniform(-0.01, 0.01), 4, "Z"), mat=0)
        y -= pw
    # stringers + posts every 2.2 m (posts go 1.8 m below the water)
    for sx in (-1, 1):
        wood.box((0.12, L + 1.5, 0.18), m=Matrix.Translation((rx + sx * (W / 2 - 0.15), ry + 0.75 - L / 2, dz - 0.12)), mat=1)
    n_posts = int(L / 2.2) + 1
    for i in range(n_posts):
        py = ry - i * (L / (n_posts - 1))
        for sx in (-1, 1):
            p = (rx + sx * (W / 2 - 0.05), py, -1.8)
            wood.cylinder(dz + 2.3, 0.11, 0.1, segs=8, m=frame(p, (rng.uniform(-0.02, 0.02), 0, 1), up=(1, 0, 0)),
                          mat=1)
    # end bench / mooring cleats
    wood.box((W * 0.7, 0.4, 0.06), m=Matrix.Translation((rx, ry - L + 0.5, dz + 0.42)), mat=0)
    for sx in (-0.6, 0.6):
        wood.box((0.06, 0.35, 0.42), m=Matrix.Translation((rx + sx, ry - L + 0.5, dz + 0.21)), mat=1)
    wood_obj = wood.build("Dock_Wood", [mats["deck"], mats["log"]], smooth=False)

    objs = [wood_obj]
    boat_info = None
    if cfg.get("boat", True):
        bm = MeshBuilder()
        _boat(bm, mat=0, seat_mat=1)
        boat = bm.build("Dock_Boat", [mats["boat"], mats["deck"]], smooth=True)
        side = rng.choice((-1, 1))
        bx = rx + side * (W / 2 + 0.85)
        by = ry - L * rng.uniform(0.45, 0.75)
        boat.location = (bx, by, -0.18)
        boat.rotation_euler = (rng.uniform(-0.03, 0.03), rng.uniform(-0.04, 0.04),
                               math.pi / 2 + rng.uniform(-0.25, 0.25))
        objs.append(boat)
        boat_info = (bx, by)

    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)

    lights = []
    if lantern:
        lp = MeshBuilder()
        p = (rx + W / 2 - 0.15, ry - L + 0.2, dz)
        lp.cylinder(1.6, 0.05, segs=6, m=frame(p, (0, 0, 1), up=(1, 0, 0)), mat=0)
        lp.box((0.18, 0.18, 0.26), m=Matrix.Translation((p[0], p[1], dz + 1.75)), mat=1)
        lo = lp.build("Dock_LanternPost", [mats["log"], mats["lantern_glow"]], smooth=False)
        for c in list(lo.users_collection):
            c.objects.unlink(lo)
        col.objects.link(lo)
        objs.append(lo)
        lt = bpy.data.lights.new("DockLantern", "POINT")
        lt.energy = cfg.get("lantern_watts", 12) * practical_scale
        lt.color = core.kelvin_rgb(2100)
        lt.shadow_soft_size = 0.06
        o = bpy.data.objects.new("DockLantern", lt)
        o.location = (p[0], p[1], dz + 1.75)
        col.objects.link(o)
        lights.append(o)

    end = (rx, ry - L, dz)
    pts = [(rx + sx * (W / 2 + 0.3), yy, z) for sx in (-1, 1) for yy in (ry, ry - L) for z in (-0.2, dz + 1.9)]
    if boat_info:
        pts += [(boat_info[0], boat_info[1] + d, z) for d in (-1.8, 1.8) for z in (-0.2, 0.5)]
    return {
        "objects": objs, "collection": "Dock", "bbox_points": pts,
        "center": (rx, ry - L * 0.55, 0.8), "height": dz + 2.2, "base_z": 0.0,
        "end": end, "root": root,
        "footprint": (rx - W / 2 - 2.0, rx + W / 2 + 2.0, ry - L - 0.6, ry + 1.6),
    }
