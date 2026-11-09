"""產生一條賽道的模型：路面、路緣石、護牆、地形、水（湖／海／熔岩）、起終點門、看台、主題場景物件。

用法（在 repo 根目錄）：
  <Blender>\\blender.exe -b --factory-startup -P tools\\blender\\build_track.py -- . <賽道 id>
讀 tools\\blender\\<id>_layout.json，輸出 assets\\<id>.glb 與 assets\\<id>_path.json
（遊戲用的中心線取樣，跟模型同一份資料，物理與畫面才對得上）。

主題（layout 的 theme）決定材質顏色、地形起伏、場景物件與遠景，見下面 THEMES 與 scatter_*。
天空、霧、燈光是 three.js 端的事（js/themes.js），這裡只管模型。
"""
import bpy
import json
import math
import os
import random
import sys
from mathutils import Vector, noise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Builder, Instances, M, basis, box, cone, cylinder, export_glb, mat, reset_scene, sphere)  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ROOT = os.path.abspath(argv[0] if argv else '.')
TRACK = argv[1] if len(argv) > 1 else 'hills'
LAYOUT = json.load(open(os.path.join(ROOT, 'tools', 'blender', TRACK + '_layout.json'), encoding='utf-8'))
THEME = LAYOUT.get('theme', 'hills')

HW = LAYOUT['halfWidth']
CURB = LAYOUT['curb']
WALL = LAYOUT['wall']
WALL_T = 0.7
WALL_H = 1.0
STEP = 2.0
LAKES = LAYOUT.get('lakes', [])
random.seed(617 + sum(map(ord, TRACK)))
UP = Vector((0, 1, 0))

reset_scene()

# ================================================================ 主題
# terrain：hills 起伏丘陵、sea 小島（外圍沉進海裡）、dunes 沙丘、flat 平地（城市）
THEMES = {
    'hills': dict(ground='#6cc24a', terrain='hills', amp=16, curb=('#e53935', '#f4f4f4'),
                  wall=('#1e88e5', '#fafafa', '#ffd54f'), water='Water', banner='#1a3fa0'),
    'beach': dict(ground='#f0d595', terrain='sea', amp=3, curb=('#ff7043', '#ffffff'),
                  wall=('#26c6da', '#ffffff', '#ffb74d'), water='Water', banner='#00838f'),
    'desert': dict(ground='#e2a865', terrain='dunes', amp=12, curb=('#e65100', '#fff3e0'),
                   wall=('#d84315', '#ffe0b2', '#8d6e63'), water=None, banner='#bf360c'),
    'snow': dict(ground='#f2f6fb', terrain='hills', amp=26, curb=('#1e88e5', '#ffffff'),
                 wall=('#e53935', '#fafafa', '#90caf9'), water='Ice', banner='#1565c0'),
    'city': dict(ground='#3b404c', terrain='flat', amp=0, curb=('#ffd600', '#222222'),
                 wall=('#ff2e88', '#20232c', '#00e5ff'), water=None, banner='#311b92'),
    'volcano': dict(ground='#3d3436', terrain='hills', amp=20, curb=('#d50000', '#212121'),
                    wall=('#4e342e', '#ff7043', '#ffab00'), water='Lava', banner='#3e2723'),
}
TH = THEMES[THEME]

# ================================================================ 中心線
P = [Vector((p[0], p[2] if len(p) > 2 else 0.0, p[1])) for p in LAYOUT['points']]  # 遊戲座標 (x, 高度, z)
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

CURV = []
for i in range(N):
    a, b = T[i - 1], T[(i + 1) % N]
    CURV.append(math.atan2(a.x * b.z - a.z * b.x, a.dot(b)) / (2 * STEP))
print(f'[track] {TRACK} ({THEME}) length={LENGTH:.1f}m samples={N} minRadius={min(1 / max(abs(c), 1e-6) for c in CURV):.1f}m')

# ---------------------------------------------------------------- 取樣點空間索引
CELL = 25.0
grid = {}
for i, p in enumerate(S):
    grid.setdefault((int(math.floor(p.x / CELL)), int(math.floor(p.z / CELL))), []).append(i)


def nearest(x, z, reach=3):
    """回傳 (水平距離, 該處路面高度, 取樣索引)；太遠找不到回 (1e9, None, -1)。"""
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


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


MARGIN = 260 if TH['terrain'] == 'sea' else 230
minx = min(p.x for p in S) - MARGIN
maxx = max(p.x for p in S) + MARGIN
minz = min(p.z for p in S) - MARGIN
maxz = max(p.z for p in S) + MARGIN
cx, cz = (minx + maxx) / 2, (minz + maxz) / 2
FAR = max(maxx - minx, maxz - minz) / 2 + 160
WATER_Y = -0.6


def ground(x, z):
    d, h, _ = nearest(x, z)
    if h is None:
        h = 0.0
    base = h - 0.12
    mode = TH['terrain']
    k = smooth(WALL + 2.0, WALL + 45.0, d)
    nz1 = noise.noise(Vector((x * 0.011, z * 0.011, 0.3))) * 0.5 + 0.5
    nz2 = noise.noise(Vector((x * 0.05, z * 0.05, 1.7)))
    ex = min(x - minx, maxx - x, z - minz, maxz - z)
    if mode == 'sea':
        # 小島：離賽道越遠越往下沉進海裡，邊緣是深海
        y = base + nz2 * 0.3 - smooth(WALL + 5, WALL + 34, d) * 4.0 - (1 - smooth(0, 200, ex)) * 6
        return y
    if mode == 'flat':
        y = base
    elif mode == 'dunes':
        dunes = abs(noise.noise(Vector((x * 0.018, z * 0.03, 4.0)))) * TH['amp']
        y = base + k * (dunes + nz2 * 1.0)
    else:
        y = base + k * max(0.0, nz1 * TH['amp'] + nz2 * 1.5)
    y += (1 - smooth(0, 120, ex)) * (8 if mode == 'flat' else 55.0)
    for lx, lz, lr in LAKES:
        r = math.hypot(x - lx, z - lz)
        if r < lr + 12:
            y = min(y, base) - smooth(lr + 12, lr - 6, r) * 2.6
    return y


# ================================================================ 材質
m_road = mat('Road', '#5b6170', rough=0.9)
m_ground = mat('Ground', TH['ground'], rough=1.0)
m_curb_r = mat('CurbA', TH['curb'][0])
m_curb_w = mat('CurbB', TH['curb'][1])
m_wall_a = mat('WallA', TH['wall'][0], emit=0.6 if THEME == 'city' else 0)
m_wall_b = mat('WallB', TH['wall'][1])
m_wall_top = mat('WallTop', TH['wall'][2], emit=1.0 if THEME == 'city' else 0)
m_chk_b = mat('CheckBlack', '#202020')
m_chk_w = mat('CheckWhite', '#ffffff')
m_tire = mat('Tire', '#262626', rough=0.95)
m_sign = mat('SignYellow', '#ffd600')
m_arrow = mat('ArrowRed', '#e53935')
m_concrete = mat('Concrete', '#d5dbe0' if THEME != 'city' else '#5a6070')
m_roof = mat('RoofRed', '#e53935')
m_people = [mat(f'Fan{i}', c) for i, c in enumerate(['#e53935', '#1e88e5', '#fdd835', '#43a047', '#ff7043', '#ab47bc', '#ffffff'])]
m_skin = mat('Skin', '#f2c6a0')
m_metal = mat('Metal', '#b0bec5', rough=0.35, metal=0.6)
m_banner = mat('Banner', TH['banner'])
m_text = mat('BannerText', '#ffffff', emit=0.3)
m_flag = [mat('FlagRed', '#ff3b30'), mat('FlagYellow', '#ffcc00'), mat('FlagGreen', '#34c759'), mat('FlagBlue', '#007aff')]
m_cloud = mat('Cloud', '#ffffff', emit=0.25)

# ================================================================ 路面、路緣石、護牆、起終點
CROSS = [-HW, -HW / 2, 0.0, HW / 2, HW]


def at(i, off, dy=0.0):
    i %= N
    p = S[i] + R[i] * off
    return Vector((p.x, p.y + dy, p.z))


road = Builder('Road')
for i in range(N):
    for c in range(len(CROSS) - 1):
        o0, o1 = CROSS[c], CROSS[c + 1]
        v0, v1 = i * STEP / 8.0, (i + 1) * STEP / 8.0
        u0, u1 = (o0 + HW) / (2 * HW), (o1 + HW) / (2 * HW)
        road.quad(at(i, o0), at(i + 1, o0), at(i + 1, o1), at(i, o1), m_road,
                  uv=[(u0, v0), (u0, v1), (u1, v1), (u1, v0)], smooth=True)
road.weld = True
road.build()

curbs = Builder('Curbs')
for i in range(N):
    m = m_curb_r if i % 2 == 0 else m_curb_w
    for side in (-1, 1):
        a0, a1 = side * HW, side * (HW + CURB)
        curbs.quad(at(i, a0, 0.02), at(i + 1, a0, 0.02), at(i + 1, a1, 0.1), at(i, a1, 0.1), m)
        curbs.quad(at(i, a1, 0.1), at(i + 1, a1, 0.1), at(i + 1, a1, -0.15), at(i, a1, -0.15), m)
curbs.build()

walls = Builder('Walls')
for i in range(N):
    m = m_wall_a if (i // 2) % 2 == 0 else m_wall_b
    for side in (-1, 1):
        if CURV[i] * side > 0 and 1 / max(abs(CURV[i]), 1e-6) < WALL + 2:
            continue  # 內彎半徑小於牆距：牆會自己打結，跳過
        a, b = side * (WALL - WALL_T / 2), side * (WALL + WALL_T / 2)
        walls.quad(at(i, a, -0.2), at(i + 1, a, -0.2), at(i + 1, a, WALL_H), at(i, a, WALL_H), m)
        walls.quad(at(i, b, WALL_H), at(i + 1, b, WALL_H), at(i + 1, b, -0.2), at(i, b, -0.2), m)
        walls.quad(at(i, a, WALL_H), at(i + 1, a, WALL_H), at(i + 1, b, WALL_H), at(i, b, WALL_H), m_wall_top)
walls.build()

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
nzc = int((maxz - minz) / GS) + 1
H = [[ground(minx + ix * GS, minz + iz * GS) for ix in range(nx)] for iz in range(nzc)]
terrain = Builder('Terrain')
terrain.verts = [(minx + ix * GS, H[iz][ix], minz + iz * GS) for iz in range(nzc) for ix in range(nx)]
mi = terrain._mi(m_ground)
for iz in range(nzc - 1):
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
    ix = max(0, min(nx - 2, int(fx)))
    iz = max(0, min(nzc - 2, int(fz)))
    tx, tz = fx - ix, fz - iz
    a = H[iz][ix] * (1 - tx) + H[iz][ix + 1] * tx
    b = H[iz + 1][ix] * (1 - tx) + H[iz + 1][ix + 1] * tx
    return a * (1 - tz) + b * tz


def disc(name, cxz, y, r, m, seg=40):
    b = Builder(name)
    c = Vector((cxz[0], y, cxz[1]))
    for k in range(seg):
        a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        b.quad(c, c + Vector((r * math.cos(a1), 0, r * math.sin(a1))), c + Vector((r * math.cos(a0), 0, r * math.sin(a0))), c, m)
    return b.build()


water_m = None
if TH['water'] == 'Water':
    water_m = mat('Water', '#3fb6f5', rough=0.2)
elif TH['water'] == 'Ice':
    water_m = mat('Ice', '#bfe7ff', rough=0.1)
elif TH['water'] == 'Lava':
    water_m = mat('Lava', '#ff5a1f', emit=2.0)
if TH['terrain'] == 'sea':
    # 整片海：大方形
    sea = Builder('Water')
    E = 3000
    sea.quad((cx - E, WATER_Y, cz - E), (cx - E, WATER_Y, cz + E), (cx + E, WATER_Y, cz + E), (cx + E, WATER_Y, cz - E), water_m)
    sea.build()
elif water_m:
    for k, (lx, lz, lr) in enumerate(LAKES):
        disc(f'{TH["water"]}_{k}', (lx, lz), -0.55, lr + 8, water_m)


def free_spot(x, z, clear):
    d, _, _ = nearest(x, z, reach=4)
    if d < clear:
        return False
    for lx, lz, lr in LAKES:
        if math.hypot(x - lx, z - lz) < lr + 6:
            return False
    if TH['terrain'] == 'sea' and gh(x, z) < WATER_Y + 0.25:
        return False
    return True


def variant(name, parts):
    b = Builder(name)
    for prim, m, mtx in parts:
        b.add(prim, m, mtx)
    return b.mesh()


def scatter(count, clear, put, cluster=True, tries=20000, near=None):
    """在空地上撒 count 個；put(x, z) 回傳 True 才算數。near=(最近, 最遠)：只撒在離賽道這個距離之間。"""
    placed = t = 0
    while placed < count and t < tries:
        t += 1
        if near:
            i = random.randrange(N)
            p = at(i, random.choice((-1, 1)) * random.uniform(*near))
            x, z = p.x, p.z
        else:
            x, z = random.uniform(minx + 40, maxx - 40), random.uniform(minz + 40, maxz - 40)
            if cluster and noise.noise(Vector((x * 0.02, z * 0.02, 5.0))) < -0.15 and random.random() < 0.7:
                continue
        if not free_spot(x, z, clear):
            continue
        if put(x, z):
            placed += 1
    return placed


props = Builder('Props')
anim = []  # 要動的零件另外建物件（Spin_*、Bob_*）

# ================================================================ 各主題的場景物件


def scatter_hills():
    m_trunk = mat('Trunk', '#8d5a3b')
    m_leaf = [mat('Leaf1', '#43a047'), mat('Leaf2', '#7cc95a'), mat('Leaf3', '#2e8b3e')]
    m_pine = mat('Pine', '#2f7d55')
    m_rock = mat('Rock', '#a3a7ad')
    m_flower = [mat('FlowerRed', '#ff5a5f'), mat('FlowerYellow', '#ffd23f'), mat('FlowerPink', '#ff8fd0'), mat('FlowerWhite', '#ffffff')]
    rounds = [variant(f'TreeRound{k}', [(cylinder(0.35, 2.6, 7), m_trunk, M((0, -0.1, 0))),
                                        (sphere(2.0, 9, 6), lm, M((0, 3.6, 0), scale=(1, 0.95, 1))),
                                        (sphere(1.4, 8, 5), lm, M((0.9, 4.6, -0.4)))]) for k, lm in enumerate(m_leaf)]
    pine = variant('TreePine', [(cylinder(0.3, 1.6, 6), m_trunk, M((0, -0.1, 0)))] +
                   [(cone(r, h, 9), m_pine, M((0, yy, 0), rot=(0, k * 0.7, 0))) for k, (r, h, yy) in enumerate(((2.4, 3.2, 1.2), (1.9, 2.8, 2.6), (1.3, 2.4, 3.9)))])
    bushes = [variant(f'Bush{k}', [(sphere(0.9, 8, 5), lm, M((dx, 0.5, dz))) for dx, dz in ((-0.7, 0.2), (0.6, 0.5), (0.1, -0.7))]) for k, lm in enumerate(m_leaf)]
    trees = Instances('Trees')

    def tree(x, z):
        kd = random.random()
        me = random.choice(rounds) if kd < 0.55 else pine if kd < 0.85 else random.choice(bushes)
        trees.put(me, (x, gh(x, z), z), yaw=random.uniform(0, 6.28), scale=random.uniform(0.8, 1.35))
        return True
    print('[track] trees', scatter(420, WALL + 5, tree))
    _fl = random.Random(3)
    flowers = []
    for k, fm in enumerate(m_flower):
        parts = []
        for f in range(6):
            fx, fz = _fl.uniform(-1.6, 1.6), _fl.uniform(-1.6, 1.6)
            parts.append((sphere(0.28, 6, 4), fm, M((fx, 0.32, fz))))
            parts.append((sphere(0.4, 6, 3), m_leaf[1], M((fx, 0.08, fz), scale=(1, 0.45, 1))))
        flowers.append(variant(f'Flowers{k}', parts))
    fi = Instances('Flowers')
    scatter(150, WALL + 1.2, lambda x, z: bool(fi.put(random.choice(flowers), (x, gh(x, z), z), yaw=random.uniform(0, 6.28))), near=(WALL + 1.5, WALL + 6))
    rock = variant('Rock', [(sphere(1.0, 7, 5, smooth=False), m_rock, None)])
    ri = Instances('Rocks')

    def rk(x, z):
        s = random.uniform(0.6, 2.2)
        ri.put(rock, (x, gh(x, z) + 0.2 * s, z), yaw=random.uniform(0, 6.28), scale=(1.3 * s, 0.8 * s, s))
        return True
    scatter(60, WALL + 4, rk, cluster=False)
    # 風車（葉片另建物件，three.js 轉它）
    m_mill = mat('MillWhite', '#f5f0e6')
    m_mill_roof = mat('MillRoof', '#c62828')
    m_wood = mat('Wood', '#b07a4a')
    lx, lz = (LAKES[0][0] - 30, LAKES[0][1] + 55) if LAKES else (cx, cz)
    if not free_spot(lx, lz, WALL + 8):
        lx, lz = cx, cz
    my = gh(lx, lz)
    props.add(cylinder(3.2, 12, 12, r2=2.2), m_mill, M((lx, my - 0.5, lz)))
    props.add(cone(3.0, 3.6, 12, smooth=True), m_mill_roof, M((lx, my + 11.4, lz)))
    props.add(box(1.4, 2.4, 0.3, base=True), m_wood, M((lx, my, lz + 3.0)))
    bl = Builder('Spin_Windmill')
    for k in range(4):
        a = k * math.pi / 2
        bl.add(box(0.5, 7.5, 0.15, base=True), m_wood, M(rot=(0, 0, a)))
        bl.add(box(1.5, 5.5, 0.08, base=True), m_mill, M(rot=(0, 0, a)) @ M((0.9, 1.8, 0.05)))
    bl.add(cylinder(0.5, 0.8, 10), m_mill_roof, M(rot=(math.pi / 2, 0, 0)))
    bl.build(origin=(lx, my + 11.5, lz + 3.2), local=True)
    balloons(5)
    mountains(['#6f9a86', '#86a3bd', '#7c8fa8'], snow=True)


def balloons(nb):
    cols = [mat('BalloonA', '#ff5252'), mat('BalloonB', '#ffca28'), mat('BalloonC', '#26c6da'), mat('BalloonD', '#7e57c2')]
    m_basket = mat('Basket', '#a1724e')
    for k in range(nb):
        a = 2 * math.pi * k / nb + 0.4
        x, z = cx + math.cos(a) * random.uniform(120, 260), cz + math.sin(a) * random.uniform(100, 230)
        bl = Builder(f'Bob_Balloon_{k}')
        bm = cols[k % 4]
        bl.add(sphere(6.0, 14, 10), bm, M(scale=(1, 1.15, 1)))
        bl.add(cone(4.4, 4.0, 14, smooth=True), bm, M((0, -2.6, 0), rot=(math.pi, 0, 0)))
        for s in range(0, 14, 2):
            bl.add(sphere(6.06, 14, 10), cols[(k + 1) % 4], M(rot=(0, 2 * math.pi * s / 14, 0)) @ M(scale=(0.13, 1.151, 1.001)))
        bl.add(box(1.6, 1.2, 1.6, base=True), m_basket, M((0, -9.6, 0)))
        for sx, sz in ((-0.7, -0.7), (0.7, -0.7), (0.7, 0.7), (-0.7, 0.7)):
            bl.add(box(0.05, 3.2, 0.05, base=True), m_basket, M((sx, -8.4, sz)))
        bl.build(origin=(x, random.uniform(45, 85), z), local=True)


def mountains(colors, snow=False, count=16, hmin=140, hmax=300, y0=-10, flat_top=False):
    ms = [mat(f'Mountain{k}', c) for k, c in enumerate(colors)]
    m_snow = mat('Snow', '#ffffff')
    for k in range(count):
        a = 2 * math.pi * k / count + random.uniform(-0.12, 0.12)
        rr = FAR + random.uniform(40, 260)
        x, z = cx + math.cos(a) * rr, cz + math.sin(a) * rr
        h = random.uniform(hmin, hmax)
        r = h * random.uniform(0.9, 1.4)
        jit = [random.uniform(0.8, 1.15) for _ in range(9)]
        if flat_top:
            # 平頂山（台地）：幾層錐台疊起來
            m = random.choice(ms)
            layers = 3
            for L in range(layers):
                r0 = r * (1 - L * 0.12)
                props.add(cylinder(r0, h / layers + 0.5, 9, r2=r0 * 0.9, smooth=False), ms[(k + L) % len(ms)],
                          M((x, y0 + L * h / layers, z), rot=(0, random.random() * 6, 0)))
        else:
            props.add(cone(r, h, 9, jitter=jit), random.choice(ms), M((x, y0, z), rot=(0, random.random() * 6, 0)))
            if snow:
                props.add(cone(r * 0.33, h * 0.33, 9, jitter=jit), m_snow, M((x, y0 + h * 0.67 + 0.5, z)))


def scatter_beach():
    m_trunk = mat('PalmTrunk', '#a07850')
    m_frond = [mat('Frond1', '#2e9b4f'), mat('Frond2', '#4cbb5c')]
    m_coco = mat('Coconut', '#6d4c2f')
    palms = []
    for k, fm in enumerate(m_frond):
        parts = []
        lean = 0.0
        y = 0.0
        x = 0.0
        for s in range(6):  # 彎彎的樹幹
            parts.append((cylinder(0.32 - s * 0.03, 1.25, 8), m_trunk, M((x, y, 0), rot=(0, 0, -lean))))
            x += math.sin(lean) * 1.2
            y += math.cos(lean) * 1.2
            lean += 0.06
        for f in range(7):
            a = f * 2 * math.pi / 7
            parts.append((cone(0.7, 4.2, 4), fm, M((x, y, 0), rot=(0, a, 0)) @ M(rot=(0, 0, -1.85)) @ M(scale=(1, 1, 0.28))))
        for c in range(3):
            a = c * 2.1
            parts.append((sphere(0.28, 7, 5), m_coco, M((x + math.cos(a) * 0.35, y - 0.3, math.sin(a) * 0.35))))
        palms.append(variant(f'Palm{k}', parts))
    pi_ = Instances('Palms')

    def palm(x, z):
        pi_.put(random.choice(palms), (x, gh(x, z) - 0.1, z), yaw=random.uniform(0, 6.28), scale=random.uniform(0.85, 1.3))
        return True
    print('[track] palms', scatter(260, WALL + 3, palm))
    # 遮陽傘
    cols = [mat('Umb1', '#ff5252'), mat('Umb2', '#ffd740'), mat('Umb3', '#40c4ff')]
    m_white = mat('UmbWhite', '#ffffff')
    umbs = [variant(f'Umbrella{k}', [(cylinder(0.06, 2.6, 6), m_white, None), (cone(1.6, 0.7, 8, smooth=False), c, M((0, 2.3, 0))),
                                    (box(0.8, 0.12, 1.9, base=True), c, M((1.4, 0, 0.2), rot=(0, 0.3, 0)))]) for k, c in enumerate(cols)]
    ui = Instances('Umbrellas')
    scatter(70, WALL + 2, lambda x, z: bool(ui.put(random.choice(umbs), (x, gh(x, z), z), yaw=random.uniform(0, 6.28))), near=(WALL + 3, WALL + 14))
    # 燈塔
    m_lw = mat('LighthouseWhite', '#ffffff')
    m_lr = mat('LighthouseRed', '#e53935')
    m_lamp = mat('LampGlow', '#fff59d', emit=2.0)
    best = None
    for i in range(0, N, 7):
        for side in (-1, 1):
            p = at(i, side * (WALL + 30))
            if free_spot(p.x, p.z, WALL + 20) and gh(p.x, p.z) > WATER_Y + 0.2:
                best = p
                break
        if best:
            break
    if best:
        y = gh(best.x, best.z) - 0.3
        for s in range(6):
            props.add(cylinder(3.0 - s * 0.3, 3.0, 14, r2=2.7 - s * 0.3), m_lw if s % 2 == 0 else m_lr, M((best.x, y + s * 3, best.z)))
        props.add(cylinder(1.4, 2.0, 12), m_lamp, M((best.x, y + 18, best.z)))
        props.add(cone(1.9, 1.6, 12, smooth=True), m_lr, M((best.x, y + 20, best.z)))
    # 遠方小島
    m_isl = mat('Island', '#4caf50')
    m_sand2 = mat('IslandSand', '#f0d595')
    for k in range(9):
        a = 2 * math.pi * k / 9 + random.uniform(-0.2, 0.2)
        rr = FAR + random.uniform(150, 500)
        x, z = cx + math.cos(a) * rr, cz + math.sin(a) * rr
        r = random.uniform(40, 110)
        props.add(cylinder(r * 1.15, 1.2, 14, r2=r * 1.1), m_sand2, M((x, WATER_Y - 0.9, z)))
        props.add(cone(r, r * random.uniform(0.4, 0.9), 10, jitter=[random.uniform(0.85, 1.1) for _ in range(10)]), m_isl, M((x, WATER_Y, z)))
    balloons(3)


def scatter_desert():
    m_cac = mat('Cactus', '#3f9b4f')
    m_flower = mat('CactusFlower', '#ff6fae')
    m_rock = mat('RedRock', '#b5552f')
    m_rock2 = mat('RedRock2', '#d47a45')
    m_bush = mat('DryBush', '#a88b4a')
    cacti = []
    for k in range(3):
        parts = [(cylinder(0.45, 4.2 + k, 9, r2=0.4), m_cac, None), (sphere(0.42, 9, 6), m_cac, M((0, 4.2 + k, 0)))]
        for side, hh in ((1, 1.8 + k * 0.3), (-1, 2.4)):
            parts.append((cylinder(0.28, 1.0, 8), m_cac, M((0.3 * side, hh, 0), rot=(0, 0, -1.57 * side))))
            parts.append((cylinder(0.28, 1.6, 8), m_cac, M((1.25 * side, hh - 0.05, 0))))
            parts.append((sphere(0.28, 8, 5), m_cac, M((1.25 * side, hh + 1.55, 0))))
        parts.append((sphere(0.22, 6, 4), m_flower, M((0, 4.55 + k, 0))))
        cacti.append(variant(f'Cactus{k}', parts))
    ci = Instances('Cacti')
    print('[track] cacti', scatter(260, WALL + 3, lambda x, z: bool(ci.put(random.choice(cacti), (x, gh(x, z) - 0.1, z), yaw=random.uniform(0, 6.28), scale=random.uniform(0.8, 1.3)))))
    bush = variant('DryBush', [(sphere(0.7, 7, 4, smooth=False), m_bush, M((dx, 0.35, dz), scale=(1, 0.6, 1))) for dx, dz in ((-0.5, 0), (0.5, 0.3), (0, -0.5))])
    bi = Instances('DryBushes')
    scatter(160, WALL + 1.5, lambda x, z: bool(bi.put(bush, (x, gh(x, z), z), yaw=random.uniform(0, 6.28))), near=(WALL + 2, WALL + 25))
    # 紅岩柱（近景）
    for k in range(26):
        for _ in range(60):
            x, z = random.uniform(minx + 60, maxx - 60), random.uniform(minz + 60, maxz - 60)
            if free_spot(x, z, WALL + 18):
                break
        else:
            continue
        h = random.uniform(10, 32)
        r = random.uniform(5, 12)
        y = gh(x, z) - 1
        layers = random.randint(2, 4)
        for L in range(layers):
            r0 = r * (1 - L * 0.1)
            props.add(cylinder(r0, h / layers + 0.2, 8, r2=r0 * 0.92, smooth=False), m_rock if L % 2 == 0 else m_rock2,
                      M((x, y + L * h / layers, z), rot=(0, random.random() * 6, 0)))
    rock = variant('DesertRock', [(sphere(1.0, 7, 5, smooth=False), m_rock2, None)])
    ri = Instances('Rocks')
    scatter(70, WALL + 3, lambda x, z: bool(ri.put(rock, (x, gh(x, z), z), yaw=random.uniform(0, 6.28), scale=random.uniform(0.6, 2.4))), cluster=False)
    mountains(['#b5552f', '#c96b3c', '#a3462a'], flat_top=True, hmin=80, hmax=180)


def scatter_snow():
    m_trunk = mat('Trunk', '#6d4c3b')
    m_pine = mat('SnowPine', '#2c6b4f')
    m_snowcap = mat('SnowCap', '#ffffff')
    m_ice = mat('IceCrystal', '#9fdcff', emit=0.25)
    m_carrot = mat('Carrot', '#ff8a00')
    m_coal = mat('Coal', '#222222')
    m_scarf = mat('Scarf', '#e53935')
    m_cabin = mat('Cabin', '#8d5a3b')
    m_window = mat('CabinWindow', '#ffd77a', emit=1.2)
    pines = []
    for k in range(2):
        parts = [(cylinder(0.3, 1.6, 6), m_trunk, M((0, -0.1, 0)))]
        for L, (r, h, yy) in enumerate(((2.6, 3.2, 1.2), (2.0, 2.8, 2.7), (1.4, 2.4, 4.1))):
            parts.append((cone(r, h, 9), m_pine, M((0, yy, 0), rot=(0, L * 0.7, 0))))
            parts.append((cone(r * 0.62, h * 0.42, 9), m_snowcap, M((0, yy + h * 0.6, 0), rot=(0, L * 0.7, 0))))
        pines.append(variant(f'SnowPine{k}', parts))
    pi_ = Instances('Pines')
    print('[track] pines', scatter(480, WALL + 4, lambda x, z: bool(pi_.put(random.choice(pines), (x, gh(x, z), z), yaw=random.uniform(0, 6.28), scale=random.uniform(0.8, 1.5)))))
    snowman = variant('Snowman', [(sphere(0.9, 10, 7), m_snowcap, M((0, 0.8, 0))), (sphere(0.65, 10, 7), m_snowcap, M((0, 2.0, 0))),
                                  (sphere(0.45, 10, 7), m_snowcap, M((0, 2.95, 0))), (cone(0.08, 0.5, 6), m_carrot, M((0, 2.95, 0.4), rot=(1.57, 0, 0))),
                                  (sphere(0.06, 6, 4), m_coal, M((0.15, 3.1, 0.38))), (sphere(0.06, 6, 4), m_coal, M((-0.15, 3.1, 0.38))),
                                  (cylinder(0.5, 0.18, 12), m_scarf, M((0, 2.45, 0)))])
    si = Instances('Snowmen')
    scatter(24, WALL + 2, lambda x, z: bool(si.put(snowman, (x, gh(x, z), z), yaw=random.uniform(0, 6.28))), near=(WALL + 3, WALL + 12))
    crystal = variant('IceCrystal', [(cone(0.5, 3.0, 5), m_ice, M(rot=(0.2, 0, 0.1))), (cone(0.35, 2.0, 5), m_ice, M((0.5, 0, 0.2), rot=(0, 0, -0.4)))])
    ii = Instances('Crystals')
    scatter(60, WALL + 2, lambda x, z: bool(ii.put(crystal, (x, gh(x, z), z), yaw=random.uniform(0, 6.28), scale=random.uniform(0.7, 1.6))))
    # 小木屋（亮著窗）
    for k in range(7):
        for _ in range(80):
            i = random.randrange(N)
            p = at(i, random.choice((-1, 1)) * random.uniform(WALL + 14, WALL + 30))
            if free_spot(p.x, p.z, WALL + 12):
                break
        else:
            continue
        y = gh(p.x, p.z) - 0.2
        mm = basis(T[i], UP, T[i].cross(UP), Vector((p.x, y, p.z)))
        props.add(box(6, 3.2, 5, base=True), m_cabin, mm)
        props.add(cone(4.6, 2.4, 4, smooth=False), m_snowcap, mm @ M((0, 3.2, 0), rot=(0, math.pi / 4, 0)) @ M(scale=(1.05, 1, 0.85)))
        for wx in (-1.6, 1.6):
            props.add(box(1.0, 1.0, 0.1), m_window, mm @ M((wx, 1.7, 2.52)))
            props.add(box(1.0, 1.0, 0.1), m_window, mm @ M((wx, 1.7, -2.52)))
    mountains(['#dfe8f2', '#c9d6e3', '#b8c7d8'], snow=True, hmin=200, hmax=380)


def scatter_city():
    bodies = [mat('Bldg1', '#2a2f45'), mat('Bldg2', '#353b55'), mat('Bldg3', '#1f2436'), mat('Bldg4', '#40384f')]
    wins = [mat('WindowWarm', '#ffd77a', emit=1.6), mat('WindowCool', '#8fe3ff', emit=1.6), mat('WindowPink', '#ff8fd8', emit=1.6)]
    neons = [mat('NeonPink', '#ff2e88', emit=2.5), mat('NeonCyan', '#00e5ff', emit=2.5), mat('NeonYellow', '#ffe14d', emit=2.5), mat('NeonGreen', '#39ff88', emit=2.5)]
    m_lamp = mat('LampGlow', '#fff3c4', emit=2.5)
    m_pole = mat('LampPole', '#5b6270')

    def building(x, z, w, d, h, yaw, near_track=False):
        y = gh(x, z) - 0.2
        mm = M((x, y, z), rot=(0, yaw, 0))
        props.add(box(w, h, d, base=True), random.choice(bodies), mm)
        wm = random.choice(wins)
        floors = int(h / 3.2)
        for f in range(1, floors):
            if random.random() < 0.18:
                continue
            # 每層一條窗帶：比樓身稍大的扁盒子，四面一次包住
            props.add(box(w + 0.06, 0.9, d + 0.06), wm, mm @ M((0, f * 3.2, 0)))
        if near_track and random.random() < 0.7:
            nm = random.choice(neons)
            props.add(box(w * 0.7, 1.6, 0.3), nm, mm @ M((0, min(h - 2, 6 + random.random() * 6), d / 2 + 0.2)))
            props.add(box(w * 0.7, 1.6, 0.3), nm, mm @ M((0, min(h - 2, 6 + random.random() * 6), -d / 2 - 0.2)))
        if random.random() < 0.3:
            props.add(cylinder(0.12, 6, 5), m_pole, mm @ M((w * 0.3, h, 0)))
            props.add(sphere(0.35, 6, 4), mat('AntennaRed', '#ff1744', emit=2.5), mm @ M((w * 0.3, h + 6, 0)))

    # 沿著賽道兩側一整排大樓（街景）
    cnt = 0
    i = 0
    while i < N:
        for side in (-1, 1):
            off = side * (WALL + random.uniform(9, 14))
            p = at(i, off)
            w = random.uniform(10, 18)
            if free_spot(p.x, p.z, WALL + 7):
                building(p.x, p.z, w, random.uniform(10, 16), random.uniform(14, 60), math.atan2(T[i].x, T[i].z), near_track=True)
                cnt += 1
        i += random.randint(7, 10)
    # 後排更高的樓
    def far_bldg(x, z):
        building(x, z, random.uniform(14, 26), random.uniform(14, 26), random.uniform(30, 110), random.uniform(0, 6.28))
        return True
    cnt += scatter(110, WALL + 30, far_bldg, cluster=False)
    print('[track] buildings', cnt)
    # 路燈
    lamp = variant('StreetLamp', [(cylinder(0.12, 6.5, 6), m_pole, None), (box(1.6, 0.15, 0.2, base=True), m_pole, M((0.7, 6.4, 0))),
                                   (box(0.7, 0.25, 0.45), m_lamp, M((1.4, 6.3, 0)))])
    li = Instances('Lamps')
    for i in range(0, N, 12):
        for side in (-1, 1):
            p = at(i, side * (WALL + 0.9))
            yaw = math.atan2(T[i].x, T[i].z) + (math.pi / 2 if side > 0 else -math.pi / 2)
            li.put(lamp, (p.x, p.y - 0.1, p.z), yaw=yaw)
    # 遠方天際線
    for k in range(70):
        a = 2 * math.pi * k / 70 + random.uniform(-0.03, 0.03)
        rr = FAR + random.uniform(20, 200)
        x, z = cx + math.cos(a) * rr, cz + math.sin(a) * rr
        h = random.uniform(60, 220)
        w = random.uniform(25, 50)
        mm = M((x, -1, z), rot=(0, -a, 0))
        props.add(box(w, h, w, base=True), random.choice(bodies), mm)
        wm = random.choice(wins)
        for f in range(1, int(h / 14)):
            if random.random() < 0.35:
                continue
            props.add(box(w + 0.2, 2.6, w + 0.2), wm, mm @ M((0, f * 14, 0)))


def scatter_volcano():
    m_dead = mat('DeadWood', '#2b2222')
    m_rock = mat('Basalt', '#2a2426')
    m_glow = mat('LavaGlow', '#ff6a00', emit=2.2)
    m_ash = mat('Ash', '#5d5355')
    m_crater = mat('Crater', '#ff3d00', emit=3.0)
    deads = []
    for k in range(2):
        parts = [(cylinder(0.32, 4.5, 6, r2=0.14), m_dead, None)]
        for b in range(4):
            a = b * 1.7 + k
            parts.append((cylinder(0.12, 2.0, 5, r2=0.04), m_dead, M((0, 2.2 + b * 0.55, 0), rot=(0, a, 0)) @ M(rot=(0, 0, -0.9))))
        deads.append(variant(f'DeadTree{k}', parts))
    di = Instances('DeadTrees')
    print('[track] deadtrees', scatter(200, WALL + 4, lambda x, z: bool(di.put(random.choice(deads), (x, gh(x, z), z), yaw=random.uniform(0, 6.28), scale=random.uniform(0.8, 1.4)))))
    rock = variant('LavaRock', [(sphere(1.0, 7, 5, smooth=False), m_rock, None), (sphere(0.55, 6, 4, smooth=False), m_glow, M((0.2, 0.55, 0.1)))])
    ri = Instances('Rocks')
    scatter(140, WALL + 2, lambda x, z: bool(ri.put(rock, (x, gh(x, z), z), yaw=random.uniform(0, 6.28), scale=random.uniform(0.6, 2.6))), cluster=False)
    # 路邊的熔岩裂縫（發光的細條）
    for k in range(60):
        i = random.randrange(N)
        side = random.choice((-1, 1))
        p = at(i, side * random.uniform(WALL + 2, WALL + 8))
        if not free_spot(p.x, p.z, WALL + 1.5):
            continue
        y = gh(p.x, p.z) + 0.02
        props.add(box(random.uniform(2, 6), 0.06, 0.35), m_glow, M((p.x, y, p.z), rot=(0, random.uniform(0, 6.28), 0)))
    # 大火山（遠景）＋發光火山口
    a = random.uniform(0, 2 * math.pi)
    vx, vz = cx + math.cos(a) * (FAR + 150), cz + math.sin(a) * (FAR + 150)
    props.add(cone(420, 360, 14, jitter=[random.uniform(0.85, 1.1) for _ in range(14)]), m_ash, M((vx, -10, vz)))
    props.add(cylinder(70, 8, 14, r2=60), m_crater, M((vx, 330, vz)))
    sm = Builder('Spin_Smoke')
    for k in range(8):
        sm.add(sphere(30 + k * 6, 9, 6), m_ash, M((math.cos(k) * 20, 360 + k * 35, math.sin(k) * 20), scale=(1, 0.6, 1)))
    sm.build(origin=(vx, 0, vz), local=True)
    mountains(['#3a3234', '#4a3f42', '#2e2729'], hmin=120, hmax=260)


{'hills': scatter_hills, 'beach': scatter_beach, 'desert': scatter_desert,
 'snow': scatter_snow, 'city': scatter_city, 'volcano': scatter_volcano}[THEME]()

# ================================================================ 共用：輪胎牆、箭頭牌、起終點門、看台、旗子
corner_peaks = []
for i in range(N):
    c = abs(CURV[i])
    if c > 1 / 45 and c >= abs(CURV[i - 1]) and c >= abs(CURV[(i + 1) % N]):
        if all(min(abs(i - j), N - abs(i - j)) > 25 for j in corner_peaks):
            corner_peaks.append(i)
print(f'[track] corners={len(corner_peaks)}')
tire = variant('TireStack', [(cylinder(0.5, 0.32, 10), m_tire, M((0, h * 0.33, 0))) for h in range(3)])
ti = Instances('Tires')
for ci in corner_peaks:
    side = -1 if CURV[ci] > 0 else 1  # 外側
    for k in range(-10, 11, 2):
        i = (ci + k) % N
        p = at(i, side * (WALL + 1.3))
        ti.put(tire, (p.x, p.y - 0.15, p.z), yaw=random.uniform(0, 6.28))
    for k in range(-6, 7, 3):
        i = (ci + k) % N
        o = at(i, side * (WALL + 0.9), 0.0)
        inward = R[i] * (-side)
        fwd = T[i]
        mtx = basis(fwd, UP, inward, o)
        sgn = 1
        if fwd.cross(UP).dot(inward) < 0:  # 保持右手座標；左右側不同時把 x 反過來，箭頭跟著反
            mtx = basis(-fwd, UP, inward, o)
            sgn = -1
        props.add(box(0.12, 2.0, 0.12, base=True), m_metal, mtx @ M((-0.7, -0.2, 0)))
        props.add(box(0.12, 2.0, 0.12, base=True), m_metal, mtx @ M((0.7, -0.2, 0)))
        props.add(box(2.0, 1.2, 0.12), m_sign, mtx @ M((0, 2.2, 0.08)))
        for yy in (0.22, -0.22):
            props.add(box(0.75, 0.2, 0.06), m_arrow, mtx @ M((-0.05 * sgn, 2.2 + yy, 0.16), rot=(0, 0, -sgn * math.copysign(0.62, yy))))

p0, t0, r0 = S[0], T[0], R[0]
gate_h = 7.5
for side in (-1, 1):
    base = p0 + r0 * side * (WALL + 0.9) + t0 * 3
    props.add(cylinder(0.6, gate_h + 1.5, 12), m_metal, M((base.x, base.y - 0.2, base.z)))
    props.add(sphere(0.9, 10, 6), m_flag[0], M((base.x, base.y + gate_h + 1.6, base.z)))
gc = p0 + t0 * 3 + Vector((0, gate_h, 0))
gm = basis(r0, UP, -t0, gc)
gw = 2 * WALL + 1.8
props.add(box(gw, 2.6, 0.8), m_banner, gm)
for k in range(28):
    xx = -(WALL + 0.9) + (k + 0.5) * gw / 28
    props.add(box(gw / 28, 0.45, 0.85), m_chk_b if k % 2 == 0 else m_chk_w, gm @ M((xx, 1.5, 0)))
    props.add(box(gw / 28, 0.45, 0.85), m_chk_w if k % 2 == 0 else m_chk_b, gm @ M((xx, -1.5, 0)))


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
        q = at(i, WALL + 4 + tier * 1.4)
        props.add(box(STEP + 0.05, 0.9 + tier * 0.75, 1.45, base=True), m_concrete, basis(T[i], UP, T[i].cross(UP), q) @ M((0, -0.3, 0)))
        if random.random() < 0.8:
            top = q.y - 0.3 + 0.9 + tier * 0.75
            pp = q + T[i] * random.uniform(-0.5, 0.5)
            props.add(cylinder(0.28, 0.75, 6), random.choice(m_people), M((pp.x, top, pp.z)))
            props.add(sphere(0.24, 7, 5), m_skin, M((pp.x, top + 0.95, pp.z)))
    if k % 6 == 0:
        q = at(i, WALL + 4 + 6 * 1.4 + 0.5)
        props.add(cylinder(0.12, 9.5, 6), m_metal, M((q.x, q.y - 0.3, q.z)))
roof_m = basis(T[0], UP, T[0].cross(UP), at(0, WALL + 4 + 3.5 * 1.4) + Vector((0, 9.3, 0)))
props.add(box(STEP * 37 + 2, 0.4, 11, base=True), m_roof, roof_m @ M(rot=(0.12, 0, 0)))

for i in range(0, N, 9):
    if abs(CURV[i]) > 1 / 120 or THEME == 'city':
        continue
    for side in (-1, 1):
        q = at(i, side * (WALL + 0.2))
        props.add(cylinder(0.06, 4.2, 5), m_metal, M((q.x, q.y + WALL_H - 0.1, q.z)))
        fb = basis(T[i], UP, T[i].cross(UP), q + Vector((0, WALL_H + 3.6, 0)) + T[i] * 0.55)
        props.add(box(1.1, 0.7, 0.04), m_flag[(i // 9 + (side > 0)) % 4], fb)
props.build()

# 雲（城市夜景不要）
if THEME != 'city':
    clouds = Builder('Clouds')
    m_c = m_cloud if THEME != 'volcano' else mat('AshCloud', '#6d6266')
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
for ob in bpy.context.scene.objects:
    if ob.type == 'MESH' and len(ob.data.vertices) > 8000:
        print(f'[track]   {ob.name}: {len(ob.data.vertices)} verts')
export_glb(glb)
path = {
    'id': TRACK,
    'name': LAYOUT.get('name', TRACK),
    'theme': THEME,
    'difficulty': LAYOUT.get('difficulty', 1),
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
