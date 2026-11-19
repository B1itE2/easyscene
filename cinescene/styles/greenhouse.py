"""Style: greenhouse / conservatory (温室花房). Still image only (no camera move).

The camera stands just inside the door looking down the central aisle:
benches of potted plants on both sides, hanging baskets, a tall palm and an
iron bench at the far end, soft daylight diffused through the glass roof.
"""

import math
import time

import bpy
from mathutils import Vector

from .. import atmosphere, camera, lighting, scatter
from .. import rng as rngmod
from ..modeling import deciduous, greenhouse, vegetation
from ..modeling.mesh import MeshBuilder, frame


def log(msg):
    print(f"[cinescene] {msg}", flush=True)


class Flat:
    """Flat lawn around the glasshouse (terrain API for checks/camera)."""
    path = None

    def height(self, x, y):
        return 0.0

    def flatten_segment(self, *_a, **_k):
        pass


def _pot(rng, mats, name, r):
    mb = MeshBuilder()
    h = r * rng.uniform(1.0, 1.3)
    mb.cylinder(h, r * 0.75, r, segs=14, m=frame((0, 0, 0), (0, 0, 1), up=(1, 0, 0)), mat=0)
    mb.cylinder(0.04, r * 1.08, r * 1.08, segs=14, m=frame((0, 0, h - 0.04), (0, 0, 1), up=(1, 0, 0)), mat=0)
    mb.cylinder(0.01, r * 0.95, segs=14, m=frame((0, 0, h - 0.03), (0, 0, 1), up=(1, 0, 0)), mat=1)
    return mb.build(name, [mats["terracotta"], mats["soil"]], link=False), h - 0.03


def build(spec, R, q, mats, tex, hdri):
    t0 = time.time()
    seed = spec["seed"]
    T = Flat()
    gc = R["greenhouse"]
    gh = greenhouse.build(rngmod.stream(seed, "greenhouse"), gc, mats)
    W, L, H = gh["size"]

    # lawn outside
    lawn = MeshBuilder()
    lawn.box((200, 200, 0.1), m=__import__("mathutils").Matrix.Translation((0, 0, -0.06)))
    lawn.build("Terrain", [mats["lawn"]], smooth=False)

    # ---- camera in the doorway ------------------------------------------------
    cs = spec["camera"]
    cam_obj = camera.create(lens=cs["lens_mm"], clip_end=500.0)
    c_rng = rngmod.stream(seed, "camera")
    loc = Vector((c_rng.uniform(-0.25, 0.25), -L / 2 + R["camera"]["inside_m"], R["camera"]["eye_height_m"]))
    target = Vector((gh["center"][0] + c_rng.uniform(-0.3, 0.3), gh["center"][1], R["camera"]["aim_z"]))
    cam_obj.location = loc
    camera.look_at(cam_obj, target)
    cam_obj.data.lens = cs["lens_mm"]
    cam_obj.data.dof.use_dof = True
    cam_obj.data.dof.focus_distance = (target - loc).length * 0.55
    cam_obj.data.dof.aperture_fstop = R["camera"]["fstop"]
    solved = {"location": tuple(loc), "target": tuple(target), "shift_x": 0.0,
              "focus": (target - loc).length, "yaw": camera.yaw_of(tuple(target - loc)),
              "lens": cs["lens_mm"], "aspect": cs["aspect"]}

    linfo = lighting.apply(R["lighting_by_time"][spec["time_of_day"]], solved["yaw"], hdri,
                           R.get("lighting_overrides", {}).get(spec["time_of_day"]))

    # ---- plants -----------------------------------------------------------------
    p_rng = rngmod.stream(seed, "plants")
    models = []
    for mid, size, own_pot in R["plants"]["models"]:
        models += [(o, size, own_pot) for o in
                   vegetation.load_model(mid, "plant", max_objects=3, max_size=size, join=own_pot)]
    if not models:
        log("plant models unavailable -> procedural shrubs")
        models = [(deciduous.tree(p_rng, 0.6, mats, name=f"PotShrub{i}"), 0.6, False) for i in range(3)]
    pots = []
    for i in range(4):
        o, top = _pot(p_rng, mats, f"Pot{i}", p_rng.uniform(0.09, 0.16))
        pots.append((o, top))
    # each bench spot: a pot + a plant on top of it
    pot_pts, plant_pts = [], []
    for (x, y, z) in gh["bench_spots"]:
        if p_rng.random() < R["plants"]["empty_ratio"]:
            continue
        m = p_rng.randrange(len(models))
        ps = p_rng.uniform(0.85, 1.2)
        if models[m][2]:                              # model brings its own pot
            plant_pts.append((x, y, z, 0, 0, p_rng.uniform(0, math.tau), ps, m))
            continue
        ps *= 1.35                                    # small plants: fill their pot
        k = p_rng.randrange(len(pots))
        s = p_rng.uniform(0.75, 1.0)
        pot_pts.append((x, y, z, 0, 0, p_rng.uniform(0, math.tau), s, k))
        plant_pts.append((x, y, z + pots[k][1] * s - 0.02, 0, 0, p_rng.uniform(0, math.tau), ps, m))
    scatter.scatter("Pots", pot_pts, scatter.variant_collection("PotVariants", [p[0] for p in pots]))
    scatter.scatter("Plants", plant_pts, scatter.variant_collection("PlantVariants", [m[0] for m in models]))

    # ferns and leafy ground cover in the gravel beds under the benches
    fern_v = vegetation.load_model("fern_02", "fern", max_objects=2, max_size=0.9) or \
        [vegetation.fern(p_rng, mats, f"Fern{i}") for i in range(2)]
    under = []
    aw = gc["aisle_width"]
    for _ in range(R["plants"]["under_bench"]):
        sx = p_rng.choice((-1, 1))
        x = sx * p_rng.uniform(aw / 2 + 0.3, W / 2 - 0.4)
        y = p_rng.uniform(-L / 2 + 1.0, L / 2 - 2.6)
        under.append((x, y, 0.04, 0, 0, p_rng.uniform(0, math.tau), p_rng.uniform(0.6, 1.0),
                      p_rng.randrange(len(fern_v))))
    scatter.scatter("UnderFerns", under, scatter.variant_collection("UnderFernVariants", fern_v))

    # hanging baskets from the roof purlins: pot + trailing fern
    hang_pts, hang_plants = [], []
    for (x, y, z) in gh["hanging"]:
        if p_rng.random() < 0.3 or (Vector((x, y, z)) - loc).length < 3.5:
            continue
        hz = z - p_rng.uniform(0.6, 1.0)
        hang_pts.append((x, y, hz, 0, 0, 0, 1.0, 0))
        hang_plants.append((x, y, hz - 0.05, math.pi, 0, p_rng.uniform(0, math.tau), 0.8,
                            p_rng.randrange(len(fern_v))))
    hb = MeshBuilder()
    hb.cylinder(0.14, 0.12, 0.17, segs=12, m=frame((0, 0, -0.14), (0, 0, 1), up=(1, 0, 0)))
    hb.cylinder(1.0, 0.004, segs=4, m=frame((0, 0, 0), (0, 0, 1), up=(1, 0, 0)))
    basket = hb.build("Basket", [mats["terracotta"]], link=False)
    scatter.scatter("Baskets", [(p[0], p[1], p[2] + 0.14, 0, 0, 0, 1.0, 0) for p in hang_pts],
                    scatter.variant_collection("BasketVariants", [basket]))
    scatter.scatter("Trailing", hang_plants,
                    scatter.variant_collection("TrailingVariants", [o.copy() for o in fern_v]))

    # the tall palm at the far end (a big plant model, else a procedural tree)
    big = vegetation.load_model(R["plants"]["hero"], "plant", max_objects=1, max_size=3.8)
    if big:
        palm = big[0]
        bpy.context.scene.collection.objects.link(palm)
        palm.location = gh["palm_spot"]
        palm.rotation_euler.z = p_rng.uniform(0, math.tau)

    # ---- faint humid haze (light shafts through the glass) ----------------------------
    fog_d = R["fog"]["density_by_weather"][spec["weather"]]
    atmosphere.height_fog(max(W, L) * 1.4, H + 4.0, R["fog"], fog_d)

    layout = {
        "subject": {"center": gh["center"], "height": gh["height"], "footprint": gh["footprint"],
                    "bbox_points": gh["bbox_points"], "base_z": 0.0, "collection": "Greenhouse"},
        "camera": solved, "trees": [], "sun_dir": linfo["sun_dir"],
    }
    log(f"style built in {time.time() - t0:.1f}s: {len(plant_pts)} potted plants, {len(under)} ferns")
    cyaw = solved["yaw"] + math.pi
    anchors = {
        "aisle": [(0.25 * s_, -L / 2 + d_, 0.06, cyaw) for d_, s_ in ((3.5, 1), (6.0, -1), (8.5, 1))],
        "bench": [(x, y, z, cyaw) for (x, y, z) in gh["bench_spots"][2:40:9]],
        "end": [(-0.9, gh["center"][1] - 0.6, 0.0, cyaw), (0.9, gh["center"][1] - 0.6, 0.0, cyaw)],
    }
    return {"layout": layout, "lighting": linfo, "camera_obj": cam_obj, "shot": None, "terrain": T,
            "anchors": anchors}
