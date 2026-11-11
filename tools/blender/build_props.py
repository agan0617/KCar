"""場景物件庫：把 CC0 素材（Kenney、Quaternius）整理成賽道產生器可以直接撒的模型，素材缺的（日式建築、櫻花、燈籠…）用程式畫。

用法（在 repo 根目錄）：
  <Blender>\\blender.exe -b --factory-startup -P tools\\blender\\build_props.py -- [主題 ...] [--no-render] [--src <素材目錄>]
主題：common beach sakura snow city volcano autumn（不寫＝全部）。
素材目錄預設是 repo 旁邊的 KCar_assets_src\\（下載的原始素材，不進 git，清單見那邊的 INVENTORY.md）。

輸出：
  assets_src/props/<主題>.glb    每個物件是一個頂層 object，名稱 <類別>_<變體>（palm_a、rock_large_a…）
                                 原點在底部中心（貼地）、+Y 朝上、正面朝 +Z、單位公尺
  assets_src/props/<主題>.json   每個物件的類別、尺寸、面數、建議用途與密度、發光材質、來源
  assets_src/props/LICENSE.md    每個物件來自哪個素材包（由全部 json 重新產生）
  tmp_layout/props_<主題>.png    物件陳列圖（照實際比例排列，人工檢查用）

處理規則：
  - 材質一律重建成 Principled（three.js 會讀成受光的 MeshStandardMaterial），名稱前綴 P_（跟賽道材質 Road、Ground 等不撞名）
  - Kenney 舊 kit（nature、racing）的顏色是沒轉線性的 sRGB 值，這裡轉回去，不然會洗白
  - Quaternius Ultimate Nature 的 FBX 匯入後 Alpha=0，重建材質時一律不透明
  - 貼圖縮到 512 以下（樹皮 256）並嵌進 GLB；有透明的用 PNG＋alphaMode MASK，其餘 JPEG
  - 面數：一般物件 <= 3,000、地標 <= 15,000，超過用 Decimate 減面
  - 發光（emissive）材質：霓虹招牌、窗戶、燈、熔岩、燈籠火袋。three.js 端用 bloom 讓它發光；
    名稱列在 json 的 emissive 欄
"""
import bpy
import bmesh
import colorsys
import json
import math
import os
import random
import re
import sys
import time

import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402
from common import Builder, box, cone, cylinder, sphere, torus, M  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(REPO, 'assets_src', 'props')
TMP = os.path.join(REPO, 'tmp_layout')
TEXD = os.path.join(TMP, 'props_tex')
ALL_THEMES = ['common', 'beach', 'sakura', 'snow', 'city', 'volcano', 'autumn']

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
SRC = os.path.normpath(os.path.join(REPO, '..', 'KCar_assets_src'))
RENDER = True
THEMES = []
i = 0
while i < len(argv):
    a = argv[i]
    if a == '--src':
        SRC = os.path.abspath(argv[i + 1])
        i += 1
    elif a == '--no-render':
        RENDER = False
    elif a in ALL_THEMES:
        THEMES.append(a)
    else:
        raise SystemExit(f'不認得的參數：{a}')
    i += 1
THEMES = THEMES or ALL_THEMES

LIMIT = 3000          # 一般物件面數上限（三角面）
LIMIT_LANDMARK = 15000

# ================================================================ 來源與授權

QPACK_URL = {
    'ultimate-nature': 'https://quaternius.com/packs/ultimatenature.html',
    'stylized-nature-megakit': 'https://quaternius.itch.io/stylized-nature-megakit',
    'ultimate-stylized-nature': 'https://quaternius.com/packs/ultimatestylizednature.html',
    'pirate-kit': 'https://quaternius.com/packs/piratekit.html',
    'sushi-restaurant-kit': 'https://quaternius.com/packs/sushirestaurantkit.html',
    'cyberpunk-game-kit': 'https://quaternius.com/packs/cyberpunkgamekit.html',
    'modular-streets': 'https://quaternius.com/packs/modularstreets.html',
}
_PP = None


def pp_sources():
    global _PP
    if _PP is None:
        _PP = {}
        p = os.path.join(SRC, 'quaternius', 'polypizza', 'SOURCES.tsv')
        if os.path.exists(p):
            for ln in open(p, encoding='utf-8-sig').read().splitlines()[1:]:
                c = ln.split('\t')
                if len(c) >= 5:
                    _PP['quaternius/polypizza/' + c[3]] = (c[2], c[4])
    return _PP


def source_info(rel):
    rel = rel.replace('\\', '/')
    p = rel.split('/')
    if p[0] == 'kenney':
        return dict(pack=f'Kenney {p[1]}', file=rel, license='CC0 1.0', url=f'https://kenney.nl/assets/{p[1]}')
    if p[0] == 'quaternius' and p[1] == 'polypizza':
        title, url = pp_sources().get(rel, ('', 'https://poly.pizza/u/Quaternius'))
        return dict(pack=f'Quaternius（poly.pizza 單件：{title}）', file=rel, license='CC0 1.0', url=url)
    if p[0] == 'quaternius':
        return dict(pack=f'Quaternius {p[1]}', file=rel, license='CC0 1.0', url=QPACK_URL.get(p[1], 'https://quaternius.com'))
    return dict(pack=rel, file=rel, license='?', url='')


def kit_of(rel):
    p = rel.replace('\\', '/').split('/')
    camel = lambda s: ''.join(w[:1].upper() + w[1:] for w in re.split(r'[-_ ]', s) if w)  # noqa: E731
    if p[0] == 'kenney':
        return 'k' + camel(p[1].replace('-kit', '').replace('kit-', ''))
    if p[1] == 'polypizza':
        return 'qPP'
    return 'q' + camel(p[1].replace('-kit', ''))


# ================================================================ 顏色、材質

def srgb2lin(c):
    return common._lin(c)


def lin2srgb(c):
    c = max(0.0, c)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def lin(c):
    """'#rrggbb'（sRGB）或 (r, g, b) 線性值 -> 線性值。"""
    if isinstance(c, str):
        return tuple(srgb2lin(v) for v in common.hexc(c))
    return tuple(c[:3])


def adjust(c_lin, sat=1.0, val=1.0, tint=None):
    s = [lin2srgb(v) for v in c_lin]
    h, sv, v = colorsys.rgb_to_hsv(*s)
    s = colorsys.hsv_to_rgb(h, min(1.0, sv * sat), min(1.0, v * val))
    out = tuple(srgb2lin(v) for v in s)
    if tint:
        out = tuple(a * b for a, b in zip(out, tint))
    return out


_MAT = {}


def _new_mat(key, cull=True):
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    m.use_backface_culling = cull
    _MAT[key] = m
    return m, m.node_tree.nodes['Principled BSDF'], m.node_tree


def pmat(name, color, rough=0.8, metal=0.0, emit=0.0, emit_color=None, cull=True):
    """純色材質。name 不含前綴（會自動加 P_）。color：'#hex'（sRGB）或線性 tuple。"""
    key = 'P_' + name
    if key in _MAT:
        return _MAT[key]
    m, p, nt = _new_mat(key, cull)
    p.inputs['Base Color'].default_value = (*lin(color), 1.0)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metal
    if emit > 0:
        p.inputs['Emission Color'].default_value = (*lin(emit_color or color), 1.0)
        p.inputs['Emission Strength'].default_value = emit
    return m


def tmat(name, img, rough=0.8, alpha=False, emit=0.0, vcol=False, cull=True):
    """貼圖材質。alpha=True 匯出成 alphaMode MASK（1 - (alpha < 0.5)，glTF 匯出器認得這個寫法）。"""
    key = 'P_' + name
    if key in _MAT:
        return _MAT[key]
    m, p, nt = _new_mat(key, cull and not alpha)
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = img
    col = t.outputs['Color']
    if vcol:
        ca = nt.nodes.new('ShaderNodeVertexColor')
        mx = nt.nodes.new('ShaderNodeMix')
        mx.data_type = 'RGBA'
        mx.blend_type = 'MULTIPLY'
        mx.inputs['Factor'].default_value = 1.0
        nt.links.new(col, mx.inputs[6])
        nt.links.new(ca.outputs['Color'], mx.inputs[7])
        col = mx.outputs[2]
    nt.links.new(col, p.inputs['Base Color'])
    p.inputs['Roughness'].default_value = rough
    if alpha:
        lt = nt.nodes.new('ShaderNodeMath')
        lt.operation = 'LESS_THAN'
        lt.inputs[1].default_value = 0.5
        nt.links.new(t.outputs['Alpha'], lt.inputs[0])
        sub = nt.nodes.new('ShaderNodeMath')
        sub.operation = 'SUBTRACT'
        sub.inputs[0].default_value = 1.0
        nt.links.new(lt.outputs[0], sub.inputs[1])
        nt.links.new(sub.outputs[0], p.inputs['Alpha'])
        m.blend_method = 'CLIP'
    if emit > 0:
        nt.links.new(t.outputs['Color'], p.inputs['Emission Color'])
        p.inputs['Emission Strength'].default_value = emit
    return m


def mat_image(m):
    if not m or not m.use_nodes:
        return None
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and n.image.colorspace_settings.name != 'Non-Color':
            return n.image
    return None


def mat_color(m):
    """材質的底色（線性）與發光強度。"""
    if not m:
        return (0.8, 0.8, 0.8), 0.0
    if not m.use_nodes:
        return tuple(m.diffuse_color[:3]), 0.0
    p = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not p:
        return (0.8, 0.8, 0.8), 0.0
    return tuple(p.inputs['Base Color'].default_value[:3]), p.inputs['Emission Strength'].default_value


# ---------------------------------------------------------------- 貼圖

_IMG = {}


def img_id(img):
    return bpy.path.abspath(img.filepath) if img.filepath else img.name


def prep_img(img, maxsz=512, fn=None, fnkey='', alpha=False, name=None):
    """縮圖（<= maxsz）、選擇性做像素處理（fn(array Nx4, sRGB 0-1) -> array），存成檔案後重新載入。
    同一張來源圖＋同樣處理只做一次，所以同一個 GLB 裡共用貼圖。"""
    k = (img_id(img), maxsz, fnkey, alpha)
    if k in _IMG:
        return _IMG[k]
    w, h = img.size
    s = min(1.0, maxsz / max(w, h))
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    cp = img.copy()
    if (nw, nh) != (w, h):
        cp.scale(nw, nh)
    arr = np.empty(nw * nh * 4, np.float32)
    cp.pixels.foreach_get(arr)
    bpy.data.images.remove(cp)
    arr = arr.reshape(-1, 4)
    if fn:
        arr = np.clip(fn(arr.copy()), 0.0, 1.0).astype(np.float32)
    if not alpha:
        arr[:, 3] = 1.0
    fmt = 'PNG' if (alpha or max(nw, nh) <= 256) else 'JPEG'
    sid = img_id(img).replace('\\', '/')
    base = name or re.sub(r'[^A-Za-z0-9_]+', '_', os.path.splitext(os.path.basename(sid))[0])
    m = re.search(r'/(kenney|quaternius)/([^/]+)/', sid)  # 每個 kit 都有自己的 colormap.png，檔名要分開
    if m:
        base = f'{m.group(2).replace("-", "")}_{base}'
    elif not os.path.isabs(sid):  # GLB 內嵌的圖：用像素內容區分
        base = f'{base}_{abs(hash(sid)) % 10000:04d}'
    base = f'{base}_{nw}' + (f'_{fnkey}' if fnkey else '')
    path = os.path.join(TEXD, base + ('.png' if fmt == 'PNG' else '.jpg'))
    os.makedirs(TEXD, exist_ok=True)
    new = bpy.data.images.new(base, nw, nh, alpha=True)
    new.pixels.foreach_set(arr.ravel())
    new.filepath_raw = path
    new.file_format = fmt
    try:
        new.save(quality=85)
    except TypeError:
        new.save()
    bpy.data.images.remove(new)
    out = bpy.data.images.load(path)
    out.name = base
    out.pack()  # 讀進記憶體，之後同名檔被覆寫也不受影響
    _IMG[k] = out
    return out


def pixels_of(img):
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


# ---------------------------------------------------------------- 匯入的材質轉換

def _upstream(sock):
    seen, out, stack = set(), [], [l.from_node for l in sock.links]
    while stack:
        n = stack.pop()
        if n.name in seen:
            continue
        seen.add(n.name)
        out.append(n)
        for s in n.inputs:
            stack.extend(l.from_node for l in s.links)
    return out


def analyze(m):
    info = dict(color=(0.8, 0.8, 0.8), img=None, alpha=False, vcol=False, emit=0.0)
    if not m.use_nodes:
        info['color'] = tuple(m.diffuse_color[:3])
        return info
    nt = m.node_tree
    p = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    imgs = [n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image and n.image.colorspace_settings.name != 'Non-Color']
    for n in nt.nodes:
        if n.type == 'MAPPING':
            v = [tuple(n.inputs[k].default_value) for k in ('Location', 'Rotation', 'Scale')]
            if v != [(0, 0, 0), (0, 0, 0), (1, 1, 1)]:
                print(f'  [warn] {m.name}: 貼圖有 UV 變換 {v}（沒有套用）')
    if not p:
        if imgs:
            info['img'] = imgs[0].image
        return info
    bc = p.inputs['Base Color']
    if bc.is_linked:
        ups = _upstream(bc)
        ti = [n for n in ups if n.type == 'TEX_IMAGE' and n.image]
        info['img'] = ti[0].image if ti else None
        info['vcol'] = any(n.type in ('VERTEX_COLOR', 'ATTRIBUTE') for n in ups)
        rgb = [n for n in ups if n.type == 'RGB']
        if not ti and rgb:
            info['color'] = tuple(rgb[0].outputs[0].default_value[:3])
    else:
        info['color'] = tuple(bc.default_value[:3])
        if imgs:  # 底色沒接貼圖、貼圖接在發光上（Cyberpunk 招牌）
            info['img'] = imgs[0].image
            info['color'] = (1.0, 1.0, 1.0)
    if p.inputs['Alpha'].is_linked and info['img'] is not None:
        info['alpha'] = True
    ec = p.inputs['Emission Color']
    es = p.inputs['Emission Strength'].default_value
    if es > 0 and (ec.is_linked or max(ec.default_value[:3]) > 0.01):
        info['emit'] = es
    return info


def recolor_mat(v, kit, base):
    if isinstance(v, bpy.types.Material):
        return v
    if isinstance(v, tuple) and isinstance(v[0], str) and not v[0].startswith('#'):
        return pmat(v[0], v[1], *v[2:])
    return pmat(f'{kit}_{base}_{str(v).lstrip("#")}', v)


GENERIC_TEX_NAMES = {'colormap', 'atlas', 'texture_signs'}


def convert(m, rel, opt):
    kit = kit_of(rel)
    base = re.sub(r'\.\d{3}$', '', m.name)
    rc = opt.get('recolor', {})
    if base in rc:
        return recolor_mat(rc[base], kit, base)
    info = analyze(m)
    tag = opt.get('tag', '')
    cull = m.use_backface_culling if rel.lower().endswith(('.glb', '.gltf')) else opt.get('cull', True)
    if info['img'] is not None:
        emit = opt.get('emit_tex', {}).get(base, info['emit'])
        fn, fkey = opt.get('img_fn'), opt.get('img_key', '')
        if isinstance(fn, dict):  # 只處理指定材質的貼圖
            fn = fn.get(base)
            fkey = fkey if fn else ''
        maxtex = opt.get('maxtex', 512)
        if 'bark' in base.lower() or 'trunk' in base.lower():
            maxtex = min(maxtex, 256)
        img = prep_img(info['img'], maxtex, fn, fkey, info['alpha'])
        nm = kit if base.lower() in GENERIC_TEX_NAMES else f'{kit}_{base}'
        nm += (tag if fn or not isinstance(opt.get('img_fn'), dict) else '') + ('_Glow' if emit else '')
        return tmat(nm, img, alpha=info['alpha'], emit=emit, vcol=info['vcol'], cull=cull)
    c = info['color']
    if opt.get('srgb_fix'):
        c = tuple(srgb2lin(v) for v in c)  # 原值其實是 sRGB
    c = adjust(c, opt.get('sat', 1.0), opt.get('val', 1.0), opt.get('tint'))
    return pmat(f'{kit}_{base}{tag}', c, cull=cull, emit=info['emit'])


# ================================================================ 物件：匯入、合併、正規化

def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def join(obs, name='tmp'):
    obs = [o for o in obs if o is not None]
    srcs = []
    for o in obs:
        srcs += json.loads(o.get('src', '[]'))
    if len(obs) > 1:
        with bpy.context.temp_override(active_object=obs[0], object=obs[0], selected_objects=obs, selected_editable_objects=obs):
            bpy.ops.object.join()
    ob = obs[0]
    ob.name = name
    ob['src'] = json.dumps(sorted(set(srcs)))
    return ob


def imp(rel, mtx=None, **opt):
    """匯入一個素材檔：烘焙變換、合併成一個物件、材質換成 P_ 材質。mtx：額外的變換（Blender 座標）。"""
    path = os.path.join(SRC, rel)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    before = set(bpy.data.objects)
    if rel.lower().endswith('.fbx'):
        bpy.ops.import_scene.fbx(filepath=path)
        opt.setdefault('cull', False)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = []
    for o in new:
        if o.type == 'MESH':
            me = o.data.copy()
            mw = o.matrix_world.copy()
            if mtx is not None:
                mw = mtx @ mw
            me.transform(mw)
            if mw.determinant() < 0:
                me.flip_normals()
            meshes.append(me)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    obs = [link(bpy.data.objects.new('tmp', me)) for me in meshes]
    ob = join(obs)
    k = kit_of(rel).lower()
    if 'srgb_fix' not in opt and k in ('knature', 'kracing'):
        opt['srgb_fix'] = True
    me = ob.data
    for i, m in enumerate(me.materials):
        if m is not None:
            me.materials[i] = convert(m, rel, opt)
    ob['src'] = json.dumps([rel.replace('\\', '/')])
    return ob


def proc(builder, name='tmp'):
    """程式畫的物件（common.Builder，遊戲座標）。"""
    ob = builder.build()
    ob.name = name
    ob['src'] = '[]'
    return ob


def verts_np(me):
    a = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get('co', a)
    return a.reshape(-1, 3)


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def normalize(ob, h=None, s=None, yaw=0.0, center='bbox'):
    """原點移到底部中心、縮放成公尺。h：目標高度；s：直接給倍率。yaw：繞垂直軸轉（弧度，正面要朝 +Z 時用）。"""
    me = ob.data
    if yaw:
        me.transform(Matrix.Rotation(yaw, 4, 'Z'))
    v = verts_np(me)
    mn, mx = v.min(0), v.max(0)
    if s is None:
        s = h / max(1e-6, mx[2] - mn[2]) if h else 1.0
    if center == 'base':  # 樹：以樹幹底部為中心（彎的椰子樹不會偏）
        sl = v[v[:, 2] < mn[2] + 0.04 * (mx[2] - mn[2])]
        c = (sl.min(0) + sl.max(0)) / 2
    else:
        c = (mn + mx) / 2
    me.transform(Matrix.Diagonal((s, s, s, 1.0)) @ Matrix.Translation((-c[0], -c[1], -mn[2])))
    me.update()


def decimate(ob, limit):
    for _ in range(4):
        t = tri_count(ob)
        if t <= limit:
            return
        mod = ob.modifiers.new('dec', 'DECIMATE')
        mod.ratio = limit / t * 0.97
        mod.use_collapse_triangulate = True
        dg = bpy.context.evaluated_depsgraph_get()
        me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.clear()
        old = ob.data
        ob.data = me2
        bpy.data.meshes.remove(old)


def dedupe_slots(ob):
    me = ob.data
    mats = list(me.materials)
    uniq = []
    remap = []
    for m in mats:
        if m in uniq:
            remap.append(uniq.index(m))
        else:
            uniq.append(m)
            remap.append(len(uniq) - 1)
    if len(uniq) == len(mats):
        return
    idx = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get('material_index', idx)
    idx = np.array(remap, np.int32)[idx]
    me.materials.clear()
    for m in uniq:
        me.materials.append(m)
    me.polygons.foreach_set('material_index', idx)
    me.update()


# ---------------------------------------------------------------- 依顏色／位置換材質（窗戶發光、燈泡發光…）

def face_rgb(ob):
    """每個面的 sRGB 底色（有貼圖就取 UV 中心的像素）。"""
    me = ob.data
    uv = me.uv_layers.active
    pix = {}
    out = []
    for p in me.polygons:
        m = me.materials[p.material_index] if me.materials else None
        img = mat_image(m)
        if img is not None and uv is not None:
            if img.name not in pix:
                pix[img.name] = pixels_of(img)
            a = pix[img.name]
            u = sum(uv.data[li].uv[0] for li in p.loop_indices) / p.loop_total
            v = sum(uv.data[li].uv[1] for li in p.loop_indices) / p.loop_total
            hh, ww = a.shape[:2]
            c = a[int((v % 1.0) * hh) % hh, int((u % 1.0) * ww) % ww][:3]
            out.append(tuple(float(x) for x in c))
        else:
            c, _ = mat_color(m)
            out.append(tuple(lin2srgb(x) for x in c))
    return out


def set_faces(ob, sel, mat):
    """sel：面索引集合 -> 換成 mat。"""
    me = ob.data
    if mat not in list(me.materials):
        me.materials.append(mat)
    mi = list(me.materials).index(mat)
    for i in sel:
        me.polygons[i].material_index = mi


def islands(ob, sel):
    """sel 裡用邊相連的面分組。"""
    me = ob.data
    sel = set(sel)
    edge_faces = {}
    for p in me.polygons:
        if p.index in sel:
            for ek in p.edge_keys:
                edge_faces.setdefault(ek, []).append(p.index)
    seen, groups = set(), []
    for f in sel:
        if f in seen:
            continue
        g, st = [], [f]
        seen.add(f)
        while st:
            x = st.pop()
            g.append(x)
            for ek in me.polygons[x].edge_keys:
                for y in edge_faces.get(ek, ()):
                    if y not in seen:
                        seen.add(y)
                        st.append(y)
        groups.append(g)
    return groups


def light_windows(ob, rnd, lit=0.65):
    """窗戶玻璃（Kenney city-kit-commercial 的藍色、淺藍色那兩格；灰藍那格是窗框，不算）-> 一扇一扇（相連的面）隨機亮暖光、冷光或不亮。
    只取朝側面的面（排除屋頂上的東西）。"""
    cols = face_rgb(ob)
    pol = ob.data.polygons
    win = [i for i, (r, g, b) in enumerate(cols)
           if b - r > 0.15 and b > 0.6 and r < 0.85 and abs(pol[i].normal.z) < 0.3]
    warm = pmat('CityWindowWarm', '#ffd98a', rough=0.3, emit=2.2)
    cool = pmat('CityWindowCool', '#9fe6ff', rough=0.3, emit=2.0)
    dark = pmat('CityWindowDark', '#1d2a44', rough=0.25)
    sw, sc, sd = [], [], []
    for g in islands(ob, win):
        r = rnd.random()
        (sw if r < lit * 0.6 else sc if r < lit else sd).extend(g)
    set_faces(ob, sw, warm)
    set_faces(ob, sc, cool)
    set_faces(ob, sd, dark)
    return len(win)


def emit_where(ob, pred, mat):
    """pred(rgb, polygon, hf) 為真的面換成 mat。rgb：sRGB 底色；hf：面中心的高度比例（0＝底、1＝頂）。在 add() 之前呼叫。"""
    cols = face_rgb(ob)
    z = verts_np(ob.data)[:, 2]
    z0, z1 = z.min(), z.max()
    sel = [p.index for p in ob.data.polygons if pred(cols[p.index], p, (p.center.z - z0) / max(1e-6, z1 - z0))]
    set_faces(ob, sel, mat)
    print(f'    emit_where {mat.name}: {len(sel)} 面')
    return ob


def lamp_down(c, p, hf):
    """路燈燈頭：頂端附近朝下的面。"""
    return p.normal.z < -0.5 and hf > 0.85


# ================================================================ 程式畫的幾何（遊戲座標：x 右、y 上、z 前）

_ICO = {}


def ico(sub=1):
    if sub not in _ICO:
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
        v = [tuple(x.co) for x in bm.verts]
        f = [tuple(x.index for x in fc.verts) for fc in bm.faces]
        bm.free()
        _ICO[sub] = (v, f)
    return _ICO[sub]


def blob(r, rnd, sub=1, jit=0.16, sq=(1, 1, 1)):
    """低多邊形團塊（葉團、花團、石頭）：icosphere 加隨機起伏，平面著色。"""
    v, f = ico(sub)
    out = []
    for p in v:
        k = 1 + rnd.uniform(-jit, jit)
        out.append((p[0] * r * k * sq[0], p[1] * r * k * sq[1], p[2] * r * k * sq[2]))
    return out, f, False


def blob_split(r, rnd, frac, sub=1, jit=0.16, sq=(1, 1, 1)):
    """同一團分成兩組面（例：岩石上 frac 比例的面發光）。"""
    v, f, _ = blob(r, rnd, sub, jit, sq)
    a, b = [], []
    for fc in f:
        (b if rnd.random() < frac else a).append(fc)
    return (v, a, False), (v, b, False)


def prism(r, h, n=6, r2=None):
    return cylinder(r, h, n, r2=r2, smooth=False)


def seg(p0, p1):
    """把 +Y 方向的單位原件轉到 p0 -> p1，回傳 (矩陣, 長度)。"""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    q = Vector((0, 1, 0)).rotation_difference(d.normalized())
    return Matrix.Translation(p0) @ q.to_matrix().to_4x4(), d.length


def limb(b, p0, p1, r0, r1, m, n=6, smooth=True):
    mt, L = seg(p0, p1)
    b.add(cylinder(r0, L, n, r2=r1), m, mt, smooth=smooth)


class Poly:
    """自己組多邊形：每個面指定想要的法線方向，順序自動翻，不用擔心繞向。"""

    def __init__(self):
        self.v, self.f = [], []

    def face(self, pts, want):
        pts = [Vector(p) for p in pts]
        n = Vector((0, 0, 0))
        for i in range(len(pts)):  # Newell 法線
            a, c = pts[i], pts[(i + 1) % len(pts)]
            n += Vector(((a.y - c.y) * (a.z + c.z), (a.z - c.z) * (a.x + c.x), (a.x - c.x) * (a.y + c.y)))
        if n.dot(Vector(want)) < 0:
            pts = pts[::-1]
        k = len(self.v)
        self.v.extend(tuple(p) for p in pts)
        self.f.append(tuple(range(k, k + len(pts))))

    def prim(self):
        return self.v, self.f, False


def sweep(pts, h, d):
    """沿 XY 平面上的折線拉一根矩形斷面的梁（h：垂直於折線的厚度，d：z 方向寬度）。鳥居笠木、橋面、欄杆。"""
    P = Poly()
    n = len(pts)
    rings = []
    for i, c in enumerate(pts):
        c = Vector(c)
        t = (Vector(pts[min(i + 1, n - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
        nn = Vector((-t.y, t.x, 0))
        rings.append([c + nn * (sy * h / 2) + Vector((0, 0, sz * d / 2)) for sy, sz in ((-1, -1), (-1, 1), (1, 1), (1, -1))])
    for i in range(n - 1):
        a, b2 = rings[i], rings[i + 1]
        cen = (Vector(pts[i]) + Vector(pts[i + 1])) / 2
        for k in range(4):
            k2 = (k + 1) % 4
            q = [a[k], b2[k], b2[k2], a[k2]]
            mid = sum(q, Vector()) / 4
            P.face(q, mid - cen)
    t0 = Vector(pts[0]) - Vector(pts[1])
    t1 = Vector(pts[-1]) - Vector(pts[-2])
    P.face(rings[0], t0)
    P.face(rings[-1], t1)
    return P.prim()


def ring_roof(eave, ridge, H, th, lift=0.0, rows=5, expo=1.6, tmax=0.94, a=1.0, b=1.0):
    """屋頂殼：eave 是屋簷外圈 (x, z)、ridge 是每個點對應的屋脊點；高度沿 t^expo 上凹（屋簷平、近屋脊陡），
    四角往上翹 lift。回傳 (上表面, 下表面＋屋簷厚度)，兩組面分開給材質（瓦／椽木色）。"""
    rowsP = []
    for k in range(rows + 1):
        tt = k / rows
        t = tmax * tt
        row = []
        for (ex, ez), (rx, rz) in zip(eave, ridge):
            x = ex * (1 - t) + rx * t
            z = ez * (1 - t) + rz * t
            cf = (abs(ex) / a * abs(ez) / b) ** 4
            y = H * tt ** expo + lift * cf * (1 - tt) ** 2
            row.append(Vector((x, y, z)))
        rowsP.append(row)
    top, under = Poly(), Poly()
    n = len(eave)
    dn = Vector((0, -th, 0))
    for k in range(rows):
        r0, r1 = rowsP[k], rowsP[k + 1]
        for i in range(n):
            j = (i + 1) % n
            top.face([r0[i], r0[j], r1[j], r1[i]], (0, 1, 0))
            under.face([r0[i] + dn, r0[j] + dn, r1[j] + dn, r1[i] + dn], (0, -1, 0))
    r0 = rowsP[0]
    for i in range(n):
        j = (i + 1) % n
        mid = (r0[i] + r0[j]) / 2
        under.face([r0[i], r0[j], r0[j] + dn, r0[i] + dn], (mid.x, 0, mid.z))
    top.face(rowsP[-1], (0, 1, 0))
    under.face([p + dn for p in rowsP[-1]], (0, -1, 0))
    return top.prim(), under.prim()


def hip_roof(a, b, r, H, th, lift=0.0, per=6, rows=5, expo=1.6):
    """寄棟（四坡）屋頂；r＝屋脊半長（0＝方錐，五重塔用）。a >= b，屋簷外緣半寬 a、半深 b。"""
    corners = [(a, b), (a, -b), (-a, -b), (-a, b)]
    eave, ridge = [], []
    for k in range(4):
        x0, z0 = corners[k]
        x1, z1 = corners[(k + 1) % 4]
        for j in range(per):
            t = j / per
            x, z = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
            eave.append((x, z))
            if abs(abs(z) - b) < 1e-6 and abs(x) < a - 1e-6:
                ridge.append((x * r / a, 0.0))
            else:
                ridge.append((math.copysign(r, x) if r > 0 else 0.0, 0.0))
    return ring_roof(eave, ridge, H, th, lift, rows, expo, a=a, b=b)


def poly_roof(n, R, H, th, lift=0.0, rows=4, expo=1.5):
    """正 n 角錐屋頂（石燈籠的笠、涼亭）。"""
    eave = [(R * math.cos(2 * math.pi * i / n), R * math.sin(2 * math.pi * i / n)) for i in range(n)]
    eave = eave[::-1]
    ridge = [(0.0, 0.0)] * n
    # 角翹：用 |cos| |sin| 的乘積算不準多邊形頂點，改成每個頂點都翹（lift 只作用在頂點上）
    top, under = ring_roof(eave, ridge, H, th, 0.0, rows, expo, tmax=0.9)
    if lift:
        for prim in (top, under):
            v = prim[0]
            for i, p in enumerate(v):
                rr = math.hypot(p[0], p[2])
                if rr > R * 0.97:
                    v[i] = (p[0] * 1.06, p[1] + lift, p[2] * 1.06)
    return top, under


def gable_y(u, bl, bs, H, expo):
    """切妻屋頂離屋脊水平距離 u 處的高度（相對屋頂底）。較長的那一坡同樣的曲線、屋簷落得更低。"""
    tt = 1 - u / bl
    return H - (H - H * tt ** expo) * (bl / bs)


def gable_roof(a, bf, bb, H, th, cols=6, rows=5, expo=1.5, sori=0.0):
    """切妻（兩坡）屋頂，屋脊沿 x、高 H：a＝半長（含出簷），bf／bb＝前／後坡的水平長（神社流造前坡較長）。"""
    top, under = Poly(), Poly()
    dn = Vector((0, -th, 0))
    bs = min(bf, bb)
    for side, bl in ((1, bf), (-1, bb)):
        G = []
        for i in range(cols + 1):
            x = -a + 2 * a * i / cols
            col = []
            for k in range(rows + 1):
                tt = k / rows
                u = bl * (1 - tt)
                y = gable_y(u, bl, bs, H, expo) + (abs(x) / a) ** 3 * sori * (1 - tt)
                col.append(Vector((x, y, side * u)))
            G.append(col)
        for i in range(cols):
            for k in range(rows):
                q = [G[i][k], G[i + 1][k], G[i + 1][k + 1], G[i][k + 1]]
                top.face(q, (0, 1, 0))
                under.face([p + dn for p in q], (0, -1, 0))
        for i in range(cols):  # 屋簷厚度
            p, q = G[i][0], G[i + 1][0]
            under.face([p, q, q + dn, p + dn], (0, 0, side))
        for i, sx in ((0, -1), (cols, 1)):  # 破風（山牆邊）厚度
            for k in range(rows):
                p, q = G[i][k], G[i][k + 1]
                under.face([p, q, q + dn, p + dn], (sx, 0, 0))
    return top.prim(), under.prim()


# ================================================================ 登記物件

ITEMS = []


def add(name, cat, use, dens, desc, ob, h=None, s=None, yaw=0.0, center=None, limit=None):
    center = center or ('base' if cat == 'tree' else 'bbox')
    normalize(ob, h=h, s=s, yaw=yaw, center=center)
    ob.name = name
    ob.data.name = name
    lim = limit or (LIMIT_LANDMARK if cat == 'landmark' else LIMIT)
    t0 = tri_count(ob)
    if t0 > lim:
        decimate(ob, lim)
    dedupe_slots(ob)
    v = verts_np(ob.data)
    d = v.max(0) - v.min(0)
    emissive = sorted({m.name for m in ob.data.materials if m and mat_color(m)[1] > 0
                       or (m and m.use_nodes and m.node_tree.nodes['Principled BSDF'].inputs['Emission Color'].is_linked)})
    srcs = json.loads(ob.get('src', '[]'))
    ITEMS.append(dict(
        name=name, category=cat, use=use, density=dens, desc=desc,
        size=[round(float(d[0]), 2), round(float(d[1]), 2), round(float(d[2]), 2)],
        tris=tri_count(ob), tris_source=t0 if t0 != tri_count(ob) else None,
        materials=[m.name for m in ob.data.materials if m],
        emissive=emissive,
        source=[source_info(s) for s in srcs] if srcs else [dict(pack='自製（build_props.py 程式產生）', file='', license='同本 repo', url='')],
        obj=ob))
    print(f'  {name:22s} {cat:9s} {d[0]:6.2f} x {d[1]:6.2f} x {d[2]:6.2f} m  tris {t0}' + (f' -> {tri_count(ob)}' if t0 != tri_count(ob) else ''))
    return ob


# 密度寫法：per_ha＝撒的區域裡每公頃幾個；per_100m＝沿賽道每 100 公尺幾個（兩側合計）；per_track＝一條賽道放幾個
def D(**k):
    return k


# ================================================================ 日式物件（程式畫）

def M4(pos=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    return M(pos, rot, scale)


def torii(H=7.0, span=4.6, name='torii'):
    """明神鳥居：朱紅柱（微內傾）、黑色根卷、貫、額束＋額、島木、上翹的黑笠木。H＝笠木頂高，span＝兩柱中心距。"""
    k = H / 7.0
    R = pmat('JpVermilion', '#d8391c', rough=0.55)
    K = pmat('JpBlack', '#1d1b1b', rough=0.6)
    G = pmat('JpGold', '#d9a441', rough=0.35, metal=0.6)
    NV = pmat('JpNavy', '#1f2b45', rough=0.6)
    b = Builder(name)
    pr = 0.30 * k
    lean = 0.022
    for sx in (-1, 1):
        mt = M4((sx * span / 2, 0, 0), rot=(0, 0, sx * lean))
        b.add(cylinder(pr, H - 0.95 * k, 12, r2=pr * 0.9), R, mt)
        b.add(cylinder(pr * 1.18, 0.55 * k, 12), K, M4((sx * span / 2, 0, 0)))          # 根卷
        b.add(cylinder(pr * 1.25, 0.12 * k, 12), K, M4((sx * span / 2, 0.55 * k, 0)))
        b.add(box(0.12 * k, 0.32 * k, 0.5 * k), R, M4((sx * (span / 2 + 0.42 * k), 0.70 * H - 0.05 * k, 0)))  # 楔
    nl = span + 1.3 * k
    b.add(box(nl, 0.36 * k, 0.26 * k), R, M4((0, 0.70 * H, 0)))                           # 貫
    b.add(box(0.34 * k, 0.95 * k, 0.24 * k, base=True), R, M4((0, 0.70 * H + 0.18 * k, 0)))  # 額束
    b.add(box(0.85 * k, 1.05 * k, 0.12 * k), NV, M4((0, 0.70 * H + 0.75 * k, 0.15 * k)))  # 額
    b.add(box(0.95 * k, 1.15 * k, 0.08 * k), G, M4((0, 0.70 * H + 0.75 * k, 0.11 * k)))
    L = span + 3.0 * k
    sori = 0.42 * k
    pts = [(x, H - 0.28 * k + sori * (abs(x) / (L / 2)) ** 2.6, 0) for x in np.linspace(-L / 2, L / 2, 15)]
    b.add(sweep(pts, 0.46 * k, 0.52 * k), K)                                            # 笠木（黑）
    pts2 = [(x, H - 0.70 * k + 0.6 * sori * (abs(x) / (L / 2)) ** 2.6, 0) for x in np.linspace(-L / 2 + 0.2 * k, L / 2 - 0.2 * k, 13)]
    b.add(sweep(pts2, 0.40 * k, 0.44 * k), R)                                          # 島木（朱）
    return proc(b)


def stone_lantern_kasuga():
    """春日型石燈籠：基礎、竿、中台、火袋（發光）、六角笠（角翹）、寶珠。高約 2.4 m。"""
    S = pmat('JpStone', '#b9b3a7', rough=0.95)
    S2 = pmat('JpStoneDark', '#9a958b', rough=0.95)
    GL = pmat('JpLanternGlow', '#ffd27a', rough=0.5, emit=2.5)
    b = Builder('toro')
    b.add(prism(0.50, 0.22, 6), S2)
    b.add(prism(0.42, 0.16, 6, r2=0.30), S, M4((0, 0.22, 0)))
    b.add(cylinder(0.15, 0.85, 10, r2=0.13), S, M4((0, 0.38, 0)))
    b.add(torus(0.16, 0.035, 10, 4), S, M4((0, 0.80, 0), rot=(math.pi / 2, 0, 0)))
    b.add(prism(0.22, 0.16, 6, r2=0.40), S, M4((0, 1.22, 0)))
    b.add(prism(0.42, 0.08, 6), S2, M4((0, 1.38, 0)))
    for i in range(6):  # 火袋的六根柱
        a = 2 * math.pi * (i + 0.5) / 6
        b.add(box(0.09, 0.46, 0.09, base=True), S, M4((0.30 * math.cos(a), 1.46, 0.30 * math.sin(a)), rot=(0, -a, 0)))
    b.add(prism(0.24, 0.44, 6), GL, M4((0, 1.46, 0)))
    b.add(prism(0.36, 0.06, 6), S2, M4((0, 1.90, 0)))
    top, under = poly_roof(6, 0.68, 0.36, 0.09, lift=0.07)
    b.add(top, S, M4((0, 2.02, 0)))
    b.add(under, S2, M4((0, 2.02, 0)))
    b.add(sphere(0.11, 8, 5, smooth=False), S, M4((0, 2.40, 0), scale=(1, 0.6, 1)))
    b.add(sphere(0.10, 8, 6, smooth=False), S, M4((0, 2.50, 0)))
    b.add(cone(0.06, 0.12, 8), S, M4((0, 2.56, 0)))
    return proc(b)


def stone_lantern_yukimi():
    """雪見燈籠：三腳、低矮、大傘狀的笠。"""
    S = pmat('JpStone', '#b9b3a7', rough=0.95)
    S2 = pmat('JpStoneDark', '#9a958b', rough=0.95)
    GL = pmat('JpLanternGlow', '#ffd27a', rough=0.5, emit=2.5)
    b = Builder('yukimi')
    for i in range(3):
        a = 2 * math.pi * i / 3 + math.pi / 2
        limb(b, (0.55 * math.cos(a), 0, 0.55 * math.sin(a)), (0.22 * math.cos(a), 0.55, 0.22 * math.sin(a)), 0.07, 0.06, S, 6, False)
    b.add(prism(0.38, 0.08, 6), S2, M4((0, 0.55, 0)))
    b.add(prism(0.24, 0.32, 6), GL, M4((0, 0.63, 0)))
    for i in range(6):
        a = 2 * math.pi * (i + 0.5) / 6
        b.add(box(0.08, 0.32, 0.08, base=True), S, M4((0.30 * math.cos(a), 0.63, 0.30 * math.sin(a)), rot=(0, -a, 0)))
    top, under = poly_roof(6, 0.95, 0.32, 0.10, lift=0.06)
    b.add(top, S, M4((0, 0.98, 0)))
    b.add(under, S2, M4((0, 0.98, 0)))
    b.add(sphere(0.10, 8, 6, smooth=False), S, M4((0, 1.36, 0)))
    b.add(cone(0.05, 0.10, 8), S, M4((0, 1.42, 0)))
    return proc(b)


def paper_lantern_post():
    """木柱掛紅提燈（發光），參道、店門口用。"""
    W = pmat('JpDarkWood', '#4a3326', rough=0.8)
    RD = pmat('JpChochin', '#e2402a', rough=0.6, emit=1.8, emit_color='#ff7a3a')
    K = pmat('JpBlack', '#1d1b1b', rough=0.6)
    b = Builder('chochin')
    b.add(box(0.16, 2.9, 0.16, base=True), W)
    b.add(box(0.36, 0.2, 0.36, base=True), W)
    b.add(box(0.12, 0.10, 0.9), W, M4((0, 2.75, 0.38)))
    b.add(cylinder(0.012, 0.25, 4), K, M4((0, 2.45, 0.72)))
    b.add(sphere(0.28, 10, 7), RD, M4((0, 2.12, 0.72), scale=(1, 1.35, 1)))
    b.add(cylinder(0.17, 0.08, 10), K, M4((0, 2.45, 0.72)))
    b.add(cylinder(0.17, 0.08, 10), K, M4((0, 1.68, 0.72)))
    return proc(b)


def momiji_like(rnd, name, H, crown, colors, trunk_col, n_limbs=4, n_blob=12, blob_r=(1.2, 1.9), flat=0.78, lean=0.0,
                limb_up=(0.45, 0.85), trunk_r=0.32):
    """闊葉樹：彎一點的樹幹＋幾根枝＋一團團低多邊形的葉（花）團。櫻花、紅葉、松都用這支。"""
    T = pmat(trunk_col[0], trunk_col[1], rough=0.9)
    Ms = [pmat(n, c, rough=0.85) for n, c in colors]
    b = Builder(name)
    # 樹幹：三節，往一個方向微彎
    p = Vector((0, 0, 0))
    ang = rnd.uniform(0, 6.28)
    lean_dir = Vector((math.cos(ang), 0, math.sin(ang)))
    th = H * 0.42
    r = trunk_r
    pts = [p.copy()]
    for k in range(3):
        q = pts[-1] + Vector((0, th / 3, 0)) + lean_dir * (lean * th / 3 + rnd.uniform(-0.12, 0.12))
        pts.append(q)
    for k in range(3):
        limb(b, pts[k], pts[k + 1], r * (1 - 0.18 * k), r * (1 - 0.18 * (k + 1)), T, 7)
    b.add(cone(r * 1.6, 0.5, 7), T, M4(tuple(pts[0])))  # 根張り
    top = pts[-1]
    tips = []
    for i in range(n_limbs):
        a = 2 * math.pi * i / n_limbs + rnd.uniform(-0.4, 0.4)
        up = rnd.uniform(*limb_up)
        L = crown * rnd.uniform(0.75, 1.0)
        mid = top + Vector((math.cos(a) * L * 0.5, L * up * 0.6, math.sin(a) * L * 0.5))
        end = top + Vector((math.cos(a) * L, L * up, math.sin(a) * L))
        limb(b, top, mid, r * 0.55, r * 0.38, T, 6)
        limb(b, mid, end, r * 0.38, r * 0.18, T, 5)
        tips += [mid, end]
    # 葉團：在枝端與樹冠範圍內，下層的顏色較深
    cy = top.y + crown * 0.45
    for i in range(n_blob):
        if i < len(tips):
            c = tips[i] + Vector((0, rnd.uniform(0.1, 0.5), 0))
        else:  # 圓頂狀的樹冠：外圈低、中間高
            a = rnd.uniform(0, 6.28)
            rr = crown * math.sqrt(rnd.uniform(0.0, 1.0)) * 1.05
            yy = cy - 0.4 + crown * 0.55 * math.sqrt(max(0.0, 1 - (rr / (crown * 1.1)) ** 2)) * rnd.uniform(0.55, 1.05)
            c = Vector((top.x + math.cos(a) * rr, yy, top.z + math.sin(a) * rr))
        rad = rnd.uniform(*blob_r)
        mi = 0 if c.y < cy - 0.1 else rnd.randrange(1, len(Ms)) if len(Ms) > 1 else 0
        b.add(blob(rad, rnd, 1, 0.18, (1, flat, 1)), Ms[mi], M4(tuple(c), rot=(0, rnd.uniform(0, 6.28), 0)))
    return proc(b)


def matsu(rnd, name='matsu'):
    """日本黑松：斜而彎的樹幹、水平伸出的枝，上面一片片扁平的針葉團（庭園修剪的樣子）。"""
    T = pmat('JpPineBark', '#5b4335', rough=0.95)
    G1 = pmat('JpPineNeedle', '#2f5e3b', rough=0.9)
    G2 = pmat('JpPineNeedleLight', '#467a46', rough=0.9)
    b = Builder(name)
    pts = [Vector((0, 0, 0)), Vector((0.5, 2.2, 0.1)), Vector((0.2, 4.2, -0.2)), Vector((0.9, 6.0, 0.0)), Vector((0.6, 7.4, 0.2))]
    for k in range(len(pts) - 1):
        limb(b, pts[k], pts[k + 1], 0.38 - 0.06 * k, 0.32 - 0.06 * k, T, 7)
    pads = []
    for k, (hy, L, a) in enumerate(((2.6, 3.4, 0.4), (3.6, 3.0, 2.6), (4.6, 2.8, 4.4), (5.6, 2.3, 1.4), (6.4, 1.8, 3.4))):
        base = pts[1] + (pts[2] - pts[1]) * 0.5 if hy < 4 else pts[3]
        base = Vector((base.x, hy, base.z))
        end = base + Vector((math.cos(a) * L, 0.35, math.sin(a) * L))
        limb(b, base, end, 0.16, 0.08, T, 5)
        pads.append((end, 1.5 - 0.12 * k))
    pads.append((pts[-1] + Vector((0, 0.3, 0)), 1.5))
    for c, rr in pads:
        b.add(blob(rr, rnd, 1, 0.15, (1.15, 0.36, 1.0)), G1, M4(tuple(c), rot=(0, rnd.uniform(0, 6.28), 0)))
        b.add(blob(rr * 0.75, rnd, 1, 0.15, (1.1, 0.32, 1.0)), G2, M4(tuple(c + Vector((0.1, 0.32, 0.05))), rot=(0, rnd.uniform(0, 6.28), 0)))
    return proc(b)


def bamboo(rnd, n=12, H=(8.5, 11.5), spread=2.2, name='bamboo'):
    """竹叢：細長、帶節的竹竿，上半部一叢叢竹葉。"""
    C = pmat('JpBamboo', '#7fb24a', rough=0.6)
    N = pmat('JpBambooNode', '#5f8f37', rough=0.6)
    Lf = [pmat('JpBambooLeaf', '#5e9e3c', rough=0.85), pmat('JpBambooLeafLight', '#86c255', rough=0.85)]
    b = Builder(name)
    for i in range(n):
        a = rnd.uniform(0, 6.28)
        rr = spread * math.sqrt(rnd.random())
        x, z = math.cos(a) * rr, math.sin(a) * rr
        h = rnd.uniform(*H)
        r = rnd.uniform(0.07, 0.1)
        tilt = Vector((rnd.uniform(-0.08, 0.08), 1, rnd.uniform(-0.08, 0.08))).normalized()
        p0 = Vector((x, 0, z))
        p1 = p0 + tilt * h
        limb(b, p0, p1, r, r * 0.6, C, 6, False)
        nodes = int(h / 0.95)
        for k in range(1, nodes):
            q = p0 + tilt * (k * 0.95)
            mt, _ = seg(q, q + tilt * 0.05)
            b.add(cylinder(r * 1.25, 0.05, 6, cap=False, smooth=False), N, mt)
        for k in range(5):  # 竹葉：從竹竿往外斜垂的細長葉簇
            q = p0 + tilt * (h * rnd.uniform(0.5, 0.97))
            yaw = rnd.uniform(0, 6.28)
            L = rnd.uniform(1.1, 1.8)
            mt = M4(tuple(q), rot=(0, yaw, 0)) @ M4(rot=(0, 0, -rnd.uniform(1.75, 2.2)))  # 往外、略往下
            b.add(cone(0.32, L, 4), Lf[k % 2], mt @ M4(scale=(1.0, 1.0, 0.35)))
    return proc(b)


def taiko_bridge():
    """太鼓橋：朱紅拱橋，木橋面、欄杆、擬寶珠。跨距 12 m、寬 3.2 m（沿 x）。"""
    R = pmat('JpVermilion', '#d8391c', rough=0.55)
    W = pmat('JpWood', '#8b6243', rough=0.85)
    G = pmat('JpGold', '#d9a441', rough=0.35, metal=0.6)
    b = Builder('bridge')
    L, rise, w = 12.0, 2.0, 3.2
    xs = np.linspace(-L / 2, L / 2, 17)
    arc = lambda x: rise * (1 - (2 * x / L) ** 2) + 0.15  # noqa: E731
    b.add(sweep([(x, arc(x), 0) for x in xs], 0.3, w), W)
    for sz in (-1, 1):
        b.add(sweep([(x, arc(x) - 0.45, sz * (w / 2 - 0.15)) for x in xs], 0.6, 0.3), R)       # 桁
        b.add(sweep([(x, arc(x) + 0.95, sz * w / 2) for x in xs], 0.12, 0.14), R)              # 笠木（欄杆頂）
        b.add(sweep([(x, arc(x) + 0.45, sz * w / 2) for x in xs], 0.08, 0.08), R)
        for x in np.linspace(-L / 2 + 0.2, L / 2 - 0.2, 9):
            b.add(box(0.16, 1.0, 0.16, base=True), R, M4((x, arc(x), sz * w / 2)))
        for x in (-L / 2 + 0.2, L / 2 - 0.2):
            b.add(box(0.24, 1.15, 0.24, base=True), R, M4((x, arc(x), sz * w / 2)))
            b.add(sphere(0.17, 8, 6, smooth=False), G, M4((x, arc(x) + 1.3, sz * w / 2), scale=(1, 0.9, 1)))
            b.add(cone(0.08, 0.22, 8), G, M4((x, arc(x) + 1.42, sz * w / 2)))
    for x in (-L / 2 + 1.5, L / 2 - 1.5):  # 橋墩
        for sz in (-1, 1):
            b.add(cylinder(0.18, arc(x) - 0.6, 8), R, M4((x, 0, sz * (w / 2 - 0.3))))
    return proc(b)


def machiya():
    """二層町家：格子門面、暖簾、中間的小屋簷、蟲籠窗、瓦頂。寬 6.5 m 深 9 m，門高 2.2 m。"""
    PL = pmat('JpPlaster', '#efe7d6', rough=0.9)
    DW = pmat('JpDarkWood', '#4a3326', rough=0.8)
    TL = pmat('JpRoofTile', '#3d4655', rough=0.6)
    TU = pmat('JpRafter', '#6b4c38', rough=0.85)
    NO = pmat('JpNoren', '#27406e', rough=0.9)
    ST = pmat('JpStoneBase', '#8f8a80', rough=0.95)
    IN = pmat('JpInterior', '#2a211c', rough=0.9)
    GL = pmat('JpLanternGlow', '#ffd27a', rough=0.5, emit=2.5)
    b = Builder('machiya')
    w, d = 6.5, 9.0
    fz = d / 2
    b.add(box(w + 0.3, 0.3, d + 0.3, base=True), ST)
    b.add(box(w, 2.9, d, base=True), PL, M4((0, 0.3, 0)))
    for sx in (-1, 1):  # 柱
        b.add(box(0.24, 6.1, 0.24, base=True), DW, M4((sx * w / 2, 0.3, fz)))
        b.add(box(0.24, 6.1, 0.24, base=True), DW, M4((sx * w / 2, 0.3, -fz)))
    b.add(box(w + 0.1, 0.22, 0.26), DW, M4((0, 3.25, fz)))
    # 一樓門面：入口（暗）＋暖簾，其餘是格子
    b.add(box(1.8, 2.2, 0.06, base=True), IN, M4((-1.5, 0.3, fz + 0.01)))
    for k in range(3):
        b.add(box(0.56, 0.75, 0.04, base=True), NO, M4((-2.1 + k * 0.6, 1.75, fz + 0.12)))
    b.add(box(0.1, 2.3, 0.14, base=True), DW, M4((-2.45, 0.3, fz + 0.05)))
    b.add(box(0.1, 2.3, 0.14, base=True), DW, M4((-0.55, 0.3, fz + 0.05)))
    b.add(box(2.0, 0.12, 0.16), DW, M4((-1.5, 2.55, fz + 0.06)))
    b.add(box(3.6, 2.35, 0.06, base=True), IN, M4((1.35, 0.55, fz + 0.01)))
    for k in range(17):  # 格子
        b.add(box(0.06, 2.35, 0.08, base=True), DW, M4((-0.4 + k * 0.22, 0.55, fz + 0.06)))
    b.add(box(3.6, 0.1, 0.1), DW, M4((1.35, 2.9, fz + 0.07)))
    b.add(box(3.6, 0.1, 0.1), DW, M4((1.35, 0.6, fz + 0.07)))
    # 提燈
    b.add(sphere(0.2, 8, 6), GL, M4((-2.75, 2.3, fz + 0.35), scale=(1, 1.3, 1)))
    # 中間的小屋簷（一樓上方，前後各一）
    for sz in (1, -1):
        G = [[Vector((x, 3.7 - 0.55 * t, sz * (fz + 1.0 * t))) for t in (0, 1)] for x in (-w / 2 - 0.3, w / 2 + 0.3)]
        P, U = Poly(), Poly()
        q = [G[0][0], G[1][0], G[1][1], G[0][1]]
        P.face(q, (0, 1, 0))
        U.face([p + Vector((0, -0.12, 0)) for p in q], (0, -1, 0))
        U.face([G[0][1], G[1][1], G[1][1] + Vector((0, -0.12, 0)), G[0][1] + Vector((0, -0.12, 0))], (0, 0, sz))
        b.add(P.prim(), TL)
        b.add(U.prim(), TU)
    # 二樓（較矮）＋蟲籠窗
    b.add(box(w, 2.2, d, base=True), PL, M4((0, 3.2, 0)))
    b.add(box(w + 0.1, 0.18, 0.26), DW, M4((0, 5.35, fz)))
    b.add(box(3.2, 0.9, 0.05, base=True), IN, M4((0, 4.0, fz + 0.01)))
    for k in range(9):
        b.add(box(0.16, 0.9, 0.12, base=True), PL, M4((-1.4 + k * 0.35, 4.0, fz + 0.05)))
    b.add(box(3.4, 0.12, 0.14), DW, M4((0, 4.95, fz + 0.06)))
    # 屋頂：切妻，屋脊與街道平行（沿 x）
    top, under = gable_roof(w / 2 + 0.6, fz + 1.0, fz + 1.0, 2.3, 0.2, cols=4, rows=5, expo=1.25)
    b.add(top, TL, M4((0, 5.35, 0)))
    b.add(under, TU, M4((0, 5.35, 0)))
    b.add(box(w + 1.4, 0.32, 0.36), TL, M4((0, 7.7, 0)))
    for sx in (-1, 1):
        b.add(box(0.3, 0.6, 0.5, base=True), TL, M4((sx * (w / 2 + 0.6), 7.55, 0)))  # 鬼瓦
    for sx in (-1, 1):  # 山牆（側面三角形）
        P = Poly()
        P.face([(sx * w / 2, 5.4, -fz), (sx * w / 2, 5.4, fz), (sx * w / 2, 5.4 + 2.2, 0)], (sx, 0, 0))
        b.add(P.prim(), PL)
    return proc(b)


def hiraya():
    """平屋（和風平房）：石基、緣側、障子、白牆、寄棟瓦頂（四角微翹）。寬 9 m 深 7 m。"""
    PL = pmat('JpPlaster', '#efe7d6', rough=0.9)
    DW = pmat('JpDarkWood', '#4a3326', rough=0.8)
    WD = pmat('JpWood', '#8b6243', rough=0.85)
    TL = pmat('JpRoofTile', '#3d4655', rough=0.6)
    TU = pmat('JpRafter', '#6b4c38', rough=0.85)
    SH = pmat('JpShoji', '#f6efdf', rough=0.9)
    ST = pmat('JpStoneBase', '#8f8a80', rough=0.95)
    b = Builder('hiraya')
    w, d = 9.0, 7.0
    fz = d / 2
    b.add(box(w + 0.4, 0.5, d + 0.4, base=True), ST)
    b.add(box(w + 0.4, 0.14, 1.3, base=True), WD, M4((0, 0.5, fz + 0.6)))       # 緣側
    b.add(box(w, 2.7, d, base=True), PL, M4((0, 0.6, 0)))
    for i in range(7):
        x = -w / 2 + i * w / 6
        for z in (fz, -fz):
            b.add(box(0.2, 2.7, 0.2, base=True), DW, M4((x, 0.6, z)))
        b.add(box(0.18, 2.7, 0.18, base=True), DW, M4((x, 0.6, fz + 1.15)))      # 緣側外柱
    for z in (-fz / 3, fz / 3):
        for sx in (-1, 1):
            b.add(box(0.2, 2.7, 0.2, base=True), DW, M4((sx * w / 2, 0.6, z)))
    for i in range(6):  # 障子
        x0 = -w / 2 + i * w / 6
        b.add(box(w / 6 - 0.3, 2.1, 0.05, base=True), SH, M4((x0 + w / 12, 0.75, fz + 0.03)))
        for k in range(1, 4):
            b.add(box(w / 6 - 0.3, 0.04, 0.07), DW, M4((x0 + w / 12, 0.75 + k * 0.52, fz + 0.05)))
        for k in (-1, 0, 1):
            b.add(box(0.04, 2.1, 0.07, base=True), DW, M4((x0 + w / 12 + k * 0.4, 0.75, fz + 0.05)))
    b.add(box(w + 0.1, 0.22, 0.24), DW, M4((0, 3.2, fz)))
    b.add(box(w + 0.4, 0.2, 0.2), DW, M4((0, 3.25, fz + 1.15)))
    a, bb = w / 2 + 1.4, fz + 1.4 + 0.0
    top, under = hip_roof(a, bb, a - bb, 2.9, 0.24, lift=0.35, per=6, rows=5, expo=1.5)
    b.add(top, TL, M4((0, 3.3, 0)))
    b.add(under, TU, M4((0, 3.3, 0)))
    b.add(box(2 * (a - bb) + 0.6, 0.34, 0.4), TL, M4((0, 6.2, 0)))
    for sx in (-1, 1):
        b.add(box(0.36, 0.62, 0.5, base=True), TL, M4((sx * (a - bb + 0.25), 6.05, 0)))
    return proc(b)


def shrine():
    """神社拜殿（流造）：石基壇、高床、朱紅柱、白牆、正面階梯、銅綠色切妻屋頂（前坡長）、千木、鰹木、注連縄、賽錢箱。寬 9 m。"""
    R = pmat('JpVermilion', '#d8391c', rough=0.55)
    PL = pmat('JpPlaster', '#efe7d6', rough=0.9)
    WD = pmat('JpWood', '#8b6243', rough=0.85)
    DW = pmat('JpDarkWood', '#4a3326', rough=0.8)
    CU = pmat('JpCopperRoof', '#4f9a83', rough=0.55)
    CU2 = pmat('JpCopperRoofUnder', '#7a5a42', rough=0.85)
    G = pmat('JpGold', '#d9a441', rough=0.35, metal=0.6)
    ST = pmat('JpStoneBase', '#8f8a80', rough=0.95)
    RP = pmat('JpRope', '#d8c27a', rough=0.95)
    WH = pmat('JpPaperWhite', '#fbfaf5', rough=0.9)
    IN = pmat('JpInterior', '#2a211c', rough=0.9)
    b = Builder('shrine')
    w, d = 9.0, 7.0
    fz = d / 2
    b.add(box(w + 3, 0.4, d + 4.5, base=True), ST, M4((0, 0, 0.6)))
    b.add(box(w + 1.6, 0.35, d + 2.6, base=True), ST, M4((0, 0.4, 0.5)))
    fl = 1.6  # 地板高
    b.add(box(w + 1.2, 0.2, d + 1.2, base=True), WD, M4((0, fl - 0.2, 0)))          # 緣
    rz = fz + 0.6
    b.add(box(w + 1.2, 0.08, 0.1), R, M4((0, fl + 0.75, -rz)))                      # 緣的欄杆
    for sx in (-1, 1):
        b.add(box(0.1, 0.08, d + 1.2), R, M4((sx * (w / 2 + 0.6), fl + 0.75, 0)))
        b.add(box(w / 2 - 1.1, 0.08, 0.1), R, M4((sx * (w / 4 + 1.35), fl + 0.75, rz)))
        for x in np.linspace(1.8, w / 2 + 0.6, 4):
            b.add(box(0.1, 0.8, 0.1, base=True), R, M4((sx * x, fl, rz)))
    for x in np.linspace(-w / 2 - 0.6, w / 2 + 0.6, 9):
        b.add(box(0.1, 0.8, 0.1, base=True), R, M4((x, fl, -rz)))
    for z in np.linspace(-rz, rz, 7):
        for sx in (-1, 1):
            b.add(box(0.1, 0.8, 0.1, base=True), R, M4((sx * (w / 2 + 0.6), fl, z)))
    # 本體：柱、白牆、正面板戶（暗）
    ch = 3.0
    b.add(box(w - 0.2, ch, d - 0.2, base=True), PL, M4((0, fl, 0)))
    b.add(box(w - 2.0, ch - 0.6, 0.05, base=True), IN, M4((0, fl, fz - 0.08)))
    for k in range(5):
        b.add(box(0.05, ch - 0.6, 0.08, base=True), DW, M4((-(w - 2.0) / 2 + k * (w - 2.0) / 4, fl, fz - 0.04)))
    for x in np.linspace(-w / 2, w / 2, 5):
        for z in (fz, -fz, 0):
            if z == 0 and abs(x) < w / 2 - 0.1:
                continue
            b.add(cylinder(0.2, fl + ch - 0.55, 10), R, M4((x, 0.75, z)))
    for z in (fz, -fz):  # 前後的貫
        b.add(box(w + 0.4, 0.26, 0.24), R, M4((0, fl + ch - 0.35, z)))
        b.add(box(w + 0.4, 0.2, 0.22), R, M4((0, fl + 0.25, z)))
    for sx in (-1, 1):
        b.add(box(0.24, 0.26, d + 0.4), R, M4((sx * w / 2, fl + ch - 0.35, 0)))
    # 屋頂：切妻，屋脊沿 x，前坡延伸到向拜（流造）
    rh, bf, bb, th = 3.2, fz + 3.3, fz + 1.2, 0.28
    ry = fl + ch - 0.2
    top, under = gable_roof(w / 2 + 1.3, bf, bb, rh, th, cols=6, rows=6, expo=1.35, sori=0.25)
    # 向拜柱：撐到前坡的底面
    zk = fz + 2.3
    yk = ry + gable_y(zk, bf, bb, rh, 1.35) - th - 0.05
    for x in (-w / 2, -w / 6, w / 6, w / 2):
        b.add(cylinder(0.17, yk - 0.75, 10), R, M4((x, 0.75, zk)))
    b.add(box(w + 0.4, 0.24, 0.22), R, M4((0, yk - 0.2, zk)))
    # 階梯
    for k in range(5):
        b.add(box(3.2, 0.3, 0.42, base=True), WD, M4((0, 0.75 + k * 0.17 - 0.13, fz + 2.6 - k * 0.38)))
    for sx in (-1, 1):  # 階梯扶手（沿 z 斜上）
        b.add(sweep([(fz + 2.9, 1.55, 0), (fz + 0.6, fl + 0.75, 0)], 0.1, 0.1), R, M4((sx * 1.7, 0, 0), rot=(0, -math.pi / 2, 0)))
        b.add(box(0.12, 0.85, 0.12, base=True), R, M4((sx * 1.7, 0.75, fz + 2.9)))
    # 賽錢箱
    b.add(box(1.6, 0.7, 0.7, base=True), DW, M4((0, 0.75, fz + 3.4)))
    b.add(box(1.7, 0.08, 0.8, base=True), WD, M4((0, 1.45, fz + 3.4)))
    b.add(top, CU, M4((0, ry, 0)))
    b.add(under, CU2, M4((0, ry, 0)))
    b.add(box(w + 2.8, 0.42, 0.55), CU, M4((0, ry + rh + 0.05, 0)))
    for sx in (-1, 1):  # 山牆
        P = Poly()
        P.face([(sx * (w / 2), ry, -fz), (sx * (w / 2), ry, fz), (sx * (w / 2), ry + rh * 0.92, 0)], (sx, 0, 0))
        b.add(P.prim(), PL)
        # 千木：兩片交叉的板，從屋脊兩端往上伸
        for sz in (-1, 1):
            b.add(box(0.14, 2.4, 0.32), WD, M4((sx * (w / 2 + 1.2), ry + rh + 0.6, sz * 0.35), rot=(sz * 0.55, 0, 0)))
            b.add(box(0.16, 0.12, 0.34), G, M4((sx * (w / 2 + 1.2), ry + rh + 1.55, sz * 0.92), rot=(sz * 0.55, 0, 0)))
    for x in np.linspace(-w / 2 + 0.6, w / 2 - 0.6, 5):  # 鰹木
        b.add(cylinder(0.2, 1.6, 8), DW, M4((x, ry + rh + 0.45, -0.8), rot=(math.pi / 2, 0, 0)))
        b.add(cylinder(0.205, 0.12, 8), G, M4((x, ry + rh + 0.45, -0.8), rot=(math.pi / 2, 0, 0)))
        b.add(cylinder(0.205, 0.12, 8), G, M4((x, ry + rh + 0.45, 0.68), rot=(math.pi / 2, 0, 0)))
    # 注連縄：向拜下垂掛的粗繩＋紙垂＋鈴
    zr = fz + 2.15
    yr = fl + ch - 0.95
    xs = np.linspace(-w / 2 + 0.3, w / 2 - 0.3, 13)
    rope = [(x, yr - 0.45 * (1 - (2 * x / (w - 0.6)) ** 2), 0) for x in xs]
    b.add(sweep(rope, 0.34, 0.34), RP, M4((0, 0, zr)))
    for x in np.linspace(-w / 2 + 1.2, w / 2 - 1.2, 5):
        y = yr - 0.45 * (1 - (2 * x / (w - 0.6)) ** 2)
        for k in range(3):
            b.add(box(0.18, 0.2, 0.02, base=True), WH, M4((x + (0.06 if k % 2 else -0.06), y - 0.4 - k * 0.22, zr + 0.12)))
    b.add(sphere(0.25, 8, 6, smooth=False), G, M4((0, yr - 1.05, zr)))
    b.add(cylinder(0.02, 0.5, 4), RP, M4((0, yr - 0.85, zr)))
    return proc(b)


def pagoda():
    """五重塔：石基壇、五層（白牆＋朱紅柱、斗栱、上翹的方錐瓦頂）、相輪（九輪）、水煙、寶珠。高約 30 m。"""
    R = pmat('JpVermilion', '#d8391c', rough=0.55)
    PL = pmat('JpPlaster', '#efe7d6', rough=0.9)
    TL = pmat('JpRoofTile', '#3d4655', rough=0.6)
    TU = pmat('JpBracket', '#c9893a', rough=0.75)
    BR = pmat('JpBronze', '#8a6a2c', rough=0.4, metal=0.7)
    G = pmat('JpGold', '#d9a441', rough=0.35, metal=0.6)
    ST = pmat('JpStoneBase', '#8f8a80', rough=0.95)
    IN = pmat('JpInterior', '#2a211c', rough=0.9)
    b = Builder('pagoda')
    b.add(box(12, 0.9, 12, base=True), ST)
    for k in range(3):
        b.add(box(2.4, 0.3, 0.6, base=True), ST, M4((0, k * 0.3, 6.3 + (2 - k) * 0.45)))
    y = 0.9
    for t in range(5):
        s = 7.2 - t * 0.75
        hb = 3.3 if t == 0 else 2.6
        b.add(box(s, hb, s, base=True), PL, M4((0, y, 0)))
        for sx in (-1, 0, 1):
            for sz in (-1, 1):
                if sx == 0:
                    b.add(box(1.1 if t == 0 else 0.8, hb - 0.4, 0.06, base=True), IN, M4((0, y, sz * (s / 2 + 0.01))))
                    b.add(box(1.1 if t == 0 else 0.8, hb - 0.4, 0.06, base=True), IN, M4((sz * (s / 2 + 0.01), y, 0), rot=(0, math.pi / 2, 0)))
                    continue
                for xx, zz in ((sx * s / 2, sz * s / 2), (sx * s / 6, sz * s / 2), (sz * s / 2, sx * s / 6)):
                    b.add(box(0.28, hb, 0.28, base=True), R, M4((xx, y, zz)))
        b.add(box(s + 0.2, 0.25, s + 0.2), R, M4((0, y + hb - 0.25, 0)))
        b.add(box(s + 1.0, 0.5, s + 1.0, base=True), TU, M4((0, y + hb, 0)))                # 斗栱
        b.add(box(s + 1.8, 0.3, s + 1.8, base=True), TU, M4((0, y + hb + 0.5, 0)))
        a = s / 2 + 2.2
        top, under = hip_roof(a, a, 0.0, 1.9, 0.32, lift=0.95, per=6, rows=5, expo=2.0)
        b.add(top, TL, M4((0, y + hb + 0.8, 0)))
        b.add(under, TU, M4((0, y + hb + 0.8, 0)))
        if t < 4:
            b.add(box(s - 0.6, 0.6, s - 0.6, base=True), PL, M4((0, y + hb + 0.8 + 0.4, 0)))
        y += hb + 0.8 + 1.0
    # 相輪
    y -= 0.2
    b.add(box(1.4, 0.6, 1.4, base=True), TL, M4((0, y, 0)))
    b.add(sphere(0.7, 10, 6, smooth=False), BR, M4((0, y + 0.6, 0), scale=(1, 0.6, 1)))
    b.add(cylinder(0.14, 7.0, 8), BR, M4((0, y + 0.8, 0)))
    for r in range(9):
        b.add(torus(0.5 - r * 0.015, 0.07, 12, 4), BR, M4((0, y + 1.5 + r * 0.42, 0), rot=(math.pi / 2, 0, 0)))
    for k in range(4):  # 水煙
        b.add(box(0.06, 0.9, 0.7, base=True), G, M4((0, y + 5.6, 0), rot=(0, k * math.pi / 4, 0)))
    b.add(sphere(0.3, 8, 6, smooth=False), G, M4((0, y + 6.8, 0)))
    b.add(sphere(0.22, 8, 6, smooth=False), G, M4((0, y + 7.3, 0)))
    b.add(cone(0.12, 0.35, 8), G, M4((0, y + 7.45, 0)))
    return proc(b)


# ================================================================ 其他主題的程式物件

def bungalow():
    """海邊高腳茅草屋：木樁、甲板、竹牆、茅草四坡頂、梯子。"""
    WD = pmat('BeachWood', '#9a6b43', rough=0.85)
    BM = pmat('BeachBambooWall', '#d9b77a', rough=0.85)
    TH = pmat('BeachThatch', '#d6b05e', rough=0.95)
    TH2 = pmat('BeachThatchUnder', '#a8803e', rough=0.95)
    IN = pmat('BeachInterior', '#3a2a1e', rough=0.9)
    b = Builder('bungalow')
    deck = 1.0
    for x in (-2.3, 0, 2.3):
        for z in (-2.3, 0, 2.3):
            b.add(cylinder(0.14, deck, 8), WD, M4((x, 0, z)))
    b.add(box(5.2, 0.16, 6.2, base=True), WD, M4((0, deck, 0.5)))
    for x in np.linspace(-2.6, 2.6, 8):  # 欄杆柱
        b.add(box(0.08, 0.9, 0.08, base=True), WD, M4((x, deck + 0.16, 3.6)))
    b.add(box(5.2, 0.08, 0.1), WD, M4((0, deck + 1.0, 3.6)))
    b.add(box(4.0, 2.4, 4.0, base=True), BM, M4((0, deck + 0.16, 0)))
    b.add(box(1.0, 2.0, 0.05, base=True), IN, M4((0, deck + 0.16, 2.01)))
    for sx in (-1, 1):
        b.add(box(0.05, 0.8, 1.0, base=True), IN, M4((sx * 2.01, deck + 1.1, 0)))
        b.add(box(0.8, 0.8, 0.05, base=True), IN, M4((sx * 1.3, deck + 1.1, 2.01)))
    for x in (-2, 2):
        for z in (-2, 2):
            b.add(box(0.16, 2.4, 0.16, base=True), WD, M4((x, deck + 0.16, z)))
    top, under = hip_roof(3.4, 3.4, 0.0, 2.4, 0.35, lift=0.0, per=4, rows=3, expo=1.0)
    b.add(top, TH, M4((0, deck + 2.5, 0)))
    b.add(under, TH2, M4((0, deck + 2.5, 0)))
    for k in range(4):  # 梯子
        b.add(box(1.0, 0.06, 0.25), WD, M4((-1.6, 0.25 + k * 0.25, 4.0 + (3 - k) * 0.22)))
    return proc(b)


def lifeguard_tower():
    """救生員瞭望台：白色高腳、紅頂小屋、斜梯、旗。"""
    WH = pmat('BeachWhite', '#f4f1ea', rough=0.7)
    RD = pmat('BeachRed', '#e0402e', rough=0.6)
    BL = pmat('BeachBlueWindow', '#3a86b8', rough=0.3)
    YL = pmat('BeachYellow', '#ffcf3a', rough=0.6)
    b = Builder('lifeguard')
    for x in (-1.0, 1.0):
        for z in (-1.0, 1.0):
            limb(b, (x * 1.15, 0, z * 1.15), (x, 2.4, z), 0.09, 0.08, WH, 6, False)
    b.add(box(2.8, 0.15, 3.2, base=True), WH, M4((0, 2.4, 0.2)))
    b.add(box(2.2, 1.9, 2.2, base=True), WH, M4((0, 2.55, -0.2)))
    b.add(box(1.8, 0.8, 0.05, base=True), BL, M4((0, 3.4, 0.91)))
    for sx in (-1, 1):
        b.add(box(0.05, 0.8, 1.6, base=True), BL, M4((sx * 1.11, 3.4, -0.2)))
    top, under = hip_roof(1.6, 1.6, 0.0, 0.9, 0.12, per=2, rows=2, expo=1.0)
    b.add(top, RD, M4((0, 4.45, -0.2)))
    b.add(under, WH, M4((0, 4.45, -0.2)))
    for sx in (-1, 1):  # 斜梯
        limb(b, (sx * 0.45, 0, 3.4), (sx * 0.45, 2.45, 1.7), 0.05, 0.05, WH, 5, False)
    for k in range(6):
        y = 0.35 + k * 0.38
        b.add(box(0.95, 0.05, 0.22), WH, M4((0, y, 3.4 - (y / 2.45) * 1.7)))
    b.add(box(2.8, 0.08, 0.08), RD, M4((0, 3.25, 1.8)))
    b.add(cylinder(0.04, 3.2, 6), WH, M4((1.3, 2.55, 1.6)))
    b.add(box(0.9, 0.55, 0.03, base=True), YL, M4((1.75, 5.1, 1.6)))
    return proc(b)


def lighthouse():
    """燈塔（地標）：紅白相間的塔身、迴廊、發光燈室、紅色圓頂。高約 22 m。"""
    WH = pmat('BeachWhite', '#f4f1ea', rough=0.7)
    RD = pmat('BeachRed', '#e0402e', rough=0.6)
    DK = pmat('BeachDarkMetal', '#2e3440', rough=0.5, metal=0.5)
    GL = pmat('BeachLighthouseGlow', '#fff2b0', rough=0.2, emit=4.0)
    ST = pmat('BeachStone', '#a99f90', rough=0.95)
    b = Builder('lighthouse')
    b.add(cylinder(4.2, 0.8, 16, smooth=False), ST)
    b.add(box(4.0, 3.0, 3.6, base=True), WH, M4((3.0, 0.8, 0)))
    top, under = hip_roof(2.4, 2.2, 0.2, 1.3, 0.12, per=2, rows=2, expo=1.0)
    b.add(top, RD, M4((3.0, 3.8, 0)))
    b.add(under, WH, M4((3.0, 3.8, 0)))
    H = 17.0
    n = 6
    for k in range(n):
        y0 = 0.8 + H * k / n
        r0 = 2.3 - 0.7 * k / n
        r1 = 2.3 - 0.7 * (k + 1) / n
        b.add(cylinder(r0, H / n, 16, r2=r1, smooth=True), RD if k % 2 else WH, M4((0, y0, 0)))
    yt = 0.8 + H
    b.add(cylinder(2.4, 0.3, 16), DK, M4((0, yt, 0)))
    b.add(torus(2.3, 0.05, 20, 4), DK, M4((0, yt + 1.0, 0), rot=(math.pi / 2, 0, 0)))
    for k in range(12):
        a = 2 * math.pi * k / 12
        b.add(box(0.06, 1.0, 0.06, base=True), DK, M4((2.3 * math.cos(a), yt + 0.3, 2.3 * math.sin(a))))
    b.add(cylinder(1.25, 0.5, 12), WH, M4((0, yt + 0.3, 0)))
    b.add(cylinder(1.05, 1.8, 12), GL, M4((0, yt + 0.8, 0)))
    for k in range(6):
        a = 2 * math.pi * k / 6
        b.add(box(0.1, 1.8, 0.1, base=True), DK, M4((1.08 * math.cos(a), yt + 0.8, 1.08 * math.sin(a))))
    b.add(cone(1.45, 1.3, 16), RD, M4((0, yt + 2.6, 0)))
    b.add(sphere(0.25, 8, 6), DK, M4((0, yt + 3.95, 0)))
    b.add(cylinder(0.04, 0.8, 4), DK, M4((0, yt + 4.1, 0)))
    for k in range(3):
        b.add(box(0.7, 1.0, 0.05, base=True), DK, M4((0, 3.0 + k * 5.0, 2.15 - k * 0.17)))
    return proc(b)


def lounger(rnd, col):
    WD = pmat('BeachWood', '#9a6b43', rough=0.85)
    C = pmat(f'BeachCloth_{col.lstrip("#")}', col, rough=0.9)
    WH = pmat('BeachWhite', '#f4f1ea', rough=0.7)
    b = Builder('lounger')
    for x in (-0.3, 0.3):
        for z in (-0.8, 0.5):
            b.add(box(0.06, 0.3, 0.06, base=True), WD, M4((x, 0, z)))
    b.add(box(0.7, 0.08, 1.4, base=True), WD, M4((0, 0.3, -0.1)))
    b.add(box(0.66, 0.07, 1.3, base=True), C, M4((0, 0.38, -0.1)))
    b.add(box(0.7, 0.08, 0.75, base=True), WD, M4((0, 0.32, 0.85), rot=(-0.85, 0, 0)))
    b.add(box(0.66, 0.07, 0.7, base=True), C, M4((0, 0.4, 0.8), rot=(-0.85, 0, 0)))
    for k in range(3):
        b.add(box(0.67, 0.075, 0.18, base=True), WH, M4((0, 0.381, -0.6 + k * 0.4)))
    return proc(b)


def log_cabin():
    """雪地小木屋：疊圓木的牆（轉角出頭）、暖光窗、門、積雪的切妻屋頂、石煙囪。寬 6 m 深 5 m。"""
    LG = pmat('SnowLog', '#8a5a36', rough=0.9)
    LG2 = pmat('SnowLogDark', '#6e4529', rough=0.9)
    RF = pmat('SnowRoofWood', '#5b3a26', rough=0.9)
    SN = pmat('SnowWhite', '#f4f8ff', rough=0.9)
    ST = pmat('SnowStone', '#8d8c92', rough=0.95)
    GL = pmat('SnowWindowGlow', '#ffc96b', rough=0.3, emit=2.2)
    DR = pmat('SnowDoor', '#4a2c1a', rough=0.85)
    b = Builder('cabin')
    w, d, wh = 6.0, 5.0, 2.7
    r = 0.17
    rows = int(wh / (2 * r))
    for k in range(rows):
        y = r + k * 2 * r
        m = LG if k % 2 else LG2
        for sz in (-1, 1):
            b.add(cylinder(r, w + 0.7, 7), m, M4((-(w + 0.7) / 2, y, sz * d / 2), rot=(0, 0, -math.pi / 2)))
        for sx in (-1, 1):
            b.add(cylinder(r, d + 0.7, 7), m, M4((sx * w / 2, y + r * 0.5, -(d + 0.7) / 2), rot=(math.pi / 2, 0, 0)))
    b.add(box(w - 0.2, wh, d - 0.2, base=True), LG2)
    fz = d / 2 + r
    b.add(box(1.05, 2.1, 0.06, base=True), DR, M4((-1.4, 0.02, fz)))
    b.add(box(1.3, 0.14, 0.14), RF, M4((-1.4, 2.15, fz + 0.03)))
    for x in (1.2,):
        b.add(box(1.1, 0.9, 0.05, base=True), GL, M4((x, 1.0, fz)))
        b.add(box(1.3, 0.12, 0.12), RF, M4((x, 0.95, fz + 0.04)))
        b.add(box(1.3, 0.12, 0.12), RF, M4((x, 1.95, fz + 0.04)))
        b.add(box(0.07, 0.9, 0.08, base=True), RF, M4((x, 1.0, fz + 0.04)))
        b.add(box(1.1, 0.07, 0.08), RF, M4((x, 1.45, fz + 0.04)))
    for sx in (-1, 1):
        b.add(box(0.05, 0.9, 1.0, base=True), GL, M4((sx * (w / 2 + r), 1.0, 0)))
    # 山牆（兩側）
    rh = 2.3
    for sx in (-1, 1):
        P = Poly()
        P.face([(sx * w / 2, wh, -d / 2 - r), (sx * w / 2, wh, d / 2 + r), (sx * w / 2, wh + rh, 0)], (sx, 0, 0))
        b.add(P.prim(), LG)
    top, under = gable_roof(w / 2 + 0.6, d / 2 + 0.8, d / 2 + 0.8, rh + 0.3, 0.18, cols=3, rows=4, expo=1.0)
    b.add(top, RF, M4((0, wh - 0.1, 0)))
    b.add(under, RF, M4((0, wh - 0.1, 0)))
    st, su = gable_roof(w / 2 + 0.55, d / 2 + 0.7, d / 2 + 0.7, rh + 0.25, 0.22, cols=3, rows=4, expo=1.0)
    b.add(st, SN, M4((0, wh + 0.12, 0)))
    b.add(su, SN, M4((0, wh + 0.12, 0)))
    b.add(box(0.9, 4.6, 0.9, base=True), ST, M4((-w / 2 + 1.2, 0.0, -1.0)))
    b.add(box(1.05, 0.25, 1.05, base=True), SN, M4((-w / 2 + 1.2, 4.6, -1.0)))
    b.add(box(1.4, 0.3, 0.5, base=True), SN, M4((1.2, 0.0, fz + 0.3)))
    return proc(b)


def ice_spikes(rnd):
    """冰晶叢：幾根六角冰柱，淡藍、微微發光。"""
    I1 = pmat('SnowIce', '#a8e2ff', rough=0.15, emit=0.35, emit_color='#6fcfff')
    I2 = pmat('SnowIceDeep', '#6fbde8', rough=0.15, emit=0.35, emit_color='#4fb8ff')
    b = Builder('ice')
    for i in range(8):
        a = rnd.uniform(0, 6.28)
        rr = 0.0 if i == 0 else rnd.uniform(0.8, 2.2)
        h = 7.5 if i == 0 else rnd.uniform(2.0, 5.5)
        r = 0.9 if i == 0 else rnd.uniform(0.35, 0.7)
        tilt = (rnd.uniform(-0.35, 0.35), 0, rnd.uniform(-0.35, 0.35)) if i else (0.05, 0, -0.04)
        mt = M4((math.cos(a) * rr, -0.3, math.sin(a) * rr), rot=tilt)
        m = I1 if i % 2 == 0 else I2
        b.add(prism(r, h, 6), m, mt)
        b.add(cone(r, r * 1.8, 6), m, mt @ M4((0, h, 0)))
    return proc(b)


def brazier(rnd):
    """火盆：三腳鐵架上的鐵盆，盆裡疊幾團發光的火焰（橘、黃）。高約 1.9 m。"""
    IR = pmat('VolcanoIron', '#3a3532', rough=0.6, metal=0.6)
    F1 = pmat('VolcanoFireGlow', '#ff7a1a', rough=0.5, emit=3.5)
    F2 = pmat('VolcanoFireCore', '#ffd04a', rough=0.5, emit=4.0)
    b = Builder('brazier')
    for i in range(3):
        a = 2 * math.pi * i / 3
        limb(b, (0.55 * math.cos(a), 0, 0.55 * math.sin(a)), (0.25 * math.cos(a), 1.05, 0.25 * math.sin(a)), 0.05, 0.045, IR, 6, False)
    b.add(torus(0.3, 0.04, 12, 4), IR, M4((0, 0.6, 0), rot=(math.pi / 2, 0, 0)))
    b.add(cylinder(0.25, 0.4, 10, r2=0.55, smooth=False), IR, M4((0, 1.0, 0)))
    b.add(torus(0.55, 0.05, 14, 4), IR, M4((0, 1.4, 0), rot=(math.pi / 2, 0, 0)))
    for k in range(5):
        a = rnd.uniform(0, 6.28)
        rr = 0.0 if k == 0 else rnd.uniform(0.15, 0.3)
        h = 0.7 if k == 0 else rnd.uniform(0.35, 0.55)
        b.add(cone(0.22 if k == 0 else 0.14, h, 6), F1 if k else F2, M4((math.cos(a) * rr, 1.32, math.sin(a) * rr), rot=(rnd.uniform(-0.2, 0.2), 0, rnd.uniform(-0.2, 0.2))))
    return proc(b)


def lava_rock(rnd, r=1.4, frac=0.22, name='lavarock'):
    RK = pmat('VolcanoRock', '#2e2624', rough=0.95)
    LV = pmat('VolcanoLavaGlow', '#ff5a1f', rough=0.6, emit=3.0, emit_color='#ff6a1a')
    b = Builder(name)
    a, c = blob_split(r, rnd, frac, 2, 0.2, (1.3, 0.75, 1.1))
    b.add(a, RK)
    b.add(c, LV)
    return proc(b)


def volcano(rnd):
    """火山（遠景地標）：圓錐山體、火口、火口裡的熔岩、往下流的三條熔岩流（發光）。底徑約 200 m、高 65 m。"""
    R1 = pmat('VolcanoRock', '#2e2624', rough=0.95)
    R2 = pmat('VolcanoRockLight', '#4a3c36', rough=0.95)
    LV = pmat('VolcanoLavaGlow', '#ff5a1f', rough=0.6, emit=3.0, emit_color='#ff6a1a')
    from mathutils import noise
    b = Builder('volcano')
    H, Rb, Rc = 65.0, 100.0, 15.0
    NA, NR = 48, 12
    streams = [rnd.uniform(0, 6.28) for _ in range(3)]

    def hgt(r):
        t = (r - Rc) / (Rb - Rc)
        return H * (1 - t) ** 1.6

    pts = []
    for i in range(NR + 1):
        r = Rc + (Rb - Rc) * (i / NR) ** 1.3
        row = []
        for j in range(NA):
            a = 2 * math.pi * j / NA
            n = noise.noise(Vector((math.cos(a) * 2.0, math.sin(a) * 2.0, i * 0.4)))
            rr = r * (1 + 0.08 * n)
            y = max(0.0, hgt(r) + 3.0 * n * (1 if 0 < i < NR else 0))
            if i == NR:
                y = 0.0
            row.append(Vector((math.cos(a) * rr, y, math.sin(a) * rr)))
        pts.append(row)
    rock, lava, rock2 = Poly(), Poly(), Poly()
    for i in range(NR):
        for j in range(NA):
            j2 = (j + 1) % NA
            q = [pts[i][j], pts[i][j2], pts[i + 1][j2], pts[i + 1][j]]
            a = 2 * math.pi * (j + 0.5) / NA
            r = (i + 0.5) / NR
            wig = [s + 0.25 * math.sin(r * 9 + s * 3) for s in streams]
            on = any(abs((a - s + math.pi) % (2 * math.pi) - math.pi) < 0.09 + 0.05 * (1 - r) for s in wig) and r < 0.8
            (lava if on else (rock2 if noise.noise(Vector((i * 0.7, j * 0.45, 3.0))) > 0.25 else rock)).face(q, (0, 1, 0))
    # 火口：內壁往下、底部熔岩湖
    inner = [Vector((p.x * 0.6, H - 9.0, p.z * 0.6)) for p in pts[0]]
    for j in range(NA):
        j2 = (j + 1) % NA
        rock.face([pts[0][j], pts[0][j2], inner[j2], inner[j]], (0, 1, 0))
    lava.face(inner, (0, 1, 0))
    b.add(rock.prim(), R1)
    b.add(rock2.prim(), R2)
    b.add(lava.prim(), LV)
    return proc(b)


def leaf_pile(rnd):
    C = [pmat('AutumnLeafOrange', '#e8822a', rough=0.95), pmat('AutumnLeafRed', '#c8402a', rough=0.95), pmat('AutumnLeafYellow', '#e9b53a', rough=0.95)]
    b = Builder('leaves')
    b.add(blob(1.1, rnd, 1, 0.2, (1.2, 0.35, 1.0)), C[0])
    for k in range(5):
        a = rnd.uniform(0, 6.28)
        b.add(blob(rnd.uniform(0.35, 0.55), rnd, 1, 0.25, (1.2, 0.4, 1.0)), C[k % 3], M4((math.cos(a) * 0.7, 0.2, math.sin(a) * 0.6)))
    return proc(b)


def tire(R=0.30, r=0.13):
    return torus(R, r, 10, 5)


def tire_stack(colors=('#e53935',), n=4, name='tires'):
    K = pmat('TrackTireBlack', '#1f1f22', rough=0.9)
    b = Builder(name)
    for k in range(n):
        m = K if k < n - 1 else pmat(f'TrackTire_{colors[0].lstrip("#")}', colors[0], rough=0.8)
        b.add(tire(), m, M4((0, 0.13 + k * 0.255, 0), rot=(math.pi / 2, 0, 0)))
    return proc(b)


def tire_wall(n=8, rows=3):
    K = pmat('TrackTireBlack', '#1f1f22', rough=0.9)
    RD = pmat('TrackTire_e53935', '#e53935', rough=0.8)
    WH = pmat('TrackTire_f5f5f5', '#f5f5f5', rough=0.8)
    b = Builder('tirewall')
    for i in range(n):
        for k in range(rows):
            m = (RD if i % 2 else WH) if k == rows - 1 else K
            b.add(tire(), m, M4(((i - (n - 1) / 2) * 0.62, 0.13 + k * 0.255, 0), rot=(math.pi / 2, 0, 0)))
    return proc(b)


def boost_arrow():
    """加速帶：深色底板上三個發光箭頭（朝 +Z）。3 m 寬、6 m 長、0.04 m 厚。"""
    BS = pmat('TrackBoostBase', '#1b2340', rough=0.4)
    AR = pmat('TrackBoostGlow', '#ffc21a', rough=0.3, emit=3.0)
    b = Builder('boost')
    b.add(box(3.0, 0.03, 6.0, base=True), BS)
    for k in range(3):
        z0 = -2.2 + k * 1.9
        for sx in (-1, 1):
            P = Poly()
            pts = [(0, 0.04, z0 + 1.1), (sx * 1.25, 0.04, z0 - 0.15), (sx * 1.25, 0.04, z0 - 0.75), (0, 0.04, z0 + 0.5)]
            P.face(pts, (0, 1, 0))
            b.add(P.prim(), AR)
    return proc(b)


# ================================================================ 各主題的清單

def theme_common():
    R = 'kenney/racing-kit/Models/GLTF format/'
    rnd = random.Random(1)
    add('arch_start_a', 'trackside', 'track', D(per_track=1), '起終點拱門（附起跑燈號），跨在路面上',
        imp(R + 'overheadLights.glb'), s=16)
    add('arch_a', 'trackside', 'track', D(per_track=2), '一般拱門（檢查點、贊助門）',
        imp(R + 'overhead.glb'), s=16)
    add('grandstand_a', 'trackside', 'roadside', D(per_track=3), '有頂看台（10 m 一節，可並排）',
        imp(R + 'grandStandCovered.glb'), s=10)
    add('grandstand_b', 'trackside', 'roadside', D(per_track=3), '無頂看台',
        imp(R + 'grandStand.glb'), s=10)
    add('pits_garage_a', 'building', 'roadside', D(per_track=4), '維修區車庫（10 m 一格，可並排）',
        imp(R + 'pitsGarage.glb'), s=10)
    add('tent_a', 'trackside', 'roadside', D(per_100m=0.3), '活動帳篷',
        imp(R + 'tent.glb'), h=3.6)
    add('billboard_a', 'trackside', 'roadside', D(per_100m=0.4), '廣告看板',
        imp(R + 'billboard.glb'), h=8)
    add('banner_tower_a', 'trackside', 'roadside', D(per_100m=0.3), '紅色旗塔',
        imp(R + 'bannerTowerRed.glb'), h=9)
    add('flag_checker_a', 'deco', 'roadside', D(per_track=6), '方格旗（起終點兩側）',
        imp(R + 'flagCheckers.glb'), h=5)
    add('flag_red_a', 'deco', 'roadside', D(per_100m=1), '紅旗',
        imp(R + 'flagRed.glb'), h=5)
    add('light_post_a', 'trackside', 'roadside', D(per_100m=1), '賽道燈柱（燈頭發光）',
        emit_where(imp(R + 'lightPostModern.glb'), lamp_down, pmat('TrackLampGlow', '#fff4d6', rough=0.3, emit=3.0)), h=9)
    add('barrier_red_a', 'trackside', 'roadside', D(per_100m=20), '紅色護欄塊（1.75 m，排成一列）',
        imp(R + 'barrierRed.glb'), s=7)
    add('barrier_white_a', 'trackside', 'roadside', D(per_100m=20), '白色護欄塊（跟紅色交錯排）',
        imp(R + 'barrierWhite.glb'), s=7)
    add('barrier_wall_a', 'trackside', 'roadside', D(per_100m=14), '紅白護牆（7 m 一段）',
        imp(R + 'barrierWall.glb'), s=7)
    add('rail_a', 'trackside', 'roadside', D(per_100m=25), '雙層鋼護欄（4.5 m 一段）',
        imp(R + 'railDouble.glb'), s=4.5)
    add('fence_a', 'trackside', 'roadside', D(per_100m=16), '鐵絲網圍籬（6 m 一段，網子是透明貼圖）',
        imp(R + 'fenceStraight.glb'), s=6)
    add('barrier_jersey_a', 'trackside', 'roadside', D(per_100m=10), '紐澤西水泥護欄（施工段）',
        imp('kenney/city-kit-roads/Models/GLB format/construction-barrier.glb'), h=1.0, yaw=math.pi / 2)
    add('cone_a', 'deco', 'roadside', D(per_100m=4), '三角錐（Kenney）',
        imp(R + 'pylon.glb'), h=0.75)
    add('cone_b', 'deco', 'roadside', D(per_100m=4), '三角錐（Quaternius，反光條）',
        imp('quaternius/polypizza/track/Traffic_Cone__aDIrUbMbW3.glb'), h=0.75)
    add('tires_a', 'deco', 'roadside', D(per_100m=1), '散落的輪胎堆',
        imp('quaternius/polypizza/track/Tires__mmq7GmG1AK.glb'), h=1.1)
    add('tire_stack_a', 'trackside', 'roadside', D(per_100m=6), '四個疊起來的輪胎（頂上紅）', tire_stack(('#e53935',)))
    add('tire_stack_b', 'trackside', 'roadside', D(per_100m=6), '四個疊起來的輪胎（頂上白）', tire_stack(('#f5f5f5',), name='tires2'))
    add('tire_wall_a', 'trackside', 'roadside', D(per_100m=12), '輪胎牆（5 m 一段，紅白交錯，彎道外側）', tire_wall())
    add('boost_arrow_a', 'trackside', 'track', D(per_track=4), '加速帶（發光箭頭朝 +Z，貼在路面上）', boost_arrow())
    add('arrow_sign_a', 'trackside', 'roadside', D(per_100m=1), '立式轉彎箭頭牌（彎道外側）',
        imp('kenney/watercraft-kit/Models/GLB format/arrow-standing.glb'), h=2.2, yaw=math.pi / 2)


def theme_beach():
    QN = 'quaternius/ultimate-nature/FBX/'
    KP = 'kenney/pirate-kit/Models/GLB format/'
    QP = 'quaternius/pirate-kit/glTF/'
    rnd = random.Random(2)
    qn = dict(sat=1.3, val=1.08)
    add('palm_a', 'tree', 'roadside', D(per_ha=25), '高椰子樹（細長、微彎）', imp(QN + 'PalmTree_1.fbx', **qn), h=10)
    add('palm_b', 'tree', 'roadside', D(per_ha=25), '高椰子樹（另一個姿勢）', imp(QN + 'PalmTree_3.fbx', **qn), h=11)
    add('palm_c', 'tree', 'roadside', D(per_ha=15), '矮椰子樹', imp(QN + 'PalmTree_2.fbx', **qn), h=7)
    add('palm_d', 'tree', 'roadside', D(per_ha=20), '卡通彎椰子樹（Kenney）', imp(KP + 'palm-detailed-bend.glb'), h=8)
    add('palm_e', 'tree', 'roadside', D(per_ha=20), '卡通直椰子樹（Kenney）', imp(KP + 'palm-detailed-straight.glb'), h=9)
    add('plant_a', 'deco', 'roadside', D(per_ha=60), '熱帶灌木', imp(QN + 'Plant_1.fbx', **qn), h=1.3)
    add('plant_b', 'deco', 'roadside', D(per_ha=60), '大葉植物', imp(QN + 'Plant_3.fbx', **qn), h=1.6)
    add('rock_a', 'rock', 'roadside', D(per_ha=12), '沙灘岩（半埋在沙裡）', imp(KP + 'rocks-sand-a.glb'), h=2.6)
    add('rock_b', 'rock', 'roadside', D(per_ha=12), '沙灘岩（小）', imp(KP + 'rocks-sand-c.glb'), h=1.8)
    add('rock_c', 'rock', 'roadside', D(per_ha=8), '灰岩堆', imp(KP + 'rocks-b.glb'), h=3.5)
    add('rock_large_a', 'rock', 'far', D(per_ha=3), '大圓石', imp(QP + 'Environment_Rock_2.gltf'), h=5)
    add('cliff_a', 'landmark', 'far', D(per_track=4), '海崖岩塊（海岸線、遠景）', imp(QP + 'Environment_Cliff1.gltf'), h=12)
    add('dock_a', 'building', 'roadside', D(per_track=2), '木碼頭一段（含木樁，可接成長碼頭）', imp(QP + 'Environment_Dock.gltf'), s=1.4)
    add('bungalow_a', 'building', 'roadside', D(per_track=6), '高腳茅草屋（度假小屋）', bungalow())
    add('lifeguard_a', 'building', 'roadside', D(per_track=3), '救生員瞭望台', lifeguard_tower())
    add('lighthouse_a', 'landmark', 'landmark', D(per_track=1), '紅白燈塔（燈室發光）', lighthouse())
    add('parasol_a', 'deco', 'roadside', D(per_ha=30), '海灘遮陽傘', imp('kenney/city-kit-commercial/Models/GLB format/detail-parasol-a.glb'), h=2.6)
    add('parasol_b', 'deco', 'roadside', D(per_ha=30), '海灘遮陽傘（另一色）', imp('kenney/city-kit-commercial/Models/GLB format/detail-parasol-b.glb'), h=2.6)
    add('lounger_a', 'deco', 'roadside', D(per_ha=40), '海灘躺椅（藍）', lounger(rnd, '#2f8fd8'))
    add('lounger_b', 'deco', 'roadside', D(per_ha=40), '海灘躺椅（橘）', lounger(rnd, '#ff8a3d'))
    add('boat_a', 'deco', 'far', D(per_track=6), '小划船（擺在沙灘或水上）', imp('kenney/watercraft-kit/Models/GLB format/boat-row-small.glb'), s=1.3)
    add('buoy_a', 'deco', 'far', D(per_track=8), '浮標（水面）', imp('kenney/watercraft-kit/Models/GLB format/buoy-flag.glb'), h=2.0)
    add('tent_a', 'deco', 'roadside', D(per_track=4), '帆布遮陽棚', imp('kenney/survival-kit/Models/GLB format/tent-canvas.glb'), h=2.6)
    add('barrel_a', 'deco', 'roadside', D(per_100m=0.5), '木桶', imp(QP + 'Prop_Barrel.gltf'), h=1.0)


def sakura_pink_leaves(a):
    """USN 楓葉貼圖改成櫻花粉：依亮度對應到深粉～淺粉。"""
    lum = a[:, 0] * 0.3 + a[:, 1] * 0.59 + a[:, 2] * 0.11
    t = np.clip((lum - lum[a[:, 3] > 0.5].min()) / max(1e-3, np.ptp(lum[a[:, 3] > 0.5])), 0, 1) if (a[:, 3] > 0.5).any() else lum
    dark = np.array([0.93, 0.55, 0.70])
    light = np.array([1.0, 0.90, 0.95])
    a[:, :3] = dark * (1 - t[:, None]) + light * t[:, None]
    return a


def theme_sakura():
    rnd = random.Random(3)
    pinks = [('JpSakuraDeep', '#e9809f'), ('JpSakura', '#f4a0bf'), ('JpSakuraLight', '#f8bcd2'), ('JpSakuraPale', '#fbd3e2')]
    bark = ('JpSakuraBark', '#5a3d33')
    add('sakura_a', 'tree', 'roadside', D(per_ha=40), '櫻花樹（寬樹冠）',
        momiji_like(rnd, 'sakura_a', 7.5, 3.8, pinks, bark, n_limbs=5, n_blob=26, blob_r=(0.9, 1.4)), h=8.5)
    add('sakura_b', 'tree', 'roadside', D(per_ha=30), '櫻花樹（高）',
        momiji_like(rnd, 'sakura_b', 9.5, 3.1, pinks, bark, n_limbs=4, n_blob=24, blob_r=(0.9, 1.35), limb_up=(0.7, 1.1)), h=10.5)
    add('sakura_c', 'tree', 'roadside', D(per_ha=40), '櫻花樹（小、斜）',
        momiji_like(rnd, 'sakura_c', 5.5, 2.7, pinks, bark, n_limbs=4, n_blob=18, blob_r=(0.75, 1.15), lean=0.5, trunk_r=0.24), h=6.5)
    add('sakura_d', 'tree', 'roadside', D(per_ha=25), '櫻花樹（葉片貼圖版，USN 楓樹改粉紅；近景用）',
        imp('quaternius/ultimate-stylized-nature/glTF/MapleTree_2.gltf', img_fn={'MapleTree_Leaves': sakura_pink_leaves}, img_key='sakura', tag='Sakura'), h=8)
    add('maple_a', 'tree', 'roadside', D(per_ha=15), '紅葉（楓）樹，跟櫻花混著撒',
        momiji_like(rnd, 'maple_a', 6.5, 3.0, [('JpMapleDeep', '#a8261d'), ('JpMaple', '#d8402a'), ('JpMapleOrange', '#ee7a2c')],
                    ('JpMapleBark', '#4a3328'), n_limbs=4, n_blob=20, blob_r=(0.8, 1.25), flat=0.7), h=7)
    add('pine_jp_a', 'tree', 'roadside', D(per_ha=10), '日本黑松（庭園修剪、扁平針葉團）', matsu(rnd), h=8)
    add('bamboo_a', 'tree', 'roadside', D(per_ha=30), '竹林一叢（十二根，撒密一點就是竹林）', bamboo(rnd), h=11)
    add('bamboo_b', 'tree', 'roadside', D(per_ha=40), '小竹叢（六根）', bamboo(rnd, n=6, H=(5.5, 7.5), spread=0.8, name='bamboo_b'), h=7.5)
    add('torii_a', 'landmark', 'roadside', D(per_track=4), '鳥居（7 m，參道入口）', torii(7.0, 4.6))
    add('torii_large_a', 'landmark', 'track', D(per_track=2), '大鳥居（跨賽道用，柱距 20 m、高 13 m）', torii(13.0, 20.0, 'torii_l'))
    add('torii_small_a', 'deco', 'roadside', D(per_100m=8), '小鳥居（千本鳥居，沿路排成隧道）', torii(3.4, 2.2, 'torii_s'))
    add('lantern_stone_a', 'deco', 'roadside', D(per_100m=4), '石燈籠（春日型，火袋發光）', stone_lantern_kasuga())
    add('lantern_stone_b', 'deco', 'roadside', D(per_100m=2), '雪見燈籠（三腳、低矮）', stone_lantern_yukimi())
    add('lantern_paper_a', 'deco', 'roadside', D(per_100m=3), '掛紅提燈的木柱（發光）', paper_lantern_post())
    add('house_a', 'building', 'roadside', D(per_100m=1), '二層町家（格子門面、暖簾）', machiya())
    add('house_b', 'building', 'roadside', D(per_100m=0.6), '和風平房（緣側、障子、四坡瓦頂）', hiraya())
    add('shrine_a', 'landmark', 'landmark', D(per_track=1), '神社拜殿（銅綠屋頂、千木鰹木、注連縄）', shrine())
    add('pagoda_a', 'landmark', 'landmark', D(per_track=1), '五重塔（遠景地標）', pagoda())
    add('bridge_a', 'landmark', 'roadside', D(per_track=1), '朱紅太鼓橋（12 m，裝飾用，車不能走）', taiko_bridge())
    add('rock_a', 'rock', 'roadside', D(per_ha=10), '青苔石', imp('quaternius/ultimate-nature/FBX/Rock_Moss_3.fbx', sat=1.2), h=1.3)
    add('rock_b', 'rock', 'roadside', D(per_ha=8), '庭石（立石）',
        imp('kenney/nature-kit/Models/GLTF format/stone_tallB.glb', recolor={'stone': ('JpGardenStone', '#a59f94'), 'stoneDark': ('JpGardenStoneDark', '#878177'), '_defaultMat': ('JpGardenStoneDark', '#878177')}), h=1.8)
    add('path_a', 'deco', 'roadside', D(per_100m=2), '踏石（一組圓形飛石）',
        imp('kenney/nature-kit/Models/GLTF format/path_stoneCircle.glb', recolor={'stone': ('JpGardenStone', '#a59f94'), 'stoneDark': ('JpGardenStoneDark', '#878177'), '_defaultMat': ('JpGardenStoneDark', '#878177')}), s=4)


def theme_snow():
    QN = 'quaternius/ultimate-nature/FBX/'
    KH = 'kenney/holiday-kit/Models/GLB format/'
    rnd = random.Random(4)
    qn = dict(sat=1.25, val=1.12)
    add('pine_snow_a', 'tree', 'roadside', D(per_ha=50), '積雪雪松', imp(QN + 'PineTree_Snow_1.fbx', **qn), h=10)
    add('pine_snow_b', 'tree', 'roadside', D(per_ha=50), '積雪雪松（細高）', imp(QN + 'PineTree_Snow_4.fbx', **qn), h=12)
    add('pine_snow_c', 'tree', 'roadside', D(per_ha=40), '卡通積雪松（Kenney）', imp(KH + 'tree-snow-a.glb'), h=7)
    add('pine_snow_d', 'tree', 'roadside', D(per_ha=40), '卡通積雪松（Kenney，另一款）', imp(KH + 'tree-snow-b.glb'), h=8)
    add('pine_snow_e', 'tree', 'roadside', D(per_ha=30), '圓胖積雪松', imp('kenney/platformer-kit/Models/GLB format/tree-pine-snow.glb'), h=6)
    add('tree_snow_a', 'tree', 'roadside', D(per_ha=15), '積雪闊葉樹', imp(QN + 'CommonTree_Snow_2.fbx', **qn), h=8)
    add('birch_dead_snow_a', 'tree', 'roadside', D(per_ha=10), '積雪枯白樺', imp(QN + 'BirchTree_Dead_Snow_1.fbx', **qn), h=8)
    add('tree_dead_snow_a', 'tree', 'roadside', D(per_ha=8), '積雪枯樹', imp('quaternius/polypizza/snow/Dead_Tree_with_Snow__PILl2nbDNz.glb'), h=6)
    add('bush_snow_a', 'deco', 'roadside', D(per_ha=50), '積雪灌木', imp(QN + 'Bush_Snow_1.fbx', **qn), h=1.2)
    add('rock_snow_a', 'rock', 'roadside', D(per_ha=15), '雪地岩石', imp(QN + 'Rock_Snow_2.fbx', **qn), h=1.6)
    add('rock_snow_b', 'rock', 'roadside', D(per_ha=10), '雪地岩石（大）', imp(QN + 'Rock_Snow_5.fbx', **qn), h=2.6)
    add('rock_snow_c', 'rock', 'roadside', D(per_ha=10), '積雪岩堆（Kenney）', imp(KH + 'rocks-large.glb'), h=2.2)
    add('log_snow_a', 'deco', 'roadside', D(per_ha=8), '積雪倒木', imp(QN + 'WoodLog_Snow.fbx', **qn), h=0.8)
    add('stump_snow_a', 'deco', 'roadside', D(per_ha=8), '積雪樹樁', imp(QN + 'TreeStump_Snow.fbx', **qn), h=0.9)
    add('snow_pile_a', 'deco', 'roadside', D(per_100m=2), '雪堆', imp(KH + 'snow-pile.glb'), h=1.0)
    add('snowman_a', 'deco', 'roadside', D(per_track=6), '雪人', imp(KH + 'snowman.glb'), h=1.8)
    add('snowman_b', 'deco', 'roadside', D(per_track=4), '戴帽雪人', imp(KH + 'snowman-hat.glb'), h=2.0)
    add('sled_a', 'deco', 'roadside', D(per_track=4), '雪橇', imp(KH + 'sled.glb'), h=0.7)
    add('lantern_a', 'deco', 'roadside', D(per_100m=1), '木屋旁的路燈（燈罩發光）',
        emit_where(imp(KH + 'lantern.glb'), lambda c, p, hf: c[0] > 0.75 and c[1] > 0.6 and c[2] < 0.6,
                   pmat('SnowLampGlow', '#ffd58a', rough=0.3, emit=2.5)), h=3.0)
    add('ice_block_a', 'deco', 'roadside', D(per_ha=6), '冰塊', imp('quaternius/polypizza/snow/Ice_Block__dEY0gPZNzG.glb'), h=1.5)
    add('ice_spikes_a', 'landmark', 'roadside', D(per_track=6), '冰晶叢（淡藍微光）', ice_spikes(rnd))
    add('cabin_a', 'building', 'roadside', D(per_track=6), '雪地小木屋（窗戶暖光、屋頂積雪、煙囪）', log_cabin())


def theme_city():
    KC = 'kenney/city-kit-commercial/Models/GLB format/'
    KR = 'kenney/city-kit-roads/Models/GLB format/'
    CY = 'quaternius/cyberpunk-game-kit/Platforms/'
    rnd = random.Random(5)
    for nm, f, desc in (('skyscraper_a', 'building-skyscraper-a', '摩天樓（窗戶發光）'),
                        ('skyscraper_b', 'building-skyscraper-b', '摩天樓'),
                        ('skyscraper_c', 'building-skyscraper-c', '摩天樓（細高）'),
                        ('skyscraper_d', 'building-skyscraper-e', '摩天樓（直條窗）')):
        ob = imp(KC + f + '.glb')
        light_windows(ob, rnd)
        add(nm, 'building', 'far', D(per_ha=4), desc, ob, s=11)
    for nm, f, desc in (('building_a', 'building-a', '商業樓'), ('building_b', 'building-c', '商業樓（轉角）'),
                        ('building_c', 'building-f', '商業樓'), ('building_d', 'building-h', '商業樓（大窗）'),
                        ('building_e', 'building-k', '商業樓')):
        ob = imp(KC + f + '.glb')
        light_windows(ob, rnd)
        add(nm, 'building', 'roadside', D(per_100m=2), desc + '，窗戶發光', ob, s=11)
    for nm, f in (('bg_a', 'low-detail-building-a'), ('bg_b', 'low-detail-building-e'), ('bg_c', 'low-detail-building-wide-a'),
                  ('bg_d', 'low-detail-building-h')):
        ob = imp(KC + f + '.glb')
        light_windows(ob, rnd)
        add(nm, 'building', 'far', D(per_ha=8), '遠景低模大樓（188 面上下）', ob, s=11)
    add('light_street_a', 'deco', 'roadside', D(per_100m=3), '彎臂路燈（燈頭發光）',
        emit_where(imp(KR + 'light-curved.glb'), lamp_down, pmat('CityLampGlow', '#fff2c8', rough=0.3, emit=3.0)), s=11)
    add('light_street_b', 'deco', 'roadside', D(per_100m=3), '細路燈（Quaternius，燈發光）',
        imp(CY + 'Light_Street_1.gltf', recolor={'Light': pmat('CityLampGlow', '#fff2c8', rough=0.3, emit=3.0)}), h=6.5)
    add('traffic_light_a', 'deco', 'roadside', D(per_100m=0.5), '紅綠燈（燈號不發光：素材的燈號跟外殼同一色塊分不開）',
        imp(KR + 'traffic-light.glb'), s=11)
    add('sign_highway_a', 'trackside', 'track', D(per_track=2), '高速公路門架標誌', imp(KR + 'sign-highway.glb'), s=11, yaw=math.pi / 2)
    sg = dict(emit_tex={'Texture_Signs': 2.5})
    add('sign_a', 'deco', 'roadside', D(per_100m=2), '霓虹招牌（橫，日文；掛在建築上）', imp(CY + 'Sign_1.gltf', **sg), s=3.5)
    add('sign_b', 'deco', 'roadside', D(per_100m=2), '霓虹招牌（橫）', imp(CY + 'Sign_2.gltf', **sg), s=3.5)
    add('sign_c', 'deco', 'roadside', D(per_100m=2), '霓虹招牌（「リンゴ」）', imp(CY + 'Sign_3.gltf', **sg), s=3.5)
    add('sign_d', 'deco', 'roadside', D(per_100m=2), '霓虹招牌（直）', imp(CY + 'Sign_4.gltf', **sg), s=3.5)
    add('sign_corner_a', 'deco', 'roadside', D(per_100m=1), '轉角霓虹招牌', imp(CY + 'Sign_Corner_2.gltf', **sg), s=3.5)
    add('sign_corner_b', 'deco', 'roadside', D(per_100m=1), '轉角霓虹招牌（另一款）', imp(CY + 'Sign_Corner_3.gltf', **sg), s=3.5)
    add('sign_small_a', 'deco', 'roadside', D(per_100m=3), '小霓虹招牌', imp(CY + 'Sign_Small_1.gltf', **sg), s=3.5)
    add('sign_small_b', 'deco', 'roadside', D(per_100m=3), '小霓虹招牌（另一款）', imp(CY + 'Sign_Small_2.gltf', **sg), s=3.5)
    add('tv_a', 'deco', 'roadside', D(per_100m=0.5), '屋頂電視牆（螢幕發光）', imp(CY + 'TV_2.gltf', **sg), s=3.5)
    add('ac_a', 'deco', 'roadside', D(per_100m=1), '屋頂冷氣機（疊）', imp(CY + 'AC_Stacked.gltf'), s=2.0)
    add('antenna_a', 'deco', 'roadside', D(per_100m=1), '屋頂天線', imp(CY + 'Antenna_1.gltf'), s=2.5)
    add('barrier_a', 'trackside', 'roadside', D(per_100m=10), '施工柵欄', imp(KR + 'construction-fence.glb'), h=1.2, yaw=math.pi / 2)
    add('cone_city_a', 'deco', 'roadside', D(per_100m=4), '施工錐', imp(KR + 'construction-cone.glb'), h=0.75)


def theme_volcano():
    QN = 'quaternius/ultimate-nature/FBX/'
    KN = 'kenney/nature-kit/Models/GLTF format/'
    PV = 'quaternius/polypizza/volcano/'
    rnd = random.Random(6)
    burnt = dict(recolor={'Wood': ('VolcanoCharWood', '#3a2c26')})
    dark_rock = dict(recolor={'Rock': ('VolcanoRockMid', '#4a3e3a')})
    dark_tex = dict(img_fn=lambda a: a * np.array([0.42, 0.36, 0.34, 1.0]), img_key='dark', tag='Dark')  # Kenney 貼圖岩石壓成深褐
    kn_dark = dict(recolor={'stone': ('VolcanoRockMid', '#4a3e3a'), 'stoneDark': ('VolcanoRock', '#2e2624'),
                            'rock': ('VolcanoRockMid', '#4a3e3a'), 'rockDark': ('VolcanoRock', '#2e2624'), 'dirt': ('VolcanoRockMid', '#4a3e3a'), 'grass': ('VolcanoAsh', '#5c4d45'), '_defaultMat': ('VolcanoRock', '#2e2624')})
    add('tree_lava_a', 'tree', 'roadside', D(per_ha=15), '熔岩植物（奇幻造型）', imp(PV + 'Tree_Lava__9gRfmVKx9W.glb'), h=6)
    add('tree_lava_b', 'tree', 'roadside', D(per_ha=15), '熔岩植物（另一款）', imp(PV + 'Tree_Lava__sTYjmQObr1.glb'), h=5.5)
    add('tree_lava_c', 'tree', 'roadside', D(per_ha=15), '熔岩植物（另一款）', imp(PV + 'Tree_Lava__wkLmuxEbMW.glb'), h=5)
    add('tree_dead_a', 'tree', 'roadside', D(per_ha=20), '焦黑枯樹', imp(QN + 'CommonTree_Dead_2.fbx', **burnt), h=8)
    add('tree_dead_b', 'tree', 'roadside', D(per_ha=15), '焦黑枯樹（細）', imp(QN + 'BirchTree_Dead_1.fbx', **burnt), h=7.5)
    add('tree_dead_c', 'tree', 'roadside', D(per_ha=15), '焦黑枯樹幹（矮）', imp(QN + 'Willow_Dead_3.fbx', **burnt), h=4.5)
    add('pine_crooked_a', 'tree', 'roadside', D(per_ha=10), '扭曲松', imp('kenney/graveyard-kit/Models/GLB format/pine-crooked.glb'), h=7)
    add('rock_a', 'rock', 'roadside', D(per_ha=20), '深色岩石', imp(QN + 'Rock_3.fbx', **dark_rock), h=1.5)
    add('rock_b', 'rock', 'roadside', D(per_ha=15), '深色岩石（大）', imp(QN + 'Rock_6.fbx', **dark_rock), h=2.6)
    add('rock_c', 'rock', 'roadside', D(per_ha=10), '岩石（貼圖，壓暗）',
        imp('quaternius/stylized-nature-megakit/glTF/Rock_Medium_1.gltf', img_fn=lambda a: a * np.array([0.5, 0.42, 0.40, 1.0]), img_key='dark'), h=2.3)
    add('rock_tall_a', 'rock', 'roadside', D(per_ha=6), '高岩柱', imp(KN + 'rock_tallB.glb', **kn_dark), h=6)
    add('rock_pillar_a', 'rock', 'far', D(per_ha=3), '尖石柱（遠景）', imp(KN + 'rock_tallG.glb', **kn_dark), h=11)
    add('rocks_a', 'rock', 'roadside', D(per_ha=10), '岩堆', imp('kenney/graveyard-kit/Models/GLB format/rocks-tall.glb', **dark_tex), h=2.5)
    add('rocks_b', 'rock', 'roadside', D(per_ha=10), '岩堆（寬）', imp('kenney/castle-kit/Models/GLB format/rocks-large.glb', **dark_tex), h=3)
    add('cliff_a', 'rock', 'far', D(per_ha=2), '懸崖岩壁（一片，可並排成崖）', imp(KN + 'cliff_large_rock.glb', **kn_dark), h=12)
    add('lava_rock_a', 'rock', 'roadside', D(per_ha=12), '熔岩石（裂縫發光）', lava_rock(rnd))
    add('lava_rock_b', 'rock', 'roadside', D(per_ha=12), '熔岩石（小）', lava_rock(rnd, 0.8, 0.3, 'lavarock2'))
    add('brazier_a', 'deco', 'roadside', D(per_100m=2), '火盆（鐵盆＋三腳架，火焰發光，賽道邊照明）', brazier(rnd))
    lava_top = dict(recolor={'Snow': pmat('VolcanoLavaGlow', '#ff5a1f', rough=0.6, emit=3.0, emit_color='#ff6a1a'),
                             'Stone': ('VolcanoRockMid', '#4a3e3a'), 'Dirt': ('VolcanoRock', '#2e2624')})
    add('mountain_a', 'landmark', 'far', D(per_track=3), '火山（山頂熔岩發光，遠景）', imp(PV + 'Mountain__XY4ej3Zg3I.glb', **lava_top), h=45)
    add('mountain_b', 'landmark', 'far', D(per_track=3), '山群（遠景）', imp(PV + 'Mountain_Group__a52gSEEq8X.glb', **lava_top), h=35)
    add('volcano_a', 'landmark', 'far', D(per_track=1), '大火山（火口熔岩湖＋三條熔岩流，底徑 200 m）', volcano(rnd))


def theme_autumn():
    QN = 'quaternius/ultimate-nature/FBX/'
    KN = 'kenney/nature-kit/Models/GLTF format/'
    USN = 'quaternius/ultimate-stylized-nature/glTF/'
    rnd = random.Random(7)
    qn = dict(sat=1.2, val=1.08)
    add('tree_autumn_a', 'tree', 'roadside', D(per_ha=40), '秋色闊葉樹（橘）', imp(QN + 'CommonTree_Autumn_1.fbx', **qn), h=9)
    add('tree_autumn_b', 'tree', 'roadside', D(per_ha=40), '秋色闊葉樹', imp(QN + 'CommonTree_Autumn_4.fbx', **qn), h=8)
    add('tree_autumn_c', 'tree', 'roadside', D(per_ha=30), '秋色闊葉樹（高）', imp(QN + 'CommonTree_Autumn_3.fbx', **qn), h=10)
    add('birch_autumn_a', 'tree', 'roadside', D(per_ha=25), '秋色白樺', imp(QN + 'BirchTree_Autumn_2.fbx', **qn), h=10)
    add('pine_autumn_a', 'tree', 'roadside', D(per_ha=25), '秋色松', imp(QN + 'PineTree_Autumn_3.fbx', **qn), h=11)
    add('willow_autumn_a', 'tree', 'roadside', D(per_ha=10), '秋色柳（水邊）', imp(QN + 'Willow_Autumn_2.fbx', **qn), h=8)
    add('maple_a', 'tree', 'roadside', D(per_ha=20), '紅楓（葉片貼圖）', imp(USN + 'MapleTree_1.gltf'), h=8)
    add('maple_b', 'tree', 'roadside', D(per_ha=20), '紅楓（小）', imp(USN + 'MapleTree_4.gltf'), h=6)
    add('oak_fall_a', 'tree', 'roadside', D(per_ha=30), '卡通秋色橡樹（Kenney）', imp(KN + 'tree_oak_fall.glb', recolor={'woodBirch': ('AutumnTrunk', '#6b4a35')}), h=7)
    add('tree_fall_b', 'tree', 'roadside', D(per_ha=30), '卡通秋色樹（Kenney）', imp(KN + 'tree_detailed_fall.glb'), h=8)
    add('tree_fall_c', 'tree', 'far', D(per_ha=40), '卡通秋色胖樹（50 面，遠景大量撒）', imp(KN + 'tree_fat_fall.glb', recolor={'woodBirch': ('AutumnTrunk', '#6b4a35')}), h=6)
    add('tree_fall_d', 'tree', 'far', D(per_ha=40), '卡通秋色尖樹（遠景）', imp(KN + 'tree_cone_fall.glb'), h=9)
    add('pine_fall_a', 'tree', 'roadside', D(per_ha=25), '秋色松（Kenney survival）', imp('kenney/survival-kit/Models/GLB format/tree-autumn-tall.glb'), h=9)
    add('rock_moss_a', 'rock', 'roadside', D(per_ha=12), '青苔岩', imp(QN + 'Rock_Moss_3.fbx', **qn), h=1.4)
    add('rock_moss_b', 'rock', 'roadside', D(per_ha=8), '青苔岩（大）', imp(QN + 'Rock_Moss_6.fbx', **qn), h=2.4)
    add('stone_a', 'rock', 'roadside', D(per_ha=12), '溪石', imp(KN + 'stone_largeB.glb', recolor={'stone': ('AutumnStone', '#9c978d'), '_defaultMat': ('AutumnStoneDark', '#7f7a72')}), h=1.2)
    add('log_moss_a', 'deco', 'roadside', D(per_ha=8), '青苔倒木', imp(QN + 'WoodLog_Moss.fbx', **qn), h=0.8)
    add('stump_moss_a', 'deco', 'roadside', D(per_ha=8), '青苔樹樁', imp(QN + 'TreeStump_Moss.fbx', **qn), h=0.9)
    add('mushroom_a', 'deco', 'roadside', D(per_ha=20), '紅菇一叢', imp(KN + 'mushroom_redGroup.glb'), h=0.5)
    add('pumpkin_a', 'deco', 'roadside', D(per_100m=0.5), '南瓜（收成擺飾）', imp('kenney/graveyard-kit/Models/GLB format/pumpkin.glb'), h=0.6)
    add('leaf_pile_a', 'deco', 'roadside', D(per_100m=3), '落葉堆', leaf_pile(rnd))
    add('bridge_a', 'landmark', 'roadside', D(per_track=1), '木橋（6 m，裝飾）', imp(KN + 'bridge_wood.glb', recolor={'stone': ('AutumnStone', '#9c978d')}), s=6)


BUILDERS = dict(common=theme_common, beach=theme_beach, sakura=theme_sakura, snow=theme_snow,
                city=theme_city, volcano=theme_volcano, autumn=theme_autumn)

# ================================================================ 輸出

LEGEND = {
    'size': '[寬(x), 深(z), 高(y)]，公尺；原點在底部中心，正面朝 +Z',
    'category': 'tree 樹／rock 岩石／building 建築／landmark 地標／deco 點綴／trackside 賽道設施',
    'use': 'far 遠景撒／roadside 路邊（護牆外）／landmark 地標（一條賽道放一兩個）／track 跨在或貼在路面上',
    'density': 'per_ha＝撒的區域裡每公頃幾個；per_100m＝沿賽道每 100 公尺幾個（兩側合計）；per_track＝一條賽道放幾個',
    'emissive': '發光材質（three.js 端用 bloom 發光；名稱以 P_ 開頭）',
}


def export(theme):
    os.makedirs(OUT, exist_ok=True)
    obs = [it['obj'] for it in ITEMS]
    for o in bpy.data.objects:
        o.select_set(o in obs)
    path = os.path.join(OUT, theme + '.glb')
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', use_selection=True, export_yup=True, export_apply=True,
        export_texcoords=True, export_normals=True, export_materials='EXPORT', export_image_format='AUTO',
        export_cameras=False, export_lights=False, export_animations=False, export_vertex_color='MATERIAL',
        export_extras=False)
    meta = dict(theme=theme, glb=theme + '.glb', generator='tools/blender/build_props.py',
                generated=time.strftime('%Y-%m-%d'), legend=LEGEND,
                objects=[{k: v for k, v in it.items() if k != 'obj' and v is not None} for it in ITEMS])
    with open(os.path.join(OUT, theme + '.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f'[props] {theme}: {len(ITEMS)} 件 -> {path} ({os.path.getsize(path) / 1e6:.2f} MB)')


def write_license():
    rows = []
    for th in ALL_THEMES:
        p = os.path.join(OUT, th + '.json')
        if not os.path.exists(p):
            continue
        for o in json.load(open(p, encoding='utf-8'))['objects']:
            for s in o['source']:
                rows.append((th, o['name'], s))
    L = ['# 場景物件的來源與授權', '',
         '`tools/blender/build_props.py` 產生；每次重跑會依各主題 json 重寫這份。',
         '素材原檔放在 repo 外的 `KCar_assets_src\\`（路徑相對於那個目錄）。',
         '', 'Kenney、Quaternius 的素材都是 **CC0 1.0**（公眾領域），可商用、免標示；這份清單是為了追溯來源。',
         '標「自製」的是 build_props.py 用程式畫的，沒有第三方素材。', '']
    for th in ALL_THEMES:
        rs = [r for r in rows if r[0] == th]
        if not rs:
            continue
        L += [f'## {th}（`{th}.glb`）', '', '| 物件 | 素材包 | 原檔 | 授權 | 來源網址 |', '|---|---|---|---|---|']
        for _, name, s in rs:
            L.append(f"| `{name}` | {s['pack']} | {('`' + s['file'] + '`') if s['file'] else '—'} | {s['license']} | {s['url'] or '—'} |")
        L.append('')
    with open(os.path.join(OUT, 'LICENSE.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))


# ---------------------------------------------------------------- 陳列圖

def render(theme, night=False, suffix='', small=False):
    """陳列圖。small=False：全部物件、真實比例；small=True：只排 5 m 以下的小東西（放大看細節）。"""
    sc = bpy.context.scene
    items = sorted(ITEMS, key=lambda it: (it['size'][2], it['size'][0]))
    if small:
        items = [it for it in items if it['size'][2] < 5.0 and max(it['size'][0], it['size'][1]) < 8.0]
    if not items:
        return
    for it in ITEMS:
        it['obj'].hide_render = it not in items
    # 參考物：卡丁車（1.6 m）與人（1.75 m）
    ref = Builder('ref_kart')
    ref.add(box(1.1, 0.55, 1.6, base=True), pmat('RefKart', '#ff2d55'), M4((0, 0.1, 0)))
    for sx in (-1, 1):
        for sz in (-1, 1):
            ref.add(cylinder(0.16, 0.2, 10), pmat('RefTire', '#222222'), M4((sx * 0.6, 0.16, sz * 0.55), rot=(0, 0, math.pi / 2)))
    ref.add(cylinder(0.22, 1.5, 10), pmat('RefMan', '#3a7bd5'), M4((1.4, 0, 0)))
    ref.add(sphere(0.14, 10, 8), pmat('RefMan', '#3a7bd5'), M4((1.4, 1.62, 0)))
    rob = ref.build()
    entries = [(rob, 'kart+man', (2.2, 1.6, 1.75))] + [(it['obj'], f"{it['name']} {it['size'][2]:.1f}m", it['size']) for it in items]
    n = len(entries)
    med = sorted(max(e[2][0], e[2][2]) for e in entries)[n // 2]
    tsize = min(2.5, max(0.18, med * 0.1))
    slot = lambda e: max(e[2][0], len(e[1]) * tsize * 0.62)  # noqa: E731
    nrows = max(1, round(math.sqrt(n / 2.6)))
    per = math.ceil(n / nrows)
    rows = [entries[i:i + per] for i in range(0, n, per)]
    el = math.radians(28)
    y_cursor = 0.0
    prev_h = 0.0
    labels = []
    maxw = 0.0
    placed = []
    for r in rows:
        depth = max(e[2][1] for e in r)
        hmax = max(e[2][2] for e in r)
        y_cursor += max(prev_h * 1.5, tsize * 4) + depth / 2
        x = 0.0
        xs = []
        for e in r:
            w = slot(e)
            xs.append(x + w / 2)
            x += w + tsize * 1.5 + 0.15 * e[2][0]
        width = x
        maxw = max(maxw, width)
        placed.append((r, xs, width, y_cursor, depth))
        y_cursor += depth / 2
        prev_h = hmax
    total_d = y_cursor
    for r, xs, width, yc, depth in placed:
        for (ob, lbl, sz), x in zip(r, xs):
            ob.location = (x - width / 2, yc, 0)
            cu = bpy.data.curves.new('lbl', 'FONT')
            cu.body = lbl
            cu.size = tsize
            cu.align_x = 'CENTER'
            t = bpy.data.objects.new('lbl', cu)
            link(t)
            t.location = (x - width / 2, yc - depth / 2 - tsize * 1.4, 0.02)
            t.data.materials.append(pmat('RefLabelNight', '#e8e8e8', emit=1.0) if night else pmat('RefLabel', '#111111'))
            labels.append(t)
    # 地面
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, total_d / 2, 0))
    gp = bpy.context.active_object
    gp.scale = (maxw * 1.6 + 60, total_d * 1.6 + 60, 1)
    gp.data.materials.append(pmat('RefGroundNight', '#22252c', rough=1.0) if night else pmat('RefGround', '#7d8288', rough=1.0))
    # 相機（正交，從前上方看，等比例）
    cam_d = bpy.data.cameras.new('cam')
    cam_d.type = 'ORTHO'
    cam = bpy.data.objects.new('cam', cam_d)
    link(cam)
    cam.rotation_euler = (math.pi / 2 - el, 0, 0)
    rot = cam.rotation_euler.to_matrix()
    inv = rot.inverted()
    pts = []
    for ob, lbl, sz in entries:
        for dx in (-0.5, 0.5):
            for dy in (-0.5, 0.5):
                for dz in (0, 1):
                    pts.append(inv @ Vector((ob.location.x + dx * sz[0], ob.location.y + dy * sz[1], dz * sz[2])))
    for t in labels:
        pts.append(inv @ Vector((t.location.x, t.location.y - tsize, 0)))
    xs_ = [p.x for p in pts]
    ys_ = [p.y for p in pts]
    W, Hh = max(xs_) - min(xs_), max(ys_) - min(ys_)
    rx, ry = 2400, max(900, min(2400, int(2400 * (Hh / max(W, 1e-3)) + 80)))
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    cam_d.ortho_scale = max(W, Hh * rx / ry) * 1.06
    cx, cy = (max(xs_) + min(xs_)) / 2, (max(ys_) + min(ys_)) / 2
    zc = max(p.z for p in pts) + 200
    cam.location = rot @ Vector((cx, cy, zc))
    cam_d.clip_end = 2000
    sc.camera = cam
    # 燈光、世界
    sun_d = bpy.data.lights.new('sun', 'SUN')
    sun_d.energy = 0.5 if night else 2.4
    sun_d.angle = math.radians(3)
    sun = bpy.data.objects.new('sun', sun_d)
    link(sun)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    w = bpy.data.worlds.new('w')
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs[0].default_value = (0.02, 0.025, 0.05, 1) if night else (0.55, 0.62, 0.72, 1)
    bg.inputs[1].default_value = 0.8
    sc.world = w
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    try:
        sc.eevee.taa_render_samples = 16
    except AttributeError:
        pass
    sc.view_settings.view_transform = 'Standard'
    sc.render.filepath = os.path.join(TMP, f'props_{theme}{suffix}.png')
    bpy.ops.render.render(write_still=True)
    print(f'[props] 陳列圖 {sc.render.filepath}')
    # 清掉陳列用的東西，物件位置還原
    for o in labels + [gp, cam, sun, rob]:
        bpy.data.objects.remove(o, do_unlink=True)
    for it in ITEMS:
        it['obj'].location = (0, 0, 0)
        it['obj'].hide_render = False


def main():
    for th in THEMES:
        common.reset_scene()
        _MAT.clear()
        _IMG.clear()
        _ICO.clear()
        ITEMS.clear()
        print(f'[props] ===== {th}')
        BUILDERS[th]()
        export(th)
        if RENDER:
            render(th, night=(th == 'city'))
            render(th, night=(th == 'city'), suffix='_small', small=True)
            if th == 'city':
                render(th, night=False, suffix='_day')
    write_license()
    tot = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f'[props] assets_src/props 合計 {tot / 1e6:.2f} MB')


main()
