// 各主題的天空、霧、燈光與地面／路面紋理顏色（模型本身的顏色在 Blender 腳本的 THEMES）。
// env：環境光照強度；exposure：曝光；bloom：[強度, 半徑, 門檻]（高畫質才有泛光）

export const THEMES = {
  hills: {
    env: 0.55, exposure: 1.0, bloom: [0.3, 0.4, 1.0],
    skyTop: '#3d9bff', horizon: '#d9f1ff', fog: [380, 1500],
    hemi: ['#dff1ff', '#5f8f3f', 1.35], sun: ['#fffaf0', 2.4], sunDir: [-0.45, 1, 0.3],
    ground: { base: '#7ccf52', dots: ['rgba(90,170,60,0.55)', 'rgba(150,220,95,0.5)', 'rgba(70,140,50,0.6)'], blade: true },
    road: { base: '#6a7080', speck: [90, 140], edge: '#f4f4f4', center: 'rgba(255,255,255,0.85)' },
  },
  beach: {
    env: 0.55, exposure: 1.0, bloom: [0.3, 0.4, 1.0],
    skyTop: '#22a6ff', horizon: '#e6f8ff', fog: [480, 1900],
    hemi: ['#eaf8ff', '#e2cf9a', 1.45], sun: ['#fff6e0', 2.6], sunDir: [0.4, 1, 0.35],
    ground: { base: '#f0d595', dots: ['rgba(255,240,200,0.6)', 'rgba(215,180,110,0.5)', 'rgba(250,225,160,0.5)'] },
    road: { base: '#757b88', speck: [100, 150], edge: '#ffffff', center: 'rgba(255,255,255,0.85)' },
  },
  desert: {
    env: 0.55, exposure: 1.0, bloom: [0.3, 0.4, 1.0],
    skyTop: '#3f95e3', horizon: '#ffe6c0', fog: [360, 1500],
    hemi: ['#fff0dc', '#b97a45', 1.3], sun: ['#fff0d0', 2.9], sunDir: [-0.6, 0.9, -0.2],
    ground: { base: '#e2a865', dots: ['rgba(240,190,120,0.6)', 'rgba(190,130,70,0.5)', 'rgba(255,215,160,0.45)'] },
    road: { base: '#7c7068', speck: [105, 150], edge: '#fff3e0', center: 'rgba(255,230,180,0.85)' },
  },
  snow: {
    env: 0.5, exposure: 0.9, bloom: [0.25, 0.4, 1.05],
    skyTop: '#78aee6', horizon: '#eef4fb', fog: [260, 1200],
    hemi: ['#f0f6ff', '#c3d2e6', 1.4], sun: ['#ffffff', 1.9], sunDir: [0.3, 0.8, -0.5],
    ground: { base: '#f2f6fb', dots: ['rgba(210,225,245,0.7)', 'rgba(255,255,255,0.8)', 'rgba(190,210,235,0.5)'] },
    road: { base: '#5d6472', speck: [85, 130], edge: '#ffffff', center: 'rgba(255,255,255,0.85)' },
  },
  city: {
    env: 1.2, exposure: 1.0, bloom: [0.55, 0.35, 1.0],
    night: true,
    skyTop: '#04061a', horizon: '#2c1b52', fog: [220, 950],
    hemi: ['#6574b8', '#16161f', 0.75], sun: ['#aab8ff', 0.9], sunDir: [0.3, 1, 0.6],
    ground: { base: '#3b404c', dots: ['rgba(70,76,92,0.7)', 'rgba(40,44,54,0.6)', 'rgba(90,96,110,0.4)'] },
    road: { base: '#3f4350', speck: [55, 95], edge: '#f4f4f4', center: 'rgba(255,214,0,0.9)' },
  },
  volcano: {
    env: 1.0, exposure: 1.0, bloom: [0.6, 0.4, 0.95],
    skyTop: '#3b1410', horizon: '#d8642e', fog: [230, 1100],
    hemi: ['#ffb894', '#2a1a1a', 0.95], sun: ['#ffb27a', 1.9], sunDir: [0.5, 0.8, 0.2],
    ground: { base: '#3d3436', dots: ['rgba(30,24,26,0.7)', 'rgba(80,66,68,0.5)', 'rgba(120,50,30,0.35)'] },
    road: { base: '#4a4446', speck: [60, 100], edge: '#ffccbc', center: 'rgba(255,140,60,0.9)' },
  },
  sakura: {
    env: 0.55, exposure: 1.0, bloom: [0.3, 0.4, 1.0],
    skyTop: '#6fb2f5', horizon: '#ffe8f2', fog: [380, 1500],
    hemi: ['#fff0f6', '#8fbf6a', 1.35], sun: ['#fff4ec', 2.4], sunDir: [0.4, 1, 0.25],
    // 草地上散著粉紅、白色的落花
    ground: { base: '#9ccc65', dots: ['rgba(110,170,70,0.55)', 'rgba(255,170,205,0.8)', 'rgba(255,236,244,0.85)'] },
    road: { base: '#6e6a76', speck: [95, 140], edge: '#ffffff', center: 'rgba(255,255,255,0.85)' },
  },
  autumn: {
    env: 0.55, exposure: 1.0, bloom: [0.3, 0.4, 1.0],
    skyTop: '#4f8fdc', horizon: '#ffe2bf', fog: [340, 1400],
    hemi: ['#fff0dc', '#8a6a3a', 1.3], sun: ['#ffe0b0', 2.5], sunDir: [-0.5, 0.75, 0.35],
    // 乾草地上的紅、橘落葉
    ground: { base: '#b39b4c', dots: ['rgba(205,85,40,0.6)', 'rgba(235,150,40,0.6)', 'rgba(140,110,50,0.5)'] },
    road: { base: '#6a6560', speck: [95, 140], edge: '#fff3e0', center: 'rgba(255,235,200,0.85)' },
  },
  candy: {
    env: 0.6, exposure: 1.0, bloom: [0.32, 0.4, 1.0],
    skyTop: '#7fc0ff', horizon: '#ffe3f5', fog: [420, 1600],
    hemi: ['#fff0fa', '#f6b6d6', 1.45], sun: ['#fff8f0', 2.4], sunDir: [0.3, 1, 0.4],
    // 粉紅糖霜上撒彩色糖粒
    ground: { base: '#ffdff0', dots: ['rgba(255,160,205,0.55)', 'rgba(140,230,200,0.65)', 'rgba(140,190,255,0.7)'] },
    road: { base: '#7a5f78', speck: [110, 160], edge: '#ffffff', center: 'rgba(255,220,240,0.9)' },
  },
  harbor: {
    env: 1.15, exposure: 1.0, bloom: [0.55, 0.35, 1.0],
    night: true,
    skyTop: '#030817', horizon: '#173556', fog: [240, 1100],
    hemi: ['#6f86c0', '#141a24', 0.8], sun: ['#c8d6ff', 0.95], sunDir: [-0.4, 1, 0.5],
    ground: { base: '#454a55', dots: ['rgba(70,76,90,0.7)', 'rgba(38,42,52,0.6)', 'rgba(95,100,112,0.4)'] },
    road: { base: '#3c404c', speck: [55, 95], edge: '#f4f4f4', center: 'rgba(255,214,0,0.9)' },
  },
};
