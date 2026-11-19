"""Victorian-style glasshouse: white steel frame, gabled glass roof, benches of plants.

Origin at the centre of the floor; the long axis runs along +Y, the door is at
-Y. The camera stands in the doorway looking down the central aisle, so the
"subject" is the display at the far end (a tall palm and an iron bench).
"""

import math

import bpy
from mathutils import Matrix, Vector

from .. import core
from .mesh import MeshBuilder, frame


def build(rng, cfg: dict, mats: dict):
    W, L, H = cfg["width"], cfg["length"], cfg["wall_height"]
    pitch = math.radians(cfg["roof_pitch_deg"])
    ridge = H + (W / 2) * math.tan(pitch)
    bay = cfg["bay_m"]
    col = core.collection("Greenhouse")

    frm = MeshBuilder()
    glass = MeshBuilder()
    n_bays = max(2, int(round(L / bay)))
    bay = L / n_bays
    t = cfg["bar"]
    ys = [-L / 2 + i * bay for i in range(n_bays + 1)]
    # ---- portal frames (posts + rafters) every bay ------------------------------
    for y in ys:
        for sx in (-1, 1):
            frm.box((t, t, H), m=Matrix.Translation((sx * W / 2, y, H / 2)))
            d = Vector((-sx * math.cos(pitch), 0, math.sin(pitch)))
            Lr = (W / 2) / math.cos(pitch)
            c = Vector((sx * W / 2, y, H)) + d * (Lr / 2)
            frm.box((Lr, t, t), m=frame(c, d))
    # eaves, ridge, base beams, mullions and purlins
    for sx in (-1, 1):
        frm.box((t, L, t), m=Matrix.Translation((sx * W / 2, 0, H)))
        frm.box((t * 1.5, L, 0.45), m=Matrix.Translation((sx * W / 2, 0, 0.225)))     # low brick sill
        for k in range(1, 3):
            frm.box((t * 0.6, L, t * 0.6), m=Matrix.Translation((sx * W / 2, 0, H * k / 3)))
        for k in (1, 2):
            f = k / 3
            p = Vector((sx * W / 2 * (1 - f), 0, H + (ridge - H) * f))
            frm.box((t * 0.6, L, t * 0.6), m=Matrix.Translation(p))
    frm.box((t * 1.4, L, t * 1.4), m=Matrix.Translation((0, 0, ridge)))
    # roof ridge cresting (decorative finials)
    for y in ys:
        frm.cylinder(0.35, 0.03, 0.01, segs=6, m=frame((0, y, ridge), (0, 0, 1), up=(1, 0, 0)))
    # gable ends: verticals + door opening at -Y
    door_w = cfg["door_width"]
    for yend in (-L / 2, L / 2):
        for k in range(-3, 4):
            x = k * W / 7
            top = H + (W / 2 - abs(x)) * math.tan(pitch)
            if yend < 0 and abs(x) < door_w / 2 + 0.01:
                frm.box((t * 0.6, t * 0.6, top - 2.3), m=Matrix.Translation((x, yend, 2.3 + (top - 2.3) / 2)))
                continue
            frm.box((t * 0.6, t * 0.6, top), m=Matrix.Translation((x, yend, top / 2)))
        frm.box((W, t * 0.6, t * 0.6), m=Matrix.Translation((0, yend, H)))
    frm.box((door_w, t, t), m=Matrix.Translation((0, -L / 2, 2.3)))
    frame_obj = frm.build("GH_Frame", [mats["frame"]], smooth=False)

    # ---- glass skin (thin, light passes: no shadows) ------------------------------
    g = 0.01
    for sx in (-1, 1):
        glass.box((g, L, H - 0.45), m=Matrix.Translation((sx * W / 2, 0, 0.45 + (H - 0.45) / 2)))
        d = Vector((-sx * math.cos(pitch), 0, math.sin(pitch)))
        Lr = (W / 2) / math.cos(pitch)
        c = Vector((sx * W / 2, 0, H)) + d * (Lr / 2)
        glass.box((Lr, L, g), m=frame(c, d))
    for yend in (-L / 2, L / 2):
        b = glass.add_verts([(-W / 2, yend, H), (W / 2, yend, H), (0, yend, ridge)])
        glass.add_face((b, b + 1, b + 2), ((0, 0), (1, 0), (0.5, 1)))
        if yend > 0:
            glass.box((W, g, H), m=Matrix.Translation((0, yend, H / 2)))
        else:
            for sx in (-1, 1):
                wpart = W / 2 - door_w / 2
                glass.box((wpart, g, H), m=Matrix.Translation((sx * (door_w / 2 + wpart / 2), yend, H / 2)))
            glass.box((door_w, g, H - 2.3), m=Matrix.Translation((0, yend, 2.3 + (H - 2.3) / 2)))
    glass_obj = glass.build("GH_Glass", [mats["glass"]], smooth=False)
    glass_obj.visible_shadow = False

    # ---- floor: central aisle tiles, gravel beds under benches ------------------------
    floor = MeshBuilder()
    floor.box((cfg["aisle_width"], L, 0.06), m=Matrix.Translation((0, 0, 0.03)), mat=0)
    for sx in (-1, 1):
        w = W / 2 - cfg["aisle_width"] / 2
        floor.box((w, L, 0.04), m=Matrix.Translation((sx * (cfg["aisle_width"] / 2 + w / 2), 0, 0.02)), mat=1)
    floor_obj = floor.build("GH_Floor", [mats["tiles"], mats["gravel"]], smooth=False)

    # ---- benches along both sides ------------------------------------------------
    bench = MeshBuilder()
    bw = W / 2 - cfg["aisle_width"] / 2 - 0.25
    bh = cfg["bench_height"]
    spots = []
    for sx in (-1, 1):
        bx = sx * (cfg["aisle_width"] / 2 + 0.1 + bw / 2)
        y0, y1 = -L / 2 + 1.2, L / 2 - 2.8
        bench.box((bw, y1 - y0, 0.05), m=Matrix.Translation((bx, (y0 + y1) / 2, bh)), mat=0)
        for yy in [y0 + i * (y1 - y0) / 6 for i in range(7)]:
            for dx in (-bw / 2 + 0.05, bw / 2 - 0.05):
                bench.box((0.05, 0.05, bh), m=Matrix.Translation((bx + dx, yy, bh / 2)), mat=1)
        y = y0 + 0.3
        while y < y1 - 0.2:
            for row in range(2 if bw > 1.0 else 1):
                spots.append((bx + (row - 0.5) * bw * 0.45 if bw > 1.0 else bx, y + rng.uniform(-0.08, 0.08), bh + 0.03))
            y += rng.uniform(0.32, 0.48)
    bench_obj = bench.build("GH_Benches", [mats["bench_wood"], mats["frame"]], smooth=False)

    # far-end display: iron bench and a planter for the tall palm
    disp = MeshBuilder()
    yd = L / 2 - 1.4
    bx = -1.9
    disp.box((1.4, 0.45, 0.06), m=Matrix.Translation((bx, yd - 0.4, 0.45)), mat=0)
    disp.box((1.4, 0.06, 0.45), m=Matrix.Translation((bx, yd - 0.18, 0.7)), mat=0)
    for dx in (-0.6, 0.6):
        disp.box((0.05, 0.4, 0.45), m=Matrix.Translation((bx + dx, yd - 0.4, 0.22)), mat=0)
    disp.cylinder(0.75, 0.65, 0.55, segs=16, m=frame((0.0, yd + 0.2, 0.0), (0, 0, 1), up=(1, 0, 0)), mat=1)
    disp_obj = disp.build("GH_Display", [mats["frame"], mats["terracotta"]], smooth=True)

    objs = [frame_obj, glass_obj, floor_obj, bench_obj, disp_obj]
    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)

    hang = [(sx * (cfg["aisle_width"] / 2 - 0.1), y, H - 0.2) for sx in (-1, 1) for y in ys[1:-1:2]]
    palm_spot = (0.0, yd + 0.2, 0.72)        # centred at the end of the aisle: the focal point
    pts = [(x, yd + dy, z) for x in (-2.0, 1.8) for dy in (-0.4, 0.4) for z in (0.0, 3.2)]
    return {
        "objects": objs, "collection": "Greenhouse", "bbox_points": pts,
        "center": (0.0, yd, 1.6), "height": 3.2, "base_z": 0.0,
        "footprint": (-W / 2 - 0.3, W / 2 + 0.3, -L / 2 - 0.3, L / 2 + 0.3),
        "bench_spots": spots, "hanging": hang, "palm_spot": palm_spot,
        "door": (0.0, -L / 2), "ridge": ridge, "size": (W, L, H),
    }
