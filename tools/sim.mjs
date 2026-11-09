// 無頭模擬：用自動駕駛跑賽道，檢查操控參數合不合理（圈速、撞牆、甩尾／小噴次數）。
// 用法：node tools/sim.mjs [圈數=2] [drift|grip|both]
// 參數覆寫：node tools/sim.mjs 2 both driftYaw=1.1 driftGrip=2
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { Track } from '../js/track.js';
import { Kart } from '../js/kart.js';
import { P } from '../js/tuning.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const track = new Track(JSON.parse(readFileSync(join(root, 'assets', 'track1_path.json'), 'utf8')));
const args = process.argv.slice(2);
const laps = parseInt(args[0] || '2', 10);
const modes = (args[1] || 'both') === 'both' ? ['grip', 'drift'] : [args[1]];
for (const a of args.slice(2)) { const [k, v] = a.split('='); if (k in P) P[k] = parseFloat(v); }

const wrap = (a) => { while (a > Math.PI) a -= 2 * Math.PI; while (a < -Math.PI) a += 2 * Math.PI; return a; };
const headAt = (s) => { const p = track.pointAt(s); return Math.atan2(p.tx, p.tz); };

function run(useDrift) {
  const k = new Kart(track);
  k.resetRace(track.length - 8, 0);
  const keys = new Set(), edges = new Set();
  const inp = {
    get steer() { return (keys.has('right') ? 1 : 0) - (keys.has('left') ? 1 : 0); },
    get throttle() { return keys.has('up') ? 1 : 0; },
    get braking() { return false; },
    get driftHeld() { return keys.has('drift'); },
    get jet() { return edges.has('up'); },
    pressed: (a) => edges.has(a),
  };
  const set = (a, v) => { if (v && !keys.has(a)) edges.add(a); if (v) keys.add(a); else keys.delete(a); };
  const st = { drifting: false, dir: 0, wantJet: false };
  const dt = 1 / 120;
  let t = 0, lapStart = 0, lapsDone = 0, grass = 0, n = 0;
  const lapTimes = [], cnt = {};
  const jetSlips = [];
  while (lapsDone < laps && t < 600) {
    // ---- 自動駕駛（每 1/60 秒決策一次）
    if (n % 2 === 0) {
      const s = k.lastS, v = Math.max(5, k.spd);
      const p = track.pointAt(s + 8 + v * 0.45);
      const err = wrap(Math.atan2(p.x - k.x, p.z - k.z) - k.h);
      const turnAhead = wrap(headAt(s + 40) - headAt(s + 8));
      if (useDrift && !k.drift && !st.drifting && Math.abs(turnAhead) > 0.75 && k.spd > 18) {
        st.drifting = true;
        st.dir = turnAhead < 0 ? 1 : -1;
        st.t0 = t;
        set('up', false);
        set('drift', true);
      }
      if (st.drifting && !k.drift && t - st.t0 > 0.3) { st.drifting = false; set('drift', false); }
      if (st.drifting) {
        const sk = st.dir > 0 ? 'right' : 'left', ot = st.dir > 0 ? 'left' : 'right';
        set(ot, false);
        set(sk, -err * st.dir > -0.05 || !k.drift);
        const remain = wrap(headAt(s + 25) - k.phi);
        if (k.drift && Math.abs(turnAhead) < 0.35 && Math.abs(remain) < 0.25) {
          set('drift', false); set(sk, false); st.drifting = false; st.wantJet = true;
        }
      } else {
        set('drift', false);
        set('left', err > 0.04);
        set('right', err < -0.04);
        if (st.wantJet && k.jetWin) {
          if (k.jetWin.stage === 1) { if (k.slipDeg < P.jetPerfect * 0.8) set('up', true); }
          else if (k.jetWin.t > (P.djMin + P.djMax) / 2) { if (keys.has('up')) set('up', false); else { set('up', true); st.wantJet = false; } }
          else set('up', false);
        } else { st.wantJet = false; set('up', true); }
        if (k.nitros > 0 && Math.abs(turnAhead) < 0.2) set('nitro', true); else set('nitro', false);
      }
    }
    k.step(dt, inp, true);
    edges.clear();
    for (const e of k.events) {
      const key = e.type + (e.q ? ':' + e.q : '') + (e.reason ? ':' + e.reason : '');
      cnt[key] = (cnt[key] || 0) + 1;
      if (e.type === 'jet') jetSlips.push(e.slip);
    }
    k.events.length = 0;
    if (k.onGrass) grass++;
    t += dt;
    n++;
    const ld = Math.floor(k.dist / track.length);
    if (ld > lapsDone) { lapsDone = ld; lapTimes.push(+(t - lapStart).toFixed(2)); lapStart = t; }
  }
  return { mode: useDrift ? 'drift' : 'grip', lapTimes, grassPct: +(grass / n * 100).toFixed(1), events: cnt };
}

for (const m of modes) console.log(JSON.stringify(run(m === 'drift')));
