// 卡丁車物理（街機式）。
//
// 模型：車頭方向 h 由方向鍵／甩尾控制；速度方向 phi 以「抓地力」的速率追車頭。
// 正常行駛抓地強（phi 幾乎等於 h）；甩尾時抓地弱，車頭轉得比速度方向快，就產生側滑角（slip）。
// 側滑角 × 車速 → 集氣；甩尾放開後車身回正，在時機窗內「再按 ↑」＝小噴，
// 回正得越正（側滑角越小）越完美；小噴後再按一次＝雙噴。集滿氣得到一顆氮氣（最多兩顆）。
//
// 座標：three.js，Y 朝上。前方 = (sin h, cos h)，右手邊 = (-cos h, sin h)，右轉 = h 變小。

import { P } from './tuning.js';

const DEG = Math.PI / 180;
const wrap = (a) => {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
};
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

export class Kart {
  constructor(track) {
    this.track = track;
    this.proj = {};
    this.events = [];
    this.place(0, 0);
  }

  /** 放到沿線距離 s、橫向偏移 lateral（右正）的地方，靜止 */
  place(s, lateral) {
    const p = this.track.pointAt(s);
    this.x = p.x + -p.tz * lateral;
    this.z = p.z + p.tx * lateral;
    this.y = p.y;
    this.h = Math.atan2(p.tx, p.tz);
    this.phi = this.h;
    this.spd = 0;
    this.steer = 0;
    this.hint = -1;
    this.drift = false;
    this.driftDir = 0;
    this.driftT = 0;
    this.driftMaxSlip = 0;
    this.driftArm = false;
    this.recoverT = 99;
    this.jetWin = null;
    this.boostT = 0;
    this.boostAdd = 0;
    this.boostKind = '';
    this.nitroT = 0;
    this.gauge = this.gauge ?? 0;
    this.nitros = this.nitros ?? 0;
    this.onGrass = false;
    this.onCurb = false;
    this.pitch = 0;
    this.yawRate = 0;
    const pr = this.track.project(this.x, this.z, -1, this.proj);
    this.hint = pr.i;
    this.lastS = pr.s;
  }

  resetRace(s, lateral) {
    this.gauge = 0;
    this.nitros = 0;
    this.place(s, lateral);
    // 起跑格在線後方：dist 從負的開始，過線才算第 1 圈開始
    const L = this.track.length;
    let back = this.lastS;
    if (back > L / 2) back -= L;
    this.dist = back;
  }

  get slip() { return wrap(this.h - this.phi); }
  get slipDeg() { return Math.abs(this.slip) / DEG; }
  get boosting() { return this.boostT > 0 || this.nitroT > 0; }

  addBoost(add, time, kind) {
    this.boostAdd = Math.max(this.boostT > 0 ? this.boostAdd : 0, add);
    this.boostT = Math.max(this.boostT, time);
    this.boostKind = kind;
    this.spd += add * 0.45;
  }

  /** 回到最近的賽道中心（卡住時用） */
  respawn() {
    const pr = this.track.project(this.x, this.z, this.hint, this.proj);
    const keepDist = this.dist;
    this.place(pr.s, 0);
    this.dist = keepDist;
  }

  step(dt, inp, control) {
    const ev = this.events;
    const steerIn = control ? inp.steer : 0;
    this.steer += (steerIn - this.steer) * Math.min(1, P.steerResponse * dt);
    const thr = control ? inp.throttle : 0;
    const brake = control && inp.braking;

    // ---------------------------------------------------------- 甩尾開始／持續／結束
    if (control && inp.pressed('drift')) this.driftArm = true;
    if (!inp.driftHeld) this.driftArm = false;
    if (!this.drift && this.driftArm && steerIn !== 0 && this.spd > P.driftMinSpeed) {
      this.drift = true;
      this.driftArm = false;
      this.driftDir = Math.sign(steerIn);
      this.driftT = 0;
      this.driftMaxSlip = 0;
      this.h -= this.driftDir * P.driftKick;
      this.jetWin = null;
      ev.push({ type: 'driftStart', dir: this.driftDir });
    }

    let grip;
    const speedAbs = Math.abs(this.spd);
    if (this.drift) {
      const rel = this.steer * this.driftDir; // +1 內切、-1 外拉
      const yaw = this.driftDir * (P.driftYaw + P.driftYawSteer * rel);
      this.h -= yaw * dt;
      this.yawRate = -yaw;
      grip = P.driftGrip;
      this.driftT += dt;
      const s = Math.abs(this.slip);
      this.driftMaxSlip = Math.max(this.driftMaxSlip, s);
      if (this.spd > 0) this.spd -= P.driftDrag * Math.sin(s) * dt;
      const keep = (control && inp.driftHeld) || steerIn * this.driftDir > 0;
      if (!keep) this.endDrift(true, 'release');
      else if (this.spd < P.driftMinSpeed * 0.6) this.endDrift(true, 'slow');
    } else {
      const hi = Math.min(1, speedAbs / P.maxSpeed);
      const low = Math.min(1, speedAbs / 5);
      const rate = P.steerRate * (1 - P.steerHighLoss * hi) * low;
      const yaw = this.steer * rate * (this.spd >= 0 ? 1 : -1);
      this.h -= yaw * dt;
      this.yawRate = -yaw;
      this.recoverT += dt;
      const t = clamp(this.recoverT / P.gripRecover, 0, 1);
      grip = P.driftGrip + (P.grip - P.driftGrip) * t * t;
    }

    // ---------------------------------------------------------- 小噴／雙噴時機
    if (this.jetWin) {
      const w = this.jetWin;
      w.t += dt;
      if (w.stage === 1) {
        if (control && inp.jet) {
          const sd = this.slipDeg;
          const q = sd < P.jetPerfect ? 'perfect' : sd < P.jetGood ? 'good' : 'early';
          const mul = q === 'perfect' ? 1 : q === 'good' ? 0.7 : 0.4;
          this.addBoost(P.jetSpeed * mul, P.jetTime, 'jet');
          ev.push({ type: 'jet', q, slip: sd, t: w.t });
          this.jetWin = { t: 0, stage: 2 };
        } else if (w.t > P.jetWindow) {
          ev.push({ type: 'jetMiss' });
          this.jetWin = null;
        }
      } else if (control && inp.jet) {
        if (w.t >= P.djMin && w.t <= P.djMax) {
          this.addBoost(P.jetSpeed * 0.5 + P.djSpeed, P.jetTime, 'dj');
          ev.push({ type: 'dj', t: w.t });
        } else {
          ev.push({ type: 'djEarly', t: w.t });
        }
        this.jetWin = null;
      } else if (w.t > P.djMax) {
        this.jetWin = null;
      }
    }

    // ---------------------------------------------------------- 氮氣
    if (control && inp.pressed('nitro') && this.nitros > 0 && this.nitroT <= 0) {
      this.nitros--;
      this.nitroT = P.nitroTime;
      this.spd += 3;
      ev.push({ type: 'nitro' });
    }
    if (this.drift && this.nitroT <= 0) {
      const sf = clamp(Math.abs(this.slip) / (30 * DEG), 0.3, 1.3);
      const vf = clamp(this.spd / P.maxSpeed, 0, 1.2);
      this.gauge += dt * P.chargeRate * sf * vf * (this.onGrass ? 0.4 : 1);
      if (this.gauge >= 1) {
        if (this.nitros < 2) {
          this.nitros++;
          this.gauge = 0;
          ev.push({ type: 'nitroReady' });
        } else this.gauge = 1;
      }
    }

    // ---------------------------------------------------------- 速度
    let top = P.maxSpeed;
    if (this.boostT > 0) { top += this.boostAdd; this.boostT -= dt; }
    if (this.nitroT > 0) { top += P.nitroSpeed; this.nitroT -= dt; }
    if (this.onGrass) top *= P.grassTop;
    const boosting = this.boosting;
    if (brake) {
      if (this.spd > 0.5) this.spd -= P.brake * dt;
      else this.spd = Math.max(-P.reverseMax, this.spd - P.accel * 0.6 * dt);
    } else if ((thr || boosting) && this.spd < top) {
      const r = Math.max(0, this.spd) / top;
      const a = boosting ? P.boostAccel : P.accel * Math.max(0.2, 1 - r * r);
      this.spd = Math.min(top, this.spd + a * dt);
    } else if (!thr && !boosting && !this.drift) {
      // 甩尾時鬆 ↑ 是基本動作（為了等一下小噴），不額外掉速，只算甩尾本身的損失
      this.spd -= Math.sign(this.spd) * Math.min(Math.abs(this.spd), P.coastDrag * dt);
    }
    if (this.spd > top) this.spd = Math.max(top, this.spd - ((this.spd - top) * 1.5 + 2) * dt);
    if (this.onGrass) this.spd -= Math.sign(this.spd) * Math.min(Math.abs(this.spd), P.grassDrag * 0.25 * dt);

    // 速度方向追車頭
    if (this.spd >= 0) this.phi += wrap(this.h - this.phi) * (1 - Math.exp(-grip * dt));
    else this.phi = this.h;
    this.h = wrap(this.h);
    this.phi = wrap(this.phi);

    // ---------------------------------------------------------- 移動與碰撞
    this.x += Math.sin(this.phi) * this.spd * dt;
    this.z += Math.cos(this.phi) * this.spd * dt;
    const tr = this.track;
    let pr = tr.project(this.x, this.z, this.hint, this.proj);
    this.hint = pr.i;
    const limit = tr.wall - tr.wallT / 2 - 0.85;
    if (Math.abs(pr.d) > limit) {
      const sg = Math.sign(pr.d);
      const rx = -pr.tz, rz = pr.tx;
      const over = Math.abs(pr.d) - limit;
      this.x -= rx * sg * over;
      this.z -= rz * sg * over;
      let vx = Math.sin(this.phi) * this.spd, vz = Math.cos(this.phi) * this.spd;
      const vn = (vx * rx + vz * rz) * sg;
      if (vn > 0) {
        vx -= rx * sg * vn * (1 + P.wallBounce);
        vz -= rz * sg * vn * (1 + P.wallBounce);
        const impact = clamp(vn / Math.max(1, Math.abs(this.spd)), 0, 1);
        const ns = Math.hypot(vx, vz) * (1 - P.wallLoss * impact);
        if (this.spd >= 0) { this.phi = Math.atan2(vx, vz); this.spd = ns; }
        else { this.phi = Math.atan2(-vx, -vz); this.spd = -ns; }
        this.h += wrap(this.phi - this.h) * Math.min(1, impact * 1.5) * 0.5;
        if (this.drift && impact > 0.25) this.endDrift(false, 'wall');
        if (vn > 1.5) ev.push({ type: 'wall', impact: vn });
      }
      pr = tr.project(this.x, this.z, this.hint, this.proj);
    }
    const ad = Math.abs(pr.d);
    this.onGrass = ad > tr.halfWidth + tr.curb * 0.7;
    this.onCurb = !this.onGrass && ad > tr.halfWidth;
    this.y = pr.y;
    const gradeF = pr.grade * (Math.sin(this.h) * pr.tx + Math.cos(this.h) * pr.tz);
    this.pitch = -Math.atan(gradeF);

    // 圈數：沿線累積距離（倒車會扣回去）
    const L = tr.length;
    let ds = pr.s - this.lastS;
    if (ds < -L / 2) ds += L;
    else if (ds > L / 2) ds -= L;
    this.dist += ds;
    this.lastS = pr.s;
  }

  endDrift(allowJet, reason) {
    if (!this.drift) return;
    this.drift = false;
    this.recoverT = 0;
    const can = allowJet && this.driftT >= P.jetMinDrift && this.driftMaxSlip > 8 * DEG;
    this.jetWin = can ? { t: 0, stage: 1 } : null;
    this.events.push({ type: 'driftEnd', canJet: can, reason });
  }
}
