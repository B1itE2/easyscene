"""Orchestrator: validated spec -> complete Blender scene -> render -> post -> manifest.

Build order matters for reproducibility and for layout rules:
terrain -> subject -> camera -> light -> forest (avoids the camera's view)
-> undergrowth -> atmosphere. Each step draws from its own seeded stream.
"""

import hashlib
import json
import math
import platform
import subprocess
import time
from pathlib import Path

import bpy

from . import (__version__, assets, atmosphere, budget, camera, core, lighting, materials,
               post, recipes, scatter)
from . import rng as rngmod
from .modeling import cabin, forest, terrain, vegetation


class BudgetError(RuntimeError):
    pass


def log(msg):
    print(f"[cinescene] {msg}", flush=True)


def _git_rev(root):
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def build_scene(spec: dict):
    """Create the full scene in the current Blender session. Returns a context dict."""
    t0 = time.time()
    seed = spec["seed"]
    recipe_raw = recipes.load(spec["style"])
    R = recipes.resolve(recipe_raw, rngmod.stream(seed, "recipe"))
    q = budget.QUALITY[spec["quality"]]

    scene = core.reset()
    core.setup_units(scene)
    core.setup_color(scene)
    rinfo = core.setup_render(scene, spec["quality"], spec["camera"]["aspect"], seed)
    log(f"render {rinfo['width']}x{rinfo['height']} {rinfo['samples']} spp on {rinfo['device']}")

    # ---- assets (CC0) with procedural fallback ------------------------------
    res = q["texture_res"]
    tex = {}
    for role, tid in R["assets"]["textures"].items():
        tex[role] = assets.fetch_texture(tid, res, role=role)
        if tex[role] is None:
            log(f"texture {tid} unavailable -> procedural {role}")
    hdri = assets.fetch_hdri(R["assets"]["hdri"], "1k" if spec["quality"] != "final" else "2k")
    mats = materials.library(tex)

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
    cs = spec["camera"]
    cam_obj = camera.create(lens=cs["lens_mm"])
    solved = camera.solve_static(cab, T, cs, R["camera"])
    camera.apply_static(cam_obj, solved, R["camera"]["fstop"])
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
        for x, y in edge["trunk"]:
            tpts.append((x, y, T.height(x, y) - 0.15, 0, 0, dress_rng.uniform(0, math.tau),
                         1.0, fc["variants"]))      # the bare snag: a trunk, not a wall of needles
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
                            lambda x, y: under_keep(x, y) or sight(x, y),
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
    atmosphere.height_fog(tc["size_m"] - 4, 75.0, R["fog"], fog_d)
    if sub["chimney_smoke"]:
        atmosphere.chimney_smoke(cab["chimney_top"], R["smoke"], seed)
    atmosphere.set_time(3.0)

    layout = {
        "subject": {k2: cab[k2] for k2 in ("center", "height", "footprint", "chimney_top",
                                           "bbox_points", "door", "eave", "ridge")},
        "camera": solved, "trees": [(round(p[0], 3), round(p[1], 3), round(p[6], 3)) for p in tpts],
        "sun_dir": linfo["sun_dir"],
    }
    scene["cinescene_layout"] = json.dumps(layout)
    log(f"scene built in {time.time() - t0:.1f}s: {len(tpts)} trees, {len(gpts)} grass, "
        f"{len(fpts)} ferns, {len(rpts)} rocks")
    return {"recipe": R, "recipe_raw": recipe_raw, "render": rinfo, "lighting": linfo,
            "layout": layout, "camera_obj": cam_obj, "build_seconds": time.time() - t0}


def check_budget(ctx, frames=1, force=False):
    tris, inst = core.scene_stats()
    bpx, fpx = core.image_pixels()
    r = ctx["render"]
    mem = budget.estimate_memory_gb(tris, inst, bpx, fpx, r["width"], r["height"])
    secs, guessed = budget.estimate_seconds(r["width"], r["height"], r["samples"], frames)
    info = {"unique_tris": tris, "instances": inst, "texture_mpx": round(bpx / 1e6, 1),
            "est_memory_gb": round(mem, 2), "mem_limit_gb": budget.DEFAULT_MEM_LIMIT_GB,
            "est_seconds": round(secs), "estimate_is_guess": guessed}
    log(f"budget: {tris:,} unique tris, {inst:,} instances, {info['texture_mpx']} MPx textures "
        f"-> ~{mem:.1f} GB (limit {budget.DEFAULT_MEM_LIMIT_GB} GB), "
        f"~{secs / 60:.1f} min{' (rough guess, not calibrated yet)' if guessed else ''}")
    if mem > budget.DEFAULT_MEM_LIMIT_GB and not force:
        raise BudgetError(f"estimated {mem:.1f} GB exceeds the {budget.DEFAULT_MEM_LIMIT_GB} GB "
                          "safety line. Use --quality draft, or render on the desktop "
                          "(see docs/DESKTOP.md), or pass --force.")
    return info


def render_still(ctx, out: Path, spec: dict):
    scene = bpy.context.scene
    raw = out / "still_raw.png"
    scene.render.filepath = str(raw)
    t = time.time()
    bpy.ops.render.render(write_still=True)
    secs = time.time() - t
    r = ctx["render"]
    budget.record_timing(r["width"], r["height"], r["samples"], secs)
    log(f"rendered still in {secs:.1f}s -> {raw}")
    final = out / "still.png"
    post.grade_still(raw, final, ctx["recipe"]["post"], spec["seed"])
    return {"raw": str(raw), "final": str(final), "render_seconds": round(secs, 1)}


def write_manifest(out: Path, spec, ctx, extra):
    root = Path(__file__).resolve().parent.parent
    recipe_hash = hashlib.sha256(json.dumps(ctx["recipe_raw"], sort_keys=True).encode()).hexdigest()[:12]
    lic = assets.ledger_records()
    manifest = {
        "cinescene_version": __version__, "git_rev": _git_rev(root),
        "blender_version": bpy.app.version_string, "platform": platform.platform(),
        "created_unix": int(time.time()),
        "spec": spec, "seed": spec["seed"], "recipe_sha256_12": recipe_hash,
        "resolved_recipe": ctx["recipe"], "render": ctx["render"], "lighting": ctx["lighting"],
        "camera": ctx["layout"]["camera"], "build_seconds": round(ctx["build_seconds"], 1),
        "assets": lic, **extra,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    lines = ["# Asset licenses", "",
             "All third-party assets are CC0-1.0 (public domain) from Poly Haven.",
             "Everything else in this scene is procedurally generated by cinescene.", ""]
    lines += [f"- **{a.get('name', a['id'])}** (`{a['id']}`, {a.get('role')}) — {a['license']} — "
              f"{', '.join(a.get('authors', [])) or 'Poly Haven'} — {a['source']}" for a in lic]
    (out / "ASSET_LICENSES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
