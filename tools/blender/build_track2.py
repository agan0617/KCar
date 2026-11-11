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
import re
import struct
import sys
import time
from mathutils import Matrix, Vector, noise

_SELF = os.path.dirname(os.path.abspath(__file__))
HERE = _SELF
if not os.path.exists(os.path.join(HERE, 'common.py')):  # 開發用副本（tmp_layout\）
    HERE = os.path.join(os.path.dirname(HERE), 'tools', 'blender')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))  # tools\：check_layout2
if _SELF != HERE:
    sys.path.insert(0, _SELF)  # 開發用副本旁邊若有 check_layout2.py 就用它
from common import (Builder, Instances, M, basis, box, cone, cylinder, export_glb, mat, reset_scene, sphere)  # noqa: E402
import check_layout2 as L2  # noqa: E402

# 參數：<repo> <賽道 id> [--out <輸出目錄>] [--theme <主題>]（後兩個是測試用：輸出到別處、換主題試撒）
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OPTS = {}
_pos = []
_k = 0
while _k < len(argv):
    if argv[_k].startswith('--') and _k + 1 < len(argv):
        OPTS[argv[_k][2:]] = argv[_k + 1]
        _k += 2
    else:
        _pos.append(argv[_k])
        _k += 1
ROOT = os.path.abspath(_pos[0] if _pos else '.')
TRACK = _pos[1] if len(_pos) > 1 else 'testbed'
OUTDIR = os.path.abspath(OPTS['out']) if 'out' in OPTS else os.path.join(ROOT, 'assets')
LAYOUT = L2.load_layout(TRACK, ROOT)
if not L2.is_v2(LAYOUT):
    raise SystemExit(f'[track2] {TRACK}_layout.json 不是 v2 格式（points 要是物件，見 TRACK_V2.md）')
THEME = OPTS.get('theme', LAYOUT.get('theme', 'hills'))
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
WALL_T = 0.7         # 護牆厚度
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


def corr_margin(x, z, reach=40.0):
    """離最近的路肩外緣多遠（橋、缺口不算：hazard 可以在它們底下）。"""
    m = 1e9
    for st in STRIPS:
        for j in st.near(x, z, reach):
            k = st.nxt(j)
            if k is None or not (st.drawn[j] and st.drawn[k]) or st.bridge[j] or st.bridge[k] or st.gap[j] or st.gap[k]:
                continue
            a, b = st.S[j], st.S[k]
            ex, ez = b[0] - a[0], b[2] - a[2]
            l2 = ex * ex + ez * ez or 1e-9
            u = max(0.0, min(1.0, ((x - a[0]) * ex + (z - a[2]) * ez) / l2))
            d = math.hypot(x - a[0] - ex * u, z - a[2] - ez * u) - max(st.eo_max(j), st.eo_max(k))
            m = min(m, d)
    return m


def hz_expand(poly, d):
    """外擴 d 公尺（水岸蓋到斜坡下）；靠近路的地方不外擴（離路肩外緣 6m 內維持 layout 原本的岸線）。"""
    out = []
    full = expand_poly(poly, d)
    for p, q in zip(poly, full):
        dd = d
        for _ in range(8):
            x, z = p[0] + (q[0] - p[0]) * dd / d, p[1] + (q[1] - p[1]) * dd / d
            if corr_margin(x, z) >= 6.0 or dd <= 0:
                break
            dd = max(0.0, dd - 1.0)
        out.append((p[0] + (q[0] - p[0]) * dd / d, p[1] + (q[1] - p[1]) * dd / d))
    return out


def hz_tris(poly):
    """多邊形三角化，壓到路面（路肩外緣內）的部分細分後丟掉。回傳 [((x,z),(x,z),(x,z))]。"""
    out = []

    def rec(a, b, c, depth):
        cxz = ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3)
        size = max(math.dist(a, b), math.dist(b, c), math.dist(c, a))
        m = min(corr_margin(*q, reach=size + 40) for q in (a, b, c, cxz))
        if m > 0.3 + 0.05:
            out.append((a, b, c))
            return
        if size < 1.6 or depth > 12:
            if corr_margin(*cxz) > 0.3:
                out.append((a, b, c))
            return
        ab, bc, ca = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), ((b[0] + c[0]) / 2, (b[1] + c[1]) / 2), ((c[0] + a[0]) / 2, (c[1] + a[1]) / 2)
        for t in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)):
            rec(*t, depth + 1)
    for i, j, k in triangulate(poly):
        rec(poly[i], poly[j], poly[k], 0)
    return out


HAZ = []
for hz in LAYOUT.get('hazards', []):
    poly = [(float(p[0]), float(p[1])) for p in hz['poly']]
    HAZ.append({'type': hz.get('type', 'water'), 'poly': poly, 'y': float(hz.get('y', -1.0)),
                'vis': hz_expand(poly, 6.0)})

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
        # 小島沿著賽道長：離路肩外緣 c 公尺開始沉進海裡，c 隨雜訊變化 → 自然的海岸線（不跟地圖矩形走）
        c = 30.0 + 14.0 * noise.noise(Vector((x * 0.009, z * 0.009, 7.0))) + 5.0 * noise.noise(Vector((x * 0.03, z * 0.03, 2.5)))
        return y + nz2 * 0.3 * k - smooth(c - 14, c + 16, emin) * 7.0
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
            # 路邊 1～7m 內不往下挖（車稍微出界不會一下子騰空掉進水裡）；水面延伸到路肩外 1m 為止
            keep = 1.0 - smooth(1.0, 7.0, corr_margin(x, z))
            h = floor + (h - floor) * max(smooth(0.0, 8.0, sd), keep)
    return h


def _closed_dist(st, side):
    """每個取樣點沿線到「這一側不開放」（有牆、橋、隧道、缺口）的最近距離。"""
    n = st.n
    closed = [st.drawn[i] and (st.gap[i] or st.bridge[i] or st.tunnel[i] or st.wall(i, side) != 'none') for i in range(n)]
    d = [0.0 if c else 1e9 for c in closed]
    order = list(range(2 * n)) if st.closed else list(range(n))
    for k in order:
        i, j = k % n, k % n - 1
        if j < 0 and not st.closed:
            continue
        d[i] = min(d[i], d[j % n] + st.step)
    for k in reversed(order):
        i, j = k % n, k % n + 1
        if j >= n and not st.closed:
            continue
        d[i] = min(d[i], d[j % n] + st.step)
    return d


CLOSED_D = {(st.name, side): _closed_dist(st, side) for st in STRIPS for side in (-1, 1)}


def region(x, z):
    """車開得到的範圍：r ≤ 0 在裡面。回傳 (r, 最近那條路是否為開放路肩, 最近那條路的高度)。
    開放路肩外 OPEN_REACH 公尺；快接到有牆段時 45 度斜收到護牆內面（不留開得進去、出不來的口袋）；
    有牆、橋、隧道那側貼著護牆外緣；缺口兩側留 1.5m。"""
    best = (1e9, False, 0.0)
    for st in STRIPS:
        pr = st.project(x, z, 4, False)
        if pr is None:
            continue
        d, o, a, u, bi = pr
        side = 1 if o >= 0 else -1
        eo = st.eo_max(bi)
        open_ = st.drawn[bi] and not st.gap[bi] and not st.bridge[bi] and not st.tunnel[bi] and st.wall(bi, side) == 'none'
        if open_:
            reach = eo + min(OPEN_REACH, CLOSED_D[(st.name, side)][bi])  # 45 度收到護牆內面（跟牆頭斜收同一條線）
        else:
            reach = eo + (1.5 if st.gap[bi] else WALL_T)
        r = d - reach
        if r < best[0]:
            best = (r, open_, st.S[bi][1])
    for hz in HAZ:  # hazard 整塊圈進來（邊界牆不會穿過熔岩池）
        r = sdist(x, z, hz['poly']) - 10.0
        if r < best[0]:
            best = (r, True, hz['y'])
    return best


BR_STRIPS = [st for st in STRIPS if any(st.bridge)]

# 隧道：每一段的沿線起訖、洞口；隧道上方的地形至少蓋到頂（外殼頂再上 0.7m），往兩側 1:1.7 斜下去像一座山
TUN_RUNS = []
_t = [MAIN.tunnel[i] and MAIN.seg_ok(i) for i in range(N)]
for _i in range(N):
    if _t[_i] and not _t[_i - 1]:
        _k = 0
        while _t[(_i + _k) % N] and _k < N:
            _k += 1
        TUN_RUNS.append({'i0': _i, 'i1': (_i + _k) % N, 's0': MAIN.s[_i], 'len': _k * MAIN.step})
TUN_ROOF = 4.2 + 3.2 + 0.8 + 0.7
PORTAL = 6.0     # 洞口前後幾公尺地形網格挖空（換成精細的補片＋擋土牆）


def tun_at(x, z):
    """(隧道段, 進隧道的沿線距離, 橫向距離, 外殼半寬, 路面高度)；不在隧道附近回 None。"""
    if not TUN_RUNS:
        return None
    pr = MAIN.project(x, z, 3, False)
    if pr is None:
        return None
    d, o, a, u, bi = pr
    s = MAIN.s[a] + u * MAIN.step
    for tr in TUN_RUNS:
        ds = (s - tr['s0'] + PORTAL * 2) % MAIN.length - PORTAL * 2
        if -PORTAL * 2 <= ds <= tr['len'] + PORTAL * 2:
            ii = min(max(bi, 0), N - 1)
            return tr, ds, d, MAIN.eo(ii) + 1.3 + 0.8, MAIN.surface_y(a, u, 0.0)
    return None


def tun_cover(x, z):
    """隧道頂上的地形高度下限；不在隧道段上方回 None。"""
    t = tun_at(x, z)
    if t is None:
        return None
    tr, ds, d, a, y = t
    if ds < 0 or ds > tr['len'] or d > a + 30:
        return None
    return y + TUN_ROOF - max(0.0, d - a) * 0.6


def tun_portal(x, z):
    """這一點在洞口前後 PORTAL 公尺、隧道寬度內（地形網格要挖空）。"""
    t = tun_at(x, z)
    if t is None:
        return False
    tr, ds, d, a, y = t
    return d <= a + 1.5 and (abs(ds) <= PORTAL or abs(ds - tr['len']) <= PORTAL)


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
m_wood = mat('Boardwalk', '#a8794e', rough=0.85)  # 木棧道（viaduct: "wood"）：路面、路肩、橋面板、木樁
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
        tc = tun_cover(x, z)
        if tc is not None:
            h = max(h, tc)
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
nhole = 0
for iz in range(gnz - 1):
    for ix in range(gnx - 1):
        a = iz * gnx + ix
        b, c, d = a + gnx, a + gnx + 1, a + 1
        inr = min(RG[iz][ix], RG[iz + 1][ix], RG[iz + 1][ix + 1], RG[iz][ix + 1]) <= 9.0
        for tri in ((a, b, c), (a, c, d)):
            if TUN_RUNS:
                gx = sum(terrain.v[q][0] for q in tri) / 3
                gz = sum(terrain.v[q][2] for q in tri) / 3
                if tun_portal(gx, gz):
                    nhole += 1
                    continue
            terrain.tri(*tri, m_ground, surf=TERRAIN_SURF if inr else None)
            ncol_terrain += 1 if inr else 0
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
        wood = getattr(st, 'viaduct', None) and st.viaduct[i] == 'wood'
        for c in range(2):
            u0, u1 = c * 0.5, (c + 1) * 0.5
            mb.quad(ri[c], ri[c + 1], rj[c + 1], rj[c], m_wood if wood else rmat, uv=[(u0, vi), (u1, vi), (u1, vj), (u0, vj)], surf=rsurf)
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
                em = (m_wood if wood else m_bridge) if br else EDGE_MAT.get(st.edge[i], m_ground)
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
m_ice = mat('Ice', '#bfe7ff', rough=0.1)
for sc in SCS:
    if sc.surf == 'ice':  # 冰面捷徑：畫面用 Ice、碰撞當路面（打滑交給 JS 依材質名稱判斷）
        strip_surfaces(sc, sc_mb, m_ice, SURF['road'])
    else:
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
    if st is not MAIN:  # 捷徑的牆離主線路肩外緣 6m 內不放（進出口留成喇叭口，牆頭再往外斜收）
        for k in (i, j):
            q = st.point(k, side * (st.eo(k) + 0.35))
            pr = MAIN.project(q[0], q[2], 3, False)
            if pr is not None and pr[0] < MAIN.eo(pr[4]) + 6.0:
                return None
    return w


FLARE = ((2.5, 2.5), (5.0, 5.0))  # 護牆末端往外 45 度斜收（跟地圖邊界的漏斗同一條線，不留楔形死角）：(沿線往前, 往外) 公尺


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
            if not full:  # 兩端：接開放路肩的那頭往外斜收（導引，不留直角斷頭），然後封口
                for ii, rev, prev_seg in ((segs[0], False, (segs[0] - 1) % st.n if st.closed else segs[0] - 1),
                                          (st.nxt(segs[-1]), True, st.nxt(segs[-1]))):
                    ends = [lambda k, ii=ii: wp(ii, k)]
                    flare = (prev_seg is not None and 0 <= prev_seg < st.n and st.drawn[prev_seg]
                             and wall_kind(st, prev_seg, side) is None and not st.gap[prev_seg]
                             and not st.bridge[prev_seg] and not st.tunnel[prev_seg])
                    if flare:
                        dirn = 1 if rev else -1
                        ow = st.eo(ii)
                        yb = st.plane_y(ii, side * ow)
                        t, r = st.T[ii], st.R[ii]
                        prev_in = st.point(ii, side * ow)
                        prev_k = None
                        for fi, (al, out) in enumerate(FLARE):
                            bx = prev_in0 = st.point(ii, side * (ow + out))
                            bx = (bx[0] + t[0] * dirn * al, yb, bx[2] + t[2] * dirn * al)

                            def fp(k, bx=bx, fi=fi):
                                px, py = prof[k]
                                return mb.V(key + ('flare', ii, fi, k), (bx[0] + r[0] * side * px, bx[1] + py, bx[2] + r[2] * side * px))
                            last = ends[-1]
                            nk2 = len(prof) if wk == 'rail' else len(prof) - 1
                            for k in range(nk2):
                                k2 = (k + 1) % len(prof)
                                a, b, c, d = last(k), last(k2), fp(k2), fp(k)
                                if (side < 0) != rev:
                                    a, b, c, d = b, a, d, c
                                mb.face((a, b, c, d), m_wall_top if wk == 'wall' and 0 < k < len(prof) - 2 else (m_wall_a if wk == 'wall' else m_rail))
                            col_wall(prev_in, bx, yb - 0.5, yb + (WALL_H if wk == 'wall' else RAIL_H))
                            prev_in = bx
                            ends.append(fp)
                    ring = [ends[-1](k) for k in range(len(prof))]
                    if (side < 0) != rev:
                        ring.reverse()
                    mb.face(ring, m_wall_top if wk == 'wall' else m_rail)
walls_mb.build()
rails_mb.build()
log(f'walls: {nwall} segments, rail posts {posts.count}')

# ================================================================ 橋：橋面板、橋墩
deck = MB('BridgeDeck')
m_bridge_c = m_bridge
npier = 0
PIERS = []  # (x, z, 半徑)：場景物件要避開
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
            m_bridge = m_wood if (getattr(st, 'viaduct', None) and st.viaduct[i] == 'wood') else m_bridge_c
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
        m_bridge = m_bridge_c
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
                if top - bot < 0.5:
                    continue
                cols.append((p, top, bot))
            yaw = fwd_yaw(st.T[ii])
            wood = getattr(st, 'viaduct', None) and st.viaduct[ii] == 'wood'
            for p, top, bot in cols:
                PIERS.append((p[0], p[2], 1.0))
                props.add(box(1.3, top - bot, 1.3, base=True) if not wood else cylinder(0.35, top - bot, 8),
                          m_wood if wood else m_pier, M((p[0], bot, p[2]), rot=(0, yaw, 0)))
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

# 隧道洞口：地形網格挖空的地方換成 2m 一格的補片（洞外貼原本的地形、洞內蓋到隧道頂），洞口立一面擋土牆
m_portal = mat('TunnelPortal', '#9a9488', rough=0.9)
tcov = MB('TunnelCover')
portal = MB('TunnelPortal')
for tr in TUN_RUNS:
    for ii, sp, outward in ((tr['i0'], tr['s0'], -1), (tr['i1'], tr['s0'] + tr['len'], 1)):
        a_in = MAIN.eo(ii) + 1.3
        a_out = a_in + 0.8
        wide = a_out + 2.0
        y0 = MAIN.S[ii][1]
        for zone in (outward, -outward):  # 洞外、洞內
            rows = []
            for k in range(0, int(PORTAL * 1.5 / 2) + 2):
                ss = sp + zone * k * 2.0
                row = []
                for m in range(-int(wide), int(wide) + 1, 2):
                    p = MAIN.pos_at_s(ss, float(m))
                    if zone == outward:
                        h, lower, emin = tinfo(p[0], p[2])
                        y = h - lower
                    else:
                        y = max(tinfo(p[0], p[2])[0], y0 + TUN_ROOF - max(0.0, abs(m) - a_out) * 0.6)
                    row.append(tcov.add((p[0], y, p[2])))
                rows.append(row)
            for k in range(len(rows) - 1):
                for m in range(len(rows[k]) - 1):
                    q = (rows[k][m], rows[k][m + 1], rows[k + 1][m + 1], rows[k + 1][m])
                    if (zone > 0) == (outward > 0):
                        q = (q[1], q[0], q[3], q[2])
                    tcov.quad(*q, m_ground, surf=TERRAIN_SURF if zone == outward else None)
        # 擋土牆：洞口外殼外緣到隧道頂，兩側延伸到補片外
        pro = []
        for k in range(1, 10):
            t = math.pi - math.pi * k / 10
            pro.append((a_out * math.cos(t), 4.2 + 4.0 * math.sin(t)))
        pro = [(-a_out, 4.2)] + pro + [(a_out, 4.2)]
        top = y0 + TUN_ROOF + 0.4
        r = MAIN.R[ii]
        c0 = MAIN.S[ii]

        def P(o, y):
            return (c0[0] + r[0] * o, y, c0[2] + r[2] * o)
        bot = y0 - 2.5
        for sd in (-1, 1):  # 兩側
            q = [portal.add(P(sd * a_out, bot)), portal.add(P(sd * (wide + 1.0), bot)), portal.add(P(sd * (wide + 1.0), top)), portal.add(P(sd * a_out, top))]
            portal.face(q, m_portal, smooth=False)
            col_wall(P(sd * a_out, 0), P(sd * (wide + 1.0), 0), bot, top)
        for k in range(len(pro) - 1):
            (o0, h0), (o1, h1) = pro[k], pro[k + 1]
            q = [portal.add(P(o0, y0 + h0)), portal.add(P(o1, y0 + h1)), portal.add(P(o1, top)), portal.add(P(o0, top))]
            portal.face(q, m_portal, smooth=False)
tcov.build(color_fn=cg_at)
portal.build()
if TUN_RUNS:
    log(f'tunnel cover: runs={len(TUN_RUNS)} terrain holes={nhole}')

# ================================================================ 跳台：缺口兩端的斷面、深谷的水
cliff = MB('Cliff')
pitw = MB('PitWater')
m_water = HZ_MAT['water']()
for g in GAPS:
    _pi = int(math.floor(MAIN.U[g['g0']])) % len(MD['pts'])
    g['fill'] = MD['pts'][_pi].get('gapFill') or ('lava' if THEME == 'volcano' else 'water')
for g in GAPS:
    m_fill = HZ_MAT.get(g['fill'], HZ_MAT['water'])()
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
        pitw.quad(wv(i, -ow_i), wv(i, ow_i), wv(j, ow_j), wv(j, -ow_j), m_fill, smooth=False, surf=SURF['hazard'])
    # 看不見的重生面：缺口正下方、比兩端路面低 3 公尺（掉下去碰到谷壁斜坡之前就先重生）
    ky = min(MAIN.S[g['lip']][1], MAIN.S[g['land']][1]) - 3.0
    for k in range(g['g0'] - 1, g['g0'] + g['count']):  # 起跳點 → 落地點
        i, j = k % N, (k + 1) % N
        oi, oj = MAIN.eo_max(i) + 3, MAIN.eo_max(j) + 3  # 只蓋缺口自己的路寬（兩側有邊界牆），免得蓋到旁邊別段較低的路
        a, b = MAIN.point(i, -oi), MAIN.point(i, oi)
        c, d = MAIN.point(j, oj), MAIN.point(j, -oj)
        a, b, c, d = [(p[0], ky, p[2]) for p in (a, b, c, d)]
        col_tri(a, b, c, SURF['hazard'])
        col_tri(a, c, d, SURF['hazard'])
cliff.build()
pitw.build()

# ================================================================ hazard（熔岩、水）
for k, hz in enumerate(HAZ):
    tris = hz_tris(hz['vis'])
    if TH['terrain'] in ('sea', 'quay') and hz['type'] == 'water' and abs(hz['y'] - WATER_Y) < 0.05:
        for pa, pb, pc in tris:  # 跟海面同高的 water：只留碰撞（畫面上就是海，免得兩層水面閃爍）
            col_tri((pa[0], hz['y'], pa[1]), (pc[0], hz['y'], pc[1]), (pb[0], hz['y'], pb[1]), SURF['hazard'])
        continue
    hb = MB(f'Hazard_{k}')
    m = HZ_MAT.get(hz['type'], HZ_MAT['water'])()
    for pa, pb, pc in tris:
        ia, ib, ic = (hb.add((q[0], hz['y'], q[1])) for q in (pa, pb, pc))
        if (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0]) > 0:
            ib, ic = ic, ib
        hb.tri(ia, ib, ic, m, smooth=False, surf=SURF['hazard'])
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
    BS = b['strip']  # 主線或捷徑
    cnt = max(2, int(round(b['s1'] - b['s0'])) + 1)
    prev = None
    for k in range(cnt):
        s = b['s0'] + (b['s1'] - b['s0']) * k / (cnt - 1)
        a, u = BS.locate(s)
        bb = BS.nxt(a)
        if bb is None:
            bb, u = a, 0.0
        hw = BS.lerp(BS.hw, a, u)
        o0, o1 = max(-hw + 0.2, b['d'] - b['w']), min(hw - 0.2, b['d'] + b['w'])
        row = []
        for o in (o0, o1):
            p = lerp3(BS.point(a, o, 0.02 + (0.03 if BS is not MAIN else 0.0)), BS.point(bb, o, 0.02 + (0.03 if BS is not MAIN else 0.0)), u)
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
if not os.path.exists(os.path.join(ROOT, 'assets_src', 'props', 'common.glb')):  # 沒有物件庫才用程序化的門
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

# ================================================================ 場景物件（assets_src/props 物件庫：<主題>.glb＋common.glb）
# 每件物件匯入一次，之後全部用共用 mesh 的實例（同一個父物件底下 → glTF EXT_mesh_gpu_instancing，mesh 只存一份）。
# 撒的區域：far＝地圖邊界外（遠景、天際線）、road＝護牆或路肩外（車到不了）、inside＝車開得到的範圍（開放路肩、過渡帶）。
# inside 只放低矮小物；樹、石頭、雪人這類放了就在 _col.json 的 walls 加一圈圍住底部的線段，車不會穿過去。


def free_spot(x, z, clear=3.0):
    """（無物件庫主題的佔位撒法用）"""
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


SEA = TH['terrain'] in ('sea', 'quay')
INST = {}
PSTAT = {}
NCOLP = [0]
OCC = {}
OCC_C = 8.0
PROP_SUBST = []
C_ = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))  # 遊戲座標 → Blender 座標


def L(name):
    """找物件：主題庫優先，再 common。"""
    return LIB.get(f'{THEME}:{name}') or LIB.get(f'common:{name}') or LIB.get(name)


def inst(e):
    k = e['key']
    if k not in INST:
        INST[k] = Instances('S_' + k.replace(':', '_'))
    return INST[k]


def put(e, x, y, z, yaw=0.0, scale=1.0):
    ob = inst(e).put(e['me'], (x, y, z), yaw=yaw, scale=scale)
    PSTAT[e['key']] = PSTAT.get(e['key'], 0) + 1
    return ob


def put_basis(e, origin, xa, ya, za, scale=(1.0, 1.0, 1.0)):
    ob = inst(e).put(e['me'], origin)
    mg = basis(Vector(xa), Vector(ya), Vector(za), Vector(origin)) @ Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    ob.matrix_basis = C_ @ mg @ C_.inverted()
    PSTAT[e['key']] = PSTAT.get(e['key'], 0) + 1
    return ob


def yaw_face(dx, dz):
    """讓物件的 +Z（正面）朝向 (dx, dz)。"""
    return math.atan2(dx, dz)


def loc2w(x, z, yaw, lx, lz):
    c, s = math.cos(yaw), math.sin(yaw)
    return x + lx * c + lz * s, z - lx * s + lz * c


def col_circle(x, z, r, y0, y1, n=8):
    pts = [(x + r * math.cos(2 * math.pi * k / n), 0.0, z + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    for k in range(n):
        col_wall(pts[k], pts[(k + 1) % n], y0, y1)
    NCOLP[0] += 1


def col_rect(x, z, hw_, hd, yaw, y0, y1):
    cs = [loc2w(x, z, yaw, a * hw_, b * hd) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for k in range(4):
        col_wall((cs[k][0], 0, cs[k][1]), (cs[(k + 1) % 4][0], 0, cs[(k + 1) % 4][1]), y0, y1)
    NCOLP[0] += 1


def occ_free(x, z, r):
    gx0, gz0 = int(math.floor(x / OCC_C)), int(math.floor(z / OCC_C))
    rr = int(math.ceil((r + 14) / OCC_C))
    for gx in range(gx0 - rr, gx0 + rr + 1):
        for gz in range(gz0 - rr, gz0 + rr + 1):
            for ox, oz, orad in OCC.get((gx, gz), ()):
                if (ox - x) ** 2 + (oz - z) ** 2 < (r + orad) ** 2:
                    return False
    return True


def occ_add(x, z, r):
    OCC.setdefault((int(math.floor(x / OCC_C)), int(math.floor(z / OCC_C))), []).append((x, z, min(r, 14.0)))


def track_margin(x, z, reach=40.0):
    """離最近的路肩外緣（含護牆厚度）、橋墩多遠；負的就是壓到了。"""
    m = 1e9
    for st in STRIPS:
        for j in st.near(x, z, reach):
            k = st.nxt(j)
            if k is None or not st.drawn[j]:
                continue
            a, b = st.S[j], st.S[k]
            ex, ez = b[0] - a[0], b[2] - a[2]
            l2 = ex * ex + ez * ez or 1e-9
            u = max(0.0, min(1.0, ((x - a[0]) * ex + (z - a[2]) * ez) / l2))
            d = math.hypot(x - a[0] - ex * u, z - a[2] - ez * u) - max(st.eo_max(j), st.eo_max(k)) - 0.8
            if d < m:
                m = d
    for px, pz, pr in PIERS:
        d = math.hypot(x - px, z - pz) - pr - 1.0
        if d < m:
            m = d
    return m


def behind_wall(x, z):
    """最近的那條路在這一側有護牆（或是橋），而且這個點在護牆外：車過不來。"""
    best = None
    for st in STRIPS:
        pr = st.project(x, z, 3, False)
        if pr and (best is None or pr[0] - st.eo_max(pr[4]) < best[0]):
            best = (pr[0] - st.eo_max(pr[4]), st, pr)
    if best is None:
        return False
    e, st, (d, o, a, u, bi) = best
    side = 1 if o >= 0 else -1
    return e >= 0.7 and (st.wall(bi, side) in ('wall', 'rail') or st.bridge[bi]) and not st.gap[bi]


def in_pit(x, z, r=0.0):
    if not GAPS:
        return False
    pr = MAIN.project(x, z, 3, False)
    return bool(pr and pr[4] in GAP_OF and pr[0] < MAIN.eo_max(pr[4]) + 32 + r)


def hz_margin(x, z):
    return min((sdist(x, z, hz['poly']) for hz in HAZ), default=1e9)


def spot_ok(x, z, r, zone, water=False, near_road=0.5):
    if not (minx + 8 < x < maxx - 8 and minz + 8 < z < maxz - 8):
        return False
    rv = rv_at(x, z)
    if zone == 'inside':
        if rv > -(r + 1.5):
            return False
    elif rv < r + 1.0 and not (rv > -2.0 and behind_wall(x, z)):
        return False
    tm = track_margin(x, z, r + 30)
    if tm < r + (5.0 if zone == 'inside' else near_road):
        return False
    if zone == 'road' and tm > 70:
        return False
    if not water and hz_margin(x, z) < r + 2:
        return False
    if in_pit(x, z, r):
        return False
    if SEA:
        y = gh(x, z)
        if (y > WATER_Y - 0.4) if water else (y < WATER_Y + 0.3):
            return False
    return occ_free(x, z, r)


def ground_y(x, z, w, d):
    if max(w, d) < 3.5:
        return gh(x, z)
    hs = [gh(x, z)] + [gh(x + a * w / 2, z + b * d / 2) for a in (-1, 1) for b in (-1, 1)]
    return min(hs) - 0.15


def fp_r(e, s):
    w, d, h = e['size']
    if e['cat'] == 'tree':
        return max(0.8, 0.28 * max(w, d) * s)
    if e['cat'] in ('building', 'landmark'):
        return 0.55 * max(w, d) * s
    if e['cat'] == 'trackside':
        return max(0.4, 0.5 * min(w, d) * s + 0.3)
    return max(0.4, 0.45 * max(w, d) * s)


def add_inside_col(e, x, y, z, s, yaw=0.0):
    """車開得到的地方放了物件：圍一圈碰撞。回傳是否需要（低矮小物不用）。"""
    w, d, h = (v * s for v in e['size'])
    if h <= 0.9 and e['cat'] not in ('building', 'landmark'):
        return
    if e['cat'] == 'tree':
        col_circle(x, z, min(0.8, max(0.35, 0.08 * max(w, d))), y - 1.0, y + h)
    elif e['cat'] in ('building', 'landmark'):
        col_rect(x, z, w / 2, d / 2, yaw, y - 1.0, y + h)
    else:
        col_circle(x, z, max(0.3, 0.38 * min(w, d)), y - 1.0, y + h)


def pick(pool, rng):
    tot = sum(w for _, w in pool)
    t = rng.uniform(0, tot)
    for e, w in pool:
        t -= w
        if t <= 0:
            return e
    return pool[-1][0]


def roadside_xy(rng, r, lo, hi, strip=None, zone='road'):
    """沿路邊挑一點。road：護牆外，開放路肩那側就從車開得到的範圍外面算起；inside：開放路肩外（範圍內）。"""
    st = strip or (MAIN if (not SCS or rng.random() < 0.85) else rng.choice(SCS))
    i = rng.randrange(st.n)
    side = rng.choice((-1, 1))
    o = st.eo(i) + 0.7 + r + rng.uniform(lo, hi)
    if zone == 'road' and st.wall(i, side) == 'none' and not st.bridge[i]:
        o += OPEN_REACH + 1.0
    p = st.point(i, side * o)
    return p[0], p[2], (-side * st.R[i][0], -side * st.R[i][2])


def scatter_pool(pool, count, zone, rng, lo=2.0, hi=40.0, scl=(0.85, 1.2), face=False, cluster=None, water=False,
                 sink=0.0, tries=30, y_fn=None, rmul=1.0):
    """pool：[(物件, 權重)]。回傳實際放了幾個。"""
    if not pool or count <= 0:
        return 0
    placed = t = 0
    while placed < count and t < count * tries:
        t += 1
        e = pick(pool, rng)
        s = rng.uniform(*scl)
        r = fp_r(e, s) * rmul
        if zone == 'far':
            x, z = rng.uniform(minx + 10, maxx - 10), rng.uniform(minz + 10, maxz - 10)
            fd = None
        else:
            x, z, fd = roadside_xy(rng, r, lo, hi, zone=zone)
        if cluster is not None and noise.noise(Vector((x * 0.02, z * 0.02, 5.0))) < cluster and rng.random() < 0.75:
            continue
        if not spot_ok(x, z, r, zone, water):
            continue
        w, d, h = (v * s for v in e['size'])
        y = y_fn(x, z) if y_fn else ground_y(x, z, w, d) - sink * h
        yaw = (yaw_face(*fd) + rng.uniform(-0.3, 0.3)) if (face and fd) else rng.uniform(0, 2 * math.pi)
        put(e, x, y, z, yaw, s)
        occ_add(x, z, r)
        if zone == 'inside':
            add_inside_col(e, x, y, z, s, yaw)
        placed += 1
    return placed


def place_auto(e, x, z, yaw, s=1.0, y=None, need_clear=True):
    """指定位置放一個；自動判斷在不在車開得到的範圍（在的話加碰撞）。"""
    r = fp_r(e, s)
    rv = rv_at(x, z)
    zone = 'inside' if rv < 0 else 'road'
    if need_clear == 'lite':  # 刻意貼著護牆外放的東西（燈籠、火盆）：只確認沒壓到路、hazard、別的物件
        if track_margin(x, z, 30) < 0.1 or hz_margin(x, z) < r or in_pit(x, z) or not occ_free(x, z, r * 0.5):
            return False
    elif need_clear and not spot_ok(x, z, r, 'inside' if zone == 'inside' else 'any'):
        return False
    w, d, h = (v * s for v in e['size'])
    if y is None:
        y = ground_y(x, z, w, d)
    put(e, x, y, z, yaw, s)
    occ_add(x, z, r)
    if zone == 'inside':
        add_inside_col(e, x, y, z, s, yaw)
    return True


def at_s(st, s, extra, side):
    """沿線距離 s、路肩外緣再往外 extra 公尺的位置，以及該處的切線、右手方向。"""
    a, u = st.locate(s)
    b = st.nxt(a)
    if b is None:
        b = a
    eo = st.eo(a) + (st.eo(b) - st.eo(a)) * u
    p = lerp3(st.point(a, side * (eo + extra)), st.point(b, side * (eo + extra)), u)
    return p, st.T[a], st.R[a], a, eo


def rect_clear(x, z, w, d, yaw, need_out=True):
    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1), (0, 1), (0, -1), (0, 0)):
        px, pz = loc2w(x, z, yaw, a * w / 2, b * d / 2)
        if track_margin(px, pz, 30) < 0.3:
            return False
        if need_out and rv_at(px, pz) < 0.5 and not behind_wall(px, pz):
            return False
        if hz_margin(px, pz) < 1.0 or in_pit(px, pz):
            return False
    return occ_free(x, z, 0.45 * min(w, d))


def walled(i, side):
    return MAIN.wall(i, side) in ('wall', 'rail') and not (MAIN.gap[i] or MAIN.bridge[i] or MAIN.tunnel[i])


def straight_spots(count, sep=300.0, avoid=()):
    cand = []
    for i in range(0, N, 3):
        s = MAIN.s[i]
        if s < 120 or s > MAIN.length - 60:
            continue
        if any(MAIN.gap[(i + k) % N] or MAIN.bridge[(i + k) % N] or MAIN.tunnel[(i + k) % N] for k in range(-10, 11)):
            continue
        cand.append((max(abs(MAIN.curv[(i + k) % N]) for k in range(-15, 16, 3)), i))
    cand.sort()
    out = []
    for c, i in cand:
        if c > 1 / 150 or len(out) >= count:
            break
        if all(min(abs(MAIN.s[i] - MAIN.s[j]), MAIN.length - abs(MAIN.s[i] - MAIN.s[j])) > sep for j in list(out) + list(avoid)):
            out.append(i)
    return out


def pillar_span(e):
    """跨路物件（拱門、大鳥居、門架）的柱子：(內緣, 外緣) 離中心的距離。"""
    if 'span' not in e:
        xs = [abs(v.co.x) for v in e['me'].vertices if v.co.z < 0.6]
        outer = max(xs) if xs else e['size'][0] / 2
        inner = min([x for x in xs if x > outer * 0.5] or [outer * 0.9])
        e['span'] = (inner, outer)
    return e['span']


def span_road(e, s, extra=0.8, max_sy=1.3):
    """在沿線距離 s 放一個跨過路面的物件，柱子放到路肩（護牆）外面。"""
    a, u = MAIN.locate(s)
    inner, outer = pillar_span(e)
    eo = max(MAIN.eo(a), MAIN.eo(MAIN.nxt(a)))
    sx = max(1.0, (eo + 0.7 + extra) / max(inner, 0.5))
    sy = min(sx, max_sy)
    p = MAIN.pos_at_s(s)
    t, r = MAIN.T[a], MAIN.R[a]
    pl = [(p[0] + r[0] * sd * (inner + outer) / 2 * sx, p[2] + r[2] * sd * (inner + outer) / 2 * sx) for sd in (-1, 1)]
    y = min([p[1]] + [gh(*q) for q in pl]) - 0.2
    put(e, p[0], y, p[2], yaw_face(-t[0], -t[2]), (sx, sy, 1.0))
    for q in pl:
        col_circle(q[0], q[1], (outer - inner) / 2 * sx + 0.25, y - 1.0, y + e['size'][2] * sy)
        occ_add(q[0], q[1], (outer - inner) / 2 * sx + 0.5)
    return sx


# ---------------------------------------------------------------- 物件庫載入
PROPDIR = os.path.join(ROOT, 'assets_src', 'props')
LIB = {}


def load_lib(key):
    gp, jp = os.path.join(PROPDIR, key + '.glb'), os.path.join(PROPDIR, key + '.json')
    if not (os.path.exists(gp) and os.path.exists(jp)):
        return 0
    with open(jp, encoding='utf-8') as f:
        info = json.load(f)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=gp)
    new = [o for o in bpy.data.objects if o not in before]
    byname = {re.sub(r'\.\d{3}$', '', o.name): o for o in new}
    n = 0
    for it in info['objects']:
        o = byname.get(it['name'])
        if o is None or o.type != 'MESH':
            continue
        me = o.data
        me.transform(o.matrix_world)
        me.name = f'{key}_{it["name"]}'
        e = {'me': me, 'info': it, 'key': f'{key}:{it["name"]}', 'name': it['name'], 'size': it['size'],
             'tris': it.get('tris', 500), 'cat': it.get('category', 'deco'), 'use': it.get('use', 'roadside'),
             'dens': it.get('density') or {}}
        LIB[e['key']] = e
        LIB.setdefault(it['name'], e)
        n += 1
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    return n


HAS_THEME_LIB = load_lib(THEME) > 0
HAS_COMMON = load_lib('common') > 0
log(f'prop library: theme {THEME} {"yes" if HAS_THEME_LIB else "no"}, common {"yes" if HAS_COMMON else "no"} ({len(LIB)} keys)')


def mirrored(e):
    """左右鏡像版（轉彎箭頭牌往左指）：複製 mesh、x 取負、翻面。"""
    k = e['key'] + '_L'
    if k not in LIB:
        me = e['me'].copy()
        me.name = e['me'].name + '_L'
        me.transform(Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)))
        me.flip_normals()
        LIB[k] = dict(e, me=me, key=k)
    return LIB[k]


# ---------------------------------------------------------------- 賽道設施（common）
def facilities(rng):
    if not HAS_COMMON:
        return
    # 起終點拱門（跨路）＋方格旗
    e = LIB['common:arch_start_a']
    sx = span_road(e, 1.0)
    inner, outer = pillar_span(e)
    for sd in (-1, 1):
        p, t, r, a, eo = at_s(MAIN, 6.0, (outer * sx) - eo_of(0) + 1.8, sd)
        place_auto(LIB['common:flag_checker_a'], p[0], p[2], yaw_face(-t[0], -t[2]), need_clear=False)
    # 看台（起跑直線一側）、維修區（另一側）
    side_st = 1 if sum(1 for k in range(-20, 10) if walled(k % N, 1)) >= sum(1 for k in range(-20, 10) if walled(k % N, -1)) else -1
    for side, key, n_, back in ((side_st, 'common:grandstand_a', 4, 1.5), (-side_st, 'common:pits_garage_a', 4, 2.0)):
        e = LIB[key]
        w, d, h = e['size']
        for push in range(0, 40, 4):
            ok = []
            for k in range(n_):
                s = -55.0 + k * (w + 0.05)
                p, t, r, a, eo = at_s(MAIN, s, back + push + d / 2, side)
                yaw = yaw_face(-side * r[0], -side * r[2])
                if not rect_clear(p[0], p[2], w, d, yaw):
                    break
                ok.append((p, yaw))
            if len(ok) == n_:
                for p, yaw in ok:
                    y = ground_y(p[0], p[2], w, d)
                    put(e, p[0], y, p[2], yaw)
                    occ_add(p[0], p[2], 0.55 * max(w, d))
                break
    # 加速帶：發光箭頭貼在加速帶上
    ba = LIB['common:boost_arrow_a']
    for b in MD['boosts']:
        BS = b['strip']
        sm = (b['s0'] + b['s1']) / 2
        a, u = BS.locate(sm)
        bb = BS.nxt(a)
        if bb is None:
            bb, u = a, 0.0
        lift = 0.06 + (0.03 if BS is not MAIN else 0.0)
        c = lerp3(BS.point(a, b['d'], lift), BS.point(bb, b['d'], lift), u)
        f0 = BS.pos_at_s(b['s0'], b['d'])
        f1 = BS.pos_at_s(b['s1'], b['d'])
        za = Vector((f1[0] - f0[0], f1[1] - f0[1], f1[2] - f0[2])).normalized()
        rr = Vector(lerp3(BS.point(a, 1.0), BS.point(bb, 1.0), u)) - Vector(lerp3(BS.point(a, 0.0), BS.point(bb, 0.0), u))
        xa = rr.normalized()
        ya = za.cross(xa).normalized()
        xa = ya.cross(za).normalized()
        put_basis(ba, c, xa, ya, za, (2 * b['w'] / ba['size'][0], 1.0, (b['s1'] - b['s0']) / ba['size'][1]))
    # 彎道：外側護牆前加輪胎牆（有碰撞）、護牆外放轉彎箭頭牌、少數彎道外放看台
    peaks = []
    for i in range(N):
        c = abs(MAIN.curv[i])
        if c > 1 / 55 and c >= abs(MAIN.curv[i - 1]) and c >= abs(MAIN.curv[(i + 1) % N]):
            if all(min(abs(i - j), N - abs(i - j)) > 30 for j in peaks):
                peaks.append(i)
    tw = LIB['common:tire_wall_a']
    sign = LIB['common:arrow_sign_a']
    ntw = nsign = nstand = 0
    for ci in peaks:
        side = -1 if MAIN.curv[ci] > 0 else 1  # 外側
        right_turn = MAIN.curv[ci] > 0
        if MAIN.wall(ci, side) == 'wall' and MAIN.run[ci] >= 1.6 and not MAIN.bridge[ci] and not MAIN.tunnel[ci]:
            for k in range(-2, 3):
                s = MAIN.s[ci] + k * 5.3
                a, u = MAIN.locate(s)
                if MAIN.wall(a, side) != 'wall' or MAIN.gap[a]:
                    continue
                p, t, r, a, eo = at_s(MAIN, s, -0.45, side)
                put(tw, p[0], MAIN.plane_y(a, side * (eo - 0.45)) - 0.05, p[2], fwd_yaw(t))
                q0 = at_s(MAIN, s - 2.6, -0.85, side)[0]
                q1 = at_s(MAIN, s + 2.6, -0.85, side)[0]
                yb = MAIN.plane_y(a, side * eo)
                col_wall(q0, q1, yb - 0.5, yb + 0.85)
                ntw += 1
        # 轉彎箭頭牌：彎頂前 30m、15m、彎頂，外側
        for back in (30.0, 15.0, 0.0):
            a0, _ = MAIN.locate(MAIN.s[ci] - back)
            p, t, r, a, eo = at_s(MAIN, MAIN.s[ci] - back, 2.6 if MAIN.wall(a0, side) != 'none' else 8.0, side)
            if MAIN.gap[a] or MAIN.bridge[a] or MAIN.tunnel[a]:
                continue
            e = sign if right_turn else mirrored(sign)
            # 牌面朝來車、箭頭指向彎的方向
            tt = MAIN.T[a]
            if place_auto(e, p[0], p[2], yaw_face(-tt[0], -tt[2]), need_clear=True):
                nsign += 1
        if nstand < 2 and walled(ci, side) and rng.random() < 0.6:
            e = LIB['common:grandstand_b']
            w, d, h = e['size']
            p, t, r, a, eo = at_s(MAIN, MAIN.s[ci], 2.5 + d / 2, side)
            yaw = yaw_face(-side * r[0], -side * r[2])
            if rect_clear(p[0], p[2], w, d, yaw):
                put(e, p[0], ground_y(p[0], p[2], w, d), p[2], yaw)
                occ_add(p[0], p[2], 0.55 * max(w, d))
                nstand += 1
    # 跨路拱門（直線上）：city 用高速公路門架、sakura 用大鳥居，其他用一般拱門
    spk = {'city': 'city:sign_highway_a', 'sakura': 'sakura:torii_large_a'}.get(THEME)
    spe = LIB.get(spk) if spk else None
    spe = spe or LIB['common:arch_a']
    for i in straight_spots(2, avoid=[0]):
        span_road(spe, MAIN.s[i])
    # 看板、旗塔、帳篷（護牆外）
    for key, n_ in (('common:billboard_a', 4), ('common:banner_tower_a', 4), ('common:tent_a', 3)):
        scatter_pool([(LIB[key], 1)], n_, 'road', rng, lo=0.8, hi=6, scl=(1, 1), face=True)
    if NIGHT and THEME != 'city':
        e = LIB['common:light_post_a']
        for side in (-1, 1):
            s = 10.0
            while s < MAIN.length - 10:
                p, t, r, a, eo = at_s(MAIN, s, 1.2, side)
                if walled(a, side):
                    place_auto(e, p[0], p[2], yaw_face(-side * r[0], -side * r[2]), need_clear='lite')
                s += 55.0
    log(f'facilities: corners={len(peaks)} tire walls={ntw} signs={nsign} corner stands={nstand}')


def eo_of(i):
    return MAIN.eo(i % N)


# ---------------------------------------------------------------- layout 的 props
KIND_MAP = {'torii': 'torii_a', 'torii_small': 'torii_small_a', 'torii_large': 'torii_large_a', 'lighthouse': 'lighthouse_a',
            'pagoda': 'pagoda_a', 'shrine': 'shrine_a', 'volcano': 'volcano_a', 'castle': 'pagoda_a', 'house': 'house_a',
            'cabin': 'cabin_a', 'bungalow': 'bungalow_a', 'dock': 'dock_a', 'grandstand': 'grandstand_a', 'arch': 'arch_a',
            'billboard': 'billboard_a', 'ice': 'ice_spikes_a', 'skyscraper': 'skyscraper_a', 'mountain': 'mountain_a',
            'sando_gate': 'torii_a', 'gate': 'torii_a', 'temple': 'shrine_a', 'lantern': 'lantern_stone_a', 'tower': 'pagoda_a'}
USED_LANDMARKS = set()


def resolve_kind(kind):
    for c in (KIND_MAP.get(kind), kind, kind + '_a'):
        if c and L(c):
            if not c.startswith(kind):
                PROP_SUBST.append(f'{kind}→{c}')
            return L(c)
    cands = sorted(k for k in LIB if k.split(':')[-1].startswith(kind))
    if cands:
        PROP_SUBST.append(f'{kind}→{LIB[cands[0]]["name"]}（前綴）')
        return LIB[cands[0]]
    return None


def layout_props():
    m_marker = mat('Marker', '#ffca28')
    for pp in LAYOUT.get('props', []):
        kind = pp.get('kind', '')
        s = MAIN.at_to_s(pp['at'])
        a, u = MAIN.locate(s)
        d = float(pp.get('d', 0))
        p = MAIN.pos_at_s(s, d)
        t = MAIN.T[a]
        rot = math.radians(float(pp.get('rot', 0)))
        if kind == 'torii' and abs(d) < 1.0 and L('torii_large_a'):
            span_road(L('torii_large_a'), s)  # d＝0 的鳥居跨過路面（一列就是千本鳥居隧道）
            USED_LANDMARKS.add('torii_large_a')
            continue
        # 落在捷徑路面上的鳥居（或任何 kind 加 "span": true）：跨過那條小路
        on_sc = None
        for sc in SCS:
            pr = sc.project(p[0], p[2], 2, False)
            if pr and sc.drawn[pr[4]] and pr[0] < sc.eo(pr[4]) + 2.0:  # 落在捷徑路面或路肩上：吸到捷徑中心線、跨過去
                on_sc = (sc, pr)
        if kind in ('torii', 'sando_gate', 'gate') and on_sc and L('torii_a'):
            sc, pr = on_sc
            e = L('torii_a')
            inner, outer = pillar_span(e)
            bi = pr[4]
            sx = max(1.0, (sc.eo(bi) + (WALL_T if sc.wall(bi, 1) != 'none' else 0.0) + 0.6) / max(inner, 0.5))
            tt = sc.T[bi]
            q = sc.S[bi]
            yaw = yaw_face(-tt[0], -tt[2])  # 跨捷徑：方向一律跟捷徑走（rot 不用）
            pl = [loc2w(q[0], q[2], yaw, sd * (inner + outer) / 2 * sx, 0.0) for sd in (-1, 1)]
            y = min([q[1]] + [gh(*c) for c in pl]) - 0.2
            put(e, q[0], y, q[2], yaw, (sx, min(sx, 1.3), 1.0))
            for c in pl:
                col_circle(c[0], c[1], (outer - inner) / 2 * sx + 0.25, y - 1.0, y + e['size'][2] * 1.3)
            USED_LANDMARKS.add('torii_a')
            continue
        if kind == 'castle' and L('house_b') and L('shrine_a'):
            # 物件庫沒有城：石垣（程序化）＋和風平房＋神社屋頂疊成天守的樣子
            yaw = yaw_face(-t[0], -t[2]) + rot
            gy = ground_y(p[0], p[2], 22, 22)
            props.add(cylinder(15.5, 7.0, 4, r2=12.5, smooth=False), mat('CastleStone', '#8c8a84', rough=1.0),
                      M((p[0], gy, p[2]), rot=(0, yaw + math.pi / 4, 0)))
            put(L('house_b'), p[0], gy + 7.0, p[2], yaw, 1.45)
            put(L('shrine_a'), p[0], gy + 7.0 + 6.7 * 1.45 - 1.0, p[2], yaw, 0.95)
            occ_add(p[0], p[2], 16)
            if rv_at(p[0], p[2]) < 18:
                col_circle(p[0], p[2], 15.5, gy - 1, gy + 7, n=8)
            PROP_SUBST.append('castle→石垣＋house_b＋shrine_a 組合')
            continue
        e = resolve_kind(kind)
        if e is None and kind == 'torii':  # 沒有物件庫：程序化鳥居
            m_torii = mat('ToriiRed', '#d32f2f')
            half = (MAIN.eo_max(a) + 1.2) if abs(d) < 1 else 3.5
            ym = basis(Vector(MAIN.R[a]), Vector((0, 1, 0)), Vector((-t[0], 0, -t[2])), Vector((p[0], p[1], p[2]))) @ M(rot=(0, rot, 0))
            for sd in (-1, 1):
                props.add(cylinder(0.45, 7.6, 12), m_torii, ym @ M((sd * half, -0.5, 0)))
            props.add(box(2 * half + 3.0, 0.6, 0.9), m_torii, ym @ M((0, 7.2, 0)))
            props.add(box(2 * half + 0.6, 0.4, 0.5), m_torii, ym @ M((0, 6.0, 0)))
            continue
        if e is None:
            PROP_SUBST.append(f'{kind}→（找不到，放標記柱）')
            props.add(box(1.0, 4.0, 1.0, base=True), m_marker, M((p[0], p[1], p[2]), rot=(0, fwd_yaw(t), 0)))
            continue
        USED_LANDMARKS.add(e['name'])
        w, dd, h = e['size']
        yaw = yaw_face(-t[0], -t[2]) + rot  # rot＝相對主線方向（度）；0＝正面朝來車
        if e['name'] == 'volcano_a':
            put(e, p[0], -10.0, p[2], yaw, 1.6)
            continue
        if track_margin(p[0], p[2], 40) < 0.5 * min(w, dd):
            log(f'  !! layout prop {kind} at={pp["at"]} 壓到路面（離路肩 {track_margin(p[0], p[2], 40):.1f}m）')
        y = ground_y(p[0], p[2], w, dd)
        put(e, p[0], y, p[2], yaw)
        occ_add(p[0], p[2], 0.55 * max(w, dd))
        if rv_at(p[0], p[2]) < 0.55 * max(w, dd):
            col_rect(p[0], p[2], w / 2, dd / 2, yaw, y - 1, y + h)


# ---------------------------------------------------------------- 主題：一般撒法（依 json 的 category／use／density）
SPECIAL = {
    'sakura': {'torii_small_a', 'torii_large_a', 'torii_a', 'shrine_a', 'pagoda_a', 'lantern_stone_a', 'house_a', 'house_b',
               'bamboo_a', 'bamboo_b', 'bridge_a'},
    'beach': {'lighthouse_a', 'dock_a', 'boat_a', 'buoy_a', 'cliff_a', 'parasol_a', 'parasol_b', 'lounger_a', 'lounger_b',
              'bungalow_a', 'lifeguard_a', 'tent_a'},
    'snow': {'cabin_a', 'lantern_a', 'snowman_a', 'snowman_b', 'sled_a', 'ice_spikes_a'},
    'volcano': {'volcano_a', 'mountain_a', 'mountain_b', 'cliff_a', 'rock_pillar_a', 'lava_rock_a', 'lava_rock_b', 'brazier_a'},
    'autumn': {'bridge_a'},
}
RATE = {'tree_road': 0.16, 'tree_far': 12.0, 'rock_road': 0.35, 'rock_far': 0.3, 'deco_ha': 0.12, 'deco_100': 0.5, 'inside': 1.0}


def theme_items():
    return [e for k, e in LIB.items() if k.startswith(THEME + ':') and not k.endswith('_L')]


def areas():
    a_road = MAIN.length * 2 * 40 / 1e4
    n_in = sum(1 for row in RV for v in row if v < 0)
    a_in = max(0.0, n_in * RS * RS / 1e4 - MAIN.length * 2 * (sum(MAIN.hw) / N + 4.5) / 1e4)
    a_far = max(1.0, (maxx - minx) * (maxz - minz) / 1e4 - a_road - n_in * RS * RS / 1e4)
    return a_road, a_far, a_in


def generic_nature(rng, skip=(), far_mul=1.0, road_mul=1.0):
    items = [e for e in theme_items() if e['name'] not in skip]
    a_road, a_far, a_in = areas()
    ph = lambda e: float(e['dens'].get('per_ha', 0))  # noqa: E731
    trees = [(e, ph(e)) for e in items if e['cat'] == 'tree' and e['use'] == 'roadside' and ph(e) > 0]
    ftrees = [(e, ph(e)) for e in items if e['cat'] == 'tree' and e['use'] == 'far' and ph(e) > 0]
    if not ftrees and trees:  # 沒有遠景專用樹：拿面數最少的三種
        ftrees = [(e, 1.0) for e, _ in sorted(trees, key=lambda t: t[0]['tris'])[:3]]
    rocks = [(e, ph(e)) for e in items if e['cat'] == 'rock' and e['use'] == 'roadside' and ph(e) > 0]
    frocks = [(e, ph(e)) for e in items if e['cat'] == 'rock' and e['use'] == 'far' and ph(e) > 0]
    deco = [(e, ph(e)) for e in items if e['cat'] == 'deco' and ph(e) > 0]
    deco100 = [(e, float(e['dens'].get('per_100m', 0))) for e in items if e['cat'] in ('deco', 'trackside') and e['use'] == 'roadside'
               and e['dens'].get('per_100m')]
    low = [(e, max(ph(e), 5.0)) for e in items if e['cat'] in ('deco', 'rock') and e['size'][2] <= 0.9 and max(e['size'][:2]) <= 3.5]
    # 數量：密度 × 面積 × 係數，再壓到面數預算內
    plan = [
        (trees, sum(w for _, w in trees) * a_road * RATE['tree_road'] * road_mul, 'road', dict(cluster=-0.35, lo=1.0, hi=38)),
        (ftrees, a_far * RATE['tree_far'] * far_mul, 'far', dict(cluster=0.0, scl=(1.0, 1.8))),
        (rocks, sum(w for _, w in rocks) * a_road * RATE['rock_road'], 'road', dict(lo=0.5, hi=30, sink=0.12)),
        (frocks, sum(w for _, w in frocks) * a_far * RATE['rock_far'], 'far', dict(sink=0.1, scl=(1.0, 2.0))),
        (deco, sum(w for _, w in deco) * a_road * RATE['deco_ha'], 'road', dict(lo=0.5, hi=25)),
        (deco100, sum(w for _, w in deco100) * MAIN.length / 100 * RATE['deco_100'], 'road', dict(lo=0.3, hi=10, face=True)),
        # 車開得到的範圍：稀疏的樹與石頭（有碰撞）、低矮小物（沒碰撞）
        (trees, a_in * 4, 'inside', dict(scl=(0.8, 1.1))),
        (rocks, a_in * 4, 'inside', dict(sink=0.12)),
        (low, a_in * 12, 'inside', {}),
    ]
    tris = sum(cnt * sum(e['tris'] * w for e, w in pool) / max(1e-6, sum(w for _, w in pool)) for pool, cnt, _, _ in plan if pool)
    k = min(1.0, NATURE_TRIS / max(tris, 1.0))
    out = []
    for pool, cnt, zone, kw in plan:
        out.append(scatter_pool(pool, int(round(cnt * k)), zone, rng, **kw))
    log(f'nature: planned tris {tris / 1e3:.0f}k x{k:.2f}; placed trees road/far/in={out[0]}/{out[1]}/{out[6]} '
        f'rocks={out[2]}+{out[3]}+{out[7]} deco={out[4]}+{out[5]} low-in={out[8]}')


def landmarks_roadside(rng, names, lo=12, hi=45):
    for nm in names:
        e = L(nm)
        if e is None or nm in USED_LANDMARKS:
            continue
        n_ = int(e['dens'].get('per_track', 1))
        scatter_pool([(e, 1)], n_, 'road', rng, lo=lo, hi=hi, scl=(1, 1), face=True, tries=200)


def buildings_generic(rng, skip=()):
    for e in theme_items():
        if e['cat'] != 'building' or e['name'] in skip or e['use'] == 'far':
            continue
        n_ = int(e['dens'].get('per_track', 0)) or int(round(float(e['dens'].get('per_100m', 0)) * MAIN.length / 100 * 0.5))
        scatter_pool([(e, 1)], min(n_, 12), 'road', rng, lo=3, hi=25, scl=(1, 1), face=True, tries=80)


def along_walls(e, spacing, extra, rng, sides=(-1, 1), yaw_mode='face', s0=8.0, jitter=0.0, scl=1.0):
    n_ = 0
    for side in sides:
        s = s0 + rng.uniform(0, spacing)
        while s < MAIN.length - 5:
            p, t, r, a, eo = at_s(MAIN, s, extra, side)
            if walled(a, side) and walled(MAIN.nxt(a), side):
                yaw = yaw_face(-side * r[0], -side * r[2]) if yaw_mode == 'face' else rng.uniform(0, 6.28)
                if place_auto(e, p[0], p[2], yaw, s=scl, need_clear='lite'):
                    n_ += 1
            s += spacing + rng.uniform(-jitter, jitter)
    return n_


def ring_far(names_scales, count, rng, r0=40, r1=260, y0=-10.0):
    """地圖外圈的大型遠景（山、火山群、海崖）。"""
    for k in range(count):
        nm, s0, s1 = names_scales[k % len(names_scales)]
        e = L(nm)
        if e is None:
            continue
        a = 2 * math.pi * k / count + rng.uniform(-0.15, 0.15)
        rr = FAR + rng.uniform(r0, r1)
        put(e, cx + math.cos(a) * rr, y0, cz + math.sin(a) * rr, rng.uniform(0, 6.28), rng.uniform(s0, s1))


def street_row(rng, pool, side, s0, s1, setback, gap=(0.4, 2.5), hs=(0.9, 1.5), deco=None):
    """沿護牆外排一列建築（正面朝路）。deco(e, x, y, z, yaw, w, d, h) 可加招牌、屋頂小物。"""
    s = s0
    n_ = 0
    while s < s1:
        e = pick(pool, rng)
        w, d, h = e['size']
        sy = rng.uniform(*hs)
        sc = s + w / 2
        p, t, r, a, eo = at_s(MAIN, sc, setback + d / 2, side)
        if walled(a, side):
            yaw = yaw_face(-side * r[0], -side * r[2])
            if rect_clear(p[0], p[2], w, d, yaw):
                y = ground_y(p[0], p[2], w, d) - 0.1
                put(e, p[0], y, p[2], yaw, (1.0, sy, 1.0))
                occ_add(p[0], p[2], 0.45 * min(w, d))
                if deco:
                    deco(e, p[0], y, p[2], yaw, w, d, h * sy)
                n_ += 1
        s += w + rng.uniform(*gap)
    return n_


def wall_runs(side, minlen=60.0):
    """這一側連續有護牆（不是橋、隧道、缺口）的路段：[(s0, s1)]。"""
    out = []
    cur = None
    for i in range(N):
        if walled(i, side):
            cur = [MAIN.s[i], MAIN.s[i]] if cur is None else [cur[0], MAIN.s[i]]
        elif cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return [(a, b) for a, b in out if b - a >= minlen]


def water_edges(spacing, off_lo, off_hi, rng):
    """水邊（water hazard 外圍）每隔 spacing 公尺一個點。"""
    pts = []
    for hz in HAZ:
        if hz['type'] != 'water':
            continue
        poly = hz['poly']
        ccw = poly_area(poly) > 0
        for k in range(len(poly)):
            a, b = poly[k], poly[(k + 1) % len(poly)]
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            nx, nz = ((b[1] - a[1]) / ln, -(b[0] - a[0]) / ln) if ccw else (-(b[1] - a[1]) / ln, (b[0] - a[0]) / ln)
            t = rng.uniform(0, spacing)
            while t < ln:
                o = rng.uniform(off_lo, off_hi)
                pts.append((a[0] + (b[0] - a[0]) * t / ln + nx * o, a[1] + (b[1] - a[1]) * t / ln + nz * o, nx, nz))
                t += spacing
    return pts


# ---------------------------------------------------------------- 主題專屬
def theme_sakura(rng):
    generic_nature(rng, SPECIAL['sakura'])
    # 竹林：一叢一叢
    bam = [(L('bamboo_a'), 1), (L('bamboo_b'), 1.5)]
    for k in range(10):
        x, z, fd = roadside_xy(rng, 4, 4, 35)
        if not spot_ok(x, z, 6, 'road'):
            continue
        for j in range(rng.randint(6, 11)):
            e = pick(bam, rng)
            px, pz = x + rng.uniform(-7, 7), z + rng.uniform(-7, 7)
            if spot_ok(px, pz, 1.2, 'road'):
                put(e, px, gh(px, pz), pz, rng.uniform(0, 6.28), rng.uniform(0.85, 1.2))
                occ_add(px, pz, 1.2)
    # 神社（前面一座鳥居、一對石燈籠）、五重塔
    if 'shrine_a' not in USED_LANDMARKS:
        e = L('shrine_a')
        for _ in range(300):
            x, z, fd = roadside_xy(rng, 8, 14, 40)
            yaw = yaw_face(*fd)
            w, d, h = e['size']
            fx, fz = loc2w(x, z, yaw, 0, d / 2 + 9)
            if spot_ok(x, z, 8, 'road') and rect_clear(fx, fz, 8, 1.5, yaw):
                put(e, x, ground_y(x, z, w, d), z, yaw)
                occ_add(x, z, 8)
                put(L('torii_a'), fx, gh(fx, fz), fz, yaw)
                occ_add(fx, fz, 4)
                for sd in (-1, 1):
                    lx, lz = loc2w(x, z, yaw, sd * 3.2, d / 2 + 4)
                    put(L('lantern_stone_a'), lx, gh(lx, lz), lz, yaw)
                break
    landmarks_roadside(rng, ['pagoda_a'], lo=20, hi=55)
    # 石燈籠：護牆外排成列
    for side in (-1, 1):
        for s0, s1 in wall_runs(side)[:2]:
            s = s0 + 5
            while s < min(s1, s0 + 160):
                p, t, r, a, eo = at_s(MAIN, s, 1.1, side)
                place_auto(L('lantern_stone_a'), p[0], p[2], yaw_face(-side * r[0], -side * r[2]), need_clear='lite')
                s += 16
    # 町家一排（各一段直線、正面朝路）
    houses = [(L('house_a'), 2), (L('house_b'), 1)]
    nh = 0
    for side in (1, -1):
        runs_ = wall_runs(side, 120)
        if runs_:
            s0, s1 = max(runs_, key=lambda t: t[1] - t[0])
            nh += street_row(rng, houses, side, s0 + 10, min(s1, s0 + 200), 3.0, gap=(1.5, 5.0), hs=(1, 1))
    # 千本鳥居（小）：護牆外一條參道
    tr = L('torii_small_a')
    for side in (-1, 1):
        runs_ = wall_runs(side, 80)
        if not runs_:
            continue
        s0, s1 = runs_[len(runs_) // 2]
        s = s0 + 10
        cnt = 0
        while s < s1 - 10 and cnt < 40:
            p, t, r, a, eo = at_s(MAIN, s, 6.0, side)
            yaw = yaw_face(t[0], t[2])
            if rect_clear(p[0], p[2], 3.7, 0.6, yaw):
                put(tr, p[0], gh(p[0], p[2]), p[2], yaw)
                occ_add(p[0], p[2], 0.8)
                cnt += 1
            s += 1.6
        if cnt:
            break
    # 河邊櫻花
    nriver = 0
    for x, z, nx, nz in water_edges(11, 3, 8, rng):
        e = pick([(L('sakura_a'), 2), (L('sakura_c'), 2), (L('sakura_b'), 1)], rng)
        if spot_ok(x, z, 2.5, 'road', water=True) or spot_ok(x, z, 2.5, 'inside', water=True):
            place_auto(e, x, z, rng.uniform(0, 6.28), need_clear=False)
            nriver += 1
    log(f'sakura: houses={nh} river sakura={nriver}')


def theme_beach(rng):
    generic_nature(rng, SPECIAL['beach'])
    # 碼頭：岸邊往海裡接 4 段
    def shore_points():
        pts = []
        for _ in range(4000):
            x, z = rng.uniform(minx + 30, maxx - 30), rng.uniform(minz + 30, maxz - 30)
            y = gh(x, z)
            if abs(y - WATER_Y) < 0.3 and track_margin(x, z, 40) > 14:
                gx = gh(x + 2, z) - gh(x - 2, z)
                gz = gh(x, z + 2) - gh(x, z - 2)
                ll = math.hypot(gx, gz)
                if ll > 0.05:
                    pts.append((x, z, -gx / ll, -gz / ll))
        return pts
    shore = shore_points() if SEA else [(x, z, -nx, -nz) for x, z, nx, nz in water_edges(20, 0, 0.5, rng)]
    rng.shuffle(shore)
    dk = L('dock_a')
    ndock = 0
    for x, z, dx, dz in shore:
        if ndock >= 2:
            break
        if not occ_free(x, z, 12):
            continue
        yaw = yaw_face(dx, dz)
        for k in range(5):
            px, pz = x + dx * (k * dk['size'][1] - 1.0), z + dz * (k * dk['size'][1] - 1.0)
            put(dk, px, WATER_Y + 1.0 - dk['size'][2], pz, yaw)
            if rv_at(px, pz) < 0:  # 碼頭在車開得到的海灘上：加碰撞
                col_rect(px, pz, dk['size'][0] / 2, dk['size'][1] / 2, yaw, WATER_Y - 2, WATER_Y + 1.5)
        occ_add(x + dx * 8, z + dz * 8, 10)
        ndock += 1
    # 船、浮標、海崖（水上）
    wy = lambda x, z: WATER_Y - 0.25  # noqa: E731
    scatter_pool([(L('boat_a'), 1)], 6, 'far', rng, water=True, y_fn=wy, scl=(1, 1))
    scatter_pool([(L('buoy_a'), 1)], 8, 'far', rng, water=True, y_fn=lambda x, z: WATER_Y - 1.0, scl=(1, 1))
    scatter_pool([(L('cliff_a'), 1)], 4, 'far', rng, water=True, y_fn=lambda x, z: gh(x, z) - 1.0, scl=(1.0, 1.6))
    # 高腳屋、救生員台、遮陽傘＋躺椅（沙灘上）
    # 開放的海灘多半都在車開得到的範圍裡：護牆外放不下的就放進範圍內（加碰撞）
    for nm, n_, lo, hi in (('bungalow_a', 6, 4, 30), ('lifeguard_a', 3, 6, 30), ('tent_a', 3, 2, 15)):
        got = scatter_pool([(L(nm), 1)], n_, 'road', rng, lo=lo, hi=hi, scl=(1, 1), face=True, tries=100)
        scatter_pool([(L(nm), 1)], n_ - got, 'inside', rng, lo=8, hi=30, scl=(1, 1), face=True, tries=100)
    # 沙灘上（車開得到的範圍）多撒椰子樹（樹幹有碰撞）
    a_road, a_far, a_in = areas()
    palms = [(L(n), 1) for n in ('palm_a', 'palm_b', 'palm_c', 'palm_d', 'palm_e') if L(n)]
    npalm = scatter_pool(palms, int(a_in * 7), 'inside', rng, scl=(0.85, 1.2), cluster=-0.3)
    scatter_pool([(L('plant_a'), 1), (L('plant_b'), 1), (L('rock_b'), 0.5)], int(a_in * 5), 'inside', rng)
    npar = 0
    for _ in range(2500):
        if npar >= 26:
            break
        x, z, fd = roadside_xy(rng, 3, 6, 30, zone='inside')
        inside = rv_at(x, z) < 0
        if not spot_ok(x, z, 3.0, 'inside' if inside else 'road'):
            continue
        yaw = rng.uniform(0, 6.28)
        put(pick([(L('parasol_a'), 1), (L('parasol_b'), 1)], rng), x, gh(x, z), z, yaw)
        if inside:
            col_circle(x, z, 0.3, gh(x, z) - 1, gh(x, z) + 2.6, n=6)
        for sd in (-1, 1):
            lx, lz = loc2w(x, z, yaw, sd * 1.0, 0.6)
            put(pick([(L('lounger_a'), 1), (L('lounger_b'), 1)], rng), lx, gh(lx, lz), lz, yaw)
        occ_add(x, z, 3.0)
        npar += 1
    scatter_pool([(L('lounger_a'), 1), (L('lounger_b'), 1)], 18, 'inside', rng)
    # 燈塔：layout 沒指定就放在岸邊
    if 'lighthouse_a' not in USED_LANDMARKS:
        e = L('lighthouse_a')
        for x, z, dx, dz in shore:
            if occ_free(x, z, 8) and track_margin(x, z, 40) > 20:
                yy = gh(x, z) - 0.3
                put(e, x, yy, z, rng.uniform(0, 6.28))
                occ_add(x, z, 8)
                if rv_at(x, z) < 6:
                    col_circle(x, z, 4.2, yy - 1, yy + 22)
                break
    log(f'beach: docks={ndock} parasol sets={npar} beach palms={npalm}')


def theme_snow(rng):
    generic_nature(rng, SPECIAL['snow'], far_mul=1.5)
    cab = L('cabin_a')
    n_ = 0
    for _ in range(400):
        if n_ >= 6:
            break
        x, z, fd = roadside_xy(rng, 5, 5, 28)
        yaw = yaw_face(*fd)
        if not spot_ok(x, z, 5.5, 'road'):
            continue
        w, d, h = cab['size']
        put(cab, x, ground_y(x, z, w, d), z, yaw)
        occ_add(x, z, 5.5)
        lx, lz = loc2w(x, z, yaw, w / 2 + 1.2, d / 2 + 0.8)
        put(L('lantern_a'), lx, gh(lx, lz), lz, yaw)
        if rng.random() < 0.6:
            sx_, sz_ = loc2w(x, z, yaw, -w / 2 - 1.5, d / 2 + 1.5)
            put(L('sled_a'), sx_, gh(sx_, sz_), sz_, rng.uniform(0, 6.28))
        n_ += 1
    snowmen = [(L('snowman_a'), 1), (L('snowman_b'), 1)]
    scatter_pool(snowmen, 6, 'inside', rng, scl=(1, 1.2))
    scatter_pool(snowmen, 5, 'road', rng, lo=1, hi=12, scl=(1, 1.2), face=True)
    scatter_pool([(L('sled_a'), 1)], 4, 'inside', rng, scl=(1, 1))
    scatter_pool([(L('ice_spikes_a'), 1)], 6, 'road', rng, lo=1, hi=20, scl=(0.8, 1.4))
    scatter_pool([(L('ice_spikes_a'), 1)], 2, 'inside', rng, scl=(0.7, 1.0))
    log(f'snow: cabins={n_}')


def theme_volcano(rng):
    generic_nature(rng, SPECIAL['volcano'])
    if 'volcano_a' not in USED_LANDMARKS:
        # 背景大火山：賽道範圍外、離中心最遠的那一側
        best = max(((math.cos(a), math.sin(a)) for a in [k * math.pi / 4 for k in range(8)]),
                   key=lambda d: min(math.hypot(p[0] - (cx + d[0] * (FAR + 150)), p[2] - (cz + d[1] * (FAR + 150))) for p in MAIN.S[::10]))
        put(L('volcano_a'), cx + best[0] * (FAR + 150), -12.0, cz + best[1] * (FAR + 150), rng.uniform(0, 6.28), 1.7)
    ring_far([('mountain_a', 2.0, 3.2), ('mountain_b', 2.0, 3.0)], 10, rng)
    scatter_pool([(L('rock_pillar_a'), 1)], int(areas()[1] * 0.6), 'far', rng, scl=(1.0, 2.2), sink=0.05)
    scatter_pool([(L('cliff_a'), 1)], 10, 'far', rng, scl=(1.2, 2.2), sink=0.1)
    # 熔岩池邊的熔岩石
    nl = 0
    for hz in HAZ:
        if hz['type'] != 'lava':
            continue
        poly = hz['poly']
        ccw = poly_area(poly) > 0
        for k in range(len(poly)):
            a, b = poly[k], poly[(k + 1) % len(poly)]
            ln = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
            nx, nz = ((b[1] - a[1]) / ln, -(b[0] - a[0]) / ln) if ccw else (-(b[1] - a[1]) / ln, (b[0] - a[0]) / ln)
            t = rng.uniform(0, 8)
            while t < ln:
                o = rng.uniform(1.5, 6)
                x, z = a[0] + (b[0] - a[0]) * t / ln + nx * o, a[1] + (b[1] - a[1]) * t / ln + nz * o
                e = L('lava_rock_a') if rng.random() < 0.5 else L('lava_rock_b')
                if track_margin(x, z, 30) > 3 and occ_free(x, z, 2):
                    put(e, x, gh(x, z) - 0.2, z, rng.uniform(0, 6.28), rng.uniform(0.8, 1.3))
                    occ_add(x, z, 2)
                    if rv_at(x, z) < 0:
                        add_inside_col(e, x, gh(x, z), z, 1.0)
                    nl += 1
                t += rng.uniform(6, 11)
    scatter_pool([(L('lava_rock_a'), 1), (L('lava_rock_b'), 1)], 30, 'road', rng, lo=1, hi=30, sink=0.15)
    nb = along_walls(L('brazier_a'), 45, 1.4, rng)
    log(f'volcano: lava rocks={nl} braziers={nb}')


def theme_city(rng):
    signs_h = [(L(n), 1) for n in ('sign_a', 'sign_b', 'sign_c', 'sign_small_a', 'sign_small_b')]
    roof = [(L('ac_a'), 3), (L('antenna_a'), 2), (L('tv_a'), 1)]
    nsg = [0]

    def deco(e, x, y, z, yaw, w, d, h):
        # 正面（朝路那面）掛霓虹招牌、側邊直式招牌、屋頂冷氣機／天線／電視牆
        for k in range(rng.randint(1, 3)):
            sg = pick(signs_h, rng)
            sw = sg['size'][0]
            if w < sw + 1:
                continue
            lx = rng.uniform(-w / 2 + sw / 2 + 0.4, w / 2 - sw / 2 - 0.4)
            px, pz = loc2w(x, z, yaw, lx, d / 2 + 0.12)
            put(sg, px, y + rng.uniform(3.0, max(3.5, min(h - 2.5, 12.0))), pz, yaw)
            nsg[0] += 1
        if rng.random() < 0.5:
            sd = rng.choice((-1, 1))
            px, pz = loc2w(x, z, yaw, sd * (w / 2 - 0.9), d / 2 + 0.6)
            put(L('sign_d'), px, y + rng.uniform(3.5, max(4.0, min(h - 5.0, 9.0))), pz, yaw + sd * math.pi / 2)
            nsg[0] += 1
        for k in range(rng.randint(1, 3)):
            ro = pick(roof, rng)
            px, pz = loc2w(x, z, yaw, rng.uniform(-w / 3, w / 3), rng.uniform(-d / 3, d / 3))
            put(ro, px, y + h, pz, yaw + rng.choice((0, math.pi / 2, math.pi)))
    pool = [(L(n), 1) for n in ('building_a', 'building_b', 'building_c', 'building_d', 'building_e')]
    lights = [L('light_street_a'), L('light_street_b')]
    nb = 0
    nl = 0
    for side in (-1, 1):
        for s0, s1 in wall_runs(side, 30):
            # 路燈（燈臂伸到路面上）
            s = s0 + 6
            while s < s1 - 3:
                p, t, r, a, eo = at_s(MAIN, s, 0.7, side)
                e = lights[(nl // 2) % 2]
                put(e, p[0], MAIN.plane_y(a, side * eo) - 0.3, p[2], yaw_face(-side * r[0], -side * r[2]))
                occ_add(p[0], p[2], 0.6)
                nl += 1
                s += 26
            nb += street_row(rng, pool, side, s0, s1, 2.2, gap=(0.3, 1.8), hs=(0.9, 1.7), deco=deco)
    # 遠景天際線：摩天樓＋低模樓群
    a_road, a_far, a_in = areas()
    sky = [(L(n), 1) for n in ('skyscraper_a', 'skyscraper_b', 'skyscraper_c', 'skyscraper_d')]
    bg = [(L(n), 1) for n in ('bg_a', 'bg_b', 'bg_c', 'bg_d')]
    n1 = scatter_pool(sky, int(a_far * 2.2), 'far', rng, scl=(0.9, 1.5), tries=20)
    n2 = scatter_pool(bg, int(a_far * 6), 'far', rng, scl=(1.0, 2.0), tries=20)
    # 護牆外的大樓之間偶爾一棟摩天樓（第二排）
    n3 = scatter_pool(sky, 25, 'road', rng, lo=14, hi=40, scl=(0.8, 1.3), face=True, tries=60)
    scatter_pool([(L('traffic_light_a'), 1)], 8, 'road', rng, lo=0.3, hi=2, scl=(1, 1), face=True)
    scatter_pool([(L('barrier_a'), 1), (L('cone_city_a'), 2)], 20, 'road', rng, lo=0.3, hi=4, scl=(1, 1))
    log(f'city: street buildings={nb} signs={nsg[0]} lights={nl} skyline={n1}+{n2} second row={n3}')


def theme_autumn(rng):
    generic_nature(rng, SPECIAL['autumn'])


NATURE_TRIS = 900_000  # 自然物件（樹、石、點綴）的面數上限


def scatter_placeholder():
    """沒有物件庫的主題：沿用 v1 的程序化樹、石頭。"""
    rnd = random.Random(42)

    def scatter(count, put_, tries=20000, near=None, clear=3.0):
        placed = t = 0
        while placed < count and t < tries:
            t += 1
            if near:
                i = rnd.randrange(MAIN.n)
                p = MAIN.point(i, rnd.choice((-1, 1)) * (MAIN.eo(i) + rnd.uniform(*near)))
                x, z = p[0], p[2]
            else:
                x, z = rnd.uniform(minx + 40, maxx - 40), rnd.uniform(minz + 40, maxz - 40)
                if noise.noise(Vector((x * 0.02, z * 0.02, 5.0))) < -0.15 and rnd.random() < 0.7:
                    continue
            if not free_spot(x, z, clear):
                continue
            if put_(x, z):
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
        trees.put(rnd.choice(rounds) if rnd.random() < 0.6 else pine, (x, gh(x, z), z), yaw=rnd.uniform(0, 6.28), scale=rnd.uniform(0.8, 1.35))
        return True
    log('placeholder trees', scatter(380, tree), '+ near', scatter(120, tree, near=(6, 30), tries=4000))
    rock = variant('Rock', [(sphere(1.0, 7, 5, smooth=False), m_rock, None)])
    ri = Instances('Rocks')

    def rk(x, z):
        s = rnd.uniform(0.6, 2.2)
        ri.put(rock, (x, gh(x, z) + 0.2 * s, z), yaw=rnd.uniform(0, 6.28), scale=(1.3 * s, 0.8 * s, s))
        return True
    scatter(60, rk)


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


RNG = random.Random(9173 + sum(map(ord, TRACK)))  # 固定種子：同一份 layout 重產結果一樣
layout_props()
facilities(RNG)
{'sakura': theme_sakura, 'beach': theme_beach, 'snow': theme_snow, 'volcano': theme_volcano,
 'city': theme_city, 'autumn': theme_autumn}.get(THEME if HAS_THEME_LIB else None, lambda rng: scatter_placeholder())(RNG)
if THEME != 'volcano' or not HAS_THEME_LIB:
    mountains(TH['mountains'])
props.build()
ptris = sum(PSTAT[k] * LIB[k]['tris'] for k in PSTAT)
log(f'props: {sum(PSTAT.values())} instances of {len(PSTAT)} kinds, ~{ptris / 1e3:.0f}k tris, prop collisions={NCOLP[0]}'
    + (f', layout subst: {PROP_SUBST}' if PROP_SUBST else ''))

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
os.makedirs(OUTDIR, exist_ok=True)
glb = os.path.join(OUTDIR, TRACK + '.glb')
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
with open(os.path.join(OUTDIR, TRACK + '_path.json'), 'w', encoding='utf-8') as f:
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
colp = os.path.join(OUTDIR, TRACK + '_col.json')
with open(colp, 'w', encoding='utf-8') as f:
    json.dump(col, f, separators=(',', ':'))
cnt = {}
for s in COL_S:
    cnt[s] = cnt.get(s, 0) + 1
log(f'col: tris={len(COL_S)} {dict(sorted(cnt.items()))} walls={len(COL_W) // 6} killY={col["killY"]}')
log(f'wrote {glb} ({os.path.getsize(glb) // 1024} KB), col {os.path.getsize(colp) // 1024} KB')
