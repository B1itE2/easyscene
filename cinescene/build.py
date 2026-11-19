"""Orchestrator: validated spec -> complete Blender scene -> render -> post -> manifest.

Generic for every style: scene foundation, assets, materials, budget,
still/animation rendering, encoding and the manifest. What the scene
*contains* is decided by ``cinescene.styles.<style>.build``.
"""

import hashlib
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path

import bpy

from . import __version__, assets, atmosphere, budget, core, materials, post, recipes, styles
from . import rng as rngmod


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
    hdri = assets.fetch_hdri(R["assets"]["hdri"], q["texture_res"])
    mats = materials.library(tex)

    style = styles.get(spec["style"])
    res = style.build(spec, R, q, mats, tex, hdri)
    layout = res["layout"]
    shot = res["shot"]
    if shot is not None:
        shot.apply(res["camera_obj"], R["camera"]["fstop"])
        atmosphere.key_time(shot.fps, 1, shot.frames)
        layout["motion"] = shot.stats()
        log(f"motion {shot.preset}: {layout['motion']}")
    else:
        atmosphere.set_time(3.0)
    scene["cinescene_layout"] = json.dumps(layout)
    log(f"scene built in {time.time() - t0:.1f}s")
    return {"recipe": R, "recipe_raw": recipe_raw, "render": rinfo, "lighting": res["lighting"],
            "layout": layout, "camera_obj": res["camera_obj"], "shot": shot,
            "terrain": res.get("terrain"),
            "build_seconds": time.time() - t0}


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


def render_still(ctx, out: Path, spec: dict, frame=None):
    """Render one frame (default: the last frame of a move = the hero composition)."""
    scene = bpy.context.scene
    if ctx.get("shot") is not None:
        scene.frame_set(frame if frame is not None else scene.frame_end)
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


def render_animation(ctx, out: Path, spec: dict, step=1):
    """Render the frame sequence (every ``step``-th frame), then MP4 + contact sheet."""
    scene = bpy.context.scene
    frames_dir = out / "frames"
    frames_dir.mkdir(exist_ok=True)
    for old in frames_dir.glob("f_*.png"):
        old.unlink()
    scene.render.filepath = str(frames_dir / "f_####")
    scene.frame_step = step
    scene.render.use_persistent_data = True      # keep BVH between frames: only the camera moves
    t = time.time()
    bpy.ops.render.render(animation=True)
    secs = time.time() - t
    n = len(list(frames_dir.glob("f_*.png")))
    r = ctx["render"]
    budget.record_timing(r["width"], r["height"], r["samples"], secs / max(n, 1))
    log(f"rendered {n} frames in {secs / 60:.1f} min ({secs / max(n, 1):.1f} s/frame)")
    res = {"frames_dir": str(frames_dir), "frames": n, "frame_step": step,
           "render_seconds": round(secs, 1)}
    # sequential numbering for ffmpeg when frames were skipped
    files = sorted(frames_dir.glob("f_*.png"))
    seq = out / "_seq"
    seq.mkdir(exist_ok=True)
    for old in seq.glob("*.png"):
        old.unlink()
    for i, f in enumerate(files):
        dst = seq / f"s_{i:04d}.png"
        try:
            dst.symlink_to(f.resolve())
        except OSError:                       # Windows without developer mode: copy instead
            shutil.copyfile(f, dst)
    fps = max(1, round(ctx["shot"].fps / step))
    name = spec["quality"]
    video = out / (f"{name}.mp4" if step == 1 else f"{name}_step{step}.mp4")
    try:
        post.encode_video(seq / "s_%04d.png", video, fps, ctx["recipe"]["post"], spec["seed"])
        post.contact_sheet(seq / "s_%04d.png", out / "sheet.png", n)
        res.update({"video": str(video), "sheet": str(out / "sheet.png")})
    except RuntimeError as e:                 # frames are safe on disk; video can be made later
        log(f"video encoding skipped: {e}")
    return res


def run_checks(ctx, out: Path, still_path=None):
    """Scene + render checks -> out/checks.json. Returns the summary."""
    from . import checks
    scene_c, geo = checks.scene_checks(ctx["layout"], ctx.get("terrain"))
    allc = list(scene_c)
    if still_path:
        allc += checks.render_checks(still_path, ctx["recipe"]["checks"], geo["subject_area"])
    summ = checks.summarize(allc)
    summ["geometry"] = geo
    checks.write(out / "checks.json", summ)
    for c in allc:
        log(f"check {'PASS' if c['ok'] else 'FAIL'} {c['id']}: {c['value']} (limit {c['limit']})"
            + (f"  -> {c['hint']}" if c["hint"] else ""))
    log(f"checks: {'ALL PASSED' if summ['passed'] else 'FAILED ' + ', '.join(summ['failed'])}")
    return summ


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
        "camera": ctx["layout"]["camera"], "motion": ctx["layout"].get("motion"),
        "build_seconds": round(ctx["build_seconds"], 1),
        "assets": lic, **extra,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    lines = ["# Asset licenses", "",
             "All third-party assets are CC0-1.0 (public domain) from Poly Haven.",
             "Everything else in this scene is procedurally generated by cinescene.", ""]
    lines += [f"- **{a.get('name', a['id'])}** (`{a['id']}`, {a.get('role')}) — {a['license']} — "
              f"{', '.join(a.get('authors', [])) or 'Poly Haven'} — {a['source']}" for a in lic]
    (out / "ASSET_LICENSES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
