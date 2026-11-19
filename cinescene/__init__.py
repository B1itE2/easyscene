"""cinescene — one sentence in, a cinematic realistic Blender scene out.

Package layout
--------------
Pure-Python modules (usable from system Python *and* Blender's Python):
    rng, spec, budget, assets, post, recipes
Blender-only modules (import ``bpy``; only import them inside Blender):
    nodes, core, materials, lighting, atmosphere, camera, scatter,
    modeling.*, build

The AI agent never writes Blender code. It writes a *scene spec* (JSON,
see ``schema/scene_spec.schema.json``) and runs ``tools/build.py``.
"""

__version__ = "0.1.0"
