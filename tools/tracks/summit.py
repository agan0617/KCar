"""雲海絕嶺（規格 6.12）：最難最長。
山腳湖畔起跑（往東）→ 松林高速 S 彎 → 左轉往北進山 → 五連髮夾之字山道（左右交替、往北爬）→ 山中隧道 →
稜線窄路 → 山頂 180° 盲彎（往南）→ 助跑 → 大跳台飛越峽谷 → 下山傾斜高速掃彎 ×3 → 盲坡 →
石拱橋跨過進山的松林路 → 湖南岸 → 繞回起跑直線。
用法：python tools/tracks/summit.py [--sketch]  → tools/blender/summit_layout.json、tmp_layout/summit_sketch.png
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from layout_lib import Course  # noqa: E402

c = Course('summit', name='雲海絕嶺', theme='hills', look='summit', difficulty=5, laps=2,
           defaults=dict(w=7.5, bank=0, curb=1.0, wallL='wall', wallR='wall', run=3.0, edge='grass'),
           note='最難最長（規格 6.12）。由 tools/tracks/summit.py 產生，不要手改這個檔。')

# ---- 山腳湖畔起跑直線（往東；右手邊是湖）
c.go(130, y=0, tag='start', w=9.5, run=4.0)
# ---- 松林高速 S 彎
c.turn(130, 35, y=2, tag='forest1', w=8.5, bank=-6)
c.go(60, y=3, tag='forest_st', bank=0)
c.turn(130, -35, y=4, tag='forest2', bank=6)
c.go(50, y=5, tag='forest_out', bank=0)
# ---- 左轉往北進山（這段會被下山的石拱橋跨過）
c.turn(60, 90, y=8, tag='enter', w=8, bank=-6)                                   # → 往北
c.go(50, y=12, tag='approach', bank=0)
# ---- 五連髮夾之字山道（腿東西向、往北爬；髮夾平、腿 13～15%）
c.turn(40, 90, y=15, tag='zz_in', bank=-5)                                       # → 往西
c.go(120, y=27, tag='leg1', w=7.5, bank=0, wallL='wall', wallR='rail')
c.turn(32, -180, y=33, tag='hp1', w=9, bank=6)                              # → 往東
c.go(88, y=43, tag='leg2', w=7.5, bank=0)
c.turn(33, 180, y=50, tag='hp2', w=9, bank=-6)                              # → 往西
c.go(68, y=58, tag='leg3', w=7.5, bank=0)
c.turn(35, -180, y=65, tag='hp3', w=10, bank=6)                              # → 往東
c.go(70, y=72, tag='leg4', w=7.5, bank=0)
c.turn(33, 180, y=79, tag='hp4', w=9, bank=-6)                              # → 往西
c.go(67, y=86, tag='leg5', w=7.5, bank=0)
c.turn(35, -180, y=93, tag='hp5', w=10, bank=6)                              # → 往東
c.go(56, y=97, tag='leg6', w=7.5, bank=0)
c.turn(45, 90, y=99, tag='zz_out', bank=-5)                                     # → 往北
# ---- 山中隧道
c.go(60, y=104, tag='mtn_rd', bank=0, w=7.5)
c.go(92, y=112, tag='tunnel', tunnel=True)
# ---- 稜線窄路（右側懸崖低護欄、左側開放碎石坡）
c.turn(100, -40, y=119, tag='ridge1', tunnel=False, w=5.5, bank=4, wallL='none', wallR='rail', edge='dirt', run=4.0)
c.go(130, y=128, tag='ridge_st', bank=0)
c.turn(100, 40, y=133, tag='ridge2', bank=-4)
c.go(55, y=139, tag='ridge_top', bank=0, w=7.5, wallL='wall', wallR='wall', run=2.0)                    # 盲坡：上山頂前的緩坡頂（低速、兩側牆、直線）
c.go(35, y=138.5, tag='crest')
# ---- 山頂雲海觀景台 180° 盲彎（內側岩壁擋視線）
c.turn(45, -180, flat=True, tag='summit', w=8.5, bank=6, wallL='rail', wallR='wall', edge='grass', run=3.0)   # → 往南
# ---- 助跑直線 → 大跳台飛越峽谷 → 著陸坡
c.go(50, y=138, tag='runup', w=8, bank=0, wallL='rail', wallR='rail')
c.go(25, y=140.2, tag='ramp')
c.go(19, y=136.5, tag='jump', gap=True)
c.go(40, y=134, tag='land', w=10)
c.go(50, y=126.5, tag='land2')
# ---- 下山傾斜高速掃彎 ×3
c.turn(125, -45, y=117, tag='sweep1', w=10, bank=14, wallL='wall', wallR='wall')
c.go(60, y=111, tag='sweep_st1', bank=0, wallL='none', wallR='wall')
c.turn(160, 80, y=98, tag='sweep2', bank=-15, wallL='none')
c.go(60, y=93, tag='sweep_st2', bank=0, wallL='none')
c.turn(160, -50, y=83, tag='sweep3', bank=12, wallL='wall', wallR='wall', run=1.0)
c.go(None, free=True, y=77, tag='descent', bank=0, w=9.5, run=4.0, wallR='none', edge='grass')
# ---- 下山直線（原規劃的盲坡：高速下坡時坡頂會把車彈過護牆，改成一路緩降）
c.go(60, y=71, tag='down_st')
# ---- 右轉往西、石拱橋跨過進山的松林路（approach）
c.turn(110, -75, y=60, tag='to_bridge', bank=8, w=9, run=3.0, wallR='rail')                              # → 往西
c.go(230, y=30, tag='bridge', bank=0, wallL='wall', wallR='wall')
# ---- 左轉往南、再從起跑區的松林上方跨過去，下到湖南岸
c.turn(90, 90, y=21, tag='down1', bank=-7, w=10)                                       # → 往南
c.go(150, y=9, tag='bridge2', bank=0, w=8.5)
c.turn(60, -90, y=5, tag='lake_s', bank=6, wallL='wall', wallR='none')          # → 往西（右手邊是湖）
c.go(None, free=True, y=3, tag='lake_st', bank=0, w=8.5)
# ---- 湖西端繞回起跑直線（右轉往北、再右轉往東）
c.turn(65, -90, y=1, tag='lake_w', bank=7, w=10)                                       # → 往北
c.go(20, y=0, tag='lake_n', bank=0)
c.turn(65, -90, y=0, tag='final', bank=7, w=10)                                   # → 往東
c.go(50, y=0, tag='to_start', bank=0, w=9.5)
if '--sketch' in sys.argv:
    print(c.sketch())
    sys.exit()
c.close()
c.write()
# ---- 加速帶（5 個）
c.boost('leg2', 0.35, d=0, len=10, w=2.5)             # 第一個髮夾出口後
c.boost('leg5', 0.3, d=0, len=10, w=2.5)              # 第四個髮夾出口後
c.boost('sweep_st1', 0.5, d=0, len=10, w=3)          # 第一、二個掃彎之間
c.boost('lake_st', 0.5, d=0, len=10, w=3)            # 湖南岸直線
c.boost('to_start', 0.2, d=0, len=10, w=3)           # 湖畔長甩出口
# ---- 捷徑①：髮夾道東側的碎石陡坡直上（跳過第四、第五個髮夾），接回隧道前的山路
SHORTCUT1 = '--sc1' in sys.argv   # 碎石坡捷徑：自動駕駛走不了（轉不過分岔、撞邊界牆、會卡住），預設不加，待重新設計
if SHORTCUT1:
    # 髮夾道東側：從第四段（往東）南側分出、繞到第四個髮夾外側往北爬，接回隧道前的山路（跳過第四、五個髮夾）
    E, Z, A = c.pos('leg4', 1.0), c.pos('mtn_rd', 0.0), c.pos('leg4', 0.25)
    c.shortcut('leg4', 'mtn_rd', via=[(E[0] - 14, E[1] + 32, A[2] + 0.5), (E[0] + 42, E[1] + 38, A[2] + 2), (E[0] + 94, E[1] + 12, A[2] + 4),
                                      (E[0] + 104, E[1] - 50, A[2] + 9), (E[0] + 96, E[1] - 112, A[2] + 15), (Z[0] + 37, Z[1] + 6, Z[2] - 6), (Z[0] + 19, Z[1] - 27, Z[2])],
               w=5, surf='dirt', ffrac=0.25, tfrac=0.9, edge='dirt', wall='none')
# ---- 捷徑②：下山林道（從第二個掃彎內側直穿松林，無牆）
c.shortcut('sweep_st1', 'sweep_st2', via=[c.pos('sweep2', 0.5, d=-58)], w=4.5, surf='dirt', ffrac=0.5, tfrac=0.5, edge='grass', wall='none')
# ---- 山腳的湖（起跑直線、湖南岸、湖西端、石拱橋下坡圍起來的那一塊）
c.hazard('water', [(-22, 36), (170, 36), (176, 60), (170, 100), (-22, 100), (-30, 68)], y=-1.5)
c.write()
print(c.sketch())
c.report_tags()