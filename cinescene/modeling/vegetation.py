"""Ground cover: grass clumps, ferns, rocks, stumps, fallen logs.

Poly Haven models are used when cached/downloadable (fern, mossy rocks,
stump); otherwise procedural stand-ins of the same role are generated.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector, noise

from .. import assets
from .. import rng as rngmod
from .mesh import MeshBuilder, frame


# ------------------------------------------------------------ procedural ---
def grass_clump(rng, mats, name):
    mb = MeshBuilder()
    for _ in range(rng.randint(30, 50)):
        a = rng.uniform(0, math.tau)
        r0 = rng.uniform(0, 0.16)
        base = Vector((math.cos(a) * r0, math.sin(a) * r0, -0.02))
        h = rng.uniform(0.08, 0.38) * rng.choice((0.6, 1.0, 1.0))
        lean = rng.uniform(0.15, 0.6)
        d = Vector((math.cos(a + rng.uniform(-0.6, 0.6)), math.sin(a + rng.uniform(-0.6, 0.6)), 0))
        side = Vector((-d.y, d.x, 0))
        w = rng.uniform(0.004, 0.008)
        rows = []
        for i in range(5):
            t = i / 4
            c = base + d * (lean * h * t * t) + Vector((0, 0, h * t * (1 - 0.25 * t * lean)))
            ww = w * (1 - t * 0.9)
            rows.append([c - side * ww, c + side * ww])
        mb.strip(rows)
    return mb.build(name, [mats["grass"]], link=False)


def fern(rng, mats, name):
    mb = MeshBuilder()
    n = rng.randint(7, 12)
    for k in range(n):
        a = k * math.tau / n + rng.uniform(-0.25, 0.25)
        d = Vector((math.cos(a), math.sin(a), 0))
        side = Vector((-d.y, d.x, 0))
        L = rng.uniform(0.45, 0.9)
        lift = rng.uniform(0.5, 0.9)
        rows = []
        for i in range(8):
            t = i / 7
            c = d * (L * t) + Vector((0, 0, L * (lift * t - 0.85 * t * t)))
            w = L * 0.22
            rows.append([c - side * w, c, c + side * w])
        mb.strip(rows)
    return mb.build(name, [mats["fern"]], link=False)


def rock(rng, mats, name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
    off = Vector((rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)))
    sx, sy, sz = rng.uniform(0.6, 1.2), rng.uniform(0.5, 1.0), rng.uniform(0.35, 0.6)
    for v in bm.verts:
        n = noise.fractal(v.co * 1.3 + off, 0.5, 2.0, 4)
        v.co *= 1.0 + 0.28 * n
        v.co.x *= sx
        v.co.y *= sy
        v.co.z = v.co.z * sz + 0.15 * sz   # sunk: bottom third below ground
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["rock"])
    for p in me.polygons:
        p.use_smooth = True
    return bpy.data.objects.new(name, me)


def fallen_log(rng, mats, name):
    mb = MeshBuilder()
    L, r = rng.uniform(4.0, 8.0), rng.uniform(0.18, 0.32)
    wob = [rng.uniform(0.9, 1.1) for _ in range(9 * 10)]
    mb.cylinder(L, r, r * 0.7, segs=10, rings=8, jitter=lambda i, j: wob[i * 10 + j],
                m=Matrix.Translation((-L / 2, 0, r * 0.6)))
    return mb.build(name, [mats["bark"]], link=False)


# -------------------------------------------------------- Poly Haven models ---
def load_model(asset_id, role, max_objects=8, max_size=None):
    """Append mesh objects from a cached Poly Haven .blend, normalised so each
    sits on z=0 centred on the origin. Returns [] if unavailable."""
    path = assets.fetch_model(asset_id, role=role)
    if not path:
        return []
    with bpy.data.libraries.load(str(path), link=False, relative=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    out = []
    for o in dst.objects:
        if o is None or o.type != "MESH":
            continue
        if any(t in o.name.upper() for t in ("LOD1", "LOD2", "LOD3", "LOD4")):
            continue
        me = o.data.copy()
        me.transform(o.matrix_world)
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        zs = [v.co.z for v in me.vertices]
        me.transform(Matrix.Translation((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2,
                                         -min(zs) - 0.02)))
        size = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        if max_size and size > max_size:      # scanned sets can be huge: bring to scene scale
            me.transform(Matrix.Scale(max_size / size, 4))
        out.append(bpy.data.objects.new(f"{asset_id}_{len(out)}", me))
        if len(out) >= max_objects:
            break
    out.sort(key=lambda ob: ob.name)
    return out


# ------------------------------------------------------------- placement ---
def place_clustered(rng, n, r_range, terrain, keep_out, n_var, per_cluster=(6, 18), spread=0.7,
                    scale=(0.7, 1.3), weight=None):
    """Patchy placement: plants grow in clumps, not in an even carpet."""
    out, tries = [], 0
    while len(out) < n and tries < n * 4:
        tries += 1
        a = rng.uniform(0, math.tau)
        d = math.sqrt(rng.uniform(r_range[0] ** 2, r_range[1] ** 2))
        cx, cy = math.cos(a) * d, math.sin(a) * d
        if weight and rng.random() > weight(cx, cy, d):
            continue
        big = rng.random() < 0.25          # a few large meadows between small tufts
        for _ in range(rng.randint(*per_cluster) * (3 if big else 1)):
            x = cx + rng.gauss(0, spread * (2.2 if big else 1.0))
            y = cy + rng.gauss(0, spread * (2.2 if big else 1.0))
            if keep_out(x, y):
                continue
            out.append((x, y, terrain.height(x, y), 0.0, 0.0, rng.uniform(0, math.tau),
                        rng.uniform(*scale), rng.randrange(n_var)))
    return out[:n]



def place(rng, n, r_range, terrain, keep_out, n_var, scale=(0.8, 1.25), sink=0.0,
          weight=None):
    """Rejection-sample ``n`` points in an annulus around the subject."""
    out, tries = [], 0
    while len(out) < n and tries < n * 30:
        tries += 1
        a = rng.uniform(0, math.tau)
        d = math.sqrt(rng.uniform(r_range[0] ** 2, r_range[1] ** 2))
        x, y = math.cos(a) * d, math.sin(a) * d
        if keep_out(x, y):
            continue
        if weight and rng.random() > weight(x, y, d):
            continue
        out.append((x, y, terrain.height(x, y) - sink, 0.0, 0.0, rng.uniform(0, math.tau),
                    rng.uniform(*scale), rng.randrange(n_var)))
    return out
