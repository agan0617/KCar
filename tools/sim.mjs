// 無頭模擬：用自動駕駛跑賽道，檢查操控參數與電腦強度合不合理。
//
//   node tools/sim.mjs tt [賽道…]           計時賽：完美自動駕駛（每彎甩、完美小噴＋雙噴）與不甩尾的圈速
//   node tools/sim.mjs race [賽道…] [N=5]   競賽：玩家自動駕駛分「完美」與「普通玩家」兩種，各跑 N 場，看名次分布與時間差
//   參數覆寫：在最後加 driftYaw=1.1 driftGrip=2 這種
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { Track } from '../js/track.js';
import { Race } from '../js/race.js';
import { P } from '../js/tuning.js';
import { TRACKS } from '../js/tracks.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const cmd = args[0] || 'tt';
const ids = args.slice(1).filter((a) => TRACKS.some((t) => t.id === a));
const nArg = args.slice(1).find((a) => /^\d+$/.test(a));
for (const a of args) { const [k, v] = a.split('='); if (v !== undefined && k in P) P[k] = parseFloat(v); }
const list = ids.length ? TRACKS.filter((t) => ids.includes(t.id)) : TRACKS;

function rng(seed) {
  let s = seed >>> 0 || 1;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

const GOOD_PLAYER = { speed: 1, drift: 0.9, perfect: 0.45, dj: 0.4, nitro: 0.9, line: 0.85, lane: 0 };
const NO_DRIFT = { drift: 0, perfect: 0, dj: 0 };

function run(meta, mode, playerSkill, seed) {
  const track = new Track(JSON.parse(readFileSync(join(root, 'assets', meta.id + '_path.json'), 'utf8')));
  const race = new Race(track, { mode, laps: meta.laps, difficulty: meta.difficulty, rng: rng(seed), playerSkill });
  const dt = 1 / 120;
  let t = 0, walls = 0;
  // 倒數 3 秒
  while (t < 3) { race.step(dt, null, false); t += dt; }
  while (race.player.finishT == null && race.clock < 900) {
    race.step(dt, null, true);
    for (const e of race.player.kart.events) if (e.type === 'wall') walls++;
    race.player.kart.events.length = 0;
  }
  return { race, walls };
}

if (cmd === 'tt') {
  for (const meta of list) {
    const a = run(meta, 'time', {}, 1);
    const b = run(meta, 'time', NO_DRIFT, 1);
    const f = (r) => r.race.player.laps.map((x) => x.toFixed(1)).join(' / ');
    console.log(`${meta.id.padEnd(8)} ★${meta.difficulty}  甩尾＋完美小噴 ${f(a)}（撞牆 ${a.walls}）   不甩尾 ${f(b)}（撞牆 ${b.walls}）`);
  }
} else {
  const N = parseInt(nArg || '5', 10);
  for (const meta of list) {
    for (const [label, sk] of [['完美', {}], ['普通', GOOD_PLAYER]]) {
      const places = [0, 0, 0, 0];
      const gaps = [];
      for (let i = 0; i < N; i++) {
        const { race } = run(meta, 'race', sk, 100 + i);
        const order = race.racers.map((r) => ({ name: r.name, t: race.estimateFinish(r) })).sort((x, y) => x.t - y.t);
        const pi = order.findIndex((o) => o.name === race.player.name);
        places[pi]++;
        const best = order.find((o) => o.name !== race.player.name);
        gaps.push(race.player.finishT - best.t);
      }
      const avg = gaps.reduce((s, g) => s + g, 0) / N;
      console.log(`${meta.id.padEnd(8)} ★${meta.difficulty} 玩家=${label}  名次分布 1:${places[0]} 2:${places[1]} 3:${places[2]} 4:${places[3]}  與最強電腦差 ${avg >= 0 ? '+' : ''}${avg.toFixed(1)}s`);
    }
  }
}
