// 多人連線 client：連線（Net）與連線比賽（OnlineRace：本地預測＋回滾重放＋對手前推＋顯示誤差吸收）。
// 同步做法的總說明在 shared.js 開頭。

import { Kart } from '../kart.js';
import { collideKarts, standingsOf, estimateFinishOf, GRID_SLOTS } from '../race.js';
import { PROTO, STEP, FrameInput, packFrame, stepKart, SEAT_COLORS } from './shared.js';
import { VERSION } from '../version.js';

/** 預設 server：網頁本身就是 server 給的（http）就連同一台；否則（GitHub Pages）連這台電腦 */
export function defaultServer() {
  if (location.protocol === 'http:' && location.host) return location.host;
  return 'localhost:8787';
}

/** 「192.168.1.5:8787」「http://x:8787/」都轉成 ws://x:8787/ws */
export function wsUrl(addr) {
  let a = String(addr || '').trim();
  if (!a) a = defaultServer();
  a = a.replace(/^https?:\/\//, '').replace(/^wss?:\/\//, '').replace(/\/.*$/, '');
  if (!/:\d+$/.test(a)) a += ':8787';
  return `ws://${a}/ws`;
}

export class Net {
  constructor() {
    this.ws = null;
    this.handlers = new Map();
    this.rtt = 0;
    this.id = 0;
    this.name = '';
  }

  on(type, fn) { this.handlers.set(type, fn); }

  /** 連上並打招呼；成功回 welcome，失敗丟出原因 */
  connect(addr, name) {
    return new Promise((resolve, reject) => {
      let ws;
      try { ws = new WebSocket(wsUrl(addr)); } catch (e) { reject(new Error('網址不對')); return; }
      this.ws = ws;
      let settled = false;
      const fail = (msg) => { if (!settled) { settled = true; reject(new Error(msg)); } };
      const timer = setTimeout(() => { fail('連不上（逾時）'); ws.close(); }, 5000);
      ws.onopen = () => ws.send(JSON.stringify({ t: 'hello', name, ver: VERSION, proto: PROTO }));
      ws.onerror = () => fail('連不上 server：確認 server 有開、位址與埠對不對');
      ws.onclose = () => {
        clearTimeout(timer);
        clearInterval(this.pinger);
        fail('連線被關掉了');
        if (settled && this.ws === ws) { this.ws = null; const h = this.handlers.get('close'); if (h) h(); }
      };
      ws.onmessage = (ev) => {
        let m;
        try { m = JSON.parse(ev.data); } catch (e) { return; }
        if (!settled) {
          if (m.t === 'welcome') {
            settled = true;
            clearTimeout(timer);
            this.id = m.id;
            this.name = m.name;
            this.pinger = setInterval(() => this.send({ t: 'ping', c: performance.now() }), 1000);
            resolve(m);
          } else if (m.t === 'error') { fail(m.msg); ws.close(); }
          return;
        }
        if (m.t === 'pong') {
          const r = performance.now() - m.c;
          this.rtt = this.rtt ? this.rtt * 0.8 + r * 0.2 : r;
          return;
        }
        const h = this.handlers.get(m.t);
        if (h) h(m);
      };
    });
  }

  get connected() { return !!this.ws && this.ws.readyState === 1; }
  send(obj) { if (this.connected) this.ws.send(JSON.stringify(obj)); }

  close() {
    const ws = this.ws;
    this.ws = null;
    clearInterval(this.pinger);
    if (ws) ws.close();
  }
}

const wrap = (a) => {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
};

/**
 * 連線比賽（client 端）。對 main.js 長得跟單機的 Race 一樣：racers、player、laps、clock、standings()、estimateFinish()。
 *
 * 每台車有兩份 Kart：
 *   sim  ＝ 預測用：快照來了就回到快照狀態再重放；自己用自己的輸入，對手用快照裡「當下按著的鍵」前推
 *   kart ＝ 畫面用：sim ＋ 顯示誤差。回滾讓 sim 瞬間跳一下時，誤差吸收那一下再慢慢歸零（畫面、鏡頭、特效都讀這份）
 */
export class OnlineRace {
  constructor(track, net, { seats, laps, goTick, myId }) {
    this.online = true;
    this.mode = 'race';
    this.track = track;
    this.net = net;
    this.laps = laps;
    this.goTick = goTick;
    this.clock = 0;
    this.tick = 0; // 下一步是第幾步（預測的時刻）
    this.seq = 0;
    this.hist = []; // 還沒被 server 確認的輸入
    this.out = []; // 還沒送出的輸入
    this.fi = new FrameInput([0, 0, 0, 0, 0, 0]);
    this.lastSnap = -1;
    this.qAvg = 4;
    this.rate = 1;
    this.corr = 0; // 最近一次回滾的位置修正量（m），除錯看同步品質用
    this.lapQueue = [];
    const L = track.length;
    // 起跑格：跟 server 同一套排法（電腦在前、真人在後）
    const order = [...seats].sort((a, b) => (a.bot === b.bot ? a.seat - b.seat : a.bot ? -1 : 1));
    this.racers = [...seats].sort((a, b) => a.seat - b.seat).map((s) => {
      const sim = new Kart(track);
      const [ds, lat] = GRID_SLOTS[order.indexOf(s)];
      sim.resetRace(L + ds, lat);
      const kart = new Kart(track);
      kart.setState(sim.getState());
      return {
        seat: s.seat, id: s.id, name: s.name, bot: s.bot, color: SEAT_COLORS[s.seat], isPlayer: !s.bot && s.id === myId,
        sim, kart, held: new FrameInput([0, 0, 0, 0, 0, 0]), ctrl: s.bot ? 'b' : 'h',
        lapsDone: 0, lapStart: 0, laps: [], finishT: null, err: { x: 0, y: 0, z: 0, h: 0 },
      };
    });
    this.player = this.racers.find((r) => r.isPlayer);
    this.sims = this.racers.map((r) => r.sim);
  }

  get phase() { return this.tick < this.goTick ? 'count' : 'race'; }
  get countLeft() { return (this.goTick - this.tick) * STEP; }
  /** 自己的車要不要預測：真人在開、還沒完賽（server 交給電腦代駕時改跟快照走） */
  get predicting() { return this.player.finishT == null && this.player.ctrl === 'h'; }

  standings() { return standingsOf(this.racers); }
  estimateFinish(r) { return estimateFinishOf(r, this.laps, this.track.length, this.clock); }

  /** 一步模擬（預測與重放共用）。live＝這一步是真的往前走（不是重放），才保留自己的事件給畫面 */
  simStep(frame, live) {
    const me = this.player, pred = this.predicting;
    for (const r of this.racers) {
      const inp = r === me && pred ? this.fi.set(frame) : r.held;
      stepKart(r.sim, inp, this.tick, this.goTick);
    }
    collideKarts(this.sims);
    for (const r of this.racers) {
      if (live && r === me) { r.kart.events.push(...r.sim.events); }
      r.sim.events.length = 0;
    }
    this.tick++;
  }

  /** 每個物理步（120Hz）：收這一步的輸入、預測往前走一步 */
  step(input) {
    const f = packFrame(++this.seq, input);
    this.hist.push(f);
    this.out.push(f);
    if (this.hist.length > 720) this.hist.shift(); // server 太久沒回（5 秒以上），舊的就不留了
    this.simStep(f, true);
  }

  /** 收到快照：回到 server 的狀態，重放還沒確認的輸入 */
  onSnap(m) {
    if (m.k <= this.lastSnap) return;
    this.lastSnap = m.k;
    const before = this.racers.map((r) => [r.sim.x, r.sim.y, r.sim.z, r.sim.h]);
    for (const row of m.r) {
      const [seat, state, held, ld, ls, ft, ctrl, laps] = row;
      const r = this.racers.find((x) => x.seat === seat);
      if (!r) continue;
      if (r.isPlayer && ld > r.lapsDone && ld > 0) this.lapQueue.push({ lap: ld, time: laps[laps.length - 1], finished: ft != null });
      r.lapsDone = ld;
      r.lapStart = ls;
      r.finishT = ft;
      r.ctrl = ctrl;
      r.laps = laps;
      r.sim.setState(state);
      r.held.set([0, held[0], held[1], held[2], held[3], 0]);
    }
    while (this.hist.length && this.hist[0][0] <= m.a) this.hist.shift();
    this.tick = m.k;
    for (const f of this.hist) this.simStep(f, false);
    // 位置跳動交給顯示誤差吸收；跳太多（重生、剛開始）就直接跳過去
    this.racers.forEach((r, i) => {
      const [x, y, z, h] = before[i];
      const e = r.err;
      e.x += x - r.sim.x; e.y += y - r.sim.y; e.z += z - r.sim.z; e.h = wrap(e.h + wrap(h - r.sim.h));
      if (Math.hypot(e.x, e.z) > 8) { e.x = 0; e.y = 0; e.z = 0; e.h = 0; }
      if (r.isPlayer) this.corr = this.corr * 0.9 + Math.hypot(x - r.sim.x, z - r.sim.z) * 0.1;
    });
    // 時間微調：server 那邊這位玩家的輸入排隊目標 4 筆（約 33ms 緩衝）；太少就跑快一點、太多就慢一點。
    // 排隊空掉時 server 只好延用上一筆，時間軸就錯開一步（滿速約 33cm 的修正），緩衝就是拿來吸網路抖動的
    this.qAvg = this.qAvg * 0.9 + m.q * 0.1;
    this.rate = Math.max(0.97, Math.min(1.03, 1 + (4 - this.qAvg) * 0.01));
  }

  /** 每個畫面幀：誤差衰減，算出畫面用的車 */
  updateView(dt) {
    const a = Math.exp(-dt * 10);
    for (const r of this.racers) {
      const e = r.err, k = r.kart;
      e.x *= a; e.y *= a; e.z *= a; e.h *= a;
      k.setState(r.sim.getState());
      k.x += e.x; k.y += e.y; k.z += e.z;
      k.h = wrap(k.h + e.h);
      k.phi = wrap(k.phi + e.h);
    }
    this.clock = Math.max(0, (this.tick - this.goTick) * STEP);
  }

  /** 把這一幀收集的輸入送出去（一幀一包） */
  flush() {
    if (!this.out.length) return;
    this.net.send({ t: 'in', f: this.out });
    this.out = [];
  }
}
