// 按鍵設定：每個動作最多兩個鍵（主要／次要），存在這台裝置的 localStorage。
// 也負責「按鍵設定」與「操作說明」兩個面板（HTML，疊在遊戲上）。

export const ACTIONS = [
  ['up', '油門', '甩尾放開後再按一次＝小噴，接著再按一次＝雙噴；倒數 GO 時按＝起步噴'],
  ['down', '煞車／倒車', '甩尾中點一下＝點煞：車頭往彎內甩、掉一點速度'],
  ['left', '左轉', ''],
  ['right', '右轉', ''],
  ['drift', '甩尾', '按住＋方向起甩'],
  ['nitro', '氮氣', '集滿氣後使用'],
  ['reset', '回到賽道', '卡住時用'],
  ['pause', '暫停', ''],
  ['tuning', '操控調參面板', ''],
];

// 左手 A D 轉向、Space 甩尾；右手 J 油門（小噴）、K 煞車、L 氮氣（2026-11-09 Ken 指定）
export const DEFAULT_KEYS = {
  up: ['KeyJ', ''], down: ['KeyK', ''], left: ['KeyA', ''], right: ['KeyD', ''],
  drift: ['Space', ''], nitro: ['KeyL', ''],
  reset: ['KeyR', ''], pause: ['Escape', 'KeyP'], tuning: ['KeyT', ''],
};

// 預設鍵位換過就換存檔名，舊設定（WASD 版）不沿用
const STORE = 'kcar.keys.v2';
export const KEYS = load();
const listeners = new Set();

function load() {
  const k = JSON.parse(JSON.stringify(DEFAULT_KEYS));
  try {
    const saved = JSON.parse(localStorage.getItem(STORE) || '{}');
    for (const a in saved) if (a in k && Array.isArray(saved[a])) k[a] = [saved[a][0] || '', saved[a][1] || ''];
  } catch (e) { /* 用預設 */ }
  return k;
}

function save() {
  try { localStorage.setItem(STORE, JSON.stringify(KEYS)); } catch (e) { /* 忽略 */ }
  for (const fn of listeners) fn();
}

export function onKeysChange(fn) { listeners.add(fn); }

/** e.code → 動作 */
export function codeMap() {
  const m = new Map();
  for (const a in KEYS) for (const c of KEYS[a]) if (c) m.set(c, a);
  return m;
}

const NAMES = {
  ArrowUp: '↑', ArrowDown: '↓', ArrowLeft: '←', ArrowRight: '→',
  ShiftLeft: '左 Shift', ShiftRight: '右 Shift', ControlLeft: '左 Ctrl', ControlRight: '右 Ctrl',
  AltLeft: '左 Alt', AltRight: '右 Alt', Space: '空白鍵', Escape: 'Esc', Enter: 'Enter', Tab: 'Tab',
  Backspace: 'Backspace', CapsLock: 'Caps Lock', Semicolon: ';', Quote: "'", Comma: ',', Period: '.',
  Slash: '/', Backslash: '\\', BracketLeft: '[', BracketRight: ']', Minus: '-', Equal: '=', Backquote: '`',
};

export function keyName(code) {
  if (!code) return '';
  if (NAMES[code]) return NAMES[code];
  if (/^Key[A-Z]$/.test(code)) return code.slice(3);
  if (/^Digit\d$/.test(code)) return code.slice(5);
  if (/^Numpad/.test(code)) return '數字鍵 ' + code.slice(6);
  return code;
}

/** 某動作的按鍵名稱，例如「W」或「Esc／P」 */
export function keysOf(a) { return KEYS[a].filter(Boolean).map(keyName).join('／') || '（未設定）'; }

// ------------------------------------------------------------ 面板
let open = null;
export function dialogOpen() { return !!open; }
export function closeDialog() {
  if (!open) return;
  open.remove();
  open = null;
  removeEventListener('keydown', capture, true);
}

function dialog(title) {
  closeDialog();
  const d = document.createElement('div');
  d.className = 'dlg';
  d.innerHTML = `<div class="dlg-box"><div class="dlg-head"><b>${title}</b><button class="dlg-x" title="關閉">✕</button></div><div class="dlg-body"></div><div class="dlg-bar"></div></div>`;
  d.querySelector('.dlg-x').onclick = closeDialog;
  d.addEventListener('pointerdown', (e) => { e.stopPropagation(); if (e.target === d) closeDialog(); });
  document.body.appendChild(d);
  open = d;
  return { body: d.querySelector('.dlg-body'), bar: d.querySelector('.dlg-bar') };
}

/** 給其他面板用（多人連線大廳）：開一個對話框，面板開著時按鍵不漏給遊戲、Esc 關閉 */
export function openDialog(title) {
  const d = dialog(title);
  addEventListener('keydown', capture, true);
  return d;
}

function btn(text, onClick, cls = '') {
  const b = document.createElement('button');
  b.textContent = text;
  b.className = cls;
  b.onclick = onClick;
  return b;
}

// 改鍵：點了某一格後，下一個按下的鍵就是新設定
let waiting = null;
function capture(e) {
  if (!waiting) {
    // 面板開著時，Esc 關面板；其他鍵不要漏給遊戲
    if (e.code === 'Escape') closeDialog();
    e.stopImmediatePropagation();
    return;
  }
  e.preventDefault();
  e.stopImmediatePropagation();
  const { action, slot, done } = waiting;
  waiting = null;
  const code = e.code;
  let moved = '';
  for (const a in KEYS) {
    KEYS[a].forEach((c, i) => {
      if (c === code && !(a === action && i === slot)) { KEYS[a][i] = ''; moved = a; }
    });
  }
  KEYS[action][slot] = code;
  save();
  done(moved);
}

/** 按鍵設定面板。onTuning：打開操控調參 */
export function openKeySettings({ onTuning, quality } = {}) {
  const { body, bar } = dialog('設定');
  addEventListener('keydown', capture, true);
  if (quality) {
    const q = document.createElement('div');
    q.className = 'quality';
    const draw = () => {
      q.innerHTML = '<h4>畫質</h4>';
      const row = document.createElement('div');
      row.className = 'qrow';
      for (const [v, label, tip] of [['high', '高畫質', '泛光、反鋸齒、高解析陰影'], ['low', '省電', '手機跑不順時用']]) {
        const b = btn('', () => { quality.set(v); draw(); }, 'qbtn' + (quality.get() === v ? ' on' : ''));
        b.innerHTML = `<b>${label}</b><small>${tip}</small>`;
        row.appendChild(b);
      }
      q.appendChild(row);
    };
    draw();
    body.appendChild(q);
    const h = document.createElement('h4');
    h.textContent = '按鍵';
    body.appendChild(h);
  }
  const note = document.createElement('p');
  note.className = 'dlg-note';
  note.textContent = '點一格，再按想用的鍵。每個動作可以設兩個鍵；同一個鍵只能給一個動作（會自動從原本的動作拿掉）。';
  const table = document.createElement('div');
  table.className = 'keys';
  const render = (msg) => {
    table.innerHTML = '<div class="kh">動作</div><div class="kh">主要</div><div class="kh">次要</div>';
    for (const [a, label] of ACTIONS) {
      const name = document.createElement('div');
      name.className = 'kn';
      name.textContent = label;
      table.appendChild(name);
      for (const slot of [0, 1]) {
        const cell = document.createElement('div');
        cell.className = 'kc';
        const b = btn(keyName(KEYS[a][slot]) || '—', () => {
          b.textContent = '按下新按鍵…';
          b.classList.add('wait');
          waiting = {
            action: a, slot,
            done: (moved) => render(moved ? `「${keyName(KEYS[a][slot])}」原本是「${ACTIONS.find((x) => x[0] === moved)[1]}」的鍵，已改給「${label}」` : ''),
          };
        }, 'key');
        cell.appendChild(b);
        if (KEYS[a][slot]) {
          cell.appendChild(btn('✕', () => { KEYS[a][slot] = ''; save(); render(''); }, 'clr'));
        }
        table.appendChild(cell);
      }
    }
    note.textContent = msg || '點一格，再按想用的鍵。每個動作可以設兩個鍵；同一個鍵只能給一個動作（會自動從原本的動作拿掉）。';
    note.classList.toggle('warn', !!msg);
  };
  render('');
  body.append(note, table);
  bar.append(
    btn('恢復預設', () => { for (const a in DEFAULT_KEYS) KEYS[a] = [...DEFAULT_KEYS[a]]; save(); render(''); }),
    ...(onTuning ? [btn('操控調參', () => { closeDialog(); onTuning(); })] : []),
    btn('完成', closeDialog, 'primary'),
  );
}

/** 操作說明面板（依目前的按鍵設定顯示） */
export function openHelp({ touch } = {}) {
  const { body, bar } = dialog('操作說明');
  addEventListener('keydown', capture, true);
  const k = keysOf;
  const kbd = (a) => `<kbd>${k(a)}</kbd>`;
  const rows = ACTIONS.map(([a, label, tip]) => `<tr><td>${kbd(a)}</td><td>${label}${tip ? `<small>${tip}</small>` : ''}</td></tr>`).join('');
  body.innerHTML = `
    <h4>鍵盤（目前的設定）</h4>
    <table class="help">${rows}</table>
    <h4>技巧</h4>
    <ol class="tips">
      <li><b>甩尾集氣：</b>過彎時按住 ${kbd('drift')} ＋方向（${kbd('left')}／${kbd('right')}）起甩。方向往彎內壓轉得更急，往外拉走大圈（比不甩尾還緩），長彎可以一路甩到底。車身側滑越大、速度越快，集氣越快。</li>
      <li><b>小噴：</b>甩尾時先放開 ${kbd('up')}；彎道快結束時放開甩尾，車頭會轉回前進方向（同時按反方向回正更快），車身回正的瞬間<b>再按一次</b> ${kbd('up')}。畫面下方的時機表：綠區完美、黃區普通、紅區太早。</li>
      <li><b>雙噴：</b>小噴之後，在時機表的綠區內再按一次 ${kbd('up')}。</li>
      <li><b>點煞（急彎用）：</b>甩尾中短按 ${kbd('down')}，車頭會再往彎內甩一截、轉得更急，代價是掉一點速度；按住不放轉更多、掉更多。髮夾彎方向鍵壓到底還轉不過去時用。</li>
      <li><b>氮氣：</b>集滿一條氣得到一顆（最多兩顆），直線上按 ${kbd('nitro')} 使用。</li>
      <li><b>起步噴：</b>倒數 GO 出現的瞬間按 ${kbd('up')}，太早按就沒了。</li>
      <li>出賽道外側的草地、沙地會大幅減速，撞牆掉速；卡住按 ${kbd('reset')} 回到賽道。</li>
    </ol>
    <h4>手機觸控</h4>
    <p>自動油門；左下 ◀ ▶ 轉向（手指可在兩鍵間滑），右下「甩尾」按住起甩、「噴」＝小噴／雙噴／起步噴、「氮氣」、「煞」煞車。</p>
    ${touch ? '' : '<p class="dlg-note">按鍵可以在首頁或暫停選單的「設定」裡改。</p>'}`;
  bar.append(btn('知道了', closeDialog, 'primary'));
}
