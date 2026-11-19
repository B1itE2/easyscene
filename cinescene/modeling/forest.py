"""Forest: procedural spruce/fir variants and their placement.

A spruce is a tapered trunk plus whorls of drooping frond strips whose
needle silhouette is cut by the ``needles`` material alpha. Lower trunk
carries a few dead twigs, as real spruces in dense stands do.
"""

import math

from mathutils import Matrix, Vector

from .. import rng as rngmod
from .mesh import MeshBuilder, frame


def _frond(mb, start, direction, L, droop, rng, mat, roll=0.0):
    """One needle-covered twig strip. ``roll`` tilts it around its own axis (radians),
    so twigs point in all directions instead of lying flat like a comb."""
    d = Vector((direction[0], direction[1], 0)).normalized()
    side = Vector((-d.y, d.x, 0))
    if roll:
        side = (side * math.cos(roll) + Vector((0, 0, 1)) * math.sin(roll)).normalized()
    rows = []
    for i in range(7):
        t = i / 6
        c = Vector(start) + d * (L * t * (1 - 0.12 * t)) + \
            Vector((0, 0, L * (0.10 * t - droop * t * t)))
        w = L * 0.34 * math.sin(math.pi * (0.12 + 0.78 * t)) + 0.03
        sag = w * 0.3 * math.cos(roll)  # edges hang lower than the rib
        rows.append([c - side * w / 2 - Vector((0, 0, sag)), c,
                     c + side * w / 2 - Vector((0, 0, sag))])
    mb.strip(rows, mat=mat)


def _branch(mb, start, a, L, droop, rng):
    """Main branch axis with paired side branchlets: reads as fine needle mass, not leaves."""
    d = Vector((math.cos(a), math.sin(a), 0))

    def axis(t):
        return Vector(start) + d * (L * t) + Vector((0, 0, L * (0.12 * t - droop * t * t)))

    # woody branch axis: a thin tapered bark tube following the droop curve
    steps = 5
    for k in range(steps):
        p0, p1 = axis(k / steps), axis((k + 1) / steps)
        seg = p1 - p0
        r0 = 0.035 * (1 - 0.8 * k / steps) * min(1.0, L / 2.5) + 0.006
        mb.cylinder(seg.length, r0, r0 * 0.8, segs=4, m=frame(p0, seg), caps=False, mat=0)
    n = max(4, int(L / 0.12))
    for i in range(n):
        t = 0.08 + 0.92 * (i + rng.uniform(-0.3, 0.3)) / n
        p = axis(t)
        tangent = (axis(min(1.0, t + 0.05)) - p).normalized()
        ls = min(0.45, L * rng.uniform(0.16, 0.22) * (1.2 - 0.6 * t) + 0.12)
        for side in (-1, 1, 0):          # left, right, and one twig rolled up/down
            if side == 0 and rng.random() < 0.4:
                continue
            ang = a + (side or rng.choice((-1, 1))) * rng.uniform(0.5, 1.1)
            roll = rng.uniform(-0.6, 0.6) if side else rng.choice((-1, 1)) * rng.uniform(0.9, 1.3)
            _frond(mb, p, (math.cos(ang) + tangent.x * 0.7, math.sin(ang) + tangent.y * 0.7),
                   ls * (0.75 if side == 0 else 1.0), rng.uniform(0.25, 0.5), rng, 1, roll)
    _frond(mb, axis(0.9), (d.x, d.y), min(0.5, L * 0.25 + 0.15), droop, rng, 1)


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

    z, Lmax = zb, height * rng.uniform(0.13, 0.17)
    while z < height - 0.3:
        u = (height - z) / (height - zb)                 # 1 at crown base, 0 at top
        n_br = rng.randint(6, 9)
        a0 = rng.uniform(0, math.tau)
        for k in range(n_br):
            a = a0 + k * math.tau / n_br + rng.uniform(-0.3, 0.3)
            L = Lmax * (u ** 0.85) * rng.uniform(0.8, 1.15) + 0.35
            droop = rng.uniform(0.08, 0.22) * (0.5 + 0.7 * u)
            st = axis_at(z) + Vector((math.cos(a), math.sin(a), 0)) * r0 * (1 - 0.8 * (1 - u))
            _branch(mb, st, a, L, droop, rng)
        z += rng.uniform(0.3, 0.42) * (0.7 + 0.3 * height / 20)
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


def thin_toward_sun(points, sun_dir, seed, cfg):
    """Open 'light windows' in the forest wall on the sun side of the clearing.

    Low sun only makes visible shafts in fog if it can pass *between* trunks.
    Inside a wedge around the sun azimuth, most trees are removed and the rest
    get bare trunks (snag variant) so light streams in under the canopy.
    """
    if not sun_dir:
        return points
    r = rngmod.stream(seed, "forest.sunwindow")
    az = math.atan2(sun_dir[1], sun_dir[0])
    half = math.radians(cfg.get("sun_window_deg", 22))
    near, far = cfg["clear_radius_m"], cfg.get("sun_window_depth_m", 60.0)
    out = []
    for p in points:
        d = math.hypot(p[0], p[1])
        da = abs((math.atan2(p[1], p[0]) - az + math.pi) % math.tau - math.pi)
        if near < d < far and da < half:
            edge = da / half                                  # soft wedge edges
            if r.random() > 0.15 + 0.6 * edge * edge:
                continue
        out.append(p)
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
