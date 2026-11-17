"""斷崖海岸（規格 6.8）：8 字形。
港口起跑直線（往東）→ 右轉沿東岸海岸公路往南爬（懸崖 S 彎）→ 南端海角燈塔 180° 大甩 → 盲坡 → 下坡 S 掃彎 →
三連下坡髮夾 → 往北從高處跨過起跑直線（棧橋）→ 海蝕洞 → 跳台飛越海灣 → 北邊沙灘 → 西邊漁村窄巷 → 左轉接回起跑直線。
用法：python tools/tracks/coast.py [--sketch]  → tools/blender/coast_layout.json、tmp_layout/coast_sketch.png
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from layout_lib import Course  # noqa: E402

c = Course('coast', name='斷崖海岸', theme='beach', look='coast', difficulty=3, laps=2,
           defaults=dict(w=7.5, bank=0, curb=1.0, wallL='wall', wallR='wall', run=3.0, edge='grass'),
           note='長賽道入門（規格 6.8）。由 tools/tracks/coast.py 產生，不要手改這個檔。')

# ---- 港口起跑直線（往東）
c.go(155, y=0, tag='start', w=9.5, run=4.0)
c.turn(80, -90, y=3, tag='t1', w=8.5, bank=5)                                   # → 往南
# ---- 東岸海岸公路：懸崖邊爬坡 S 彎 ×4（往南時左手邊是海：左側低護欄、右側山坡開放）
c.go(60, y=8, tag='coast_rd', w=7.5, bank=0, wallL='rail', wallR='none', edge='grass')
c.turn(55, 45, y=13, tag='s1', bank=-6)
c.go(45, y=18)
c.turn(50, -70, y=24, tag='s2', bank=7)
c.go(70, y=29, tag='cave', tunnel=True)                                            # 海蝕洞：穿過海岬
c.turn(55, 55, y=34, tag='s3', bank=-6, tunnel=False)
c.go(40, y=38)
c.turn(60, -30, y=41, tag='s4', bank=4)
c.go(150, y=46, tag='cliff_st', bank=0, w=5.5)
c.go(60, y=52, tag='pre_light', w=8)
# ---- 南端海角燈塔 180° 大甩（最高的平台；內側草坡是捷徑①）
c.turn(70, -180, flat=True, tag='light', w=8.5, bank=6, wallL='rail', wallR='none')   # → 往北
# ---- 盲坡（先上後下）→ 下坡 S 掃彎
c.go(60, y=55, tag='crest', w=8.5, bank=0, wallL='rail', wallR='rail')
c.go(70, y=50, tag='blind', w=8)
c.turn(120, 35, y=45, tag='sweep1', bank=-9, w=8)
c.turn(120, -35, y=41, tag='sweep2', bank=9)
# ---- 三連下坡髮夾（腿往東西走，整體往北下山；髮夾本身平）
c.turn(42, 90, y=39, tag='hp_in', w=7.5, bank=-7)                                 # → 往西
c.go(95, y=31, tag='leg1', bank=0, wallL='rail', wallR='wall')
c.turn(30, -180, flat=True, tag='hp1', bank=6, w=8)                                   # → 往東
c.go(95, y=24, tag='leg2', bank=0, w=7.5)
c.turn(30, 180, flat=True, tag='hp2', bank=-6, w=8)                                   # → 往西
c.go(95, y=18, tag='leg3', bank=0, w=7.5)
c.turn(30, -180, flat=True, tag='hp3', bank=6, w=8)                                   # → 往東
c.go(60, y=16, tag='leg4', bank=0, w=7.5)
c.turn(48, 90, y=14, tag='hp_out', bank=-6, w=8)                                      # → 往北
# ---- 從高處跨過起跑直線（棧橋）→ 海蝕洞（下坡隧道）→ 出洞起跳 → 飛越海灣
c.go(None, free=True, y=10, tag='bridge', w=8, bank=0, wallL='rail', wallR='rail')
c.go(25, y=12.5, tag='ramp', w=7.5)
c.go(18, y=10, tag='jump', gap=True)
c.go(48, y=3, tag='land', w=10, wallL='none', wallR='none', edge='sand')
# ---- 北邊沙灘（開放沙地、椰林）
c.turn(70, 90, y=2, tag='beach1', w=8, bank=-6)                                 # → 往西
c.go(None, free=True, y=2, tag='beach_st', bank=0)
# ---- 西邊漁村窄巷（直角彎、全牆、半寬 5.5）
c.turn(36, 90, y=2, tag='v1', w=7, bank=0, wallL='wall', wallR='wall', run=1.0, edge='grass')  # → 往南
c.go(50, y=2, tag='v_st1')
c.turn(36, -90, y=2, tag='v2')                                                   # → 往西
c.go(45, y=2, tag='v_st2')
c.turn(36, 90, y=1, tag='v3')                                                    # → 往南
c.go(60, y=1, tag='v_out', w=7.5, run=3.0)
c.turn(45, 90, y=0, tag='final', w=8.5, bank=-6, run=4.0)                        # → 往東接起跑直線
c.go(105, y=0, tag='to_start', w=9.5, bank=0)

if '--sketch' in sys.argv:
    print(c.sketch())
    sys.exit()
c.close()
c.write()
# ---- 加速帶（4 個）
c.boost('light', 0.62, d=3.5, len=10, w=2.5)        # 燈塔大甩彎心內側
c.boost('leg4', 0.3, d=0, len=10, w=3)              # 第三個髮夾出口
c.boost('bridge', 0.9, d=0, len=12, w=3.5)          # 跳台助跑
c.boost('v_out', 0.5, d=0, len=10, w=2.5)           # 漁村出口
# ---- 捷徑①：燈塔大甩內側的草坡小徑（土路、無牆）
p0, pm, p1 = c.pos('pre_light', 0.85), c.pos('light', 0.5, d=40), c.pos('crest', 0.15)
c.shortcut('pre_light', 'crest', via=[c.pos('pre_light', 1.0, d=19), c.pos('light', 0.5, d=31), c.pos('crest', 0.0, d=19)], w=4, surf='dirt', ffrac=0.75, tfrac=0.35, edge='grass', wall='none')
# ---- 捷徑②：漁村出口的巷弄斜切最後一個左彎（土路、半寬 3.5）
c.shortcut('v_out', 'to_start', via=[c.pos('final', 0.5, d=-30)], w=3.5, surf='dirt', ffrac=0.5, tfrac=0.12, edge='grass', wall='wall')
# ---- 地標
c.prop('lighthouse', 'light', 0.5, d=-30)
c.write()
print(c.sketch())
c.report_tags()