// 輸入：鍵盤＋觸控按鈕，整理成每一幀的狀態與「這一幀剛按下」的邊緣事件。
//
// 鍵盤（照 QQ飛車 PC 版）：
//   ← → 轉向、↑ 油門、↓ 煞車／倒車、Shift 甩尾、Ctrl 或 Space 氮氣
//   小噴＝甩尾放開後在時機內「再按一次 ↑」（所以甩尾時要先鬆 ↑）
//   R 回到賽道、Esc／P 暫停、T 調參面板
// 觸控：自動油門；◀ ▶、甩尾、噴（小噴／雙噴／起步噴）、氮氣、煞車

const MAP = {
  ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down',
  ShiftLeft: 'drift', ShiftRight: 'drift',
  ControlLeft: 'nitro', ControlRight: 'nitro', Space: 'nitro',
  KeyR: 'reset', Escape: 'pause', KeyP: 'pause', KeyT: 'tuning',
};

export class Input {
  constructor() {
    this.keys = new Set();
    this.touch = new Set();
    this.edges = new Set();
    this.isTouch = matchMedia('(pointer: coarse)').matches || navigator.maxTouchPoints > 0;
    this.lastKeyboard = -1e9;
    addEventListener('keydown', (e) => {
      const a = MAP[e.code];
      if (!a) return;
      e.preventDefault();
      this.lastKeyboard = performance.now();
      if (!this.keys.has(a)) this.edges.add(a);
      this.keys.add(a);
    });
    addEventListener('keyup', (e) => {
      const a = MAP[e.code];
      if (!a) return;
      e.preventDefault();
      this.keys.delete(a);
    });
    addEventListener('blur', () => { this.keys.clear(); this.touch.clear(); });
  }

  /** 觸控按鈕呼叫：name 是 left/right/drift/jet/nitro/down/pause */
  setTouch(name, down) {
    if (down && !this.touch.has(name)) this.edges.add(name === 'jet' ? 'jet' : name);
    if (down) this.touch.add(name); else this.touch.delete(name);
  }

  held(a) { return this.keys.has(a) || this.touch.has(a); }
  pressed(a) { return this.edges.has(a); }

  /** 觸控模式（最近沒用鍵盤）：自動油門 */
  get autoThrottle() { return this.isTouch && performance.now() - this.lastKeyboard > 5000; }

  get steer() { return (this.held('right') ? 1 : 0) - (this.held('left') ? 1 : 0); }
  get throttle() { return this.held('up') || (this.autoThrottle && !this.held('down')) ? 1 : 0; }
  get braking() { return this.held('down'); }
  get driftHeld() { return this.held('drift'); }
  /** 小噴觸發：鍵盤是 ↑ 剛按下，觸控是「噴」鈕 */
  get jet() { return this.pressed('up') || this.pressed('jet'); }

  endFrame() { this.edges.clear(); }
}
