// 無頭模擬：用自動駕駛跑賽道，檢查操控參數與電腦強度合不合理。
//
//   node tools/sim.mjs tt [賽道…]           計時賽：自動駕駛「每彎甩、顧甜蜜區間」「每彎甩、不顧」「不甩尾」三種的圈速與小噴段數
//   node tools/sim.mjs race [賽道…] [N=5]   競賽：玩家自動駕駛分「完美」與「普通玩家」兩種，各跑 N 場，看名次分布與時間差
//   參數覆寫：在最後加 driftTurn=0.9 driftSlip=20 這種；sc=0／sc=1 指定自動駕駛不走／一定走捷徑
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { Track } from '../js/track.js';
import { readTrackData } from '../server/load_track.mjs';
import { Race } from '../js/race.js';
import { P } from '../js/tuning.js';
import { TRACKS, aiLevel } from '../js/tracks.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const cmd = args[0] || 'tt';
const ids = args.slice(1).filter((a) => TRACKS.some((t) => t.id === a));
const nArg = args.slice(1).find((a) => /^\d+$/.test(a));
for (const a of args) { const [k, v] = a.split('='); if (v !== undefined && k in P) P[k] = parseFloat(v); }
const list = ids.length ? TRACKS.filter((t) => ids.includes(t.id)) : TRACKS;
const scArg = args.find((a) => /^sc=[01]$/.test(a)); // sc=0 不走捷徑、sc=1 一定走（自動駕駛）
const SC = scArg ? { shortcut: +scArg.slice(3) } : {};

function rng(seed) {
  let s = seed >>> 0 || 1;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

const GOOD_PLAYER = { speed: 1, drift: 0.9, angle: 0.45, nitro: 0.9, line: 0.85, lane: 0 };
const NO_DRIFT = { drift: 0 };
const NO_ANGLE = { angle: 0 }; // 每彎都甩，但不顧甜蜜區間（照走線需要外拉、點煞）

function run(meta, mode, playerSkill, seed) {
  const track = new Track(readTrackData(root, meta.id));
  const race = new Race(track, { mode, laps: meta.laps, difficulty: aiLevel(meta), rng: rng(seed), playerSkill });
  const dt = 1 / 120;
  let t = 0, walls = 0;
  const tiers = [0, 0, 0, 0];
  // 倒數 3 秒
  while (t < 3) { race.step(dt, null, false); t += dt; }
  while (race.player.finishT == null && race.clock < 900) {
    race.step(dt, null, true);
    for (const e of race.player.kart.events) {
      if (e.type === 'wall') walls++;
      else if (e.type === 'driftEnd') tiers[e.tier]++;
    }
    race.player.kart.events.length = 0;
  }
  return { race, walls, tiers };
}

if (cmd === 'tt') {
  for (const meta of list) {
    const a = run(meta, 'time', { ...SC }, 1);
    const c = run(meta, 'time', { ...NO_ANGLE, ...SC }, 1);
    const b = run(meta, 'time', { ...NO_DRIFT, ...SC }, 1);
    const f = (r) => r.race.player.laps.map((x) => x.toFixed(1)).join(' / ');
    const tz = (r) => `段數 0:${r.tiers[0]} 1:${r.tiers[1]} 2:${r.tiers[2]} 3:${r.tiers[3]}`;
    console.log(`${meta.id.padEnd(8)} ★${meta.difficulty}  顧甜蜜區 ${f(a)}（撞牆 ${a.walls}，${tz(a)}）`);
    console.log(`${''.padEnd(12)}不顧甜蜜區 ${f(c)}（撞牆 ${c.walls}，${tz(c)}）   不甩尾 ${f(b)}（撞牆 ${b.walls}）`);
  }
} else if (cmd === 'timing') {
  // 進彎時機：起甩點提早／照常／延後（entry，公尺），看總時間與小噴段數
  const sum = (r) => r.race.player.laps.reduce((s, x) => s + x, 0);
  for (const meta of list) {
    const row = [];
    for (const [label, entry] of [['早 15m', 15], ['早 8m', 8], ['準', 0], ['晚 6m', -6], ['晚 12m', -12]]) {
      const r = run(meta, 'time', { entry, ...SC }, 1);
      row.push(`${label} ${sum(r).toFixed(1)}s［${r.tiers.join('/')}］撞${r.walls}`);
    }
    console.log(`${meta.id.padEnd(8)} ${row.join('  ')}`);
  }
  console.log('［a/b/c/d］＝小噴段數 0／1／2／3 各幾次');
} else if (cmd === 'zigzag') {
  // 直線蛇行：在一條沒有牆的無限長直線上，比「一直全油門」和「左右連續短甩」誰在 20 秒內跑得遠
  const straight = {
    length: 1e9, wall: 1e6, wallT: 1, halfWidth: 1e5, curb: 1, gap: [], n: 1, step: 1,
    pointAt: (s) => ({ x: 0, y: 0, z: s, tx: 0, tz: 1 }),
    project: (x, z, hint, out) => Object.assign(out || {}, { s: z, d: x, i: 0, y: 0, grade: 0, tx: 0, tz: 1, hw: 1e5 }),
  };
  const { Kart } = await import('../js/kart.js');
  const go = (half) => {
    const k = new Kart(straight);
    k.resetRace(0, 0);
    k.spd = 38;
    const keys = new Set(), edges = new Set();
    const inp = {
      get steer() { return (keys.has('right') ? 1 : 0) - (keys.has('left') ? 1 : 0); },
      get throttle() { return 1; },
      get braking() { return false; },
      get driftHeld() { return keys.has('drift'); },
      get jet() { return false; },
      pressed: (a) => edges.has(a),
    };
    const dt = 1 / 120;
    let t = 0, phase = 0, dir = 1, next = half ? half / 2 : Infinity, maxLat = 0;
    const tiers = [0, 0, 0, 0];
    while (t < 20) {
      edges.clear();
      if (t >= next) {
        // 換邊：放開甩尾一步，再往另一邊起甩
        phase++;
        dir = -dir;
        next += half;
        keys.delete('drift');
      } else if (half && !keys.has('drift')) {
        keys.add('drift'); edges.add('drift');
        keys.delete('left'); keys.delete('right');
        keys.add(dir > 0 ? 'right' : 'left');
      } else if (k.drift) { keys.delete('left'); keys.delete('right'); } // 起甩後放開方向＝不按（甩尾維持）
      k.step(dt, inp, true);
      for (const e of k.events) if (e.type === 'driftEnd') tiers[e.tier]++;
      k.events.length = 0;
      maxLat = Math.max(maxLat, Math.abs(k.x));
      t += dt;
    }
    return { d: k.z, maxLat, tiers };
  };
  const base = go(0);
  console.log(`一直全油門：20 秒 ${base.d.toFixed(1)} m`);
  for (const half of [0.6, 0.8, 1.0, 1.2, 1.5, 2.0]) {
    const r = go(half);
    console.log(`每 ${half}s 換邊甩：${r.d.toFixed(1)} m（${r.d >= base.d ? '比全油門遠' : '比全油門近'} ${(r.d - base.d).toFixed(1)} m，最大橫向偏移 ${r.maxLat.toFixed(1)} m，段數［${r.tiers.join('/')}］）`);
  }
} else {
  const N = parseInt(nArg || '5', 10);
  for (const meta of list) {
    for (const [label, sk] of [['完美', {}], ['普通', GOOD_PLAYER]]) {
      const places = [0, 0, 0, 0];
      const gaps = [];
      let stuck = 0;
      for (let i = 0; i < N; i++) {
        const { race } = run(meta, 'race', sk, 100 + i);
        for (const r of race.racers) if (r.driver) stuck += r.driver.stuckN || 0;
        const order = race.racers.map((r) => ({ name: r.name, t: race.estimateFinish(r) })).sort((x, y) => x.t - y.t);
        const pi = order.findIndex((o) => o.name === race.player.name);
        places[pi]++;
        const best = order.find((o) => o.name !== race.player.name);
        gaps.push(race.player.finishT - best.t);
      }
      const avg = gaps.reduce((s, g) => s + g, 0) / N;
      console.log(`${meta.id.padEnd(8)} ★${meta.difficulty} 玩家=${label}  名次分布 1:${places[0]} 2:${places[1]} 3:${places[2]} 4:${places[3]}  與最強電腦差 ${avg >= 0 ? '+' : ''}${avg.toFixed(1)}s  卡住重生共 ${stuck} 次`);
    }
  }
}
