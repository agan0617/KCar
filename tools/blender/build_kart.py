"""產生卡丁車與駕駛（戴耳機的柴犬 Komugi）。

用法（在 repo 根目錄）：
  <Blender>\\blender.exe -b --factory-startup -P tools\\blender\\build_kart.py -- .
輸出 assets\\kart.glb。車頭朝 +Z（遊戲座標）、原點在地面中心。
three.js 端靠物件名稱找零件：Body、Driver、Wheel_FL/FR/RL/RR（原點在輪心，可轉）、Exhaust_L/R（排氣口位置）。
材質名稱也有用：KartRed、Hoodie、ShibaFur、ShibaCream 是對手換色的對象；KartRed 等是烤漆。
"""
import bpy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Builder, M, box, cone, cylinder, empty, export_glb, mat, reset_scene, sphere, torus  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ROOT = os.path.abspath(argv[0] if argv else '.')
reset_scene()

red = mat('KartRed', '#e8322b', rough=0.35)
white = mat('KartWhite', '#f7f7f7', rough=0.4)
black = mat('KartBlack', '#1d1d1f', rough=0.7)
carbon = mat('KartCarbon', '#2b2d33', rough=0.45, metal=0.3)
metal = mat('KartMetal', '#c9d1d9', rough=0.22, metal=0.9)
gold = mat('KartGold', '#f2b21b', rough=0.3, metal=0.8)
yellow = mat('KartYellow', '#ffcc1a', rough=0.4)
tire_m = mat('KartTire', '#222222', rough=0.92)
light_m = mat('KartLight', '#fff6d6', emit=2.0)
tail_m = mat('KartTail', '#ff2a2a', emit=1.6)
glow_m = mat('ExhaustGlow', '#ff8a2a', emit=1.2)
fur = mat('ShibaFur', '#e39a4f', rough=0.9)
cream = mat('ShibaCream', '#fff4e2', rough=0.9)
nose_m = mat('ShibaNose', '#1a1a1a', rough=0.3)
eye_hi = mat('EyeShine', '#ffffff', emit=0.6)
hoodie = mat('Hoodie', '#22a699', rough=0.8)
phone = mat('Headphone', '#2b2f36', rough=0.3, metal=0.4)
phone2 = mat('HeadphoneAccent', '#7fe3d4', rough=0.35)
tongue = mat('Tongue', '#ff7a8a', rough=0.6)

HALF_PI = math.pi / 2

# ---------------------------------------------------------------- 車身（硬殼：導圓角）
shell = Builder('Body')
shell.add(box(1.02, 0.14, 2.1), carbon, M((0, 0.19, 0)))                              # 底盤
shell.add(box(1.36, 0.08, 0.42), carbon, M((0, 0.2, 1.05)))                          # 前擾流板
shell.add(box(0.5, 0.06, 0.62), white, M((0, 0.56, 0.78)))                           # 車頭白條
shell.add(box(1.3, 0.07, 0.38), red, M((0, 1.06, -1.06)))                            # 尾翼
shell.add(box(1.32, 0.04, 0.08), white, M((0, 1.11, -0.9)))
for sx in (-1, 1):
    shell.add(box(0.06, 0.5, 0.42), red, M((0.66 * sx, 1.0, -1.06)))                 # 尾翼側板
    shell.add(box(0.05, 0.44, 0.22, base=True), carbon, M((0.36 * sx, 0.62, -1.02)))  # 尾翼支架
    shell.add(box(0.08, 0.1, 1.0), carbon, M((0.62 * sx, 0.18, -0.05)))              # 側裙
shell.add(box(0.62, 0.36, 0.42), metal, M((0, 0.44, -0.92)))                         # 引擎
for i in range(3):
    shell.add(box(0.66, 0.03, 0.4), carbon, M((0, 0.5 + i * 0.07, -0.92)))           # 散熱片
shell.add(box(0.66, 0.14, 0.55), black, M((0, 0.36, -0.32)))                         # 座墊
shell.add(box(0.66, 0.62, 0.12), black, M((0, 0.62, -0.6), rot=(-0.25, 0, 0)))       # 椅背
shell.add(box(0.7, 0.08, 0.14), red, M((0, 0.92, -0.67), rot=(-0.25, 0, 0)))         # 椅背頂飾條
shell.add(box(1.2, 0.12, 0.14), white, M((0, 0.26, -1.18)))                          # 後保險桿
shell.build(bevel=(0.025, 3))

# ---------------------------------------------------------------- 車身（曲面：圓頭、側箱、葉子板）
body = Builder('BodyCurves')
body.add(sphere(0.5, 24, 16), red, M((0, 0.34, 0.78), scale=(1.15, 0.5, 1.05)))     # 圓車頭
body.add(cylinder(0.075, 1.36, 16), white, M((0.68, 0.24, 1.2), rot=(0, 0, HALF_PI)))  # 前保險桿
for sx in (-1, 1):
    body.add(sphere(0.4, 20, 12), red, M((0.55 * sx, 0.34, -0.05), scale=(0.8, 0.62, 2.0)))   # 側箱
    body.add(sphere(0.12, 12, 8), black, M((0.62 * sx, 0.38, 0.32), scale=(0.6, 0.9, 1.6)))   # 側箱進氣口
    # 前葉子板：半圈弧蓋在前輪上
    body.add(torus(0.36, 0.06, 18, 8, arc=math.pi), red, M((0.66 * sx, 0.29, 0.72), rot=(0, HALF_PI, 0)) @ M(scale=(1, 1, 2.2)))
    body.add(torus(0.42, 0.07, 18, 8, arc=math.pi), red, M((0.7 * sx, 0.34, -0.72), rot=(0, HALF_PI, 0)) @ M(scale=(1, 1, 2.6)))
    body.add(sphere(0.07, 12, 8), light_m, M((0.26 * sx, 0.42, 1.22), scale=(1.3, 0.8, 0.6)))  # 大燈
    body.add(sphere(0.05, 10, 6), tail_m, M((0.4 * sx, 0.3, -1.26), scale=(1.4, 0.8, 0.5)))    # 尾燈
    body.add(cylinder(0.075, 0.42, 14), metal, M((0.18 * sx, 0.52, -1.08), rot=(HALF_PI, 0, 0)) @ M((0, -0.42, 0)))  # 排氣管
    body.add(cylinder(0.09, 0.06, 14), metal, M((0.18 * sx, 0.52, -1.5), rot=(HALF_PI, 0, 0)))   # 尾管口
    body.add(cylinder(0.055, 0.02, 12), glow_m, M((0.18 * sx, 0.52, -1.52), rot=(HALF_PI, 0, 0)))
body.add(cylinder(0.035, 0.55, 10), metal, M((0, 0.32, 0.62), rot=(-0.95, 0, 0)))  # 方向盤柱
body.add(torus(0.17, 0.035, 24, 8), black, M((0, 0.72, 0.36), rot=(-0.6, 0, 0)))  # 方向盤
body.add(cylinder(0.05, 0.03, 12), gold, M((0, 0.72, 0.36), rot=(-0.6 + HALF_PI, 0, 0)))
body.add(cylinder(0.13, 0.02, 20), white, M((0, 0.37, 1.32), rot=(HALF_PI, 0, 0)))  # 號碼牌底
body.add(cylinder(0.1, 0.022, 20), red, M((0, 0.37, 1.333), rot=(HALF_PI, 0, 0)))
body.build()

# ---------------------------------------------------------------- 駕駛：Komugi
drv = Builder('Driver')
drv.add(sphere(0.3, 20, 14), hoodie, M((0, 0.32, 0), scale=(1.05, 1.15, 0.85)))     # 身體
drv.add(torus(0.22, 0.06, 18, 8), hoodie, M((0, 0.62, -0.06), rot=(HALF_PI, 0, 0)))   # 帽兜領口
for sx in (-1, 1):
    drv.add(cylinder(0.075, 0.64, 10), hoodie, M((0.24 * sx, 0.5, 0.05), rot=(1.84, 0, 0)))  # 手臂
    drv.add(sphere(0.085, 10, 8), cream, M((0.22 * sx, 0.33, 0.68)))                         # 手掌
drv.add(sphere(0.32, 24, 16), fur, M((0, 0.88, 0.02), scale=(1.08, 0.95, 1.0)))       # 頭
drv.add(sphere(0.2, 18, 12), cream, M((0, 0.8, 0.22), scale=(1.0, 0.72, 1.0)))        # 口鼻
drv.add(sphere(0.06, 10, 6), tongue, M((0, 0.72, 0.35), scale=(1.0, 0.5, 0.8)))       # 舌頭
for sx in (-1, 1):
    drv.add(sphere(0.12, 14, 10), cream, M((0.17 * sx, 0.82, 0.18)))                 # 臉頰
    drv.add(sphere(0.046, 12, 8), nose_m, M((0.12 * sx, 0.95, 0.28)))                # 眼睛
    drv.add(sphere(0.014, 6, 4), eye_hi, M((0.11 * sx + 0.012, 0.965, 0.318)))       # 眼睛高光
    drv.add(sphere(0.05, 8, 6), cream, M((0.12 * sx, 1.02, 0.27), scale=(1.4, 0.5, 0.6)))  # 白眉
    drv.add(cone(0.13, 0.24, 14, smooth=True), fur, M((0.19 * sx, 1.1, -0.02), rot=(0, 0, -0.32 * sx)))  # 耳朵
    drv.add(cone(0.07, 0.15, 10, smooth=True), cream, M((0.19 * sx, 1.12, 0.03), rot=(0, 0, -0.32 * sx)))
    drv.add(cylinder(0.12, 0.09, 24), phone, M((0.31 * sx, 0.9, 0), rot=(0, 0, -HALF_PI * sx)))  # 耳罩
    drv.add(cylinder(0.075, 0.1, 20), phone2, M((0.35 * sx, 0.9, 0), rot=(0, 0, -HALF_PI * sx)))
    drv.add(torus(0.12, 0.025, 20, 6), phone2, M((0.31 * sx, 0.9, 0), rot=(0, HALF_PI, 0)))
drv.add(sphere(0.045, 10, 8), nose_m, M((0, 0.86, 0.4)))                             # 鼻頭
drv.add(torus(0.37, 0.032, 28, 8, arc=math.pi), phone, M((0, 0.9, -0.02)))           # 耳機頭帶
drv.build(origin=(0, 0.42, -0.36), local=True)

# ---------------------------------------------------------------- 輪子（原點在輪心）：圓胖輪胎＋五爪鋁圈
WHEELS = {'FL': (0.66, 0.29, 0.72, 0.29, 0.26), 'FR': (-0.66, 0.29, 0.72, 0.29, 0.26),
          'RL': (0.7, 0.34, -0.72, 0.34, 0.36), 'RR': (-0.7, 0.34, -0.72, 0.34, 0.36)}
for name, (x, y, z, r, w) in WHEELS.items():
    wb = Builder('Wheel_' + name)
    tr = w * 0.5
    # 輪胎：甜甜圈（軸朝 X），外徑＝r
    wb.add(torus(r - tr * 0.85, tr, 28, 12), tire_m, M(rot=(0, HALF_PI, 0)) @ M(scale=(1, 1, 1.0)))
    wb.add(cylinder(r * 0.66, w * 0.9, 24), metal, M((-(w * 0.9) / 2, 0, 0), rot=(0, 0, -HALF_PI)))  # 鋁圈
    side = 1 if x > 0 else -1
    for k in range(5):
        a = k * 2 * math.pi / 5
        wb.add(box(0.04, r * 1.1, 0.07), yellow, M((side * w * 0.46, 0, 0), rot=(a, 0, 0)))  # 輪輻
    wb.add(cylinder(r * 0.2, w * 0.98, 16), gold, M((-(w * 0.98) / 2, 0, 0), rot=(0, 0, -HALF_PI)))  # 輪轂
    wb.build(origin=(x, y, z), local=True)

empty('Exhaust_L', (0.18, 0.52, -1.52))
empty('Exhaust_R', (-0.18, 0.52, -1.52))

os.makedirs(os.path.join(ROOT, 'assets'), exist_ok=True)
out = os.path.join(ROOT, 'assets', 'kart.glb')
export_glb(out)
print(f'[kart] wrote {out} ({os.path.getsize(out) // 1024} KB)')
