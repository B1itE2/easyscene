"""Camera moves: route planning, easing, obstacle clearance, keyframing.

Every preset is a *planner* that turns the scene layout into a few control
points (camera position + look target). The shared machinery then
* builds a smooth cubic Bezier route through them,
* re-parametrises it by arc length so speed is controlled only by easing
  (slow start, fast middle, slow end),
* derives yaw/pitch with zero roll from the look target (no Dutch angle,
  no sudden head turns), and
* clears trees whose crowns/trunks come too close to the route.

Presets: cloud_descent (implemented); orbit, push_in, low_flyover (reserved).
"""

import math

from mathutils import Vector


# ------------------------------------------------------------------ easing ---
def smootherstep(u):
    u = max(0.0, min(1.0, u))
    return u * u * u * (u * (u * 6 - 15) + 10)


class Ease:
    """Dolly-style speed profile: smooth (cosine) acceleration over the first
    ``accel`` fraction of the shot, constant cruise, smooth deceleration over
    the last ``decel``. Speed is exactly zero at both ends, but unlike
    smootherstep it does not crawl for seconds before stopping.
    """

    def __init__(self, accel=0.25, decel=0.35, n=2000):
        def v(u):
            if u < accel:
                return 0.5 - 0.5 * math.cos(math.pi * u / accel)
            if u > 1 - decel:
                return 0.5 - 0.5 * math.cos(math.pi * (1 - u) / decel)
            return 1.0
        self.table = [0.0]
        for i in range(n):
            self.table.append(self.table[-1] + v((i + 0.5) / n) / n)
        total = self.table[-1]
        self.table = [t / total for t in self.table]
        self.n = n

    def __call__(self, u):
        u = max(0.0, min(1.0, u))
        f = u * self.n
        i = min(int(f), self.n - 1)
        return self.table[i] + (self.table[i + 1] - self.table[i]) * (f - i)


# ------------------------------------------------------------------ curves ---
def bezier(p0, p1, p2, p3, t):
    a = 1 - t
    return p0 * a ** 3 + p1 * 3 * a * a * t + p2 * 3 * a * t * t + p3 * t ** 3


class Route:
    """Cubic Bezier route with arc-length lookup."""

    def __init__(self, ctrl, samples=2000):
        self.ctrl = [Vector(c) for c in ctrl]
        self.pts = [bezier(*self.ctrl, i / samples) for i in range(samples + 1)]
        self.cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + (b - a).length)
        self.length = self.cum[-1]

    def at_distance(self, s):
        """Point at arc length s (linear search on the cumulative table; fine for 2k)."""
        s = max(0.0, min(self.length, s))
        lo, hi = 0, len(self.cum) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cum[mid] < s:
                lo = mid
            else:
                hi = mid
        seg = self.cum[hi] - self.cum[lo]
        f = 0.0 if seg == 0 else (s - self.cum[lo]) / seg
        return self.pts[lo].lerp(self.pts[hi], f)


# ------------------------------------------------------------------- shot ---
class Shot:
    """Per-frame camera samples plus helpers to apply and validate them."""

    def __init__(self, preset, positions, targets, fps, info=None):
        self.preset = preset
        self.positions = positions
        self.targets = targets
        self.fps = fps
        self.info = info or {}

    @property
    def frames(self):
        return len(self.positions)

    def yaw_pitch(self, i):
        d = self.targets[i] - self.positions[i]
        yaw = math.atan2(-d.x, d.y)
        pitch = math.atan2(d.z, math.hypot(d.x, d.y))
        return yaw, pitch

    # ---- validation ---------------------------------------------------------
    def angular_speeds(self):
        """Degrees per frame between consecutive view directions."""
        out = []
        prev = None
        for p, t in zip(self.positions, self.targets):
            d = (t - p).normalized()
            if prev is not None:
                out.append(math.degrees(prev.angle(d, 0.0)))
            prev = d
        return out

    def stats(self):
        sp = self.angular_speeds()
        steps = [(b - a).length for a, b in zip(self.positions, self.positions[1:])]
        return {
            "frames": self.frames, "fps": self.fps,
            "route_length_m": round(sum(steps), 2),
            "max_turn_deg_per_frame": round(max(sp), 3) if sp else 0.0,
            "max_speed_m_s": round(max(steps) * self.fps, 2) if steps else 0.0,
            "start_speed_m_s": round(steps[0] * self.fps, 3) if steps else 0.0,
            "end_speed_m_s": round(steps[-1] * self.fps, 3) if steps else 0.0,
            **self.info,
        }

    # ---- obstacle clearance ---------------------------------------------------
    def clear_trees(self, points, variant_dims, margin=1.2, low_only=True):
        """Drop trees that the route would pass through.

        points: scatter tuples (x, y, z, rx, ry, rz, scale, vid)
        variant_dims[vid] = (height, crown_radius, crown_base)
        Crown is modelled as a cone from crown_base (radius crown_radius)
        to the top (radius 0); below crown_base only the trunk (0.5 m) counts.
        """
        samples = self.positions[::2]
        kept, removed = [], 0
        for p in points:
            h, cr, cb = variant_dims[p[7]]
            s = p[6]
            h, cr, cb = h * s, cr * s, cb * s
            top = p[2] + h
            hit = False
            for c in samples:
                if c.z > top + margin:
                    continue
                rel = c.z - p[2]
                if rel < cb:
                    rad = 0.5
                else:
                    rad = cr * max(0.0, (h - rel) / max(h - cb, 1e-3)) + 0.3
                if math.hypot(c.x - p[0], c.y - p[1]) < rad + margin:
                    hit = True
                    break
            if hit:
                removed += 1
            else:
                kept.append(p)
        self.info["trees_cleared"] = self.info.get("trees_cleared", 0) + removed
        return kept

    def min_ground_clearance(self, terrain):
        return min(c.z - terrain.height(c.x, c.y) for c in self.positions)

    def inside_box(self, bounds_xy, z_range):
        x0, x1, y0, y1 = bounds_xy
        return sum(1 for c in self.positions
                   if x0 < c.x < x1 and y0 < c.y < y1 and z_range[0] < c.z < z_range[1])

    # ---- Blender ---------------------------------------------------------------
    def apply(self, cam_obj, fstop, frame_start=1):
        """Key location, rotation (yaw/pitch, zero roll) and focus on every frame."""
        import bpy
        scene = bpy.context.scene
        scene.frame_start = frame_start
        scene.frame_end = frame_start + self.frames - 1
        scene.render.fps = self.fps
        cam = cam_obj.data
        cam.dof.use_dof = True
        cam.dof.aperture_fstop = fstop
        cam.shift_x = 0.0
        prev_yaw = None
        for i in range(self.frames):
            f = frame_start + i
            yaw, pitch = self.yaw_pitch(i)
            if prev_yaw is not None:                     # unwrap: never spin the long way
                while yaw - prev_yaw > math.pi:
                    yaw -= math.tau
                while yaw - prev_yaw < -math.pi:
                    yaw += math.tau
            prev_yaw = yaw
            cam_obj.location = self.positions[i]
            cam_obj.rotation_euler = (math.pi / 2 + pitch, 0.0, yaw)
            cam.dof.focus_distance = (self.targets[i] - self.positions[i]).length
            cam_obj.keyframe_insert("location", frame=f)
            cam_obj.keyframe_insert("rotation_euler", frame=f)
            cam.dof.keyframe_insert("focus_distance", frame=f)
        for owner in (cam_obj, cam):
            ad = owner.animation_data
            if ad and ad.action:
                from .atmosphere import _fcurves
                for fc in _fcurves(ad.action):
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"


def _sample(route, t0, t1, frames, easing):
    positions, targets = [], []
    for i in range(frames):
        u = i / (frames - 1) if frames > 1 else 1.0
        e = easing(u)
        positions.append(route.at_distance(e * route.length))
        targets.append(t0.lerp(t1, smootherstep(e)))
    return positions, targets


# ---------------------------------------------------------------- presets ---
def cloud_descent(layout, terrain, cfg, duration_s, fps):
    """Start high inside a cloud bank looking down, sink through the canopy level,
    level out and settle at eye height in front of the subject (subject centred).

    The route stays in the vertical plane through the subject and the final
    camera position, so yaw never changes: the only rotation is pitch, from
    ~80 deg down to level. No head swings by construction.
    """
    sub = layout["subject"]
    fin = layout["camera"]
    C = Vector((sub["center"][0], sub["center"][1], 0.0))
    F = Vector(fin["location"])
    flat = Vector((F.x - C.x, F.y - C.y, 0.0))
    D = flat.length
    d = flat.normalized()
    z0 = cfg["start_height_m"]
    s0 = cfg["start_offset"] * D
    zf = F.z
    p0 = C + d * s0 + Vector((0, 0, z0))
    p1 = C + d * (s0 + 0.05 * D) + Vector((0, 0, z0 * cfg.get("drop_bias", 0.5)))
    p2 = C + d * (0.8 * D) + Vector((0, 0, zf + cfg.get("level_out_m", 2.5)))
    route = Route([p0, p1, p2, F])
    t0 = Vector((C.x, C.y, 1.0))
    t1 = Vector(fin["target"])
    frames = int(round(duration_s * fps)) + 1
    ez = cfg.get("ease", {})
    pos, tgt = _sample(route, t0, t1, frames, Ease(ez.get("accel", 0.25), ez.get("decel", 0.35)))
    # never closer than 1.2 m to the ground (terrain may bulge under the route)
    for i, c in enumerate(pos):
        g = terrain.height(c.x, c.y) + 1.2
        if c.z < g:
            pos[i] = Vector((c.x, c.y, g))
    return Shot("cloud_descent", pos, tgt, fps,
                {"start": tuple(round(v, 2) for v in p0), "end": tuple(round(v, 2) for v in F),
                 "cloud_center_xy": (p0.x, p0.y)})


def orbit(layout, terrain, cfg, duration_s, fps):
    """Circle around the subject, always looking at it, landing on the hero framing.

    Radius and height interpolate from a start setting to the final camera, so
    the move can also spiral in. Yaw changes smoothly (angular speed is checked
    in stats); clearance above terrain is enforced per frame.
    """
    sub = layout["subject"]
    fin = layout["camera"]
    C = Vector((sub["center"][0], sub["center"][1], 0.0))
    F = Vector(fin["location"])
    a1 = math.atan2(F.y - C.y, F.x - C.x)
    r1 = math.hypot(F.x - C.x, F.y - C.y)
    sweep = math.radians(cfg["sweep_deg"]) * cfg.get("direction", 1)
    a0 = a1 - sweep
    r0 = r1 * cfg.get("start_radius_scale", 1.0)
    z0 = F.z + cfg.get("start_rise_m", 0.0)
    t_end = Vector(fin["target"])
    t_start = t_end + Vector((0, 0, cfg.get("start_look_up_m", 0.0)))
    ez = cfg.get("ease", {})
    easing = Ease(ez.get("accel", 0.2), ez.get("decel", 0.3))
    frames = int(round(duration_s * fps)) + 1
    pos, tgt = [], []
    for i in range(frames):
        e = easing(i / (frames - 1))
        a = a0 + sweep * e
        r = r0 + (r1 - r0) * e
        p = Vector((C.x + math.cos(a) * r, C.y + math.sin(a) * r, z0 + (F.z - z0) * smootherstep(e)))
        g = terrain.height(p.x, p.y) + cfg.get("min_clearance_m", 2.0)
        if p.z < g:
            p.z = g
        pos.append(p)
        tgt.append(t_start.lerp(t_end, smootherstep(e)))
    return Shot("orbit", pos, tgt, fps, {"sweep_deg": cfg["sweep_deg"], "radius_m": round(r1, 1)})


def water_skim(layout, terrain, cfg, duration_s, fps):
    """Glide low over calm water toward the subject, then rise gently to the hero framing.

    Starts ``start_distance`` metres out along the hero sight line, ``skim_height``
    above the water, with a slight sideways arc; never drops below
    ``min_height_above_water``. Looks a little ahead of the subject at first
    (horizon in frame), then settles on the hero target.
    """
    fin = layout["camera"]
    F = Vector(fin["location"])
    T1 = Vector(fin["target"])
    d = Vector((F.x - T1.x, F.y - T1.y, 0)).normalized()
    side = Vector((-d.y, d.x, 0)) * cfg.get("arc_m", 6.0) * cfg.get("direction", 1)
    h = cfg["skim_height_m"]
    S = F + d * cfg["start_distance_m"] + side
    S.z = h
    p1 = S.lerp(F, 0.35) - side * 0.2
    p1.z = h
    p2 = S.lerp(F, 0.8) - side * 0.1
    p2.z = h + (F.z - h) * 0.25
    route = Route([S, p1, p2, F])
    t0 = T1 + Vector((0, 0, cfg.get("start_look_up_m", 1.5)))
    ez = cfg.get("ease", {})
    frames = int(round(duration_s * fps)) + 1
    pos, tgt = _sample(route, t0, T1, frames, Ease(ez.get("accel", 0.15), ez.get("decel", 0.35)))
    floor = cfg.get("min_height_above_water_m", 0.6)
    for i, c in enumerate(pos):
        g = max(terrain.height(c.x, c.y) + 1.0, floor)
        if c.z < g:
            pos[i] = Vector((c.x, c.y, g))
    return Shot("water_skim", pos, tgt, fps, {"start": tuple(round(v, 2) for v in S)})


def _reserved(name):
    def planner(*_a, **_k):
        raise NotImplementedError(f"motion preset {name!r} is reserved but not implemented yet")
    return planner


PRESETS = {
    "cloud_descent": cloud_descent,
    "orbit": orbit,
    "push_in": _reserved("push_in"),
    "low_flyover": _reserved("low_flyover"),
    "water_skim": water_skim,
}


def plan(preset, layout, terrain, cfg, duration_s, fps):
    return PRESETS[preset](layout, terrain, cfg, duration_s, fps)
