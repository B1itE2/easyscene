"""Poly Haven (CC0) asset fetching with a local cache and a license ledger.

Pure Python (urllib only). Every function returns ``None`` instead of
raising when the network or an asset is unavailable, so the builder can
fall back to procedural materials and still produce an image.

Cache layout (``$CINESCENE_CACHE`` or ``~/.cache/cinescene``)::

    polyhaven/<id>/<files...>
    polyhaven/<id>/info.json      # name, authors, license, source url
"""

import hashlib
import json
import os
import shutil
import tempfile
import time
import urllib.request
from pathlib import Path

API = "https://api.polyhaven.com"
UA = {"User-Agent": "cinescene/0.1 (+https://github.com/cinescene)"}
TIMEOUT = 30

# Assets actually used during this process; written into the run manifest.
LEDGER = {}


def cache_dir() -> Path:
    d = Path(os.environ.get("CINESCENE_CACHE", Path.home() / ".cache" / "cinescene"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def offline() -> bool:
    return os.environ.get("CINESCENE_OFFLINE", "") not in ("", "0")


def log(msg):
    print(f"[cinescene.assets] {msg}", flush=True)


def _get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _download(url, dest: Path, md5=None, retries=2):
    """Download atomically (tmp file + rename) and verify md5 if given."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
            h = hashlib.md5()
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r, os.fdopen(fd, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    h.update(chunk)
                    f.write(chunk)
            if md5 and h.hexdigest() != md5:
                raise IOError(f"md5 mismatch for {url}")
            shutil.move(tmp, dest)
            return dest
        except Exception as e:  # network errors, timeouts, md5
            try:
                os.remove(tmp)
            except Exception:
                pass
            if attempt == retries:
                log(f"download failed: {url} ({e})")
                return None
            time.sleep(1.5 * (attempt + 1))


def _info(asset_id):
    """Cached asset metadata (name, authors, license)."""
    d = cache_dir() / "polyhaven" / asset_id
    p = d / "info.json"
    if p.exists():
        return json.loads(p.read_text())
    if offline():
        return None
    try:
        i = _get_json(f"{API}/info/{asset_id}")
    except Exception as e:
        log(f"info failed for {asset_id}: {e}")
        return None
    rec = {
        "id": asset_id, "name": i.get("name", asset_id),
        "authors": sorted((i.get("authors") or {}).keys()),
        "license": "CC0-1.0", "source": f"https://polyhaven.com/a/{asset_id}",
        "type": {0: "hdri", 1: "texture", 2: "model"}.get(i.get("type"), "unknown"),
    }
    d.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2))
    return rec


def _files(asset_id):
    d = cache_dir() / "polyhaven" / asset_id
    p = d / "files.json"
    if p.exists():
        return json.loads(p.read_text())
    if offline():
        return None
    try:
        f = _get_json(f"{API}/files/{asset_id}")
    except Exception as e:
        log(f"files failed for {asset_id}: {e}")
        return None
    d.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(f))
    return f


def _use(asset_id, role, files):
    info = _info(asset_id) or {"id": asset_id, "license": "CC0-1.0",
                               "source": f"https://polyhaven.com/a/{asset_id}"}
    LEDGER[asset_id] = dict(info, role=role, files=[str(f) for f in files])


def fetch_hdri(asset_id, res="1k", role="environment"):
    """Path to an .hdr file, or None."""
    files = _files(asset_id)
    try:
        entry = files["hdri"][res]["hdr"]
    except (TypeError, KeyError):
        return None
    dest = cache_dir() / "polyhaven" / asset_id / Path(entry["url"]).name
    got = dest if dest.exists() else (None if offline() else _download(entry["url"], dest, entry.get("md5")))
    if got:
        _use(asset_id, role, [got])
    return got


TEXTURE_MAPS = {"diff": ["Diffuse", "diff"], "rough": ["Rough", "rough"],
                "nor": ["nor_gl"], "ao": ["AO"], "disp": ["Displacement"]}


def fetch_texture(asset_id, res="1k", maps=("diff", "rough", "nor"), role="material"):
    """Dict map-name -> jpg path. Returns None if the diffuse map is missing."""
    files = _files(asset_id)
    if files is None:
        return None
    out = {}
    for m in maps:
        for key in TEXTURE_MAPS[m]:
            try:
                entry = files[key][res]["jpg"]
            except (KeyError, TypeError):
                continue
            dest = cache_dir() / "polyhaven" / asset_id / Path(entry["url"]).name
            got = dest if dest.exists() else (None if offline() else _download(entry["url"], dest, entry.get("md5")))
            if got:
                out[m] = str(got)
            break
    if "diff" not in out:
        return None
    _use(asset_id, role, out.values())
    return out


def fetch_model(asset_id, res="1k", role="model"):
    """Path to a .blend with its textures next to it, or None."""
    files = _files(asset_id)
    try:
        entry = files["blend"][res]["blend"]
    except (TypeError, KeyError):
        return None
    base = cache_dir() / "polyhaven" / asset_id / res
    dest = base / Path(entry["url"]).name
    paths = []
    for rel, inc in (entry.get("include") or {}).items():
        p = base / rel
        if not p.exists() and (offline() or not _download(inc["url"], p, inc.get("md5"))):
            return None
        paths.append(p)
    if not dest.exists() and (offline() or not _download(entry["url"], dest, entry.get("md5"))):
        return None
    _use(asset_id, role, [dest] + paths)
    return dest


def ledger_records():
    """License list for the manifest, without local file paths."""
    return [{k: v for k, v in rec.items() if k != "files"}
            for _, rec in sorted(LEDGER.items())]


def prefetch(recipe: dict, res="1k"):
    """Download everything a recipe may use. CLI: python3 -m cinescene.assets STYLE."""
    a = recipe.get("assets", {})
    ok = bool(fetch_hdri(a["hdri"], res)) if a.get("hdri") else True
    for role, tid in a.get("textures", {}).items():
        ok &= bool(fetch_texture(tid, res, role=role))
    for role, mid in a.get("models", {}).items():
        ok &= bool(fetch_model(mid, "1k", role=role))
    return ok


if __name__ == "__main__":
    import sys
    from . import recipes
    style = sys.argv[1] if len(sys.argv) > 1 else "foggy_forest_cabin"
    res = sys.argv[2] if len(sys.argv) > 2 else "1k"
    t = time.time()
    good = prefetch(recipes.load(style), res)
    for r in ledger_records():
        print(f"  {r['id']:34s} {r.get('license')}  {r.get('source')}")
    print(f"{'all assets ready' if good else 'some assets missing (procedural fallback will be used)'}"
          f"  ({time.time() - t:.0f}s, cache: {cache_dir()})")
