"""Forest: procedural spruce/fir variants and their placement.

A spruce is a tapered trunk plus whorls of drooping frond strips whose
needle silhouette is cut by the ``needles`` material alpha. Lower trunk
carries a few dead twigs, as real spruces in dense stands do.
"""

import math

from mathutils import Matrix, Vector

from .. import rng as rngmod
from .mesh import MeshBuilder, frame


def _frond(mb, start, direction, L, droop, rng, mat):
    d = Vector((direction[0], direction[1], 0)).normalized()
    side = Vector((-d.y, d.x, 0))
    rows = []
    for i in range(7):
        t = i / 6
        c = Vector(start) + d * (L * t * (1 - 0.12 * t)) + \
            Vector((0, 0, L * (0.10 * t - droop * t * t)))
        w = L * 0.38 * math.sin(math.pi * (0.12 + 0.78 * t)) + 0.03
        sag = w * 0.35  # edges hang lower than the rib
        rows.append([c - side * w / 2 - Vector((0, 0, sag)), c,
                     c + side * w / 2 - Vector((0, 0, sag))])
    mb.strip(rows, mat=mat)


def _branch(mb, start, a, L, droop, rng):
    """Main branch axis with paired side branchlets: reads as fine needle mass, not leaves."""
    d = Vector((math.cos(a), math.sin(a), 0))

    def axis(t):
        return Vector(start) + d * (L * t) + Vector((0, 0, L * (0.12 * t - droop * t * t)))

    n = max(3, int(L / 0.28))
    for i in range(n):
        t = 0.12 + 0.88 * (i + rng.uniform(-0.2, 0.2)) / n
        p = axis(t)
        tangent = (axis(min(1.0, t + 0.05)) - p).normalized()
        ls = min(0.85, L * rng.uniform(0.22, 0.3) * (1.15 - 0.6 * t) + 0.15)
        for side in (-1, 1):
            ang = a + side * rng.uniform(0.75, 1.05)
            _frond(mb, p, (math.cos(ang) + tangent.x * 0.6, math.sin(ang) + tangent.y * 0.6),
                   ls, rng.uniform(0.35, 0.6), rng, 1)
    _frond(mb, axis(0.85), (d.x, d.y), min(0.9, L * 0.3 + 0.2), droop, rng, 1)


def spruce(rng, height, crown_base_ratio, mats, dead=False, name="Spruce"):
    mb = MeshBuilder()
    r0 = height * rng.uniform(0.014, 0.019)
    wob = [rng.uniform(0.92, 1.08) for _ in range(7 * 10)]

    def jit(i, j):
        flare = 1.35 if i == 0 else 1.0
        return wob[i * 10 + j] * flare

    lean = (rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25))
    mb.cylinder(height + 0.5, r0, 0.025, segs=10, rings=6, mat=0, jitter=jit,
                m=frame((0, 0, -0.5), (0, 0, 1), up=(1, 0, 0)),
                bend=lambda t: (lean[0] * t * t, lean[1] * t * t), caps=False, uv_scale=0.5)

    def axis_at(z):
        t = (z + 0.5) / (height + 0.5)
        return Vector((lean[1] * t * t, -lean[0] * t * t, z))  # frame maps local (y,z) -> world (-y,x)

    zb = height * crown_base_ratio
    # dead twigs on the bare lower trunk
    for _ in range(int(rng.uniform(8, 16))):
        z = rng.uniform(1.8, max(2.0, zb if not dead else height * 0.9))
        a = rng.uniform(0, math.tau)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(-0.35, 0.05))).normalized()
        L = rng.uniform(0.4, 1.4)
        mb.cylinder(L, 0.025, 0.006, segs=4, mat=0, m=frame(axis_at(z), d), caps=False)
    if dead:
        return mb.build(name, [mats["bark"], mats["needles"]], link=False)

    z, Lmax = zb, height * rng.uniform(0.17, 0.22)
    while z < height - 0.3:
        u = (height - z) / (height - zb)                 # 1 at crown base, 0 at top
        n_br = rng.randint(5, 8)
        a0 = rng.uniform(0, math.tau)
        for k in range(n_br):
            a = a0 + k * math.tau / n_br + rng.uniform(-0.3, 0.3)
            L = Lmax * (u ** 0.85) * rng.uniform(0.8, 1.15) + 0.35
            droop = rng.uniform(0.22, 0.42) * (0.6 + 0.6 * u)
            st = axis_at(z) + Vector((math.cos(a), math.sin(a), 0)) * r0 * (1 - 0.8 * (1 - u))
            _branch(mb, st, a, L, droop, rng)
        z += rng.uniform(0.38, 0.55) * (0.7 + 0.3 * height / 20)
    # leader tip
    for k in range(4):
        a = k * math.tau / 4 + rng.uniform(-0.3, 0.3)
        _frond(mb, axis_at(height - 0.6), (math.cos(a), math.sin(a)), 0.45, -0.6, rng, 1)
    return mb.build(name, [mats["bark"], mats["needles"]], link=False)


def variants(seed, cfg, mats, count):
    r = rngmod.stream(seed, "forest.variants")
    lo, hi = cfg["height_range_m"]
    out = []
    for i in range(count):
        h = lo + (hi - lo) * (i + r.random()) / count     # spread heights evenly
        cb = r.uniform(*cfg["crown_base_ratio"])
        out.append(spruce(r, h, cb, mats, name=f"Spruce{i}"))
    out.append(spruce(r, r.uniform(9, 15), 0.9, mats, dead=True, name="Snag"))
    return out


def place(seed, cfg, terrain, keep_out, density=1.0):
    """Return scatter points. ``keep_out(x, y) -> bool`` marks forbidden spots."""
    r = rngmod.stream(seed, "forest.place")
    ext = cfg["extent_m"]
    pts = rngmod.poisson_disk(r, ext, ext, cfg["min_spacing_m"] / math.sqrt(density))
    n_var = cfg["variants"]
    out = []
    for x, y in pts:
        if keep_out(x, y):
            continue
        dist = math.hypot(x, y)
        # thinner near the clearing edge so the forest wall is irregular
        if r.random() > min(1.0, 0.45 + (dist - cfg["clear_radius_m"]) / 25.0):
            continue
        vid = n_var if r.random() < cfg["snag_ratio"] else r.randrange(n_var)
        out.append((x, y, terrain.height(x, y) - 0.15,
                    r.uniform(-0.03, 0.03), r.uniform(-0.03, 0.03), r.uniform(0, math.tau),
                    r.uniform(0.82, 1.18), vid))
    return out
