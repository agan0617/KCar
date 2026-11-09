# KCar

甩尾集氣、抓小噴時機的卡丁車競速遊戲。網頁版：<https://agan0617.github.io/KCar/>（Android App 外殼在 [KCarApp](https://github.com/agan0617/KCarApp)）

六條賽道、三種模式：**競賽**（對 3 位電腦車手 Mochi、Azuki、Kinako，3 圈）、**計時賽**（3 圈）、**自由練習**。

| 賽道 | 難度 | 主題 | 特色 |
|---|---|---|---|
| 椰林海灘 | ★ | 小島海灘 | 路最寬、彎道最緩，幾乎不用甩尾；椰子樹、遮陽傘、燈塔 |
| 陽光山丘 | ★★ | 草原丘陵 | 上下坡、S 彎；風車、熱氣球、湖 |
| 仙人掌峽谷 | ★★★ | 沙漠 | 一個急彎、上下坡；仙人掌、紅岩柱、平頂山 |
| 雪國山道 | ★★★★ | 雪山 | 之字形爬坡、兩個髮夾彎、路較窄；雪松、雪人、小木屋 |
| 霓虹夜城 | ★★★★ | 夜晚城市 | 街區直角彎接 S 彎、護牆貼得近；高樓、霓虹、路燈 |
| 熔岩火山 | ★★★★★ | 火山 | 路最窄、連續髮夾彎、高低差 25m；熔岩池、枯樹、遠方火山口 |

電腦車手用跟玩家同一套物理，也會甩尾、小噴、雙噴、放氮氣；賽道越難，牠們越強（極速、甩尾率、小噴準度都會提高），另有輕微追趕機制（落後玩家太多會稍微加速）。

## 玩法

| 技巧 | 鍵盤 | 觸控 |
|---|---|---|
| 油門／煞車 | ↑ ／ ↓ | 自動油門／「煞」 |
| 轉向 | ← → | ◀ ▶（手指可以在兩鍵間滑） |
| **甩尾** | Shift＋方向 | 按住「甩尾」＋方向 |
| **小噴** | 甩尾時先鬆 ↑，放開甩尾、車身回正時再按 ↑ | 放開甩尾後按「噴」 |
| **雙噴** | 小噴後再按一次 ↑（時機窗內） | 再按一次「噴」 |
| **氮氣** | Ctrl 或 Space | 「氮氣」 |
| 起步噴 | 倒數 GO 的瞬間按 ↑ | GO 的瞬間按「噴」 |
| 回到賽道／暫停／調參 | R／Esc 或 P／T | 右上暫停鈕 → 操控調參 |

- 甩尾時側滑角越大、車速越快，集氣越快；集滿一條得到一顆氮氣（最多兩顆）
- 甩尾中方向往彎內壓＝內切（轉得更急），往外拉＝走大圈
- 小噴看放開甩尾後車身回正的程度：畫面下方的時機表綠區＝完美、黃區＝普通、紅區＝太早
- 出賽道外側的草地會大幅減速，撞牆掉速

## 調操控手感

所有操控參數集中在 [js/tuning.js](js/tuning.js)。遊戲中按 **T**（或暫停選單「操控調參」）打開面板即時調，
存在這台裝置；調好按「複製參數」把有改動的值貼回來，再寫進 `tuning.js` 當預設值。

無頭模擬可以快速看參數合不合理：

```
node tools/sim.mjs tt                      # 每條賽道：甩尾＋完美小噴 vs 不甩尾的圈速
node tools/sim.mjs race volcano 10         # 競賽：玩家自動駕駛（完美／普通）對電腦的名次分布
node tools/sim.mjs tt hills driftYaw=1.1   # 臨時改參數看效果
```

電腦強度在 [js/race.js](js/race.js) 的 `rivalSkill`（賽道難度 × 第幾位對手）。

## 美術與建置

- 3D：three.js；2D 介面（首頁、HUD、觸控按鈕）：PixiJS，疊在 3D 畫布上
- 模型全部由 **Blender 腳本**產生（`tools/blender/`）：賽道路面、路緣石、護牆、地形、水（湖／海／熔岩）、起終點門、看台、各主題的場景物件（重複的用 GPU instancing）；卡丁車與駕駛（戴耳機的柴犬 Komugi，對手是同一個模型換色）
- 每條賽道一個 `tools/blender/<id>_layout.json`：控制點、路寬、護牆距離、主題、湖的位置。腳本同時輸出模型 `assets/<id>.glb` 與遊戲物理用的中心線 `assets/<id>_path.json`，兩者永遠對得上
- 主題的模型顏色與場景物件在 `build_track.py` 的 `THEMES` 與 `scatter_*`；天空、霧、燈光、路面與地面紋理在 [js/themes.js](js/themes.js)
- 路面、地面紋理在遊戲裡用 canvas 畫；材質載入後換成卡通著色（toon），發光的（霓虹、窗戶、熔岩）保留自發光

改賽道形狀前先用 `python tools/check_layout.py <id>` 檢查長度、最小彎道半徑、有沒有自己撞到自己、高低差，並出一張俯視圖。

重新產生模型（需要 Blender 4.2 以上）：

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_assets.ps1                       # 全部
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_assets.ps1 -Track snow -NoKart   # 只重產一條
```

新增賽道：寫一個 `<id>_layout.json`、在 [js/tracks.js](js/tracks.js) 加一列、跑上面的指令。

App 圖示：`blender -b --factory-startup -P tools\blender\render_icon.py -- . icons\icon-512.png`

沒有建置步驟，直接用任何靜態伺服器開 `index.html`（例如 `python -m http.server`）。版號在 [js/version.js](js/version.js)，首頁右下角顯示。

## 版權

Copyright © 2026 agan0617. All rights reserved. 保留所有權利，詳見 [LICENSE](LICENSE)。

使用的第三方素材（依各自授權）：

- **three.js** r187（`lib/three/`）：MIT，見 `lib/three/LICENSE`（https://threejs.org/）
- **PixiJS** 8.22（`lib/pixi/`）：MIT，見 `lib/pixi/LICENSE`（https://pixijs.com/）
- **Blender**：只用來產生模型的工具，沒有隨附（https://www.blender.org/）

本作品是個人製作的非官方作品，與 QQ飛車（騰訊）、瑪利歐賽車 Mario Kart（任天堂）沒有關係；相關名稱與商標屬原權利人所有。
