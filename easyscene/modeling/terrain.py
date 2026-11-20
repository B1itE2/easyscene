"""Terrain: a clearing for the subject, rolling hills that rise behind it.

``Terrain.height(x, y)`` is the exact surface used for the mesh, so
scattered objects sit on the ground (not floating, not buried).
"""

import math

import bpy
from mathutils import Vector, noise

from .mesh import MeshBuilder


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


class Path:
    """A trodden footpath: polyline + width. Used by the ground shader (mud strip),
    by scattering (no plants on it) and by the terrain (slightly sunk)."""

    def __init__(self, points, width=0.9):
        self.points = [tuple(p) for p in points]
        self.width = width

    @classmethod
    def from_door(cls, rng, door_xy, toward_xy, length=26.0, width=0.9):
        """Meander from the door step toward a point (usually beside the camera)."""
        start = Vector((door_xy[0], door_xy[1], 0))
        goal = Vector((toward_xy[0], toward_xy[1], 0))
        d = (goal - start).normalized()
        side = Vector((-d.y, d.x, 0))
        pts = [start]
        n = 5
        for i in range(1, n + 1):
            t = i / n
            wig = math.sin(t * math.pi * rng.uniform(0.8, 1.6)) * rng.uniform(0.6, 1.6)
            pts.append(start + d * (length * t) + side * wig * t)
        return cls([(p.x, p.y) for p in pts], width)

    def dist(self, x, y):
        best = 1e9
        for (x0, y0), (x1, y1) in zip(self.points, self.points[1:]):
            vx, vy = x1 - x0, y1 - y0
            t = max(0.0, min(1.0, ((x - x0) * vx + (y - y0) * vy) / (vx * vx + vy * vy)))
            best = min(best, math.hypot(x - x0 - vx * t, y - y0 - vy * t))
        return best


class Terrain:
    def __init__(self, rng, size=260.0, resolution=200, clearing=11.0, hills=5.0,
                 back_slope=0.06, center=(0.0, 0.0)):
        self.size, self.res = size, resolution
        self.clearing, self.hills, self.back_slope = clearing, hills, back_slope
        self.cx, self.cy = center
        # seed = offset into the noise field (mathutils.noise has no seed argument)
        self.off = Vector((rng.uniform(-500, 500), rng.uniform(-500, 500), rng.uniform(0, 50)))
        self.flat = []   # (x0, y0, x1, y1, half_width): sight lines kept free of hills
        self.path = None

    def flatten_segment(self, p0, p1, half_width):
        """Keep the ground low and gentle along a sight line (camera -> subject)."""
        self.flat.append((p0[0], p0[1], p1[0], p1[1], half_width))

    def _flat_mask(self, x, y):
        m = 1.0
        for x0, y0, x1, y1, w in self.flat:
            vx, vy = x1 - x0, y1 - y0
            t = max(0.0, min(1.0, ((x - x0) * vx + (y - y0) * vy) / (vx * vx + vy * vy)))
            d = math.hypot(x - x0 - vx * t, y - y0 - vy * t)
            m = min(m, smoothstep(w, w * 2.5, d))
        return m

    def height(self, x, y):
        r = math.hypot(x - self.cx, y - self.cy)
        p = Vector((x / 45.0, y / 45.0, 0)) + self.off
        big = noise.fractal(p, 0.6, 2.1, 4, noise_basis="PERLIN_NEW")
        fine = noise.noise(Vector((x / 6.0, y / 6.0, 0)) + self.off, noise_basis="PERLIN_NEW")
        mask = smoothstep(self.clearing, self.clearing + 25.0, r) * self._flat_mask(x, y)
        h = big * self.hills * mask + fine * (0.12 + 0.35 * mask)
        h += self.back_slope * max(0.0, (y - self.cy) - 8.0) * mask   # rises behind subject
        h *= smoothstep(4.0, 9.0, r) * 0.85 + 0.15                     # flat pad for subject
        if self.path is not None:                                        # trodden: a few cm lower
            h -= 0.05 * (1.0 - smoothstep(self.path.width * 0.3, self.path.width, self.path.dist(x, y)))
        return h

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
                x = -s / 2 + j * step + self.cx
                y = -s / 2 + i * step + self.cy
                mb.verts.append((x, y, self.height(x, y)))
        for i in range(n):
            for j in range(n):
                a = i * (n + 1) + j
                mb.add_face((a, a + 1, a + n + 2, a + n + 1),
                            ((j, i), (j + 1, i), (j + 1, i + 1), (j, i + 1)))
        obj = mb.build("Terrain", [material])
        return obj
