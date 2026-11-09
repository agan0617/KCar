// 輸入：鍵盤＋觸控按鈕，整理成每一幀的狀態與「這一幀剛按下」的邊緣事件。
//
// 鍵盤預設：A D 轉向、Space 甩尾、J 油門、K 煞車／倒車、L 氮氣、R 回到賽道、Esc／P 暫停、T 調參面板
// 小噴＝甩尾放開後在時機內「再按一次油門」（所以甩尾時要先鬆油門）。按鍵可在設定裡改（controls.js）。
// 觸控：自動油門；◀ ▶、甩尾、噴（小噴／雙噴／起步噴）、氮氣、煞車

import { codeMap, onKeysChange } from './controls.js';

export class Input {
  constructor() {
    this.keys = new Set();
    this.touch = new Set();
    this.edges = new Set();
    this.isTouch = matchMedia('(pointer: coarse)').matches || navigator.maxTouchPoints > 0;
    this.lastKeyboard = -1e9;
    this.map = codeMap();
    onKeysChange(() => { this.map = codeMap(); this.keys.clear(); });
    addEventListener('keydown', (e) => {
      const a = this.map.get(e.code);
      if (!a) return;
      e.preventDefault();
      this.lastKeyboard = performance.now();
      if (!this.keys.has(a)) this.edges.add(a);
      this.keys.add(a);
    });
    addEventListener('keyup', (e) => {
      const a = this.map.get(e.code);
      if (!a) return;
      e.preventDefault();
      // 同一個動作綁了兩個鍵：另一個還按著就不放開
      for (const [c, act] of this.map) if (act === a && c !== e.code && this.down?.has(c)) return;
      this.keys.delete(a);
    });
    // 記錄實體按鍵（給上面「兩個鍵同一動作」判斷用）
    this.down = new Set();
    addEventListener('keydown', (e) => this.down.add(e.code), true);
    addEventListener('keyup', (e) => this.down.delete(e.code), true);
    addEventListener('blur', () => { this.keys.clear(); this.touch.clear(); this.down.clear(); });
  }

  /** 觸控按鈕呼叫：name 是 left/right/drift/jet/nitro/down */
  setTouch(name, down) {
    if (down && !this.touch.has(name)) this.edges.add(name);
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
  /** 小噴觸發：鍵盤是油門鍵剛按下，觸控是「噴」鈕 */
  get jet() { return this.pressed('up') || this.pressed('jet'); }

  endFrame() { this.edges.clear(); }
}
