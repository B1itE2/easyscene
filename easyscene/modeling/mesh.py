"""Minimal mesh builder: accumulate verts/faces/UVs/material ids, emit one mesh.

Building whole objects (all logs of a cabin, all fronds of a tree) as a
single mesh keeps object counts low and Blender fast.
"""

import math

import bpy
from mathutils import Matrix, Vector


class MeshBuilder:
    def __init__(self):
        self.verts, self.faces, self.uvs, self.mats = [], [], [], []

    def add_face(self, idx, uv, mat=0):
        self.faces.append(tuple(idx))
        self.uvs.append(tuple(uv))
        self.mats.append(mat)

    def add_verts(self, pts, m: Matrix = None):
        base = len(self.verts)
        for p in pts:
            v = Vector(p)
            self.verts.append(tuple(m @ v) if m is not None else tuple(v))
        return base

    # -- primitives ---------------------------------------------------------
    def cylinder(self, length, r0, r1=None, segs=12, rings=1, m: Matrix = None, mat=0,
                 jitter=None, caps=True, uv_scale=1.0, bend=None):
        """Cylinder along local +X from 0..length. ``jitter(i_ring, j_seg)->scale``.
        ``bend(t)->(dy,dz)`` offsets the axis for slightly crooked logs/trunks."""
        r1 = r0 if r1 is None else r1
        ring_idx = []
        for i in range(rings + 1):
            t = i / rings
            r = r0 + (r1 - r0) * t
            dy, dz = bend(t) if bend else (0.0, 0.0)
            pts = []
            for j in range(segs):
                a = j / segs * math.tau
                k = jitter(i, j) if jitter else 1.0
                pts.append((t * length, dy + math.cos(a) * r * k, dz + math.sin(a) * r * k))
            ring_idx.append(self.add_verts(pts, m))
        circ = math.tau * max(r0, r1)
        for i in range(rings):
            a0, a1 = ring_idx[i], ring_idx[i + 1]
            for j in range(segs):
                j2 = (j + 1) % segs
                u0, u1 = i / rings * length * uv_scale, (i + 1) / rings * length * uv_scale
                v0, v1 = j / segs * circ * uv_scale, (j + 1) / segs * circ * uv_scale
                self.add_face((a0 + j, a0 + j2, a1 + j2, a1 + j),
                              ((u0, v0), (u0, v1), (u1, v1), (u1, v0)), mat)
        if caps:
            for idx, flip in ((ring_idx[0], True), (ring_idx[-1], False)):
                face = [idx + j for j in range(segs)]
                if flip:
                    face.reverse()
                uv = [(0.5 + 0.5 * math.cos(j / segs * math.tau) * 0.3,
                       0.5 + 0.5 * math.sin(j / segs * math.tau) * 0.3) for j in range(segs)]
                self.add_face(face, uv if not flip else uv[::-1], mat)
        return ring_idx

    def box(self, size, m: Matrix = None, mat=0, uv_scale=1.0):
        """Box of ``size`` (x,y,z) centred at origin, UVs in metres * uv_scale."""
        sx, sy, sz = (s / 2 for s in size)
        c = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
             (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
        b = self.add_verts(c, m)
        quads = [((0, 3, 2, 1), (2 * sx, 2 * sy)), ((4, 5, 6, 7), (2 * sx, 2 * sy)),
                 ((0, 1, 5, 4), (2 * sx, 2 * sz)), ((1, 2, 6, 5), (2 * sy, 2 * sz)),
                 ((2, 3, 7, 6), (2 * sx, 2 * sz)), ((3, 0, 4, 7), (2 * sy, 2 * sz))]
        for q, (w, h) in quads:
            w, h = w * uv_scale, h * uv_scale
            self.add_face([b + i for i in q], ((0, 0), (w, 0), (w, h), (0, h)), mat)

    def strip(self, rows, mat=0):
        """Quad strip from a list of rows of points (each row = cross-section).
        UV: u across (0..1), v along (0..1)."""
        n_rows, n_cols = len(rows), len(rows[0])
        base = len(self.verts)
        for row in rows:
            self.verts.extend(tuple(p) for p in row)
        for i in range(n_rows - 1):
            for j in range(n_cols - 1):
                a = base + i * n_cols + j
                self.add_face((a, a + 1, a + n_cols + 1, a + n_cols),
                              ((j / (n_cols - 1), i / (n_rows - 1)),
                               ((j + 1) / (n_cols - 1), i / (n_rows - 1)),
                               ((j + 1) / (n_cols - 1), (i + 1) / (n_rows - 1)),
                               (j / (n_cols - 1), (i + 1) / (n_rows - 1))), mat)

    # -- output -------------------------------------------------------------
    def build(self, name, materials=(), smooth=True, link=True):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.verts, [], self.faces)
        uv = me.uv_layers.new(name="UVMap")
        k = 0
        for poly, fuv in zip(me.polygons, self.uvs):
            for li, u in zip(poly.loop_indices, fuv):
                uv.data[li].uv = u
            k += 1
        for m in materials:
            me.materials.append(m)
        if materials:
            me.polygons.foreach_set("material_index", self.mats)
        me.polygons.foreach_set("use_smooth", [smooth] * len(me.polygons))
        me.validate(clean_customdata=False)
        me.update()
        obj = bpy.data.objects.new(name, me)
        if link:
            bpy.context.scene.collection.objects.link(obj)
        return obj


def frame(origin, x_axis, up=(0, 0, 1)) -> Matrix:
    """4x4 matrix whose local +X points along ``x_axis`` with Z roughly ``up``."""
    x = Vector(x_axis).normalized()
    z = Vector(up)
    y = z.cross(x)
    if y.length < 1e-6:
        y = Vector((0, 1, 0)).cross(x)
    y.normalize()
    z = x.cross(y).normalized()
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(origin)
    return m
