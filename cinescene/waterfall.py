"""Waterfalls: branching white-water ribbons that follow a cliff face.

A waterfall here is a small *system*:

* the **main fall** leaves the lip as one ballistic curtain that widens all the way
  into the pool, with a narrower companion curtain beside it;
* **side strands**: thin ribbons that seep from the lip or from ledges, hug the
  rock and break up into separate tongues;
* every strand is two offset sheets (front + back) so it reads as a thick body
  of falling water, with ragged edges, falling "heads" of aerated water and a
  bottom that dissolves into spray;
* the function returns impact points so the pool can churn and the fog shader
  can add spray exactly where water lands.

All shapes are seeded; the cliff is any object with ``height(x, y)``.
"""

import math

import bpy
from mathutils import Matrix, Vector, noise

from .modeling.mesh import MeshBuilder, frame
from .nodes import NB, new_material


# ------------------------------------------------------------------ material --
def white_water_material(name="WhiteWater", top=20.0):
    """Aerated falling water. UV: u across a strand (k + 0..1 per strand), v down (metres)."""
    mat, nb = new_material(name)
    uv = nb.coord("UV")
    u, v, _ = nb.sep(uv)
    t = nb.new("ShaderNodeValue")
    t.name = t.label = "cinescene_time"
    tt = t.outputs[0]
    ul = nb.math("FRACT", u)                                  # 0..1 across this strand
    sid = nb.math("FLOOR", u)                                 # strand id -> decorrelate noise
    flow = nb.math("SUBTRACT", v, nb.math("MULTIPLY", tt, 4.0))   # scrolls downward

    ox, _, oz = nb.sep(nb.coord("Object"))
    # vertical streaks (individual jets) at a fixed world density, two scales so they
    # are not a regular comb; streaks wander a little sideways as they fall
    wander = nb.math("MULTIPLY", nb.noise(nb.comb(ox, nb.math("MULTIPLY", oz, 0.15), 0.0), scale=0.35, detail=2.0), 1.2)
    xw = nb.math("ADD", ox, wander)
    s1 = nb.noise(nb.comb(nb.math("ADD", nb.math("MULTIPLY", xw, 2.2), nb.math("MULTIPLY", sid, 13.1)),
                          nb.math("MULTIPLY", flow, 0.12), 0.0), scale=1.0, detail=6.0, rough=0.6)
    s2 = nb.noise(nb.comb(nb.math("MULTIPLY", xw, 7.5), nb.math("MULTIPLY", flow, 0.35), 3.3),
                  scale=1.0, detail=8.0, rough=0.7)
    streak = nb.math("ADD", nb.math("MULTIPLY", s1, 0.6), nb.math("MULTIPLY", s2, 0.4))
    # big lumpy "heads" of aerated water that travel down the fall
    h_vec = nb.comb(nb.math("ADD", nb.math("MULTIPLY", ul, 3.0), nb.math("MULTIPLY", sid, 5.3)),
                    nb.math("MULTIPLY", flow, 0.18), nb.math("MULTIPLY", sid, 2.7))
    heads = nb.maprange(nb.noise(h_vec, scale=1.0, detail=3.0, rough=0.5), 0.4, 0.68)
    aer = nb.math("ADD", nb.math("MULTIPLY", nb.maprange(streak, 0.38, 0.72), 0.65),
                  nb.math("MULTIPLY", heads, 0.55))
    # water entrains air as it falls: glassy at the lip, solid white foam near the pool
    fallen = nb.maprange(oz, top, top * 0.25)
    aer = nb.math("ADD", nb.math("MULTIPLY", aer, nb.mixf(fallen, 0.75, 1.0)),
                  nb.math("MULTIPLY", fallen, 0.35))
    aer = nb.math("MINIMUM", aer, 1.0)

    # ragged edges: the strand's width is eaten by noise that also flows down
    e_noise = nb.noise(nb.comb(nb.math("MULTIPLY", sid, 7.7), nb.math("MULTIPLY", flow, 0.6), 0.0),
                       scale=1.0, detail=4.0)
    ragged = nb.maprange(e_noise, 0.3, 0.7, 0.06, 0.42)
    dx = nb.math("ABSOLUTE", nb.math("SUBTRACT", ul, 0.5))
    edge = nb.maprange(nb.math("SUBTRACT", 0.5, dx), 0.0, ragged)

    # vertex colour "fade" (0 at the strand bottom) lets each strand dissolve into spray
    fade = nb.o(nb.new("ShaderNodeVertexColor", layer_name="fade"), "Color")
    fr, _, _ = nb.sep(fade)
    alpha = nb.math("MULTIPLY", nb.math("MULTIPLY", nb.math("ADD", 0.18, nb.math("MULTIPLY", aer, 0.82)), edge), fr)
    alpha = nb.math("MINIMUM", alpha, 1.0)

    deep = (0.18, 0.26, 0.25)                                 # green-grey glassy water
    white = (0.9, 0.93, 0.93)
    col = nb.mix(aer, deep, white)
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    nb.set(bsdf, "Base Color", col)
    nb.set(bsdf, "Roughness", nb.mixf(aer, 0.08, 0.45))      # glassy where clear, matte where foamy
    nb.set(bsdf, "IOR", 1.33)
    nb.set(bsdf, "Alpha", alpha)
    tr = nb.new("ShaderNodeBsdfTranslucent", inputs={"Color": (0.8, 0.9, 0.88)})
    ms = nb.new("ShaderNodeMixShader", inputs={0: 0.25})     # glows when backlit
    nb.links.new(bsdf.outputs[0], ms.inputs[1])
    nb.links.new(tr.outputs[0], ms.inputs[2])
    tp = nb.new("ShaderNodeBsdfTransparent")
    ma = nb.new("ShaderNodeMixShader")
    nb.set(ma, 0, alpha)
    nb.links.new(tp.outputs[0], ma.inputs[1])
    nb.links.new(ms.outputs[0], ma.inputs[2])
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(ma.outputs[0], nb.i(out, "Surface"))
    return mat


# ------------------------------------------------------------------ geometry --
def _face_y(cliff, x, z, y_back, y_front):
    """Y of the cliff surface at (x, z): march from behind the face toward the viewer."""
    if hasattr(cliff, "face_y"):
        return cliff.face_y(x, z)
    y = y_back
    while cliff.height(x, y) > z and y > y_front:
        y -= 0.12
    return y


class _Strand:
    def __init__(self, x, z_top, z_bot, w_top, w_bot, push, lean=0.0, split=None, layer_gap=0.35):
        self.x, self.z_top, self.z_bot = x, z_top, z_bot
        self.w_top, self.w_bot = w_top, w_bot
        self.push = push                   # how far the water leaves the face (m) at the bottom
        self.lean = lean                   # sideways drift over the drop (m)
        self.split = split                 # None or (z_split, gap_m): open a gap below z_split
        self.layer_gap = layer_gap
        self.y_off = 0.0
        self.hug = 0.0                     # 0 = free-falling curtain, 1 = film running down the rock


def _emit_strand(mb, cliff, s, sid, y_back, y_front, seed, fade_cols, rows=36, cols=11,
                 fade_top=True, fade_bottom=True):
    """Two offset sheets per strand. Returns the impact point (x, y, z)."""
    pts_bottom = None
    # the curtain is ballistic: it leaves the lip and only ever moves *away* from the wall.
    # Following face_y row by row made the water kink in and out with every rock bed,
    # which read as horizontal stripes (a striped cloth pinned to a brick wall).
    xl = s.x
    y_lip = _face_y(cliff, xl, s.z_top, y_back, y_front)
    for layer in (0, 1):
        grid = []
        fade_rows = []
        y_prev = None
        for i in range(rows + 1):
            t = i / rows
            z = s.z_top + (s.z_bot - s.z_top) * t
            xc = s.x + s.lean * t * t
            off = 0.25 + layer * s.layer_gap + s.y_off
            y_ball = y_lip - s.push * (t ** 0.6) - off
            y_rock = _face_y(cliff, xc, z, y_back, y_front) - off - 0.15 * s.hug
            # hugging strands follow the rock a little; the main curtain clears it
            y = min(y_ball, y_rock) if s.hug < 0.5 else y_rock - s.push * (t ** 0.6)
            if y_prev is not None:
                y = min(y, y_prev + 0.02 * s.hug)
            y_prev = y
            w = s.w_top + (s.w_bot - s.w_top) * t
            row = []
            for k in range(cols):
                c = k / (cols - 1) - 0.5
                xx = xc + c * w
                if s.split and z < s.split[0]:
                    g = s.split[1] * min(1.0, (s.split[0] - z) / 2.0)      # gap opens below the rock
                    xx += math.copysign(g / 2, c) if abs(c) > 1e-6 else 0.0
                wob = noise.noise(Vector((xx * 0.4 + seed, z * 0.25, sid + layer * 3.3)))
                bulge = 0.15 * (1 - (2 * c) ** 2)                          # rounded front
                row.append((xx + wob * (0.25 if s.hug else 0.12), y - bulge + wob * 0.15, z))
            grid.append(row)
            # fade to 0 over the last 15 % (spray hides the end) and 6 % at the lip
            f = (min(1.0, t / 0.06) if fade_top else 1.0) * (min(1.0, (1 - t) / 0.15) if fade_bottom else 1.0)
            fade_rows.append(f)
        base = len(mb.verts)
        for row in grid:
            mb.verts.extend(row)
        for i in range(rows):
            for k in range(cols - 1):
                a = base + i * cols + k
                lid = 2 * sid + layer                 # each sheet gets its own noise (FLOOR(u))
                u0 = lid + 0.999 * k / (cols - 1)
                u1 = lid + 0.999 * (k + 1) / (cols - 1)
                v0 = s.z_top - grid[i][0][2]
                v1 = s.z_top - grid[i + 1][0][2]
                mb.add_face((a, a + 1, a + cols + 1, a + cols), ((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
                fade_cols.append((fade_rows[i], fade_rows[i], fade_rows[i + 1], fade_rows[i + 1]))
        pts_bottom = grid[-1]
    mid = pts_bottom[len(pts_bottom) // 2]
    return (mid[0], mid[1], mid[2])


def build(cliff, rng, cfg: dict, lip_x: float, top: float, y_back: float, y_front: float):
    """Create the whole waterfall. Returns dict(objects, impacts, lip, width, outcrop)."""
    W = cfg["width"]
    sid = 0
    mb = MeshBuilder()
    fade = []
    impacts = []
    seed = rng.uniform(0, 100)
    pool_z = cfg.get("pool_z", -0.15)

    # main fall: one continuous curtain from the lip into the pool, widening as it falls,
    # plus a narrower companion curtain beside it so the silhouette is not a rectangle.
    # (An earlier version split the fall around a buttress halfway down; the two halves
    # never lined up and left a hard horizontal seam.)
    z_split = top * 0.5
    lean = rng.uniform(-0.6, 0.6)
    push = rng.uniform(1.6, 2.3)
    xs = lip_x + lean
    main = _Strand(lip_x, top, pool_z - 0.2, W, W * 1.45, push=push, lean=lean)
    ip = _emit_strand(mb, cliff, main, sid, y_back, y_front, seed, fade, rows=90, cols=19)
    impacts.append((ip[0], ip[1], pool_z, W * 0.55))
    sid += 1
    side = rng.choice((-1, 1))
    w2 = W * rng.uniform(0.25, 0.4)
    cx = lip_x + side * (W / 2 + w2 * 0.35)
    z2 = top - rng.uniform(0.0, 1.5)
    comp = _Strand(cx, z2, pool_z - 0.2, w2, w2 * 1.8, push=push * 0.8, lean=side * rng.uniform(0.4, 1.2))
    comp.y_off = 0.3
    ip = _emit_strand(mb, cliff, comp, sid, y_back, y_front, seed, fade, rows=80, cols=11)
    impacts.append((ip[0], ip[1], pool_z, w2 * 0.8))
    sid += 1
    gap = 0.0

    # side strands: thin, hugging the rock, some starting below the lip (seeps/ledges)
    n_side = rng.randint(cfg.get("side_min", 2), cfg.get("side_max", 4))
    for k in range(n_side):
        side = -1 if k % 2 == 0 else 1
        off = side * (W / 2 + rng.uniform(1.2, 4.5) + (k // 2) * 2.0)
        z0 = top - rng.choice((0.0, 0.0, rng.uniform(2.0, top * 0.35)))
        w0 = rng.uniform(0.25, 0.7)
        st = _Strand(lip_x + off, z0, pool_z - 0.2, w0, w0 * rng.uniform(1.6, 2.6),
                     push=rng.uniform(0.1, 0.3), lean=side * rng.uniform(0.2, 0.8), layer_gap=0.12)
        st.hug = 1.0
        ip = _emit_strand(mb, cliff, st, sid, y_back, y_front, seed, fade, rows=30, cols=7)
        impacts.append((ip[0], ip[1], pool_z, w0 * 1.5))
        sid += 1

    obj = mb.build("Waterfall", [white_water_material(top=top)], smooth=True)
    # per-corner fade colour (red channel), same face order as mb.faces
    ca = obj.data.color_attributes.new("fade", "FLOAT_COLOR", "CORNER")
    for poly, fc in zip(obj.data.polygons, fade):
        for li, f in zip(poly.loop_indices, fc):
            ca.data[li].color = (f, f, f, 1.0)
    obj.visible_shadow = False

    # the outcrop that splits the main fall: a wet boulder jutting from the face
    oy = _face_y(cliff, xs, z_split, y_back, y_front) - push * 0.6 - 0.9   # juts through the curtain
    rock = None
    if cfg.get("outcrop", True) and not hasattr(cliff, "face_y"):
        import bmesh
        me = bpy.data.meshes.new("Outcrop")
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
        for v in bm.verts:
            v.co *= 1.0 + 0.3 * noise.fractal(v.co * 1.5 + Vector((seed, 0, 0)), 0.5, 2.0, 4)
            v.co.x *= gap * 0.55 + 0.4
            v.co.y *= 2.6
            v.co.z *= 0.75
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        rock = bpy.data.objects.new("Outcrop", me)
        rock.location = (xs, oy + 1.3, z_split - 0.35)          # rooted in the wall, juts out
        bpy.context.scene.collection.objects.link(rock)
    return {"objects": [o for o in (obj, rock) if o], "impacts": impacts, "lip": (lip_x, oy, top),
            "width": W, "outcrop": rock, "split_z": z_split}


# ------------------------------------------------------------------- mist ---
def add_mist(fog_obj, fall: dict, cfg: dict):
    """Spray at every impact + a thin veil of mist hanging in front of the falls.

    Merged into the fog material (one volume, no box seams)."""
    mat = fog_obj.data.materials[0]
    nb = NB(mat.node_tree, clear=False)
    P = nb.coord("Object")
    t = mat.node_tree.nodes["cinescene_time"].outputs[0]
    total = None
    for (x, y, z, r) in fall["impacts"]:
        p = nb.vmath("SUBTRACT", P, (x, y, z))
        px, py, pz = nb.sep(p)
        rr = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", px, px), nb.math("MULTIPLY", py, py)))
        big = min(1.0, max(0.0, (r - 0.3) / 1.7))          # main curtains boil, seeps barely mist
        R = r + cfg["radius_m"] * (0.4 + 0.6 * big)
        radial = nb.maprange(rr, 0.0, R, 1.0, 0.0, interp="SMOOTHSTEP")
        vert = nb.math("EXPONENT", nb.math("DIVIDE", nb.math("MAXIMUM", pz, 0.0), -cfg["height_m"] * (0.5 + r / 3)))
        d = nb.math("MULTIPLY", nb.math("MULTIPLY", radial, vert), 0.25 + 0.75 * big)
        total = d if total is None else nb.math("MAXIMUM", total, d)
    # veil: thin slab in front of the whole fall, densest low down
    lx, ly, top = fall["lip"]
    ly = fall["impacts"][0][1]
    px, py, pz = nb.sep(nb.vmath("SUBTRACT", P, (lx, ly - 1.5, 0.0)))
    slab = nb.math("MULTIPLY", nb.maprange(nb.math("ABSOLUTE", px), fall["width"] * 2.2, fall["width"] * 0.6,
                                           interp="SMOOTHSTEP"),
                   nb.maprange(nb.math("ABSOLUTE", py), 3.5, 0.5, interp="SMOOTHSTEP"))
    slab = nb.math("MULTIPLY", slab, nb.maprange(pz, top * 0.35, 0.0, 0.0, 0.25))  # only low down
    total = nb.math("MAXIMUM", total, slab)
    puff = nb.maprange(nb.noise(P, scale=0.45, detail=5.0, dims="4D", w=nb.math("MULTIPLY", t, 0.4)),
                       0.3, 0.72, 0.1, 1.4)
    dens = nb.math("MULTIPLY", nb.math("MULTIPLY", total, puff), cfg["density"])
    svol = nb.new("ShaderNodeVolumePrincipled", inputs={"Color": (0.95, 0.97, 0.98), "Anisotropy": 0.55})
    nb.set(svol, "Density", dens)
    out = [n for n in nb.nodes if n.bl_idname == "ShaderNodeOutputMaterial"][0]
    prev = out.inputs["Volume"].links[0].from_socket
    add = nb.new("ShaderNodeAddShader")
    nb.links.new(prev, add.inputs[0])
    nb.links.new(svol.outputs[0], add.inputs[1])
    nb.links.new(add.outputs[0], out.inputs["Volume"])


# ------------------------------------------------------------ pool churn ---
def pool_material(impacts, deep=(0.01, 0.03, 0.025)):
    """Plunge-pool water: dark and reflective, white churning foam + strong ripples at impacts."""
    from .water import water_material
    mat = water_material("PlungePool", deep=deep, rough=0.02, ripple=0.25)
    nb = NB(mat.node_tree, clear=False)
    world = nb.o(nb.new("ShaderNodeNewGeometry"), "Position")
    t = mat.node_tree.nodes["cinescene_time"].outputs[0]
    near = None
    for (x, y, _z, r) in impacts:
        d = nb.vmath("DISTANCE", world, (x, y, 0.0), out="Value")
        f = nb.maprange(d, r * 0.4, r + 2.5, 1.0, 0.0, interp="SMOOTHSTEP")
        near = f if near is None else nb.math("MAXIMUM", near, f)
    churn = nb.maprange(nb.noise(world, scale=1.6, detail=8.0, rough=0.7, dims="4D",
                                 w=nb.math("MULTIPLY", t, 0.8)), 0.35, 0.65)
    foam = nb.math("MULTIPLY", near, churn, clamp=True)
    # expanding rings of foam drifting away from the impacts
    ring_n = nb.noise(world, scale=0.35, detail=2.0)
    rings = nb.maprange(nb.math("SINE", nb.math("ADD", nb.math("MULTIPLY", ring_n, 30.0),
                                                     nb.math("MULTIPLY", t, -2.0))), 0.7, 1.0)
    far = nb.maprange(near, 0.0, 0.4)
    foam = nb.math("MAXIMUM", foam, nb.math("MULTIPLY", nb.math("MULTIPLY", rings, far), 0.35))
    bsdf = [n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"][0]
    old_col = bsdf.inputs["Base Color"].default_value[:]
    nb.set(bsdf, "Base Color", nb.mix(foam, old_col, (0.82, 0.86, 0.86)))
    nb.set(bsdf, "Roughness", nb.mixf(foam, 0.02, 0.5))
    bump = [n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBump"][0]
    hsrc = bump.inputs["Height"].links[0].from_socket
    nb.set(bump, "Height", nb.math("ADD", hsrc, nb.math("MULTIPLY", near, nb.math("MULTIPLY", churn, 3.0))))
    return mat
