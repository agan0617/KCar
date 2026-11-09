"""Blender 腳本共用：材質、幾何原件、合併建構器、遊戲座標 <-> Blender 座標。

遊戲（three.js）用 Y 朝上；Blender 用 Z 朝上。glTF 匯出時 Blender (x, y, z) 會轉成 (x, z, -y)，
所以這裡一律用「遊戲座標」寫幾何，建物件前用 B() 轉成 Blender 座標：遊戲 (x, y, z) -> Blender (x, -z, y)。
"""
import bpy
import math
from mathutils import Vector, Matrix


def B(v):
    return (v[0], -v[2], v[1])


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mats.clear()


def hexc(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


_mats = {}


def mat(name, color, rough=0.75, metal=0.0, emit=0.0):
    """建（或取用）一個材質。color 是 sRGB 十六進位字串。three.js 端依名稱換成卡通材質。"""
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    rgb = tuple(_lin(c) for c in hexc(color))
    b.inputs['Base Color'].default_value = (*rgb, 1.0)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit > 0:
        b.inputs['Emission Color'].default_value = (*rgb, 1.0)
        b.inputs['Emission Strength'].default_value = emit
    _mats[name] = m
    return m


# ---------------------------------------------------------------- 原件（遊戲座標、局部）
# 每個回傳 (verts, faces, smooth)

def box(sx, sy, sz, base=False):
    x, y, z = sx / 2, sy / 2, sz / 2
    y0, y1 = (0, sy) if base else (-y, y)
    v = [(-x, y0, -z), (x, y0, -z), (x, y0, z), (-x, y0, z),
         (-x, y1, -z), (x, y1, -z), (x, y1, z), (-x, y1, z)]
    f = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return v, f, False


def cylinder(r, h, n=12, r2=None, cap=True, smooth=True):
    r2 = r if r2 is None else r2
    v, f = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        v.append((r * math.cos(a), 0, r * math.sin(a)))
        v.append((r2 * math.cos(a), h, r2 * math.sin(a)))
    for i in range(n):
        j = (i + 1) % n
        f.append((2 * i, 2 * i + 1, 2 * j + 1, 2 * j))
    if cap:
        f.append(tuple(2 * i for i in range(n)))
        f.append(tuple(2 * i + 1 for i in reversed(range(n))))
    return v, f, smooth


def cone(r, h, n=10, smooth=False, jitter=None):
    v = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * (jitter[i] if jitter else 1.0)
        v.append((rr * math.cos(a), 0, rr * math.sin(a)))
    v.append((0, h, 0))
    f = [(i, n, (i + 1) % n) for i in range(n)]
    f.append(tuple(reversed(range(n))))
    return v, f, smooth


def sphere(r, seg=12, ring=8, smooth=True):
    v = [(0, r, 0)]
    for j in range(1, ring):
        p = math.pi * j / ring
        for i in range(seg):
            a = 2 * math.pi * i / seg
            v.append((r * math.sin(p) * math.cos(a), r * math.cos(p), r * math.sin(p) * math.sin(a)))
    v.append((0, -r, 0))
    f = []
    for i in range(seg):
        f.append((0, 1 + (i + 1) % seg, 1 + i))
    for j in range(ring - 2):
        a0 = 1 + j * seg
        a1 = a0 + seg
        for i in range(seg):
            i2 = (i + 1) % seg
            f.append((a0 + i, a0 + i2, a1 + i2, a1 + i))
    last = len(v) - 1
    b0 = 1 + (ring - 2) * seg
    for i in range(seg):
        f.append((b0 + i, b0 + (i + 1) % seg, last))
    return v, f, smooth


def torus(R, r, seg=16, ring=8, arc=2 * math.pi, smooth=True):
    """圓環，躺在 XY 平面（軸朝 Z）；arc < 2π 時是一段弧（耳機頭帶用）。"""
    closed = arc >= 2 * math.pi - 1e-6
    ns = seg if closed else seg + 1
    v, f = [], []
    for i in range(ns):
        a = arc * i / seg
        c = Vector((math.cos(a), math.sin(a), 0))
        for j in range(ring):
            b = 2 * math.pi * j / ring
            p = c * (R + r * math.cos(b)) + Vector((0, 0, r * math.sin(b)))
            v.append(tuple(p))
    for i in range(seg):
        i2 = (i + 1) % ns
        for j in range(ring):
            j2 = (j + 1) % ring
            f.append((i * ring + j, i2 * ring + j, i2 * ring + j2, i * ring + j2))
    return v, f, smooth


# ---------------------------------------------------------------- 變換

def M(pos=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    """遊戲座標的變換矩陣。rot 是 (x, y, z) 弧度，順序 XYZ（同 three.js 預設）。"""
    s = scale if hasattr(scale, '__len__') else (scale, scale, scale)
    S = Matrix.Diagonal((s[0], s[1], s[2], 1.0))
    R = Matrix.Rotation(rot[0], 4, 'X') @ Matrix.Rotation(rot[1], 4, 'Y') @ Matrix.Rotation(rot[2], 4, 'Z')
    return Matrix.Translation(Vector(pos)) @ R @ S


def basis(xa, ya, za, origin):
    m = Matrix.Identity(4)
    for r in range(3):
        m[r][0] = xa[r]
        m[r][1] = ya[r]
        m[r][2] = za[r]
        m[r][3] = origin[r]
    return m


class Builder:
    """把很多原件併成一個物件（每個材質一個 glTF primitive，draw call 少）。"""

    def __init__(self, name):
        self.name = name
        self.verts, self.faces, self.fmat, self.fsmooth, self.fuv = [], [], [], [], []
        self.mats = []
        self.has_uv = False

    def _mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def add(self, prim, m, mtx=None, smooth=None):
        v, f, sm = prim
        if smooth is not None:
            sm = smooth
        base = len(self.verts)
        if mtx is None:
            self.verts.extend(v)
        else:
            for p in v:
                q = mtx @ Vector(p)
                self.verts.append((q.x, q.y, q.z))
        mi = self._mi(m)
        for fc in f:
            self.faces.append(tuple(base + i for i in fc))
            self.fmat.append(mi)
            self.fsmooth.append(sm)
            self.fuv.append(None)

    def quad(self, a, b, c, d, m, uv=None, smooth=False):
        base = len(self.verts)
        self.verts.extend([tuple(a), tuple(b), tuple(c), tuple(d)])
        self.faces.append((base, base + 1, base + 2, base + 3))
        self.fmat.append(self._mi(m))
        self.fsmooth.append(smooth)
        self.fuv.append(uv)
        if uv:
            self.has_uv = True

    def build(self, origin=(0, 0, 0), yaw=0.0, local=False):
        """local=True：verts 已經是相對 origin 的局部座標（要轉動的零件用）。"""
        me = self.mesh()
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        if local:
            ob.location = B(origin)
            ob.rotation_euler = (0, 0, yaw)
        return ob

    def mesh(self):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([B(p) for p in self.verts], [], self.faces)
        for m in self.mats:
            me.materials.append(m)
        uvl = me.uv_layers.new(name='UVMap') if self.has_uv else None
        for i, poly in enumerate(me.polygons):
            poly.material_index = self.fmat[i]
            poly.use_smooth = self.fsmooth[i]
            if uvl is not None:
                uv = self.fuv[i]
                for k, li in enumerate(poly.loop_indices):
                    uvl.data[li].uv = uv[k] if uv else (0.0, 0.0)
        me.validate()
        if getattr(self, 'weld', False):
            import bmesh
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
            bm.to_mesh(me)
            bm.free()
        me.update()
        return me


class Instances:
    """同一個 mesh 擺很多份（樹、花、輪胎…）：匯出成 EXT_mesh_gpu_instancing，three.js 讀成 InstancedMesh。
    匯出器只把「同一個空物件底下、共用 mesh」的子物件合成 instancing，所以全部掛在 parent 底下。"""

    def __init__(self, name):
        self.parent = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(self.parent)
        self.count = 0

    def put(self, me, pos, yaw=0.0, scale=1.0):
        s = scale if hasattr(scale, '__len__') else (scale, scale, scale)
        ob = bpy.data.objects.new(f'{self.parent.name}_{self.count}', me)
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = self.parent
        ob.location = B(pos)
        ob.rotation_euler = (0, 0, yaw)
        ob.scale = (s[0], s[2], s[1])
        self.count += 1
        return ob


def empty(name, pos, parent=None):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(pos)
    if parent is not None:
        ob.parent = parent
    return ob


def export_glb(path):
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format='GLB',
        export_yup=True,
        export_apply=True,
        export_texcoords=True,
        export_normals=True,
        export_materials='EXPORT',
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_gpu_instances=True,
    )
