"""Style: foggy forest cabin (雾气森林小木屋).

Build order matters for reproducibility and for layout rules:
terrain -> subject -> final camera -> camera move -> light -> forest (kept out
of the view and the route) -> undergrowth -> atmosphere. Each step draws
from its own seeded stream, so changing one layer never moves another.
"""

import math
import time

from .. import atmosphere, camera, lighting, materials, motion, scatter
from .. import rng as rngmod
from ..modeling import cabin, forest, terrain, vegetation


def log(msg):
    print(f"[cinescene] {msg}", flush=True)


def _tree_dims(obj):
    """(height, crown radius, crown base) of a tree variant mesh, for route clearance."""
    vs = obj.data.vertices
    h = max(v.co.z for v in vs)
    cr = max((v.co.x ** 2 + v.co.y ** 2) ** 0.5 for v in vs)
    crown = [obj.data.vertices[i].co.z for p in obj.data.polygons if p.material_index == 1
             for i in p.vertices]
    return h, cr, (min(crown) if crown else h)


def build(spec, R, q, mats, tex, hdri):
    """Populate the (already reset) scene. Returns layout, lighting, camera, shot."""
    t0 = time.time()
    seed = spec["seed"]
    # ---- terrain ------------------------------------------------------------
    tc = R["terrain"]
    T = terrain.Terrain(rngmod.stream(seed, "terrain"), size=tc["size_m"],
                        resolution=tc["resolution"], clearing=tc["clearing_radius_m"],
                        hills=tc["hill_amplitude_m"], back_slope=tc["back_slope"])

    # ---- subject ------------------------------------------------------------
    preset = R["lighting_by_time"][spec["time_of_day"]]
    pscale = lighting.PRESETS[preset]["practical_scale"]
    sub = spec["subject"]
    cab = cabin.build(rngmod.stream(seed, "cabin"), R["cabin"], sub["size"], mats,
                      practical_scale=pscale, lights_on=sub["lights_on"],
                      chimney_side=-1 if R["camera"]["view_azimuth_deg"][spec["camera"]["view"]] < 0 else 1)

    # ---- camera + light -----------------------------------------------------
    cs = dict(spec["camera"])
    mv = spec["motion"]
    if mv["preset"] != "none":
        cs["composition"] = "center"          # a move always lands with the subject centred
    cam_obj = camera.create(lens=cs["lens_mm"])
    solved = camera.solve_static(cab, T, cs, R["camera"])
    camera.apply_static(cam_obj, solved, R["camera"]["fstop"])
    shot = None
    cloud = None
    if mv["preset"] != "none":
        sub_layout = {"subject": {"center": cab["center"]}, "camera": solved}
        shot = motion.plan(mv["preset"], sub_layout, T, R["motion"][mv["preset"]],
                           mv["duration_s"], mv["fps"])
        if mv["preset"] == "cloud_descent":   # local cloud bank around the opening shot
            mc = R["motion"]["cloud_descent"]
            cloud = (shot.info["cloud_center_xy"], shot.positions[0].z - mc["cloud_below_start_m"],
                     mc["cloud_thickness_m"], mc["cloud_radius_m"], mc["cloud_density"])
    hfov, _ = camera.fovs(cs["lens_mm"], cs["aspect"])
    # footpath: from the door step to just beside the camera (a leading line into frame)
    uc = R["undergrowth"]
    p_rng = rngmod.stream(seed, "path")
    door = cab["door"]
    cl = solved["location"]
    fwd = (solved["target"][0] - cl[0], solved["target"][1] - cl[1])
    fl = math.hypot(*fwd)
    fwd = (fwd[0] / fl, fwd[1] / fl)
    right = (fwd[1], -fwd[0])
    side = -1 if solved["shift_x"] <= 0 else 1      # enter frame bottom, on the open side
    toward = (cl[0] + fwd[0] * 2.0 + right[0] * side * 0.8 + p_rng.uniform(-0.4, 0.4),
              cl[1] + fwd[1] * 2.0 + right[1] * side * 0.8 + p_rng.uniform(-0.4, 0.4))
    T.path = terrain.Path.from_door(p_rng, (door[0], door[1] - 2.1), toward,
                                    length=math.dist((door[0], door[1] - 2.1), toward) + 2,
                                    width=uc["path_width_m"])
    mats["ground"] = materials.ground(tex.get("ground"), tex.get("ground_b"), path=T.path,
                                      maps_path=tex.get("path"), clearing=tc["clearing_radius_m"])
    T.build(mats["ground"])              # after the camera flattened its sight line
    linfo = lighting.apply(preset, solved["yaw"], hdri)

    # ---- forest -------------------------------------------------------------
    fc = R["forest"]
    keep = camera.keep_out_view(solved, fc["clear_radius_m"], fc["camera_corridor_m"], hfov)
    tvars = forest.variants(seed, fc, mats, fc["variants"])
    crown = [max((v.co.x ** 2 + v.co.y ** 2) ** 0.5 for v in o.data.vertices) for o in tvars]
    tcol = scatter.variant_collection("TreeVariants", tvars)
    tpts = forest.place(seed, fc, T, keep, q["tree_density"])
    n0 = len(tpts)
    tpts = forest.thin_toward_sun(tpts, linfo["sun_dir"], seed, fc)
    log(f"opened a light window toward the sun: {n0 - len(tpts)} trees removed")
    if sub["chimney_smoke"]:   # keep crowns out of the plume so it reads against the sky
        bx0, bx1, by0, by1 = atmosphere.smoke_bounds(cab["chimney_top"], R["smoke"])
        n0 = len(tpts)
        tpts = [p for p in tpts if math.hypot(max(bx0 - p[0], 0, p[0] - bx1),
                                              max(by0 - p[1], 0, p[1] - by1)) > crown[p[7]] * p[6] + 0.3]
        log(f"removed {n0 - len(tpts)} trees whose crowns would reach the chimney smoke")
    dress_rng = rngmod.stream(seed, "dressing")
    edge = camera.frame_edge_points(solved, hfov, T, dress_rng)
    if R["camera"].get("foreground_dressing"):
        # frame-edge trunk: the variant with the highest crown base, so only a real spruce
        # trunk (bark + dead twigs) shows in frame and its needles stay above the top edge
        dims = [_tree_dims(o) for o in tvars[:fc["variants"]]]
        tall = max(range(len(dims)), key=lambda i: dims[i][2])
        for x, y in edge["trunk"]:
            tpts.append((x, y, T.height(x, y) - 0.15, 0, 0, dress_rng.uniform(0, math.tau),
                         1.0, tall))
    if shot is not None:
        n0 = len(tpts)
        tpts = shot.clear_trees(tpts, [_tree_dims(o) for o in tvars])
        log(f"camera route: cleared {n0 - len(tpts)} trees in its way")
    scatter.scatter("Forest", tpts, tcol)

    # ---- undergrowth --------------------------------------------------------
    u_rng = rngmod.stream(seed, "undergrowth")
    fx0, fx1, fy0, fy1 = cab["footprint"]
    cx, cy, _ = solved["location"]

    def solid_keep(x, y):   # cabin footprint and the spot the camera stands on
        return (fx0 - 0.3 < x < fx1 + 0.3 and fy0 - 0.3 < y < fy1 + 0.3) or \
            math.hypot(x - cx, y - cy) < 1.6

    def under_keep(x, y):   # plants also stay off the footpath
        return solid_keep(x, y) or T.path.dist(x, y) < T.path.width * 0.6

    k = q["undergrowth"]
    grass_v = [vegetation.grass_clump(u_rng, mats, f"Grass{i}") for i in range(6)]
    gpts = vegetation.place_clustered(u_rng, int(uc["grass_clumps"] * k), uc["radius_m"], T,
                                      under_keep, 6, scale=(0.6, 1.4),
                            weight=lambda x, y, d: 1.0 if d < 22 else 0.25)
    for x, y in edge["ground"]:
        gpts.append((x, y, T.height(x, y), 0, 0, u_rng.uniform(0, math.tau), 1.0, u_rng.randrange(6)))
    scatter.scatter("Grass", gpts, scatter.variant_collection("GrassVariants", grass_v))

    fern_v = vegetation.load_model(R["assets"]["models"]["fern"], "fern", max_objects=2,
                                                                       max_size=1.2) or \
        [vegetation.fern(u_rng, mats, f"Fern{i}") for i in range(3)]
    fpts = vegetation.place(u_rng, int(uc["ferns"] * k), (8.0, uc["radius_m"][1]), T, under_keep,
                            len(fern_v), scale=(0.6, 1.1),
                            weight=lambda x, y, d: 0.4 + 0.6 * min(1.0, (d - 8) / 10))
    for x, y in edge["ground"][::2]:
        fpts.append((x, y, T.height(x, y), 0, 0, u_rng.uniform(0, math.tau), 0.9,
                     u_rng.randrange(len(fern_v))))
    scatter.scatter("Ferns", fpts, scatter.variant_collection("FernVariants", fern_v))

    rock_v = vegetation.load_model(R["assets"]["models"]["rocks"], "rocks", max_objects=6,
                                                                        max_size=1.6) or \
        [vegetation.rock(u_rng, mats, f"Rock{i}") for i in range(5)]
    sight = camera.keep_out_view(solved, 0.0, 2.0, hfov)   # nothing solid in the sight line
    rpts = vegetation.place(u_rng, int(uc["rocks"] * k), (6.5, uc["radius_m"][1]), T,
                            lambda x, y: under_keep(x, y) or sight(x, y) or
                            math.hypot(x - cx, y - cy) < 8.0,        # no boulder in the near corner
                            len(rock_v), scale=(0.5, 1.3), sink=0.08)
    scatter.scatter("Rocks", rpts, scatter.variant_collection("RockVariants", rock_v))

    misc_v = [vegetation.fallen_log(u_rng, mats, f"Fallen{i}") for i in range(3)]
    misc_v += vegetation.load_model(R["assets"]["models"]["stump"], "stump", max_objects=1,
                                                                    max_size=1.0)
    mpts = vegetation.place(u_rng, uc["fallen_logs"], (12.0, 35.0), T,
                            lambda x, y: under_keep(x, y) or keep(x, y), 3, scale=(0.9, 1.1), sink=0.1)
    if len(misc_v) > 3:
        mpts += [(p[0], p[1], p[2], 0, 0, p[5], p[6], 3) for p in
                 vegetation.place(u_rng, 3, (8.0, 13.0), T, lambda x, y: under_keep(x, y) or keep(x, y),
                                  1, scale=(0.9, 1.2))]
    scatter.scatter("DeadWood", mpts, scatter.variant_collection("DeadWoodVariants", misc_v))

    # low ground cover: dense near the clearing edge, thinning out with distance
    leaf_v = [vegetation.leaf_rosette(u_rng, mats, f"Leaf{i}") for i in range(5)]
    lpts = vegetation.place_clustered(u_rng, int(uc["leaf_cover"] * k), (4.5, 35.0), T, under_keep,
                                      5, per_cluster=(8, 30), spread=0.9, scale=(0.7, 1.6),
                                      weight=lambda x, y, d: 1.0 if d < 18 else 0.5)
    scatter.scatter("LeafCover", lpts, scatter.variant_collection("LeafVariants", leaf_v))

    twig_v = [vegetation.twig(u_rng, mats, f"Twig{i}") for i in range(6)]
    wpts = vegetation.place(u_rng, int(uc["twigs"] * k), (4.0, 35.0), T,
                            solid_keep, 6, scale=(0.8, 1.3))
    scatter.scatter("Twigs", wpts, scatter.variant_collection("TwigVariants", twig_v))

    # moss cushions where moss really grows: tree bases, around rocks, along the foundation
    moss_v = [vegetation.moss_cushion(u_rng, mats, f"MossPad{i}") for i in range(5)]
    if moss_v:
        anchors = [(p[0], p[1], 0.6) for p in tpts if math.hypot(p[0], p[1]) < 40]
        anchors += [(p[0], p[1], 0.9 * p[6]) for p in rpts]
        anchors += [(x, y, 0.2) for x in (fx0 + 0.9, fx1 - 0.9) for y in (fy0 + 1.8, 0.0, fy1 - 0.5)]
        mpts2 = []
        for _ in range(int(uc["moss_patches"] * k)):
            ax, ay, ar = anchors[u_rng.randrange(len(anchors))]
            a = u_rng.uniform(0, math.tau)
            d = ar + abs(u_rng.gauss(0, 0.5))
            x, y = ax + math.cos(a) * d, ay + math.sin(a) * d
            if T.path.dist(x, y) < T.path.width * 0.6:
                continue
            mpts2.append((x, y, T.height(x, y) - 0.03, 0, 0, u_rng.uniform(0, math.tau),
                          u_rng.uniform(0.6, 1.5), u_rng.randrange(len(moss_v))))
        scatter.scatter("Moss", mpts2, scatter.variant_collection("MossVariants", moss_v))

    # ---- atmosphere ---------------------------------------------------------
    fog_d = R["fog"]["density_by_weather"][spec["weather"]]
    fog_top = 75.0
    if cloud is not None:
        _, cloud_bottom = atmosphere.cloud_bank(*cloud, R["fog"])
        fog_top = cloud_bottom - 0.5      # never coplanar: shared faces confuse the volume stack
    fog_obj = atmosphere.height_fog(tc["size_m"] - 4, fog_top, R["fog"], fog_d)
    if sub["chimney_smoke"]:
        atmosphere.chimney_smoke(fog_obj, cab["chimney_top"], R["smoke"], seed)

    if sub["chimney_smoke"] and shot is not None:
        bx = atmosphere.smoke_bounds(cab["chimney_top"], R["smoke"])
        z0 = cab["chimney_top"][2]
        shot.info["frames_in_smoke"] = shot.inside_box(bx, (z0, z0 + R["smoke"]["height_m"]))
        shot.info["min_ground_clearance_m"] = round(shot.min_ground_clearance(T), 2)

    layout = {
        "subject": {k2: cab[k2] for k2 in ("center", "height", "footprint", "chimney_top",
                                           "bbox_points", "door", "eave", "ridge")},
        "camera": solved, "trees": [(round(p[0], 3), round(p[1], 3), round(p[6], 3)) for p in tpts],
        "sun_dir": linfo["sun_dir"],
    }
    log(f"style built in {time.time() - t0:.1f}s: {len(tpts)} trees, {len(gpts)} grass, "
        f"{len(fpts)} ferns, {len(rpts)} rocks")
    dx, dy, dz = cab["door"]
    cyaw = solved["yaw"] + math.pi                       # props face the camera
    fx0_, fx1_, fy0_, fy1_ = cab["footprint"]
    pp = T.path.points
    anchors = {
        "porch": [(dx + 1.0, dy - 0.8, dz, cyaw), (dx + 0.3, dy - 1.2, dz, cyaw), (dx - 1.0, dy - 1.1, dz, cyaw)],
        "door": [(dx + 0.75, dy - 0.35, dz, cyaw)],
        "window": [(1.35, dy - 0.45, dz, cyaw)],
        # yard: in front of the cabin, beside the path, on the camera side (visible)
        "yard": [(x, y, T.height(x, y), cyaw) for x, y in ((dx + 2.6, dy - 2.6), (dx + 3.5, dy - 2.2),
                                                             (dx - 2.2, dy - 2.8))],
        "path": [(pp[2][0] + 0.9, pp[2][1], T.height(pp[2][0] + 0.9, pp[2][1]), cyaw),
                 (pp[3][0] - 0.9, pp[3][1], T.height(pp[3][0] - 0.9, pp[3][1]), cyaw)],
    }
    return {"layout": layout, "lighting": linfo, "camera_obj": cam_obj, "shot": shot, "terrain": T,
            "anchors": anchors}
