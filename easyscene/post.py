"""Post-processing with ffmpeg: grade, vignette, film grain, encoding.

Fog layering is done *in render* (volumes); this module only adds the
final camera-like touches. Grain uses a fixed seed so output is repeatable.
"""

import shutil
import subprocess
from pathlib import Path


def ffmpeg_bin():
    exe = shutil.which("ffmpeg")
    if exe is None:
        for cand in (Path.home() / ".local/bin/ffmpeg", Path("/opt/homebrew/bin/ffmpeg"),
                     Path("/usr/local/bin/ffmpeg")):
            if cand.exists():
                return str(cand)
    return exe


def filter_chain(post: dict, seed: int, animated: bool = False) -> str:
    sh = post.get("shadows_rgb", [0, 0, 0])
    hi = post.get("highlights_rgb", [0, 0, 0])
    parts = [
        f"colorbalance=rs={sh[0]}:gs={sh[1]}:bs={sh[2]}:rh={hi[0]}:gh={hi[1]}:bh={hi[2]}",
        f"eq=contrast={post.get('contrast', 1)}:saturation={post.get('saturation', 1)}"
        f":gamma={post.get('gamma', 1)}",
        f"vignette=angle={post.get('vignette_angle', 0.5)}",
    ]
    g = int(post.get("grain", 0))
    if g > 0:
        # 't' = temporal (changes per frame) only for animation; stills stay stable.
        flags = "t+u" if animated else "u"
        parts.append(f"noise=alls={g}:allf={flags}:all_seed={seed % 2147483647}")
    return ",".join(parts)


def run(cmd):
    print("[easyscene.post] " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{r.stderr[-2000:]}")


def grade_still(src, dst, post: dict, seed: int):
    exe = ffmpeg_bin()
    if exe is None:
        shutil.copyfile(src, dst)
        print("[easyscene.post] ffmpeg not found: wrote ungraded image")
        return False
    run([exe, "-y", "-loglevel", "error", "-i", str(src),
         "-vf", filter_chain(post, seed) + ",format=rgb24", "-frames:v", "1", str(dst)])
    return True


def encode_video(frame_pattern, dst, fps: int, post: dict, seed: int, crf: int = 18):
    """frame_pattern like out/frames/f_%04d.png -> graded H.264 MP4."""
    exe = ffmpeg_bin()
    if exe is None:
        raise RuntimeError("ffmpeg is required to encode video")
    vf = filter_chain(post, seed, animated=True) + ",format=yuv420p"
    run([exe, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frame_pattern),
         "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
         "-movflags", "+faststart", str(dst)])


def contact_sheet(frame_pattern, dst, n_frames, cols=3, rows=2, width=1440):
    """Thumbnail grid of evenly spaced frames, first and last always included."""
    exe = ffmpeg_bin()
    if exe is None or n_frames < 1:
        return False
    k = cols * rows
    picks = sorted({round(i * (n_frames - 1) / (k - 1)) for i in range(k)})
    sel = "+".join(f"eq(n\\,{p})" for p in picks)
    tw = width // cols
    run([exe, "-y", "-loglevel", "error", "-i", str(frame_pattern),
         "-vf", f"select='{sel}',scale={tw}:-2,tile={cols}x{rows}:padding=4:color=white",
         "-frames:v", "1", "-fps_mode", "vfr", str(dst)])
    return True
