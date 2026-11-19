"""Instancing via Geometry Nodes: one point-cloud object per layer of scattering.

Points carry ``rot`` (euler), ``scl`` and ``vid`` (variant index); a GN
modifier instances the matching variant from a collection that is *not*
linked to the scene. Thousands of trees cost one copy of each variant in
memory, and the whole layer is one object in the outliner.
"""

import bpy


def variant_collection(name, objs):
    col = bpy.data.collections.new(name)
    for i, o in enumerate(objs):
        o.name = f"{name}_{i:02d}"     # Collection Info orders children by name
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    return col


def scatter(name, points, variants_col, parent=None, shadow=True):
    """points: list of (x, y, z, rx, ry, rz, scale, variant_index)."""
    n = len(points)
    me = bpy.data.meshes.new(f"{name}_points")
    me.vertices.add(n)
    me.vertices.foreach_set("co", [c for p in points for c in p[0:3]])
    a = me.attributes.new("rot", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", [c for p in points for c in p[3:6]])
    a = me.attributes.new("scl", "FLOAT", "POINT")
    a.data.foreach_set("value", [p[6] for p in points])
    a = me.attributes.new("vid", "INT", "POINT")
    a.data.foreach_set("value", [int(p[7]) for p in points])
    me.update()
    obj = bpy.data.objects.new(name, me)
    (parent or bpy.context.scene.collection).objects.link(obj)

    ng = bpy.data.node_groups.new(f"{name}_GN", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N = ng.nodes
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    ci = N.new("GeometryNodeCollectionInfo")
    ci.transform_space = "ORIGINAL"
    ci.inputs["Collection"].default_value = variants_col
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    iop = N.new("GeometryNodeInstanceOnPoints")
    iop.inputs["Pick Instance"].default_value = True

    def attr(nm, dtype):
        na = N.new("GeometryNodeInputNamedAttribute")
        na.data_type = dtype
        na.inputs["Name"].default_value = nm
        return na.outputs["Attribute"]

    L = ng.links
    L.new(gi.outputs[0], iop.inputs["Points"])
    L.new(ci.outputs[0], iop.inputs["Instance"])
    L.new(attr("vid", "INT"), iop.inputs["Instance Index"])
    L.new(attr("rot", "FLOAT_VECTOR"), iop.inputs["Rotation"])
    L.new(attr("scl", "FLOAT"), iop.inputs["Scale"])
    L.new(iop.outputs[0], go.inputs[0])
    mod = obj.modifiers.new("scatter", "NODES")
    mod.node_group = ng
    obj.visible_shadow = shadow
    return obj
