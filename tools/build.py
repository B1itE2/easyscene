"""Entry point, run inside Blender:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/build.py -- \
        --spec examples/foggy_cabin_morning.json --quality preview

Outputs go to out/<spec.name>/ unless --out is given.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="tools/build.py")
    ap.add_argument("--spec", required=True, help="scene spec JSON")
    ap.add_argument("--out", help="output folder (default out/<name>)")
    ap.add_argument("--quality", choices=["draft", "preview", "final_fast", "final"], help="override spec.quality")
    ap.add_argument("--seed", type=int, help="override spec.seed")
    ap.add_argument("--no-render", action="store_true", help="build + save .blend only")
    ap.add_argument("--force", action="store_true", help="ignore the memory safety line")
    ap.add_argument("--still-only", action="store_true", help="moves: render only the final frame")
    ap.add_argument("--step", type=int, default=1,
                    help="moves: render every N-th frame (quick look; MP4 plays at fps/N)")
    return ap.parse_args(argv)


def main():
    import bpy
    from easyscene import build, spec as specmod

    a = parse()
    raw = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    if a.quality:
        raw["quality"] = a.quality
    if a.seed is not None:
        raw["seed"] = a.seed
    spec = specmod.validate(raw)
    out = Path(a.out) if a.out else ROOT / "out" / spec["name"]
    out.mkdir(parents=True, exist_ok=True)

    ctx = build.build_scene(spec)
    shot = ctx["shot"]
    n_frames = 1 if (shot is None or a.still_only or a.no_render) else \
        len(range(0, shot.frames, max(1, a.step))) + 1
    bud = build.check_budget(ctx, frames=n_frames, force=a.force)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"), compress=True)
    extra = {"budget": bud}
    if not a.no_render:
        extra["still"] = build.render_still(ctx, out, spec)
        if shot is not None and not a.still_only:
            extra["animation"] = build.render_animation(ctx, out, spec, step=max(1, a.step))
    still = extra.get("still", {}).get("final")
    extra["checks"] = {k: v for k, v in build.run_checks(ctx, out, still).items() if k != "checks"}
    build.write_manifest(out, spec, ctx, extra)
    print(f"[easyscene] DONE -> {out}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
