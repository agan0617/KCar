// 卡丁車物理（街機式）。
//
// 模型（1.0 起）：車頭方向 h 有轉動慣性（角速度 w 追方向鍵要的轉速），速度方向 phi 以「抓地力」的速率追車頭。
// 正常行駛抓地力高，phi 幾乎等於 h；甩尾時抓地力降低，車頭先轉、路線慢半拍跟上，側滑角（slip）是自然甩出來的：
// 往彎內壓＝車頭轉得急、偏角變大、路線跟著收緊；往外拉＝車頭轉得緩、偏角變小、走大圈。
// 按甩尾鍵先小跳一下（hop）；有上下速度 vy、重力、離地（air）與落地；上下坡會影響車速。
// 側滑角 × 車速 → 集氣；甩尾放開後車頭轉回路線方向（回正，反打方向更快），在時機窗內「再按 ↑」＝小噴，
// 回正得越正（側滑角越小）越完美；小噴後再按一次＝雙噴。集滿氣得到一顆氮氣（最多兩顆）。
//
// 座標：three.js，Y 朝上。前方 = (sin h, cos h)，右手邊 = (-cos h, sin h)，右轉 = h 變小。

import { P } from './tuning.js';
import { SURF } from './collision.js';

const DEG = Math.PI / 180;
const KART_R = 0.85; // 車子碰撞半徑
const wrap = (a) => {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
};
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

// 多人連線：一台車的完整物理狀態（快照下傳、client 回滾重放都靠它）。
// 加了會影響 step() 的欄位，一定要補進這裡，不然連線時預測會一直被校正。
const STATE_KEYS = ['x', 'y', 'z', 'h', 'phi', 'spd', 'steer', 'hint', 'drift', 'driftDir', 'driftT', 'driftMaxSlip',
  'driftArm', 'recoverT', 'straighten', 'boostT', 'boostAdd', 'boostKind', 'nitroT', 'gauge', 'nitros', 'onGrass', 'onCurb',
  'pitch', 'yawRate', 'lastS', 'dist', 'topMul', 'sbUsed', 'sbPend', 'w', 'vy', 'air', 'surf', 'roll'];

export class Kart {
  constructor(track) {
    this.track = track;
    this.proj = {};
    this.events = [];
    this.topMul = 1; // 極速倍率（電腦車手的強弱、追趕機制用；玩家固定 1）
    this.sbUsed = false; // 起步噴：這場按過了（連線版由 net/shared.js 判，單機版由 main.js 判）
    this.sbPend = false; // 起步噴：倒數最後 0.25 秒按了，GO 時生效
    this.dist = 0;
    this.place(0, 0);
  }

  getState() {
    const s = STATE_KEYS.map((k) => this[k]);
    s.push(this.jetWin ? [this.jetWin.t, this.jetWin.stage] : 0);
    return s;
  }

  setState(s) {
    for (let i = 0; i < STATE_KEYS.length; i++) this[STATE_KEYS[i]] = s[i];
    const w = s[STATE_KEYS.length];
    this.jetWin = w ? { t: w[0], stage: w[1] } : null;
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
    this.straighten = false;
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
    this.w = 0; // 車頭角速度（rad/s，左轉為正）
    this.vy = 0; // 上下速度
    this.air = false; // 離地中
    this.surf = 0; // 腳下的地面種類（collision.js 的 SURF）
    this.roll = 0; // 路面側傾（右側高為正）
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
    const tr = this.track;
    const L = tr.length;
    // 回到最後通過的沿線位置；在跳台缺口裡就往前移到缺口後的路面（不然會再掉下去）
    let i = Math.floor((((this.lastS % L) + L) % L) / tr.step) % tr.n;
    let skip = 0;
    while (tr.gap[i] && skip < tr.n) { i = (i + 1) % tr.n; skip++; }
    if (skip) i = (i + 4) % tr.n;
    const s0 = this.lastS;
    const keepDist = this.dist;
    this.place(i * tr.step, 0);
    let ds = this.lastS - s0;
    if (ds < -L / 2) ds += L;
    else if (ds > L / 2) ds -= L;
    this.dist = keepDist + Math.max(0, ds);
    this.events.push({ type: 'respawn' });
  }

  step(dt, inp, control) {
    const ev = this.events;
    const steerIn = control ? inp.steer : 0;
    this.steer += (steerIn - this.steer) * Math.min(1, P.steerResponse * dt);
    const thr = control ? inp.throttle : 0;
    const brake = control && inp.braking;

    // ---------------------------------------------------------- 小跳＋甩尾開始／持續／結束
    if (control && inp.pressed('drift')) {
      this.driftArm = true;
      if (!this.air && this.spd > 4 && P.hopSpeed > 0) {
        this.vy = P.hopSpeed;
        this.air = true;
        ev.push({ type: 'hop' });
      }
    }
    if (!inp.driftHeld) this.driftArm = false;
    if (!this.drift && this.driftArm && steerIn !== 0 && this.spd > P.driftMinSpeed) {
      this.drift = true;
      this.driftArm = false;
      this.driftDir = Math.sign(steerIn);
      this.driftT = 0;
      this.driftMaxSlip = 0;
      this.straighten = false;
      this.w -= this.driftDir * P.driftKick * P.yawResp; // 起甩：車頭被甩進彎一下
      this.jetWin = null;
      ev.push({ type: 'driftStart', dir: this.driftDir });
    }

    // ---------------------------------------------------------- 車頭轉動（有慣性）
    const speedAbs = Math.abs(this.spd);
    const h0 = this.h;
    const ctl = this.air ? P.airControl : 1;
    let wT, pathTurn = 0;
    if (this.drift) {
      const rel = this.steer * this.driftDir; // +1 內切、-1 外拉
      // 點煞：甩尾中按煞車，車頭往彎內多甩（剛按下那一下先甩一截），代價是掉速（在下面速度段算）
      const pb = brake ? P.brakeYaw : 0;
      if (control && inp.pressed('down')) {
        this.w -= this.driftDir * P.brakeKick * P.yawResp;
        ev.push({ type: 'pointBrake' });
      }
      wT = -this.driftDir * Math.max(0, P.driftTurn + P.driftTurnSteer * rel + pb);
      this.driftT += dt;
    } else {
      const hi = Math.min(1, speedAbs / P.maxSpeed);
      const low = Math.min(1, speedAbs / 5);
      const rate = P.steerRate * (1 - P.steerHighLoss * hi) * low;
      const yaw = -this.steer * rate * (this.spd >= 0 ? 1 : -1);
      this.recoverT += dt;
      if (this.straighten && this.spd >= 0) {
        // 回正中：方向鍵轉的是路線，車頭往路線方向收；反打方向（往甩尾的反方向）收得更快
        const counter = steerIn * this.driftDir < 0 ? P.counterSteer : 1;
        pathTurn = yaw;
        wT = yaw - wrap(this.h - this.phi) * P.driftRecover * counter;
      } else {
        this.straighten = false;
        wT = yaw;
      }
    }
    this.w += (wT - this.w) * (1 - Math.exp(-P.yawResp * ctl * dt));
    this.h += this.w * dt;

    // ---------------------------------------------------------- 路線（速度方向）追車頭
    if (this.spd < 0) this.phi = this.h;
    else if (this.air) {
      // 空中沒有抓地力，路線不變
    } else if (this.drift) {
      this.phi += wrap(this.h - this.phi) * (1 - Math.exp(-P.driftGrip * dt));
      const max = P.driftSlipMax * DEG;
      const sl = wrap(this.h - this.phi);
      if (Math.abs(sl) > max) this.phi = this.h - Math.sign(sl) * max;
    } else if (this.straighten) {
      this.phi += pathTurn * dt;
      if (Math.abs(wrap(this.h - this.phi)) < 0.5 * DEG) this.straighten = false;
    } else {
      this.phi += wrap(this.h - this.phi) * (1 - Math.exp(-P.grip * dt));
    }

    if (this.drift) {
      const s = Math.abs(this.slip);
      this.driftMaxSlip = Math.max(this.driftMaxSlip, s);
      if (this.spd > 0 && !this.air) this.spd -= P.driftDrag * Math.sin(s) * dt;
      const keep = (control && inp.driftHeld) || steerIn * this.driftDir > 0;
      if (!keep) this.endDrift(true, 'release');
      else if (this.spd < P.driftMinSpeed * 0.6) this.endDrift(true, 'slow');
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
    let top = P.maxSpeed * this.topMul;
    if (this.boostT > 0) { top += this.boostAdd; this.boostT -= dt; }
    if (this.nitroT > 0) { top += P.nitroSpeed; this.nitroT -= dt; }
    if (this.onGrass) top *= P.grassTop * (this.surf === SURF.SAND ? 0.85 : 1);
    else if (this.surf === SURF.DIRT) top *= P.dirtTop;
    const boosting = this.boosting;
    if (this.air) {
      // 空中：引擎推不到地，只有一點空氣阻力
      if (this.spd > top) this.spd -= Math.min(this.spd - top, 2 * dt);
    } else {
      if (brake && this.drift) {
        this.spd -= P.brakeDrag * dt; // 點煞：比一般煞車輕，主要拿來甩車頭
      } else if (brake) {
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
      // 上坡掉速、下坡加速（pitch 是上一步算的車頭俯仰，上坡為負）
      if (Math.abs(this.spd) > 1) this.spd += P.slopeGrav * Math.tan(this.pitch) * dt;
    }

    this.yawRate = dt > 0 ? wrap(this.h - h0) / dt : 0;
    this.h = wrap(this.h);
    this.phi = wrap(this.phi);

    // ---------------------------------------------------------- 移動與碰撞
    this.x += Math.sin(this.phi) * this.spd * dt;
    this.z += Math.cos(this.phi) * this.spd * dt;
    const tr = this.track;
    let pr = tr.project(this.x, this.z, this.hint, this.proj, this.y);
    this.hint = pr.i;
    let gy;
    const g0 = this.gnd || (this.gnd = { y: 0, nx: 0, ny: 1, nz: 0, surf: 0 });
    let g = null;
    if (tr.col) {
      // v2：護牆是線段、地面是三角形（橋上橋下分得開）
      tr.col.eachWallHit(this.x, this.z, this.y + 0.3, KART_R, this.wallFn || (this.wallFn = (nx, nz, depth) => this.wallHit(nx, nz, depth)));
      g = tr.col.ground(this.x, this.z, this.y + (this.air ? 0.4 : 1.0) + Math.max(0, this.vy * dt), g0);
      this.surf = g ? g.surf : -1;
      gy = g ? g.y : -Infinity;
      this.onGrass = this.surf === SURF.GRASS || this.surf === SURF.SAND;
      this.onCurb = this.surf === SURF.CURB;
      pr = tr.project(this.x, this.z, this.hint, this.proj, this.y);
    } else {
      const limit = tr.wall - tr.wallT / 2 - KART_R;
      if (Math.abs(pr.d) > limit) {
        const sg = Math.sign(pr.d);
        this.wallHit(pr.tz * sg, -pr.tx * sg, Math.abs(pr.d) - limit);
        pr = tr.project(this.x, this.z, this.hint, this.proj, this.y);
      }
      const ad = Math.abs(pr.d);
      this.onGrass = ad > tr.halfWidth + tr.curb * 0.7;
      this.onCurb = !this.onGrass && ad > tr.halfWidth;
      this.surf = this.onGrass ? SURF.GRASS : this.onCurb ? SURF.CURB : SURF.ROAD;
      gy = pr.y;
    }

    // ---------------------------------------------------------- 上下：重力、離地、落地
    if (this.air) {
      this.vy -= P.gravity * dt;
      this.y += this.vy * dt;
      if (this.y <= gy) {
        const imp = Math.max(0, -this.vy); // 落地時往下的速度
        this.y = gy;
        this.vy = -imp; // 保留往下的速度：落在下坡時才不會下一步又被判成離地（一路彈跳）
        this.air = false;
        ev.push({ type: 'land', impact: imp });
        if (imp > 8 && this.spd > 0) this.spd *= 1 - Math.min(0.12, (imp - 8) * 0.015);
      }
    } else {
      const need = (gy - this.y) / dt; // 貼地需要的上下速度
      if (need < this.vy - P.gravity * dt - P.liftSpeed) {
        // 地面掉得比重力還快（坡頂、跳台邊緣、路面缺口）：飛出去
        this.air = true;
        this.vy -= P.gravity * dt;
        this.y += this.vy * dt;
        if (this.y < gy) { this.y = gy; this.air = false; this.vy = need; }
      } else {
        this.y = gy;
        this.vy = need; // 貼地時上下速度就是地面的（只有地面突然往下掉得比重力快才會飛起來）
      }
    }
    if (g) {
      // 地面法向量 → 沿車頭方向的坡度（俯仰）與左右的側傾
      const fx = Math.sin(this.h), fz = Math.cos(this.h);
      if (!this.air) {
        this.pitch = -Math.atan(-(g.nx * fx + g.nz * fz) / g.ny);
        this.roll = Math.atan(-(g.nx * -fz + g.nz * fx) / g.ny);
      }
    } else if (!tr.col) {
      const gradeF = pr.grade * (Math.sin(this.h) * pr.tx + Math.cos(this.h) * pr.tz);
      this.pitch = -Math.atan(gradeF);
      this.roll = 0;
    }

    // 加速帶
    if (this.surf === SURF.BOOST && !this.air && !(this.boostKind === 'pad' && this.boostT > P.padTime * 0.6)) {
      this.addBoost(P.padSpeed, P.padTime, 'pad');
      ev.push({ type: 'pad' });
    }
    // 掉出賽道、掉進熔岩／水：重生
    if (tr.col && (this.y < tr.col.killY || (this.surf === SURF.HAZARD && !this.air))) {
      ev.push({ type: 'fall', hazard: this.surf === SURF.HAZARD });
      this.respawn();
      return;
    }

    // 圈數：沿線累積距離（倒車會扣回去）
    const L = tr.length;
    let ds = pr.s - this.lastS;
    if (ds < -L / 2) ds += L;
    else if (ds > L / 2) ds -= L;
    this.dist += ds;
    this.lastS = pr.s;
  }

  /** 撞牆：法向量 (nx, nz) 從牆指向車，depth 是穿進去多深 */
  wallHit(nx, nz, depth) {
    this.x += nx * depth;
    this.z += nz * depth;
    let vx = Math.sin(this.phi) * this.spd, vz = Math.cos(this.phi) * this.spd;
    const vn = -(vx * nx + vz * nz); // 往牆裡衝的速度
    if (vn <= 0) return;
    vx += nx * vn * (1 + P.wallBounce);
    vz += nz * vn * (1 + P.wallBounce);
    const impact = clamp(vn / Math.max(1, Math.abs(this.spd)), 0, 1);
    const ns = Math.hypot(vx, vz) * (1 - P.wallLoss * impact);
    if (this.spd >= 0) { this.phi = Math.atan2(vx, vz); this.spd = ns; }
    else { this.phi = Math.atan2(-vx, -vz); this.spd = -ns; }
    this.h += wrap(this.phi - this.h) * Math.min(1, impact * 1.5) * 0.5;
    // 撞牆的反作用：車頭被彈離牆面（牆在右邊 → 往左轉）
    const side = nx * -Math.cos(this.h) + nz * Math.sin(this.h); // 法向量在車右手方向的分量：牆在右邊時為負
    this.w = this.w * (1 - Math.min(1, impact * 1.5)) - Math.sign(side) * impact * P.wallSpin;
    if (this.drift && impact > 0.25) this.endDrift(false, 'wall');
    if (vn > 1.5) this.events.push({ type: 'wall', impact: vn });
  }

  endDrift(allowJet, reason) {
    if (!this.drift) return;
    this.drift = false;
    this.recoverT = 0;
    this.straighten = true;
    const can = allowJet && this.driftT >= P.jetMinDrift && this.driftMaxSlip > 8 * DEG;
    this.jetWin = can ? { t: 0, stage: 1 } : null;
    this.events.push({ type: 'driftEnd', canJet: can, reason });
  }
}
