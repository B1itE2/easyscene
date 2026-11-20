"""Automatic checks: scene (in Blender) and render (pixels).

Every check returns a dict ``{"id", "ok", "value", "limit", "hint"}``.
``hint`` tells an agent what to change *in the spec* when a check fails -
agents never patch Blender code to fix a render.

Scene checks need ``bpy``; render checks only need numpy and an image
loader (Pillow if present, else Blender's image API).
"""

import json
import math
import os


def _c(cid, ok, value, limit, hint=""):
    return {"id": cid, "ok": bool(ok), "value": value, "limit": limit, "hint": "" if ok else hint}


# ===================================================================== scene ==
def scene_checks(layout: dict, terrain=None):
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector

    scene = bpy.context.scene
    out = []

    # 1. missing textures ------------------------------------------------------
    missing = [img.name for img in bpy.data.images
               if img.source == "FILE" and not img.packed_file
               and not os.path.exists(bpy.path.abspath(img.filepath))]
    out.append(_c("textures_present", not missing, missing, [],
                  "re-run `python3 -m easyscene.assets STYLE` or set EASYSCENE_OFFLINE=1"))

    # 2. floating subject parts. A part is grounded if one of its lowest points
    #    touches the ground (or is buried); other parts count as supported when
    #    their bounding box touches an already-supported part (roof on logs,
    #    curtains inside the walls). Whatever is left over is floating.
    dg = bpy.context.evaluated_depsgraph_get()
    col = bpy.data.collections.get(layout["subject"].get("collection", "Cabin")) or \
        bpy.data.collections.get("Lighthouse")
    parts = [o for o in (col.objects if col else []) if o.type == "MESH"]
    boxes, supported = {}, set()
    for obj in parts:
        ws = [obj.matrix_world @ v.co for v in obj.data.vertices]
        boxes[obj.name] = (Vector((min(p.x for p in ws), min(p.y for p in ws), min(p.z for p in ws))),
                           Vector((max(p.x for p in ws), max(p.y for p in ws), max(p.z for p in ws))))
        for p in sorted(ws, key=lambda p: p.z)[:12]:
            g = terrain.height(p.x, p.y) if terrain else 0.0
            wl = layout["subject"].get("water_level")
            if wl is not None:          # boats and posts are held by the water surface
                g = max(g, wl)
            if p.z - g <= 0.08:
                supported.add(obj.name)
                break

    def touch(a, b, eps=0.03):
        return all(a[0][i] - eps <= b[1][i] and b[0][i] - eps <= a[1][i] for i in range(3))
    grew = True
    while grew:
        grew = False
        for obj in parts:
            if obj.name not in supported and any(touch(boxes[obj.name], boxes[s_]) for s_ in supported):
                supported.add(obj.name)
                grew = True
    floating = sorted(o.name for o in parts if o.name not in supported)
    out.append(_c("subject_grounded", (not parts) or (bool(supported) and not floating), floating,
                  "every part connected to the ground",
                  "terrain under the subject is too low: try another seed"))

    # 3. nothing scattered inside the subject footprint --------------------------
    fx0, fx1, fy0, fy1 = layout["subject"]["footprint"]
    inside = [t for t in layout.get("trees", []) if fx0 < t[0] < fx1 and fy0 < t[1] < fy1]
    out.append(_c("no_trees_in_subject", not inside, len(inside), 0, "layout bug: report it"))

    # 4. camera route clear of tree trunks + above ground -------------------------
    shot_frames = range(scene.frame_start, scene.frame_end + 1)
    trees = layout.get("trees", [])
    worst_trunk, worst_ground = 1e9, 1e9
    for f in shot_frames:
        scene.frame_set(f)
        c = scene.camera.matrix_world.translation
        if terrain:
            worst_ground = min(worst_ground, c.z - terrain.height(c.x, c.y))
        for tx, ty, s in trees:
            d = math.hypot(c.x - tx, c.y - ty) - 0.5 * s
            if d < worst_trunk:
                worst_trunk = d
    out.append(_c("camera_clears_trunks", worst_trunk > 0.6, round(worst_trunk, 2), "> 0.6 m",
                  "camera path grazes a trunk: try another seed"))
    if terrain:
        out.append(_c("camera_above_ground", worst_ground > 0.8, round(worst_ground, 2), "> 0.8 m",
                      "lower lens_mm or another seed"))

    # 5. subject in frame on the hero frame (last frame of a move) ----------------
    scene.frame_set(scene.frame_end)
    pts = [world_to_camera_view(scene, scene.camera, Vector(p))
           for p in layout["subject"]["bbox_points"]]
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    in_frame = all(-0.02 <= v <= 1.02 for v in xs + ys) and all(p.z > 0 for p in pts)
    out.append(_c("subject_in_frame", in_frame,
                  [round(min(xs), 3), round(max(xs), 3), round(min(ys), 3), round(max(ys), 3)],
                  "all corners inside [0,1]", "use framing 'wide' or a longer distance"))
    cx = (min(xs) + max(xs)) / 2
    if layout.get("motion"):
        out.append(_c("subject_centered_end", abs(cx - 0.5) < 0.12, round(cx, 3), "|x-0.5| < 0.12",
                      "layout bug in the move planner: report it"))
    area = _hull_area([(min(max(x, 0), 1), min(max(y, 0), 1)) for x, y in zip(xs, ys)])
    return out, {"subject_area": area, "subject_center_x": cx}


def _hull_area(pts):
    """Area of the convex hull of 2D points (monotone chain + shoelace)."""
    pts = sorted(set(pts))
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    h = lower[:-1] + upper[:-1]
    return abs(sum(h[i][0] * h[(i + 1) % len(h)][1] - h[(i + 1) % len(h)][0] * h[i][1]
                   for i in range(len(h)))) / 2


# ==================================================================== render ==
def load_luma(path):
    """Rec.709 luma in 0..1 as a numpy array (display-referred PNG)."""
    import numpy as np
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        a = np.asarray(im, dtype=np.float32) / 255.0
    except ImportError:
        import bpy
        img = bpy.data.images.load(str(path), check_existing=False)
        w, h = img.size
        a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1, :, :3]
        bpy.data.images.remove(img)
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def render_checks(image_path, limits: dict, subject_area=None):
    import numpy as np
    y = load_luma(image_path)
    mean = float(y.mean())
    clip = float((y > 0.985).mean())
    crush = float((y < 0.015).mean())
    lo, hi = limits["mean_luma"]
    out = [
        _c("exposure_mean", lo <= mean <= hi, round(mean, 3), limits["mean_luma"],
           "too dark: weather 'light_fog' or time 'morning'; too bright: 'dense_fog' is flatter"),
        _c("clipped_highlights", clip <= limits["clipped_highlights_max"], round(clip, 4),
           f"<= {limits['clipped_highlights_max']}", "large burnt areas: change view or seed"),
        _c("crushed_shadows", crush <= limits["crushed_shadows_max"], round(crush, 4),
           f"<= {limits['crushed_shadows_max']}", "large pure-black areas: change view or seed"),
    ]
    if subject_area is not None:
        a0, a1 = limits["subject_area"]
        out.append(_c("subject_area", a0 <= subject_area <= a1, round(subject_area, 3),
                      limits["subject_area"],
                      "subject too small: framing 'medium'/'close'; too big: 'wide'"))
    # contrast: a fog scene must not be a flat grey card
    p5, p95 = np.percentile(y, [5, 95])
    out.append(_c("tonal_range", (p95 - p5) >= 0.25, round(float(p95 - p5), 3), ">= 0.25",
                  "image is flat: weather 'fog' instead of 'dense_fog'"))
    return out


def summarize(checks):
    failed = [c for c in checks if not c["ok"]]
    return {"passed": not failed, "n": len(checks), "failed": [c["id"] for c in failed],
            "checks": checks}


def write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
