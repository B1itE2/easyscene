"""Quality presets plus memory / time budgeting.

Numbers are deliberately conservative: the 16 GB MacBook Air froze on a big
scene before, so ``preview`` is sized to stay well under ~8 GB.
"""

import json
import os
import platform
from pathlib import Path

# Short side of the frame in pixels; the long side follows the aspect ratio.
QUALITY = {
    "draft": {
        "short_side": 360, "samples": 16, "denoise": True,
        "volume_step_rate": 3.0, "volume_max_steps": 256, "volume_bounces": 0,
        "max_bounces": 4, "transparent_bounces": 12, "texture_res": "1k",
        "texture_limit": "1024", "tree_density": 1.0, "undergrowth": 1.0,
    },
    "preview": {
        "short_side": 540, "samples": 32, "denoise": True,
        "volume_step_rate": 2.0, "volume_max_steps": 512, "volume_bounces": 1,
        "max_bounces": 6, "transparent_bounces": 16, "texture_res": "1k",
        "texture_limit": "1024", "tree_density": 1.0, "undergrowth": 1.0,
    },
    # 1080p with fewer samples + denoiser: ~4-6x faster than final, fine for social video
    "final_fast": {
        "short_side": 1080, "samples": 64, "denoise": True,
        "volume_step_rate": 2.0, "volume_max_steps": 512, "volume_bounces": 1,
        "max_bounces": 8, "transparent_bounces": 24, "texture_res": "2k",
        "texture_limit": "2048", "tree_density": 1.0, "undergrowth": 1.0,
    },
    "final": {
        "short_side": 1080, "samples": 256, "denoise": True,
        "volume_step_rate": 1.0, "volume_max_steps": 1024, "volume_bounces": 1,
        "max_bounces": 10, "transparent_bounces": 32, "texture_res": "2k",
        "texture_limit": "2048", "tree_density": 1.0, "undergrowth": 1.0,
    },
}

ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "2.39:1": 2.39}

# Safety line for total Blender memory on this machine (GB). Overridable.
DEFAULT_MEM_LIMIT_GB = float(os.environ.get("CINESCENE_MEM_LIMIT_GB", "8"))


def resolution(aspect: str, quality: str):
    """(width, height), both even numbers (needed by H.264)."""
    a = ASPECTS[aspect]
    s = QUALITY[quality]["short_side"]
    w, h = (s * a, s) if a >= 1 else (s, s / a)
    return int(round(w / 2) * 2), int(round(h / 2) * 2)


def estimate_memory_gb(unique_tris: int, instances: int, texture_pixels: int,
                       float_texture_pixels: int, width: int, height: int) -> float:
    """Rough upper bound of Cycles memory for one frame.

    ~180 B per unique triangle (mesh + BVH), ~250 B per instance,
    4 B/px for 8-bit textures (+33% mips), 16 B/px for float (HDRI),
    ~20 float passes for the film incl. denoiser buffers, ~0.9 GB baseline.
    """
    b = unique_tris * 180 + instances * 250
    b += texture_pixels * 4 * 1.33 + float_texture_pixels * 16
    b += width * height * 4 * 20
    return 0.9 + b / 1024 ** 3


def _calib_path():
    from .assets import cache_dir
    return cache_dir() / "calibration.json"


def machine_key():
    return f"{platform.system()}-{platform.machine()}-{platform.node()}"


def seconds_per_unit():
    """Measured seconds per (megapixel x sample); None if never measured here."""
    try:
        data = json.loads(_calib_path().read_text())
        return data.get(machine_key())
    except (OSError, ValueError):
        return None


def record_timing(width, height, samples, seconds):
    units = width * height / 1e6 * samples
    if units <= 0:
        return
    p = _calib_path()
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        data = {}
    old = data.get(machine_key())
    new = seconds / units
    data[machine_key()] = new if old is None else 0.5 * old + 0.5 * new
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def estimate_seconds(width, height, samples, frames=1):
    """Per-run estimate; falls back to a guess for an M-series laptop GPU."""
    spu = seconds_per_unit()
    guessed = spu is None
    spu = spu if spu is not None else 3.0
    return width * height / 1e6 * samples * spu * frames + 15, guessed
