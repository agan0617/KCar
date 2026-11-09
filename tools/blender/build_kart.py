"""產生卡丁車與駕駛（戴耳機的柴犬 Komugi）。

用法（在 repo 根目錄）：
  <Blender>\\blender.exe -b --factory-startup -P tools\\blender\\build_kart.py -- .
輸出 assets\\kart.glb。車頭朝 +Z（遊戲座標）、原點在地面中心。
three.js 端靠物件名稱找零件：Body、Driver、Wheel_FL/FR/RL/RR（原點在輪心，可轉）、Exhaust_L/R（排氣口位置）。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Builder, M, box, cone, cylinder, empty, export_glb, mat, reset_scene, sphere, torus  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ROOT = os.path.abspath(argv[0] if argv else '.')
reset_scene()

red = mat('KartRed', '#e8322b', rough=0.45)
white = mat('KartWhite', '#f7f7f7', rough=0.5)
black = mat('KartBlack', '#1d1d1f', rough=0.8)
metal = mat('KartMetal', '#c9d1d9', rough=0.25, metal=0.8)
yellow = mat('KartYellow', '#ffcc1a', rough=0.5)
tire_m = mat('KartTire', '#222222', rough=0.95)
fur = mat('ShibaFur', '#e39a4f', rough=0.9)
cream = mat('ShibaCream', '#fff4e2', rough=0.9)
nose_m = mat('ShibaNose', '#1a1a1a', rough=0.4)
hoodie = mat('Hoodie', '#22a699', rough=0.85)
phone = mat('Headphone', '#2b2f36', rough=0.4)
phone2 = mat('HeadphoneAccent', '#7fe3d4', rough=0.4)

HALF_PI = math.pi / 2

# ---------------------------------------------------------------- 車身
body = Builder('Body')
body.add(box(1.0, 0.12, 2.1), black, M((0, 0.2, 0)))                      # 底盤
body.add(sphere(0.5, 16, 10), red, M((0, 0.34, 0.78), scale=(1.15, 0.5, 1.05)))  # 圓車頭
body.add(box(0.5, 0.06, 0.62), white, M((0, 0.55, 0.78)))                    # 車頭白條
body.add(cylinder(0.08, 1.36, 10), white, M((0.68, 0.24, 1.18), rot=(0, 0, HALF_PI)))  # 前保險桿
for sx in (-1, 1):
    body.add(sphere(0.4, 14, 8), red, M((0.55 * sx, 0.34, -0.05), scale=(0.8, 0.62, 2.0)))  # 側箱
    body.add(cylinder(0.07, 0.42, 8), metal, M((0.18 * sx, 0.52, -1.08), rot=(HALF_PI, 0, 0)) @ M((0, -0.42, 0)))  # 排氣管
    body.add(box(0.05, 0.42, 0.24, base=True), black, M((0.5 * sx, 0.62, -1.02)))  # 尾翼支架
body.add(box(1.3, 0.07, 0.36), red, M((0, 1.05, -1.06)))                   # 尾翼
body.add(box(1.32, 0.03, 0.06), white, M((0, 1.09, -0.9)))
body.add(box(0.62, 0.38, 0.42), metal, M((0, 0.42, -0.92)))                # 引擎
body.add(box(0.66, 0.14, 0.55), black, M((0, 0.36, -0.32)))                # 座墊
body.add(box(0.66, 0.62, 0.12), black, M((0, 0.62, -0.6), rot=(-0.25, 0, 0)))  # 椅背
body.add(cylinder(0.035, 0.55, 8), metal, M((0, 0.32, 0.62), rot=(-0.95, 0, 0)))  # 方向盤柱
body.add(torus(0.17, 0.035, 18, 6), black, M((0, 0.72, 0.36), rot=(-0.6, 0, 0)))  # 方向盤
body.add(cylinder(0.11, 0.02, 14), white, M((0, 0.37, 1.32), rot=(HALF_PI, 0, 0)))  # 號碼牌底
body.build()

# ---------------------------------------------------------------- 駕駛：Komugi
drv = Builder('Driver')
drv.add(sphere(0.3, 14, 9), hoodie, M((0, 0.32, 0), scale=(1.05, 1.15, 0.85)))     # 身體
for sx in (-1, 1):
    # 手臂：肩膀到方向盤
    drv.add(cylinder(0.075, 0.64, 8), hoodie, M((0.24 * sx, 0.5, 0.05), rot=(1.84, 0, 0)))
    drv.add(sphere(0.085, 8, 6), cream, M((0.22 * sx, 0.33, 0.68)))            # 手掌
drv.add(sphere(0.32, 18, 12), fur, M((0, 0.88, 0.02), scale=(1.08, 0.95, 1.0)))   # 頭
drv.add(sphere(0.2, 14, 9), cream, M((0, 0.8, 0.22), scale=(1.0, 0.72, 1.0)))     # 口鼻
for sx in (-1, 1):
    drv.add(sphere(0.12, 10, 7), cream, M((0.17 * sx, 0.82, 0.18)))           # 臉頰
    drv.add(sphere(0.043, 8, 6), nose_m, M((0.12 * sx, 0.95, 0.28)))          # 眼睛
    drv.add(sphere(0.05, 8, 6), cream, M((0.12 * sx, 1.02, 0.27), scale=(1.4, 0.5, 0.6)))  # 眉毛（柴犬的白眉）
    drv.add(cone(0.13, 0.24, 10, smooth=True), fur, M((0.19 * sx, 1.1, -0.02), rot=(0, 0, -0.32 * sx)))  # 耳朵
    drv.add(cone(0.07, 0.15, 8, smooth=True), cream, M((0.19 * sx, 1.12, 0.03), rot=(0, 0, -0.32 * sx)))
    drv.add(cylinder(0.12, 0.09, 16), phone, M((0.31 * sx, 0.9, 0), rot=(0, 0, -HALF_PI * sx)))  # 耳罩
    drv.add(cylinder(0.075, 0.1, 14), phone2, M((0.35 * sx, 0.9, 0), rot=(0, 0, -HALF_PI * sx)))
drv.add(sphere(0.045, 8, 6), nose_m, M((0, 0.86, 0.4)))                        # 鼻頭
drv.add(torus(0.37, 0.032, 20, 6, arc=math.pi), phone, M((0, 0.9, -0.02)))      # 耳機頭帶
drv.build(origin=(0, 0.42, -0.36), local=True)

# ---------------------------------------------------------------- 輪子（原點在輪心）
WHEELS = {'FL': (0.66, 0.29, 0.72, 0.29, 0.26), 'FR': (-0.66, 0.29, 0.72, 0.29, 0.26),
          'RL': (0.7, 0.34, -0.72, 0.34, 0.36), 'RR': (-0.7, 0.34, -0.72, 0.34, 0.36)}
for name, (x, y, z, r, w) in WHEELS.items():
    wb = Builder('Wheel_' + name)
    wb.add(cylinder(r, w, 18), tire_m, M((-w / 2, 0, 0), rot=(0, 0, -HALF_PI)))
    wb.add(cylinder(r * 0.55, w + 0.02, 12), yellow, M((-(w + 0.02) / 2, 0, 0), rot=(0, 0, -HALF_PI)))
    wb.add(box(w + 0.05, r * 1.5, 0.08), metal, M((0, 0, 0)))  # 輪輻：看得出在轉
    wb.build(origin=(x, y, z), local=True)

empty('Exhaust_L', (0.18, 0.52, -1.52))
empty('Exhaust_R', (-0.18, 0.52, -1.52))

os.makedirs(os.path.join(ROOT, 'assets'), exist_ok=True)
out = os.path.join(ROOT, 'assets', 'kart.glb')
export_glb(out)
print(f'[kart] wrote {out} ({os.path.getsize(out) // 1024} KB)')
