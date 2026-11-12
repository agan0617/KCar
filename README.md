# KCar

甩尾集氣、抓小噴時機的卡丁車競速遊戲。網頁版：<https://agan0617.github.io/KCar/>（Android App 外殼在 [KCarApp](https://github.com/agan0617/KCarApp)）

五條賽道、四種模式：**競賽**（對 3 位電腦車手 Mochi、Azuki、Kinako，3 圈）、**計時賽**（3 圈）、**自由練習**、**多人連線**（最多 4 人，空位電腦補；server 架在自己的電腦，見〈多人連線〉）。

| 賽道 | 難度 | 主題 | 特色 |
|---|---|---|---|
| 椰林海灘 | ★ | 熱帶海島 | 繞著小島跑一圈：海岸傾斜掃彎（衝出去就掉進海裡）、水上木棧道、繞燈塔的大甩尾、飛越小溪的跳台、穿過椰林的沙地捷徑 |
| 櫻花古都 | ★★ | 春天和風 | 甩尾天堂：四個半徑不同的長甩彎、S 彎練換向甩；8 字路線先從城下河邊穿過、再從拱橋上跨回來；千本鳥居、五重塔、神社參道捷徑 |
| 雪國山道 | ★★★ | 雪山 | 之字爬坡兩個髮夾彎、山頂盲彎接大跳台、傾斜的下山掃彎、穿山冰隧道；橫越結冰湖的捷徑 |
| 霓虹夜城 | ★★★★ | 夜晚城市 | 270° 圓環匝道爬上高架、8 字立體交叉、直角街區與直角 S 彎、下坡大直線接急彎、地下道；窄巷捷徑 |
| 熔岩火山 | ★★★★★ | 火山 | 路窄、路旁就是熔岩：兩個飛越熔岩的跳台、連續髮夾彎爬上火山口、岩石拱橋、熔岩湖上的窄石橋捷徑 |

電腦車手用跟玩家同一套物理，也會甩尾、點煞、小噴、雙噴、放氮氣、走捷徑（走線越準越常走）；賽道越難，牠們越強（極速、小噴與雙噴準度、走線都會提高），另有輕微追趕機制（落後玩家太多會稍微加速）。

## 玩法

| 技巧 | 鍵盤（預設） | 觸控 |
|---|---|---|
| 油門／煞車 | J ／ K | 自動油門／「煞」 |
| 轉向 | A D | ◀ ▶（手指可以在兩鍵間滑） |
| **甩尾** | Space＋方向 | 按住「甩尾」＋方向 |
| **小噴** | 甩尾時先鬆 J，放開甩尾、車身回正時再按 J | 放開甩尾後按「噴」 |
| **雙噴** | 小噴後再按一次 J（時機窗內） | 再按一次「噴」 |
| **點煞** | 甩尾中短按 K | 甩尾中點「煞」 |
| **氮氣** | L | 「氮氣」 |
| 起步噴 | 倒數 GO 的瞬間按 J | GO 的瞬間按「噴」 |
| 回到賽道／暫停／調參 | R／Esc 或 P／T | 右上暫停鈕 → 設定 → 操控調參 |

**按鍵可以自己改**：首頁右上「設定」或暫停選單「設定（按鍵／調參）」，每個動作可設兩個鍵，存在這台裝置。
首頁右上「操作說明」與暫停選單「操作說明」會照目前的按鍵顯示說明（定義在 [js/controls.js](js/controls.js)）。

**重播**：比完（單機、多人都算）成績頁按「重播」，從開跑前 1.5 秒開始重播剛才那場。
控制列可以暫停（空白鍵）、0.25～4 倍速、拖時間軸（← → 跳 5 秒）、換跟拍的車（↑ ↓），Esc 回成績頁。
只留最後一場、放在記憶體（一場約 1MB，重新整理就沒了）；做法在 [js/replay.js](js/replay.js)：比賽中每 1/30 秒記下每台車畫面要用的狀態，播放時內插。

- 甩尾時側滑角越大、車速越快，集氣越快；集滿一條得到一顆氮氣（最多兩顆）
- 按甩尾鍵車子先小跳一下。甩尾中抓地力變低：方向鍵控制車頭轉多快，路線慢半拍跟上——往彎內壓＝車頭甩得更開、路線跟著收緊（轉得更急），往外拉＝車身偏角變小、走大圈（比不甩尾還緩，長彎能一路甩完）。車頭有轉動慣性，要提早一點進甩。還不夠急就點煞（短按煞車），車頭再往內甩一截、掉一點速度
- 車子有重量：懸吊會隨加速、煞車、過彎、落地晃動；上坡掉速、下坡加速，坡頂衝太快會飛起來；撞牆會把車頭彈開
- 放開甩尾後是車頭轉回前進方向（回正），路線不會往彎心切；同時按反方向回正更快
- 小噴看放開甩尾後車身回正的程度：畫面下方的時機表綠區＝完美、黃區＝普通、紅區＝太早
- 開放路肩外的草地、沙地、雪地會大幅減速；捷徑多半是土路（小幅減速），要搭配小噴、氮氣或捷徑上的加速帶才划算
- 加速帶（路面上往前流動的箭頭）一碰就加速；跳台要有速度才飛得過缺口
- 掉進海、熔岩或跳台缺口，會在最後通過的路面重生（缺口前就移到缺口後）；撞牆會掉速、車頭被彈開

## 多人連線

最多 4 人同場（座位 0～3 依序是紅、藍、綠、紫四台車），空位由電腦補滿；server 架在自己的電腦上，不用 npm install。

```
node server/server.mjs                 # 或雙擊 server\start.bat；預設埠 8787
```

server 啟動時會列出網址：

- **這台電腦**：直接開 GitHub Pages 版，首頁「多人連線」的 Server 欄填 `localhost:8787`（或留空）
- **同網路的其他電腦、手機、KCar App**：Server 欄填那台的 IP（例如 `192.168.1.5`），會自動改開 server 供應的 `http://<IP>:8787/` 網頁並連上（server 同時供應遊戲網頁，版本一定對得上）；也可以直接用瀏覽器開那個網址。App 在 server 網頁上按返回鍵回線上版
- 第一次啟動 Windows 防火牆會問要不要讓 Node.js 連網，要勾「私人網路」，其他裝置才連得進來
- GitHub Pages 是 https，瀏覽器不准它連別台電腦的 `ws://`（只有 localhost 例外），所以才要轉去 server 給的 http 網址

流程：連線 → 開新房間（房主選賽道）或輸入 4 位數房號加入 → 房主按「開始比賽」→ 大家載完賽道一起倒數。
比完回房間可以再開一場。連線比賽一律用預設操控參數（調參面板關閉），成績不列入個人紀錄。

### 同步做法

參考貪食蛇 server（partygo-server-snake）的權威 server 路線，程式在 [js/net/](js/net/)：

| 部分 | 做法 |
|---|---|
| 權威 server | [server/server.mjs](server/server.mjs) 以固定 120Hz 跑整場比賽，物理就是這個 repo 的 `kart.js`（直接 import，不用移植，兩邊天生一致）。一房一個單寫者迴圈，計時用實際經過時間追（Windows 計時器不準，晚到就一次多跑幾步） |
| 上行 | client 每一步送一筆輸入（序號、方向、油門、煞車、甩尾、「剛按下」位元），一幀打包一次；server 不信 client 報的位置，輸入值也夾回合法範圍 |
| 下行 | 30Hz 快照：每台車的完整物理狀態＋當下按著的鍵＋這位玩家的輸入處理到第幾號（ack）＋排隊長度。慢連線丟舊保新（寫不出去就跳過這張快照） |
| 自己的車 | 本地預測：按下去立刻動。快照來了就回到 server 的狀態、把還沒確認的輸入重放一次（回滾重放） |
| 對手 | 不落後畫：用快照狀態＋當下按著的鍵、以同一套物理前推到跟自己同一時刻（車與車的碰撞也照算） |
| 平滑 | 回滾造成的位置跳動交給「顯示誤差」吸收、約 0.1 秒歸零（畫面、鏡頭、特效都讀吸收後的那份） |
| 時間微調 | server 那邊每位玩家的輸入排隊目標 4 筆（約 33ms 緩衝）；client 依回報的排隊長度把模擬快慢微調 ±3% |
| 斷線／掛機 | 誰在開這台車只看「這個座位有沒有真人連著、3 秒內有沒有送輸入」：沒有就電腦代駕，回來自動接回；離開房間的座位由電腦開完 |
| 結束 | 真人都完賽（或第一位真人完賽後 30 秒）就結算，沒跑完的用平均速度估時間 |

改了 `Kart.step()` 用到的欄位，要補進 `kart.js` 的 `STATE_KEYS`，不然快照帶不到、預測會一直被校正。

測同步：server 可以模擬網路（單向延遲、抖動、快照丟包），再用無頭測試開幾個假玩家（自動駕駛開自己預測的車）跑完一場，看回滾修正量：

```
node server/server.mjs --port 8799 --lag 40 --jitter 20 --loss 0.05
node tools/nettest.mjs 4 volcano 8799      # 人數、賽道、埠；設 NETDEBUG=1 印逐段細節
```

本機實測（2 人、椰林海灘）：無網路模擬時預測幾乎零修正；單向 40ms＋抖動 20ms 下平均修正約 1cm，偶爾 33～100cm（排隊被抖動吃空、時間軸錯開 1～3 步，由顯示誤差平滑掉）。

協議（JSON 文字訊框，`ws://<host>:8787/ws`；`/version` 回目前版本、房數、人數）：

| 方向 | type | 內容 |
|---|---|---|
| C→S | `hello` | 名字、遊戲版本、協議版本（版本不同會被拒，請重新整理） |
| C→S | `list`／`create`／`join`／`leave`／`track`／`start` | 房間清單、開房（賽道）、加入（房號）、離開、房主換賽道、房主開賽 |
| C→S | `loaded` | 賽道載好了 |
| C→S | `in` | 這一幀的輸入：`[[序號, 方向, 油門, 煞車, 甩尾, 剛按下位元], …]` |
| C→S／S→C | `ping`／`pong` | 量延遲 |
| S→C | `welcome`／`rooms`／`room`／`error` | 連上、房間清單（在大廳才推）、房間狀態（每次變動整份重送）、錯誤 |
| S→C | `prep` | 開賽準備：賽道、圈數、四個座位（誰是真人） |
| S→C | `go` | 全員載好（或 15 秒），開始倒數；GO 在第 360 步 |
| S→C | `snap` | 快照（30Hz） |
| S→C | `result` | 結算：名次、時間、各圈 |

## 調操控手感

所有操控參數集中在 [js/tuning.js](js/tuning.js)。遊戲中按 **T**（或暫停選單「操控調參」）打開面板即時調，
存在這台裝置；調好按「複製參數」把有改動的值貼回來，再寫進 `tuning.js` 當預設值。

無頭模擬可以快速看參數合不合理：

```
node tools/sim.mjs tt                      # 每條賽道：甩尾＋完美小噴 vs 不甩尾的圈速
node tools/sim.mjs race volcano 10         # 競賽：玩家自動駕駛（完美／普通）對電腦的名次分布
node tools/sim.mjs tt sakura driftTurn=0.9 # 臨時改參數看效果
node tools/sim.mjs tt city sc=0           # sc=0／sc=1：自動駕駛不走／一定走捷徑
```

電腦強度在 [js/race.js](js/race.js) 的 `rivalSkill`（賽道難度 × 第幾位對手）；賽道難度用 [js/tracks.js](js/tracks.js) 的 `ai`（沒寫就是星等 `difficulty`，可以有小數）。電腦怎麼開在 [js/bot.js](js/bot.js)。

## 美術與建置

- 3D：three.js；2D 介面（首頁、HUD、觸控按鈕）：PixiJS，疊在 3D 畫布上
- **賽道**由 Blender 腳本 `tools/blender/build_track2.py` 依每條的 `tools/blender/<id>_layout.json` 產生（格式見 [TRACK_V2.md](tools/blender/TRACK_V2.md)、設計守則見 [TRACK_DESIGN.md](tools/blender/TRACK_DESIGN.md)）：逐點路寬與側傾、護牆可有可無、跳台缺口、加速帶、捷徑、立體交叉與高架（自動做橋與橋墩）、隧道、海與熔岩。同一份 layout 同時輸出模型 `assets/<id>.glb`、中心線 `assets/<id>_path.json`（圈數、名次、電腦走線、小地圖）、碰撞 `assets/<id>_col.json`（地面三角形＋護牆線段），三者永遠對得上
- **物理**用碰撞資料（[js/collision.js](js/collision.js)）：往下找車子高度以下最高的地面（橋上橋下分得開），地面種類決定減速、加速帶、重生；護牆是線段
- **場景物件庫**：`tools/blender/build_props.py` 把 CC0 素材（Kenney、Quaternius）整理成 `assets_src/props/<主題>.glb`（統一比例、修色、減面），日式物件（櫻花、鳥居、石燈籠、町家、神社、五重塔）是自製的；產生器依主題撒（同一件物件共用 mesh），車開得到的範圍內的樹、石頭、房子會加碰撞。來源清單見 [assets_src/props/LICENSE.md](assets_src/props/LICENSE.md)
- **天空**是 Poly Haven 的 HDRI 轉成的照片天空（`assets/sky/`），環境光照用同一張產生；**地面、路肩、崖壁、橋、木棧道**用 Poly Haven 照片材質處理成的細節紋路（`assets/tex/`）乘上 Blender 算的頂點色（大片深淺、坡度、磨損帶），兩個尺度混合避免看得出重複；路面是 canvas 畫的邊線與虛線疊在柏油照片上。天空圖與細節紋路由 `tools/art/` 的腳本從原檔產生；各主題的天空、霧、燈光在 [js/themes.js](js/themes.js)
- 算繪：PBR 材質（車身烤漆是透明漆層），Neutral 色調映射，柔和陰影、車底接觸陰影；
  「高畫質」另有泛光（霓虹、熔岩、車燈）、調色與 4 倍 MSAA，「省電」直接畫。設定裡切換，手機跑不順（連續 4 秒低於 40fps）會自動切到省電
- 卡丁車與駕駛（戴耳機的柴犬 Komugi，對手是同一個模型換色）由 `tools/blender/build_kart.py` 產生；車身（輪子以外）有懸吊：加速抬頭、煞車點頭、過彎側傾、落地壓縮
- 速度感：低而近的鏡頭、視角隨車速放大、加速時鏡頭被甩開、高速細微震動（參數都在調參面板「鏡頭」）；
  接近極速出現速度線與從兩側刷過的風線；高畫質另有放射狀動態模糊（中間清楚、四周糊）；風切聲隨車速變大

改賽道形狀前先檢查長度、彎道半徑、坡度、總爬升、最長直線、立體交叉高差、跳台需要的速度、hazard 有沒有蓋到路面，並出一張俯視圖：

```
python tools/check_layout2.py <id>
```

重新產生模型（需要 Blender 4.2 以上）：

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_assets.ps1 -V2                       # 全部賽道＋卡丁車
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_assets.ps1 -V2 -Track snow -NoKart   # 只重產一條
blender -b --factory-startup -P tools/blender/build_props.py -- [主題...]                          # 重產場景物件庫（素材原檔預設在 D:\GameResources\Art\KCar，別處用 --src 指定）
```

新增賽道：照 [TRACK_DESIGN.md](tools/blender/TRACK_DESIGN.md) 寫一個 `<id>_layout.json`、在 [js/tracks.js](js/tracks.js) 加一列、跑上面的指令，再用 `node tools/sim.mjs tt <id>` 與 `race <id>` 驗收。
`testbed_layout.json` 是用到所有功能的測試賽道（不在遊戲清單裡）。

App 圖示：`blender -b --factory-startup -P tools\blender\render_icon.py -- . icons\icon-512.png`

沒有建置步驟，直接用任何靜態伺服器開 `index.html`（例如 `python -m http.server`）。版號在 [js/version.js](js/version.js)，首頁右下角顯示。

## 版權

Copyright © 2026 agan0617. All rights reserved. 保留所有權利，詳見 [LICENSE](LICENSE)。

使用的第三方素材（依各自授權）：

- **three.js** r187（`lib/three/`）：MIT，見 `lib/three/LICENSE`（https://threejs.org/）
- **PixiJS** 8.22（`lib/pixi/`）：MIT，見 `lib/pixi/LICENSE`（https://pixijs.com/）
- **Blender**：只用來產生模型的工具，沒有隨附（https://www.blender.org/）
- **Kenney** 素材包（https://kenney.nl/）：CC0，場景物件（逐件來源見 `assets_src/props/LICENSE.md`）
- **Quaternius** 素材包（https://quaternius.com/）：CC0，場景物件（同上）
- **Poly Haven**（https://polyhaven.com/）：CC0，天空 HDRI（`assets/sky/`）與地面材質（`assets/tex/`）

本作品是個人製作的非官方作品，與 QQ飛車（騰訊）、瑪利歐賽車 Mario Kart（任天堂）沒有關係；相關名稱與商標屬原權利人所有。
