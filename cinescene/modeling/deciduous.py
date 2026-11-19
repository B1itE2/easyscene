"""Deciduous (autumn) trees: recursive branching trunk + leaf-card clusters.

Leaves are small alpha-cut quads grouped in clumps at branch tips, so a full
autumn crown costs ~2-4k quads per variant. Colour comes from the material
(per-instance + per-clump randomness over an autumn palette), so the same
meshes serve red maples, yellow birches or a mixed bank depending on recipe.
"""

import math

from mathutils import Matrix, Vector

from .mesh import MeshBuilder, frame


def _branch(mb, rng, base, direction, length, radius, depth, tips):
    d = Vector(direction).normalized()
    segs = 3
    pts = [Vector(base)]
    for i in range(segs):
        bend = Vector((rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), rng.uniform(-0.05, 0.15)))
        d = (d + bend).normalized()
        pts.append(pts[-1] + d * (length / segs))
    for i in range(segs):
        seg = pts[i + 1] - pts[i]
        r0 = radius * (1 - 0.55 * i / segs)
        r1 = radius * (1 - 0.55 * (i + 1) / segs)
        mb.cylinder(seg.length, r0, r1, segs=6 if depth == 0 else 5, m=frame(pts[i], seg), caps=False, mat=0)
    if depth >= 1:            # leaves along the outer branches too, not only at the tips
        for k in range(2):
            tips.append((pts[1 + k], d))
    if depth >= 3 or radius < 0.02:
        tips.append((pts[-1], d))
        return
    n = rng.randint(2, 3) if depth > 0 else rng.randint(3, 5)
    for k in range(n):
        t = rng.uniform(0.45, 1.0)
        i = min(segs - 1, int(t * segs))
        f = t * segs - i
        p = pts[i].lerp(pts[i + 1], f)
        a = rng.uniform(0, math.tau)
        side = Vector((math.cos(a), math.sin(a), 0))
        nd = (d * 0.6 + side * 0.8 + Vector((0, 0, rng.uniform(0.1, 0.5)))).normalized()
        _branch(mb, rng, p, nd, length * rng.uniform(0.5, 0.72), radius * rng.uniform(0.5, 0.65),
                depth + 1, tips)


def _leaf_clump(mb, rng, centre, size, n):
    for _ in range(n):
        off = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 0.7))) * size
        c = Vector(centre) + off
        s = rng.uniform(0.12, 0.2)
        yaw, pitch = rng.uniform(0, math.tau), rng.uniform(-0.6, 0.9)
        dx = Vector((math.cos(yaw), math.sin(yaw), 0)) * s
        dz = Vector((-math.sin(yaw) * math.sin(pitch), math.cos(yaw) * math.sin(pitch), math.cos(pitch))) * s
        b = len(mb.verts)
        mb.verts += [tuple(c - dx - dz), tuple(c + dx - dz), tuple(c + dx + dz), tuple(c - dx + dz)]
        mb.add_face((b, b + 1, b + 2, b + 3), ((0, 0), (1, 0), (1, 1), (0, 1)), 1)


def tree(rng, height, mats, name="Maple", leaf_density=1.0):
    mb = MeshBuilder()
    r0 = height * rng.uniform(0.022, 0.03)
    trunk_h = height * rng.uniform(0.16, 0.26)    # lakeside trees keep low branches (open light)
    lean = Vector((rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12), 1)).normalized()
    top = lean * trunk_h
    mb.cylinder(trunk_h + 0.3, r0 * 1.25, r0, segs=8, rings=3, m=frame((0, 0, -0.3), lean), caps=False,
                jitter=None, mat=0)
    tips = []
    for k in range(rng.randint(3, 5)):
        a = k * math.tau / 4 + rng.uniform(-0.5, 0.5)
        d = Vector((math.cos(a) * 0.9, math.sin(a) * 0.9, 0.8))
        _branch(mb, rng, top, d, height * rng.uniform(0.28, 0.36), r0 * 0.7, 0, tips)
    for p, d in tips:
        _leaf_clump(mb, rng, p + d * 0.2, rng.uniform(0.5, 0.85), int(rng.randint(45, 70) * leaf_density))
    return mb.build(name, [mats["bark_birch" if "Birch" in name else "bark"], mats["autumn_leaf"]],
                    link=False)


def variants(rng, count, height_range, mats, leaf_density=1.0):
    lo, hi = height_range
    return [tree(rng, lo + (hi - lo) * (i + rng.random()) / count, mats, name=f"Maple{i}",
                 leaf_density=leaf_density) for i in range(count)]
