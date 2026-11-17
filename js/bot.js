// 電腦車手：用跟玩家完全相同的 Kart 物理，只是把「按鍵」交給程式決定。
// 也給 tools/sim.mjs 當自動駕駛用（skill 開滿＝每個彎都甩、甩尾中盡量把側滑角留在甜蜜區間）。
// 小噴是自動的（放開甩尾時依甩尾分觸發），電腦不用決定。
//
// skill 欄位（0..1 越大越強，除非另註）：
//   speed     極速倍率（乘在 P.maxSpeed 上，約 0.9～1.02）
//   drift     遇到彎會甩尾的機率
//   angle     控角率：這次甩尾要不要顧甜蜜區間（顧的話，快掉出區間就不外拉、不點煞）
//   nitro     有氮氣就會用的機率（每秒判一次）
//   line      走線準度：越低越常偏離理想路線、彎前判斷越晚
//   lane      偏好的橫向位置（公尺，右正），避免四台車疊成一條線

import { P } from './tuning.js';

const wrap = (a) => {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
};

export const PERFECT_SKILL = { speed: 1, drift: 1, angle: 1, nitro: 1, line: 1, lane: 0 };

export class AutoDriver {
  constructor(kart, skill, rng = Math.random) {
    this.kart = kart;
    this.skill = { ...PERFECT_SKILL, ...skill };
    this.rng = rng;
    this.keys = new Set();
    this.edges = new Set();
    this.st = { drifting: false, dir: 0, t0: 0, care: false, nitroWait: 0, stuck: 0, laneT: 0 };
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
  think(dt, others = [], control = true) {
    this.edges.clear();
    this.t += dt;
    this.decide -= dt;
    if (this.decide > 0) return;
    this.decide = 1 / 60;
    const k = this.kart, tr = k.track, sk = this.skill, st = this.st;    const headAt = (s) => { const p = tr.pointAt(s); return Math.atan2(p.tx, p.tz); };
    const s = k.lastS, v = Math.max(5, k.spd);

    // 卡住（撞牆停下、倒退）就重生
    // 看「往前進了多少」而不是車速：貼著牆磨的時候車速會在 1～3 m/s 跳來跳去，車速判斷抓不到
    if (!control) { st.stuck = 0; st.progD = k.dist; }
    else if (k.dist > (st.progD ?? k.dist) + 6) { st.stuck = 0; st.progD = k.dist; }
    else st.stuck += 1 / 60;
    if (st.stuck > 3) { k.respawn(); st.stuck = 0; st.progD = k.dist; this.stuckN = (this.stuckN || 0) + 1; }
    // 剛重生（卡住、掉進熔岩或缺口）：甩尾、捷徑的狀態全部清掉，不然會帶著舊方向再開進去
    if ((k.respawns || 0) !== (st.respawns || 0)) {
      st.respawns = k.respawns;
      st.drifting = false; st.sc = null; st.scWait = false; st.scOn = false; st.skipCorner = false;
      for (const a of ['drift', 'left', 'right', 'down']) this.set(a, false);
    }

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
    // 捷徑：入口前 45～90m 決定走不走（走線越準越常走）；入口前 30m 起瞄捷徑上的點，到出口再回主線
    const L = tr.length;
    if (!st.sc && tr.shortcuts) {
      for (const sc of tr.shortcuts) {
        let dIn = sc.from - s;
        if (dIn < -L / 2) dIn += L; else if (dIn > L / 2) dIn -= L;
        if (dIn > 45 && dIn < 90 && st.scSeen !== sc) {
          st.scSeen = sc;
          if (this.rng() < (sk.shortcut ?? Math.max(0, sk.line - 0.6) * 2)) { st.sc = sc; st.scI = 0; st.scWait = true; }
        } else if (dIn < 0 && dIn > -L / 4 && st.scSeen === sc) st.scSeen = null; // 過了入口，下一圈再決定一次
      }
    }
    // 決定走捷徑時正在甩尾：先收掉甩尾，走直線進捷徑（捷徑就是為了省掉那個彎）
    if (st.sc && st.scWait) {
      let dIn = st.sc.from - s;
      if (dIn < -L / 2) dIn += L; else if (dIn > L / 2) dIn -= L;
      if (dIn < 30 && st.drifting) { st.drifting = false; this.set('drift', false); }
      if (dIn < 30) st.scWait = false;
    }
    let tx, tz, onSc = false;
    if (st.sc && !st.scWait) {
      const sc = st.sc, P3 = sc.pts, n = P3.length / 3;
      let bi = st.scI, bd = Infinity;
      for (let i = st.scI; i < Math.min(n, st.scI + 30); i++) {
        const d = (P3[i * 3] - k.x) ** 2 + (P3[i * 3 + 2] - k.z) ** 2;
        if (d < bd) { bd = d; bi = i; }
      }
      st.scI = bi;
      if (bd < 36) st.scOn = true; // 已經開上捷徑
      if (st.scOn && bd > 15 * 15) { st.sc = null; st.scOn = false; bi = n; } // 開上去後又離捷徑太遠（被撞開）：放棄，回主線
      // 前方 25m 的彎度決定能開多快（側向加速度約 28 m/s²）
      const j = Math.min(n - 1, bi + Math.round(25 / sc.spacing)), j0 = Math.min(n - 2, bi + 1);
      const ha = Math.atan2(P3[(j0 + 1) * 3] - P3[j0 * 3], P3[(j0 + 1) * 3 + 2] - P3[j0 * 3 + 2]);
      const hb = Math.atan2(P3[j * 3] - P3[(j - 1) * 3], P3[j * 3 + 2] - P3[(j - 1) * 3 + 2]);
      const bend = Math.abs(wrap(hb - ha));
      st.scVmax = bend < 0.05 ? 99 : Math.sqrt(28 * 25 / bend);
      // 看多遠：捷徑彎的地方看近一點才不會切到草地；直的地方跟主線一樣看遠，不然轉向一直過頭、左右擺盪
      // 窄捷徑（半寬 < 4.5，像雪國山道的土堤）看遠的上限也收小：切線切到水裡比擺盪更糟
      const near = 5 + v * 0.18, far = Math.min(look, near + Math.max(0, sc.hw - 3) * 6), wB = Math.min(1, bend / 0.35);
      const ti = bi + Math.round((far + (near - far) * wB) / sc.spacing);
      if (bi >= n - 3) { st.sc = null; st.scOn = false; } // 出捷徑了（或放棄）
      else if (ti < n) { tx = P3[ti * 3]; tz = P3[ti * 3 + 2]; onSc = true; }
      else {
        const p = tr.pointAt(sc.to + (ti - n + 1) * sc.spacing);
        tx = p.x; tz = p.z; onSc = true;
      }
    }
    if (!onSc) {
      const p = tr.pointAt(s + look);
      tx = p.x + -p.tz * this.lane; tz = p.z + p.tx * this.lane;
    }
    const wobble = (1 - sk.line) * 0.06 * Math.sin(this.t * 1.7 + sk.lane);
    const err = wrap(Math.atan2(tx - k.x, tz - k.z) - (k.spd > 3 ? k.phi : k.h)) + wobble; // 用路線方向（回正中車頭還歪著）
    // 車速越快看越遠（路線跟上車頭要時間）；entry（公尺，給 sim 用）＞0 起甩提早、＜0 延後
    const turnAhead = wrap(headAt(s + 28 + v * 0.45) - headAt(s + 8));
    const ent = sk.entry || 0;
    const turnIn = ent ? wrap(headAt(s + 28 + v * 0.45 + ent) - headAt(s + 8 + ent)) : turnAhead;

    if (!onSc && !k.drift && !st.drifting && Math.abs(turnIn) > 0.75 && k.spd > 18 && !st.skipCorner) {
      if (this.rng() < sk.drift) {
        st.drifting = true;
        st.dir = turnIn < 0 ? 1 : -1;
        st.t0 = this.t;
        st.care = this.rng() < (sk.angle ?? 1);
        this.set('up', true); // 甩尾中照踩油門
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
        let inn = rel > 0.3, out = rel < -0.4, brk = rel > 1.6 && sk.line > 0.7;
        if (st.care) {
          // 顧甜蜜區間：快掉出下限就不外拉（改不按），快超過上限就不點煞（改內切）；撞牆風險由走線準度承擔
          const sd = k.slipDeg;
          if (out && sd < P.driftBandMin + 2) out = false;
          if (brk && sd > P.driftBandMax - 2) { brk = false; inn = true; }
        }
        this.set(key, inn);
        this.set(other, out);
        this.set('down', brk);
      }
      const remain = wrap(headAt(s + 25) - k.phi);
      if (k.drift && Math.abs(turnAhead) < 0.35 && Math.abs(remain) < 0.25) {
        this.set('drift', false);
        // 放開甩尾的同時就照走線按方向（回正只吃真的按著的方向鍵，先全放掉會晚一拍轉不過去）
        this.set('down', false);
        this.set('left', err > 0.04);
        this.set('right', err < -0.04);
        st.drifting = false;
      }
    } else {
      this.set('drift', false);
      this.set('down', false);
      // 空中路線不會變，壓方向只會把車頭轉歪、落地斜著衝出去
      this.set('left', !k.air && err > 0.04);
      this.set('right', !k.air && err < -0.04);
      // 捷徑又窄又彎：放慢一點才不會衝出去
      this.set('up', !(onSc && k.spd > (st.scVmax ?? 99)));
      st.nitroWait -= 1 / 60;
      if (k.nitros > 0 && Math.abs(turnAhead) < 0.2 && st.nitroWait <= 0) {
        st.nitroWait = 1;
        if (this.rng() < sk.nitro) this.set('nitro', true);
      } else this.set('nitro', false);
    }
  }
}
