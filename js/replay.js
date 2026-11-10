// 重播：比賽中每 1/30 秒記下每台車「畫面要用」的狀態，比完可以從頭重播（只留最後一場，放在記憶體）。
// 單機、多人連線都一樣記（連線記的是畫面上看到的那份，含預測與平滑後的結果）。
// 播放時在兩筆紀錄之間內插，可以暫停、變速、拖時間軸、換跟拍的車。

import { Kart } from './kart.js';

// 記哪些欄位（車的外觀、特效、聲音會讀到的；布林存 0／1，boostKind 只分「雙噴」與其他）
const F = ['x', 'y', 'z', 'h', 'phi', 'spd', 'steer', 'drift', 'driftDir', 'driftT', 'boostT', 'nitroT',
  'onGrass', 'onCurb', 'pitch', 'yawRate', 'dist', 'gauge', 'nitros', 'dj'];
const ANGLE = new Set(['h', 'phi']);
const BOOL = new Set(['drift', 'onGrass', 'onCurb']);
const STEPPED = new Set(['drift', 'onGrass', 'onCurb', 'driftDir', 'nitros', 'dj']); // 不內插，取較近的那筆
const N = F.length;
const RATE = 1 / 30;
const MAX_SAMPLES = 30 * 60 * 20; // 20 分鐘

const wrap = (a) => {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
};

export class Recorder {
  /** racers：比賽的車手（要有 kart；name、color、seat、isPlayer 用來挑車的外觀與顯示名字） */
  constructor(track, racers, info) {
    this.track = track;
    this.info = info; // { trackName, laps }
    this.src = racers;
    this.racers = racers.map((r) => ({ name: r.name, color: r.color, seat: r.seat, isPlayer: r.isPlayer }));
    this.times = [];
    this.clocks = [];
    this.frames = [];
    this.time = 0;
    this.next = 0;
  }

  /** 每個畫面幀呼叫；clock＝比賽時間（倒數中是 0） */
  tick(dt, clock) {
    this.time += dt;
    if (this.time < this.next || this.frames.length >= MAX_SAMPLES) return;
    this.next = Math.max(this.next + RATE, this.time - RATE);
    const a = new Float32Array(N * this.src.length);
    this.src.forEach((r, i) => {
      const k = r.kart, o = i * N;
      for (let j = 0; j < N; j++) {
        const f = F[j];
        a[o + j] = f === 'dj' ? (k.boostKind === 'dj' ? 1 : 0) : BOOL.has(f) ? (k[f] ? 1 : 0) : k[f] || 0;
      }
    });
    this.times.push(this.time);
    this.clocks.push(clock);
    this.frames.push(a);
  }

  get duration() { return this.times.length ? this.times[this.times.length - 1] : 0; }
  get empty() { return this.frames.length < 2; }

  /** 開跑前 1.5 秒（跳過大部分倒數） */
  get startTime() {
    const i = this.clocks.findIndex((c) => c > 0);
    return i < 0 ? 0 : Math.max(0, this.times[i] - 1.5);
  }
}

export class Replay {
  constructor(rec) {
    this.rec = rec;
    this.karts = rec.racers.map(() => new Kart(rec.track));
    this.t = rec.startTime;
    this.speed = 1;
    this.playing = true;
    this.target = Math.max(0, rec.racers.findIndex((r) => r.isPlayer));
    this.apply();
  }

  get ended() { return this.t >= this.rec.duration; }

  /** 推進播放時間，回傳這一幀畫面該用的 dt（暫停時 0） */
  advance(dt) {
    if (!this.playing) return 0;
    const step = dt * this.speed;
    this.t = Math.min(this.rec.duration, this.t + step);
    if (this.ended) this.playing = false;
    this.apply();
    return step;
  }

  seek(t) {
    this.t = Math.max(0, Math.min(this.rec.duration, t));
    this.apply();
  }

  /** 比賽時間（倒數中顯示 0） */
  get clock() {
    const { i, u } = this.locate();
    const c = this.rec.clocks;
    return c[i] + (c[Math.min(i + 1, c.length - 1)] - c[i]) * u;
  }

  locate() {
    const ts = this.rec.times;
    let lo = 0, hi = ts.length - 1;
    if (this.t <= ts[0]) return { i: 0, u: 0 };
    if (this.t >= ts[hi]) return { i: hi, u: 0 };
    while (hi - lo > 1) {
      const m = (lo + hi) >> 1;
      if (ts[m] <= this.t) lo = m; else hi = m;
    }
    return { i: lo, u: (this.t - ts[lo]) / Math.max(1e-6, ts[hi] - ts[lo]) };
  }

  apply() {
    const { i, u } = this.locate();
    const fr = this.rec.frames;
    const A = fr[i], B = fr[Math.min(i + 1, fr.length - 1)];
    this.karts.forEach((k, ri) => {
      const o = ri * N;
      for (let j = 0; j < N; j++) {
        const f = F[j], a = A[o + j], b = B[o + j];
        let v;
        if (STEPPED.has(f)) v = u < 0.5 ? a : b;
        else if (ANGLE.has(f)) v = wrap(a + wrap(b - a) * u);
        else v = a + (b - a) * u;
        if (f === 'dj') k.boostKind = v ? 'dj' : 'jet';
        else k[f] = BOOL.has(f) ? v > 0.5 : v;
      }
    });
  }

  /** 名次（照跑的距離）與圈數，給控制列顯示 */
  placeOf(idx) {
    const d = this.karts.map((k) => k.dist);
    return d.filter((x) => x > d[idx]).length + 1;
  }
  lapOf(idx) {
    const L = this.rec.track.length;
    return Math.max(1, Math.min(this.rec.info.laps, Math.floor(this.karts[idx].dist / L) + 1));
  }
}

const fmt = (t) => {
  const m = Math.floor(t / 60), s = Math.floor(t - m * 60);
  return `${m}:${String(s).padStart(2, '0')}`;
};

/** 重播控制列（HTML，疊在畫面下方）。h：onExit()、onSeek()、onTarget() */
export class ReplayBar {
  constructor(h) {
    this.h = h;
    const el = (this.el = document.createElement('div'));
    el.id = 'replaybar';
    el.hidden = true;
    el.innerHTML = `
      <div class="rb-top"><b>重播</b><span data-info></span><button data-exit>離開重播（Esc）</button></div>
      <div class="rb-row">
        <button data-play title="播放／暫停（空白鍵）">⏸</button>
        <input data-seek type="range" min="0" max="1" step="0.01" value="0">
        <span data-time>0:00 / 0:00</span>
      </div>
      <div class="rb-row">
        <span class="rb-speed">${[0.25, 0.5, 1, 2, 4].map((s) => `<button data-speed="${s}">${s}×</button>`).join('')}</span>
        <span class="rb-cam"><button data-prev title="上一台（↑）">◀</button><i data-dot></i><span data-name></span><button data-next title="下一台（↓）">▶</button></span>
      </div>`;
    document.body.appendChild(el);
    const q = (s) => el.querySelector(s);
    this.$ = { info: q('[data-info]'), play: q('[data-play]'), seek: q('[data-seek]'), time: q('[data-time]'), name: q('[data-name]'), dot: q('[data-dot]') };
    q('[data-exit]').onclick = () => this.h.onExit();
    this.$.play.onclick = () => this.toggle();
    el.querySelectorAll('[data-speed]').forEach((b) => { b.onclick = () => { this.rp.speed = Number(b.dataset.speed); this.render(true); }; });
    q('[data-prev]').onclick = () => this.cycle(-1);
    q('[data-next]').onclick = () => this.cycle(1);
    this.$.seek.oninput = () => { this.rp.seek(Number(this.$.seek.value)); this.h.onSeek(); this.render(true); };
    // 控制列上的操作不要漏給遊戲（觸控按鈕、鍵盤）
    el.addEventListener('pointerdown', (e) => e.stopPropagation());
    this.onKey = (e) => {
      if (!this.rp || el.hidden) return;
      const k = e.code;
      if (k === 'Escape') this.h.onExit();
      else if (k === 'Space') this.toggle();
      else if (k === 'ArrowLeft' || k === 'ArrowRight') { this.rp.seek(this.rp.t + (k === 'ArrowLeft' ? -5 : 5)); this.h.onSeek(); }
      else if (k === 'ArrowUp' || k === 'ArrowDown') this.cycle(k === 'ArrowUp' ? -1 : 1);
      else return;
      e.preventDefault();
      e.stopImmediatePropagation();
      this.render(true);
    };
    addEventListener('keydown', this.onKey, true);
  }

  show(rp) {
    this.rp = rp;
    this.$.seek.max = String(rp.rec.duration);
    this.el.hidden = false;
    this.render(true);
  }
  hide() { this.el.hidden = true; this.rp = null; }
  get visible() { return !this.el.hidden; }

  toggle() {
    const rp = this.rp;
    if (rp.ended) { rp.seek(rp.rec.startTime); this.h.onSeek(); }
    rp.playing = !rp.playing || rp.ended;
    this.render(true);
  }

  cycle(d) {
    const rp = this.rp, n = rp.karts.length;
    rp.target = (rp.target + d + n) % n;
    this.h.onTarget();
    this.render(true);
  }

  /** 每幀更新（full：連按鈕狀態一起） */
  render(full = false) {
    const rp = this.rp;
    if (!rp) return;
    const $ = this.$, rr = rp.rec.racers[rp.target];
    if (document.activeElement !== $.seek) $.seek.value = String(rp.t);
    const cs = rp.rec.clocks;
    $.time.textContent = `${fmt(rp.clock)} / ${fmt(cs[cs.length - 1])}`;
    $.info.textContent = `${rp.rec.info.trackName}　第 ${rp.lapOf(rp.target)}／${rp.rec.info.laps} 圈　第 ${rp.placeOf(rp.target)} 名`;
    if (!full) return;
    $.play.textContent = rp.playing ? '⏸' : '▶';
    $.name.textContent = rr.name + (rr.isPlayer ? '（你）' : '');
    $.dot.style.background = rr.color;
    this.el.querySelectorAll('[data-speed]').forEach((b) => b.classList.toggle('on', Number(b.dataset.speed) === rp.speed));
  }
}
