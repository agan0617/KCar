// 找問題點：完美自動駕駛（計時賽）跑一場，列出撞牆、掉落、卡住重生、落地重摔發生在沿線哪裡，
// 並對照 layout 的控制點索引（at）與設計腳本的 tag（有 tools/tracks/<id>.py 產生的話，從 layout 點的位置反查不到 tag，只給 at）。
//   node tools/sim_walls.mjs <賽道> [race] [sc=0|1] [angle=0.45 …技能覆寫]（race：跟 3 台電腦一起跑，看被擠、卡住）
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readFileSync } from 'node:fs';
import { Track } from '../js/track.js';
import { readTrackData } from '../server/load_track.mjs';
import { Race } from '../js/race.js';
import { TRACKS, aiLevel } from '../js/tracks.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const id = process.argv[2];
const meta = TRACKS.find((t) => t.id === id);
if (!meta) { console.log('用法：node tools/sim_walls.mjs <賽道 id>'); process.exit(1); }
const skill = {};
let MODE = 'time';
for (const a of process.argv.slice(3)) {
  if (a === 'race') { MODE = 'race'; continue; }
  const [k, v] = a.split('=');
  if (k === 'sc') skill.shortcut = +v; else if (v !== undefined) skill[k] = parseFloat(v);
}
const data = readTrackData(root, id);
const track = new Track(data);
// layout 控制點 → 沿線距離（近似：投影每個控制點）
const lay = JSON.parse(readFileSync(join(root, 'tools', 'blender', `${id}_layout.json`), 'utf8'));
const cpS = lay.points.map((p) => {
  const pr = track.project(p.p[0], p.p[1], undefined, {});
  return pr ? pr.s : NaN;
});
const atOf = (s) => {
  let best = 0;
  for (let i = 0; i < cpS.length; i++) if (cpS[i] <= s && cpS[i] >= cpS[best]) best = i;
  const nx = (best + 1) % cpS.length;
  const span = ((cpS[nx] - cpS[best]) + track.length) % track.length || 1;
  return (best + Math.min(0.99, (s - cpS[best]) / span)).toFixed(2);
};
let seed = 1;
const rng = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
const race = new Race(track, { mode: MODE, laps: meta.laps, difficulty: aiLevel(meta), rng, playerSkill: skill });
const dt = 1 / 120;
let t = 0;
while (t < 3) { race.step(dt, null, false); t += dt; }
const log = [];
const k = race.player.kart;
let lastStuck = 0;
while (race.player.finishT == null && race.clock < 900) {
  race.step(dt, null, true);
  const s = ((k.lastS ?? 0) % track.length + track.length) % track.length;
  for (const e of k.events) {
    if (e.type === 'wall') log.push(['撞牆', s, `impact ${e.impact.toFixed(1)}`]);
    else if (e.type === 'fall') log.push([e.hazard ? '掉進危險區' : '掉落', s, '']);
    else if (e.type === 'land' && e.impact > 12) log.push(['重摔', s, `vy ${e.impact.toFixed(1)}`]);
  }
  k.events.length = 0;
  const st = race.player.driver?.stuckN || 0;
  if (st > lastStuck) { log.push(['卡住重生', s, '']); lastStuck = st; }
}
console.log(`${id}：${race.player.laps.map((x) => x.toFixed(1)).join(' / ')} 秒`);
// 設計腳本（tools/tracks/<id>.py）寫進 layout 的 tags：沿線距離 → 段名（依實際長度等比例換算）
const tags = lay.tags ? Object.entries(lay.tags) : [];
const tagEnd = tags.length ? Math.max(...tags.map(([, v]) => v[1])) : 1;
const tagOf = (s) => {
  if (!tags.length) return `at≈${atOf(s)}`;
  const u = s * tagEnd / track.length;
  const hit = tags.filter(([, v]) => u >= v[0] && u < v[1]).map(([k, v]) => `${k}+${Math.round(u - v[0])}m`);
  return hit.length ? hit.join(',') : `（${Math.round(u)}）`;
};
for (const [what, s, info] of log) console.log(`  ${what.padEnd(6)} s=${s.toFixed(0).padStart(5)} m  ${tagOf(s)}  ${info}`);
