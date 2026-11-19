"""Scene foundation: units, colour management, render settings, GPU.

These are fixed for every style, so an agent never has to touch them.
"""

import bpy

from . import budget


def reset():
    """Start from an empty factory scene (no default cube/light/camera)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def setup_units(scene):
    us = scene.unit_settings
    us.system = "METRIC"
    us.scale_length = 1.0
    us.length_unit = "METERS"


def setup_color(scene, look_candidates=("AgX - Medium High Contrast", "Medium High Contrast",
                                        "AgX - Base Contrast", "None")):
    """AgX view transform; look names differ slightly between versions."""
    scene.display_settings.display_device = "sRGB"
    scene.view_settings.view_transform = "AgX"
    for look in look_candidates:
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.sequencer_colorspace_settings.name = "sRGB"


def enable_gpu():
    """Prefer OptiX > CUDA > Metal > HIP > oneAPI. Returns the backend or 'CPU'."""
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except KeyError:
        return "CPU"
    for backend in ("OPTIX", "CUDA", "METAL", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == backend]
        if not gpus:
            continue
        for d in prefs.devices:
            d.use = d.type == backend  # GPU only; mixing CPU in tends to be slower
        return backend
    return "CPU"


def _set(obj, attr, value):
    """Set a property if this Blender version has it (API drifts between releases)."""
    if hasattr(obj, attr):
        try:
            setattr(obj, attr, value)
            return True
        except (TypeError, AttributeError):
            pass
    return False


def setup_render(scene, quality: str, aspect: str, seed: int):
    q = budget.QUALITY[quality]
    w, h = budget.resolution(aspect, quality)
    r = scene.render
    r.engine = "CYCLES"
    r.resolution_x, r.resolution_y = w, h
    r.resolution_percentage = 100
    r.film_transparent = False
    r.use_persistent_data = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_depth = "16"
    r.image_settings.color_mode = "RGB"

    backend = enable_gpu()
    c = scene.cycles
    c.device = "CPU" if backend == "CPU" else "GPU"
    c.samples = q["samples"]
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.02 if quality != "final" else 0.01
    c.seed = seed % 2147483647        # Cycles noise pattern is part of reproducibility
    c.use_animated_seed = False
    c.use_denoising = q["denoise"]
    _set(c, "denoiser", "OPENIMAGEDENOISE")
    _set(c, "denoising_input_passes", "RGB_ALBEDO_NORMAL")
    _set(c, "denoising_prefilter", "ACCURATE")
    _set(c, "denoising_use_gpu", True)
    c.max_bounces = q["max_bounces"]
    c.diffuse_bounces = min(3, q["max_bounces"])
    c.glossy_bounces = min(3, q["max_bounces"])
    c.transmission_bounces = q["max_bounces"]
    c.transparent_max_bounces = q["transparent_bounces"]
    c.volume_bounces = q["volume_bounces"]
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.blur_glossy = 1.0
    _set(c, "volume_biased", True)              # ray-marched volumes: faster, stable noise
    _set(c, "volume_step_rate", q["volume_step_rate"])
    _set(c, "volume_max_steps", q["volume_max_steps"])
    _set(c, "tile_size", 1024)
    _set(c, "use_auto_tile", True)
    c.sample_clamp_indirect = 8.0
    # texture size cap keeps memory predictable
    r.use_simplify = True
    _set(r, "simplify_subdivision_render", 2)
    _set(c, "texture_limit_render", q["texture_limit"])
    return {"width": w, "height": h, "device": backend, "samples": q["samples"]}


def kelvin_rgb(k: float):
    """Approximate blackbody colour (linear-ish RGB, max channel = 1)."""
    import math
    t = k / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        r = 329.698727446 * (t - 60) ** -0.1332047592
        g = 288.1221695283 * (t - 60) ** -0.0755148492
        b = 255.0
    rgb = [max(0.0, min(255.0, v)) / 255.0 for v in (r, g, b)]
    rgb = [v ** 2.2 for v in rgb]  # sRGB-ish -> linear
    m = max(rgb)
    return tuple(v / m for v in rgb)


def collection(name, parent=None):
    """Get or create a collection linked under ``parent`` (scene root by default)."""
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if col.name not in parent.children:
        parent.children.link(col)
    return col


def scene_stats():
    """(unique triangles, instance count) of the evaluated scene, for budgeting."""
    dg = bpy.context.evaluated_depsgraph_get()
    seen, tris, inst = set(), 0, 0
    for oi in dg.object_instances:
        obj = oi.object
        if obj.type != "MESH":
            continue
        if oi.is_instance:
            inst += 1
        key = obj.data.name if obj.data else obj.name
        if key in seen:
            continue
        seen.add(key)
        me = obj.data
        try:
            me.calc_loop_triangles()
            tris += len(me.loop_triangles)
        except Exception:
            pass
    return tris, inst


def image_pixels():
    """(8-bit pixels, float pixels) of all images that will be loaded."""
    byte_px = float_px = 0
    for img in bpy.data.images:
        if img.source not in ("FILE", "TILED"):
            continue
        w, h = img.size
        if img.is_float:
            float_px += w * h
        else:
            byte_px += w * h
    return byte_px, float_px
