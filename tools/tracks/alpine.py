"""雪峰速降（規格 6.11）：山頂纜車站起跑 → 下坡連續傾斜掃彎 → 滑雪跳台 1 → 雪松林 S 彎 → 冰洞隧道 → 谷底冰湖長甩 →
滑雪跳台 2 → 谷底 → 螺旋隧道（1.5 圈爬升）→ 之字坡髮夾 ×3 → 稜線窄路（盲坡）→ 山頂 180° 大甩 → 回起跑直線。
用法：python tools/tracks/alpine.py [--sketch]  → tools/blender/alpine_layout.json、tmp_layout/alpine_sketch.png
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from layout_lib import Course  # noqa: E402

TOP = 110.0
c = Course('alpine', name='雪峰速降', theme='snow', look='alpine', difficulty=4, laps=2, y0=TOP,
           defaults=dict(w=7.5, bank=0, curb=1.0, wallL='wall', wallR='wall', run=3.0, edge='snow'),
           note='長賽道（規格 6.11）。由 tools/tracks/alpine.py 產生，不要手改這個檔。')

# ---- 山頂纜車站起跑直線（往東，平）
c.go(140, y=TOP, tag='start', w=9.5, run=4.0)
c.turn(260, -14, y=TOP - 6, tag='drop', w=9)
# ---- 下坡連續傾斜掃彎（兩個右彎接一個左彎；彎道坡度放緩、陡的放在直線上）
c.turn(110, -16, y=101, tag='b1', bank=16, w=9, wallR='none')                   # 捷徑①分岔口：內側開放
c.turn(110, -40, y=95, tag='b1x', wallR='wall')
c.go(50, y=87, tag='b1b2', bank=0)
c.turn(105, -75, y=76, tag='b2', bank=17)
c.go(55, y=68, tag='b2b3', bank=0, w=8.5, wallR='none')                           # 捷徑①接回處：內側開放
c.turn(110, 105, y=58, tag='b3', bank=-17, wallR='wall')
c.go(30, y=55, tag='pre_j1', bank=0, w=8.5)
# ---- 滑雪跳台 1
c.go(25, y=57.5, tag='ramp1', w=9)
c.go(18, y=52, tag='jump1', gap=True)
c.go(55, y=45, tag='land1', w=10, wallL='none', wallR='none')
# ---- 雪松林 S 彎（開放雪地）
c.turn(90, 40, y=36, tag='forest1', w=8, bank=-8, wallL='none', wallR='none')
c.turn(80, -85, y=32, tag='forest2', bank=9)
c.go(25, y=30, tag='forest3', bank=0)
c.turn(80, 15, y=28.5, tag='forest4', bank=-4, wallL='wall', wallR='wall')
# ---- 冰洞隧道（下坡）
c.go(70, y=21, tag='cave', tunnel=True, w=7.5, bank=0)
c.go(40, y=15, tag='cave_out', tunnel=False)
# ---- 谷底冰湖長甩（內側是冰湖，捷徑②是湖中土堤）
c.turn(62, -150, y=11, tag='lake', w=8.5, bank=8, wallL='rail', wallR='rail')
c.go(60, y=9, tag='pre_j2', w=8.5, bank=0, wallL='wall', wallR='wall')
# ---- 滑雪跳台 2
c.go(25, y=12.5, tag='ramp2', w=9)
c.go(14, y=10, tag='jump2', gap=True)
c.go(60, y=3, tag='land2', w=10)
c.go(60, y=1.5, tag='valley_in', w=8.5)
c.turn(150, -50, y=1, tag='valley', w=9, bank=10)                                # → 往北
c.go(90, y=1, tag='valley_st', bank=0)
c.turn(110, 35, y=1, tag='valley_s1', bank=-8)
c.go(62, y=1, tag='valley_s2', bank=0, w=5.5, wallL='rail', wallR='rail')                # 窄路段（半寬 5.5，規格 6.1）
c.turn(110, -35, y=1, tag='valley_s3', bank=8, w=8.5, wallL='wall', wallR='wall')
c.go(None, free=True, y=1, tag='valley_end', bank=0)
# ---- 螺旋隧道（山腹內 1.5 圈左螺旋，爬升 40 m）
c.turn(46, 540, y=41, tag='spiral', w=8, bank=-8, wallL='rail', wallR='rail')
c.go(40, y=44, tag='spiral_out', bank=0, wallL='wall', wallR='wall')
# ---- 之字坡髮夾 ×3（螺旋出口往南；腿南北向、往西排開，避開螺旋；髮夾平）
c.go(90, y=53, tag='zlegA', w=7.5, bank=0)                                      # 往南
c.turn(36, -180, flat=True, tag='hp1', w=9, bank=7)                              # 右 → 往北
c.go(90, y=65, tag='zlegB', w=7.5, bank=0)
c.turn(36, 180, flat=True, tag='hp2', w=9, bank=-7)                              # 左 → 往南
c.go(90, y=77, tag='zlegC', w=7.5, bank=0)
c.turn(36, -180, flat=True, tag='hp3', w=9, bank=7)                              # 右 → 往北
c.go(70, y=86, tag='zlegD', w=7.5, bank=0)# ---- 稜線窄路（兩側懸崖低護欄、盲坡）
c.turn(110, 18, y=90, tag='ridge1', w=7, bank=-4, wallL='rail', wallR='rail', run=1.5)
c.go(110, y=99, tag='ridge_st', bank=0, w=6)
c.go(55, y=104, tag='ridge_crest')
c.go(55, y=103, tag='ridge_blind')
c.turn(80, -18, y=105, tag='ridge2', bank=4)
c.go(60, y=107, tag='pre_top', w=8, bank=0, wallL='wall', wallR='wall', run=3.0)
# ---- 山頂 180° 大甩（往北 → 往南）→ 左轉往東接起跑直線
c.turn(55, -180, y=TOP, tag='top', w=9, bank=8)
c.go(40, y=TOP, tag='top_out', bank=0)
c.turn(82, 90, y=TOP, tag='final', w=9, bank=-7)                                 # → 往東
c.go(None, free=True, y=TOP, tag='to_start', w=9.5, bank=0, run=4.0)
if '--sketch' in sys.argv:
    print(c.sketch())
    sys.exit()
c.close()
c.write()
# ---- 加速帶（5 個）
c.boost('pre_j1', 0.5, d=0, len=12, w=3.5)          # 跳台 1 助跑
c.boost('lake', 0.7, d=4, len=10, w=2.5)             # 冰湖長甩彎心內側
c.boost('zlegB', 0.3, d=0, len=10, w=3)             # 髮夾爬坡段（第一個髮夾出口）
c.boost('spiral_out', 0.5, d=0, len=10, w=3)         # 螺旋隧道出口
c.boost('top_out', 0.4, d=0, len=10, w=3)            # 山頂大甩出口
# ---- 捷徑①：滑雪道直下（雪地陡坡、土路），切掉 b1、b2 兩個右傾斜彎的內側
# 弦線直切；路面寬、兩側開放雪地（沒有護欄端點可以撞），接回 b2 後的直線
_a, _b = c.pos('b1', 0.42), c.pos('b2b3', 0.25, d=27)
_l = lambda k: tuple(_a[n] + (_b[n] - _a[n]) * k for n in range(3))  # noqa: E731
c.shortcut('b1', 'b2b3', via=[_l(0.3), _l(0.55), _l(0.8), _b], w=7, surf='dirt', ffrac=0.42, tfrac=0.9, edge='snow', wall='none')
# ---- 捷徑②：橫越冰湖的窄土堤（兩側是水）
c.shortcut('lake', 'lake', via=[c.pos('lake', 0.5, d=38)], w=4, surf='dirt', ffrac=0.06, tfrac=0.94, edge='snow', wall='rail')
# 冰湖：土堤兩側各一片水（湖面比路面低）
ly = c.pos('lake', 0.5)[2] - 1.5
c.hazard('water', [c.pos('lake', f, d=17)[:2] for f in (0.26, 0.38, 0.5, 0.62, 0.74)] + [c.pos('lake', 0.5, d=27)[:2]], y=ly)
c.hazard('water', [c.pos('lake', 0.3, d=48)[:2], c.pos('lake', 0.5, d=46)[:2], c.pos('lake', 0.7, d=48)[:2], c.pos('lake', 0.5, d=80)[:2]], y=ly)
# ---- 地標
c.prop('cabin', 'start', 0.35, d=-20, rot=90)        # 山頂纜車站（小屋）
c.prop('ice_spikes', 'lake', 0.5, d=-30)              # 冰湖外側的冰柱
c.write()
print(c.sketch())
c.report_tags()