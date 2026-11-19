"""Style: rainforest waterfall (雨林瀑布). Still image only.

Gorge -> waterfall sheet -> camera on the near bank -> light from above and
behind the falls (shafts through the canopy gap) -> plunge pool -> jungle
trees on the rims, ferns and broadleaf plants on the banks, mossy boulders ->
spray mist at the base + humid haze that shows the light shafts.
"""

import math
import time

from mathutils import Vector

from .. import atmosphere, camera, lighting, materials, scatter, water
from .. import rng as rngmod
from ..modeling import deciduous, gorge, vegetation
from ..nodes import NB


def log(msg):
    print(f"[cinescene] {msg}", flush=True)


def build(spec, R, q, mats, tex, hdri):
    t0 = time.time()
    seed = spec["seed"]
    gc = R["gorge"]
    G = gorge.Gorge(rngmod.stream(seed, "terrain"), size=gc["size_m"], resolution=gc["resolution"],
                    pool_r=gc["pool_r"], cliff_y=gc["cliff_y"], cliff_h=gc["cliff_h"], width=gc["width"])
    w_rng = rngmod.stream(seed, "waterfall")
    fall, base, top = gorge.waterfall(G, w_rng.uniform(-2.0, 2.0), gc["fall_width"], w_rng)

    # ---- camera on the near bank ---------------------------------------------------
    cs = spec["camera"]
    c_rng = rngmod.stream(seed, "camera")
    cam_obj = camera.create(lens=cs["lens_mm"], clip_end=800.0)
    cx = c_rng.uniform(-4.0, 4.0)
    cy = G.py - gc["pool_r"] - R["camera"]["back_m"]
    loc = Vector((cx, cy, G.height(cx, cy) + R["camera"]["eye_height_m"]))
    target = Vector((base[0], base[1], top * R["camera"]["aim_frac"]))
    cam_obj.location = loc
    camera.look_at(cam_obj, target)
    cam_obj.data.dof.use_dof = True
    cam_obj.data.dof.focus_distance = (target - loc).length
    cam_obj.data.dof.aperture_fstop = R["camera"]["fstop"]
    solved = {"location": tuple(loc), "target": tuple(target), "shift_x": 0.0,
              "focus": (target - loc).length, "yaw": camera.yaw_of(tuple(target - loc)),
              "lens": cs["lens_mm"], "aspect": cs["aspect"]}

    G.build(materials.jungle_ground(tex.get("rock"), tex.get("moss_ground")))
    linfo = lighting.apply(R["lighting_by_time"][spec["time_of_day"]], solved["yaw"], hdri,
                           R.get("lighting_overrides", {}).get(spec["time_of_day"]))
    water.calm_water("Pool", 300.0, level=-0.15, deep=(0.01, 0.03, 0.025), ripple=0.35)

    # ---- jungle on the rims and banks ----------------------------------------------------
    hfov, _ = camera.fovs(cs["lens_mm"], cs["aspect"])
    sight = camera.keep_out_view(solved, 4.0, 3.0, hfov * 0.55)
    f_rng = rngmod.stream(seed, "forest")
    tvars = deciduous.variants(f_rng, 6, R["forest"]["height_range_m"], mats)
    tcol = scatter.variant_collection("TreeVariants", tvars)
    pts = []
    for x, y in rngmod.poisson_disk(f_rng, 160, 160, R["forest"]["min_spacing_m"], origin=(0, 20)):
        h = G.height(x, y)
        if h < 1.5 or G.normal(x, y).z < 0.6:                 # only on rims and gentle banks
            continue
        if abs(x - base[0]) < gc["fall_width"] * 0.8 and y > gc["cliff_y"] - 4 and y < gc["cliff_y"] + 10:
            continue                                            # keep the lip of the falls open
        if (Vector((x, y, 0)) - Vector((loc.x, loc.y, 0))).length < 3.0:
            continue
        if sight(x, y):                                         # nothing between us and the falls
            continue
        pts.append((x, y, h - 0.3, 0, 0, f_rng.uniform(0, math.tau), f_rng.uniform(0.8, 1.3),
                    f_rng.randrange(len(tvars))))
    scatter.scatter("Forest", pts, tcol)

    u_rng = rngmod.stream(seed, "undergrowth")

    def on_bank(x, y):
        h = G.height(x, y)
        if (Vector((x, y, 0)) - Vector((loc.x, loc.y, 0))).length < 1.5:
            return True
        return not (0.0 < h < 30.0 and G.normal(x, y).z > 0.35)    # slopes too: jungle drapes them

    fern_v = vegetation.load_model("fern_02", "fern", max_objects=2, max_size=1.4) or \
        [vegetation.fern(u_rng, mats, f"Fern{i}") for i in range(3)]
    fpts = vegetation.place_clustered(u_rng, R["undergrowth"]["ferns"], (gc["pool_r"] - 1, 45), G,
                                      on_bank, len(fern_v), per_cluster=(4, 12), spread=1.4, scale=(0.9, 1.8),
                                      center=(0.0, G.py))
    # foreground: a dense fern bank around the camera's feet frames the bottom edge
    fwd = (target - loc).normalized()
    for _ in range(int(R["undergrowth"]["ferns"] * 0.12)):
        d = u_rng.uniform(6.0, 16.0)
        side = u_rng.uniform(-1.0, 1.0) * d * 0.8
        x = loc.x + fwd.x * d - fwd.y * side
        y = loc.y + fwd.y * d + fwd.x * side
        if abs(side) < d * 0.3:                                  # keep a window down the middle
            continue
        fpts.append((x, y, G.height(x, y), 0, 0, u_rng.uniform(0, math.tau), u_rng.uniform(1.2, 2.0),
                     u_rng.randrange(len(fern_v))))
    scatter.scatter("Ferns", fpts, scatter.variant_collection("FernVariants", fern_v))
    # procedural elephant-ear plants: the scanned leaf sets are flat (0.4 m tall) and vanish
    big_v = [vegetation.big_leaf_plant(u_rng, mats, f"BigLeaf{i}", size=u_rng.uniform(0.9, 1.4))
             for i in range(5)]
    fwd = (target - loc).normalized()
    if big_v:
        bpts = vegetation.place_clustered(u_rng, R["undergrowth"]["broadleaf"], (gc["pool_r"], 40), G,
                                          on_bank, len(big_v), per_cluster=(2, 6), spread=1.2,
                                          scale=(1.0, 2.0), center=(0.0, G.py))
        scatter.scatter("Broadleaf", bpts, scatter.variant_collection("BroadleafVariants", big_v))
    # the rock ledge we stand on, with big leaves at its lip that frame the bottom corners
    ledge_v = big_v[:] if big_v else fern_v[:]
    lpts = []
    right = Vector((fwd.y, -fwd.x, 0))
    for side in (-1, 1):
        for k in range(3):
            # we stand ~5 m up looking level: the frame's bottom edge meets the ground ~20 m out
            d = u_rng.uniform(19.0, 26.0)
            p = loc + fwd * d + right * side * d * u_rng.uniform(0.3, 0.42)
            lpts.append((p.x, p.y, G.height(p.x, p.y) - 0.05, 0, 0, u_rng.uniform(0, math.tau),
                         u_rng.uniform(1.8, 2.6), u_rng.randrange(len(ledge_v))))
    scatter.scatter("LedgePlants", lpts, scatter.variant_collection("LedgeVariants", [o.copy() for o in ledge_v]))
    rock_v = vegetation.load_model("rock_moss_set_01", "rocks", max_objects=6, max_size=2.4) or \
        [vegetation.rock(u_rng, mats, f"Rock{i}") for i in range(5)]
    rpts = vegetation.place(u_rng, R["undergrowth"]["boulders"], (gc["pool_r"] * 0.7, gc["pool_r"] + 5), G,
                            lambda x, y: (Vector((x, y, 0)) - Vector((loc.x, loc.y, 0))).length < 2.5
                            or G.height(x, y) > 1.0,                     # boulders only at the water
                            len(rock_v), scale=(0.6, 1.6), sink=0.3, center=(0.0, G.py))
    scatter.scatter("Rocks", rpts, scatter.variant_collection("RockVariants", rock_v))

    # ---- humid haze + spray mist at the base of the falls ------------------------------
    fog_d = R["fog"]["density_by_weather"][spec["weather"]]
    fog_obj = atmosphere.height_fog(gc["size_m"] * 1.2, gc["cliff_h"] + 30, R["fog"], fog_d)
    _spray(fog_obj, base, R["spray"])

    layout = {
        "subject": {"center": (base[0], base[1], top / 2), "height": top,
                    "footprint": (base[0] - 3, base[0] + 3, base[1] - 1, base[1] + 2),
                    "bbox_points": [(base[0] + sx * gc["fall_width"] / 2, base[1], z)
                                    for sx in (-1, 1) for z in (0.0, top)],
                    "base_z": 0.0, "collection": "__none__"},
        "camera": solved, "trees": [(round(p[0], 3), round(p[1], 3), round(p[6], 3)) for p in pts],
        "sun_dir": linfo["sun_dir"],
    }
    log(f"style built in {time.time() - t0:.1f}s: {len(pts)} trees, {len(fpts)} ferns, {len(rpts)} boulders")
    cyaw = solved["yaw"] + math.pi
    anchors = {"pool_edge": [(p[0], p[1], p[2] + 0.3, cyaw) for p in rpts[:3]],
               "ledge": [(loc.x + fwd.x * 2.0, loc.y + fwd.y * 2.0, G.height(loc.x + fwd.x * 2.0, loc.y + fwd.y * 2.0), cyaw)]}
    return {"layout": layout, "lighting": linfo, "camera_obj": cam_obj, "shot": None, "terrain": G,
            "anchors": anchors}


def _spray(fog_obj, base, cfg):
    """Dense white spray where the water hits the pool, added into the fog shader."""
    mat = fog_obj.data.materials[0]
    nb = NB(mat.node_tree, clear=False)
    p = nb.vmath("SUBTRACT", nb.coord("Object"), tuple(base))
    x, y, z = nb.sep(p)
    r = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", x, x), nb.math("MULTIPLY", y, y)))
    radial = nb.maprange(r, 0.0, cfg["radius_m"], 1.0, 0.0, interp="SMOOTHSTEP")
    vert = nb.math("EXPONENT", nb.math("DIVIDE", nb.math("MAXIMUM", z, 0.0), -cfg["height_m"]))
    puff = nb.maprange(nb.noise(p, scale=0.6, detail=4.0), 0.35, 0.7, 0.2, 1.3)
    dens = nb.math("MULTIPLY", nb.math("MULTIPLY", radial, vert), nb.math("MULTIPLY", puff, cfg["density"]))
    svol = nb.new("ShaderNodeVolumePrincipled", inputs={"Color": (0.95, 0.97, 0.98), "Anisotropy": 0.4})
    nb.set(svol, "Density", dens)
    out = [n for n in nb.nodes if n.bl_idname == "ShaderNodeOutputMaterial"][0]
    prev = out.inputs["Volume"].links[0].from_socket
    add = nb.new("ShaderNodeAddShader")
    nb.links.new(prev, add.inputs[0])
    nb.links.new(svol.outputs[0], add.inputs[1])
    nb.links.new(add.outputs[0], out.inputs["Volume"])
