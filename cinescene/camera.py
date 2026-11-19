"""Camera placement and composition.

Rules (shared by every style):
* distance is solved so the subject fills ``fill`` of the frame height;
* the camera sits at eye height on the terrain, looking at ~40% of the
  subject's height (a touch of upward tilt reads as "standing there");
* thirds composition uses lens shift, so verticals stay vertical;
* focus is on the subject, aperture from the recipe.
"""

import math

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

from . import budget

SENSOR = 36.0


def fovs(lens, aspect):
    """(horizontal, vertical) field of view in radians, sensor_fit AUTO."""
    a = budget.ASPECTS[aspect]
    half = SENSOR / 2 / lens
    if a >= 1:
        return 2 * math.atan(half), 2 * math.atan(half / a)
    return 2 * math.atan(half * a), 2 * math.atan(half)


def yaw_of(forward):
    """Yaw so that forward == (-sin(yaw), cos(yaw)); 0 means looking along +Y."""
    return math.atan2(-forward[0], forward[1])


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def create(name="Camera", lens=35.0, clip_end=800.0):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.sensor_width = SENSOR
    cam.sensor_fit = "AUTO"
    cam.clip_start = 0.1
    cam.clip_end = clip_end
    obj = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.scene.camera = obj
    return obj


def solve_static(subject, terrain, cam_spec, cam_cfg):
    """Return dict(location, target, shift_x, focus, yaw) for a still shot."""
    lens, aspect = cam_spec["lens_mm"], cam_spec["aspect"]
    _, vfov = fovs(lens, aspect)
    fill = cam_cfg["subject_fill"][cam_spec["framing"]]
    hs = subject["height"]
    dist = hs / fill / (2 * math.tan(vfov / 2))
    fx0, fx1, fy0, fy1 = subject["footprint"]
    dist += max(fx1 - fx0, fy1 - fy0) * 0.35          # we see the near face, not the centre
    az = math.radians(cam_cfg["view_azimuth_deg"][cam_spec["view"]])
    cx, cy, _ = subject["center"]
    x, y = cx + dist * math.sin(az), cy - dist * math.cos(az)
    terrain.flatten_segment((x, y), (cx, cy), 4.0)   # no hill between us and the subject
    z = terrain.height(x, y) + cam_cfg["eye_height_m"]
    target = Vector((cx, cy, hs * 0.40))
    loc = Vector((x, y, z))
    shift = {"center": 0.0, "thirds_left": 1 / 6, "thirds_right": -1 / 6}[cam_spec["composition"]]
    if budget.ASPECTS[aspect] < 1:
        shift = 0.0                                    # vertical video: keep centred
    fwd = (target - loc).normalized()
    return {"location": tuple(loc), "target": tuple(target), "shift_x": shift,
            "focus": (target - loc).length, "yaw": yaw_of(fwd), "lens": lens, "aspect": aspect}


def apply_static(obj, solved, fstop):
    obj.location = solved["location"]
    look_at(obj, solved["target"])
    cam = obj.data
    cam.lens = solved["lens"]
    cam.shift_x = solved["shift_x"]
    cam.dof.use_dof = True
    cam.dof.focus_distance = solved["focus"]
    cam.dof.aperture_fstop = fstop
    cam.dof.aperture_blades = 7
    cam.dof.aperture_ratio = 1.0


def keep_out_view(solved, subject_radius, corridor, hfov):
    """Predicate: is (x, y) inside the camera->subject sight line (no trees there)?"""
    cx, cy, _ = solved["location"]
    tx, ty, _ = solved["target"]
    vx, vy = tx - cx, ty - cy
    L2 = vx * vx + vy * vy
    L = math.sqrt(L2)
    half = hfov * 0.36

    def blocked(x, y):
        if math.hypot(x - tx, y - ty) < subject_radius:
            return True
        t = ((x - cx) * vx + (y - cy) * vy) / L2
        if -0.05 < t < 1.0:
            px, py = cx + vx * t, cy + vy * t
            if math.hypot(x - px, y - py) < corridor + 3.0 * t:
                return True
            ang = abs(math.atan2((x - cx) * vy - (y - cy) * vx, (x - cx) * vx + (y - cy) * vy))
            if ang < half and t * L < L + 2:
                return True
        return math.hypot(x - cx, y - cy) < 2.5
    return blocked


def frame_edge_points(solved, hfov, terrain, rng):
    """Spots for foreground dressing: lower-left/right of frame and one trunk at an edge."""
    cx, cy, _ = solved["location"]
    yaw = solved["yaw"]
    fwd = Vector((-math.sin(yaw), math.cos(yaw), 0))
    right = Vector((fwd.y, -fwd.x, 0))
    pts = {"ground": [], "trunk": []}
    for side in (-1, 1):
        for _ in range(3):
            d = rng.uniform(2.2, 4.5)
            off = side * math.tan(hfov / 2) * d * rng.uniform(0.55, 0.95)
            p = Vector((cx, cy, 0)) + fwd * d + right * off
            pts["ground"].append((p.x, p.y))
    side = -1 if solved["shift_x"] <= 0 else 1          # trunk on the empty side
    d = rng.uniform(9.0, 11.0)
    p = Vector((cx, cy, 0)) + fwd * d + right * side * math.tan(hfov / 2) * d * 0.97
    pts["trunk"].append((p.x, p.y))
    return pts


def subject_on_screen(obj, point):
    """Normalised (x, y, depth) of a world point in the camera view."""
    scene = bpy.context.scene
    v = world_to_camera_view(scene, obj, Vector(point))
    return (v.x, v.y, v.z)
