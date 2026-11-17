"""楓紅峽谷（規格 6.9）：8 字形。
溪谷底起跑直線（往東）→ 沿溪高速掃彎 → 右轉往南 → 三連髮夾之字坡爬上斷崖 → 崖頂楓林平台約 140° 長甩 →
吊橋往北跨過峽谷（橋下是剛才的溪邊路）→ 盲坡 → 瀑布旁下坡彎 → 岩洞（下坡隧道）→ 跳台飛越溪流 → 楓林 S 彎 → 回起跑直線。
用法：python tools/tracks/canyon.py [--sketch]  → tools/blender/canyon_layout.json、tmp_layout/canyon_sketch.png
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from layout_lib import Course  # noqa: E402

c = Course('canyon', name='楓紅峽谷', theme='autumn', difficulty=3, laps=2,
           defaults=dict(w=7.5, bank=0, curb=1.0, wallL='wall', wallR='wall', run=3.0, edge='grass'),
           note='秋天溪谷（規格 6.9）。由 tools/tracks/canyon.py 產生，不要手改這個檔。')

# ---- 溪谷底起跑直線（往東）＋沿溪高速掃彎（左手邊是溪：開放河灘）
c.go(170, y=0, tag='start', w=9.5, run=4.0)
c.turn(130, 30, y=1, tag='creek1', w=8.5, bank=-5, wallL='none', edge='sand')
c.go(50, y=2, bank=0)
c.turn(120, -45, y=2, tag='creek2', bank=6)
c.go(230, y=3, bank=0, tag='creek_st')
c.turn(130, 15, y=3, tag='creek3', bank=-3)
c.go(40, y=4, bank=0, w=8, wallL='wall')
# ---- 右轉往南、再左轉往東：進之字坡
c.turn(60, -90, y=6, tag='to_south', bank=6)                                      # → 往南
c.go(20, y=9, bank=0, tag='foot')
c.turn(56, 90, y=12, tag='to_east', bank=-6, w=8, run=5.0)                                      # → 往東
# ---- 三連髮夾之字坡（腿東西走、整體往南爬；髮夾本身平）
c.go(95, y=26, tag='leg1', bank=0, w=7.5, wallL='rail', wallR='wall', run=3.0)
c.turn(32, -180, flat=True, tag='hp1', w=8, bank=6)                               # → 往西
c.go(95, y=40, tag='leg2', bank=0, w=7.5)
c.turn(32, 180, flat=True, tag='hp2', w=8, bank=-6)                               # → 往東
c.go(95, y=53, tag='leg3', bank=0, w=7.5)
c.turn(32, -180, flat=True, tag='hp3', w=8, bank=6)                               # → 往西
# ---- 崖頂楓林平台：緩坡到頂 → 約 140° 長甩（內側碎石坡是捷徑①）
c.go(None, free=True, y=55, tag='plateau', bank=0, w=8, wallL='wall', wallR='wall')
c.turn(150, 50, y=61, tag='plat_l', bank=-3, w=8.5, run=3.0)
c.turn(80, -140, flat=True, tag='long', w=9, bank=7, wallL='rail', wallR='none', run=5.0)  # → 往北
# ---- 吊橋往北跨過峽谷（窄、兩側護欄；橋下是溪邊路）
c.go(60, y=62, tag='bridge_in', w=8.5, bank=0, wallL='rail', wallR='rail', run=3.0)
c.go(180, y=60, tag='bridge', w=6, run=1.0)
c.turn(100, 35, y=60, tag='after1', w=7.5, run=3.0, bank=-5, wallL='wall', wallR='wall')
c.turn(100, -35, y=61, tag='after2', bank=5)
c.go(150, y=61, tag='crest', bank=0, w=5.5)                                               # 盲坡（坡頂平、下坡緩）
# ---- 瀑布旁下坡彎（左彎；內側瀑布後窄岩縫是捷徑②）→ 岩洞（下坡隧道）
c.go(90, y=53, tag='pre_fall', w=7.5, wallL='none', wallR='rail')
c.turn(85, 130, y=42, tag='fall', w=8, bank=-7, wallL='none')                                   # → 往西北
c.go(70, y=36, tag='cave_in', bank=0, wallL='wall')
c.turn(150, -40, y=27, tag='cave', tunnel=True, w=7.5, bank=4)                    # 岩洞：緩右彎下坡
c.go(40, y=25, tag='cave_out', tunnel=False, bank=0)
# ---- 跳台飛越溪流（上坡起跳 → 缺口 → 著陸坡）
c.go(25, y=27.5, tag='ramp', w=8)
c.go(16, y=24.5, tag='jump', gap=True)
c.go(50, y=22, tag='land', w=10, wallL='none', wallR='none', edge='grass')
c.go(45, y=16, tag='runout', w=9)
# ---- 楓林 S 彎（下坡）→ 左轉往南 → 左轉往東接回起跑直線
c.turn(70, 40, y=15, tag='forest1', w=8, bank=-6, wallL='wall', wallR='wall')
c.go(40, y=13, bank=0)
c.turn(70, -40, y=11, tag='forest2', bank=6)
c.go(35, y=10, bank=0, tag='forest_st')
c.turn(60, 90, y=8, tag='to_south2', bank=-6, w=8.5)                                    # → 往南
c.go(None, free=True, y=5, bank=0, tag='descent')
c.turn(58, 90, y=1, tag='final', bank=-6, w=9)                                 # → 往東
c.go(100, y=0, tag='to_start', w=9.5, bank=0, run=4.0)

if '--sketch' in sys.argv:
    print(c.sketch())
    sys.exit()
c.close()
c.write()
# ---- 加速帶（4 個）
c.boost('hp1', 0.6, d=3.5, len=10, w=2.5)           # 第一個髮夾彎心內側
c.boost('long', 0.8, d=3.5, len=10, w=2.5)          # 崖頂長甩出口內側
c.boost('after2', 0.7, d=0, len=10, w=2.5)          # 過吊橋後
c.boost('cave_out', 0.5, d=0, len=12, w=3.5)        # 跳台助跑
# ---- 捷徑②：瀑布後的窄岩縫（土路、窄、兩側岩壁），切瀑布左彎的內側；高度沿兩端線性內插
ya, yb = c.pos('pre_fall', 0.65)[2], c.pos('cave_in', 0.35)[2]
vias = [c.pos('fall', f, d=dd) for f, dd in ((0.0, -22), (0.5, -37), (1.0, -19))]
vias = [(x, z, ya + (yb - ya) * k) for (x, z, _), k in zip(vias, (0.2, 0.5, 0.8))]
c.shortcut('pre_fall', 'cave_in', via=vias, w=3.5, surf='dirt', ffrac=0.65, tfrac=0.35, edge='grass', wall='none')# ---- 溪：沿溪邊路左側（開放河灘外）
segs = [('start', f / 4) for f in range(2, 5)] + [(tg, f / 4) for tg in ('creek1', 'creek2', 'creek_st', 'creek3') for f in range(0, 5)]
inner = [c.pos(tg, f, d=-18) for tg, f in segs]
outer = [c.pos(tg, f, d=-46) for tg, f in segs]
c.hazard('water', [(p[0], p[1]) for p in inner] + [(p[0], p[1]) for p in reversed(outer)], y=-1.5)
c.write()
print(c.sketch())
c.report_tags()