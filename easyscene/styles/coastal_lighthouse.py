"""Style: coastal lighthouse at sunset (海边灯塔).

Build order: headland -> lighthouse -> hero camera on the plateau (looking
across the tower toward the low sun) -> orbit move -> light -> ocean with
shore foam -> grass + rocks on the plateau -> thin sea haze. The sun is put
*behind and beside* the tower relative to the camera so the tower gets a
warm rim and the sea a glittering sun path.
"""

import math
import time

from mathutils import Vector

from .. import atmosphere, camera, lighting, motion, scatter, water
from .. import rng as rngmod
from ..modeling import coast, lighthouse, vegetation


def log(msg):
    print(f"[easyscene] {msg}", flush=True)


def build(spec, R, q, mats, tex, hdri):
    t0 = time.time()
    seed = spec["seed"]

    hc = R["headland"]
    T = coast.Headland(rngmod.stream(seed, "terrain"), size=hc["size_m"], resolution=hc["resolution"],
                       top=hc["top_m"], radius=hc["radius_m"], sea_floor=hc["sea_floor_m"],
                       ruggedness=hc["ruggedness"])

    preset = R["lighting_by_time"][spec["time_of_day"]]
    pscale = lighting.PRESETS[preset]["practical_scale"]
    z0 = T.height(0.0, 0.0)
    lh = lighthouse.build(rngmod.stream(seed, "lighthouse"), R["lighthouse"], mats, z0,
                          practical_scale=pscale, beam=spec["time_of_day"] in ("dusk", "night", "dawn"))

    # ---- hero camera: on the plateau edge-ish, tower against the sky --------------
    cs = dict(spec["camera"])
    mv = spec["motion"]
    if mv["preset"] != "none":
        cs["composition"] = "center"
    cc = dict(R["camera"])
    cc["min_z"] = z0 + cc["above_plateau_m"]
    cam_obj = camera.create(lens=cs["lens_mm"], clip_end=8000.0)
    solved = camera.solve_static(lh, T, cs, cc)
    camera.apply_static(cam_obj, solved, cc["fstop"])
    hfov, _ = camera.fovs(cs["lens_mm"], cs["aspect"])

    shot = None
    if mv["preset"] != "none":
        shot = motion.plan(mv["preset"], {"subject": {"center": lh["center"]}, "camera": solved}, T,
                           R["motion"][mv["preset"]], mv["duration_s"], mv["fps"])

    # ---- terrain + light ------------------------------------------------------------
    from .. import materials
    gmat = materials.coast_ground(tex.get("grass"), tex.get("rock"), hc["top_m"])
    T.build(gmat)
    linfo = lighting.apply(preset, solved["yaw"], hdri,
                           R.get("lighting_overrides", {}).get(spec["time_of_day"]))

    # ---- ocean with foam where the sea meets the cliffs ---------------------------------
    oc = R["ocean"]
    shore = water.shore_mask(T.height, hc["size_m"], res=512, reach=R["ocean"].get("surf_reach_m", 30.0))
    sea, far = water.ocean(seed, oc, shore=shore)
    water.set_time(sea, 3.0, oc["time_speed"])

    # ---- plateau grass + scattered rocks -----------------------------------------------
    u_rng = rngmod.stream(seed, "undergrowth")
    fx0, fx1, fy0, fy1 = lh["footprint"]
    cx, cy, _ = solved["location"]
    vc = R["vegetation"]

    def keep(x, y):
        if fx0 - 0.5 < x < fx1 + 0.5 and fy0 - 0.5 < y < fy1 + 0.5:
            return True
        if T.inside(x, y) < 1.5 or T.normal(x, y).z < 0.85:      # only on flat plateau
            return True
        return math.hypot(x - cx, y - cy) < 2.0

    grass_v = [vegetation.grass_clump(u_rng, mats, f"Grass{i}") for i in range(6)]
    gpts = vegetation.place_clustered(u_rng, vc["grass_clumps"], (3.0, 70.0), T, keep, 6,
                                      per_cluster=(10, 30), spread=1.2, scale=(0.8, 1.6))
    scatter.scatter("Grass", gpts, scatter.variant_collection("GrassVariants", grass_v))
    rock_v = [vegetation.rock(u_rng, mats, f"Rock{i}") for i in range(5)]
    sight = camera.keep_out_view(solved, 0.0, 2.0, hfov)
    rpts = vegetation.place(u_rng, vc["rocks"], (6.0, 70.0), T, lambda x, y: keep(x, y) or sight(x, y),
                            5, scale=(0.4, 1.1), sink=0.1)
    scatter.scatter("Rocks", rpts, scatter.variant_collection("RockVariants", rock_v))

    # ---- thin sea haze ----------------------------------------------------------------
    fog_d = R["fog"]["density_by_weather"][spec["weather"]]
    atmosphere.height_fog(hc["size_m"] * 2.5, 120.0, R["fog"], fog_d)

    if shot is not None:
        # beams sweep with the shot; ocean keeps moving
        piv = lh["pivot"]
        if piv is not None:
            for f, ang in ((1, 0.0), (shot.frames, math.tau * shot.frames / mv["fps"] / 8.0)):
                piv.rotation_euler = (0, 0, ang)
                piv.keyframe_insert("rotation_euler", frame=f)
        water.key_time(sea, mv["fps"], 1, shot.frames, oc["time_speed"])
        shot.info["min_ground_clearance_m"] = round(shot.min_ground_clearance(T), 2)
    elif lh["pivot"] is not None:
        # still: aim one beam across the frame (from camera's right toward the sea)
        lh["pivot"].rotation_euler = (0, 0, solved["yaw"] + math.radians(-35))

    layout = {
        "subject": {k: lh[k] for k in ("center", "height", "footprint", "bbox_points", "base_z")},
        "camera": solved, "trees": [], "sun_dir": linfo["sun_dir"],
    }
    log(f"style built in {time.time() - t0:.1f}s: {len(gpts)} grass, {len(rpts)} rocks")
    cyaw = solved["yaw"] + math.pi
    r0 = R["lighthouse"]["base_radius"]
    a = -math.pi / 2
    anchors = {
        "door": [(math.cos(a) * (r0 + 1.0) + 0.6, math.sin(a) * (r0 + 1.0), z0, cyaw),
                 (math.cos(a) * (r0 + 1.0) - 0.6, math.sin(a) * (r0 + 1.0), z0, cyaw)],
        "cliff_edge": [],
    }
    for k in range(24):                                   # first flat spot near the edge, camera side
        ang = solved["yaw"] + math.pi + (k - 12) * 0.05
        for rr in range(30, 4, -1):
            x, y = math.cos(ang + math.pi / 2) * rr, math.sin(ang + math.pi / 2) * rr
            if T.inside(x, y) > 3.0 and T.normal(x, y).z > 0.9:
                anchors["cliff_edge"].append((x, y, T.height(x, y), cyaw))
                break
        if len(anchors["cliff_edge"]) >= 2:
            break
    return {"layout": layout, "lighting": linfo, "camera_obj": cam_obj, "shot": shot, "terrain": T,
            "ocean": sea, "anchors": anchors}
