"""Coastal headland: a grassy plateau ending in steep, rugged cliffs above the sea.

``Headland.height(x, y)`` is analytic (same contract as ``terrain.Terrain``)
so scattering, camera clearance and the shore-foam mask all agree with the mesh.
The mainland lies toward +Y; the sea wraps around the point at the origin.
"""

import math

from mathutils import Vector, noise

from .mesh import MeshBuilder
from .terrain import smoothstep


class Headland:
    def __init__(self, rng, size=360.0, resolution=320, top=14.0, radius=32.0,
                 sea_floor=-9.0, ruggedness=1.0):
        self.size, self.res = size, resolution
        self.top, self.radius, self.floor = top, radius, sea_floor
        self.rug = ruggedness
        self.off = Vector((rng.uniform(-500, 500), rng.uniform(-500, 500), rng.uniform(0, 50)))
        self.lean = rng.uniform(-0.35, 0.35)   # the point bends left/right a little
        self.path = None
        self.flat = []

    def flatten_segment(self, *_a, **_k):   # API parity with Terrain (cliffs are not flattened)
        pass

    def inside(self, x, y):
        """Signed distance-ish: >0 on land. Disc at the point + band to the mainland."""
        p = Vector((x / 40.0, y / 40.0, 0)) + self.off
        wob = noise.fractal(p, 0.6, 2.0, 4) * 9.0 * self.rug
        # coves and buttresses: higher-frequency bites into the coastline
        q = Vector((x / 11.0, y / 11.0, 3.1)) + self.off
        wob += noise.ridged_multi_fractal(q, 1.0, 2.0, 3, 0.0, 1.0) * 3.0 * self.rug - 3.0
        d_disc = self.radius - math.hypot(x, y)
        bx = x - self.lean * max(y, 0.0)
        d_band = (self.radius * 0.85 - abs(bx)) if y > 0 else -1e9
        return max(d_disc, d_band) + wob

    def height(self, x, y):
        s = self.inside(x, y)
        # two-step profile: wave-cut rock shelf near sea level, then the main cliff,
        # with a rounded grassy brow on top (cliffs are never a knife edge)
        shelf = smoothstep(-16.0, -9.0, s)
        cliff = smoothstep(-6.5, 0.5, s)
        brow = smoothstep(0.0, 6.0, s)
        top = self.top + noise.noise(Vector((x / 25.0, y / 25.0, 0)) + self.off) * 1.2 \
            + 0.04 * max(y, 0)                                # land rises inland
        h = self.floor + (1.2 - self.floor) * shelf + (top - 2.0 - 1.2) * cliff + 2.0 * brow
        # gullies: vertical erosion stripes on the face, scale varies around the coast
        g = noise.ridged_multi_fractal(Vector((x / 3.5, y / 3.5, 0.3)) + self.off, 1.0, 2.0, 4, 0.0, 1.0)
        n = noise.fractal(Vector((x / 6.0, y / 6.0, 1.7)) + self.off, 0.7, 2.2, 4)
        face = (g * 1.4 + n * 1.6) * self.rug * (cliff * (1 - cliff)) * 4
        shelf_r = noise.fractal(Vector((x / 2.5, y / 2.5, 5.0)) + self.off, 0.6, 2.0, 3) \
            * 0.8 * shelf * (1 - cliff)                       # broken boulders on the shelf
        return h + face + shelf_r

    def normal(self, x, y, e=0.5):
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
                y = -s / 2 + i * step
                mb.verts.append((x, y, self.height(x, y)))
        for i in range(n):
            for j in range(n):
                a = i * (n + 1) + j
                mb.add_face((a, a + 1, a + n + 2, a + n + 1),
                            ((j, i), (j + 1, i), (j + 1, i + 1), (j, i + 1)))
        return mb.build("Terrain", [material])
