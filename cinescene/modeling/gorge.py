"""Rainforest gorge: plunge pool at the origin, a cliff with a waterfall behind it.

Pool (z < 0) of radius ~``pool_r`` around the origin, cliff face rising at
y = ``cliff_y`` to ``cliff_h`` metres, rocky banks rising on both sides so the
gorge frames the falls. The camera stands on the near bank (-Y).
"""

import math

import bpy
from mathutils import Vector, noise

from ..nodes import new_material
from .mesh import MeshBuilder
from .terrain import smoothstep


class Gorge:
    def __init__(self, rng, size=200.0, resolution=300, pool_r=11.0, cliff_y=13.0, cliff_h=22.0,
                 width=26.0):
        self.size, self.res = size, resolution
        self.pool_r, self.cy, self.ch, self.w = pool_r, cliff_y, cliff_h, width
        self.off = Vector((rng.uniform(-500, 500), rng.uniform(-500, 500), rng.uniform(0, 50)))
        self.py = cliff_y - pool_r * 0.7          # pool sits right at the foot of the falls
        self.path = None
        self.flat = []

    def flatten_segment(self, *_a, **_k):
        pass

    def height(self, x, y):
        n = noise.fractal(Vector((x / 9.0, y / 9.0, 0.0)) + self.off, 0.7, 2.1, 5)
        r = math.hypot(x, (y - self.py) * 1.2)
        pool = -1.8 * (1 - smoothstep(self.pool_r * 0.8, self.pool_r * 1.15, r + n * 2.0))
        bank = smoothstep(self.pool_r - 1.0, self.pool_r + 6.0, r + n * 2.5) * (0.35 + n * 0.3)
        # side walls of the gorge: rounded, vegetated slopes (not spikes)
        sw = smoothstep(self.w * 0.35, self.w * 0.9, abs(x) + n * 2.0)
        side = sw * sw * self.ch * 0.75
        # the cliff behind the pool: near-vertical wall with ledges
        ledge = noise.ridged_multi_fractal(Vector((x / 4.0, 0.0, y / 3.0)) + self.off, 1.0, 2.0, 4, 0.0, 1.0)
        cliff = smoothstep(self.cy - 1.5, self.cy + 1.0, y + n * 1.5 + ledge * 0.6) * self.ch
        # add, don't max(): side/cliff are >= 0 and would flatten the pool basin to 0
        h = pool + bank + max(side, cliff) + n * 0.4
        return h

    def normal(self, x, y, e=0.4):
        dx = self.height(x + e, y) - self.height(x - e, y)
        dy = self.height(x, y + e) - self.height(x, y - e)
        return Vector((-dx, -dy, 2 * e)).normalized()

    def build(self, material):
        mb = MeshBuilder()
        n, s = self.res, self.size
        step = s / n
        for i in range(n + 1):
            for j in range(n + 1):
                x = -s / 2 + j * step
                y = -s / 2 + i * step + s * 0.2
                mb.verts.append((x, y, self.height(x, y)))
        for i in range(n):
            for j in range(n):
                a = i * (n + 1) + j
                mb.add_face((a, a + 1, a + n + 2, a + n + 1),
                            ((j, i), (j + 1, i), (j + 1, i + 1), (j, i + 1)))
        return mb.build("Terrain", [material])


def waterfall_material(time_node_name="cinescene_time"):
    """White-water sheet: vertical streaks scrolling down, translucent edges."""
    mat, nb = new_material("Waterfall")
    uv = nb.coord("UV")
    u, v, _ = nb.sep(uv)
    t = nb.new("ShaderNodeValue")
    t.name = t.label = time_node_name
    flow = nb.math("ADD", v, nb.math("MULTIPLY", t.outputs[0], 0.35))
    streak = nb.noise(nb.comb(nb.math("MULTIPLY", u, 40.0), nb.math("MULTIPLY", flow, 3.0), 0.0),
                      detail=6.0, rough=0.6)
    foam = nb.maprange(streak, 0.35, 0.7)
    edge = nb.math("MULTIPLY", nb.maprange(u, 0.0, 0.12), nb.maprange(u, 1.0, 0.88))
    alpha = nb.math("MULTIPLY", nb.math("ADD", 0.25, nb.math("MULTIPLY", foam, 0.75)), edge)
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    nb.set(bsdf, "Base Color", nb.mix(foam, (0.35, 0.42, 0.42), (0.92, 0.95, 0.95)))
    nb.set(bsdf, "Roughness", 0.3)
    nb.set(bsdf, "Subsurface Weight", 0.3)
    nb.set(bsdf, "Alpha", alpha)
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(bsdf.outputs[0], nb.i(out, "Surface"))
    return mat


def waterfall(gorge, x_center, width, rng):
    """Curved sheet from the cliff lip down into the pool, following the cliff face."""
    top = gorge.ch + 0.3
    rows = []
    n = 40
    for i in range(n + 1):
        t = i / n
        z = top * (1 - t) - 0.3 * t
        # find the cliff face at this height: march -Y from behind until we are in front
        y = gorge.cy + 2.0
        while gorge.height(x_center, y) > z and y > gorge.cy - 6:
            y -= 0.15
        y -= 0.6 + 1.2 * t ** 0.5            # water leaves the face slightly
        w = width * (1.0 + 0.35 * t)
        row = []
        for k in range(9):
            s = k / 8 - 0.5
            row.append((x_center + s * w + noise.noise(Vector((s * 3, t * 4, 0.5))) * 0.3, y, z))
        rows.append(row)
    mb = MeshBuilder()
    mb.strip([list(r) for r in rows])
    obj = mb.build("Waterfall", [waterfall_material()], smooth=True)
    obj.visible_shadow = False
    return obj, (x_center, rows[-1][4][1], 0.0), top
