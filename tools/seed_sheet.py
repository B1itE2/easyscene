"""Render the same spec with N seeds (still only) and build a labelled comparison sheet.

  /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/seed_sheet.py -- \
      --spec examples/lighthouse_sunset.json --seeds 1 2 3 4 5 --quality preview

Runs one Blender build per seed in sequence (never in parallel: memory),
then writes out/<name>_seeds/seeds.png and seeds.json (check results per seed).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    ap.add_argument("--quality", default="preview")
    ap.add_argument("--blender", default=sys.executable if "blender" in sys.executable.lower()
                    else "/Applications/Blender.app/Contents/MacOS/Blender")
    a = ap.parse_args(argv)
    name = json.loads(Path(a.spec).read_text())["name"]
    base = ROOT / "out" / f"{name}_seeds"
    base.mkdir(parents=True, exist_ok=True)
    results = {}
    for s in a.seeds:
        out = base / f"seed_{s}"
        cmd = [a.blender, "-b", "--factory-startup", "-P", str(ROOT / "tools" / "build.py"), "--",
               "--spec", a.spec, "--seed", str(s), "--quality", a.quality, "--still-only", "--out", str(out)]
        print(f"[seeds] seed {s} ...", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        ok = r.returncode == 0 and (out / "still.png").exists()
        chk = json.loads((out / "checks.json").read_text()) if (out / "checks.json").exists() else {}
        results[s] = {"ok": ok, "checks_passed": chk.get("passed"), "failed": chk.get("failed", [])}
        print(f"[seeds] seed {s}: {'rendered' if ok else 'FAILED'}  checks: "
              f"{'pass' if chk.get('passed') else chk.get('failed')}", flush=True)
        if not ok:
            print(r.stdout[-1500:], r.stderr[-1500:])
    (base / "seeds.json").write_text(json.dumps(results, indent=2))
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("[seeds] Pillow missing: no sheet image"); return
    ims = [(s, Image.open(base / f"seed_{s}" / "still.png").convert("RGB"))
           for s in a.seeds if results[s]["ok"]]
    if not ims:
        return
    w = 640
    h = int(ims[0][1].height * w / ims[0][1].width)
    cols = 3 if len(ims) > 4 else len(ims)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols - 1) * 6, rows * (h + 26)), "white")
    d = ImageDraw.Draw(sheet)
    for i, (s, im) in enumerate(ims):
        x, y = (i % cols) * (w + 6), (i // cols) * (h + 26)
        sheet.paste(im.resize((w, h)), (x, y))
        mark = "" if results[s]["checks_passed"] else "  (checks failed)"
        d.text((x + 6, y + h + 6), f"seed {s}{mark}", fill="black")
    sheet.save(base / "seeds.png")
    print(f"[seeds] sheet -> {base / 'seeds.png'}")


if __name__ == "__main__":
    main()
