"""Style: autumn lakeside dock (湖边秋日码头).

Build order: lake shore -> dock (from the shoreline out over the water) ->
hero camera low over the water -> water_skim move -> light -> calm water ->
autumn forest on the banks (deciduous + some conifers) -> shore rocks,
floating leaves -> mist that hugs the water surface.
"""

import math
import time

from .. import atmosphere, camera, lighting, materials, motion, scatter, water
from .. import rng as rngmod
from ..modeling import deciduous, dock, forest, lake, vegetation


def log(msg):
    print(f"[easyscene] {msg}", flush=True)


def build(spec, R, q, mats, tex, hdri):
    t0 = time.time()
    seed = spec["seed"]
    lc = R["lake"]
    T = lake.LakeShore(rngmod.stream(seed, "terrain"), size=lc["size_m"], resolution=lc["resolution"],
                       bay=lc["bay"], hills=lc["hills"], depth=lc["depth"])

    preset = R["lighting_by_time"][spec["time_of_day"]]
    over = R.get("lighting_overrides", {}).get(spec["time_of_day"])
    pscale = lighting.PRESETS[preset]["practical_scale"]
    root = (0.0, T.shore_y(0.0) + 0.6, 0.0)
    dk = dock.build(rngmod.stream(seed, "dock"), R["dock"], mats, root, practical_scale=pscale,
                    lantern=spec["subject"]["lights_on"])

    # ---- camera -------------------------------------------------------------
    cs = dict(spec["camera"])
    mv = spec["motion"]
    if mv["preset"] != "none":
        cs["composition"] = "center"
    cc = dict(R["camera"])
    cam_obj = camera.create(lens=cs["lens_mm"], clip_end=3000.0)
    solved = camera.solve_static(dk, T, cs, cc)
    camera.apply_static(cam_obj, solved, cc["fstop"])
    hfov, _ = camera.fovs(cs["lens_mm"], cs["aspect"])
    shot = None
    if mv["preset"] != "none":
        shot = motion.plan(mv["preset"], {"subject": {"center": dk["center"]}, "camera": solved}, T,
                           R["motion"][mv["preset"]], mv["duration_s"], mv["fps"])

    gmat = materials.lake_ground(tex.get("land"), tex.get("shore"))
    T.build(gmat)
    linfo = lighting.apply(preset, solved["yaw"], hdri, over)
    lake_obj = water.calm_water("Lake", 3000.0, level=0.0, deep=(0.006, 0.014, 0.012), ripple=0.04)

    # ---- autumn forest on the banks --------------------------------------------
    fc = R["forest"]
    f_rng = rngmod.stream(seed, "forest.variants")
    autumn = deciduous.variants(f_rng, fc["autumn_variants"], fc["height_range_m"], mats)
    conif_cfg = dict(fc, height_range_m=fc["conifer_height_m"], variants=fc["conifer_variants"])
    conifers = forest.variants(seed, conif_cfg, mats, fc["conifer_variants"])[:fc["conifer_variants"]]
    tvars = autumn + conifers
    tcol = scatter.variant_collection("TreeVariants", tvars)
    p_rng = rngmod.stream(seed, "forest.place")
    pts = rngmod.poisson_disk(p_rng, fc["extent_m"], fc["extent_m"], fc["min_spacing_m"],
                              origin=(0.0, fc["extent_m"] / 2 - 20))
    fx0, fx1, fy0, fy1 = dk["footprint"]
    tpts = []
    for x, y in pts:
        s = T.signed(x, y) + p_rng.uniform(-2.5, 2.5)
        if not (fc["band_m"][0] < s < fc["band_m"][1]):
            continue
        if fx0 - 3 < x < fx1 + 3 and y < fy1 + 6:          # keep the dock's landing clear
            continue
        conifer = p_rng.random() < fc["conifer_ratio"]
        vid = len(autumn) + p_rng.randrange(len(conifers)) if conifer else p_rng.randrange(len(autumn))
        tpts.append((x, y, T.height(x, y) - 0.2, p_rng.uniform(-0.04, 0.04), p_rng.uniform(-0.04, 0.04),
                     p_rng.uniform(0, math.tau), p_rng.uniform(0.8, 1.2), vid))
    scatter.scatter("Forest", tpts, tcol)

    # ---- shore detail -----------------------------------------------------------
    u_rng = rngmod.stream(seed, "undergrowth")

    def bank(lo, hi):
        def keep(x, y):
            s = T.signed(x, y)
            return not (lo < s < hi) or (fx0 - 0.5 < x < fx1 + 0.5 and y < fy1 + 1.0)
        return keep

    rock_v = [vegetation.rock(u_rng, mats, f"Rock{i}") for i in range(5)]
    rpts = vegetation.place(u_rng, 120, (2.0, 90.0), T, bank(-1.5, 1.5), 5, scale=(0.2, 0.7), sink=0.05)
    scatter.scatter("Rocks", rpts, scatter.variant_collection("RockVariants", rock_v))
    # low autumn shrubs along the bank hide the bare trunk line
    shrub_v = [deciduous.tree(u_rng, u_rng.uniform(1.6, 2.8), mats, name=f"Shrub{i}") for i in range(4)]
    spts = vegetation.place_clustered(u_rng, 260, (2.0, 90.0), T, bank(0.8, 6.0), 4,
                                      per_cluster=(2, 6), spread=1.6, scale=(0.8, 1.4))
    scatter.scatter("Shrubs", spts, scatter.variant_collection("ShrubVariants", shrub_v))
    grass_v = [vegetation.grass_clump(u_rng, mats, f"Grass{i}") for i in range(5)]
    gpts = vegetation.place_clustered(u_rng, 5000, (2.0, 80.0), T, bank(0.3, 12.0), 5,
                                      per_cluster=(6, 20), scale=(1.0, 1.8))
    scatter.scatter("Grass", gpts, scatter.variant_collection("GrassVariants", grass_v))
    # leaves floating on the water near the shore
    leaf_v = [vegetation.leaf_rosette(u_rng, mats, f"Floating{i}") for i in range(3)]
    for o in leaf_v:
        o.data.materials[0] = mats["autumn_leaf"]
        for v in o.data.vertices:
            v.co.z = 0.0
    lpts = vegetation.place_clustered(u_rng, 900, (1.0, 60.0), T, bank(-8.0, -0.5), 3,
                                      per_cluster=(4, 14), spread=1.5, scale=(1.0, 2.0))
    lpts = [(p[0], p[1], 0.005) + p[3:] for p in lpts]
    scatter.scatter("FloatingLeaves", lpts, scatter.variant_collection("FloatLeafVariants", leaf_v))

    # ---- mist on the water --------------------------------------------------------
    fog_d = R["fog"]["density_by_weather"][spec["weather"]]
    atmosphere.height_fog(lc["size_m"] * 1.6, 40.0, R["fog"], fog_d)

    if shot is not None:
        shot.info["min_height_m"] = round(min(c.z for c in shot.positions), 2)
        n0 = len(tpts)
    layout = {
        "subject": dict({k: dk[k] for k in ("center", "height", "footprint", "bbox_points", "base_z",
                                             "collection")}, water_level=0.0),
        "camera": solved, "trees": [(round(p[0], 3), round(p[1], 3), round(p[6], 3)) for p in tpts],
        "sun_dir": linfo["sun_dir"],
    }
    log(f"style built in {time.time() - t0:.1f}s: {len(tpts)} trees, {len(rpts)} rocks, "
        f"{len(lpts)} floating leaves")
    cyaw = solved["yaw"] + math.pi
    ex, ey, ez = dk["end"]
    rx, ry, _ = dk["root"]
    anchors = {
        "dock_end": [(ex - 0.4, ey + 1.1, ez + 0.03, cyaw), (ex + 0.4, ey + 1.3, ez + 0.03, cyaw)],
        "dock": [(rx + 0.3, (ry + ey) / 2, ez + 0.03, cyaw)],
        "shore": [(rx + 2.5, ry + 1.5, T.height(rx + 2.5, ry + 1.5), cyaw),
                  (rx - 2.5, ry + 1.5, T.height(rx - 2.5, ry + 1.5), cyaw)],
    }
    return {"layout": layout, "lighting": linfo, "camera_obj": cam_obj, "shot": shot, "terrain": T,
            "anchors": anchors}
