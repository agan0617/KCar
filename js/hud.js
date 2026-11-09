// 2D 介面（PixiJS）：首頁、HUD、小噴時機表、觸控按鈕、暫停與成績。
// 疊在 three.js 畫布上面，透明背景。

import { Application, Container, Graphics, Text, TextStyle } from 'pixi.js';
import { P } from './tuning.js';
import { keysOf } from './controls.js';

const FONT = ['"Noto Sans TC"', '"Microsoft JhengHei"', '"PingFang TC"', '"Heiti TC"', 'sans-serif'];
const style = (size, fill = '#ffffff', extra = {}) => new TextStyle({
  fontFamily: FONT, fontSize: size, fontWeight: '900', fill,
  stroke: { color: '#14244a', width: Math.max(2, size * 0.14), join: 'round' },
  dropShadow: { color: '#000000', alpha: 0.35, blur: 3, distance: Math.max(1, size * 0.06), angle: Math.PI / 2 },
  ...extra,
});

export function fmtTime(t) {
  if (t == null || !isFinite(t)) return '--:--.--';
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${String(m).padStart(2, '0')}:${s.toFixed(2).padStart(5, '0')}`;
}

function button(label, w, h, color, onTap) {
  const c = new Container();
  const g = new Graphics();
  const draw = (hover) => {
    g.clear();
    g.roundRect(-w / 2, -h / 2 + 5, w, h, h / 2).fill({ color: 0x0b1733, alpha: 0.45 });
    g.roundRect(-w / 2, -h / 2, w, h, h / 2).fill({ color: hover ? 0xffffff : color }).stroke({ width: 4, color: 0x14244a });
  };
  draw(false);
  const t = new Text({ text: label, style: style(Math.round(h * 0.42), '#ffffff') });
  t.anchor.set(0.5);
  c.addChild(g, t);
  c.eventMode = 'static';
  c.cursor = 'pointer';
  c.on('pointerover', () => { draw(true); t.style.fill = '#14244a'; });
  c.on('pointerout', () => { draw(false); t.style.fill = '#ffffff'; });
  c.on('pointertap', (e) => { e.stopPropagation(); onTap(); });
  return c;
}

export class Hud {
  static async create(canvas, input) {
    const app = new Application();
    await app.init({
      canvas, backgroundAlpha: 0, resizeTo: window, antialias: true, autoDensity: true,
      resolution: Math.min(window.devicePixelRatio || 1, 2), autoStart: false, preference: 'webgl',
    });
    return new Hud(app, input);
  }

  constructor(app, input) {
    this.app = app;
    this.input = input;
    this.stage = app.stage;
    this.popups = [];
    this.touchButtons = [];
    this.pointerMap = new Map();

    this.lines = new Graphics();
    this.race = new Container();
    this.touchLayer = new Container();
    this.overlay = new Container();
    this.stage.addChild(this.lines, this.race, this.touchLayer, this.overlay);

    this.buildRaceHud();
    this.buildTouch();
    this.bindTouch();
    addEventListener('resize', () => this.layout());
    this.layout();
  }

  get W() { return this.app.screen.width; }
  get H() { return this.app.screen.height; }

  // ------------------------------------------------------------ 比賽 HUD
  buildRaceHud() {
    const r = this.race;
    this.panel = new Graphics();
    this.tLap = new Text({ text: 'LAP 1/3', style: style(34, '#ffd23f') });
    this.tTime = new Text({ text: '00:00.00', style: style(26) });
    this.tSub = new Text({ text: '', style: style(17, '#e8f4ff') });
    this.tSpeed = new Text({ text: '0', style: style(52, '#ffffff') });
    this.tSpeed.anchor.set(0.5, 1);
    this.tKmh = new Text({ text: 'km/h', style: style(16, '#cfe6ff') });
    this.tKmh.anchor.set(0, 1);
    this.gauge = new Graphics();
    this.meter = new Graphics();
    this.tMeter = new Text({ text: '', style: style(16, '#ffffff') });
    this.tMeter.anchor.set(0.5, 1);
    this.tCount = new Text({ text: '', style: style(120, '#ffd23f') });
    this.tCount.anchor.set(0.5);
    this.tWarn = new Text({ text: '逆向！', style: style(40, '#ff5a5f') });
    this.tWarn.anchor.set(0.5);
    this.tWarn.visible = false;
    this.pauseBtn = new Container();
    const pg = new Graphics();
    pg.circle(0, 0, 26).fill({ color: 0x0b1733, alpha: 0.45 }).stroke({ width: 3, color: 0xffffff, alpha: 0.8 });
    pg.roundRect(-9, -11, 6, 22, 2).fill(0xffffff);
    pg.roundRect(3, -11, 6, 22, 2).fill(0xffffff);
    this.pauseBtn.addChild(pg);
    this.pauseBtn.eventMode = 'static';
    this.pauseBtn.cursor = 'pointer';
    this.pauseBtn.on('pointertap', () => this.onPause && this.onPause());
    this.mini = new Container();
    this.miniTrack = new Graphics();
    this.miniDot = new Graphics();
    this.mini.addChild(this.miniTrack, this.miniDot);
    // 競賽：名次、排行、對手名牌
    this.tPlace = new Text({ text: '', style: style(58, '#ffffff') });
    this.tPlaceOf = new Text({ text: '/4', style: style(24, '#cfe6ff') });
    this.tPlaceOf.anchor.set(0, 1);
    this.board = new Container();
    this.boardBg = new Graphics();
    this.boardRows = [0, 1, 2, 3].map(() => new Text({ text: '', style: style(17, '#ffffff') }));
    this.board.addChild(this.boardBg, ...this.boardRows);
    this.tags = new Container();
    this.tagPool = [];
    r.addChild(this.tags, this.panel, this.mini, this.tPlace, this.tPlaceOf, this.board, this.tLap, this.tTime, this.tSub, this.gauge, this.tSpeed, this.tKmh, this.meter, this.tMeter, this.tCount, this.tWarn, this.pauseBtn);
    r.visible = false;
  }

  // ------------------------------------------------------------ 小地圖（北朝上，右上角）
  setTrack(track) {
    this.track = track;
    let minx = Infinity, maxx = -Infinity, minz = Infinity, maxz = -Infinity;
    for (let i = 0; i < track.n; i++) {
      minx = Math.min(minx, track.x[i]); maxx = Math.max(maxx, track.x[i]);
      minz = Math.min(minz, track.z[i]); maxz = Math.max(maxz, track.z[i]);
    }
    this.miniBounds = { minx, maxx, minz, maxz };
    this.drawMiniTrack();
  }

  drawMiniTrack() {
    const t = this.track;
    if (!t || !this.miniPos) return;
    const b = this.miniBounds, mp = this.miniPos;
    const span = Math.max(b.maxx - b.minx, b.maxz - b.minz);
    const k = (mp.size - mp.pad * 2) / span;
    const ox = mp.pad + ((mp.size - mp.pad * 2) - (b.maxx - b.minx) * k) / 2;
    const oz = mp.pad + ((mp.size - mp.pad * 2) - (b.maxz - b.minz) * k) / 2;
    this.miniMap = (x, z) => [ox + (x - b.minx) * k, oz + (z - b.minz) * k];
    const g = this.miniTrack;
    g.clear();
    g.roundRect(0, 0, mp.size, mp.size, 14 * mp.s).fill({ color: 0x0b1733, alpha: 0.42 });
    const path = (gg) => {
      for (let i = 0; i <= t.n; i += 2) {
        const [px, py] = this.miniMap(t.x[i % t.n], t.z[i % t.n]);
        if (i === 0) gg.moveTo(px, py); else gg.lineTo(px, py);
      }
      gg.closePath();
    };
    path(g);
    g.stroke({ width: 7 * mp.s, color: 0xffffff, alpha: 0.9, join: 'round' });
    path(g);
    g.stroke({ width: 3.5 * mp.s, color: 0x5b6170, join: 'round' });
    // 起終點線
    const [sx, sy] = this.miniMap(t.x[0], t.z[0]);
    const nx = -t.tz[0], nz = t.tx[0];
    const L = 6 * mp.s;
    g.moveTo(sx - nx * L, sy - nz * L).lineTo(sx + nx * L, sy + nz * L).stroke({ width: 3 * mp.s, color: 0xffd23f });
  }

  drawMiniDot(k, others = []) {
    if (!this.miniMap) return;
    const s = this.miniPos.s;
    const g = this.miniDot;
    g.clear();
    for (const o of others) {
      const [ox, oy] = this.miniMap(o.x, o.z);
      g.circle(ox, oy, 4.5 * s).fill(o.color).stroke({ width: 1.5, color: 0xffffff });
    }
    const [x, y] = this.miniMap(k.x, k.z);
    // 前方 = (sin h, cos h)，畫成指向前方的三角形
    const fx = Math.sin(k.h), fy = Math.cos(k.h);
    const rx = -fy, ry = fx;
    const a = 8 * s, w = 5.5 * s;
    g.poly([x + fx * a, y + fy * a, x - fx * a * 0.6 + rx * w, y - fy * a * 0.6 + ry * w, x - fx * a * 0.6 - rx * w, y - fy * a * 0.6 - ry * w])
      .fill(0xff3b30).stroke({ width: 2, color: 0xffffff });
  }

  // ------------------------------------------------------------ 觸控按鈕（自己做多點觸控判定，手指可以在 ◀ ▶ 之間滑）
  buildTouch() {
    const defs = [
      ['left', '◀'], ['right', '▶'], ['drift', '甩尾'], ['jet', '噴'], ['nitro', '氮氣'], ['down', '煞'],
    ];
    for (const [name, label] of defs) {
      const c = new Container();
      const g = new Graphics();
      const t = new Text({ text: label, style: style(26, '#ffffff') });
      t.anchor.set(0.5);
      c.addChild(g, t);
      this.touchLayer.addChild(c);
      this.touchButtons.push({ name, c, g, t, r: 50, down: false });
    }
    this.touchLayer.visible = false;
  }

  drawTouch(b) {
    const col = { drift: 0xff9f1c, jet: 0x2ec4b6, nitro: 0x3a86ff, down: 0xe63946 }[b.name] ?? 0xffffff;
    b.g.clear();
    b.g.circle(0, 0, b.r).fill({ color: col, alpha: b.down ? 0.75 : 0.28 }).stroke({ width: 3, color: 0xffffff, alpha: b.down ? 1 : 0.6 });
    if (b.glow) b.g.circle(0, 0, b.r + 7).stroke({ width: 5, color: 0x9ff7ff, alpha: 0.9 });
    b.t.style.fontSize = Math.round(b.r * (b.name === 'left' || b.name === 'right' ? 0.62 : 0.42));
  }

  bindTouch() {
    const canvas = this.app.canvas;
    const hit = (x, y) => {
      if (!this.touchLayer.visible) return null;
      let best = null, bd = Infinity;
      for (const b of this.touchButtons) {
        const d = Math.hypot(x - b.c.x, y - b.c.y);
        if (d < b.r * 1.35 && d < bd) { bd = d; best = b; }
      }
      return best;
    };
    const apply = () => {
      const active = new Set(this.pointerMap.values());
      for (const b of this.touchButtons) {
        const on = active.has(b.name);
        if (on !== b.down) { b.down = on; this.input.setTouch(b.name, on); this.drawTouch(b); }
      }
    };
    const rect = () => canvas.getBoundingClientRect();
    canvas.addEventListener('pointerdown', (e) => {
      const r = rect();
      const b = hit(e.clientX - r.left, e.clientY - r.top);
      if (!b) return;
      this.pointerMap.set(e.pointerId, b.name);
      apply();
    });
    canvas.addEventListener('pointermove', (e) => {
      if (!this.pointerMap.has(e.pointerId)) return;
      const cur = this.pointerMap.get(e.pointerId);
      if (cur !== 'left' && cur !== 'right') return; // 只有方向鍵可以滑動換鍵
      const r = rect();
      const b = hit(e.clientX - r.left, e.clientY - r.top);
      if (b && (b.name === 'left' || b.name === 'right') && b.name !== cur) { this.pointerMap.set(e.pointerId, b.name); apply(); }
    });
    const up = (e) => { if (this.pointerMap.delete(e.pointerId)) apply(); };
    canvas.addEventListener('pointerup', up);
    canvas.addEventListener('pointercancel', up);
    canvas.addEventListener('pointerleave', up);
    this.releaseAllTouch = () => { this.pointerMap.clear(); apply(); };
  }

  layout() {
    // Pixi 的 resizeTo 會延到下一幀才改尺寸；先同步改好，下面才拿得到新的寬高
    if (this.app.resize) this.app.resize();
    const W = this.W, H = this.H;
    const s = Math.min(1.25, Math.max(0.62, Math.min(W / 1100, H / 620)));
    this.scale = s;
    // 左上：圈數與時間
    this.panel.clear().roundRect(12, 12, 250 * s, 116 * s, 18 * s).fill({ color: 0x0b1733, alpha: 0.42 });
    for (const t of [this.tLap, this.tTime, this.tSub]) t.scale.set(s);
    this.tLap.position.set(26 * s, 18 * s);
    this.tTime.position.set(26 * s, 58 * s);
    this.tSub.position.set(26 * s, 92 * s);
    this.tPlace.scale.set(s);
    this.tPlace.position.set(22 * s, 128 * s);
    this.tPlaceOf.scale.set(s);
    this.boardPos = { x: 12, y: 206 * s, w: 170 * s, row: 24 * s, s };
    // 下方中央：速度、集氣條
    this.tSpeed.scale.set(s);
    this.tKmh.scale.set(s);
    this.tSpeed.position.set(W / 2 - 14 * s, H - 54 * s);
    this.tKmh.position.set(W / 2 + 30 * s, H - 62 * s);
    this.gaugePos = { x: W / 2, y: H - 34 * s, w: 300 * s, s };
    this.meterPos = { x: W / 2, y: H - 150 * s, w: 300 * s, s };
    this.tMeter.scale.set(s);
    this.tCount.scale.set(s);
    this.tCount.position.set(W / 2, H * 0.4);
    this.tWarn.scale.set(s);
    this.tWarn.position.set(W / 2, H * 0.28);
    this.pauseBtn.scale.set(s);
    this.pauseBtn.position.set(W - 40 * s, 40 * s);
    // 小地圖：暫停鈕下方；矮螢幕縮小，免得壓到觸控的氮氣鈕
    const size = Math.round(Math.min(190 * s, H * 0.36));
    this.miniPos = { size, pad: 12 * s, s };
    this.mini.position.set(W - 12 - size, 74 * s);
    this.drawMiniTrack();
    // 觸控按鈕
    const r = Math.max(36, Math.min(H * 0.105, 70));
    const pos = {
      left: [16 + r * 1.25, H - r * 1.45, r * 1.05],
      right: [16 + r * 3.65, H - r * 1.45, r * 1.05],
      drift: [W - 16 - r * 1.3, H - r * 1.4, r * 1.15],
      jet: [W - 16 - r * 3.75, H - r * 1.15, r * 0.88],
      nitro: [W - 16 - r * 1.3, H - r * 3.85, r * 0.88],
      down: [W - 16 - r * 3.7, H - r * 3.35, r * 0.62],
    };
    for (const b of this.touchButtons) {
      const [x, y, rr] = pos[b.name];
      b.c.position.set(x, y);
      b.r = rr;
      this.drawTouch(b);
    }
    if (this.overlayLayout) this.overlayLayout();
  }

  setRaceVisible(v, touch) {
    this.race.visible = v;
    this.touchLayer.visible = v && touch;
    if (!v && this.releaseAllTouch) this.releaseAllTouch();
  }

  /** 每幀更新 HUD；st 由 main 組好 */
  updateRace(st, k, dt) {
    const s = this.scale;
    this.tLap.text = st.mode === 'free' ? `練習 第 ${Math.max(1, st.lap)} 圈` : `LAP ${Math.min(st.lap, st.laps)}/${st.laps}`;
    this.tTime.text = fmtTime(st.time);
    this.tSub.text = `本圈 ${fmtTime(st.lapTime)}   最佳 ${fmtTime(st.bestLap)}`;
    this.tSpeed.text = String(Math.round(Math.abs(k.spd) * 3.6 * 1.8));
    this.tSpeed.style.fill = k.nitroT > 0 ? '#7fd3ff' : k.boostT > 0 ? '#ffb347' : '#ffffff';

    // 集氣條＋兩格氮氣
    const g = this.gauge, gp = this.gaugePos;
    g.clear();
    const bw = gp.w, bh = 14 * s, x0 = gp.x - bw / 2 - 30 * s, y0 = gp.y - bh / 2;
    g.roundRect(x0 - 3, y0 - 3, bw + 6, bh + 6, bh / 2 + 3).fill({ color: 0x0b1733, alpha: 0.55 });
    const fillW = Math.max(0, Math.min(1, k.gauge)) * bw;
    if (fillW > 1) g.roundRect(x0, y0, fillW, bh, bh / 2).fill({ color: k.nitroT > 0 ? 0x5fb8ff : 0x34d6ff });
    if (k.nitroT > 0) {
      const f = k.nitroT / P.nitroTime;
      g.roundRect(x0, y0 + bh + 4, bw * f, 4 * s, 2).fill({ color: 0x9fdcff });
    }
    for (let i = 0; i < 2; i++) {
      const cx = x0 + bw + 22 * s + i * 30 * s;
      g.circle(cx, gp.y, 12 * s).fill({ color: i < k.nitros ? 0x3a86ff : 0x0b1733, alpha: i < k.nitros ? 1 : 0.5 }).stroke({ width: 2.5, color: 0xffffff, alpha: 0.85 });
      if (i < k.nitros) g.circle(cx - 3 * s, gp.y - 3 * s, 4 * s).fill({ color: 0xffffff, alpha: 0.7 });
    }

    // 小噴時機表
    const m = this.meter, mp = this.meterPos;
    m.clear();
    this.tMeter.text = '';
    const w = k.jetWin;
    if (w) {
      const mw = mp.w, mh = 16 * s, mx = mp.x - mw / 2, my = mp.y;
      m.roundRect(mx - 4, my - 4, mw + 8, mh + 8, 8).fill({ color: 0x0b1733, alpha: 0.55 });
      if (w.stage === 1) {
        // 左邊 30°、右邊 0°：車身越正越往右，綠區＝完美
        const span = 30;
        const xp = (deg) => mx + mw * (1 - Math.min(span, deg) / span);
        m.rect(mx, my, xp(P.jetGood) - mx, mh).fill({ color: 0xff6b6b, alpha: 0.75 });
        m.rect(xp(P.jetGood), my, xp(P.jetPerfect) - xp(P.jetGood), mh).fill({ color: 0xffd23f, alpha: 0.85 });
        m.rect(xp(P.jetPerfect), my, mx + mw - xp(P.jetPerfect), mh).fill({ color: 0x4cd964, alpha: 0.95 });
        const cx = xp(k.slipDeg);
        m.roundRect(cx - 3, my - 7, 6, mh + 14, 3).fill(0xffffff).stroke({ width: 2, color: 0x14244a });
        const left = 1 - w.t / P.jetWindow;
        m.rect(mx, my + mh + 6, mw * Math.max(0, left), 4 * s).fill({ color: 0xffffff, alpha: 0.8 });
        this.tMeter.text = `按 ${this.input.autoThrottle ? '噴' : keysOf('up')}：小噴（車身回正到綠區最完美）`;
      } else {
        const span = P.djMax + 0.1;
        const xp = (t) => mx + mw * Math.min(1, t / span);
        m.rect(mx, my, xp(P.djMin) - mx, mh).fill({ color: 0xff6b6b, alpha: 0.75 });
        m.rect(xp(P.djMin), my, xp(P.djMax) - xp(P.djMin), mh).fill({ color: 0x4cd964, alpha: 0.95 });
        const cx = xp(w.t);
        m.roundRect(cx - 3, my - 7, 6, mh + 14, 3).fill(0xffffff).stroke({ width: 2, color: 0x14244a });
        this.tMeter.text = `再按一次：雙噴`;
      }
      this.tMeter.position.set(mp.x, my - 10 * s);
    }
    const jb = this.touchButtons.find((b) => b.name === 'jet');
    const glow = !!w;
    if (jb && jb.glow !== glow) { jb.glow = glow; this.drawTouch(jb); }

    this.tWarn.visible = !!st.wrongWay;
    this.drawMiniDot(k, st.others || []);

    // 名次與排行（只有競賽模式）
    const racing = !!st.standings;
    this.tPlace.visible = this.tPlaceOf.visible = this.board.visible = racing;
    if (racing) {
      const place = st.place;
      this.tPlace.text = String(place);
      this.tPlace.style.fill = ['#ffd23f', '#e0e6ee', '#ffb26b', '#ffffff'][place - 1];
      this.tPlaceOf.position.set(this.tPlace.x + this.tPlace.width + 4 * s, this.tPlace.y + this.tPlace.height - 8 * s);
      const bp = this.boardPos;
      this.boardBg.clear().roundRect(bp.x, bp.y, bp.w, bp.row * 4 + 10 * s, 12 * s).fill({ color: 0x0b1733, alpha: 0.42 });
      st.standings.forEach((row, i) => {
        const t = this.boardRows[i];
        t.text = `${i + 1}  ${row.name}`;
        t.style.fill = row.isPlayer ? '#ffd23f' : '#ffffff';
        t.scale.set(s);
        t.position.set(bp.x + 26 * s, bp.y + 5 * s + i * bp.row);
        this.boardBg.circle(bp.x + 14 * s, bp.y + 5 * s + i * bp.row + 11 * s, 6 * s).fill(row.color);
      });
    }
    // 對手名牌
    const tags = st.tags || [];
    while (this.tagPool.length < tags.length) {
      const t = new Text({ text: '', style: style(16, '#ffffff') });
      t.anchor.set(0.5, 1);
      this.tags.addChild(t);
      this.tagPool.push(t);
    }
    this.tagPool.forEach((t, i) => {
      const g = tags[i];
      t.visible = !!g;
      if (!g) return;
      t.text = g.name;
      t.style.fill = g.color;
      t.alpha = g.a;
      t.scale.set(s);
      t.position.set(g.x, g.y);
    });

    // 速度線
    const ln = this.lines;
    ln.clear();
    // 噴射時最濃；沒噴射但接近極速時也淡淡出現
    const fast = Math.max(0, Math.min(1, (Math.abs(k.spd) / P.maxSpeed - 0.8) / 0.25));
    const inten = Math.min(1.5, Math.max(k.nitroT > 0 ? 1 : k.boostT > 0 ? 0.6 : 0, fast * 0.4) * P.speedFx);
    if (inten > 0 && this.race.visible) {
      const W = this.W, H = this.H, cx = W / 2, cy = H * 0.45;
      const n = Math.round(26 * inten);
      for (let i = 0; i < n; i++) {
        const a = Math.random() * Math.PI * 2;
        const r0 = Math.max(W, H) * (0.36 + Math.random() * 0.2);
        const r1 = r0 + Math.max(W, H) * (0.12 + Math.random() * 0.2);
        ln.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0).lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1);
      }
      ln.stroke({ width: 2.5, color: k.nitroT > 0 ? 0xbfe6ff : 0xffffff, alpha: 0.55 });
    }

    // 彈出文字
    for (let i = this.popups.length - 1; i >= 0; i--) {
      const p = this.popups[i];
      p.t += dt;
      const a = p.t < 0.12 ? p.t / 0.12 : 1 - Math.max(0, (p.t - p.life + 0.3) / 0.3);
      p.o.alpha = Math.max(0, a);
      p.o.scale.set(s * (p.t < 0.12 ? 1.4 - p.t / 0.12 * 0.4 : 1));
      p.o.y = p.y - p.t * 18;
      if (p.t >= p.life) { p.o.destroy(); this.popups.splice(i, 1); }
    }
  }

  popup(text, color = '#ffffff', size = 44, life = 1.0, dy = 0) {
    const o = new Text({ text, style: style(size, color) });
    o.anchor.set(0.5);
    const y = this.H * 0.3 + dy * this.scale;
    o.position.set(this.W / 2, y);
    this.race.addChild(o);
    // 同一位置只留最新的
    for (const p of this.popups) if (p.dy === dy) p.t = Math.max(p.t, p.life - 0.15);
    this.popups.push({ o, t: 0, life, y, dy });
  }

  countdown(text, color = '#ffd23f') {
    this.tCount.text = text;
    this.tCount.style.fill = color;
    this.tCount.visible = !!text;
  }

  // ------------------------------------------------------------ 覆蓋層：首頁、暫停、成績、載入
  clearOverlay() {
    this.overlay.removeChildren().forEach((c) => c.destroy({ children: true }));
    this.overlayLayout = null;
  }

  showLoading(p) {
    if (!this.loadText) {
      this.clearOverlay();
      this.loadText = new Text({ text: '', style: style(28) });
      this.loadText.anchor.set(0.5);
      this.overlay.addChild(this.loadText);
      this.overlayLayout = () => this.loadText.position.set(this.W / 2, this.H / 2);
      this.overlayLayout();
    }
    this.loadText.text = `載入賽道中… ${Math.round(p * 100)}%`;
  }

  /** 首頁：賽道卡片（點了就換賽道，背景跟著換）＋三種模式 */
  showTitle({ version, tracks, selected, best, touch, loading, onSelect, onStart, onHelp, onSettings }) {
    this.clearOverlay();
    this.loadText = null;
    const o = this.overlay;
    const shade = new Graphics();
    const logo = new Text({ text: 'KCar', style: style(104, '#ffd23f', { letterSpacing: 6 }) });
    logo.anchor.set(0.5);
    const sub = new Text({ text: '甩尾 ‧ 小噴 ‧ 氮氣', style: style(22, '#ffffff', { letterSpacing: 2 }) });
    sub.anchor.set(0.5);
    const cards = tracks.map((tr) => {
      const c = new Container();
      const g = new Graphics();
      const sel = tr.id === selected;
      const W = 150, H = 92;
      g.roundRect(-W / 2, -H / 2 + 4, W, H, 14).fill({ color: 0x0b1733, alpha: 0.45 });
      g.roundRect(-W / 2, -H / 2, W, H, 14).fill({ color: sel ? 0xffd23f : 0x14244a, alpha: sel ? 1 : 0.78 })
        .stroke({ width: sel ? 4 : 2, color: sel ? 0xffffff : 0x8fb3ff, alpha: sel ? 1 : 0.6 });
      const name = new Text({ text: tr.name, style: style(21, sel ? '#14244a' : '#ffffff', { stroke: { width: sel ? 0 : 3, color: '#14244a' }, dropShadow: false }) });
      name.anchor.set(0.5);
      name.y = -20;
      const stars = new Text({ text: '★'.repeat(tr.difficulty) + '☆'.repeat(5 - tr.difficulty), style: style(17, sel ? '#c0392b' : '#ffd23f', { stroke: { width: 0 }, dropShadow: false }) });
      stars.anchor.set(0.5);
      stars.y = 6;
      const b = best[tr.id] || {};
      const rec = new Text({ text: b.lap ? `最佳 ${fmtTime(b.lap)}` : '尚無紀錄', style: style(13, sel ? '#14244a' : '#cfe6ff', { stroke: { width: 0 }, dropShadow: false }) });
      rec.anchor.set(0.5);
      rec.y = 29;
      c.addChild(g, name, stars, rec);
      c.eventMode = 'static';
      c.cursor = 'pointer';
      c.on('pointertap', (e) => { e.stopPropagation(); onSelect(tr.id); });
      return c;
    });
    const modes = [
      button('競賽（對 3 位電腦）', 300, 62, 0xff5a3d, () => onStart('race')),
      button('計時賽', 200, 62, 0x7b61ff, () => onStart('time')),
      button('自由練習', 200, 62, 0x2a9df4, () => onStart('free')),
    ];
    const loadT = new Text({ text: loading ? '載入賽道中…' : '', style: style(20, '#ffffff') });
    loadT.anchor.set(0.5);
    this.titleLoadText = loadT;
    for (const m of modes) m.alpha = loading ? 0.45 : 1;
    const cur = best[selected] || {};
    const bestT = new Text({ text: `這條賽道　最佳單圈 ${fmtTime(cur.lap)}　計時賽最佳 ${fmtTime(cur.total)}`, style: style(16, '#e8f4ff') });
    bestT.anchor.set(0.5);
    const help = new Text({
      text: touch
        ? '◀ ▶ 轉向（自動油門）．按住「甩尾」＋方向起甩．放開回正時按「噴」＝小噴，再按一次＝雙噴．集滿氣按「氮氣」'
        : `${keysOf('left')} ${keysOf('right')} 轉向．${keysOf('up')} 油門．${keysOf('down')} 煞車．${keysOf('drift')}＋方向 甩尾．`
          + `甩尾時鬆 ${keysOf('up')}，回正時再按 ${keysOf('up')}＝小噴，再按一次＝雙噴．${keysOf('nitro')} 氮氣`,
      style: style(14, '#ffffff', { wordWrap: true, wordWrapWidth: 900, align: 'center' }),
    });
    help.anchor.set(0.5, 1);
    const ver = new Text({ text: `v${version}`, style: style(18, '#ffffff') });
    ver.anchor.set(1, 1);
    // 右上角：操作說明、設定
    const small = (label, color, fn) => button(label, 150, 46, color, fn);
    const bHelp = small('操作說明', 0x2a9df4, () => onHelp && onHelp());
    const bSet = small('設定', 0x4a5a7a, () => onSettings && onSettings());
    o.addChild(shade, logo, sub, ...cards, ...modes, loadT, bestT, help, ver, bHelp, bSet);
    this.overlayLayout = () => {
      const W = this.W, H = this.H;
      const s = Math.min(1.1, Math.max(0.45, Math.min(W / 1060, H / 640)));
      shade.clear().rect(0, 0, W, H).fill({ color: 0x0b1733, alpha: 0.22 });
      logo.scale.set(s); logo.position.set(W / 2, H * 0.13);
      sub.scale.set(s); sub.position.set(W / 2, H * 0.13 + 62 * s);
      const cw = 162 * s, cy = H * 0.13 + 140 * s;
      cards.forEach((c, i) => { c.scale.set(s); c.position.set(W / 2 + (i - 2.5) * cw, cy); });
      const my = cy + 104 * s;
      // 三顆寬 300／200／200、間隔 20，整排置中
      const xs = [-220, 50, 270].map((x) => x * s);
      modes.forEach((m, i) => { m.scale.set(s); m.position.set(W / 2 + xs[i], my); });
      loadT.scale.set(s); loadT.position.set(W / 2, my + 48 * s);
      bestT.scale.set(s); bestT.position.set(W / 2, my + 52 * s);
      bestT.visible = !loading;
      help.style.wordWrapWidth = Math.min(900, (W - 40) / s);
      help.scale.set(s); help.position.set(W / 2, H - 10);
      ver.scale.set(s); ver.position.set(W - 14, H - 10 - help.height - 4);
      bSet.scale.set(s); bSet.position.set(W - 16 - 75 * s, 14 + 23 * s);
      bHelp.scale.set(s); bHelp.position.set(W - 16 - 75 * s - 160 * s, 14 + 23 * s);
    };
    this.overlayLayout();
  }

  setTitleLoading(p) {
    if (this.titleLoadText) this.titleLoadText.text = `載入賽道中… ${Math.round(p * 100)}%`;
  }

  showPause({ onResume, onRestart, onHelp, onSettings, onHome }) {
    this.clearOverlay();
    const o = this.overlay;
    const shade = new Graphics();
    const title = new Text({ text: '暫停', style: style(64, '#ffd23f') });
    title.anchor.set(0.5);
    const bs = [
      button('繼續', 280, 58, 0x2a9df4, onResume),
      button('重新開始', 280, 58, 0xff5a3d, onRestart),
      button('操作說明', 280, 58, 0x16a085, onHelp),
      button('設定（按鍵／調參）', 280, 58, 0x7b61ff, onSettings),
      button('回首頁', 280, 58, 0x4a5a7a, onHome),
    ];
    o.addChild(shade, title, ...bs);
    this.overlayLayout = () => {
      const W = this.W, H = this.H;
      const s = Math.min(1, Math.max(0.5, Math.min(W / 1000, H / 680)));
      shade.clear().rect(0, 0, W, H).fill({ color: 0x0b1733, alpha: 0.55 });
      title.scale.set(s); title.position.set(W / 2, H * 0.13);
      bs.forEach((b, i) => { b.scale.set(s); b.position.set(W / 2, H * 0.13 + 82 * s + i * 70 * s); });
    };
    this.overlayLayout();
  }

  showResult({ mode, track, total, laps, bestLap, newLap, newTotal, order, onRetry, onHome }) {
    this.clearOverlay();
    const o = this.overlay;
    const shade = new Graphics();
    const place = order ? order.findIndex((r) => r.isPlayer) + 1 : 0;
    const titleText = mode === 'race' ? ['冠軍！', '第 2 名', '第 3 名', '第 4 名'][place - 1] : mode === 'time' ? '完賽！' : '練習結束';
    const title = new Text({ text: `${titleText}`, style: style(70, place === 1 || mode !== 'race' ? '#ffd23f' : '#ffffff') });
    title.anchor.set(0.5);
    const sub = new Text({ text: track || '', style: style(22, '#cfe6ff') });
    sub.anchor.set(0.5);
    const lines = [];
    if (mode === 'race') {
      order.forEach((r, i) => lines.push(`${i + 1}　${r.name.padEnd(7, ' ')}　${r.done ? '' : '≈'}${fmtTime(r.t)}${r.isPlayer ? '　◀ 你' : ''}`));
      lines.push('');
      lines.push(`最快單圈 ${fmtTime(bestLap)}${newLap ? '  ★新紀錄' : ''}`);
    } else {
      if (mode === 'time') lines.push(`總時間 ${fmtTime(total)}${newTotal ? '  ★新紀錄' : ''}`);
      laps.forEach((t, i) => lines.push(`第 ${i + 1} 圈  ${fmtTime(t)}${t === bestLap && newLap ? '  ★最佳單圈' : ''}`));
    }
    const body = new Text({ text: lines.join('\n'), style: style(26, '#ffffff', { align: 'center', lineHeight: 40 }) });
    body.anchor.set(0.5, 0);
    const b1 = button('再跑一次', 260, 60, 0xff5a3d, onRetry);
    const b2 = button('回首頁', 260, 60, 0x4a5a7a, onHome);
    o.addChild(shade, title, sub, body, b1, b2);
    this.overlayLayout = () => {
      const W = this.W, H = this.H;
      const s = Math.min(1, Math.max(0.5, Math.min(W / 1000, H / 680)));
      shade.clear().rect(0, 0, W, H).fill({ color: 0x0b1733, alpha: 0.55 });
      title.scale.set(s); title.position.set(W / 2, H * 0.12);
      sub.scale.set(s); sub.position.set(W / 2, H * 0.12 + 56 * s);
      body.scale.set(s); body.position.set(W / 2, H * 0.12 + 86 * s);
      b1.scale.set(s); b1.position.set(W / 2 - 140 * s, H * 0.84);
      b2.scale.set(s); b2.position.set(W / 2 + 140 * s, H * 0.84);
    };
    this.overlayLayout();
  }

  render() { this.app.render(); }
}
