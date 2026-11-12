// 各主題的天空、霧、燈光與地面／路面紋理顏色（模型本身的顏色在 Blender 腳本的 THEMES）。
// env：環境光照強度；exposure：曝光；bloom：[強度, 半徑, 門檻]（高畫質才有泛光）
// 天空圖：assets/sky/<主題 id>.jpg（Poly Haven CC0 HDRI 調色後的 equirect，tools/art/make_sky.py（Blender 讀 HDR：tools/art/hdr2npy.py） 產生；來源寫在各主題的 sky 註解）。
//   horizon＝天空圖地平線的實際顏色（霧也用它，遠景才會融進天空）；skyTop＝天空圖中段的顏色（沒有天空圖時的漸層備用）；
//   sunDir＝天空圖裡太陽的方位與高度（陰影方向跟天空對得上；天空的太陽太低時燈光抬高到 30～40 度、加強度，免得地面整片變暗）；skyGain：天空亮度倍率
// ground.tex：地面照片細節圖（assets/tex/<名稱>.jpg，Poly Haven CC0；乘上 base 與 Blender 頂點色）；
//   tex2：頂點色不偏綠的地方（磨損帶、沙土）換用的第二張；沒寫 tex 就用程式畫的紋理（ground.dots）

export const THEMES = {
  // sky：kloofendal_48d_partly_cloudy_puresky（少雲晴天）
  hills: {
    env: 0.6, exposure: 1.0, bloom: [0.3, 0.4, 1.0],
    skyTop: '#85ade8', horizon: '#b4c2da', fog: [380, 1500],
    hemi: ['#dff1ff', '#5f8f3f', 1.25], sun: ['#fff6e6', 2.6], sunDir: [-0.56, 0.74, 0.37],
    ground: { base: '#7ccf52', dots: ['rgba(90,170,60,0.55)', 'rgba(150,220,95,0.5)', 'rgba(70,140,50,0.6)'], blade: true, tex: 'grass', tex2: 'dirt' },
    road: { base: '#6a7080', speck: [90, 140], edge: '#f4f4f4', center: 'rgba(255,255,255,0.85)' },
  },
  // sky：kloofendal_43d_clear_puresky（萬里無雲，調得更藍）
  beach: {
    env: 0.6, exposure: 1.0, bloom: [0.3, 0.4, 1.0],
    skyTop: '#71b4f5', horizon: '#c0dbf3', fog: [480, 1900],
    hemi: ['#eaf8ff', '#e2cf9a', 1.35], sun: ['#fff6e0', 2.7], sunDir: [0.55, 0.68, 0.48],
    ground: { base: '#f0d595', dots: ['rgba(255,240,200,0.6)', 'rgba(215,180,110,0.5)', 'rgba(250,225,160,0.5)'], tex: 'sand' },
    road: { base: '#757b88', speck: [100, 150], edge: '#ffffff', center: 'rgba(255,255,255,0.85)' },
  },
  // sky：kloofendal_43d_clear_puresky（地平線調成暖色的沙塵）
  desert: {
    env: 0.6, exposure: 1.0, bloom: [0.3, 0.4, 1.0],
    skyTop: '#89a9cf', horizon: '#d4ccc0', fog: [360, 1500],
    hemi: ['#fff0dc', '#b97a45', 1.25], sun: ['#fff0d0', 2.9], sunDir: [-0.69, 0.68, -0.23],
    ground: { base: '#e2a865', dots: ['rgba(240,190,120,0.6)', 'rgba(190,130,70,0.5)', 'rgba(255,215,160,0.45)'], tex: 'sand' },
    road: { base: '#7c7068', speck: [105, 150], edge: '#fff3e0', center: 'rgba(255,230,180,0.85)' },
  },
  // sky：kloofendal_overcast_puresky（陰天＝下雪天；太陽弱、天空光強，陰影淡）
  snow: {
    env: 0.8, exposure: 1.0, bloom: [0.25, 0.4, 1.05],
    skyTop: '#bac7e2', horizon: '#aab2c2', fog: [260, 1200],
    hemi: ['#f0f6ff', '#c3d2e6', 1.55], sun: ['#f4f8ff', 1.85], sunDir: [0.3, 0.8, -0.5],
    ground: { base: '#f2f6fb', dots: ['rgba(210,225,245,0.7)', 'rgba(255,255,255,0.8)', 'rgba(190,210,235,0.5)'], tex: 'snow' },
    road: { base: '#5d6472', speck: [85, 130], edge: '#ffffff', center: 'rgba(255,255,255,0.85)' },
  },
  // sky：rooftop_night（只取仰角 24 度以上的夜空，以下重畫成紫紅的城市光暈＋星星）
  city: {
    env: 1.1, exposure: 1.0, bloom: [0.6, 0.4, 0.95],
    night: true,
    skyTop: '#4c215f', horizon: '#5a1f5c', fog: [220, 950],
    hemi: ['#6574b8', '#16161f', 0.75], sun: ['#aab8ff', 0.9], sunDir: [0.3, 1, 0.6],
    ground: { base: '#3b404c', dots: ['rgba(70,76,92,0.7)', 'rgba(40,44,54,0.6)', 'rgba(90,96,110,0.4)'], tex: 'pavement' },
    road: { base: '#3f4350', speck: [55, 95], edge: '#f4f4f4', center: 'rgba(255,214,0,0.9)' },
  },
  // sky：the_sky_is_on_fire（火燒雲；壓暗成紅黑，地平線以下的建築重畫成熔岩光）
  volcano: {
    env: 0.75, exposure: 1.0, bloom: [0.65, 0.4, 0.92],
    skyTop: '#81403c', horizon: '#b4501c', fog: [230, 1100],
    hemi: ['#ffb08c', '#2a1a1a', 0.9], sun: ['#ffb27a', 1.9], sunDir: [0.5, 0.8, 0.2],
    ground: { base: '#3d3436', dots: ['rgba(30,24,26,0.7)', 'rgba(80,66,68,0.5)', 'rgba(120,50,30,0.35)'], tex: 'ash' },
    road: { base: '#4a4446', speck: [60, 100], edge: '#ffccbc', center: 'rgba(255,140,60,0.9)' },
  },
  // sky：kloppenheim_06_puresky（傍晚的金色雲；陽光放低、偏暖）
  sakura: {
    env: 0.65, exposure: 1.0, bloom: [0.3, 0.4, 1.0],
    skyTop: '#a0b7e3', horizon: '#b4a6aa', fog: [380, 1500],
    hemi: ['#fff0f6', '#8fbf6a', 1.35], sun: ['#ffe6cc', 2.9], sunDir: [0.73, 0.5, 0.46],
    // 草地上散著粉紅、白色的落花（照片材質模式下沒有）
    ground: { base: '#9ccc65', dots: ['rgba(110,170,70,0.55)', 'rgba(255,170,205,0.8)', 'rgba(255,236,244,0.85)'], tex: 'grass', tex2: 'dirt' },
    road: { base: '#6e6a76', speck: [95, 140], edge: '#ffffff', center: 'rgba(255,255,255,0.85)' },
  },
  // sky：autumn_field_puresky
  autumn: {
    env: 0.6, exposure: 1.0, bloom: [0.3, 0.4, 1.0],
    skyTop: '#83c2f3', horizon: '#eef2ee', fog: [340, 1400],
    hemi: ['#fff0dc', '#8a6a3a', 1.3], sun: ['#ffe0b0', 3.0], sunDir: [-0.65, 0.62, 0.45],
    // 乾草地上的紅、橘落葉
    ground: { base: '#b39b4c', dots: ['rgba(205,85,40,0.6)', 'rgba(235,150,40,0.6)', 'rgba(140,110,50,0.5)'], tex: 'leaves' },
    road: { base: '#6a6560', speck: [95, 140], edge: '#fff3e0', center: 'rgba(255,235,200,0.85)' },
  },
  // sky：kloofendal_48d_partly_cloudy_puresky（調成粉紫）
  candy: {
    env: 0.65, exposure: 1.0, bloom: [0.32, 0.4, 1.0],
    skyTop: '#aab6eb', horizon: '#cabbd9', fog: [420, 1600],
    hemi: ['#fff0fa', '#f6b6d6', 1.4], sun: ['#fff8f0', 2.4], sunDir: [0.4, 0.74, 0.54],
    // 粉紅糖霜上撒彩色糖粒（沒有合適的照片材質，維持程式畫的）
    ground: { base: '#ffdff0', dots: ['rgba(255,160,205,0.55)', 'rgba(140,230,200,0.65)', 'rgba(140,190,255,0.7)'] },
    road: { base: '#7a5f78', speck: [110, 160], edge: '#ffffff', center: 'rgba(255,220,240,0.9)' },
  },
  // sky：kloofendal_43d_clear_puresky（壓暗成深藍夜空，太陽當月亮＋星星）
  harbor: {
    env: 1.1, exposure: 1.0, bloom: [0.6, 0.4, 0.95],
    night: true,
    skyTop: '#24375f', horizon: '#3f4c66', fog: [240, 1100],
    hemi: ['#6f86c0', '#141a24', 0.8], sun: ['#c8d6ff', 0.95], sunDir: [-0.46, 0.68, 0.57],
    ground: { base: '#454a55', dots: ['rgba(70,76,90,0.7)', 'rgba(38,42,52,0.6)', 'rgba(95,100,112,0.4)'], tex: 'pavement' },
    road: { base: '#3c404c', speck: [55, 95], edge: '#f4f4f4', center: 'rgba(255,214,0,0.9)' },
  },
};
