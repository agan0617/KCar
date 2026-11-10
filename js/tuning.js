// 操控參數：全部集中在這裡，調參面板（T 鍵）即時改、存在這台裝置的 localStorage。
// 調到滿意的數字後按「複製參數」貼回來，就能寫成新的預設值。

export const DEFS = [
  ['車速', [
    ['maxSpeed', '極速 (m/s)', 18, 55, 0.5, 40],
    ['accel', '加速度', 4, 40, 0.5, 20],
    ['brake', '煞車', 5, 60, 1, 28],
    ['reverseMax', '倒車極速', 2, 15, 0.5, 8],
    ['coastDrag', '放油減速', 0, 15, 0.5, 4],
  ]],
  ['轉向', [
    ['steerRate', '轉向速度 (rad/s)', 0.5, 4, 0.05, 1.9],
    ['steerHighLoss', '高速轉向衰減', 0, 0.9, 0.05, 0.7],
    ['steerResponse', '方向鍵反應', 2, 30, 0.5, 10],
    ['grip', '抓地（速度跟車頭）', 2, 30, 0.5, 10],
  ]],
  ['甩尾', [
    ['driftMinSpeed', '可甩尾最低速', 2, 20, 0.5, 9],
    ['driftKick', '起甩甩頭 (rad)', 0, 0.5, 0.01, 0.16],
    ['driftYaw', '甩尾轉速', 0.3, 3, 0.05, 1.15],
    ['driftYawSteer', '內切／外拉幅度', 0, 1.5, 0.05, 0.62],
    ['driftGrip', '甩尾抓地', 0.2, 6, 0.1, 1.8],
    ['driftDrag', '甩尾掉速', 0, 20, 0.5, 4],
    ['gripRecover', '回正時間 (s)', 0.05, 1.2, 0.05, 0.35],
  ]],
  ['小噴／雙噴', [
    ['jetMinDrift', '甩尾多久才有小噴 (s)', 0, 1.5, 0.05, 0.35],
    ['jetWindow', '小噴時機窗 (s)', 0.1, 1.5, 0.05, 0.55],
    ['jetPerfect', '完美：車身偏角 < (°)', 1, 20, 0.5, 7],
    ['jetGood', '普通：車身偏角 < (°)', 5, 40, 0.5, 16],
    ['jetSpeed', '小噴加速 (m/s)', 0, 20, 0.5, 8],
    ['jetTime', '小噴持續 (s)', 0.1, 2, 0.05, 0.7],
    ['djMin', '雙噴最早 (s)', 0, 0.6, 0.01, 0.12],
    ['djMax', '雙噴最晚 (s)', 0.1, 1.2, 0.01, 0.5],
    ['djSpeed', '雙噴加速 (m/s)', 0, 20, 0.5, 5],
  ]],
  ['集氣／氮氣', [
    ['chargeRate', '集氣速度', 0.05, 1.5, 0.01, 0.5],
    ['nitroTime', '氮氣持續 (s)', 0.5, 6, 0.1, 3],
    ['nitroSpeed', '氮氣加速 (m/s)', 0, 25, 0.5, 13],
    ['boostAccel', '噴射推力', 5, 80, 1, 34],
    ['startBoost', '起步噴 (m/s)', 0, 20, 0.5, 8],
  ]],
  ['草地／護牆', [
    ['grassTop', '草地極速倍率', 0.2, 1, 0.05, 0.55],
    ['grassDrag', '草地阻力', 0, 30, 1, 10],
    ['wallBounce', '撞牆反彈', 0, 1, 0.05, 0.3],
    ['wallLoss', '撞牆掉速', 0, 1, 0.05, 0.3],
  ]],
  ['鏡頭', [
    ['camDist', '距離', 3, 12, 0.1, 4.6],
    ['camHeight', '高度', 1, 6, 0.1, 2.1],
    ['camFollow', '跟隨速度', 1, 15, 0.5, 5],
    ['camLookAhead', '看向車前多遠', 2, 20, 0.5, 12],
    ['camLookHeight', '看的高度（越高車越靠畫面下方）', 0, 4, 0.1, 2.4],
    ['camDriftMix', '甩尾時看車身比例', 0, 1, 0.05, 0.35],
    ['fov', '視角', 50, 90, 1, 68],
    ['fovSpeed', '車速越快視角越寬', 0, 25, 1, 6],
    ['fovBoost', '噴射時視角再加', 0, 30, 1, 8],
    ['camKick', '加速時鏡頭被甩開', 0, 3, 0.1, 0.7],
    ['camShake', '高速震動', 0, 0.1, 0.005, 0.03],
    ['speedFx', '速度線／風線濃度', 0, 2, 0.1, 1],
  ]],
];

const KEY = 'kcar.tuning.v1';
export const P = {};
export const DEFAULTS = {};
for (const [, items] of DEFS) for (const [k, , , , , d] of items) { P[k] = d; DEFAULTS[k] = d; }

try {
  const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
  for (const k in saved) if (k in P && typeof saved[k] === 'number') P[k] = saved[k];
} catch (e) { /* 沒有 localStorage 就用預設值 */ }

function save() {
  try { localStorage.setItem(KEY, JSON.stringify(P)); } catch (e) { /* 忽略 */ }
}

// ------------------------------------------------------------ 調參面板（HTML，不跟 Pixi 搶）
let panel = null;

export function togglePanel(force) {
  if (!panel) build();
  const show = force ?? panel.hidden;
  panel.hidden = !show;
  return show;
}

export function panelOpen() { return panel && !panel.hidden; }

function build() {
  panel = document.createElement('div');
  panel.id = 'tuning';
  panel.hidden = true;
  const head = document.createElement('div');
  head.className = 'tu-head';
  head.innerHTML = '<b>操控調參</b><span>T 開關．改了立即生效</span>';
  panel.appendChild(head);
  const inputs = {};
  for (const [group, items] of DEFS) {
    const h = document.createElement('div');
    h.className = 'tu-group';
    h.textContent = group;
    panel.appendChild(h);
    for (const [k, label, min, max, step] of items) {
      const row = document.createElement('label');
      row.className = 'tu-row';
      const name = document.createElement('span');
      name.textContent = label;
      const r = document.createElement('input');
      Object.assign(r, { type: 'range', min, max, step, value: P[k] });
      const val = document.createElement('output');
      val.textContent = P[k];
      r.addEventListener('input', () => {
        P[k] = parseFloat(r.value);
        val.textContent = r.value;
        val.classList.toggle('changed', P[k] !== DEFAULTS[k]);
        save();
      });
      val.classList.toggle('changed', P[k] !== DEFAULTS[k]);
      inputs[k] = [r, val];
      row.append(name, r, val);
      panel.appendChild(row);
    }
  }
  const bar = document.createElement('div');
  bar.className = 'tu-bar';
  const copy = document.createElement('button');
  copy.textContent = '複製參數';
  copy.onclick = async () => {
    const diff = {};
    for (const k in P) if (P[k] !== DEFAULTS[k]) diff[k] = P[k];
    const text = JSON.stringify(diff);
    try { await navigator.clipboard.writeText(text); copy.textContent = '已複製'; } catch (e) { prompt('複製這段：', text); }
    setTimeout(() => { copy.textContent = '複製參數'; }, 1200);
  };
  const reset = document.createElement('button');
  reset.textContent = '全部重設';
  reset.onclick = () => {
    for (const k in DEFAULTS) {
      P[k] = DEFAULTS[k];
      inputs[k][0].value = P[k];
      inputs[k][1].textContent = P[k];
      inputs[k][1].classList.remove('changed');
    }
    save();
  };
  const close = document.createElement('button');
  close.textContent = '關閉';
  close.onclick = () => togglePanel(false);
  bar.append(copy, reset, close);
  panel.appendChild(bar);
  // 面板裡的按鍵不要被遊戲吃掉
  panel.addEventListener('keydown', (e) => e.stopPropagation());
  panel.addEventListener('pointerdown', (e) => e.stopPropagation());
  document.body.appendChild(panel);
}
