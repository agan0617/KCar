// 多人連線：server 與 client 共用的部分（純邏輯，不碰 DOM／three.js，Node 也能跑）。
//
// 同步做法照貪食蛇 server（partygo-server-snake）的路線：
//   - 權威 server：固定 120Hz 推進整場比賽，跑的就是這個 repo 的 kart.js（不用移植，天生一致）
//   - client 只上傳輸入（每一步一筆、帶序號），server 不信 client 報的位置
//   - 快照 30Hz 下傳，附「這位玩家的輸入處理到第幾號」（ack）
//   - client 自己的車本地預測：收到快照就回到快照的狀態，把還沒被確認的輸入重放一次（回滾重放）
//   - 對手不落後畫：用快照裡的狀態＋當下按著的鍵，以同一套物理前推到跟自己同一時刻
//   - 回滾造成的位置跳動由一層「顯示誤差」吸收、慢慢歸零，畫面不會瞬移

import { P } from '../tuning.js';

export const PROTO = 1;
export const STEP = 1 / 120;
export const SNAP_EVERY = 4; // 每 4 步送一次快照＝30Hz
export const COUNT_TICKS = 360; // 倒數 3 秒
export const MAX_PLAYERS = 4;

// 輸入的「剛按下」位元
export const EDGE = { drift: 1, down: 2, nitro: 4, jet: 8, reset: 16 };

/** 從 Input（或電腦車手的 input）抓這一步的輸入，壓成陣列 [seq, steer, throttle, brake, driftHeld, edges] */
export function packFrame(seq, inp) {
  let e = 0;
  if (inp.pressed('drift')) e |= EDGE.drift;
  if (inp.pressed('down')) e |= EDGE.down;
  if (inp.pressed('nitro')) e |= EDGE.nitro;
  if (inp.jet) e |= EDGE.jet;
  if (inp.pressed('reset')) e |= EDGE.reset;
  return [seq, inp.steer, inp.throttle ? 1 : 0, inp.braking ? 1 : 0, inp.driftHeld ? 1 : 0, e];
}

/** 壓縮過的一筆輸入 → Kart.step 吃的介面 */
export class FrameInput {
  constructor(f) { this.set(f); }
  set(f) {
    this.f = f;
    return this;
  }
  get steer() { return this.f[1]; }
  get throttle() { return this.f[2]; }
  get braking() { return !!this.f[3]; }
  get driftHeld() { return !!this.f[4]; }
  get jet() { return !!(this.f[5] & EDGE.jet); }
  pressed(a) { return !!(this.f[5] & (EDGE[a] || 0)); }
}

/** 只有「按著的鍵」、沒有「剛按下」（server 沒收到新輸入時延用上一筆、client 前推對手時用） */
export const heldOf = (f) => [f[0], f[1], f[2], f[3], f[4], 0];
export const NEUTRAL = [0, 0, 0, 0, 0, 0];

/**
 * 一台車走一步：起步噴判定＋物理＋回到賽道。server 與 client 預測都走這裡，兩邊才會算出一樣的結果。
 * tick：這一步是第幾步（從開始倒數算起）；goTick：GO 的那一步
 */
export function stepKart(k, inp, tick, goTick) {
  const control = tick >= goTick;
  if (!control) {
    // 起步噴：GO 前 0.25 秒內按 ↑／噴才算，太早按就沒了
    if (inp.jet && !k.sbUsed) {
      k.sbUsed = true;
      if ((goTick - tick) * STEP < 0.25) k.sbPend = true;
    }
  } else {
    if (tick === goTick && k.sbPend) {
      k.sbPend = false;
      k.addBoost(P.startBoost, 1.0, 'start');
      k.events.push({ type: 'start' });
    }
    if (inp.jet && !k.sbUsed && (tick - goTick) * STEP < 0.2) {
      k.sbUsed = true;
      k.addBoost(P.startBoost, 1.0, 'start');
      k.events.push({ type: 'start' });
    }
  }
  k.step(STEP, inp, control);
  if (control && inp.pressed('reset')) k.respawn();
}

/** 座位顏色與預設名字：座位 0～3 對應首頁的四台車（Komugi 紅、Mochi 藍、Azuki 綠、Kinako 紫） */
export const SEAT_NAMES = ['Komugi', 'Mochi', 'Azuki', 'Kinako'];
export const SEAT_COLORS = ['#e8322b', '#2f80ed', '#34c759', '#a259ff'];
