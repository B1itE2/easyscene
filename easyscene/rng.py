"""Deterministic random streams.

Every subsystem draws from its *own* stream derived from (seed, name), so
adding trees never changes where the rocks go, and the same spec + seed
always produces the same scene. Never use the global ``random`` module or
Python's ``hash()`` (it is salted per process).
"""

import random
import zlib


def stream(seed: int, name: str) -> random.Random:
    """Return an independent RNG for subsystem ``name``."""
    mixed = (int(seed) * 1_000_003) ^ zlib.crc32(name.encode("utf-8"))
    return random.Random(mixed & 0xFFFFFFFFFFFF)


def poisson_disk(rng: random.Random, width: float, height: float, radius: float,
                 accept=None, k: int = 20, origin=(0.0, 0.0)):
    """Bridson Poisson-disk sampling in a rectangle centred on ``origin``.

    ``accept(x, y) -> bool`` can reject points (clearings, paths...).
    Output order is deterministic for a given rng state.
    """
    import math
    cell = radius / math.sqrt(2)
    gw, gh = int(width / cell) + 1, int(height / cell) + 1
    grid = [-1] * (gw * gh)
    pts, active, out = [], [], []
    x0, y0 = origin[0] - width / 2, origin[1] - height / 2

    def gi(p):
        return int((p[0] - x0) / cell), int((p[1] - y0) / cell)

    def far_enough(p):
        cx, cy = gi(p)
        for yy in range(max(cy - 2, 0), min(cy + 3, gh)):
            for xx in range(max(cx - 2, 0), min(cx + 3, gw)):
                j = grid[yy * gw + xx]
                if j >= 0:
                    q = pts[j]
                    if (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 < radius * radius:
                        return False
        return True

    first = (x0 + rng.random() * width, y0 + rng.random() * height)
    pts.append(first)
    active.append(0)
    cx, cy = gi(first)
    grid[cy * gw + cx] = 0
    while active:
        idx = active[rng.randrange(len(active))]
        base = pts[idx]
        for _ in range(k):
            a = rng.random() * math.tau
            r = radius * (1 + rng.random())
            p = (base[0] + math.cos(a) * r, base[1] + math.sin(a) * r)
            if not (x0 <= p[0] < x0 + width and y0 <= p[1] < y0 + height):
                continue
            if far_enough(p):
                pts.append(p)
                active.append(len(pts) - 1)
                cx, cy = gi(p)
                grid[cy * gw + cx] = len(pts) - 1
                break
        else:
            active.remove(idx)
    for p in pts:
        if accept is None or accept(p[0], p[1]):
            out.append(p)
    return out
