"""Tiny helper for building shader / geometry node trees in code.

Keeps the material code readable: ``nb.math("MULTIPLY", a, 2.0)`` instead
of five lines of node creation and linking. Sockets can be addressed by
name (first *enabled* socket with that name) or by index.
"""

import bpy


class NB:
    def __init__(self, tree, clear=True):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links
        if clear:
            self.nodes.clear()

    # -- sockets -----------------------------------------------------------
    @staticmethod
    def _find(sockets, key):
        if isinstance(key, int):
            return sockets[key]
        for s in sockets:
            if s.name == key and getattr(s, "enabled", True):
                return s
        for s in sockets:  # fall back to identifier match
            if s.identifier == key:
                return s
        raise KeyError(f"socket {key!r} not in {[s.name for s in sockets]}")

    def i(self, node, key):
        return self._find(node.inputs, key)

    def o(self, node, key=0):
        return self._find(node.outputs, key)

    def set(self, node, key, value):
        sock = self.i(node, key)
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, sock)
        elif isinstance(value, bpy.types.Node):
            self.links.new(value.outputs[0], sock)
        else:
            if isinstance(value, (tuple, list)) and len(value) == 3 and \
                    len(sock.default_value) == 4:
                value = (*value, 1.0)
            sock.default_value = value
        return sock

    # -- nodes -------------------------------------------------------------
    def new(self, kind, inputs=None, **props):
        node = self.nodes.new(kind)
        for k, v in props.items():
            setattr(node, k, v)
        for k, v in (inputs or {}).items():
            self.set(node, k, v)
        return node

    def math(self, op, a, b=None, clamp=False):
        n = self.new("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.set(n, 0, a)
        if b is not None:
            self.set(n, 1, b)
        return n.outputs[0]

    def vmath(self, op, a, b=None, out="Vector"):
        n = self.new("ShaderNodeVectorMath", operation=op)
        self.set(n, 0, a)
        if b is not None:
            self.set(n, 1, b)
        return self.o(n, out)

    def mix(self, fac, a, b, blend="MIX"):
        """Colour mix; returns the result socket."""
        n = self.new("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        self.set(n, "Factor", fac)
        self.set(n, "A", a)
        self.set(n, "B", b)
        return self.o(n, "Result")

    def mixf(self, fac, a, b):
        n = self.new("ShaderNodeMix", data_type="FLOAT")
        self.set(n, "Factor", fac)
        self.set(n, "A", a)
        self.set(n, "B", b)
        return self.o(n, "Result")

    def maprange(self, v, a, b, c=0.0, d=1.0, clamp=True, interp="LINEAR"):
        n = self.new("ShaderNodeMapRange", clamp=clamp, interpolation_type=interp)
        self.set(n, "Value", v)
        self.set(n, "From Min", a)
        self.set(n, "From Max", b)
        self.set(n, "To Min", c)
        self.set(n, "To Max", d)
        return self.o(n, "Result")

    def noise(self, vector, scale=5.0, detail=4.0, rough=0.55, dims="3D", w=None,
              out="Fac", distortion=0.0):
        n = self.new("ShaderNodeTexNoise", noise_dimensions=dims)
        if vector is not None:
            self.set(n, "Vector", vector)
        self.set(n, "Scale", scale)
        self.set(n, "Detail", detail)
        self.set(n, "Roughness", rough)
        self.set(n, "Distortion", distortion)
        if w is not None:
            self.set(n, "W", w)
        return self.o(n, out)

    def ramp(self, fac, stops):
        """stops = [(pos, (r,g,b)), ...]"""
        n = self.new("ShaderNodeValToRGB")
        self.set(n, "Fac", fac)
        els = n.color_ramp.elements
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops):
            el.position = pos
            el.color = (*col, 1.0) if len(col) == 3 else col
        return self.o(n, "Color")

    def coord(self, kind="Object"):
        n = self.new("ShaderNodeTexCoord")
        return self.o(n, kind)

    def sep(self, vec):
        n = self.new("ShaderNodeSeparateXYZ")
        self.set(n, 0, vec)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def comb(self, x, y, z):
        n = self.new("ShaderNodeCombineXYZ")
        self.set(n, 0, x)
        self.set(n, 1, y)
        self.set(n, 2, z)
        return n.outputs[0]

    def mapping(self, vec, scale=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0)):
        n = self.new("ShaderNodeMapping")
        self.set(n, "Vector", vec)
        self.set(n, "Scale", scale)
        self.set(n, "Location", loc)
        self.set(n, "Rotation", rot)
        return n.outputs[0]


def new_material(name):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True  # deprecated (always on) in Blender 5.x
    except Exception:
        pass
    nb = NB(mat.node_tree)
    return mat, nb
