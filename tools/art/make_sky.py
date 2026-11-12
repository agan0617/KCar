# 把 Poly Haven HDRI（已轉成 .npy 的線性浮點）調色、色調映射成 equirect JPG（2048x1024）給遊戲當天空。
# 用法：python -I make_sky.py <npy 目錄> <輸出目錄> [主題...]
import numpy as np, sys, os, math, json
from PIL import Image

src_dir, out_dir = sys.argv[1], sys.argv[2]
only = set(sys.argv[3:])

def az_of(v):
    return math.degrees(math.atan2(v[2], v[0]))

# 每個主題：來源、目標亮度、飽和、色調（天頂／地平線各一）、地平線以下怎麼處理、太陽方位（取自 themes.js 原本的 sunDir）
T = {
    'hills':   dict(src='kloofendal_48d_partly_cloudy_puresky', lum=0.40, sat=1.35, top=(0.85, 0.98, 1.15), hor=(1.0, 1.03, 1.06), az=az_of([-0.45, 1, 0.3]), cut=0.0),
    'beach':   dict(src='kloofendal_43d_clear_puresky', lum=0.38, sat=1.45, top=(0.8, 1.0, 1.15), hor=(0.98, 1.04, 1.06), az=az_of([0.4, 1, 0.35]), cut=0.0),
    'desert':  dict(src='kloofendal_43d_clear_puresky', lum=0.34, sat=1.25, top=(0.95, 1.0, 1.05), hor=(1.25, 1.0, 0.72), az=az_of([-0.6, 0.9, -0.2]), cut=0.0),
    'candy':   dict(src='kloofendal_48d_partly_cloudy_puresky', lum=0.48, sat=1.0, top=(1.0, 0.95, 1.12), hor=(1.18, 0.92, 1.06), az=az_of([0.3, 1, 0.4]), cut=0.0),
    'sakura':  dict(src='kloppenheim_06_puresky', lum=0.40, sat=1.15, top=(0.96, 0.95, 1.06), hor=(1.08, 0.94, 1.0), az=az_of([0.4, 1, 0.25]), cut=0.0),
    'autumn':  dict(src='autumn_field_puresky', lum=0.36, sat=1.2, top=(0.98, 1.0, 1.04), hor=(1.18, 1.0, 0.8), az=az_of([-0.5, 0.75, 0.35]), cut=0.0),
    'snow':    dict(src='kloofendal_overcast_puresky', lum=0.62, sat=1.1, top=(0.88, 0.96, 1.12), hor=(0.96, 1.0, 1.06), az=az_of([0.3, 0.8, -0.5]), cut=0.0),
    'city':    dict(src='rooftop_night', lum=0.06, sat=1.4, top=(0.55, 0.45, 1.35), hor=(1.25, 0.55, 1.15), az=az_of([0.3, 1, 0.6]), cut=0.0, clamp=4.0, stars=700, zen_dark=0.35,
                    clean=24.0, glow=(1.7, 0.75, 1.45), glow_pow=0.7),
    'harbor':  dict(src='kloofendal_43d_clear_puresky', lum=0.045, sat=1.1, top=(0.55, 0.7, 1.45), hor=(0.75, 0.9, 1.3), az=az_of([-0.4, 1, 0.5]), cut=0.0, clamp=12.0, stars=1100, zen_dark=0.45),
    'volcano': dict(src='the_sky_is_on_fire', lum=0.2, sat=1.2, top=(0.85, 0.3, 0.27), hor=(1.25, 0.55, 0.32), az=az_of([0.5, 0.8, 0.2]), cut=0.0, zen_dark=0.09,
                    clean=14.0, glow=(2.4, 1.0, 0.42), glow_pow=0.6, patch=[(236, 284, 12.0, 33.0)]),
}

def lum(a):
    return a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

def srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)

def hexc(c):
    c = srgb(np.asarray(c))
    return '#' + ''.join(f'{int(round(v * 255)):02x}' for v in c)

res = {}
for name, p in T.items():
    if only and name not in only:
        continue
    a = np.load(os.path.join(src_dir, p['src'] + '.npy')).astype(np.float32)
    H, W, _ = a.shape
    el = (0.5 - (np.arange(H) + 0.5) / H) * 180.0  # 每列仰角（度）
    # 太陽方位（未處理前找）
    L = lum(a)
    iy, ix = np.unravel_index(np.argmax(L[: H // 2]), (H // 2, W))
    sun_el = el[iy]
    sun_az = ((ix + 0.5) / W - 0.5) * 360
    # 夜空：壓掉路燈／太陽
    if 'clamp' in p:
        sky_med = np.median(L[(el > 10) & (el < 60)])
        a = np.minimum(a, sky_med * p['clamp'])
    # 曝光：仰角 10..60 度的中位亮度 → 目標
    band = (el > 10) & (el < 60)
    med = float(np.median(lum(a[band])))
    a *= p['lum'] / med
    # 有實景地面／建築的 HDRI：仰角 clean 度以下整段重畫（取 clean 那一列模糊後的顏色，往下漸變到 glow 色）
    if p.get('clean'):
        ec = p['clean']
        r = int((0.5 - ec / 180) * H)
        row = a[r - 2:r + 3].mean(axis=0)
        k = 96
        pad = np.concatenate([row[-k:], row, row[:k]])
        cs = np.cumsum(pad, axis=0)
        row = (cs[2 * k:] - cs[:-2 * k]) / (2 * k)
        row = row[:W]
        glow = np.array(p['glow'], dtype=np.float32) * float(np.median(lum(row)))
        for y in range(r, H):
            e = el[y]
            s = np.clip(e / ec, 0, 1) ** p.get('glow_pow', 1.5)
            a[y] = glow[None, :] * (1 - s) + row * s
        # 接縫上方幾列再軟化
        for i, y in enumerate(range(r - 6, r)):
            f = (i + 1) / 7
            a[y] = a[y] * (1 - f) + row * f
    # 地平線以下：換成地平線顏色（puresky 的下半是倒影；有實景地面的整片蓋掉）
    cut = p['cut']
    hb = (el > cut + 0.5) & (el < cut + 3)
    hcol = np.median(a[hb].reshape(-1, 3), axis=0)
    w = np.clip((cut + 1.5 - el) / 3.0, 0, 1)
    w = w * w * (3 - 2 * w)
    below = hcol[None, :] * (1 - 0.12 * np.clip(-el / 30, 0, 1))[:, None]
    a = a * (1 - w)[:, None, None] + below[:, None, :] * w[:, None, None]
    # 色調：依仰角在地平線色調與天頂色調之間內插；天頂可再壓暗（夜空、火山）
    t = np.clip(el / 50, 0, 1) ** 0.8
    tint = np.array(p['hor'])[None, :] * (1 - t)[:, None] + np.array(p['top'])[None, :] * t[:, None]
    zd = p.get('zen_dark', 1.0)
    dark = 1 - (1 - zd) * np.clip((el - 8) / 50, 0, 1) ** 0.9
    a *= (tint * dark[:, None])[:, None, :]
    # 飽和
    l = lum(a)[..., None]
    a = l + (a - l) * p['sat']
    a = np.maximum(a, 0)
    # 星星（夜空）
    if p.get('stars'):
        rng = np.random.default_rng(7)
        n = p['stars']
        se = np.degrees(np.arcsin(rng.uniform(math.sin(math.radians(12)), 1, n)))
        sa = rng.uniform(0, 1, n)
        br = rng.uniform(0.15, 1, n) ** 2.2
        for e, u, b in zip(se, sa, br):
            y = int((0.5 - e / 180) * H)
            x = int(u * W)
            wpx = max(1, int(round(1.4 / max(0.05, math.cos(math.radians(e))))))
            fade = min(1, (e - 12) / 15)
            col = np.array([0.85, 0.9, 1.0]) * (0.25 + 1.6 * b) * fade
            a[y, x:x + wpx] += col
            if b > 0.6 and y + 1 < H:
                a[y + 1, x:x + wpx] += col * 0.5
    # 太陽方位轉到主題的方位（水平捲動）
    shift = int(round((p['az'] - sun_az) / 360 * W))
    a = np.roll(a, shift, axis=1)
    # 局部修補（電線桿之類）：該段每列用左右兩端的顏色線性內插
    for x0, x1, e0, e1 in p.get('patch', []):
        for y in range(H):
            if e0 <= el[y] <= e1:
                l, r2 = a[y, x0 - 1].copy(), a[y, x1 + 1].copy()
                f = np.linspace(0, 1, x1 - x0 + 1)[:, None]
                a[y, x0:x1 + 1] = l * (1 - f) + r2 * f
    # 色調映射：1 以下近乎線性，亮部柔和收到 1（遊戲裡還有一層 Neutral）
    k = 0.75
    hi = a > k
    a = np.where(hi, k + (1 - k) * (1 - np.exp(-(a - k) / (1 - k))), a)
    img = (srgb(a) * 255 + 0.5).astype(np.uint8)
    os.makedirs(out_dir, exist_ok=True)
    fn = os.path.join(out_dir, name + '.jpg')
    q = 85
    while True:
        Image.fromarray(img).save(fn, quality=q, optimize=True, progressive=True)
        if os.path.getsize(fn) <= 600 * 1024 or q <= 60:
            break
        q -= 5
    # 地平線（仰角 0.5..2 度）與天頂（60..80 度）的實際顏色，給 themes.js 的霧色／天空色
    fin = np.where(hi, a, a)
    hz = np.median(a[(el > cut + 0.3) & (el < cut + 2.0)].reshape(-1, 3), axis=0)
    zn = np.median(a[(el > 55) & (el < 80)].reshape(-1, 3), axis=0)
    mid = np.median(a[(el > 12) & (el < 30)].reshape(-1, 3), axis=0)
    res[name] = dict(file=fn, kb=os.path.getsize(fn) // 1024, q=q, src=p['src'], sun_el=round(float(sun_el), 1),
                     horizon=hexc(hz), mid=hexc(mid), top=hexc(zn))
    print(name, res[name])
json.dump(res, open(os.path.join(out_dir, '_sky_info.json'), 'w'), indent=1)
