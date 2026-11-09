"""快速檢查賽道控制點（不用開 Blender）：長度、最小彎道半徑、自交間距、高低差，並畫一張俯視圖 PNG。
用法：python tools/check_layout.py hills beach ...（不給就全部）
"""
import json
import math
import os
import struct
import sys
import zlib

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
BL = os.path.join(ROOT, 'tools', 'blender')


def catmull(p0, p1, p2, p3, t, alpha=0.5):
    def d(a, b):
        return max(math.dist(a, b), 1e-4) ** alpha
    t0 = 0.0
    t1 = t0 + d(p0, p1)
    t2 = t1 + d(p1, p2)
    t3 = t2 + d(p2, p3)
    tt = t1 + (t2 - t1) * t

    def lerp(a, b, ta, tb):
        return [a[i] * (tb - tt) / (tb - ta) + b[i] * (tt - ta) / (tb - ta) for i in range(3)]
    a1 = lerp(p0, p1, t0, t1)
    a2 = lerp(p1, p2, t1, t2)
    a3 = lerp(p2, p3, t2, t3)
    b1 = lerp(a1, a2, t0, t2)
    b2 = lerp(a2, a3, t1, t3)
    return lerp(b1, b2, t1, t2)


def sample(lay, step=2.0):
    P = [(p[0], p[2] if len(p) > 2 else 0.0, p[1]) for p in lay['points']]
    n = len(P)
    dense = []
    for i in range(n):
        for k in range(80):
            dense.append(catmull(P[(i - 1) % n], P[i], P[(i + 1) % n], P[(i + 2) % n], k / 80))
    dense.append(dense[0])
    cum = [0.0]
    for i in range(1, len(dense)):
        cum.append(cum[-1] + math.dist(dense[i], dense[i - 1]))
    L = cum[-1]
    N = round(L / step)
    step = L / N
    S, j = [], 0
    for i in range(N):
        d = i * step
        while cum[j + 1] < d:
            j += 1
        t = (d - cum[j]) / max(cum[j + 1] - cum[j], 1e-9)
        S.append([dense[j][c] + (dense[j + 1][c] - dense[j][c]) * t for c in range(3)])
    return S, L, step


def png(path, w, h, px):
    raw = b''.join(b'\x00' + bytes(px[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def check(name, out_dir):
    lay = json.load(open(os.path.join(BL, name + '_layout.json'), encoding='utf-8'))
    S, L, step = sample(lay)
    N = len(S)
    T = []
    for i in range(N):
        a, b = S[i - 1], S[(i + 1) % N]
        dx, dz = b[0] - a[0], b[2] - a[2]
        l = math.hypot(dx, dz)
        T.append((dx / l, dz / l))
    curv = []
    for i in range(N):
        a, b = T[i - 1], T[(i + 1) % N]
        curv.append(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]) / (2 * step))
    minr = min(1 / max(abs(c), 1e-6) for c in curv)
    gap = 1e9
    for i in range(0, N, 2):
        for k in range(0, N, 2):
            dd = min(abs(i - k), N - abs(i - k))
            if dd * step < 80:
                continue
            gap = min(gap, math.hypot(S[i][0] - S[k][0], S[i][2] - S[k][2]))
    ys = [p[1] for p in S]
    grade = max(abs(S[(i + 1) % N][1] - S[i][1]) / step for i in range(N))
    need = 2 * lay['wall'] + 5
    tight = sum(1 for c in curv if 1 / max(abs(c), 1e-6) < 30) * step
    print(f"{name:8s} L={L:6.0f}m  halfW={lay['halfWidth']}  minR={minr:5.1f}m  R<30m 路段={tight:4.0f}m  "
          f"minGap={gap:5.1f}m (需>{need:.0f}) {'OK' if gap > need and minr > lay['halfWidth'] + 6 else '❌'}  "
          f"高低差={max(ys) - min(ys):4.1f}m 最陡={grade * 100:4.1f}%")
    # 俯視圖
    W = H = 360
    xs, zs = [p[0] for p in S], [p[2] for p in S]
    span = max(max(xs) - min(xs), max(zs) - min(zs)) + 60
    k = (W - 20) / span
    ox, oz = min(xs) - 30, min(zs) - 30
    px = bytearray([235, 240, 245] * W * H)
    for i, p in enumerate(S):
        cx, cy = int(10 + (p[0] - ox) * k), int(10 + (p[2] - oz) * k)
        r = max(1, int(lay['halfWidth'] * k))
        h = (p[1] - min(ys)) / max(1, max(ys) - min(ys))
        col = (int(60 + 180 * h), 70, int(200 - 150 * h)) if i > 3 else (240, 200, 0)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r and 0 <= cx + dx < W and 0 <= cy + dy < H:
                    o = ((cy + dy) * W + cx + dx) * 3
                    px[o:o + 3] = bytes(col)
    png(os.path.join(out_dir, name + '.png'), W, H, px)


if __name__ == '__main__':
    names = sys.argv[1:] or [f[:-12] for f in sorted(os.listdir(BL)) if f.endswith('_layout.json')]
    out = os.environ.get('LAYOUT_PNG_DIR', os.path.join(ROOT, 'tmp_layout'))
    os.makedirs(out, exist_ok=True)
    for nm in names:
        check(nm, out)
