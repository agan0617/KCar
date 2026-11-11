"""賽道格式 v2（tools/blender/TRACK_V2.md）的 layout 讀取、中心線取樣與檢查（不用開 Blender）。

build_track2.py 也 import 這支的 build_model()：取樣、捷徑、立體交叉判定只有一份程式，
模型、物理、檢查永遠對得上。

用法（repo 根目錄）：python tools/check_layout2.py testbed [其他 id ...]
檢查：一圈長度、最小彎道半徑、自我交叉處的高差（≥ 7m 才能做成立體交叉）、坡度、側傾、
跳台（缺口長度、起跳角、最低過得去的車速、40 m/s 時的落點）、捷徑、加速帶與 hazard 位置；
俯視圖 PNG 寫到 tmp_layout/<id>_v2.png（環境變數 LAYOUT_PNG_DIR 可改）。
"""
import json
import math
import os
import struct
import sys
import zlib

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
BL = os.path.join(ROOT, 'tools', 'blender')

STEP = 2.0          # 取樣間距（公尺）
SUB = 80            # 每段 Catmull-Rom 先密取樣幾點
CELL = 20.0         # 取樣點空間索引的格子
MIN_CLEAR = 7.0     # 立體交叉最少高差
BRIDGE_DY = 4.0     # 高差超過這個就當橋處理（不到 MIN_CLEAR 會報錯）
SPEED = 40.0        # 跳台試算的車速（m/s）
GRAVITY = 30.0      # 遊戲重力（m/s²）
DEFAULTS = {'w': 7.5, 'bank': 0.0, 'curb': 1.0, 'wallL': 'wall', 'wallR': 'wall', 'run': 3.0,
            'edge': 'grass', 'gap': False, 'tunnel': False, 'viaduct': False}
NUM_KEYS = ('w', 'bank', 'curb', 'run')               # 兩點之間平滑內插
SEG_KEYS = ('wallL', 'wallR', 'edge', 'gap', 'tunnel', 'viaduct')  # 取前一點的值
SHORTCUT_RUN = 1.5  # 捷徑兩側路肩寬


# ---------------------------------------------------------------- 小工具（tuple 向量）

def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def lerp3(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def dist(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def smooth(e0, e1, x):
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = (x - e0) / (e1 - e0)
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return t * t * (3 - 2 * t)


def game(p):
    """layout 的 [x, z, y] → 遊戲座標 (x, y, z)（three.js，Y 朝上）。"""
    return (float(p[0]), float(p[2]) if len(p) > 2 else 0.0, float(p[1]))


def catmull(p0, p1, p2, p3, t, alpha=0.5):
    """centripetal Catmull-Rom。"""
    def tj(ti, a, b):
        return ti + max(dist(a, b), 1e-4) ** alpha
    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)
    tt = t1 + (t2 - t1) * t

    def lp(a, b, ta, tb):
        return lerp3(a, b, (tt - ta) / (tb - ta))
    a1 = lp(p0, p1, t0, t1)
    a2 = lp(p1, p2, t1, t2)
    a3 = lp(p2, p3, t2, t3)
    b1 = lp(a1, a2, t0, t2)
    b2 = lp(a2, a3, t1, t3)
    return lp(b1, b2, t1, t2)


# ---------------------------------------------------------------- layout

def load_layout(name, root=ROOT):
    with open(os.path.join(root, 'tools', 'blender', name + '_layout.json'), encoding='utf-8') as f:
        return json.load(f)


def is_v2(lay):
    pts = lay.get('points') or []
    return bool(pts) and isinstance(pts[0], dict)


def resolve_points(lay):
    d = dict(DEFAULTS)
    d.update(lay.get('defaults') or {})
    out = []
    for p in lay['points']:
        if not isinstance(p, dict):
            p = {'p': p}
        q = dict(d)
        for k, v in p.items():
            if k != 'p':
                q[k] = v
        q['pos'] = game(p['p'])
        q['bank'] = max(-25.0, min(25.0, float(q['bank'])))
        for k in ('w', 'curb', 'run'):
            q[k] = float(q[k])
        q['gap'] = bool(q['gap'])
        q['tunnel'] = bool(q['tunnel'])
        q['viaduct'] = q['viaduct'] if q['viaduct'] in ('wood',) else bool(q['viaduct'])
        out.append(q)
    return out


def resample(dense, du, step, closed):
    cum = [0.0]
    for i in range(1, len(dense)):
        cum.append(cum[-1] + dist(dense[i], dense[i - 1]))
    L = cum[-1]
    N = max(2, int(round(L / step)))
    st = L / N
    S, U = [], []
    j = 0
    for i in range(N if closed else N + 1):
        d = min(i * st, L)
        while j < len(cum) - 2 and cum[j + 1] < d:
            j += 1
        t = (d - cum[j]) / max(cum[j + 1] - cum[j], 1e-9)
        S.append(lerp3(dense[j], dense[j + 1], t))
        U.append(du[j] + (du[j + 1] - du[j]) * t)
    return S, U, L, st


# ---------------------------------------------------------------- 一條路（主線或捷徑）的取樣

class Strip:
    """取樣後的一條路。S：中心線 (x, y, z)；每個取樣點的半寬、側傾、路緣石、路肩、護牆…
    側邊 side：+1＝往前看的右手邊、-1＝左手邊。橫向偏移 o 一律是水平距離（右正）。"""

    def __init__(self, name, S, U, step, attrs, closed, length):
        self.name = name
        self.S = S
        self.U = U
        self.step = step
        self.closed = closed
        self.length = length
        n = self.n = len(S)
        for k, v in attrs.items():
            setattr(self, k, v)
        self.tb = [math.tan(math.radians(b)) for b in self.bank]
        self.bridge = [False] * n
        self.drawn = [True] * n
        self.s = [i * step for i in range(n)]
        T, R = [], []
        for i in range(n):
            a = S[i - 1] if (closed or i > 0) else S[i]
            b = S[(i + 1) % n] if (closed or i < n - 1) else S[i]
            dx, dz = b[0] - a[0], b[2] - a[2]
            ll = math.hypot(dx, dz) or 1.0
            T.append((dx / ll, 0.0, dz / ll))
            R.append((-dz / ll, 0.0, dx / ll))  # 往前看時的右手邊
        self.T, self.R = T, R
        raw = []
        for i in range(n):
            if not closed and (i == 0 or i == n - 1):
                raw.append(0.0)
                continue
            a, b = T[i - 1], T[(i + 1) % n]
            raw.append(math.atan2(a[0] * b[2] - a[2] * b[0], a[0] * b[0] + a[2] * b[2]) / (2 * step))
        # 曲率（右彎為正）：前後各 3 點平均，去掉取樣雜訊
        self.curv = []
        for i in range(n):
            acc, cnt = 0.0, 0
            for k in range(-3, 4):
                j = i + k
                if closed:
                    j %= n
                elif j < 0 or j >= n:
                    continue
                acc += raw[j]
                cnt += 1
            self.curv.append(acc / cnt)
        self.index()

    # 索引
    def index(self):
        self.h_all = {}
        self.h_terr = {}
        for i, p in enumerate(self.S):
            k = (int(math.floor(p[0] / CELL)), int(math.floor(p[2] / CELL)))
            self.h_all.setdefault(k, []).append(i)
            if self.terr_ok(i):
                self.h_terr.setdefault(k, []).append(i)

    def terr_ok(self, i):
        """地形要貼合的取樣點：畫出來、不是缺口、不是橋（含高架）、不是隧道（隧道上面地形蓋住）。"""
        return self.drawn[i] and not self.gap[i] and not self.bridge[i] and not self.tunnel[i]

    def nxt(self, i):
        if self.closed:
            return (i + 1) % self.n
        return i + 1 if i + 1 < self.n else None

    def seg_ok(self, i):
        """第 i 段（i → i+1）有路面。"""
        j = self.nxt(i)
        return j is not None and self.drawn[i] and self.drawn[j] and not self.gap[i] and not self.gap[j]

    def wall(self, i, side):
        w = self.wallR[i] if side > 0 else self.wallL[i]
        j = self.nxt(i)
        if w == 'none' and (self.bridge[i] or (j is not None and self.bridge[j])):
            return 'rail'  # 橋上一定要有護欄
        if w == 'none' and self.tunnel[i]:
            return 'wall'  # 隧道裡一定有牆
        return w

    def eo(self, i, side=1):
        """路肩外緣（護牆內面）離中心線的水平距離。"""
        return self.hw[i] + self.curb[i] + self.run[i]

    def eo_max(self, i):
        return self.hw[i] + self.curb[i] + self.run[i]

    def plane_y(self, i, o):
        """第 i 點、橫向偏移 o 處的路面（含側傾）高度，不含路緣石隆起。"""
        return self.S[i][1] - o * self.tb[i]

    def point(self, i, o, dy=0.0):
        s, r = self.S[i], self.R[i]
        return (s[0] + r[0] * o, s[1] - o * self.tb[i] + dy, s[2] + r[2] * o)

    def lerp(self, arr, a, u):
        b = self.nxt(a)
        if b is None:
            return arr[a]
        return arr[a] + (arr[b] - arr[a]) * u

    def near(self, x, z, radius):
        r = int(math.ceil(radius / CELL))
        cx, cz = int(math.floor(x / CELL)), int(math.floor(z / CELL))
        out = []
        for gx in range(cx - r, cx + r + 1):
            for gz in range(cz - r, cz + r + 1):
                out.extend(self.h_all.get((gx, gz), ()))
        return out

    def project(self, x, z, reach=3, terr=False):
        """投影到中心線：回傳 (水平距離 d, 橫向偏移 o（右正）, 段起點 a, 段內比例 u, 最近取樣點 bi)；找不到回 None。
        terr=True 只看地形要貼合的取樣點（缺口與橋略過）。"""
        H = self.h_terr if terr else self.h_all
        cx, cz = int(math.floor(x / CELL)), int(math.floor(z / CELL))
        best, bi = 1e18, -1
        S = self.S
        for gx in range(cx - reach, cx + reach + 1):
            for gz in range(cz - reach, cz + reach + 1):
                for i in H.get((gx, gz), ()):
                    dx, dz = S[i][0] - x, S[i][2] - z
                    d2 = dx * dx + dz * dz
                    if d2 < best:
                        best, bi = d2, i
        if bi < 0:
            return None
        res = None
        n = self.n
        for a in (bi - 1, bi):
            if self.closed:
                a %= n
            elif a < 0 or a >= n - 1:
                continue
            b = (a + 1) % n
            if terr and not (self.terr_ok(a) and self.terr_ok(b)):
                continue
            ax, az, bx, bz = S[a][0], S[a][2], S[b][0], S[b][2]
            ex, ez = bx - ax, bz - az
            l2 = ex * ex + ez * ez
            if l2 < 1e-9:
                continue
            u = max(0.0, min(1.0, ((x - ax) * ex + (z - az) * ez) / l2))
            px, pz = ax + ex * u, az + ez * u
            d = math.hypot(x - px, z - pz)
            if res is None or d < res[0]:
                ll = math.sqrt(l2)
                side = (x - px) * (-ez / ll) + (z - pz) * (ex / ll)
                res = (d, d if side >= 0 else -d, a, u, bi)
        if res is None:
            d = math.sqrt(best)
            r = self.R[bi]
            side = (x - S[bi][0]) * r[0] + (z - S[bi][2]) * r[2]
            a = bi if (self.closed or bi < n - 1) else bi - 1
            u = 0.0 if a == bi else 1.0
            res = (d, d if side >= 0 else -d, a, u, bi)
        return res

    def surface_y(self, a, u, o):
        """投影點 (a, u) 的路面平面在橫向偏移 o 處的高度（路肩、路面同一個側傾平面）。"""
        b = self.nxt(a)
        if b is None:
            return self.S[a][1] - o * self.tb[a]
        y = self.S[a][1] + (self.S[b][1] - self.S[a][1]) * u
        tb = self.tb[a] + (self.tb[b] - self.tb[a]) * u
        return y - o * tb

    # 沿線位置
    def at_to_s(self, at):
        """layout 的 at（控制點索引＋小數）→ 沿線距離。"""
        U = self.U
        npts = self.npts
        a = at % npts
        lo, hi = 0, self.n - 1
        if a >= U[-1]:
            t = (a - U[-1]) / max(npts - U[-1], 1e-9)
            return self.s[-1] + (self.length - self.s[-1]) * t
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if U[mid] <= a:
                lo = mid
            else:
                hi = mid
        t = (a - U[lo]) / max(U[hi] - U[lo], 1e-9)
        return self.s[lo] + (self.s[hi] - self.s[lo]) * t

    def locate(self, s):
        """沿線距離 → (段起點 a, 段內比例 u)。"""
        if self.closed:
            s %= self.length
        else:
            s = max(0.0, min(self.length - 1e-6, s))
        f = s / self.step
        a = int(math.floor(f))
        u = f - a
        if self.closed:
            a %= self.n
        elif a >= self.n - 1:
            a, u = self.n - 2, 1.0
        return a, u

    def pos_at_s(self, s, o=0.0):
        a, u = self.locate(s)
        b = self.nxt(a)
        return lerp3(self.point(a, o), self.point(b, o), u)


def sample_main(pts, lay_walls=None):
    n = len(pts)
    P = [q['pos'] for q in pts]
    G = [q['gap'] for q in pts]
    dense, du = [], []
    for i in range(n):
        p0, p1, p2, p3 = P[(i - 1) % n], P[i], P[(i + 1) % n], P[(i + 2) % n]
        # 跳台：缺口前後兩段的高度用外插的假鄰點，起跳坡度＝前一段的坡度、落地坡度＝後一段的坡度，
        # 不會被缺口另一頭拉平
        q0 = add(p1, sub(p1, p2)) if G[(i - 1) % n] else p0
        q3 = add(p2, sub(p2, p1)) if G[(i + 1) % n] else p3
        special = (q0 is not p0) or (q3 is not p3)
        for k in range(SUB):
            t = k / SUB
            c = catmull(p0, p1, p2, p3, t)
            if G[i]:
                y = p1[1] + (p2[1] - p1[1]) * t
            elif special:
                y = catmull(q0, p1, p2, q3, t)[1]
            else:
                y = c[1]
            dense.append((c[0], y, c[2]))
            du.append(i + t)
    dense.append(dense[0])
    du.append(float(n))
    S, U, L, st = resample(dense, du, STEP, True)
    attrs = {k: [] for k in ('hw', 'bank', 'curb', 'run') + SEG_KEYS}
    for u in U:
        i = int(math.floor(u)) % n
        t = u - math.floor(u)
        j = (i + 1) % n
        s = t * t * (3 - 2 * t)
        attrs['hw'].append(pts[i]['w'] + (pts[j]['w'] - pts[i]['w']) * s)
        for k in ('bank', 'curb', 'run'):
            attrs[k].append(pts[i][k] + (pts[j][k] - pts[i][k]) * s)
        for k in SEG_KEYS:
            attrs[k].append(pts[i][k])
    for ov in lay_walls or []:  # walls 覆寫：用小數 at 指定一段護牆
        key = 'wallL' if str(ov.get('side', 'L')).upper().startswith('L') else 'wallR'
        a0, a1 = float(ov['from']) % n, float(ov['to']) % n
        for k, u in enumerate(U):
            if (a0 <= u < a1) if a0 <= a1 else (u >= a0 or u < a1):
                attrs[key][k] = ov.get('type', 'none')
    st_ = Strip('main', S, U, st, attrs, True, L)
    st_.npts = n
    return st_


def sample_shortcut(main, sc, k):
    s0 = main.at_to_s(sc['from'])
    s1 = main.at_to_s(sc['to'])
    if s1 < s0:
        s1 += main.length
    A, B = main.pos_at_s(s0), main.pos_at_s(s1)
    A0, B1 = main.pos_at_s(s0 - 25), main.pos_at_s(s1 + 25)
    ctrl = [A0, A] + [game(v) for v in sc.get('via', [])] + [B, B1]
    dense, du = [], []
    for i in range(1, len(ctrl) - 2):
        for kk in range(SUB):
            dense.append(catmull(ctrl[i - 1], ctrl[i], ctrl[i + 1], ctrl[i + 2], kk / SUB))
            du.append(i - 1 + kk / SUB)
    dense.append(B)
    du.append(float(len(ctrl) - 3))
    S, U, L, st = resample(dense, du, STEP, False)
    hw = float(sc.get('w', 3.5))
    n = len(S)
    attrs = {'hw': [hw] * n, 'bank': [0.0] * n, 'curb': [0.0] * n, 'run': [SHORTCUT_RUN] * n,
             'wallL': [sc.get('wall', 'none')] * n, 'wallR': [sc.get('wall', 'none')] * n,
             'edge': [sc.get('edge', 'grass')] * n, 'gap': [False] * n, 'tunnel': [False] * n, 'viaduct': [False] * n}
    # 高度：接主線的那一頭貼著主線的路面平面，離開主線路緣石外 hw 之後 14 公尺內漸變成 via 的高度；
    # 跟主線重疊的那一段不畫（drawn=False，車在那裡就是開在主線上）
    S2, drawn, emain = [], [], []
    for p in S:
        pr = main.project(p[0], p[2], reach=4)
        d, o, a, u, bi = pr
        e = d - (main.lerp(main.hw, a, u) + main.lerp(main.curb, a, u))
        ys = main.surface_y(a, u, o)
        y = ys + (p[1] - ys) * smooth(hw, hw + 14, e)
        y += 0.03 * (1 - smooth(hw + 8, hw + 16, e))  # 跟主線路肩重疊處墊高一點，不閃面
        S2.append((p[0], y, p[2]))
        drawn.append(e >= hw)
        emain.append(e)
    st_ = Strip(f'shortcut{k}', S2, U, st, attrs, False, L)
    st_.drawn = drawn
    st_.emain = emain
    st_.surf = sc.get('surf', 'dirt')
    st_.from_s, st_.to_s = s0, s1 % main.length
    st_.index()
    return st_


def detect_crossings(strips):
    """立體交叉：兩段路在平面上重疊（含路肩）而且高差 ≥ BRIDGE_DY → 上層標成橋（前後各多 8 公尺）。
    回傳每一處交叉 [(上層名稱, 上層索引, 下層名稱, 下層索引, 高差)]，以及高差不夠的衝突清單。"""
    recs, conflicts = [], []
    for A in strips:
        for B in strips:
            for i in range(A.n):
                if A.gap[i] or not A.drawn[i] or _near_end(A, i):
                    continue
                pa = A.S[i]
                for j in B.near(pa[0], pa[2], 40):
                    if B.gap[j] or not B.drawn[j] or _near_end(B, j):
                        continue
                    if A is B:
                        dd = abs(i - j)
                        if A.closed:
                            dd = min(dd, A.n - dd)
                        if dd * A.step < 80:
                            continue
                    elif A.name != 'main' and B.name != 'main':
                        continue
                    pb = B.S[j]
                    h = math.hypot(pa[0] - pb[0], pa[2] - pb[2])
                    if h >= A.eo_max(i) + B.eo_max(j) + 1.0:
                        continue
                    dy = pa[1] - pb[1]
                    if dy >= BRIDGE_DY:
                        A.bridge[i] = True
                        recs.append((A.name, i, B.name, j, dy, h))
                    elif abs(dy) < BRIDGE_DY:
                        conflicts.append((A.name, i, B.name, j, dy, h))
    for st in strips:
        flags = list(st.bridge)
        for i in range(st.n):
            if st.bridge[i]:
                for k in range(-4, 5):
                    j = i + k
                    if st.closed:
                        j %= st.n
                    elif j < 0 or j >= st.n:
                        continue
                    flags[j] = True
        st.bridge = flags
        st.index()
    return recs, conflicts


def _near_end(st, i):
    return (not st.closed) and (st.s[i] < 40 or st.s[i] > st.length - 40)


def gap_runs(st):
    runs = []
    n = st.n
    i = 0
    seen = 0
    # 從一個非缺口點開始繞一圈
    start = next((k for k in range(n) if not st.gap[k]), None)
    if start is None:
        return runs
    k = 0
    while k < n:
        i = (start + k) % n
        if st.gap[i]:
            g0 = i
            m = 0
            while st.gap[(g0 + m) % n] and m < n:
                m += 1
            g1 = (g0 + m - 1) % n
            runs.append({'g0': g0, 'g1': g1, 'lip': (g0 - 1) % n, 'land': (g1 + 1) % n, 'count': m})
            k += m
            seen += 1
        else:
            k += 1
    return runs


def cut_junction_walls(main, sc):
    """捷徑進出口：主線那一側的護牆自動切開（捷徑離開主線前 8m 到完全分開後 10m）。"""
    sc.junctions = []
    for idx in (range(sc.n), range(sc.n - 1, -1, -1)):
        hits = []
        for k in idx:
            if sc.emain[k] > sc.hw[k] + sc.run[k] + 6:
                break
            p = sc.S[k]
            d, o, a, u, bi = main.project(p[0], p[2], reach=4)
            hits.append((main.s[a] + u * main.step, 1 if o >= 0 else -1))
        if not hits:
            continue
        side = hits[-1][1]
        base = hits[0][0]
        rel = [((v - base + main.length / 2) % main.length) - main.length / 2 for v, _ in hits]
        s0, s1 = base + min(rel) - 8, base + max(rel) + 10
        arr = main.wallR if side > 0 else main.wallL
        for i in range(main.n):
            if ((main.s[i] - s0) % main.length) <= (s1 - s0):
                arr[i] = 'none'
        sc.junctions.append((s0 % main.length, s1 % main.length, side))


def build_model(lay):
    """layout → 主線、捷徑、交叉、缺口、加速帶。"""
    pts = resolve_points(lay)
    main = sample_main(pts, lay.get('walls'))
    shortcuts = [sample_shortcut(main, sc, k) for k, sc in enumerate(lay.get('shortcuts', []))]
    for sc in shortcuts:
        cut_junction_walls(main, sc)
    strips = [main] + shortcuts
    recs, conflicts = detect_crossings(strips)
    for i in range(main.n):  # 高架：跟立體交叉的橋同一套（地形不貼、橋面板＋橋墩）
        if main.viaduct[i]:
            main.bridge[i] = True
    # 中心線跨過 hazard（熔岩、水）的路段自動做成橋（前後多 8m）；只擦到路邊的不算（產生器會把 hazard 切開）
    polys = [h['poly'] for h in lay.get('hazards', [])]
    for st in strips:
        hit = [st.drawn[i] and not st.gap[i] and any(point_in_poly(st.S[i][0], st.S[i][2], pl) for pl in polys) for i in range(st.n)]
        for i in range(st.n):
            if hit[i]:
                for k in range(-4, 5):
                    j = i + k
                    if st.closed:
                        j %= st.n
                    if 0 <= j < st.n and st.drawn[j]:
                        st.bridge[j] = True
        st.over_hazard = sum(hit)
        st.index()
    gaps = gap_runs(main)
    for g in gaps:
        lip, land = main.S[g['lip']], main.S[g['land']]
        g['pit'] = min(lip[1], land[1]) - 11.0   # 缺口底下的深谷
    boosts = []
    for b in lay.get('boost', []):
        ln = float(b.get('len', 10))
        on = b.get('on')
        if on is not None and 0 <= int(on) < len(shortcuts):  # 捷徑上的加速帶：at＝捷徑上的比例 0..1
            st = shortcuts[int(on)]
            sc = float(b['at']) * st.length
            sc = max(ln / 2 + 1, min(st.length - ln / 2 - 1, sc))
        else:
            st = main
            sc = main.at_to_s(b['at'])
        boosts.append({'s0': sc - ln / 2, 's1': sc + ln / 2, 'd': float(b.get('d', 0)), 'w': float(b.get('w', 3)), 'at': b['at'],
                       'strip': st, 'on': on})
    return {'pts': pts, 'main': main, 'shortcuts': shortcuts, 'strips': strips, 'crossings': recs,
            'conflicts': conflicts, 'gaps': gaps, 'boosts': boosts}


# ---------------------------------------------------------------- 檢查

def jump_report(main, g, v=SPEED, g_acc=GRAVITY):
    """缺口：起跳點 lip、落地點 land。回傳 (缺口水平長度, 起跳角度, 高低差, 最低車速, v 時的落點)。"""
    n = main.n
    lip, land = g['lip'], g['land']
    k = 3
    a = main.S[(lip - k) % n]
    b = main.S[lip]
    hl = math.hypot(b[0] - a[0], b[2] - a[2])
    th = math.atan2(b[1] - a[1], hl)
    L = math.hypot(main.S[land][0] - b[0], main.S[land][2] - b[2])
    drop = b[1] - main.S[land][1]
    den = 2 * math.cos(th) ** 2 * (L * math.tan(th) + drop)
    vmin = math.sqrt(g_acc * L * L / den) if den > 0 else float('inf')
    # 落點：沿落地段往前找第一個軌跡低於路面的點
    vx, vy = v * math.cos(th), v * math.sin(th)
    land_at = None
    x_acc = 0.0
    prev = b
    for m in range(1, 200):
        i = (lip + m) % n
        p = main.S[i]
        x_acc += math.hypot(p[0] - prev[0], p[2] - prev[2])
        prev = p
        t = x_acc / vx
        y = b[1] + vy * t - 0.5 * g_acc * t * t
        if not main.gap[i] and y <= p[1]:
            land_at = x_acc - L
            break
        if main.gap[i] and y < g['pit'] + 2:
            break
    return L, math.degrees(th), drop, vmin, land_at


def check(name, out_dir):
    lay = load_layout(name)
    if not is_v2(lay):
        print(f'{name}: 不是 v2 格式（points 要是物件）')
        return False
    md = build_model(lay)
    main = md['main']
    ok = True
    N = main.n
    print(f"== {name}（{lay.get('name', '')}，主題 {lay.get('theme', 'hills')}）")
    print(f"  長度 {main.length:.0f} m（取樣 {N} 點，間距 {main.step:.3f}）")
    if not 1000 <= main.length <= 2600:
        print('  ⚠ 一圈長度不在 1.0～2.6 km')
    # 彎道半徑
    radii = [(1 / max(abs(c), 1e-6), i) for i, c in enumerate(main.curv) if not main.gap[i]]
    rmin, ri = min(radii)
    need = main.hw[ri] + main.curb[ri] + 2
    flag = '' if rmin > need + 4 else '  ❌ 太急（路面會折到）'
    print(f"  最小彎道半徑 {rmin:.1f} m（第 {main.U[ri]:.2f} 點附近，半寬 {main.hw[ri]:.1f}）{flag}")
    if flag:
        ok = False
    # 寬度、側傾
    print(f"  半寬 {min(main.hw):.1f}～{max(main.hw):.1f} m；側傾 {min(main.bank):.0f}～{max(main.bank):.0f} 度")
    if min(main.hw) < 4.5:
        print('  ❌ 半寬小於 4.5')
        ok = False
    # 坡度（缺口除外）
    grades = []
    for i in range(N):
        j = (i + 1) % N
        if main.gap[i] or main.gap[j]:
            continue
        a, b = main.S[i], main.S[j]
        grades.append((abs(b[1] - a[1]) / max(math.hypot(b[0] - a[0], b[2] - a[2]), 1e-6), i))
    gmax, gi = max(grades)
    ys = [p[1] for p in main.S]
    print(f"  高低差 {max(ys) - min(ys):.1f} m；最陡 {gmax * 100:.1f}%（第 {main.U[gi]:.2f} 點附近）{'  ⚠ 超過 20%' if gmax > 0.2 else ''}")
    climb = sum(max(0.0, main.S[(i + 1) % N][1] - main.S[i][1]) for i in range(N) if not main.gap[i])
    best, cur, b_at, c_at = 0, 0, 0, 0
    for k in range(2 * N):  # 最長直線：曲率半徑 > 300m 的連續路段
        i = k % N
        if abs(main.curv[i]) < 1 / 300 and not main.gap[i]:
            if cur == 0:
                c_at = i
            cur += 1
            if best < cur <= N:
                best, b_at = cur, c_at
        else:
            cur = 0
    print(f"  總爬升 {climb:.0f} m；最長直線 {best * main.step:.0f} m（從第 {main.U[b_at]:.2f} 點起）")
    # 立體交叉
    cl = cluster(md['crossings'])
    for c in cl:
        st = '✅' if c['dy'] >= MIN_CLEAR else '❌ 高差不足 7m'
        if c['dy'] < MIN_CLEAR:
            ok = False
        print(f"  立體交叉：{c['a']} 第 {c['ia']} 點（U={md_u(md, c['a'], c['ia'])}）在 {c['b']} 第 {c['ib']} 點上方，"
              f"最小高差 {c['dy']:.1f} m {st}")
    if md['conflicts']:
        cc = cluster([(a, i, b, j, abs(dy), h) for a, i, b, j, dy, h in md['conflicts']], key_min=True)
        for c in cc:
            print(f"  ❌ 路面重疊但高差只有 {c['dy']:.1f} m：{c['a']} 第 {c['ia']} 點 × {c['b']} 第 {c['ib']} 點")
        ok = False
    nb = sum(main.bridge)
    print(f"  橋：主線 {nb} 個取樣點（{nb * main.step:.0f} m）")
    # 跳台
    for g in md['gaps']:
        L, th, drop, vmin, land = jump_report(main, g)
        good = vmin < SPEED * 0.9 and land is not None
        if not good:
            ok = False
        lt = f'{land:.1f} m' if land is not None else '掉下去'
        print(f"  跳台：缺口 {L:.1f} m（第 {main.U[g['g0']]:.2f}～{main.U[g['g1']]:.2f}），起跳角 {th:.1f} 度，"
              f"落差 {drop:.1f} m，最低車速 {vmin:.1f} m/s，{SPEED:.0f} m/s 時落在落地點後 {lt} "
              f"{'✅' if good else '❌'}")
        if not 12 <= L <= 30:
            print('  ⚠ 缺口長度不在 12～30 m')
    # 捷徑
    for sc in md['shortcuts']:
        ml = (sc.to_s - sc.from_s) % main.length
        print(f"  捷徑 {sc.name}：長 {sc.length:.0f} m（主線同一段 {ml:.0f} m），半寬 {sc.hw[0]}，"
              f"最小半徑 {min(1 / max(abs(c), 1e-6) for c in sc.curv):.0f} m")
        if sc.length >= ml:
            print('  ⚠ 捷徑沒有比較短')
    # 加速帶
    for b in md['boosts']:
        st = b['strip']
        a, u = st.locate((b['s0'] + b['s1']) / 2)
        hw = st.lerp(st.hw, a, u)
        okb = abs(b['d']) + b['w'] <= hw + 0.01
        where = st.name if st is not main else '主線'
        print(f"  加速帶 at={b['at']}（{where}）：s={b['s0']:.0f}～{b['s1']:.0f} m，d={b['d']}，半寬 {b['w']} {'✅' if okb else '❌ 超出路面'}")
        ok = ok and okb
    # hazard
    for hz in lay.get('hazards', []):
        poly = hz['poly']
        dmin = 1e9
        for k in range(len(poly)):  # 沿每條邊每 1m 檢查（不只看頂點）；橋上不算
            p0, p1 = poly[k], poly[(k + 1) % len(poly)]
            ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            for m in range(int(ln) + 1):
                t = m / max(ln, 1e-6)
                x, z = p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t
                for st in md['strips']:
                    pr = st.project(x, z, reach=6)
                    if pr and st.drawn[pr[4]] and not st.bridge[pr[4]] and not st.gap[pr[4]]:
                        d, o, a, u, bi = pr
                        if d - st.eo(a) < dmin:
                            dmin, where = d - st.eo(a), (st.name, st.U[a] if st is main else st.s[a])
        print(f"  hazard {hz['type']}：離最近的路肩外緣 {dmin:.1f} m {'✅' if dmin > 0 else '❌ 蓋到路面（%s %.2f 附近）' % where}")
        ok = ok and dmin > 0
    # 隧道、開放路肩
    tl = sum(1 for t in main.tunnel if t) * main.step
    op = sum(1 for i in range(N) if main.wallL[i] == 'none' or main.wallR[i] == 'none') * main.step
    print(f"  隧道 {tl:.0f} m；有開放路肩的路段 {op:.0f} m")
    draw(name, md, lay, out_dir)
    print(f"  俯視圖：{os.path.join(out_dir, name + '_v2.png')}")
    print('  結果：' + ('OK' if ok else '有問題'))
    return ok


def md_u(md, name, i):
    st = next(s for s in md['strips'] if s.name == name)
    return f'{st.U[i]:.2f}' if st.name == 'main' else f's={st.s[i]:.0f}'


def cluster(recs, key_min=True):
    out = []
    for a, i, b, j, dy, h in sorted(recs, key=lambda r: (r[0], r[1])):
        for c in out:
            if c['a'] == a and c['b'] == b and abs(c['ia'] - i) < 30:
                if dy < c['dy']:
                    c['dy'], c['ia'], c['ib'] = dy, i, j
                break
        else:
            out.append({'a': a, 'ia': i, 'b': b, 'ib': j, 'dy': dy})
    return out


# ---------------------------------------------------------------- 俯視圖

def png(path, w, h, px):
    raw = b''.join(b'\x00' + bytes(px[y * w * 3:(y + 1) * w * 3]) for y in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i][0], poly[i][1]
        x2, z2 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            inside = not inside
    return inside


def draw(name, md, lay, out_dir):
    main = md['main']
    allp = [p for st in md['strips'] for p in st.S]
    minx, maxx = min(p[0] for p in allp) - 40, max(p[0] for p in allp) + 40
    minz, maxz = min(p[2] for p in allp) - 40, max(p[2] for p in allp) + 40
    k = 1100 / max(maxx - minx, maxz - minz)
    W, H = int((maxx - minx) * k) + 1, int((maxz - minz) * k) + 1
    px = bytearray([226, 236, 222] * W * H)
    ys = [p[1] for p in main.S]
    y0, y1 = min(ys), max(ys)

    def put(x, z, col):
        cx, cy = int((x - minx) * k), int((z - minz) * k)
        if 0 <= cx < W and 0 <= cy < H:
            o = (cy * W + cx) * 3
            px[o:o + 3] = bytes(col)

    def disc(x, z, r, col):
        cx, cy = (x - minx) * k, (z - minz) * k
        rr = max(0.8, r * k)
        for yy in range(int(cy - rr), int(cy + rr) + 1):
            for xx in range(int(cx - rr), int(cx + rr) + 1):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= rr * rr and 0 <= xx < W and 0 <= yy < H:
                    o = (yy * W + xx) * 3
                    px[o:o + 3] = bytes(col)

    # hazard
    for hz in lay.get('hazards', []):
        poly = hz['poly']
        col = (255, 110, 40) if hz['type'] == 'lava' else (70, 150, 230)
        bx0, bx1 = min(p[0] for p in poly), max(p[0] for p in poly)
        bz0, bz1 = min(p[1] for p in poly), max(p[1] for p in poly)
        for yy in range(int((bz0 - minz) * k), int((bz1 - minz) * k) + 1):
            for xx in range(int((bx0 - minx) * k), int((bx1 - minx) * k) + 1):
                if point_in_poly(minx + xx / k, minz + yy / k, poly):
                    put(minx + xx / k, minz + yy / k, col)
    # 依高度由低到高畫（上層蓋過下層）
    items = []
    for st in md['strips']:
        for i in range(st.n):
            if st.drawn[i]:
                items.append((st.S[i][1], st, i))
    items.sort(key=lambda t: t[0])
    # 先畫地面層、再畫橋（各自先路肩後路面），橋才會蓋在下層上面
    for layer in (False, True):
        group = [t for t in items if t[1].bridge[t[2]] == layer]
        for y, st, i in group:
            p = st.S[i]
            if not st.gap[i]:
                disc(p[0], p[2], st.eo_max(i), (150, 150, 150) if st.bridge[i] else (200, 205, 196))
        for y, st, i in group:
            p = st.S[i]
            h = (y - y0) / max(1e-6, y1 - y0)
            if st.gap[i]:
                disc(p[0], p[2], st.hw[i] * 0.35, (220, 40, 40))
                continue
            if st.name != 'main':
                col = (150, 100, 60)
            elif st.tunnel[i]:
                col = (70, 70, 80)
            else:
                col = (int(70 + 170 * h), 90, int(220 - 160 * h))
            disc(p[0], p[2], st.hw[i], col)
        for y, st, i in group:
            if st.gap[i]:
                continue
            for side in (-1, 1):
                w = st.wall(i, side)
                q = st.point(i, side * st.eo(i))
                put(q[0], q[2], (20, 20, 20) if w == 'wall' else (110, 110, 110) if w == 'rail' else (40, 170, 40))
    for b in md['boosts']:
        s = b['s0']
        while s <= b['s1']:
            for dd in (b['d'] - b['w'], b['d'], b['d'] + b['w']):
                q = main.pos_at_s(s, dd)
                disc(q[0], q[2], 0.8, (255, 210, 0))
            s += 1.0
    q = main.S[0]
    for dd in range(-8, 9):
        r = main.R[0]
        disc(q[0] + r[0] * dd, q[2] + r[2] * dd, 0.9, (255, 255, 255) if dd % 2 else (0, 0, 0))
    png(os.path.join(out_dir, name + '_v2.png'), W, H, px)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    names = sys.argv[1:] or [f[:-12] for f in sorted(os.listdir(BL)) if f.endswith('_layout.json')
                             and is_v2(load_layout(f[:-12]))]
    out = os.environ.get('LAYOUT_PNG_DIR', os.path.join(ROOT, 'tmp_layout'))
    os.makedirs(out, exist_ok=True)
    bad = 0
    for nm in names:
        if not check(nm, out):
            bad += 1
    sys.exit(1 if bad else 0)
