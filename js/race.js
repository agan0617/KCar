// 一場比賽：起跑格、每台車的圈數與名次、車與車的碰撞、電腦車手。
// 純邏輯（不碰 three.js），遊戲與 tools/sim.mjs 共用。

import { Kart } from './kart.js';
import { AutoDriver } from './bot.js';

export const PLAYER = { name: 'Komugi', color: '#e8322b' };
// 三位電腦對手（柴犬三兄妹），顏色也用在卡丁車、小地圖與名牌
export const RIVALS = [
  { name: 'Mochi', color: '#2f80ed', kart: '#2f80ed', hoodie: '#ffffff', fur: '#f3ede2', cream: '#ffffff' },
  { name: 'Azuki', color: '#34c759', kart: '#34c759', hoodie: '#ffcc00', fur: '#3b2f2f', cream: '#e8c9a0' },
  { name: 'Kinako', color: '#a259ff', kart: '#a259ff', hoodie: '#ff7aa2', fur: '#d9b07a', cream: '#fff4e2' },
];

/**
 * 電腦強度：賽道難度 d（1～5）× 第幾位對手（0 最強、2 最弱）。
 * 數字用 tools/sim.mjs race 校準過：簡單賽道上打得好的玩家能贏，最難的賽道要接近每彎完美小噴才贏得了。
 */
export function rivalSkill(d, idx) {
  const t = (d - 1) / 4; // 0..1
  const lane = [-2.2, 2.2, 0][idx];
  return {
    speed: 0.925 + 0.065 * t - idx * 0.018,
    drift: 0.55 + 0.45 * t - idx * 0.08,
    perfect: 0.15 + 0.7 * t - idx * 0.12,
    dj: 0.1 + 0.75 * t - idx * 0.1,
    nitro: 0.6 + 0.4 * t,
    line: 0.55 + 0.45 * t - idx * 0.1,
    lane,
  };
}

const GRID = [[-8, -3.2], [-8, 3.2], [-16, -3.2], [-16, 3.2]];
const KART_R = 0.85;

export class Race {
  /**
   * mode：race（對 3 台電腦）／time（計時賽）／free（自由練習）
   * playerSkill：給 sim 用，玩家也由自動駕駛開
   */
  constructor(track, { mode = 'race', laps = 3, difficulty = 2, rng = Math.random, playerSkill = null } = {}) {
    this.track = track;
    this.mode = mode;
    this.laps = mode === 'free' ? Infinity : laps;
    this.clock = 0;
    this.racers = [];
    const L = track.length;
    const add = (info, gridIdx, driverSkill) => {
      const kart = new Kart(track);
      const [ds, lat] = mode === 'race' ? GRID[gridIdx] : [-8, 0];
      kart.resetRace(L + ds, lat);
      const r = { ...info, kart, driver: driverSkill ? new AutoDriver(kart, driverSkill, rng) : null, lapsDone: 0, lapStart: 0, laps: [], finishT: null, baseSpeed: driverSkill ? driverSkill.speed : 1 };
      this.racers.push(r);
      return r;
    };
    if (mode === 'race') {
      RIVALS.forEach((rv, i) => add({ ...rv, isPlayer: false }, i, rivalSkill(difficulty, i)));
    }
    this.player = add({ ...PLAYER, isPlayer: true }, mode === 'race' ? 3 : 0, playerSkill);
    if (this.player.driver) this.player.baseSpeed = 1;
  }

  /** 一個物理步。input：玩家的輸入（自動駕駛時忽略）；control：倒數中為 false */
  step(dt, input, control) {
    if (control) this.clock += dt;
    const karts = this.racers.map((r) => r.kart);
    const pd = this.player.kart.dist;
    for (const r of this.racers) {
      const k = r.kart;
      if (!r.isPlayer) k.events.length = 0; // 電腦車的事件沒人看，別一直堆
      if (r.driver) {
        r.driver.think(dt, karts.filter((o) => o !== k));
        if (!r.isPlayer) {
          // 輕微追趕機制：落後玩家太多就稍快、領先太多就稍慢（最多 ±5%）
          const gap = pd - k.dist;
          k.topMul = r.baseSpeed + Math.max(-0.03, Math.min(0.05, gap / 600));
          if (r.finishT != null) k.topMul = 0.85;
        }
        k.step(dt, r.driver.input, control);
      } else {
        k.step(dt, input, control);
      }
    }
    if (karts.length > 1) this.collide(karts);
    if (!control) return;
    const L = this.track.length;
    for (const r of this.racers) {
      const n = Math.floor(r.kart.dist / L);
      if (n > r.lapsDone) {
        r.lapsDone = n;
        r.laps.push(this.clock - r.lapStart);
        r.lapStart = this.clock;
        if (r.lapsDone >= this.laps && r.finishT == null) r.finishT = this.clock;
        r.lapEvent = true;
      }
    }
  }

  collide(karts) {
    const minD = KART_R * 2;
    for (let i = 0; i < karts.length; i++) {
      for (let j = i + 1; j < karts.length; j++) {
        const a = karts[i], b = karts[j];
        if (Math.abs(a.y - b.y) > 2) continue;
        let dx = b.x - a.x, dz = b.z - a.z;
        const d = Math.hypot(dx, dz);
        if (d >= minD || d < 1e-4) continue;
        const nx = dx / d, nz = dz / d, push = (minD - d) / 2;
        a.x -= nx * push; a.z -= nz * push;
        b.x += nx * push; b.z += nz * push;
        const va = [Math.sin(a.phi) * a.spd, Math.cos(a.phi) * a.spd];
        const vb = [Math.sin(b.phi) * b.spd, Math.cos(b.phi) * b.spd];
        const vn = (vb[0] - va[0]) * nx + (vb[1] - va[1]) * nz;
        if (vn >= 0) continue;
        const jmp = vn * (1 + 0.35) / 2;
        va[0] += nx * jmp; va[1] += nz * jmp;
        vb[0] -= nx * jmp; vb[1] -= nz * jmp;
        for (const [k, v] of [[a, va], [b, vb]]) {
          const sp = Math.hypot(v[0], v[1]);
          if (k.spd >= 0) { k.phi = Math.atan2(v[0], v[1]); k.spd = sp; } else { k.phi = Math.atan2(-v[0], -v[1]); k.spd = -sp; }
          k.events.push({ type: 'bump', impact: -vn });
        }
      }
    }
  }

  /** 名次：先比完賽時間，沒完賽的比跑的距離 */
  standings() {
    return [...this.racers].sort((a, b) => {
      if (a.finishT != null && b.finishT != null) return a.finishT - b.finishT;
      if (a.finishT != null) return -1;
      if (b.finishT != null) return 1;
      return b.kart.dist - a.kart.dist;
    });
  }

  /** 還沒完賽的車：用目前平均速度估完賽時間（玩家先到終點時結算用） */
  estimateFinish(r) {
    if (r.finishT != null) return r.finishT;
    const total = this.laps * this.track.length;
    const v = Math.max(1, r.kart.dist / Math.max(1, this.clock));
    return this.clock + Math.max(0, total - r.kart.dist) / v;
  }
}
