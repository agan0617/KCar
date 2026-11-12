# Poly Haven 地面材質 → 遊戲用「細節圖」：
#   <name>.jpg      顏色細節（線性空間每個色版平均 0.5，shader 乘 2 後平均＝1，再乘主題底色×頂點色）
#   <name>_n.jpg    OpenGL 法線（縮到 512）
#   road.jpg        柏油的灰階細節（sRGB 平均 128，canvas 用 overlay 疊在路面底色上）
import numpy as np, os, sys
from PIL import Image

SRC = sys.argv[1]   # ...\polyhaven\textures
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

# 名稱: (Poly Haven id, 對比, 飽和)
SET = {
    'grass':    ('leafy_grass', 0.85, 0.55),
    'sand':     ('sand_01', 0.75, 0.5),
    'snow':     ('snow_02', 0.7, 0.4),
    'dirt':     ('dirt_floor', 0.85, 0.5),
    'rock':     ('rock_face_03', 0.9, 0.4),
    'ash':      ('burned_ground_01', 0.6, 0.5),
    'leaves':   ('forest_leaves_02', 0.85, 0.65),
    'pavement': ('asphalt_02', 0.75, 0.3),
}

def lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)

def enc(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)

W = np.array([0.2126, 0.7152, 0.0722])

def save(arr01, fn, q):
    Image.fromarray((np.clip(arr01, 0, 1) * 255 + 0.5).astype(np.uint8)).save(fn, quality=q, optimize=True)
    return os.path.getsize(fn)

total = 0
for name, (pid, con, sat) in SET.items():
    d = os.path.join(SRC, pid)
    im = np.asarray(Image.open(os.path.join(d, [f for f in os.listdir(d) if '_diff' in f and f.endswith('_1k.jpg')][0])).convert('RGB'), dtype=np.float64) / 255
    a = lin(im)
    a = a / a.reshape(-1, 3).mean(0)          # 每色版平均 1
    l = (a @ W)[..., None]
    l2 = 1 + (l - 1) * con                    # 降對比（以亮度）
    a = a * (l2 / np.maximum(l, 1e-4))
    l = (a @ W)[..., None]
    a = l + (a - l) * sat                     # 降飽和
    a = a / a.reshape(-1, 3).mean(0) * 0.5
    clip = float((a > 1).mean())
    total += save(enc(a), os.path.join(OUT, name + '.jpg'), 80)
    n = Image.open(os.path.join(d, f'{pid}_nor_gl_1k.jpg')).convert('RGB').resize((512, 512), Image.LANCZOS)
    n.save(os.path.join(OUT, name + '_n.jpg'), quality=82, optimize=True)
    total += os.path.getsize(os.path.join(OUT, name + '_n.jpg'))
    print(name, pid, 'clip', round(clip, 4))

# 路面柏油：灰階、sRGB 平均 0.5
pid = 'asphalt_track'
d = os.path.join(SRC, pid)
im = np.asarray(Image.open(os.path.join(d, [f for f in os.listdir(d) if '_diff' in f and f.endswith('_1k.jpg')][0])).convert('RGB'), dtype=np.float64) / 255
g = im @ W
g = g / g.mean()
g = 0.5 + (g - 1) * 0.42
g = g - g.mean() + 0.5
total += save(np.repeat(g[..., None], 3, 2), os.path.join(OUT, 'road.jpg'), 80)
n = Image.open(os.path.join(d, f'{pid}_nor_gl_1k.jpg')).convert('RGB').resize((512, 512), Image.LANCZOS)
n.save(os.path.join(OUT, 'road_n.jpg'), quality=82, optimize=True)
total += os.path.getsize(os.path.join(OUT, 'road_n.jpg'))
print('total KB', total // 1024)
for f in sorted(os.listdir(OUT)):
    print(f, os.path.getsize(os.path.join(OUT, f)) // 1024)
