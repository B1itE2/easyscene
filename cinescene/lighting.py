"""Lighting presets: environment (HDRI or procedural sky) + sun + practicals scale.

Sun direction is given *relative to the camera's viewing direction* so the
same preset gives the same look wherever the camera ends up:
``rel_azimuth`` 0 = sun straight ahead of the camera (full backlight),
180 = sun behind the camera (flat front light).
"""

import math

import bpy
from mathutils import Vector

from . import core
from .nodes import NB

PRESETS = {
    # 清晨冷雾: soft cold ambient, low sun hidden behind the trees -> light shafts
    "cold_fog_morning": {
        # ambient low vs sun high: sunlit fog must out-shine skylit fog or no light shafts
        "env_strength": 0.55, "env_tint": (0.80, 0.93, 1.0), "env_rotation_deg": 110,
        "sun": {"rel_azimuth": -30, "elevation": 24, "strength": 14.0, "kelvin": 7200, "angle": 2.5},
        "exposure": 0.2,
        "practical_scale": 1.0,
        "sky": {"zenith": (0.30, 0.42, 0.52), "horizon": (0.62, 0.70, 0.72)},
    },
    # 黄昏: warm low sun, cooler sky, practicals a bit brighter
    "golden_dusk": {
        "env_strength": 0.8, "env_tint": (1.0, 1.0, 1.0), "env_rotation_deg": 200,
        "env_saturation": 1.15, "exposure": -0.5,
        "sun": {"rel_azimuth": 40, "elevation": 4, "strength": 3.0, "kelvin": 3000, "angle": 3.5},
        "practical_scale": 1.4,
        "sky": {"zenith": (0.20, 0.25, 0.40), "horizon": (0.95, 0.55, 0.30)},
    },
    # 雨夜: dark blue ambient, faint moon, practicals carry the image
    "rainy_night": {
        "env_strength": 0.025, "env_tint": (0.55, 0.70, 1.0), "env_rotation_deg": 0,
        "sun": {"rel_azimuth": 60, "elevation": 35, "strength": 0.04, "kelvin": 8000, "angle": 1.0},
        "practical_scale": 2.2,
        "sky": {"zenith": (0.004, 0.006, 0.012), "horizon": (0.015, 0.02, 0.03)},
    },
    # 柔和散射光: bright overcast-ish daylight through glass, soft warm sun
    "soft_daylight": {
        "env_strength": 1.3, "env_tint": (1.0, 1.0, 1.0), "env_rotation_deg": 0, "env_saturation": 0.9,
        "sun": {"rel_azimuth": 140, "elevation": 40, "strength": 2.5, "kelvin": 5200, "angle": 6.0},
        "practical_scale": 1.0, "exposure": 0.0,
        "sky": {"zenith": (0.5, 0.6, 0.7), "horizon": (0.8, 0.82, 0.8)},
    },
    # 室内暖光: for interiors; very little outside light
    "interior_warm": {
        "env_strength": 0.12, "env_tint": (0.8, 0.88, 1.0), "env_rotation_deg": 0,
        "sun": None, "practical_scale": 2.5,
        "sky": {"zenith": (0.05, 0.06, 0.08), "horizon": (0.08, 0.09, 0.1)},
    },
}


def hdri_sun_phi(img):
    """Equirect azimuth (radians, Blender convention) of the brightest sky pixel."""
    import numpy as np
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    lum = px.reshape(h, w, 4)[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    lum[: h // 2] = 0                       # rows are bottom-up: keep the upper hemisphere
    _, col = np.unravel_index(int(lum.argmax()), lum.shape)
    return (col / w - 0.5) * math.tau


def _world_hdri(nb, hdri_path, p, sun_dir=None):
    tc = nb.coord("Generated")
    env = nb.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(hdri_path), check_existing=True)
    rot = math.radians(p["env_rotation_deg"])
    if sun_dir is not None and p.get("align_hdri_sun", True):
        # rotate the sky so the sun painted in the HDRI sits where our sun light is
        phi_d = math.atan2(sun_dir[1], -sun_dir[0])
        rot = phi_d - hdri_sun_phi(env.image)
    vec = nb.mapping(tc, rot=(0, 0, rot))
    env.interpolation = "Cubic"
    nb.set(env, "Vector", vec)
    # desaturate a little: real fog flattens sky colour
    # clamp the painted sun: the sun *lamp* lights the scene; an unclamped HDRI sun
    # blows out into a hard-edged block at low resolution
    clamped = nb.vmath("MINIMUM", env.outputs["Color"], (p.get("env_clamp", 6.0),) * 3)
    hsv = nb.new("ShaderNodeHueSaturation", inputs={"Saturation": p.get("env_saturation", 0.6)})
    nb.set(hsv, "Color", clamped)
    return nb.mix(1.0, hsv.outputs[0], p["env_tint"], "MULTIPLY")


def _world_sky(nb, p):
    """Procedural fallback: vertical gradient horizon -> zenith."""
    _, _, z = nb.sep(nb.coord("Generated"))
    f = nb.maprange(z, -0.05, 0.6, 0.0, 1.0, interp="SMOOTHSTEP")
    return nb.mix(f, p["sky"]["horizon"], p["sky"]["zenith"])


def apply(preset_name, camera_yaw_rad, hdri_path=None, overrides=None):
    """Create world + sun. Returns info dict (incl. practical_scale)."""
    p = dict(PRESETS[preset_name])
    p.update(overrides or {})
    world = bpy.data.worlds.new(f"World_{preset_name}")
    bpy.context.scene.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    nb = NB(world.node_tree)
    s = p.get("sun")
    sun_d = None
    if s:
        # camera forward (yaw measured from +Y, counter-clockwise) rotated by rel_azimuth
        az = camera_yaw_rad + math.radians(s["rel_azimuth"])
        el = math.radians(s["elevation"])
        sun_d = Vector((-math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    col = _world_hdri(nb, hdri_path, p, sun_d) if hdri_path else _world_sky(nb, p)
    bg = nb.new("ShaderNodeBackground", inputs={"Strength": p["env_strength"]})
    nb.set(bg, "Color", col)
    out = nb.new("ShaderNodeOutputWorld")
    nb.links.new(bg.outputs[0], nb.i(out, "Surface"))

    bpy.context.scene.view_settings.exposure = p.get("exposure", 0.0)
    info = {"preset": preset_name, "hdri": bool(hdri_path),
            "practical_scale": p["practical_scale"], "sun_dir": None}
    if s:
        d = sun_d
        light = bpy.data.lights.new("Sun", "SUN")
        light.energy = s["strength"]
        light.color = core.kelvin_rgb(s["kelvin"])
        light.angle = math.radians(s["angle"])
        obj = bpy.data.objects.new("Sun", light)
        obj.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        bpy.context.scene.collection.objects.link(obj)
        info["sun_dir"] = tuple(d)
    return info
