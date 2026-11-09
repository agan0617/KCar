# KCar

甩尾集氣、抓小噴時機的卡丁車競速遊戲。網頁版：<https://agan0617.github.io/KCar/>（Android App 外殼在 [KCarApp](https://github.com/agan0617/KCarApp)）

目前一條賽道〈陽光山丘賽道〉（約 1.85 公里，含上下坡、髮夾彎、S 彎），計時賽 3 圈或自由練習。

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

無頭模擬可以快速看參數合不合理（自動駕駛跑圈，比較不甩尾與甩尾＋小噴的圈速）：

```
node tools/sim.mjs 3 both
node tools/sim.mjs 3 drift driftYaw=1.1 driftGrip=2
```

## 美術與建置

- 3D：three.js；2D 介面（首頁、HUD、觸控按鈕）：PixiJS，疊在 3D 畫布上
- 模型全部由 **Blender 腳本**產生（`tools/blender/`）：賽道路面、路緣石、護牆、地形、湖、起終點門、看台、樹與花（GPU instancing）、風車、熱氣球；卡丁車與駕駛（戴耳機的柴犬 Komugi）
- 賽道形狀寫在 `tools/blender/track1_layout.json`（控制點），腳本同時輸出模型 `assets/track1.glb` 與遊戲物理用的中心線 `assets/track1_path.json`，兩者永遠對得上
- 路面、草地紋理在遊戲裡用 canvas 畫；材質載入後換成卡通著色（toon）

重新產生模型（需要 Blender 4.2 以上）：

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_assets.ps1 -Blender <blender.exe 路徑>
```

App 圖示：`blender -b --factory-startup -P tools\blender\render_icon.py -- . icons\icon-512.png`

沒有建置步驟，直接用任何靜態伺服器開 `index.html`（例如 `python -m http.server`）。版號在 [js/version.js](js/version.js)，首頁右下角顯示。

## 版權

Copyright © 2026 agan0617. All rights reserved. 保留所有權利，詳見 [LICENSE](LICENSE)。

使用的第三方素材（依各自授權）：

- **three.js** r187（`lib/three/`）：MIT，見 `lib/three/LICENSE`（https://threejs.org/）
- **PixiJS** 8.22（`lib/pixi/`）：MIT，見 `lib/pixi/LICENSE`（https://pixijs.com/）
- **Blender**：只用來產生模型的工具，沒有隨附（https://www.blender.org/）

本作品是個人製作的非官方作品，與 QQ飛車（騰訊）、瑪利歐賽車 Mario Kart（任天堂）沒有關係；相關名稱與商標屬原權利人所有。
