// 電腦車手：用跟玩家完全相同的 Kart 物理，只是把「按鍵」交給程式決定。
// 也給 tools/sim.mjs 當自動駕駛用（skill 開滿＝每個彎都甩、每次都完美小噴＋雙噴）。
//
// skill 欄位（0..1 越大越強，除非另註）：
//   speed     極速倍率（乘在 P.maxSpeed 上，約 0.9～1.02）
//   drift     遇到彎會甩尾的機率
//   perfect   小噴打到完美的機率（其餘是普通或太早）
//   dj        接雙噴的機率
//   nitro     有氮氣就會用的機率（每秒判一次）
//   line      走線準度：越低越常偏離理想路線、彎前判斷越晚
//   lane      偏好的橫向位置（公尺，右正），避免四台車疊成一條線

import { P } from './tuning.js';

const wrap = (a) => {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
};

export const PERFECT_SKILL = { speed: 1, drift: 1, perfect: 1, dj: 1, nitro: 1, line: 1, lane: 0 };

export class AutoDriver {
  constructor(kart, skill, rng = Math.random) {
    this.kart = kart;
    this.skill = { ...PERFECT_SKILL, ...skill };
    this.rng = rng;
    this.keys = new Set();
    this.edges = new Set();
    this.st = { drifting: false, dir: 0, t0: 0, wantJet: null, nitroWait: 0, stuck: 0, laneT: 0 };
    this.lane = this.skill.lane;
    this.t = 0;
    this.decide = 0;
    // 給 Kart.step 用的輸入介面（跟 Input 一樣的形狀）
    const self = this;
    this.input = {
      get steer() { return (self.keys.has('right') ? 1 : 0) - (self.keys.has('left') ? 1 : 0); },
      get throttle() { return self.keys.has('up') ? 1 : 0; },
      get braking() { return self.keys.has('down'); },
      get driftHeld() { return self.keys.has('drift'); },
      get jet() { return self.edges.has('up'); },
      pressed: (a) => self.edges.has(a),
    };
  }

  set(a, v) {
    if (v && !this.keys.has(a)) this.edges.add(a);
    if (v) this.keys.add(a); else this.keys.delete(a);
  }

  /** 每個物理步呼叫一次（決策 60Hz）；others：其他車（閃車用） */
  think(dt, others = []) {
    this.edges.clear();
    this.t += dt;
    this.decide -= dt;
    if (this.decide > 0) return;
    this.decide = 1 / 60;
    const k = this.kart, tr = k.track, sk = this.skill, st = this.st;
    const headAt = (s) => { const p = tr.pointAt(s); return Math.atan2(p.tx, p.tz); };
    const s = k.lastS, v = Math.max(5, k.spd);

    // 卡住（撞牆停下、倒退）就重生
    st.stuck = k.spd < 2 ? st.stuck + 1 / 60 : 0;
    if (st.stuck > 2.5) { k.respawn(); st.stuck = 0; st.drifting = false; }

    // 換線：前方 12m 內同一線有車就往旁邊閃
    st.laneT -= 1 / 60;
    if (st.laneT <= 0) {
      st.laneT = 0.5;
      let block = false;
      for (const o of others) {
        const ds = o.dist - k.dist;
        if (ds > 0 && ds < 12 && Math.abs((o.proj.d ?? 0) - this.lane) < 2.2) block = true;
      }
      const hw = k.proj.hw ?? tr.halfWidth;
      if (block) this.lane = Math.max(-hw + 2, Math.min(hw - 2, this.lane + (this.rng() < 0.5 ? -3 : 3)));
      else if (Math.abs(this.lane) > hw - 1.5) this.lane = Math.sign(this.lane) * Math.max(0, hw - 1.5);
      else this.lane += (sk.lane - this.lane) * 0.2;
    }

    const look = 8 + v * (0.4 + 0.08 * (1 - sk.line));
    const p = tr.pointAt(s + look);
    const tx = p.x + -p.tz * this.lane, tz = p.z + p.tx * this.lane;
    const wobble = (1 - sk.line) * 0.06 * Math.sin(this.t * 1.7 + sk.lane);
    const err = wrap(Math.atan2(tx - k.x, tz - k.z) - (k.spd > 3 ? k.phi : k.h)) + wobble; // 用路線方向（回正中車頭還歪著）
    const turnAhead = wrap(headAt(s + 28 + v * 0.45) - headAt(s + 8)); // 車速越快看越遠（路線跟上車頭要時間）

    if (!k.drift && !st.drifting && Math.abs(turnAhead) > 0.75 && k.spd > 18 && !st.skipCorner) {
      if (this.rng() < sk.drift) {
        st.drifting = true;
        st.dir = turnAhead < 0 ? 1 : -1;
        st.t0 = this.t;
        this.set('up', false);
        this.set('drift', true);
      } else st.skipCorner = true;
    }
    if (st.skipCorner && Math.abs(turnAhead) < 0.3) st.skipCorner = false;
    if (st.drifting && !k.drift && this.t - st.t0 > 0.3) { st.drifting = false; this.set('drift', false); }

    if (st.drifting) {
      const key = st.dir > 0 ? 'right' : 'left', other = st.dir > 0 ? 'left' : 'right';
      if (!k.drift) { this.set(other, false); this.set(key, true); }
      else {
        // 甩尾中方向鍵控制車頭轉多快，路線慢半拍跟上（抓地力低）：
        // 先預估 0.35 秒後的路線方向，再算要車頭轉多快才對得準目標，換成內切／外拉
        // 純追蹤：要的路線轉速 = 2v·sinα / 前視距離；路線目前轉速 ≈ driftGrip × 側滑角，差多少就多壓車頭
        const dx = tx - k.x, dz = tz - k.z;
        const Ld = Math.max(6, Math.hypot(dx, dz));
        const alpha = wrap(Math.atan2(dx, dz) - k.phi) + wobble;
        const wantPath = -2 * v * Math.sin(alpha) / Ld * st.dir; // 往彎內為正
        const pathNow = P.driftGrip * wrap(k.phi - k.h) * st.dir; // 往彎內為正
        const want = wantPath + 1.6 * (wantPath - pathNow);
        const rel = (want - P.driftTurn) / Math.max(0.05, P.driftTurnSteer);
        this.set(key, rel > 0.3);
        this.set(other, rel < -0.4);
        this.set('down', rel > 1.6 && sk.line > 0.7);
      }
      const remain = wrap(headAt(s + 25) - k.phi);
      if (k.drift && Math.abs(turnAhead) < 0.35 && Math.abs(remain) < 0.25) {
        this.set('drift', false);
        this.set(key, false);
        st.drifting = false;
        // 這次小噴要打多準：完美／普通／太早
        const r = this.rng();
        st.wantJet = r < sk.perfect ? P.jetPerfect * 0.8 : r < sk.perfect + (1 - sk.perfect) * 0.6 ? P.jetGood * 0.9 : 99;
        st.wantDj = this.rng() < sk.dj;
      }
    } else {
      this.set('drift', false);
      this.set('down', false);
      this.set('left', err > 0.04);
      this.set('right', err < -0.04);
      const w = k.jetWin;
      if (st.wantJet != null && w) {
        if (w.stage === 1) {
          if (k.slipDeg < st.wantJet) this.set('up', true);
        } else if (st.wantDj && w.t > (P.djMin + P.djMax) / 2) {
          if (this.keys.has('up')) this.set('up', false);
          else { this.set('up', true); st.wantJet = null; }
        } else if (!st.wantDj) { st.wantJet = null; this.set('up', true); } else this.set('up', false);
      } else {
        st.wantJet = null;
        this.set('up', true);
      }
      st.nitroWait -= 1 / 60;
      if (k.nitros > 0 && Math.abs(turnAhead) < 0.2 && st.nitroWait <= 0) {
        st.nitroWait = 1;
        if (this.rng() < sk.nitro) this.set('nitro', true);
      } else this.set('nitro', false);
    }
  }
}
