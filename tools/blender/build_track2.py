"""賽道產生器 v2（格式見 TRACK_V2.md）：一份 <id>_layout.json → 畫面 GLB、中心線 path.json、碰撞 col.json。

用法（在 repo 根目錄）：
  <Blender>\\blender.exe -b --factory-startup -P tools\\blender\\build_track2.py -- . <賽道 id>
讀 tools\\blender\\<id>_layout.json，輸出 assets\\<id>.glb、assets\\<id>_path.json、assets\\<id>_col.json。

layout 的讀取、中心線取樣、捷徑、立體交叉判定在 tools\\check_layout2.py（檢查工具共用同一份計算）。
這支負責把它們變成模型與碰撞：

- 路面（每點不同寬、側傾）、路緣石、路肩（edge 材質）、開放路肩外接地形的過渡帶（Verge）
- 護牆 wall／低護欄 rail（橋上一律有護欄）、跳台缺口（兩端斷面＋底下深谷＋水）
- 加速帶、捷徑土路、立體交叉（上層做成橋面板＋橋墩，避開下層路面）
- hazard（熔岩、水）、隧道外殼（只有畫面）、地圖邊界牆（車開得到的範圍外緣）
- 地形：貼著路的高度、離路越遠越回到主題的起伏；路底下的地形壓低，不會穿出路面

畫面與碰撞用同一組三角形（路面、路緣石、路肩、過渡帶、加速帶、地形），兩邊永遠對得上。
座標：一律寫遊戲座標（three.js，Y 朝上），建 Blender 物件時才轉；layout 的 p 是 [x, z, y]。
"""
import base64
import bpy
import json
import math
import os
import random
import struct
import sys
import time
from mathutils import Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))  # tools\：check_layout2
from common import (Builder, Instances, M, basis, box, cone, cylinder, export_glb, mat, reset_scene, sphere)  # noqa: E402
import check_layout2 as L2  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ROOT = os.path.abspath(argv[0] if argv else '.')
TRACK = argv[1] if len(argv) > 1 else 'testbed'
LAYOUT = L2.load_layout(TRACK, ROOT)
if not L2.is_v2(LAYOUT):
    raise SystemExit(f'[track2] {TRACK}_layout.json 不是 v2 格式（points 要是物件），舊格式請用 build_track.py')
THEME = LAYOUT.get('theme', 'hills')
random.seed(617 + sum(map(ord, TRACK)))
T0 = time.time()


def log(*a):
    print('[track2]', *a, f'({time.time() - T0:.1f}s)', flush=True)


reset_scene()

# ================================================================ 主題（模型顏色；天空、燈光在 js/themes.js）
# terrain：hills 起伏丘陵、dunes 沙丘、flat 平地、sea 小島（外圍沉進海裡）、quay 碼頭
# surf：地形的地面種類（col.json）
THEMES = {
    'hills': dict(ground='#6cc24a', terrain='hills', amp=16, curb=('#e53935', '#f4f4f4'),
                  wall=('#1e88e5', '#fafafa', '#ffd54f'), banner='#1a3fa0', surf='grass',
                  trees=('#43a047', '#7cc95a', '#2e8b3e', '#2f7d55'), mountains=('#6f9a86', '#86a3bd', '#7c8fa8')),
    'beach': dict(ground='#f0d595', terrain='sea', amp=3, curb=('#ff7043', '#ffffff'),
                  wall=('#26c6da', '#ffffff', '#ffb74d'), banner='#00838f', surf='sand',
                  trees=('#2e9b4f', '#4cbb5c', '#2e9b4f', '#4cbb5c'), mountains=('#4caf50', '#66bb6a', '#43a047')),
    'desert': dict(ground='#e2a865', terrain='dunes', amp=12, curb=('#e65100', '#fff3e0'),
                   wall=('#d84315', '#ffe0b2', '#8d6e63'), banner='#bf360c', surf='sand',
                   trees=('#3f9b4f', '#a88b4a', '#3f9b4f', '#a88b4a'), mountains=('#b5552f', '#c96b3c', '#a3462a')),
    'snow': dict(ground='#f2f6fb', terrain='hills', amp=26, curb=('#1e88e5', '#ffffff'),
                 wall=('#e53935', '#fafafa', '#90caf9'), banner='#1565c0', surf='snow',
                 trees=('#2c6b4f', '#2c6b4f', '#2c6b4f', '#2c6b4f'), mountains=('#dfe8f2', '#c9d6e3', '#b8c7d8')),
    'city': dict(ground='#3b404c', terrain='flat', amp=0, curb=('#ffd600', '#222222'),
                 wall=('#ff2e88', '#20232c', '#00e5ff'), banner='#311b92', surf='grass',
                 trees=('#2e7d32', '#388e3c', '#2e7d32', '#1b5e20'), mountains=('#2a2f3a', '#323848', '#262b36')),
    'volcano': dict(ground='#3d3436', terrain='hills', amp=20, curb=('#d50000', '#212121'),
                    wall=('#4e342e', '#ff7043', '#ffab00'), banner='#3e2723', surf='grass',
                    trees=('#4a3b38', '#5d4037', '#4a3b38', '#3e2723'), mountains=('#3a2a28', '#4a3230', '#2e2220')),
    'sakura': dict(ground='#9ccc65', terrain='hills', amp=10, curb=('#e91e63', '#ffffff'),
                   wall=('#d32f2f', '#fafafa', '#f8bbd0'), banner='#ad1457', surf='grass',
                   trees=('#f8bbd0', '#f48fb1', '#fce4ec', '#2f7d55'), mountains=('#8fa8b8', '#a3b4c8', '#7c8fa8')),
    'autumn': dict(ground='#b39b4c', terrain='hills', amp=24, curb=('#d84315', '#fff3e0'),
                   wall=('#6d4c41', '#ffe0b2', '#ff8f00'), banner='#bf360c', surf='grass',
                   trees=('#d84315', '#ff8f00', '#c62828', '#6d8f3a'), mountains=('#8d6e63', '#a1887f', '#795548')),
    'candy': dict(ground='#ffdff0', terrain='hills', amp=9, curb=('#ff4fa3', '#ffffff'),
                  wall=('#ff80ab', '#ffffff', '#80d8ff'), banner='#ec407a', surf='grass',
                  trees=('#ff80ab', '#80d8ff', '#b9f6ca', '#ffd180'), mountains=('#f8bbd0', '#e1bee7', '#b3e5fc')),
    'harbor': dict(ground='#4a4f5a', terrain='quay', amp=0, curb=('#ffd600', '#222222'),
                   wall=('#1e88e5', '#20232c', '#ffca28'), banner='#0d47a1', surf='grass',
                   trees=('#2e7d32', '#388e3c', '#2e7d32', '#1b5e20'), mountains=('#1d2433', '#232b3c', '#1a2030')),
}
TH = THEMES.get(THEME, THEMES['hills'])
NIGHT = THEME in ('city', 'harbor')
TINT = {  # 地面頂點色：(亮處, 暗處, 路邊磨損帶)，sRGB 乘數
    'hills': ((1.0, 1.0, 1.0), (0.74, 0.86, 0.62), (0.86, 0.8, 0.62)),
    'beach': ((1.0, 1.0, 1.0), (0.94, 0.88, 0.78), (0.9, 0.86, 0.78)),
    'desert': ((1.0, 1.0, 1.0), (0.86, 0.7, 0.58), (0.92, 0.84, 0.72)),
    'snow': ((1.0, 1.0, 1.0), (0.82, 0.88, 1.0), (0.8, 0.82, 0.86)),
    'city': ((1.0, 1.0, 1.0), (0.8, 0.82, 0.9), (0.72, 0.72, 0.76)),
    'volcano': ((1.0, 1.0, 1.0), (0.66, 0.58, 0.6), (0.78, 0.68, 0.64)),
    'sakura': ((1.0, 1.0, 1.0), (0.8, 0.9, 0.72), (0.92, 0.86, 0.8)),
    'autumn': ((1.0, 1.0, 1.0), (0.84, 0.7, 0.56), (0.86, 0.78, 0.66)),
    'candy': ((1.0, 1.0, 1.0), (0.74, 0.98, 0.9), (0.96, 0.9, 0.94)),
    'harbor': ((1.0, 1.0, 1.0), (0.84, 0.87, 0.94), (0.74, 0.74, 0.78)),
}.get(THEME, ((1.0, 1.0, 1.0), (0.74, 0.86, 0.62), (0.86, 0.8, 0.62)))

# 地面種類（col.json 的 surf）
SURF = {'road': 0, 'curb': 1, 'grass': 2, 'boost': 3, 'dirt': 4, 'hazard': 5, 'sand': 6, 'snow': 6}
TERRAIN_SURF = SURF.get(TH['surf'], 2)

OPEN_REACH = 40.0    # 開放路肩：路肩外緣再往外多遠內車開得到（地圖邊界牆圍在這裡）
BLEND = 40.0         # 地形從路邊高度漸變回主題起伏的距離
APRON = (1.5, 4.0, 8.0, 13.0, 19.0, 26.0)  # 開放路肩外的過渡帶環（離路肩外緣的距離）
WALL_PROF = [(0, -0.7), (0, 0.72), (0.0525, 0.86), (0.175, 0.96), (0.35, 1.0), (0.525, 0.96), (0.6475, 0.86), (0.7, 0.72), (0.7, -0.7)]
RAIL_PROF = [(0.0, 0.42), (0.0, 0.82), (0.12, 0.82), (0.12, 0.42)]
CURB_PROF = [(0.0, 0.02), (0.5, 0.125), (1.0, 0.05), (1.0, -0.15)]  # (路緣石寬的比例, 高度)
WALL_H, RAIL_H = 1.0, 0.82
DECK_T = 1.4         # 橋面板厚度
DECK_EDGE = 0.75     # 橋面板比路肩外緣多出去的寬度（放護欄）

# ================================================================ 賽道模型（取樣、捷徑、交叉）
MD = L2.build_model(LAYOUT)
MAIN = MD['main']
SCS = MD['shortcuts']
STRIPS = MD['strips']
GAPS = MD['gaps']
N = MAIN.n
log(f'{TRACK} ({THEME}) length={MAIN.length:.1f}m samples={N} shortcuts={len(SCS)} gaps={len(GAPS)} '
    f'bridge samples={sum(sum(st.bridge) for st in STRIPS)}')
for c in L2.cluster(MD['crossings']):
    log(f'  crossing: {c["a"]}#{c["ia"]} over {c["b"]}#{c["ib"]} dy={c["dy"]:.1f}m' + ('' if c['dy'] >= L2.MIN_CLEAR else '  !! < 7m'))
if MD['conflicts']:
    log(f'  !! {len(MD["conflicts"])} 處路面重疊但高差不足（請跑 tools/check_layout2.py）')
GAP_OF = {}
for g in GAPS:
    for k in range(g['count']):
        GAP_OF[(g['g0'] + k) % N] = g

smooth = L2.smooth


def lerp3(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


# ---------------------------------------------------------------- hazard 多邊形

def poly_area(poly):
    return sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly))) / 2


def expand_poly(poly, d):
    n = len(poly)
    ccw = poly_area(poly) > 0
    out = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        ns = []
        for a, b in ((p0, p1), (p1, p2)):
            dx, dz = b[0] - a[0], b[1] - a[1]
            ll = math.hypot(dx, dz) or 1.0
            ns.append((dz / ll, -dx / ll) if ccw else (-dz / ll, dx / ll))
        mx, mz = ns[0][0] + ns[1][0], ns[0][1] + ns[1][1]
        ml = math.hypot(mx, mz) or 1.0
        mx, mz = mx / ml, mz / ml
        k = min(2.0, 1.0 / max(0.2, mx * ns[0][0] + mz * ns[0][1]))
        out.append((p1[0] + mx * d * k, p1[1] + mz * d * k))
    return out


def triangulate(poly):
    """ear clipping；回傳頂點索引三元組。"""
    idx = list(range(len(poly)))
    if poly_area(poly) < 0:
        idx.reverse()
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if cross(a, b, c) <= 1e-9:
                continue
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def sdist(x, z, poly):
    """到多邊形邊界的距離，裡面為負。"""
    dmin = 1e18
    for i in range(len(poly)):
        ax, az = poly[i]
        bx, bz = poly[(i + 1) % len(poly)]
        ex, ez = bx - ax, bz - az
        l2 = ex * ex + ez * ez or 1e-9
        u = max(0.0, min(1.0, ((x - ax) * ex + (z - az) * ez) / l2))
        dmin = min(dmin, math.hypot(x - ax - ex * u, z - az - ez * u))
    return -dmin if L2.point_in_poly(x, z, poly) else dmin


HAZ = []
for hz in LAYOUT.get('hazards', []):
    poly = [(float(p[0]), float(p[1])) for p in hz['poly']]
    HAZ.append({'type': hz.get('type', 'water'), 'poly': poly, 'y': float(hz.get('y', -1.0)),
                'vis': expand_poly(poly, 6.0)})

# ================================================================ 範圍、基準高度
allp = [p for st in STRIPS for p in st.S]
MARGIN = 260 if TH['terrain'] in ('sea', 'quay') else 230
minx = min(p[0] for p in allp) - MARGIN
maxx = max(p[0] for p in allp) + MARGIN
minz = min(p[2] for p in allp) - MARGIN
maxz = max(p[2] for p in allp) + MARGIN
cx, cz = (minx + maxx) / 2, (minz + maxz) / 2
FAR = max(maxx - minx, maxz - minz) / 2 + 160
WATER_Y = -0.6
QUAY = 52.0

# 基準高度：地形要貼合的取樣點高度做反距離加權（粗格子，查的時候雙線性）
_bp = [(st.S[i][0], st.S[i][1], st.S[i][2]) for st in STRIPS for i in range(0, st.n, 3) if st.terr_ok(i)]
BG = 30.0
bnx = int((maxx - minx) / BG) + 2
bnz = int((maxz - minz) / BG) + 2
BASE = []
for iz in range(bnz):
    row = []
    for ix in range(bnx):
        x, z = minx + ix * BG, minz + iz * BG
        num = den = 0.0
        for px, py, pz in _bp:
            w = 1.0 / ((px - x) ** 2 + (pz - z) ** 2 + 900.0)
            num += w * py
            den += w
        row.append(num / den)
    BASE.append(row)


def base(x, z):
    fx, fz = (x - minx) / BG, (z - minz) / BG
    ix = max(0, min(bnx - 2, int(fx)))
    iz = max(0, min(bnz - 2, int(fz)))
    tx, tz = max(0.0, min(1.0, fx - ix)), max(0.0, min(1.0, fz - iz))
    a = BASE[iz][ix] * (1 - tx) + BASE[iz][ix + 1] * tx
    b = BASE[iz + 1][ix] * (1 - tx) + BASE[iz + 1][ix + 1] * tx
    return a * (1 - tz) + b * tz


def natural(x, z, emin):
    """主題的地形起伏（離路越遠越明顯）。"""
    y = base(x, z)
    mode = TH['terrain']
    amp = TH['amp']
    nz1 = noise.noise(Vector((x * 0.011, z * 0.011, 0.3))) * 0.5 + 0.5
    nz2 = noise.noise(Vector((x * 0.05, z * 0.05, 1.7)))
    k = smooth(4.0, 60.0, emin)
    ex = min(x - minx, maxx - x, z - minz, maxz - z)
    if mode == 'sea':
        return y + nz2 * 0.3 * k - smooth(5, 34, emin) * 4.0 - (1 - smooth(0, 200, ex)) * 6
    if mode == 'quay':
        edge = QUAY + noise.noise(Vector((x * 0.012, z * 0.012, 2.0))) * 8
        return y - smooth(edge, edge + 7, emin) * 5.0
    if mode == 'dunes':
        y += k * (abs(noise.noise(Vector((x * 0.018, z * 0.03, 4.0)))) * amp + nz2)
    elif mode != 'flat':
        y += k * max(0.0, nz1 * amp + nz2 * 1.5)
    y += (1 - smooth(0, 120, ex)) * (8 if mode == 'flat' else 55.0)
    return y


PIT_BACK = 6.0  # 深谷往起跳段、落地段底下多挖幾公尺（地形網格 6m 一格，斜坡才不會伸進缺口）


def pit(x, z, h):
    """跳台缺口底下的深谷。"""
    if not GAPS:
        return h
    pr = MAIN.project(x, z, 3, False)
    if pr is None:
        return h
    d, o, a, u, bi = pr
    s = MAIN.s[a] + u * MAIN.step
    g = None
    for gg in GAPS:
        s0 = MAIN.s[gg['lip']] - PIT_BACK
        span = (MAIN.s[gg['land']] - MAIN.s[gg['lip']]) % MAIN.length + 2 * PIT_BACK
        if (s - s0) % MAIN.length <= span:
            g = gg
            break
    if g is None:
        return h
    eo = MAIN.eo_max(bi)
    s = 1 - smooth(eo + 17, eo + 25, d)
    if s <= 0:
        return h
    return min(h, h + (g['pit'] - h) * s)


def hz_lower(x, z, h):
    for hz in HAZ:
        sd = sdist(x, z, hz['poly'])
        if sd > 8:
            continue
        floor = hz['y'] - 1.5 - min(2.0, max(0.0, -sd) * 0.15)
        if h > floor:
            h = floor + (h - floor) * smooth(0.0, 8.0, sd)
    return h


def region(x, z):
    """車開得到的範圍：r ≤ 0 在裡面。回傳 (r, 最近那條路是否為開放路肩, 最近那條路的高度)。"""
    best = (1e9, False, 0.0)
    for st in STRIPS:
        pr = st.project(x, z, 4, False)
        if pr is None:
            continue
        d, o, a, u, bi = pr
        side = 1 if o >= 0 else -1
        eo = st.eo_max(bi)
        open_ = st.drawn[bi] and not st.gap[bi] and not st.bridge[bi] and st.wall(bi, side) == 'none'
        r = d - (eo + (OPEN_REACH if open_ else 1.5))
        if r < best[0]:
            best = (r, open_, st.S[bi][1])
    for hz in HAZ:  # hazard 整塊圈進來（邊界牆不會穿過熔岩池）
        r = sdist(x, z, hz['poly']) - 10.0
        if r < best[0]:
            best = (r, True, hz['y'])
    return best


BR_STRIPS = [st for st in STRIPS if any(st.bridge)]


def bridge_clamp(x, z, h):
    for st in BR_STRIPS:
        pr = st.project(x, z, 2, False)
        if pr is None:
            continue
        d, o, a, u, bi = pr
        eo = st.eo_max(bi)
        if st.bridge[bi] and d < eo + 6:
            top = st.surface_y(a, u, max(-eo, min(eo, o)))
            h = min(h, top - DECK_T - 0.6)
    return h


def tinfo(x, z):
    """地形高度（貼路、回到主題起伏、深谷、hazard 窪地），以及網格要往下壓的量、離最近路肩外緣的距離。"""
    num, den = 0.0, 1.0
    emin, lower = 1e9, 0.0
    for st in STRIPS:
        pr = st.project(x, z, 3, True)
        if pr is None:
            continue
        d, o, a, u, bi = pr
        side = 1 if o >= 0 else -1
        b = st.nxt(a)
        eo = st.eo(a) + (st.eo(b) - st.eo(a)) * u if b is not None else st.eo(a)
        e = d - eo
        if e < 0:
            E = st.surface_y(a, u, o) - 0.05
        else:
            E = st.surface_y(a, u, side * eo)
        aa = max(e, 0.0) / BLEND
        if aa < 1:
            s = aa * aa * (3 - 2 * aa)
            w = (1 - s) ** 2 / (aa * aa + 1e-4)
            num += w * E
            den += w
        emin = min(emin, e)
        if e < APRON[-1]:
            # 地形網格往下壓：路底下 0.6m、過渡帶底下 0.35m，到過渡帶最外圈歸零（那裡兩者同高、接得起來）
            lower = max(lower, (0.6 - 0.25 * smooth(0, 3, e)) * (1 - smooth(APRON[-1] - 7, APRON[-1], e)))
    h = (num + natural(x, z, emin)) / den
    h = pit(x, z, h)
    h = hz_lower(x, z, h)
    return h, lower, emin


# ================================================================ 材質
m_road = mat('Road', '#5b6170', rough=0.9)
m_ground = mat('Ground', TH['ground'], rough=1.0)
m_curb = (mat('CurbA', TH['curb'][0]), mat('CurbB', TH['curb'][1]))
m_wall_a = mat('WallA', TH['wall'][0], emit=0.6 if NIGHT else 0)
m_wall_b = mat('WallB', TH['wall'][1])
m_wall_top = mat('WallTop', TH['wall'][2], emit=1.0 if NIGHT else 0)
m_chk_b = mat('CheckBlack', '#202020')
m_chk_w = mat('CheckWhite', '#ffffff')
m_boost = mat('Boost', '#ffb300', rough=0.4, emit=0.9)
m_dirt = mat('DirtRoad', '#a8825a', rough=1.0)
EDGE_MAT = {'grass': m_ground, 'sand': mat('EdgeSand', '#e8d29c', rough=1.0),
            'snow': mat('EdgeSnow', '#f4f8fc', rough=1.0), 'dirt': mat('EdgeDirt', '#9c7a52', rough=1.0)}
m_bridge = mat('Bridge', '#c9ced6' if not NIGHT else '#5a6070', rough=0.8)
m_pier = mat('BridgePier', '#a9afb8' if not NIGHT else '#4a505c', rough=0.85)
m_rail = mat('Rail', '#dfe4ea', rough=0.35, metal=0.6)
m_railpost = mat('RailPost', '#59606b', rough=0.6, metal=0.3)
m_tunnel = mat('Tunnel', '#8a8f99', rough=0.9)
m_tlight = mat('TunnelLight', '#fff3c4', emit=2.0)
m_cliff = mat('Cliff', '#8a7a68', rough=1.0)
m_fence = mat('Fence', '#b07a4a', rough=0.9)
m_metal = mat('Metal', '#b0bec5', rough=0.35, metal=0.6)
m_banner = mat('Banner', TH['banner'])
HZ_MAT = {'lava': lambda: mat('Lava', '#ff5a1f', emit=2.0), 'water': lambda: mat('Water', '#3fb6f5', rough=0.2)}

# ================================================================ 網格建構（畫面＋碰撞同一組三角形）
COL_T, COL_S, COL_W = [], [], []


def col_tri(a, b, c, s):
    COL_T.extend((a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]))
    COL_S.append(s)


def col_wall(p, q, y0, y1):
    COL_W.extend((p[0], p[2], q[0], q[2], y0, y1))


class MB:
    """共用頂點的網格。tri/quad 給 surf 就同時寫進碰撞。"""

    def __init__(self, name, uv=False):
        self.name, self.uv = name, uv
        self.v, self.f, self.fm, self.fuv, self.fs, self.mats = [], [], [], [], [], []
        self.cache = {}

    def V(self, key, p):
        i = self.cache.get(key)
        if i is None:
            i = len(self.v)
            self.v.append((p[0], p[1], p[2]))
            self.cache[key] = i
        return i

    def add(self, p):
        self.v.append((p[0], p[1], p[2]))
        return len(self.v) - 1

    def face(self, idx, m, uv=None, smooth=False):
        if m not in self.mats:
            self.mats.append(m)
        self.f.append(tuple(idx))
        self.fm.append(self.mats.index(m))
        self.fuv.append(uv)
        self.fs.append(smooth)

    def tri(self, a, b, c, m, uv=None, smooth=True, surf=None):
        self.face((a, b, c), m, uv, smooth)
        if surf is not None:
            col_tri(self.v[a], self.v[b], self.v[c], surf)

    def quad(self, a, b, c, d, m, uv=None, smooth=True, surf=None):
        self.tri(a, b, c, m, (uv[0], uv[1], uv[2]) if uv else None, smooth, surf)
        self.tri(a, c, d, m, (uv[0], uv[2], uv[3]) if uv else None, smooth, surf)

    def build(self, color_fn=None):
        if not self.f:
            return None
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([(p[0], -p[2], p[1]) for p in self.v], [], self.f)
        for m in self.mats:
            me.materials.append(m)
        uvl = me.uv_layers.new(name='UVMap') if self.uv else None
        for i, poly in enumerate(me.polygons):
            poly.material_index = self.fm[i]
            poly.use_smooth = self.fs[i]
            if uvl is not None:
                uv = self.fuv[i]
                for k, li in enumerate(poly.loop_indices):
                    uvl.data[li].uv = uv[k] if uv else (0.0, 0.0)
        me.validate()
        me.update()
        if color_fn is not None:
            attr = me.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
            for i, v in enumerate(me.vertices):
                c = v.co
                r, g, b = color_fn(c.x, c.z, -c.y)
                attr.data[i].color_srgb = (r, g, b, 1.0)
            me.color_attributes.active_color = attr
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


def runs(st, fn):
    """沿線把 fn(段) 相同的連續段分組：[(值, [段…], 是否整圈)]，值 None 的略過。"""
    m = st.n if st.closed else st.n - 1
    vals = [fn(i) for i in range(m)]
    if st.closed:
        start = next((k for k in range(m) if vals[k] != vals[k - 1]), None)
        if start is None:
            return [(vals[0], list(range(m)), True)] if vals[0] is not None else []
    else:
        start = 0
    out, cur = [], None
    for kk in range(m):
        k = (start + kk) % m
        v = vals[k]
        if cur is not None and cur[0] == v:
            cur[1].append(k)
        else:
            if cur is not None and cur[0] is not None:
                out.append((cur[0], cur[1], False))
            cur = [v, [k]]
    if cur is not None and cur[0] is not None:
        out.append((cur[0], cur[1], False))
    return out


def clampo(st, i, side, o):
    """彎道內側的偏移不超過轉彎半徑的 85%（免得路肩、護牆自己打結）。"""
    c = st.curv[i] * side
    if c > 1e-6:
        return max(st.hw[i] + st.curb[i], min(o, 0.85 / c))
    return o


def tight(st, i, side):
    c = st.curv[i] * side
    return c > 1e-6 and st.eo(i) + DECK_EDGE >= 0.85 / c


def fwd_yaw(t):
    return math.atan2(-t[2], t[0])


props = Builder('Props')

# ================================================================ 地形網格（先算：過渡帶、橋墩、場景物件都要查高度）
GS = 6.0
gnx = int((maxx - minx) / GS) + 1
gnz = int((maxz - minz) / GS) + 1
H = [[0.0] * gnx for _ in range(gnz)]
EM = [[0.0] * gnx for _ in range(gnz)]
RG = [[0.0] * gnx for _ in range(gnz)]
for iz in range(gnz):
    z = minz + iz * GS
    for ix in range(gnx):
        x = minx + ix * GS
        h, lower, emin = tinfo(x, z)
        h = bridge_clamp(x, z, h) - lower
        H[iz][ix] = h
        EM[iz][ix] = emin
        RG[iz][ix] = region(x, z)[0] if emin < OPEN_REACH + 30 else 1e9
log(f'terrain grid {gnx}x{gnz}')


def gh(x, z):
    """地形網格高度（雙線性）。"""
    fx, fz = (x - minx) / GS, (z - minz) / GS
    ix = max(0, min(gnx - 2, int(fx)))
    iz = max(0, min(gnz - 2, int(fz)))
    tx, tz = max(0.0, min(1.0, fx - ix)), max(0.0, min(1.0, fz - iz))
    a = H[iz][ix] * (1 - tx) + H[iz][ix + 1] * tx
    b = H[iz + 1][ix] * (1 - tx) + H[iz + 1][ix + 1] * tx
    return a * (1 - tz) + b * tz


def gcolor(x, z, y, e, slope):
    n = noise.noise(Vector((x * 0.018, z * 0.018, 9.0))) + 0.5 * noise.noise(Vector((x * 0.06, z * 0.06, 3.0)))
    c = L2.lerp3(TINT[0], TINT[1], smooth(-0.35, 0.45, n))
    c = tuple(v * (1 - min(0.35, slope * 0.9)) for v in c)
    c = L2.lerp3(c, TINT[2], 0.65 * (1 - smooth(-1.0, 5.0, e)))
    if THEME == 'autumn':
        c = L2.lerp3(c, (1.0, 0.62, 0.42), 0.55 * smooth(0.25, 0.6, noise.noise(Vector((x * 0.04, z * 0.04, 6.0)))))
    if THEME == 'sakura':
        c = L2.lerp3(c, (1.0, 0.8, 0.86), 0.5 * smooth(0.2, 0.55, noise.noise(Vector((x * 0.035, z * 0.035, 8.0)))))
    if THEME == 'snow':
        c = L2.lerp3(c, (0.78, 0.86, 1.0), smooth(0.2, -0.6, n))
    for hz in HAZ:  # hazard 周圍：熔岩發紅、水邊變暗
        sd = sdist(x, z, hz['poly'])
        if sd < 22:
            k = 1 - smooth(0, 22, sd)
            c = L2.lerp3(c, (1.0, 0.55, 0.38) if hz['type'] == 'lava' else (0.7, 0.66, 0.56), 0.8 * k)
    if GAPS and y < min(g['pit'] for g in GAPS) + 6:
        c = L2.lerp3(c, (0.62, 0.56, 0.5), 0.7)
    return c


CG = [[None] * gnx for _ in range(gnz)]
for iz in range(gnz):
    for ix in range(gnx):
        hx = H[iz][min(gnx - 1, ix + 1)] - H[iz][max(0, ix - 1)]
        hz_ = H[min(gnz - 1, iz + 1)][ix] - H[max(0, iz - 1)][ix]
        slope = math.hypot(hx, hz_) / (2 * GS)
        CG[iz][ix] = gcolor(minx + ix * GS, minz + iz * GS, H[iz][ix], EM[iz][ix], slope)


def cg_at(x, y, z):
    fx, fz = (x - minx) / GS, (z - minz) / GS
    ix = max(0, min(gnx - 2, int(fx)))
    iz = max(0, min(gnz - 2, int(fz)))
    tx, tz = max(0.0, min(1.0, fx - ix)), max(0.0, min(1.0, fz - iz))
    a = L2.lerp3(CG[iz][ix], CG[iz][ix + 1], tx)
    b = L2.lerp3(CG[iz + 1][ix], CG[iz + 1][ix + 1], tx)
    return L2.lerp3(a, b, tz)


terrain = MB('Terrain')
for iz in range(gnz):
    for ix in range(gnx):
        terrain.add((minx + ix * GS, H[iz][ix], minz + iz * GS))
ncol_terrain = 0
for iz in range(gnz - 1):
    for ix in range(gnx - 1):
        a = iz * gnx + ix
        b, c, d = a + gnx, a + gnx + 1, a + 1
        inr = min(RG[iz][ix], RG[iz + 1][ix], RG[iz + 1][ix + 1], RG[iz][ix + 1]) <= 9.0
        terrain.quad(a, b, c, d, m_ground, surf=TERRAIN_SURF if inr else None)
        ncol_terrain += 2 if inr else 0
t_ob = terrain.build()
attr = t_ob.data.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
for iz in range(gnz):
    for ix in range(gnx):
        attr.data[iz * gnx + ix].color_srgb = (*CG[iz][ix], 1.0)
t_ob.data.color_attributes.active_color = attr
log(f'terrain collision tris={ncol_terrain}')

# ================================================================ 路面、路緣石、路肩、過渡帶
road_mb = MB('Road', uv=True)
sc_mb = MB('Shortcut', uv=True)
curb_mb = MB('Curbs')
verge = MB('Verge')
_fcache = {}


def fh(x, z):
    k = (round(x, 3), round(z, 3))
    if k not in _fcache:
        _fcache[k] = tinfo(x, z)[0]
    return _fcache[k]


def main_apron_covers(p):
    pr = MAIN.project(p[0], p[2], 3, False)
    if pr is None:
        return False
    d, o, a, u, bi = pr
    side = 1 if o >= 0 else -1
    return (MAIN.wall(bi, side) == 'none' and not MAIN.bridge[bi] and not MAIN.gap[bi]
            and d < MAIN.eo(bi) + APRON[-1] - 2)


def main_inside(p):
    pr = MAIN.project(p[0], p[2], 3, False)
    return pr is not None and pr[0] < MAIN.eo(pr[4]) + 0.5


def strip_surfaces(st, mb, rmat, rsurf):
    key = st.name
    segs = [i for i in range(st.n if st.closed else st.n - 1) if st.seg_ok(i)]
    for i in segs:
        j = st.nxt(i)
        vi = st.s[i] / 8.0
        vj = (st.s[j] if j != 0 else st.length) / 8.0
        # 路面：三欄（-hw, 0, hw），u 橫跨路寬 0..1、v 沿路每 8 公尺一個循環（同 v1，JS 的路面紋理靠這個）
        ri = [mb.V((key, 'r', i, c), st.point(i, c * st.hw[i])) for c in (-1, 0, 1)]
        rj = [mb.V((key, 'r', j, c), st.point(j, c * st.hw[j])) for c in (-1, 0, 1)]
        for c in range(2):
            u0, u1 = c * 0.5, (c + 1) * 0.5
            mb.quad(ri[c], ri[c + 1], rj[c + 1], rj[c], rmat, uv=[(u0, vi), (u1, vi), (u1, vj), (u0, vj)], surf=rsurf)
        for side in (-1, 1):
            # 路緣石
            if st.curb[i] > 0.05 and st.curb[j] > 0.05:
                def cp(ii, k):
                    f, hh = CURB_PROF[k]
                    return curb_mb.V((key, 'c', side, ii, k), st.point(ii, side * (st.hw[ii] + f * st.curb[ii]), hh))
                m = m_curb[i % 2]
                for k in range(3):
                    a, b, c, d = cp(i, k), cp(i, k + 1), cp(j, k + 1), cp(j, k)
                    if side < 0:
                        a, b, c, d = b, a, d, c
                    curb_mb.quad(a, b, c, d, m, surf=SURF['curb'] if k < 2 else None)
            # 路肩（路緣石外緣 → 護牆內面／開放路肩外緣）
            br = st.bridge[i] and st.bridge[j]

            def vo(ii, k):
                inner = st.hw[ii] + st.curb[ii]
                o = inner if k == 0 else max(inner, clampo(st, ii, side, st.eo(ii)))
                return verge.V((key, 'v', side, ii, 0 if k == 0 else 1), st.point(ii, side * o))
            if st.run[i] > 0.05:
                em = m_bridge if br else EDGE_MAT.get(st.edge[i], m_ground)
                es = SURF['road'] if br else SURF.get(st.edge[i], TERRAIN_SURF)
                a, b, c, d = vo(i, 0), vo(i, 1), vo(j, 1), vo(j, 0)
                if side < 0:
                    a, b, c, d = b, a, d, c
                if st is not MAIN and any(main_inside(verge.v[q]) for q in (a, b, c, d)):
                    pass  # 捷徑的路肩蓋到主線路肩上：不畫（主線路肩已經是 edge 材質）
                else:
                    verge.quad(a, b, c, d, em, surf=es)
            # 過渡帶：開放路肩外面接到地形
            if st.wall(i, side) == 'none' and not (st.bridge[i] or st.bridge[j]):
                def ap(ii, k):
                    if k == 0:
                        return vo(ii, 1)
                    base_o = max(st.hw[ii] + st.curb[ii], clampo(st, ii, side, st.eo(ii)))
                    o = max(base_o, clampo(st, ii, side, st.eo(ii) + APRON[k - 1]))
                    p = st.point(ii, side * o)
                    return verge.V((key, 'a', side, ii, k), (p[0], fh(p[0], p[2]), p[2]))
                for k in range(len(APRON)):
                    a, b, c, d = ap(i, k), ap(i, k + 1), ap(j, k + 1), ap(j, k)
                    if st is not MAIN and all(main_apron_covers(verge.v[q]) for q in (a, b, c, d)):
                        continue  # 捷徑接主線處：主線的過渡帶已經鋪了，不重疊（免得閃面）
                    if side < 0:
                        a, b, c, d = b, a, d, c
                    verge.quad(a, b, c, d, m_ground, surf=TERRAIN_SURF)


strip_surfaces(MAIN, road_mb, m_road, SURF['road'])
for sc in SCS:
    strip_surfaces(sc, sc_mb, m_dirt, SURF.get(sc.surf, 4))
road_mb.build()
sc_mb.build()
curb_mb.build()
verge.build(color_fn=cg_at)
log(f'road/curb/verge built (verge verts={len(verge.v)})')

# ================================================================ 護牆、護欄
walls_mb = MB('Walls')
rails_mb = MB('Rails')
post = Builder('RailPost')
post.add(box(0.14, 1.25, 0.14, base=True), m_railpost)
post_me = post.mesh()
posts = Instances('RailPosts')


def wall_kind(st, i, side):
    if not st.seg_ok(i):
        return None
    w = st.wall(i, side)
    if w not in ('wall', 'rail'):
        return None
    j = st.nxt(i)
    if tight(st, i, side) or tight(st, j, side):
        return None
    return w


nwall = 0
for st in STRIPS:
    for side in (-1, 1):
        for wk, segs, full in runs(st, lambda i: wall_kind(st, i, side)):
            prof = WALL_PROF if wk == 'wall' else RAIL_PROF
            mb = walls_mb if wk == 'wall' else rails_mb
            key = (st.name, side, wk)

            def wp(ii, k):
                px, py = prof[k]
                ow = st.eo(ii)
                y = st.plane_y(ii, side * ow) + py
                s, r = st.S[ii], st.R[ii]
                o = side * (ow + px)
                return mb.V(key + (ii, k), (s[0] + r[0] * o, y, s[2] + r[2] * o))
            nk = len(prof) if wk == 'rail' else len(prof) - 1
            for i in segs:
                j = st.nxt(i)
                mside = m_wall_a if (i // 2) % 2 == 0 else m_wall_b
                for k in range(nk):
                    k2 = (k + 1) % len(prof)
                    a, b, c, d = wp(i, k), wp(i, k2), wp(j, k2), wp(j, k)
                    if side < 0:
                        a, b, c, d = b, a, d, c
                    if wk == 'wall':
                        mb.face((a, b, c, d), mside if k in (0, len(prof) - 2) else m_wall_top, smooth=0 < k < len(prof) - 2)
                    else:
                        mb.face((a, b, c, d), m_rail, smooth=False)
                ow_i, ow_j = st.eo(i), st.eo(j)
                yi, yj = st.plane_y(i, side * ow_i), st.plane_y(j, side * ow_j)
                col_wall(st.point(i, side * ow_i), st.point(j, side * ow_j), min(yi, yj) - 0.5,
                         max(yi, yj) + (WALL_H if wk == 'wall' else RAIL_H))
                nwall += 1
                if wk == 'rail' and i % 2 == 0:
                    p = st.point(i, side * (st.eo(i) + 0.22))
                    posts.put(post_me, (p[0], p[1] - 0.4, p[2]), yaw=fwd_yaw(st.T[i]))
            if not full:  # 兩端封口
                for ii, rev in ((segs[0], False), (st.nxt(segs[-1]), True)):
                    ring = [wp(ii, k) for k in range(len(prof))]
                    if (side < 0) != rev:
                        ring.reverse()
                    mb.face(ring, m_wall_top if wk == 'wall' else m_rail)
walls_mb.build()
rails_mb.build()
log(f'walls: {nwall} segments, rail posts {posts.count}')

# ================================================================ 橋：橋面板、橋墩
deck = MB('BridgeDeck')
npier = 0
for st in BR_STRIPS:
    def is_deck(i):
        j = st.nxt(i)
        return True if (st.seg_ok(i) and st.bridge[i] and st.bridge[j]) else None
    for _, segs, full in runs(st, is_deck):
        def dv(ii, side, k):
            ow = st.eo(ii) + (DECK_EDGE if k > 0 else 0)
            return deck.V((st.name, 'd', side, ii, k), st.point(ii, side * ow, 0.0 if k < 2 else -DECK_T))
        for i in segs:
            j = st.nxt(i)
            for side in (-1, 1):
                for k in range(2):  # 0：護欄底下的邊條，1：外側面
                    a, b, c, d = dv(i, side, k), dv(i, side, k + 1), dv(j, side, k + 1), dv(j, side, k)
                    if side < 0:
                        a, b, c, d = b, a, d, c
                    deck.face((a, b, c, d), m_bridge, smooth=False)
            deck.face((dv(i, 1, 2), dv(i, -1, 2), dv(j, -1, 2), dv(j, 1, 2)), m_bridge, smooth=False)  # 底面
        if not full:
            for ii in (segs[0], st.nxt(segs[-1])):
                deck.face((dv(ii, -1, 1), dv(ii, 1, 1), dv(ii, 1, 2), dv(ii, -1, 2)), m_bridge, smooth=False)
        # 橋墩：每 14 公尺一組，避開其他路面（含路肩）
        samples = segs + ([] if full else [st.nxt(segs[-1])])
        for k in range(3, len(samples) - 3, 7):
            ii = samples[k]
            cols = []
            for lat in (-0.55, 0.55):
                o = lat * st.hw[ii]
                p = st.point(ii, o)
                blocked = False
                for other in STRIPS:  # 附近每一段路（不只最近的那一點：最近的常常是橋自己）
                    for jj in other.near(p[0], p[2], 40):
                        if other is st:
                            dd = abs(jj - ii)
                            if st.closed:
                                dd = min(dd, st.n - dd)
                            if dd < 40:
                                continue
                        if not other.drawn[jj]:
                            continue
                        q = other.S[jj]
                        if math.hypot(p[0] - q[0], p[2] - q[2]) < other.eo_max(jj) + 0.7 + 2.0 + other.step:
                            blocked = True
                            break
                    if blocked:
                        break
                if blocked:
                    continue
                top = st.plane_y(ii, o) - DECK_T
                bot = gh(p[0], p[2]) - 1.0
                if top - bot < 1.5:
                    continue
                cols.append((p, top, bot))
            yaw = fwd_yaw(st.T[ii])
            for p, top, bot in cols:
                props.add(box(1.3, top - bot, 1.3, base=True), m_pier, M((p[0], bot, p[2]), rot=(0, yaw, 0)))
                tx, tz = st.T[ii][0], st.T[ii][2]
                rx, rz = st.R[ii][0], st.R[ii][2]
                cs = [(p[0] + (tx * a + rx * b) * 0.65, 0, p[2] + (tz * a + rz * b) * 0.65) for a, b in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
                for q in range(4):
                    col_wall(cs[q], cs[(q + 1) % 4], bot, top)
                npier += 1
            if len(cols) == 2:
                (p0, t0, _), (p1, t1, _) = cols
                mid = ((p0[0] + p1[0]) / 2, min(t0, t1), (p0[2] + p1[2]) / 2)
                span = math.hypot(p1[0] - p0[0], p1[2] - p0[2]) + 1.6
                props.add(box(1.4, 0.9, span, base=False), m_pier, M((mid[0], mid[1] - 0.45, mid[2]), rot=(0, yaw, 0)))
deck.build()
log(f'bridge piers {npier}')

# ================================================================ 隧道（只有畫面）
tun = MB('Tunnel')
ntun = 0
for st in STRIPS:
    for _, segs, full in runs(st, lambda i: True if (st.tunnel[i] and st.seg_ok(i)) else None):
        def prof(ii, outer):
            a = st.eo(ii) + 1.3 + (0.8 if outer else 0.0)
            h0 = -a * abs(st.tb[ii]) - 0.8
            crown = 3.2 + (0.8 if outer else 0.0)
            pts = [(-a, h0), (-a, 4.2)]
            for k in range(1, 10):
                t = math.pi - math.pi * k / 10
                pts.append((a * math.cos(t), 4.2 + crown * math.sin(t)))
            pts += [(a, 4.2), (a, h0)]
            return pts

        def tv(ii, outer, k):
            o, h = prof(ii, outer)[k]
            s, r = st.S[ii], st.R[ii]
            return tun.V((st.name, 't', ii, outer, k), (s[0] + r[0] * o, s[1] + h, s[2] + r[2] * o))
        npf = 13
        for i in segs:
            j = st.nxt(i)
            for outer in (False, True):
                for k in range(npf - 1):
                    a, b, c, d = tv(i, outer, k), tv(i, outer, k + 1), tv(j, outer, k + 1), tv(j, outer, k)
                    if not outer:
                        a, b, c, d = b, a, d, c
                    tun.face((a, b, c, d), m_tunnel, smooth=0 < k < npf - 2)
            if i % 4 == 0:
                s = st.S[i]
                props.add(box(0.7, 0.08, 3.2), m_tlight,
                          M((s[0], s[1] + 4.2 + 3.2 - 0.08, s[2]), rot=(0, fwd_yaw(st.T[i]) + math.pi / 2, 0)))
            ntun += 1
        if not full:  # 洞口：內外殼之間封起來
            for ii in (segs[0], st.nxt(segs[-1])):
                for k in range(npf - 1):
                    tun.face((tv(ii, False, k), tv(ii, False, k + 1), tv(ii, True, k + 1), tv(ii, True, k)), m_tunnel)
tun.build()
log(f'tunnel segments {ntun}')

# ================================================================ 跳台：缺口兩端的斷面、深谷的水
cliff = MB('Cliff')
pitw = MB('PitWater')
m_water = HZ_MAT['water']()
for g in GAPS:
    for ii in (g['lip'], g['land']):
        ow = MAIN.eo(ii) + 0.8
        lat = (-ow, -MAIN.hw[ii], 0.0, MAIN.hw[ii], ow)
        top = [cliff.add(MAIN.point(ii, o, -0.03)) for o in lat]
        bot = [cliff.add((MAIN.point(ii, o)[0], g['pit'] - 1.0, MAIN.point(ii, o)[2])) for o in lat]
        for k in range(len(lat) - 1):
            cliff.face((top[k], top[k + 1], bot[k + 1], bot[k]), m_cliff, smooth=False)
        col_wall(MAIN.point(ii, -ow), MAIN.point(ii, ow), g['pit'] - 1.0, MAIN.S[ii][1] - 0.3)
    # 起跳段、落地段懸在深谷上的那幾公尺：兩側也封成崖壁
    nb = int(math.ceil(PIT_BACK / MAIN.step)) + 1
    for k0, k1 in ((g['lip'] - nb, g['lip']), (g['land'], g['land'] + nb)):
        for k in range(k0, k1):
            i, j = k % N, (k + 1) % N
            for side in (-1, 1):
                pi_, pj = MAIN.point(i, side * (MAIN.eo(i) + 0.8)), MAIN.point(j, side * (MAIN.eo(j) + 0.8))
                q = [cliff.add(pi_), cliff.add(pj), cliff.add((pj[0], g['pit'] - 1.0, pj[2])), cliff.add((pi_[0], g['pit'] - 1.0, pi_[2]))]
                cliff.face(q, m_cliff, smooth=False)
    wy = g['pit'] + 2.0
    lo, hi = g['g0'] - 3, g['g0'] + g['count'] + 3
    for k in range(lo, hi):
        i, j = k % N, (k + 1) % N
        ow_i, ow_j = MAIN.eo_max(i) + 34, MAIN.eo_max(j) + 34

        def wv(ii, o):
            p = MAIN.point(ii, o)
            return pitw.V(('w', ii, o > 0), (p[0], wy, p[2]))
        pitw.quad(wv(i, -ow_i), wv(i, ow_i), wv(j, ow_j), wv(j, -ow_j), m_water, smooth=False, surf=SURF['hazard'])
    # 看不見的重生面：缺口正下方、比兩端路面低 3 公尺（掉下去碰到谷壁斜坡之前就先重生）
    ky = min(MAIN.S[g['lip']][1], MAIN.S[g['land']][1]) - 3.0
    for k in range(g['g0'] - 1, g['g0'] + g['count']):  # 起跳點 → 落地點
        i, j = k % N, (k + 1) % N
        oi, oj = MAIN.eo_max(i) + 20, MAIN.eo_max(j) + 20
        a, b = MAIN.point(i, -oi), MAIN.point(i, oi)
        c, d = MAIN.point(j, oj), MAIN.point(j, -oj)
        a, b, c, d = [(p[0], ky, p[2]) for p in (a, b, c, d)]
        col_tri(a, b, c, SURF['hazard'])
        col_tri(a, c, d, SURF['hazard'])
cliff.build()
pitw.build()

# ================================================================ hazard（熔岩、水）
for k, hz in enumerate(HAZ):
    hb = MB(f'Hazard_{k}')
    m = HZ_MAT.get(hz['type'], HZ_MAT['water'])()
    idx = [hb.add((p[0], hz['y'], p[1])) for p in hz['vis']]
    for a, b, c in triangulate(hz['vis']):
        hb.tri(idx[a], idx[c], idx[b], m, smooth=False, surf=SURF['hazard'])
    hb.build()
if TH['terrain'] in ('sea', 'quay'):
    sea = MB('Sea')
    E = 3000
    q = [sea.add(p) for p in ((cx - E, WATER_Y, cz - E), (cx + E, WATER_Y, cz - E), (cx + E, WATER_Y, cz + E), (cx - E, WATER_Y, cz + E))]
    sea.face((q[0], q[3], q[2], q[1]), HZ_MAT['water']())
    sea.build()
    x0, x1 = minx + MARGIN - 80, maxx - MARGIN + 80
    z0, z1 = minz + MARGIN - 80, maxz - MARGIN + 80
    a, b, c, d = (x0, WATER_Y, z0), (x0, WATER_Y, z1), (x1, WATER_Y, z1), (x1, WATER_Y, z0)
    col_tri(a, b, c, SURF['hazard'])
    col_tri(a, c, d, SURF['hazard'])

# ================================================================ 加速帶
boost = MB('Boost', uv=True)
for bk, b in enumerate(MD['boosts']):
    cnt = max(2, int(round(b['s1'] - b['s0'])) + 1)
    prev = None
    for k in range(cnt):
        s = b['s0'] + (b['s1'] - b['s0']) * k / (cnt - 1)
        a, u = MAIN.locate(s)
        bb = MAIN.nxt(a)
        hw = MAIN.lerp(MAIN.hw, a, u)
        o0, o1 = max(-hw + 0.2, b['d'] - b['w']), min(hw - 0.2, b['d'] + b['w'])
        row = []
        for o in (o0, o1):
            p = lerp3(MAIN.point(a, o, 0.02), MAIN.point(bb, o, 0.02), u)
            row.append(boost.add(p))
        v = (s - b['s0']) / (2 * b['w'])
        if prev is not None:
            (p0, p1, pv) = prev
            boost.quad(p0, p1, row[1], row[0], m_boost, uv=[(0, pv), (1, pv), (1, v), (0, v)], smooth=False, surf=SURF['boost'])
        prev = (row[0], row[1], v)
boost.build()

# ================================================================ 起終點：方格線＋門
line = MB('StartLine')
hw0 = MAIN.hw[0]
cols, rows = 12, 3
cw = 2 * hw0 / cols
for c in range(cols):
    for r in range(rows):
        m = m_chk_b if (c + r) % 2 == 0 else m_chk_w
        o0, o1 = -hw0 + c * cw, -hw0 + (c + 1) * cw
        a0, a1 = (r - rows / 2) * cw, (r + 1 - rows / 2) * cw
        q = []
        for o, al in ((o0, a0), (o1, a0), (o1, a1), (o0, a1)):
            p = MAIN.point(0, o, 0.03)
            q.append(line.add((p[0] + MAIN.T[0][0] * al, p[1], p[2] + MAIN.T[0][2] * al)))
        line.face(q, m)
line.build()
UPV = Vector((0, 1, 0))
T0v, R0v = Vector(MAIN.T[0]), Vector(MAIN.R[0])
gate_h = 7.5
gw = 2 * (MAIN.eo(0) + 1.2)
for side in (-1, 1):
    p = Vector(MAIN.point(0, side * (MAIN.eo(0) + 1.2))) + T0v * 3
    props.add(cylinder(0.6, gate_h + 1.5, 12), m_metal, M((p.x, p.y - 0.2, p.z)))
gc = Vector(MAIN.S[0]) + T0v * 3 + Vector((0, gate_h, 0))
gm = basis(R0v, UPV, -T0v, gc)
props.add(box(gw, 2.6, 0.8), m_banner, gm)
for k in range(28):
    xx = -gw / 2 + (k + 0.5) * gw / 28
    props.add(box(gw / 28, 0.45, 0.85), m_chk_b if k % 2 == 0 else m_chk_w, gm @ M((xx, 1.5, 0)))
    props.add(box(gw / 28, 0.45, 0.85), m_chk_w if k % 2 == 0 else m_chk_b, gm @ M((xx, -1.5, 0)))

# ================================================================ 地圖邊界牆（車開得到的範圍外緣）
RS = 4.0
rx0 = min(p[0] for p in allp) - OPEN_REACH - 30
rz0 = min(p[2] for p in allp) - OPEN_REACH - 30
rnx = int((max(p[0] for p in allp) + OPEN_REACH + 30 - rx0) / RS) + 2
rnz = int((max(p[2] for p in allp) + OPEN_REACH + 30 - rz0) / RS) + 2
RV = []
for iz in range(rnz):
    RV.append([region(rx0 + ix * RS, rz0 + iz * RS)[0] for ix in range(rnx)])


def rv_at(x, z):
    ix, iz = int(round((x - rx0) / RS)), int(round((z - rz0) / RS))
    if 0 <= ix < rnx and 0 <= iz < rnz:
        return RV[iz][ix]
    return 1e9


def ms_segments():
    segs = []
    for iz in range(rnz - 1):
        for ix in range(rnx - 1):
            v = (RV[iz][ix], RV[iz][ix + 1], RV[iz + 1][ix + 1], RV[iz + 1][ix])
            c = sum(1 << k for k in range(4) if v[k] <= 0)
            if c == 0 or c == 15:
                continue
            P = ((rx0 + ix * RS, rz0 + iz * RS), (rx0 + (ix + 1) * RS, rz0 + iz * RS),
                 (rx0 + (ix + 1) * RS, rz0 + (iz + 1) * RS), (rx0 + ix * RS, rz0 + (iz + 1) * RS))
            pts = {}
            for e, (a, b) in enumerate(((0, 1), (1, 2), (2, 3), (3, 0))):
                if (v[a] <= 0) != (v[b] <= 0):
                    t = v[a] / (v[a] - v[b])
                    pts[e] = (P[a][0] + (P[b][0] - P[a][0]) * t, P[a][1] + (P[b][1] - P[a][1]) * t)
            if len(pts) == 2:
                e0, e1 = sorted(pts)
                segs.append((pts[e0], pts[e1]))
            elif c == 5:
                segs += [(pts[0], pts[1]), (pts[2], pts[3])]
            elif c == 10:
                segs += [(pts[3], pts[0]), (pts[1], pts[2])]
    return segs


fence = MB('Fence')
fpost = Builder('FencePost')
fpost.add(box(0.18, 1.5, 0.18, base=True), m_fence)
fpost_me = fpost.mesh()
fposts = Instances('FencePosts')
bsegs = ms_segments()
nfence = 0
for k, (p, q) in enumerate(bsegs):
    y0, y1 = gh(*p), gh(*q)
    mx, mz = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    r, open_, ny = region(mx, mz)
    col_wall((p[0], 0, p[1]), (q[0], 0, q[1]), min(y0, y1) - 3.0, max(y0, y1, ny) + 5.0)
    if open_:  # 開放路肩外面那一圈畫成木圍欄；護牆後面的邊界只留碰撞
        a = fence.add((p[0], y0 + 0.35, p[1]))
        b = fence.add((q[0], y1 + 0.35, q[1]))
        c = fence.add((q[0], y1 + 1.05, q[1]))
        d = fence.add((p[0], y0 + 1.05, p[1]))
        fence.face((a, b, c, d), m_fence)
        nfence += 1
        if k % 2 == 0:
            fposts.put(fpost_me, (p[0], y0 - 0.2, p[1]))
fence.build()
log(f'boundary segments {len(bsegs)} (fence {nfence})')

# ================================================================ 場景物件（佔位：之後換 CC0 素材）


def free_spot(x, z, clear=3.0):
    if rv_at(x, z) < clear:
        return False
    if minx + 20 > x or x > maxx - 20 or minz + 20 > z or z > maxz - 20:
        return False
    for hz in HAZ:
        if sdist(x, z, hz['poly']) < 6:
            return False
    y = gh(x, z)
    if GAPS:
        pr = MAIN.project(x, z, 3, False)
        if pr and pr[4] in GAP_OF and pr[0] < MAIN.eo_max(pr[4]) + 32:
            return False  # 跳台深谷裡面、旁邊
    if TH['terrain'] in ('sea', 'quay') and y < WATER_Y + 0.25:
        return False
    # 橋、隧道、路面附近（region 只算到路肩外 1.5m）
    for st in STRIPS:
        pr = st.project(x, z, 1, False)
        if pr and pr[0] < st.eo_max(pr[4]) + 5:
            return False
    return True


def variant(name, parts):
    b = Builder(name)
    for prim, m, mtx in parts:
        b.add(prim, m, mtx)
    return b.mesh()


def scatter(count, put, tries=20000, near=None, clear=3.0):
    placed = t = 0
    while placed < count and t < tries:
        t += 1
        if near:
            st = MAIN
            i = random.randrange(st.n)
            p = st.point(i, random.choice((-1, 1)) * (st.eo(i) + random.uniform(*near)))
            x, z = p[0], p[2]
        else:
            x, z = random.uniform(minx + 40, maxx - 40), random.uniform(minz + 40, maxz - 40)
            if noise.noise(Vector((x * 0.02, z * 0.02, 5.0))) < -0.15 and random.random() < 0.7:
                continue
        if not free_spot(x, z, clear):
            continue
        if put(x, z):
            placed += 1
    return placed


tc = TH['trees']
m_trunk = mat('Trunk', '#8d5a3b')
m_leaf = [mat(f'Leaf{k + 1}', c) for k, c in enumerate(tc[:3])]
m_pine = mat('Pine', tc[3])
m_rock = mat('Rock', '#a3a7ad')
rounds = [variant(f'TreeRound{k}', [(cylinder(0.35, 2.6, 7), m_trunk, M((0, -0.1, 0))),
                                    (sphere(2.0, 9, 6), lm, M((0, 3.6, 0), scale=(1, 0.95, 1))),
                                    (sphere(1.4, 8, 5), lm, M((0.9, 4.6, -0.4)))]) for k, lm in enumerate(m_leaf)]
pine = variant('TreePine', [(cylinder(0.3, 1.6, 6), m_trunk, M((0, -0.1, 0)))] +
               [(cone(r, h, 9), m_pine, M((0, yy, 0), rot=(0, k * 0.7, 0))) for k, (r, h, yy) in enumerate(((2.4, 3.2, 1.2), (1.9, 2.8, 2.6), (1.3, 2.4, 3.9)))])
trees = Instances('Trees')


def tree(x, z):
    me = random.choice(rounds) if random.random() < 0.6 else pine
    trees.put(me, (x, gh(x, z), z), yaw=random.uniform(0, 6.28), scale=random.uniform(0.8, 1.35))
    return True


log('trees', scatter(380, tree), '+ near', scatter(120, tree, near=(6, 30), tries=4000))
rock = variant('Rock', [(sphere(1.0, 7, 5, smooth=False), m_rock, None)])
ri = Instances('Rocks')


def rk(x, z):
    s = random.uniform(0.6, 2.2)
    ri.put(rock, (x, gh(x, z) + 0.2 * s, z), yaw=random.uniform(0, 6.28), scale=(1.3 * s, 0.8 * s, s))
    return True


scatter(60, rk)

# layout 指定的地標（佔位）
m_torii = mat('ToriiRed', '#d32f2f')
m_marker = mat('Marker', '#ffca28')
for pp in LAYOUT.get('props', []):
    s = MAIN.at_to_s(pp['at'])
    a, u = MAIN.locate(s)
    d = float(pp.get('d', 0))
    p = MAIN.pos_at_s(s, d)
    t = MAIN.T[a]
    yaw = fwd_yaw(t) + math.radians(float(pp.get('rot', 0)))
    if pp.get('kind') == 'torii':
        half = (MAIN.eo_max(a) + 1.2) if abs(d) < 1 else 3.5
        ym = basis(Vector(MAIN.R[a]), UPV, Vector((-t[0], 0, -t[2])), Vector((p[0], p[1], p[2])))
        for sd in (-1, 1):
            props.add(cylinder(0.45, 7.6, 12), m_torii, ym @ M((sd * half, -0.5, 0)))
        props.add(box(2 * half + 3.0, 0.6, 0.9), m_torii, ym @ M((0, 7.2, 0)))
        props.add(box(2 * half + 0.6, 0.4, 0.5), m_torii, ym @ M((0, 6.0, 0)))
    else:
        props.add(box(1.0, 4.0, 1.0, base=True), m_marker, M((p[0], p[1], p[2]), rot=(0, yaw, 0)))


def mountains(colors, count=16, hmin=140, hmax=300, y0=-10):
    ms = [mat(f'Mountain{k}', c) for k, c in enumerate(colors)]
    m_snow = mat('Snow', '#ffffff')
    for k in range(count):
        a = 2 * math.pi * k / count + random.uniform(-0.12, 0.12)
        rr = FAR + random.uniform(40, 260)
        x, z = cx + math.cos(a) * rr, cz + math.sin(a) * rr
        h = random.uniform(hmin, hmax)
        r = h * random.uniform(0.9, 1.4)
        jit = [random.uniform(0.8, 1.15) for _ in range(9)]
        props.add(cone(r, h, 9, jitter=jit), random.choice(ms), M((x, y0, z), rot=(0, random.random() * 6, 0)))
        if THEME in ('hills', 'snow'):
            props.add(cone(r * 0.33, h * 0.33, 9, jitter=jit), m_snow, M((x, y0 + h * 0.67 + 0.5, z)))


mountains(TH['mountains'])
props.build()

if not NIGHT:
    clouds = Builder('Clouds')
    m_c = mat('Cloud', '#ffe3f3' if THEME == 'candy' else '#ffffff', emit=0.25) if THEME != 'volcano' else mat('AshCloud', '#6d6266')
    for k in range(26):
        a = random.uniform(0, 2 * math.pi)
        rr = random.uniform(80, FAR + 200)
        x, z, y = cx + math.cos(a) * rr, cz + math.sin(a) * rr, random.uniform(95, 170)
        s = random.uniform(6, 14)
        for b in range(5):
            clouds.add(sphere(s * random.uniform(0.6, 1.0), 10, 6), m_c,
                       M((x + random.uniform(-1.6, 1.6) * s, y + random.uniform(0, 0.4) * s, z + random.uniform(-0.7, 0.7) * s), scale=(1, 0.65, 1)))
    clouds.build()

# ================================================================ 匯出
os.makedirs(os.path.join(ROOT, 'assets'), exist_ok=True)
glb = os.path.join(ROOT, 'assets', TRACK + '.glb')
export_glb(glb)


def r3(v):
    return round(v, 3)


path = {
    'id': TRACK,
    'name': LAYOUT.get('name', TRACK),
    'theme': THEME,
    'difficulty': LAYOUT.get('difficulty', 1),
    'laps': LAYOUT.get('laps', 3),
    'step': round(MAIN.step, 5),
    'length': round(MAIN.length, 3),
    'pts': [r3(c) for p in MAIN.S for c in p],
    'hw': [r3(v) for v in MAIN.hw],
    'bank': [round(v, 2) for v in MAIN.bank],
    'gap': [1 if g else 0 for g in MAIN.gap],
    'start': 0,
    'bounds': [round(minx, 1), round(minz, 1), round(maxx, 1), round(maxz, 1)],
    'shortcuts': [{'from': round(sc.from_s, 2), 'to': round(sc.to_s, 2), 'hw': sc.hw[0], 'surf': sc.surf,
                   'pts': [r3(c) for p in sc.S for c in p]} for sc in SCS],
}
with open(os.path.join(ROOT, 'assets', TRACK + '_path.json'), 'w', encoding='utf-8') as f:
    json.dump(path, f, ensure_ascii=False, separators=(',', ':'))


def b64(fmt, arr):
    return base64.b64encode(struct.pack('<%d%s' % (len(arr), fmt), *arr)).decode('ascii')


miny = min(COL_T[1::3]) if COL_T else -10
col = {
    'tris': b64('f', COL_T),
    'surf': base64.b64encode(bytes(COL_S)).decode('ascii'),
    'walls': b64('f', COL_W),
    'killY': math.floor(min(miny, min(p[1] for p in MAIN.S) - 20) - 5),
}
colp = os.path.join(ROOT, 'assets', TRACK + '_col.json')
with open(colp, 'w', encoding='utf-8') as f:
    json.dump(col, f, separators=(',', ':'))
cnt = {}
for s in COL_S:
    cnt[s] = cnt.get(s, 0) + 1
log(f'col: tris={len(COL_S)} {dict(sorted(cnt.items()))} walls={len(COL_W) // 6} killY={col["killY"]}')
log(f'wrote {glb} ({os.path.getsize(glb) // 1024} KB), col {os.path.getsize(colp) // 1024} KB')
