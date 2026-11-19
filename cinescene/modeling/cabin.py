"""Log cabin: stacked round logs with crossed corners, gable roof, stone chimney.

Coordinates: cabin centred at origin, front (door, gable) faces -Y.
Openings cut real gaps in the logs so interior light spills out of windows
into the fog. Everything is seeded: log wobble, firewood, plank jitter.
"""

import math

import bpy
from mathutils import Matrix, Vector

from .. import core
from .mesh import MeshBuilder, frame


def _subtract(interval, holes):
    """[a,b] minus a list of [h0,h1] -> list of remaining intervals."""
    segs = [interval]
    for h0, h1 in holes:
        nxt = []
        for a, b in segs:
            if h1 <= a or h0 >= b:
                nxt.append((a, b))
                continue
            if h0 > a:
                nxt.append((a, h0))
            if h1 < b:
                nxt.append((h1, b))
        segs = nxt
    return [(a, b) for a, b in segs if b - a > 0.18]


def build(rng, cfg: dict, size: str, mats: dict, practical_scale=1.0, lights_on=True,
          chimney_side=1):
    """chimney_side: +1 = chimney on the +X wall, -1 = on the -X wall (face it to the camera)."""
    dims = cfg[size]
    W, D, N = dims["width"], dims["depth"], dims["rows"]
    r, s = cfg["log_radius"], cfg["row_step"]
    pitch = math.radians(cfg["roof_pitch_deg"])
    z0 = 0.35                                   # top of stone foundation
    H = z0 + r + (N - 1) * s + r                # eave height
    zr = H + (W / 2) * math.tan(pitch)          # ridge (underside of roof)
    over = 0.32                                 # log ends past the corners

    # openings per wall: (a0, a1, z0, z1) with a = coordinate along the wall axis
    openings = {
        "front": [(-1.55, -0.55, z0 - 0.1, z0 + 2.0, "door"),
                  (0.75, 1.95, z0 + 0.85, z0 + 1.85, "window"),
                  (-0.42, 0.42, H + 0.35, H + 1.10, "window")],
        "back": [(-0.55, 0.55, z0 + 0.9, z0 + 1.75, "window")],
        "left": [(-0.65, 0.65, z0 + 0.85, z0 + 1.8, "window")],
        "right": [(-0.65, 0.65, z0 + 0.85, z0 + 1.8, "window")],
    }
    openings["right" if chimney_side > 0 else "left"] = []   # chimney wall has no window
    walls = {  # name: (axis dir, fixed coord, half length incl. overhang, row phase)
        "front": ((1, 0, 0), (0, -D / 2), W / 2, 0.0),
        "back": ((1, 0, 0), (0, D / 2), W / 2, 0.0),
        "left": ((0, 1, 0), (-W / 2, 0), D / 2, 0.5),
        "right": ((0, 1, 0), (W / 2, 0), D / 2, 0.5),
    }

    logs = MeshBuilder()
    for name, (axis, fixed, half, phase) in walls.items():
        gable = name in ("front", "back")
        k = 0
        while True:
            zc = z0 + r + (k + phase) * s
            if not gable and k >= N - 1 + (0 if phase else 1):
                break
            if gable and zc + r > zr - 0.05:
                break
            if zc + r <= H + 0.01:
                lo, hi = -half - over, half + over
            else:  # gable triangle: shorten logs to stay under the roof
                hl = (zr - (zc + r)) / math.tan(pitch)
                if hl < 0.25:
                    break
                lo, hi = -hl, hl
            holes = [(a0, a1) for a0, a1, oz0, oz1, _ in openings[name]
                     if zc + r * 0.6 > oz0 and zc - r * 0.6 < oz1]
            for a, b in _subtract((lo, hi), holes):
                start = Vector((a, fixed[1], zc)) if axis[0] else Vector((fixed[0], a, zc))
                m = frame(start, axis)
                rr = r * rng.uniform(0.93, 1.07)
                wob = [rng.uniform(0.96, 1.04) for _ in range(5 * 12)]
                bend_amt = rng.uniform(-0.015, 0.015)
                logs.cylinder(b - a, rr, rr * rng.uniform(0.92, 1.0), segs=12, rings=4, m=m,
                              jitter=lambda i, j, w=wob: w[i * 12 + j],
                              bend=lambda t, ba=bend_amt: (0.0, ba * math.sin(t * math.pi)),
                              uv_scale=1.0)
            k += 1
    logs_obj = logs.build("Cabin_Logs", [mats["log"]])

    # ---- roof ---------------------------------------------------------------
    roof = MeshBuilder()
    ov_eave, ov_gable, t = 0.55, 0.55, 0.14
    L = (W / 2 + ov_eave) / math.cos(pitch)
    for sgn in (-1, 1):
        d = Vector((sgn * math.cos(pitch), 0, -math.sin(pitch)))
        m = frame((0, 0, zr), d)
        nrm = Vector((m[0][2], m[1][2], m[2][2]))
        c = Vector((0, 0, zr)) + d * (L / 2) + nrm * (t / 2 + 0.01)
        mm = frame(c, d)
        roof.box((L, D + 2 * ov_gable, t), m=mm, uv_scale=1.0)
    roof_obj = roof.build("Cabin_Roof", [mats["roof"]], smooth=False)
    trim = MeshBuilder()  # bargeboards + ridge log give a crisp silhouette
    for yy in (-D / 2 - ov_gable, D / 2 + ov_gable):
        for sgn in (-1, 1):
            d = Vector((sgn * math.cos(pitch), 0, -math.sin(pitch)))
            c = Vector((0, yy, zr)) + d * (L / 2) + Vector((0, 0, 0.02))
            trim.box((L, 0.06, 0.26), m=frame(c, d))
    trim.cylinder(D + 2 * ov_gable + 0.1, 0.11, segs=10,
                  m=frame((0, -D / 2 - ov_gable - 0.05, zr + t + 0.04), (0, 1, 0)))
    trim_obj = trim.build("Cabin_Trim", [mats["plank"]])

    # ---- stone: foundation + chimney ---------------------------------------
    stone = MeshBuilder()
    for (cx, cy, sx, sy) in ((0, -D / 2, W + 0.5, 0.55), (0, D / 2, W + 0.5, 0.55),
                             (-W / 2, 0, 0.55, D), (W / 2, 0, 0.55, D)):
        stone.box((sx, sy, z0 + 0.45), m=Matrix.Translation((cx, cy, (z0 - 0.45) / 2)))
    chim_x, chim_y = chimney_side * (W / 2 + 0.7), 0.4
    chim_top = zr + 0.6
    base_top = H - 0.6
    stone.box((1.5, 1.7, base_top + 0.3), m=Matrix.Translation((chim_x, chim_y, (base_top - 0.3) / 2)))
    shoulder = Matrix.Translation((chim_x, chim_y, base_top + 0.25))
    stone.box((1.25, 1.35, 0.5), m=shoulder)
    stone.box((0.9, 0.95, chim_top - base_top),
              m=Matrix.Translation((chim_x, chim_y, (chim_top + base_top) / 2)))
    stone.box((1.08, 1.12, 0.12), m=Matrix.Translation((chim_x, chim_y, chim_top + 0.06)))
    stone_obj = stone.build("Cabin_Stone", [mats["stone"]], smooth=False)

    # ---- frames, door, porch, firewood ------------------------------------
    wood = MeshBuilder()
    glass = MeshBuilder()
    curtain = MeshBuilder()
    windows = []
    for name, ops in openings.items():
        axis, fixed, _, _ = walls[name]
        out_n = {"front": (0, -1, 0), "back": (0, 1, 0), "left": (-1, 0, 0), "right": (1, 0, 0)}[name]
        for a0, a1, oz0, oz1, kind in ops:
            ac, w_, h_ = (a0 + a1) / 2, a1 - a0, oz1 - oz0
            centre = Vector((ac, fixed[1], 0)) if axis[0] else Vector((fixed[0], ac, 0))
            m_wall = frame(centre, axis)  # local x along wall, local y across wall
            depth = 2 * r + 0.06
            bw = 0.09
            parts = [((-w_ / 2 - bw / 2, 0, (oz0 + oz1) / 2), (bw, depth, h_ + 2 * bw)),
                     ((w_ / 2 + bw / 2, 0, (oz0 + oz1) / 2), (bw, depth, h_ + 2 * bw)),
                     ((0, 0, oz1 + bw / 2), (w_ + 2 * bw, depth, bw))]
            if kind == "window":
                parts.append(((0, 0, oz0 - bw / 2), (w_ + 2 * bw, depth + 0.08, bw)))
                parts.append(((0, 0, (oz0 + oz1) / 2), (w_, 0.05, 0.04)))     # mullion bars
                parts.append(((0, 0, (oz0 + oz1) / 2), (0.04, 0.05, h_)))
                g = m_wall @ Matrix.Translation((0, 0, (oz0 + oz1) / 2))
                glass.box((w_, 0.01, h_), m=g)
                # half-drawn warm curtains just inside
                inward = -Vector(out_n) * (r + 0.12)
                for side in (-1, 1):
                    cw = w_ * rng.uniform(0.22, 0.32)
                    cm = Matrix.Translation(inward) @ m_wall @ Matrix.Translation(
                        (side * (w_ / 2 - cw / 2 + 0.02), 0, (oz0 + oz1) / 2 + 0.03))
                    curtain.box((cw, 0.015, h_ + 0.1), m=cm)
                wc = m_wall @ Vector((0, 0, (oz0 + oz1) / 2))
                windows.append({"wall": name, "center": tuple(wc), "normal": out_n,
                                "size": (w_, h_)})
            else:  # door leaf, slightly recessed
                parts.append(((0, 0.04, (oz0 + 0.1 + oz1) / 2 - 0.05), (w_, 0.06, h_ - 0.1)))
            for (px, py, pz), sz in parts:
                wood.box(sz, m=m_wall @ Matrix.Translation((px, py, pz)))
    # porch deck in front of the door
    plank_w = 0.16
    x = -2.55
    while x < 0.35:
        wood.box((plank_w - 0.012, 1.55, 0.05),
                 m=Matrix.Translation((x + plank_w / 2, -D / 2 - 0.95, z0 - 0.03 + rng.uniform(-0.006, 0.006))))
        x += plank_w
    wood.box((1.3, 0.35, 0.18), m=Matrix.Translation((-1.05, -D / 2 - 1.9, 0.09)))  # step
    wood_obj = wood.build("Cabin_Wood", [mats["plank"]], smooth=False)
    glass_obj = glass.build("Cabin_Glass", [mats["glass"]], smooth=False)
    glass_obj.visible_shadow = False   # let interior light pass the panes
    curtain_obj = curtain.build("Cabin_Curtains", [mats["curtain"]], smooth=False)

    fw = MeshBuilder()  # firewood stack along the left wall
    for row in range(8):
        y = -1.6
        while y < 1.6:
            rr = rng.uniform(0.055, 0.085)
            fx = (-W / 2 - 0.95) if chimney_side > 0 else (W / 2 + 0.47)   # opposite the chimney
            m = frame((fx + rng.uniform(-0.03, 0.03), y,
                       0.05 + rr + row * 0.14),
                      (1, rng.uniform(-0.04, 0.04), 0))
            fw.cylinder(0.48, rr, segs=7, m=m)
            y += 2 * rr + 0.012
    fw_obj = fw.build("Cabin_Firewood", [mats["firewood"]])

    floor = MeshBuilder()
    floor.box((W - 0.2, D - 0.2, 0.06), m=Matrix.Translation((0, 0, z0 + 0.03)))
    floor_obj = floor.build("Cabin_Floor", [mats["deck"]], smooth=False)

    objs = [logs_obj, roof_obj, trim_obj, stone_obj, wood_obj, glass_obj, curtain_obj,
            fw_obj, floor_obj]
    col = core.collection("Cabin")
    for o in objs:
        for c in o.users_collection:
            c.objects.unlink(o)
        col.objects.link(o)

    # ---- practical lights --------------------------------------------------
    lights = []
    if lights_on:
        warm = core.kelvin_rgb(cfg["window_temp_k"])
        for name, pos, watts, rad in (
                ("Interior_Main", (0.3, 0.2, z0 + 1.7), cfg["interior_watts"], 0.25),
                ("Interior_Window", (1.3, -D / 2 + 0.9, z0 + 1.3), cfg["interior_watts"] * 0.4, 0.15),
                ("Interior_Loft", (0.0, -D / 2 + 0.8, H + 0.6), cfg["interior_watts"] * 0.3, 0.15),
                ("Interior_Side", (-chimney_side * (W / 2 - 0.9), 0.0, z0 + 1.3), cfg["interior_watts"] * 0.3, 0.15)):
            L_ = bpy.data.lights.new(name, "POINT")
            L_.energy = watts * practical_scale
            L_.color = warm
            L_.shadow_soft_size = rad
            o = bpy.data.objects.new(name, L_)
            o.location = pos
            col.objects.link(o)
            lights.append(o)
        # porch lantern
        lan = bpy.data.lights.new("Lantern", "POINT")
        lan.energy = cfg["lantern_watts"] * practical_scale
        lan.color = core.kelvin_rgb(2100)
        lan.shadow_soft_size = 0.05
        o = bpy.data.objects.new("Lantern", lan)
        o.location = (-0.3, -D / 2 - 0.3, z0 + 1.95)
        col.objects.link(o)
        lights.append(o)

    pts = [Vector((x, y, z)) for x in (-W / 2 - 0.6, W / 2 + 1.0) for y in (-D / 2 - 0.6, D / 2 + 0.6)
           for z in (0.0, zr + 0.3)] + [Vector((chim_x, chim_y, chim_top))]
    return {
        "objects": objs, "lights": lights, "bbox_points": [tuple(p) for p in pts],
        "center": (0.0, 0.0, (zr + 0.3) * 0.45), "height": zr + 0.3,
        "footprint": (-W / 2 - 1.5, W / 2 + 1.5, -D / 2 - 2.2, D / 2 + 0.8),
        "chimney_top": (chim_x, chim_y, chim_top + 0.12), "windows": windows,
        "door": (-1.05, -D / 2, z0), "eave": H, "ridge": zr,
    }
