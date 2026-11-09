"""產生賽道模型：路面、路緣石、護牆、地形、湖、起終點門、看台、場景物件。

用法（在 repo 根目錄）：
  <Blender>\\blender.exe -b --factory-startup -P tools\\blender\\build_track.py -- . track1
讀 tools\\blender\\<track>_layout.json，輸出 assets\\<track>.glb 與 assets\\<track>_path.json
（遊戲用的中心線取樣，跟模型同一份資料，物理與畫面才對得上）。
"""
import bpy
import json
import math
import os
import random
import sys
from mathutils import Vector, noise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (B, Builder, Instances, M, basis, box, cone, cylinder, export_glb, mat, reset_scene, sphere, torus)  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ROOT = os.path.abspath(argv[0] if argv else '.')
TRACK = argv[1] if len(argv) > 1 else 'track1'
LAYOUT = json.load(open(os.path.join(ROOT, 'tools', 'blender', TRACK + '_layout.json'), encoding='utf-8'))

HW = LAYOUT['halfWidth']
CURB = LAYOUT['curb']
WALL = LAYOUT['wall']
WALL_T = 0.7
WALL_H = 1.0
STEP = 2.0
random.seed(617)

reset_scene()

# ================================================================ 中心線
P = [Vector((p[0], p[2], p[1])) for p in LAYOUT['points']]  # 遊戲座標 (x, 高度, z)
n = len(P)


def catmull(p0, p1, p2, p3, t, alpha=0.5):
    def tj(ti, a, b):
        return ti + max((b - a).length, 1e-4) ** alpha
    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)
    tt = t1 + (t2 - t1) * t
    a1 = p0 * ((t1 - tt) / (t1 - t0)) + p1 * ((tt - t0) / (t1 - t0))
    a2 = p1 * ((t2 - tt) / (t2 - t1)) + p2 * ((tt - t1) / (t2 - t1))
    a3 = p2 * ((t3 - tt) / (t3 - t2)) + p3 * ((tt - t2) / (t3 - t2))
    b1 = a1 * ((t2 - tt) / (t2 - t0)) + a2 * ((tt - t0) / (t2 - t0))
    b2 = a2 * ((t3 - tt) / (t3 - t1)) + a3 * ((tt - t1) / (t3 - t1))
    return b1 * ((t2 - tt) / (t2 - t1)) + b2 * ((tt - t1) / (t2 - t1))


dense = []
for i in range(n):
    p0, p1, p2, p3 = P[(i - 1) % n], P[i], P[(i + 1) % n], P[(i + 2) % n]
    for k in range(80):
        dense.append(catmull(p0, p1, p2, p3, k / 80.0))
dense.append(dense[0].copy())
cum = [0.0]
for i in range(1, len(dense)):
    cum.append(cum[-1] + (dense[i] - dense[i - 1]).length)
LENGTH = cum[-1]
N = int(round(LENGTH / STEP))
STEP = LENGTH / N
S = []
j = 0
for i in range(N):
    d = i * STEP
    while cum[j + 1] < d:
        j += 1
    t = (d - cum[j]) / max(cum[j + 1] - cum[j], 1e-9)
    S.append(dense[j].lerp(dense[j + 1], t))

T, R = [], []
for i in range(N):
    t = S[(i + 1) % N] - S[i - 1]
    t.y = 0
    t.normalize()
    T.append(t)
    R.append(Vector((-t.z, 0.0, t.x)))  # 往前看時的右手邊

# 曲率（正＝右彎）
CURV = []
for i in range(N):
    a, b = T[i - 1], T[(i + 1) % N]
    ang = math.atan2(a.x * b.z - a.z * b.x, a.dot(b))
    CURV.append(ang / (2 * STEP))
min_r = min(1 / max(abs(c), 1e-6) for c in CURV)

# 自交檢查：沿線距離 > 80m 的兩點，水平距離要夠
min_gap = 1e9
for i in range(0, N, 2):
    for k in range(0, N, 2):
        dd = abs(i - k)
        dd = min(dd, N - dd)
        if dd * STEP < 80:
            continue
        g = math.hypot(S[i].x - S[k].x, S[i].z - S[k].z)
        min_gap = min(min_gap, g)
print(f'[track] length={LENGTH:.1f}m samples={N} minRadius={min_r:.1f}m minGap={min_gap:.1f}m')
for i in range(N):
    if 1 / max(abs(CURV[i]), 1e-6) < 22 and abs(CURV[i]) >= abs(CURV[i - 1]) and abs(CURV[i]) >= abs(CURV[(i + 1) % N]):
        print(f'[track]   TIGHT s={i * STEP:.0f}m at ({S[i].x:.0f},{S[i].z:.0f}) R={1 / abs(CURV[i]):.1f}m')

# ---------------------------------------------------------------- 取樣點空間索引
CELL = 25.0
grid = {}
for i, p in enumerate(S):
    grid.setdefault((int(math.floor(p.x / CELL)), int(math.floor(p.z / CELL))), []).append(i)


def nearest(x, z, reach=3):
    """回傳 (水平距離, 該處路面高度, 取樣索引)；找不到（太遠）回 (1e9, None, -1)。"""
    cx, cz = int(math.floor(x / CELL)), int(math.floor(z / CELL))
    best, bi = 1e18, -1
    for gx in range(cx - reach, cx + reach + 1):
        for gz in range(cz - reach, cz + reach + 1):
            for i in grid.get((gx, gz), ()):
                dx, dz = S[i].x - x, S[i].z - z
                d2 = dx * dx + dz * dz
                if d2 < best:
                    best, bi = d2, i
    if bi < 0:
        return 1e9, None, -1
    # 投影到前後兩段，內插高度
    bd, bh = math.sqrt(best), S[bi].y
    for a, b in ((S[bi - 1], S[bi]), (S[bi], S[(bi + 1) % N])):
        ex, ez = b.x - a.x, b.z - a.z
        l2 = ex * ex + ez * ez
        u = max(0.0, min(1.0, ((x - a.x) * ex + (z - a.z) * ez) / l2))
        px, pz = a.x + ex * u, a.z + ez * u
        d = math.hypot(x - px, z - pz)
        if d < bd:
            bd, bh = d, a.y + (b.y - a.y) * u
    return bd, bh, bi


LAKE = LAYOUT.get('lake')


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


minx = min(p.x for p in S) - 230
maxx = max(p.x for p in S) + 230
minz = min(p.z for p in S) - 230
maxz = max(p.z for p in S) + 230


def ground(x, z):
    d, h, _ = nearest(x, z)
    if h is None:
        h = 0.0
    base = h - 0.12
    k = smooth(WALL + 2.0, WALL + 45.0, d)
    hills = (noise.noise(Vector((x * 0.011, z * 0.011, 0.3))) * 0.5 + 0.5) * 16.0
    hills += noise.noise(Vector((x * 0.05, z * 0.05, 1.7))) * 1.5
    y = base + k * max(0.0, hills)
    # 地圖邊緣圍一圈高丘，擋住地形盡頭
    ex = min(x - minx, maxx - x, z - minz, maxz - z)
    y += (1 - smooth(0, 120, ex)) * 55.0
    if LAKE:
        r = math.hypot(x - LAKE[0], z - LAKE[1])
        if r < LAKE[2] + 12:
            dip = smooth(LAKE[2] + 12, LAKE[2] - 6, r) * 2.6
            y = min(y, base) - dip
    return y


# ================================================================ 材質
m_road = mat('Road', '#5b6170', rough=0.9)
m_grass = mat('Grass', '#6cc24a', rough=1.0)
m_curb_r = mat('CurbRed', '#e53935')
m_curb_w = mat('CurbWhite', '#f4f4f4')
m_wall_a = mat('WallBlue', '#1e88e5')
m_wall_b = mat('WallWhite', '#fafafa')
m_wall_top = mat('WallTop', '#ffd54f')
m_chk_b = mat('CheckBlack', '#202020')
m_chk_w = mat('CheckWhite', '#ffffff')
m_water = mat('Water', '#3fb6f5', rough=0.2)
m_trunk = mat('Trunk', '#8d5a3b')
m_leaf = [mat('Leaf1', '#43a047'), mat('Leaf2', '#7cc95a'), mat('Leaf3', '#2e8b3e')]
m_pine = mat('Pine', '#2f7d55')
m_rock = mat('Rock', '#a3a7ad')
m_flower = [mat('FlowerRed', '#ff5a5f'), mat('FlowerYellow', '#ffd23f'), mat('FlowerPink', '#ff8fd0'), mat('FlowerWhite', '#ffffff')]
m_tire = mat('Tire', '#262626', rough=0.95)
m_sign = mat('SignYellow', '#ffd600')
m_arrow = mat('ArrowRed', '#e53935')
m_concrete = mat('Concrete', '#d5dbe0')
m_roof = [mat('RoofRed', '#e53935'), mat('RoofYellow', '#fdd835'), mat('RoofBlue', '#1e88e5')]
m_people = [mat(f'Fan{i}', c) for i, c in enumerate(['#e53935', '#1e88e5', '#fdd835', '#43a047', '#ff7043', '#ab47bc', '#ffffff'])]
m_skin = mat('Skin', '#f2c6a0')
m_metal = mat('Metal', '#b0bec5', rough=0.35, metal=0.6)
m_banner = mat('Banner', '#1a3fa0')
m_text = mat('BannerText', '#ffffff', emit=0.3)
m_mtn = [mat('Mountain1', '#6f9a86'), mat('Mountain2', '#86a3bd'), mat('Mountain3', '#7c8fa8')]
m_snow = mat('Snow', '#ffffff')
m_cloud = mat('Cloud', '#ffffff', emit=0.25)
m_balloon = [mat('BalloonA', '#ff5252'), mat('BalloonB', '#ffca28'), mat('BalloonC', '#26c6da'), mat('BalloonD', '#7e57c2')]
m_basket = mat('Basket', '#a1724e')
m_mill = mat('MillWhite', '#f5f0e6')
m_mill_roof = mat('MillRoof', '#c62828')
m_wood = mat('Wood', '#b07a4a')
m_flag = [mat('FlagRed', '#ff3b30'), mat('FlagYellow', '#ffcc00'), mat('FlagGreen', '#34c759'), mat('FlagBlue', '#007aff')]

# ================================================================ 路面、路緣石、護牆
road = Builder('Road')
CROSS = [-HW, -HW / 2, 0.0, HW / 2, HW]


def at(i, off, dy=0.0):
    i %= N
    p = S[i] + R[i] * off
    return Vector((p.x, p.y + dy, p.z))


for i in range(N):
    for c in range(len(CROSS) - 1):
        o0, o1 = CROSS[c], CROSS[c + 1]
        v0, v1 = i * STEP / 8.0, (i + 1) * STEP / 8.0
        u0, u1 = (o0 + HW) / (2 * HW), (o1 + HW) / (2 * HW)
        road.quad(at(i, o0), at(i + 1, o0), at(i + 1, o1), at(i, o1), m_road,
                  uv=[(u0, v0), (u0, v1), (u1, v1), (u1, v0)], smooth=True)
road.weld = True  # 共用頂點＋平滑法線：上下坡的光影是連續的，檔案也小
road.build()

curbs = Builder('Curbs')
for i in range(N):
    m = m_curb_r if (i // 1) % 2 == 0 else m_curb_w
    for side in (-1, 1):
        a0, a1 = side * HW, side * (HW + CURB)
        curbs.quad(at(i, a0, 0.02), at(i + 1, a0, 0.02), at(i + 1, a1, 0.1), at(i, a1, 0.1), m)
        curbs.quad(at(i, a1, 0.1), at(i + 1, a1, 0.1), at(i + 1, a1, -0.15), at(i, a1, -0.15), m)
curbs.build()

walls = Builder('Walls')
for i in range(N):
    m = m_wall_a if (i // 2) % 2 == 0 else m_wall_b
    for side in (-1, 1):
        # 內彎側曲率半徑小於牆距時跳過（避免牆自己打結）
        if CURV[i] * side > 0 and 1 / max(abs(CURV[i]), 1e-6) < WALL + 2:
            continue
        a, b = side * (WALL - WALL_T / 2), side * (WALL + WALL_T / 2)
        walls.quad(at(i, a, -0.2), at(i + 1, a, -0.2), at(i + 1, a, WALL_H), at(i, a, WALL_H), m)
        walls.quad(at(i, b, WALL_H), at(i + 1, b, WALL_H), at(i + 1, b, -0.2), at(i, b, -0.2), m)
        walls.quad(at(i, a, WALL_H), at(i + 1, a, WALL_H), at(i + 1, b, WALL_H), at(i, b, WALL_H), m_wall_top)
walls.build()

# 起終點格子線
line = Builder('StartLine')
cols, rows, cw = 12, 3, 2 * HW / 12
for c in range(cols):
    for r in range(rows):
        m = m_chk_b if (c + r) % 2 == 0 else m_chk_w
        o0, o1 = -HW + c * cw, -HW + (c + 1) * cw
        a0, a1 = (r - rows / 2) * cw, (r + 1 - rows / 2) * cw
        q = [S[0] + R[0] * o + T[0] * a + Vector((0, 0.03, 0)) for o, a in ((o0, a0), (o0, a1), (o1, a1), (o1, a0))]
        line.quad(*q, m)
line.build()

# ================================================================ 地形
GS = 6.0
nx = int((maxx - minx) / GS) + 1
nz = int((maxz - minz) / GS) + 1
H = [[ground(minx + ix * GS, minz + iz * GS) for ix in range(nx)] for iz in range(nz)]
# 地形用共用頂點的網格（每格各自四個頂點的話檔案會大好幾倍）；UV 在 three.js 端用世界座標算，不存
terrain = Builder('Terrain')
terrain.verts = [(minx + ix * GS, H[iz][ix], minz + iz * GS) for iz in range(nz) for ix in range(nx)]
mi = terrain._mi(m_grass)
for iz in range(nz - 1):
    for ix in range(nx - 1):
        a = iz * nx + ix
        terrain.faces.append((a, a + nx, a + nx + 1, a + 1))
        terrain.fmat.append(mi)
        terrain.fsmooth.append(True)
        terrain.fuv.append(None)
terrain.build()


def gh(x, z):
    """地形網格上的高度（雙線性內插，跟畫面一致）。"""
    fx = (x - minx) / GS
    fz = (z - minz) / GS
    ix, iz = int(fx), int(fz)
    ix = max(0, min(nx - 2, ix))
    iz = max(0, min(nz - 2, iz))
    tx, tz = fx - ix, fz - iz
    a = H[iz][ix] * (1 - tx) + H[iz][ix + 1] * tx
    b = H[iz + 1][ix] * (1 - tx) + H[iz + 1][ix + 1] * tx
    return a * (1 - tz) + b * tz


if LAKE:
    water = Builder('Water')
    seg = 40
    c = Vector((LAKE[0], -0.55, LAKE[1]))
    for k in range(seg):
        a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        r = LAKE[2] + 8
        water.quad(c, c + Vector((r * math.cos(a1), 0, r * math.sin(a1))), c + Vector((r * math.cos(a0), 0, r * math.sin(a0))), c, m_water)
    water.build()

# ================================================================ 場景物件
props = Builder('Props')


def free_spot(x, z, clear):
    d, _, _ = nearest(x, z, reach=4)
    if d < clear:
        return False
    if LAKE and math.hypot(x - LAKE[0], z - LAKE[1]) < LAKE[2] + 6:
        return False
    return True


def variant(name, parts):
    b = Builder(name)
    for prim, m, mtx in parts:
        b.add(prim, m, mtx)
    return b.mesh()


# 每種造型做一個 mesh，擺放時共用（GPU instancing）
V_ROUND = [variant(f'TreeRound{k}', [(cylinder(0.35, 2.6, 7), m_trunk, M((0, -0.1, 0))),
                                     (sphere(2.0, 9, 6), lm, M((0, 3.6, 0), scale=(1, 0.95, 1))),
                                     (sphere(1.4, 8, 5), lm, M((0.9, 4.6, -0.4)))]) for k, lm in enumerate(m_leaf)]
V_PINE = variant('TreePine', [(cylinder(0.3, 1.6, 6), m_trunk, M((0, -0.1, 0)))] +
                 [(cone(r, h, 9), m_pine, M((0, yy, 0), rot=(0, k * 0.7, 0))) for k, (r, h, yy) in enumerate(((2.4, 3.2, 1.2), (1.9, 2.8, 2.6), (1.3, 2.4, 3.9)))])
V_BUSH = [variant(f'Bush{k}', [(sphere(0.9, 8, 5), lm, M((dx, 0.5, dz))) for dx, dz in ((-0.7, 0.2), (0.6, 0.5), (0.1, -0.7))]) for k, lm in enumerate(m_leaf)]
I_TREE = Instances('Trees')


def tree(x, z, s=1.0):
    y = gh(x, z)
    kind = random.random()
    me = random.choice(V_ROUND) if kind < 0.55 else V_PINE if kind < 0.85 else random.choice(V_BUSH)
    I_TREE.put(me, (x, y, z), yaw=random.uniform(0, 6.28), scale=s)


placed = 0
tries = 0
while placed < 420 and tries < 20000:
    tries += 1
    x, z = random.uniform(minx + 40, maxx - 40), random.uniform(minz + 40, maxz - 40)
    # 成群：一半的樹長在噪聲高的地方
    if noise.noise(Vector((x * 0.02, z * 0.02, 5.0))) < -0.15 and random.random() < 0.7:
        continue
    if not free_spot(x, z, WALL + 5):
        continue
    tree(x, z, random.uniform(0.8, 1.35))
    placed += 1
print(f'[track] trees={placed}')

# 花叢：貼著護牆外側
_fl = random.Random(3)
V_FLOWER = []
for k, fm in enumerate(m_flower):
    parts = []
    for f in range(6):
        fx, fz = _fl.uniform(-1.6, 1.6), _fl.uniform(-1.6, 1.6)
        parts.append((sphere(0.28, 6, 4), fm, M((fx, 0.32, fz))))
        parts.append((sphere(0.4, 6, 3), m_leaf[1], M((fx, 0.08, fz), scale=(1, 0.45, 1))))
    V_FLOWER.append(variant(f'Flowers{k}', parts))
V_ROCK = variant('Rock', [(sphere(1.0, 7, 5, smooth=False), m_rock, None)])
I_FLOWER = Instances('Flowers')
I_ROCK = Instances('Rocks')
for k in range(160):
    i = random.randrange(N)
    side = random.choice((-1, 1))
    off = side * random.uniform(WALL + 1.5, WALL + 6)
    p = at(i, off)
    if not free_spot(p.x, p.z, WALL + 1.2):
        continue
    I_FLOWER.put(random.choice(V_FLOWER), (p.x, gh(p.x, p.z), p.z), yaw=random.uniform(0, 6.28), scale=random.uniform(0.8, 1.2))

# 石頭
for k in range(60):
    x, z = random.uniform(minx + 30, maxx - 30), random.uniform(minz + 30, maxz - 30)
    if not free_spot(x, z, WALL + 4):
        continue
    s = random.uniform(0.6, 2.2)
    I_ROCK.put(V_ROCK, (x, gh(x, z) + 0.2 * s, z), yaw=random.uniform(0, 6.28), scale=(1.3 * s, 0.8 * s, s))

# 彎道外側的輪胎牆、箭頭牌
corner_peaks = []
for i in range(N):
    c = abs(CURV[i])
    if c > 1 / 45 and c >= abs(CURV[i - 1]) and c >= abs(CURV[(i + 1) % N]):
        if all(min(abs(i - j), N - abs(i - j)) > 25 for j in corner_peaks):
            corner_peaks.append(i)
print(f'[track] corners={len(corner_peaks)}')
V_TIRE = variant('TireStack', [(cylinder(0.5, 0.32, 10), m_tire, M((0, h * 0.33, 0))) for h in range(3)])
I_TIRE = Instances('Tires')
for ci in corner_peaks:
    print(f'[track]   corner s={ci * STEP:.0f}m at ({S[ci].x:.0f},{S[ci].z:.0f}) R={1 / abs(CURV[ci]):.1f}m {"right" if CURV[ci] > 0 else "left"}')
for ci in corner_peaks:
    side = -1 if CURV[ci] > 0 else 1  # 外側
    for k in range(-10, 11, 2):
        i = (ci + k) % N
        p = at(i, side * (WALL + 1.3))
        I_TIRE.put(V_TIRE, (p.x, p.y - 0.15, p.z), yaw=random.uniform(0, 6.28))
    # 箭頭牌：一排，面向賽道，箭頭指向彎的方向
    for k in range(-6, 7, 3):
        i = (ci + k) % N
        o = at(i, side * (WALL + 0.9), 0.0)
        inward = R[i] * (-side)
        fwd = T[i]
        mtx = basis(fwd, Vector((0, 1, 0)), inward, o)
        # 保持右手座標（x=前進方向, y=上, z=朝賽道）；左右側不同時把 x 反過來，箭頭跟著反
        if fwd.cross(Vector((0, 1, 0))).dot(inward) < 0:
            mtx = basis(-fwd, Vector((0, 1, 0)), inward, o)
            sgn = -1
        else:
            sgn = 1
        props.add(box(0.12, 2.0, 0.12, base=True), m_metal, mtx @ M((-0.7, -0.2, 0)))
        props.add(box(0.12, 2.0, 0.12, base=True), m_metal, mtx @ M((0.7, -0.2, 0)))
        props.add(box(2.0, 1.2, 0.12), m_sign, mtx @ M((0, 2.2, 0.08)))
        for yy in (0.22, -0.22):
            props.add(box(0.75, 0.2, 0.06), m_arrow, mtx @ M((-0.05 * sgn, 2.2 + yy, 0.16), rot=(0, 0, -sgn * math.copysign(0.62, yy))))

# 起終點門與看台
p0, t0, r0 = S[0], T[0], R[0]
gate_h = 7.5
for side in (-1, 1):
    base = p0 + r0 * side * (WALL + 0.9) + t0 * 3
    props.add(cylinder(0.6, gate_h + 1.5, 12), m_metal, M((base.x, base.y - 0.2, base.z)))
    props.add(sphere(0.9, 10, 6), m_flag[0], M((base.x, base.y + gate_h + 1.6, base.z)))
gc = p0 + t0 * 3 + Vector((0, gate_h, 0))
gm = basis(r0, Vector((0, 1, 0)), -t0, gc)
props.add(box(2 * WALL + 1.8, 2.6, 0.8), m_banner, gm)
for k in range(28):  # 上緣格子
    xx = -(WALL + 0.9) + (k + 0.5) * (2 * WALL + 1.8) / 28
    props.add(box((2 * WALL + 1.8) / 28, 0.45, 0.85), m_chk_b if k % 2 == 0 else m_chk_w, gm @ M((xx, 1.5, 0)))
    props.add(box((2 * WALL + 1.8) / 28, 0.45, 0.85), m_chk_w if k % 2 == 0 else m_chk_b, gm @ M((xx, -1.5, 0)))


def text_prim(body, size):
    cu = bpy.data.curves.new('txt', 'FONT')
    cu.body = body
    cu.size = size
    cu.extrude = 0.06
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    ob = bpy.data.objects.new('txt', cu)
    bpy.context.scene.collection.objects.link(ob)
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    v = [tuple(x.co) for x in me.vertices]
    f = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob)
    return v, f, False


# 文字的局部座標：x 往右、y 往上、z 朝讀者；gm 的 z 正好朝向開過來的車
props.add(text_prim('KCAR', 1.9), m_text, gm @ M((0, -0.05, 0.42)))
props.add(text_prim('KCAR', 1.9), m_text, gm @ M((0, -0.05, -0.42), rot=(0, math.pi, 0)))

# 看台：起跑直線右手邊
for k in range(-18, 19):
    i = k % N
    for tier in range(6):
        off = WALL + 4 + tier * 1.4
        q = at(i, off)
        props.add(box(STEP + 0.05, 0.9 + tier * 0.75, 1.45, base=True), m_concrete,
                  basis(T[i], Vector((0, 1, 0)), T[i].cross(Vector((0, 1, 0))), q) @ M((0, -0.3, 0)))
        if random.random() < 0.8:
            pm = random.choice(m_people)
            top = q.y - 0.3 + 0.9 + tier * 0.75
            jx = random.uniform(-0.5, 0.5)
            pp = q + T[i] * jx
            props.add(cylinder(0.28, 0.75, 6), pm, M((pp.x, top, pp.z)))
            props.add(sphere(0.24, 7, 5), m_skin, M((pp.x, top + 0.95, pp.z)))
    if k % 6 == 0:
        q = at(i, WALL + 4 + 6 * 1.4 + 0.5)
        props.add(cylinder(0.12, 9.5, 6), m_metal, M((q.x, q.y - 0.3, q.z)))
roof_m = basis(T[0], Vector((0, 1, 0)), T[0].cross(Vector((0, 1, 0))), at(0, WALL + 4 + 3.5 * 1.4) + Vector((0, 9.3, 0)))
props.add(box(STEP * 37 + 2, 0.4, 11, base=True), m_roof[0], roof_m @ M(rot=(0.12, 0, 0)))

# 旗子沿著直線
for i in range(0, N, 9):
    if abs(CURV[i]) > 1 / 120:
        continue
    for side in (-1, 1):
        q = at(i, side * (WALL + 0.2))
        props.add(cylinder(0.06, 4.2, 5), m_metal, M((q.x, q.y + WALL_H - 0.1, q.z)))
        fm = m_flag[(i // 9 + (side > 0)) % 4]
        fb = basis(T[i], Vector((0, 1, 0)), T[i].cross(Vector((0, 1, 0))), q + Vector((0, WALL_H + 3.6, 0)) + T[i] * 0.55)
        props.add(box(1.1, 0.7, 0.04), fm, fb)

# 遠山
cx, cz = (minx + maxx) / 2, (minz + maxz) / 2
far = max(maxx - minx, maxz - minz) / 2 + 160
for k in range(16):
    a = 2 * math.pi * k / 16 + random.uniform(-0.12, 0.12)
    rr = far + random.uniform(40, 260)
    x, z = cx + math.cos(a) * rr, cz + math.sin(a) * rr
    h = random.uniform(140, 300)
    r = h * random.uniform(0.9, 1.4)
    jit = [random.uniform(0.8, 1.15) for _ in range(9)]
    props.add(cone(r, h, 9, jitter=jit), random.choice(m_mtn), M((x, -10, z), rot=(0, random.random() * 6, 0)))
    props.add(cone(r * 0.33, h * 0.33, 9, jitter=jit), m_snow, M((x, -10 + h * 0.67 + 0.5, z), rot=(0, 0, 0)))
props.build()

# ================================================================ 要動的物件（three.js 端依名稱動畫）
# 風車
mx, mz = LAKE[0] - 30 if LAKE else 0, (LAKE[1] + 55) if LAKE else 0
if not free_spot(mx, mz, WALL + 8):
    mx, mz = cx, cz
my = gh(mx, mz)
mill = Builder('Windmill')
mill.add(cylinder(3.2, 12, 12, r2=2.2), m_mill, M((mx, my - 0.5, mz)))
mill.add(cone(3.0, 3.6, 12, smooth=True), m_mill_roof, M((mx, my + 11.4, mz)))
mill.add(box(1.4, 2.4, 0.3, base=True), m_wood, M((mx + 0, my, mz + 3.0)))
mill.build()
blades = Builder('Windmill_Blades')
for k in range(4):
    a = k * math.pi / 2
    blades.add(box(0.5, 7.5, 0.15, base=True), m_wood, M((0, 0, 0), rot=(0, 0, a)))
    blades.add(box(1.5, 5.5, 0.08, base=True), m_mill, M((0, 0, 0), rot=(0, 0, a)) @ M((0.9, 1.8, 0.05)))
blades.add(cylinder(0.5, 0.8, 10), m_mill_roof, M((0, 0, 0), rot=(math.pi / 2, 0, 0)))
blades.build(origin=(mx, my + 11.5, mz + 3.2), local=True)

# 熱氣球
for k in range(5):
    a = 2 * math.pi * k / 5 + 0.4
    x, z = cx + math.cos(a) * random.uniform(120, 260), cz + math.sin(a) * random.uniform(100, 230)
    y = random.uniform(45, 85)
    bl = Builder(f'Balloon_{k}')
    bm = m_balloon[k % 4]
    bl.add(sphere(6.0, 14, 10), bm, M((0, 0, 0), scale=(1, 1.15, 1)))
    bl.add(cone(4.4, 4.0, 14, smooth=True), bm, M((0, -2.6, 0), rot=(math.pi, 0, 0)))
    for s in range(0, 14, 2):  # 直條紋
        aa = 2 * math.pi * s / 14
        bl.add(sphere(6.06, 14, 10), m_balloon[(k + 1) % 4], M(rot=(0, aa, 0)) @ M(scale=(0.13, 1.151, 1.001)))
    bl.add(box(1.6, 1.2, 1.6, base=True), m_basket, M((0, -9.6, 0)))
    for sx, sz in ((-0.7, -0.7), (0.7, -0.7), (0.7, 0.7), (-0.7, 0.7)):
        bl.add(box(0.05, 3.2, 0.05, base=True), m_basket, M((sx, -8.4, sz)))
    bl.build(origin=(x, y, z), local=True)

# 雲
clouds = Builder('Clouds')
for k in range(26):
    a = random.uniform(0, 2 * math.pi)
    rr = random.uniform(80, far + 200)
    x, z, y = cx + math.cos(a) * rr, cz + math.sin(a) * rr, random.uniform(95, 170)
    s = random.uniform(6, 14)
    for b in range(5):
        clouds.add(sphere(s * random.uniform(0.6, 1.0), 10, 6), m_cloud,
                   M((x + random.uniform(-1.6, 1.6) * s, y + random.uniform(0, 0.4) * s, z + random.uniform(-0.7, 0.7) * s), scale=(1, 0.65, 1)))
clouds.build()

# ================================================================ 匯出
os.makedirs(os.path.join(ROOT, 'assets'), exist_ok=True)
glb = os.path.join(ROOT, 'assets', TRACK + '.glb')
for ob in bpy.context.scene.objects:
    if ob.type == 'MESH' and len(ob.data.vertices) > 3000:
        print(f'[track]   {ob.name}: {len(ob.data.vertices)} verts, {len(ob.data.polygons)} faces')
export_glb(glb)
path = {
    'name': LAYOUT.get('name', TRACK),
    'step': round(STEP, 5),
    'length': round(LENGTH, 3),
    'halfWidth': HW,
    'curb': CURB,
    'wall': WALL,
    'wallThickness': WALL_T,
    'pts': [round(c, 3) for p in S for c in (p.x, p.y, p.z)],
    'bounds': [minx, minz, maxx, maxz],
}
with open(os.path.join(ROOT, 'assets', TRACK + '_path.json'), 'w', encoding='utf-8') as f:
    json.dump(path, f, ensure_ascii=False, separators=(',', ':'))
print(f'[track] wrote {glb} ({os.path.getsize(glb) // 1024} KB)')
