// 多人連線無頭測試：開 N 個假玩家連上 server，各自用自動駕駛開「自己預測的那台車」跑完一場，
// 量回滾修正量（預測跟 server 差多少）、名次、有沒有斷線。
//
//   node server/server.mjs --port 8799 --lag 40 --jitter 20     （另一個視窗先開 server）
//   node tools/nettest.mjs [人數=2] [賽道=beach] [埠=8799]

import { Net } from '../js/net/client.js';
import { OnlineRace } from '../js/net/client.js';
import { AutoDriver, PERFECT_SKILL } from '../js/bot.js';
import { Track } from '../js/track.js';
import { STEP } from '../js/net/shared.js';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const N = Number(process.argv[2] || 2);
const trackId = process.argv[3] || 'beach';
const port = process.argv[4] || '8799';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const track = new Track(JSON.parse(readFileSync(join(root, 'assets', trackId + '_path.json'), 'utf8')));

const players = [];
for (let i = 0; i < N; i++) {
  const net = new Net();
  const p = { net, name: `測試${i + 1}`, race: null, prep: null, result: null, maxCorr: 0, sumCorr: 0, nCorr: 0, snaps: 0, closed: false };
  net.on('room', (m) => { p.room = m; });
  net.on('rooms', () => {});
  net.on('error', (m) => console.log(p.name, '錯誤', m.msg));
  net.on('prep', (m) => { p.prep = m; net.send({ t: 'loaded' }); });
  net.on('go', (m) => {
    p.race = new OnlineRace(track, net, { seats: p.prep.seats, laps: p.prep.laps, goTick: m.goTick, myId: net.id });
    // 自己那台用自動駕駛開（開的是預測的 sim，跟真人看著畫面開一樣）
    p.driver = new AutoDriver(p.race.player.sim, { ...PERFECT_SKILL, perfect: 0.6, dj: 0.5, lane: i * 2 - 1 });
  });
  net.on('snap', (m) => {
    const r = p.race;
    if (!r) return;
    const me = r.player;
    const before = [me.sim.x, me.sim.z];
    r.onSnap(m);
    p.snaps++;
    if (process.env.NETDEBUG && p.snaps % 60 === 0) console.log(p.name, `tick ${m.k} q ${m.q} 未確認 ${r.hist.length} rate ${r.rate.toFixed(3)}`);
    if (r.predicting && r.phase === 'race') {
      const d = Math.hypot(before[0] - me.sim.x, before[1] - me.sim.z);
      if (process.env.NETDEBUG && d > 0.3) console.log(p.name, `大修正 ${(d * 100).toFixed(0)}cm tick ${m.k}`);
      p.maxCorr = Math.max(p.maxCorr, d);
      p.sumCorr += d;
      p.nCorr++;
    }
  });
  net.on('result', (m) => { p.result = m; });
  net.on('close', () => { p.closed = true; });
  await net.connect(`localhost:${port}`, p.name);
  players.push(p);
}

players[0].net.send({ t: 'create', track: trackId });
await sleep(200);
const code = players[0].room.code;
for (const p of players.slice(1)) p.net.send({ t: 'join', code });
await sleep(200);
console.log(`房間 ${code}：${players[0].room.players.map((x) => `${x.name}(座位${x.seat})`).join('、')}`);
players[0].net.send({ t: 'start' });

// 每 16ms 一個「畫面幀」：照 rate 推進預測、送輸入
let acc = 0, last = performance.now();
const t0 = performance.now();
while (!players.every((p) => p.result || p.closed) && performance.now() - t0 < 300000) {
  await sleep(16);
  const now = performance.now(), dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  for (const p of players) {
    if (!p.race) continue;
    p.acc = (p.acc || 0) + dt * p.race.rate;
    while (p.acc >= STEP) {
      p.driver.think(STEP, []);
      p.race.step(p.driver.input);
      p.race.player.kart.events.length = 0;
      p.acc -= STEP;
    }
    p.race.updateView(dt);
    p.race.flush();
  }
}

for (const p of players) {
  const r = p.result;
  console.log(`${p.name}：快照 ${p.snaps}、回滾修正 平均 ${(p.sumCorr / Math.max(1, p.nCorr) * 100).toFixed(1)} cm／最大 ${(p.maxCorr * 100).toFixed(1)} cm、rate ${p.race && p.race.rate.toFixed(3)}、延遲 ${Math.round(p.net.rtt)}ms${p.closed ? '、斷線' : ''}`);
}
const res = players[0].result;
if (res) console.log('名次：' + res.order.map((o, i) => `${i + 1}.${o.name}${o.bot ? '(電腦)' : ''} ${o.t.toFixed(2)}${o.done ? '' : '≈'}`).join('  '));
else console.log('沒收到結算（逾時）');
for (const p of players) p.net.close();
process.exit(0);
