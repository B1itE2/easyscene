"""Lake shore: a bay of calm water (z < 0) with wooded banks rising behind.

The shoreline runs along +X near y = 0 and curves toward the camera on both
sides, so trees frame the shot left and right and mirror in the water.
Water level is z = 0. Same contract as ``terrain.Terrain``.
"""

import math

from mathutils import Vector, noise

from .mesh import MeshBuilder
from .terrain import smoothstep


class LakeShore:
    def __init__(self, rng, size=320.0, resolution=260, bay=0.004, hills=6.0, depth=3.5):
        self.size, self.res = size, resolution
        self.bay, self.hills, self.depth = bay, hills, depth
        self.off = Vector((rng.uniform(-500, 500), rng.uniform(-500, 500), rng.uniform(0, 50)))
        self.path = None
        self.flat = []

    def flatten_segment(self, *_a, **_k):
        pass

    def shore_y(self, x):
        return noise.noise(Vector((x / 35.0, 0.3, 0)) + self.off) * 5.0 - self.bay * x * x

    def signed(self, x, y):
        """> 0 on land, < 0 in the lake (metres from the shoreline, roughly)."""
        return y - self.shore_y(x)

    def height(self, x, y):
        s = self.signed(x, y)
        bank = smoothstep(-1.5, 2.5, s)
        land = 0.25 + 0.6 * smoothstep(0, 12, s) \
            + noise.fractal(Vector((x / 45.0, y / 45.0, 0)) + self.off, 0.6, 2.0, 4) * self.hills \
            * smoothstep(8, 40, s) + 0.05 * max(s - 20, 0)
        bottom = -self.depth * smoothstep(0, 14, -s) - 0.3
        fine = noise.noise(Vector((x / 4.0, y / 4.0, 1.0)) + self.off) * 0.12
        return bottom + (land - bottom) * bank + fine

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
                y = -s / 2 + i * step + s * 0.25        # most of the grid on the land side
                mb.verts.append((x, y, self.height(x, y)))
        for i in range(n):
            for j in range(n):
                a = i * (n + 1) + j
                mb.add_face((a, a + 1, a + n + 2, a + n + 1),
                            ((j, i), (j + 1, i), (j + 1, i + 1), (j, i + 1)))
        return mb.build("Terrain", [material])
