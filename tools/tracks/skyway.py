"""天際高架（規格 6.10）：夜晚摩天大樓群的多層高架。
地面起跑直線（往東）→ 直角右彎 → 720° 左螺旋匝道爬上第一層高架 → 右轉兩次繞回、從高架上跨過起跑直線 →
大樓之間的直角連續彎 ×4（窄）→ 爬上第二層高架（全場最高）→ 助跑 → 大樓間跳台 → 360° 右螺旋下坡匝道 →
左迴轉 → 地面大道往南、從第一層高架底下穿過兩次（交流道）→ 往西閃一下 → 地下隧道 → 左長甩回起跑直線。
用法：python tools/tracks/skyway.py [--sketch]  → tools/blender/skyway_layout.json、tmp_layout/skyway_sketch.png
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from layout_lib import Course  # noqa: E402

GROUND = dict(wallL='wall', wallR='wall', run=1.0, curb=0.6, viaduct=False)
HIGH = dict(wallL='rail', wallR='rail', run=1.5, curb=0.8, viaduct=True)

c = Course('skyway', name='天際高架', theme='city', difficulty=4, laps=2,
           defaults=dict(w=7.5, bank=0, curb=0.6, wallL='wall', wallR='wall', run=1.0, edge='grass'),
           note='夜晚城市多層高架（規格 6.10）。由 tools/tracks/skyway.py 產生，不要手改這個檔。')

# ---- 地面起跑直線（往東）→ 直角右彎
c.go(180, y=0, tag='start', w=9, **GROUND)
c.turn(34, -90, y=0, tag='c1', w=8)                                              # → 往南
c.go(50, y=1, tag='to_helix', w=8)
# ---- 720° 左螺旋匝道（邊轉邊爬 30 m，上下層高差 15 m）
c.turn(34, 720, y=31, tag='helix', w=8, bank=-12, **HIGH)                         # → 往南
c.go(40, y=32, tag='l1a', bank=0)
# ---- 第一層高架：右轉兩次繞回北方，從高架上跨過起跑直線
c.turn(46, -90, y=32, tag='r1', bank=6)                                          # → 往西
c.go(50, y=32, tag='west1', bank=0)
c.turn(40, -90, y=32, tag='r2', bank=6)                                          # → 往北
c.go(95, y=33, tag='over_start', bank=0)
c.turn(150, 15, y=33, tag='os1', bank=-4)
c.turn(150, -15, y=33, tag='os2', bank=4)
# ---- 大樓之間的直角連續彎 ×4（窄、第一層高架、平的）
c.turn(40, 90, y=34, tag='z1', w=8, bank=-4)                                     # → 往西
c.go(130, y=34, tag='z_st1', w=7, bank=0)
c.turn(40, -90, y=34, tag='z2', w=8, bank=4)                                     # → 往北
c.go(40, y=34, tag='z_st2', w=7, bank=0)
c.turn(40, -90, y=34, tag='z3', w=8, bank=4)                                     # → 往東
c.go(60, y=34, tag='z_st3', w=7, bank=0)
c.turn(40, 90, y=34, tag='z4', w=8, bank=-4)                                     # → 往北
c.go(15, y=34, tag='z_out', w=7.5, bank=0)
# ---- 爬上第二層高架（最高）→ 助跑 → 跳台（落地區是下坡）
c.go(110, y=42, tag='climb2', w=8, bank=0)
c.go(50, y=42, tag='pre_run', w=10)
c.go(50, y=42, tag='runup', w=10)
c.go(25, y=45.8, tag='ramp', w=10)
c.go(17, y=42.5, tag='jump', gap=True)
c.go(75, y=35, tag='land', w=10)
c.go(30, y=32, tag='settle', w=9)
# ---- 360° 右螺旋下坡匝道（側傾、高速長甩）
c.turn(76, -360, y=12, tag='spiral', w=9, bank=10)                                # → 往北
c.go(15, y=10.5, tag='down', bank=0, w=8.5)
c.turn(90, 180, flat=True, tag='uturn', w=8.5, bank=-6)                           # → 往南
# ---- 地面大道往南：從第一層高架（直角連續彎）底下穿過
c.go(None, free=True, y=6, tag='ret_south', bank=0, **GROUND)
c.turn(120, 25, y=5, tag='ret_s1', bank=-5)
c.turn(120, -25, y=4, tag='ret_s2', bank=5)
# ---- 大樓群繞道：往西凸出一個對稱的 C 形再回到原來那條線（中間是捷徑：大樓中庭的直線土路）
c.go(40, y=3, tag='pre_b', bank=0, w=7.5)
c.turn(38, -90, y=2.5, tag='b1', bank=5, w=8)                                     # → 往西
c.go(50, y=2, tag='b_w', bank=0, w=5)                                             # 窄路段
c.turn(38, 90, y=2, tag='b2', bank=-5, w=8)                                       # → 往南
c.go(10, y=2, tag='b_st', bank=0, w=7)
c.turn(38, 90, y=2, tag='b3', bank=-5, w=8)                                       # → 往東
c.go(50, y=2, tag='b_e', bank=0, w=5)                                             # 窄路段
c.turn(38, -90, y=1.5, tag='b4', bank=5, w=8)                                     # → 往南
c.go(75, y=1, tag='pre_tun', bank=0, w=8, run=1.0)                                         # 擺正再進隧道
# ---- 地下隧道（下沉 6 m）→ 左長甩回起跑直線
c.go(90, y=-6, tag='tunnel', tunnel=True, w=8, run=1.0)
c.go(40, y=-1, tag='tun_out', tunnel=False)
c.turn(80, 90, y=0, tag='final', w=9, bank=-8)                                  # → 往東
c.go(None, free=True, y=0, tag='to_start', w=9, bank=0)

if '--sketch' in sys.argv:
    print(c.sketch())
    sys.exit()
c.close()
c.write()
# ---- 加速帶（4 個）
c.boost('l1a', 0.5, d=0, len=10, w=3)               # 螺旋匝道出口
c.boost('pre_run', 0.25, d=0, len=12, w=3.5)         # 跳台助跑道（提早一點，車速到起跳時拉平）
c.boost('spiral', 0.78, d=3.5, len=10, w=2.5)       # 下坡螺旋彎心內側
c.boost('final', 0.8, d=-3.5, len=10, w=2.5)       # 出隧道左長甩出口內側
# ---- 捷徑：C 形繞道中間穿過大樓中庭的土路（半寬 4、兩側牆）；中段跟主線平行、往東偏 19 m，兩端用約 40 m 的緩斜線分岔／匯入
a, b = c.pos('pre_b', 0.0), c.pos('pre_tun', 0.75)
c.shortcut('pre_b', 'pre_tun', via=[(a[0] + (b[0] - a[0]) * u + 42 * 4 * u * (1 - u), a[1] + (b[1] - a[1]) * u, 3 - 1.8 * u) for u in (0.15, 0.3, 0.5, 0.7, 0.85)], w=5, surf='dirt', ffrac=0.0, tfrac=0.75, wall='none', run=2)
c.write()
print(c.sketch())
c.report_tags()