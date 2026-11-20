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
        # heightfield cliff sits 4 m *behind* the dedicated wall mesh (build_wall), so the
        # wall's alcoves and overhangs are never covered by stretched heightfield faces
        back = 4.0 if hasattr(self, "alcove") else 0.0
        cliff = smoothstep(self.cy - 1.5 + back, self.cy + 1.0 + back, y + n * 1.5 + ledge * 0.6) * self.ch
        # add, don't max(): side/cliff are >= 0 and would flatten the pool basin to 0
        h = pool + bank + max(side, cliff) + n * 0.4
        return h

    # ---- dedicated cliff wall (a heightfield can't do a good vertical face) --------
    def set_alcove(self, x, width):
        self.alcove = (x, width)

    def face_y(self, x, z):
        """Y of the cliff wall surface at (x, z). Smaller y = sticks out toward the camera."""
        y0 = self.cy - 1.2
        # Natural cliffs are not a stack of level shelves: beds dip and warp, vary in
        # thickness, and vertical joints break them into offset blocks. (The old version
        # used level beds of near-constant thickness -> it read as a brick wall.)
        warp = noise.noise(Vector((x / 18.0, 0.0, 2.2)) + self.off) * 1.6
        zz = z + 0.09 * x + warp                                  # dipping, warped bedding
        bed = noise.noise(Vector((x / 25.0, 0.0, zz / 3.0)) + self.off)
        f = zz / 2.6 + bed * 1.3
        step = math.floor(f)
        frac = f - step
        # vertical joints: columns 2.5-5 m wide, each pushed in/out a little
        jx = x / 3.6 + noise.noise(Vector((z / 6.0, 4.4, 0.0)) + self.off) * 0.9
        col = math.floor(jx)
        joint = noise.noise(Vector((col * 1.91, step * 0.7, 5.5)) + self.off) * 0.9
        jedge = abs(jx - col - 0.5) * 2.0                         # 1 at a joint, 0 mid-block
        crack = 0.35 * smoothstep(0.85, 1.0, jedge)
        jut = noise.noise(Vector((step * 1.37, x / 7.0, 0.0)) + self.off) * 1.1 + joint
        # beds erode back at their bottom edge, unevenly
        uc_amt = 0.2 + 0.3 * (0.5 + 0.5 * noise.noise(Vector((x / 5.0, step, 7.7)) + self.off))
        undercut = uc_amt * (1.0 - smoothstep(0.0, 0.25, frac))
        # big rounded bulges and hollows over the whole face
        bulge = noise.fractal(Vector((x / 9.0, z / 7.0, 9.1)) + self.off, 0.6, 2.0, 3) * 1.1
        rough = noise.fractal(Vector((x / 2.2, z / 2.2, 0.7)) + self.off, 0.6, 2.1, 5) * 0.6
        cracks = noise.ridged_multi_fractal(Vector((x / 3.0, z / 9.0, 1.1)) + self.off, 1.0, 2.0, 3, 0.0, 1.0) * 0.3
        y = y0 - jut - bulge + undercut - rough + cracks + crack
        ax, aw = getattr(self, "alcove", (0.0, 0.0))
        if aw:                                   # the falls carve an alcove behind themselves
            g = math.exp(-((x - ax) / (aw * 0.9)) ** 2)
            y += 2.2 * g * smoothstep(-1.0, self.ch * 0.6, z) * (1 - smoothstep(self.ch * 0.8, self.ch, z))
        nose = getattr(self, "nose", None)
        if nose:                                 # rock buttress that splits the falls
            nx_, nz_, nw = nose
            g = math.exp(-((x - nx_) / nw) ** 2) * math.exp(-((z - nz_) / (nw * 1.3)) ** 2)
            top_flat = 1.0 - smoothstep(nz_ + nw * 0.2, nz_ + nw * 1.2, z)    # flat-ish top: water lands on it
            y -= 2.6 * g * (0.6 + 0.4 * top_flat)
        # fine surface relief so the rock reads at 1080p
        y -= noise.fractal(Vector((x / 0.7, z / 0.7, 3.3)) + self.off, 0.55, 2.2, 4) * 0.12
        # caprock: the top bed overhangs a little
        y -= 0.8 * smoothstep(self.ch - 2.5, self.ch - 0.6, z)
        return y

    def ledge_spots(self, rng, n, x_half, avoid):
        """(x, y, z) on top of protruding beds: where the wall just below sticks out further."""
        out, tries = [], 0
        while len(out) < n and tries < n * 40:
            tries += 1
            x = rng.uniform(-x_half, x_half)
            z = rng.uniform(1.0, self.ch - 0.5)
            if any(abs(x - ax) < aw for ax, aw in avoid):
                continue
            here, below = self.face_y(x, z), self.face_y(x, z - 0.35)
            if below < here - 0.3:                   # a shelf sticks out under this point
                out.append((x, below + 0.25, z - 0.3))
        return out

    def build_wall(self, material, x_half=30.0, step=0.15):
        mb = MeshBuilder()
        nx = int(2 * x_half / step)
        z0, z1 = -2.5, self.ch + 0.6
        nz = int((z1 - z0) / step)
        for i in range(nz + 1):
            z = z0 + (z1 - z0) * i / nz
            for j in range(nx + 1):
                x = -x_half + 2 * x_half * j / nx
                # fade the wall back into the side slopes at the ends
                end = smoothstep(x_half * 0.7, x_half, abs(x))
                y = self.face_y(x, z) + end * 6.0
                mb.verts.append((x, y, z))
        # cap: roll the top edge back over the brow to meet the plateau behind it
        for k, (dy, dz) in enumerate(((0.6, 0.35), (1.6, 0.6), (3.0, 0.75), (5.5, 0.8))):
            for j in range(nx + 1):
                x = -x_half + 2 * x_half * j / nx
                end = smoothstep(x_half * 0.7, x_half, abs(x))
                yb = self.face_y(x, z1) + end * 6.0
                mb.verts.append((x, yb + dy, z1 + dz + noise.noise(Vector((x / 3, k, 0)) + self.off) * 0.2))
        nz += 4
        for i in range(nz):
            for j in range(nx):
                a = i * (nx + 1) + j
                mb.add_face((a, a + nx + 1, a + nx + 2, a + 1), ((j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i)))
        return mb.build("CliffWall", [material])

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


def waterfall_material(time_node_name="easyscene_time"):
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
