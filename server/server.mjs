// KCar 多人連線 server（本機架設）。
//
//   node server/server.mjs                  # 預設埠 8787
//   node server/server.mjs --port 9000
//   node server/server.mjs --lag 60 --jitter 30 --loss 0.05   # 網路模擬（單向延遲 ms、抖動 ms、快照丟包率），測同步用
//
// 同一個埠同時做兩件事：
//   http://<這台的 IP>:8787/      遊戲本體（直接讀這個 repo 的檔案，所以 server 與網頁永遠是同一版物理）
//   ws://<這台的 IP>:8787/ws      連線協議（JSON 文字訊框）
//   http://<這台的 IP>:8787/version  正在跑哪一版、幾間房、幾個人
//
// 零相依：只用 Node 內建模組（WebSocket 自己實作最小可用的那部分），不用 npm install。
// 同步做法見 js/net/shared.js 開頭；協議見 README〈多人連線〉。

import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { readFileSync, statSync, createReadStream } from 'node:fs';
import { networkInterfaces } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, join, normalize, extname, sep } from 'node:path';
import { performance } from 'node:perf_hooks';

import { VERSION } from '../js/version.js';
import { TRACKS, trackById } from '../js/tracks.js';
import { Track } from '../js/track.js';
import { Kart } from '../js/kart.js';
import { P } from '../js/tuning.js';
import { AutoDriver } from '../js/bot.js';
import { rivalSkill, collideKarts, estimateFinishOf, standingsOf, GRID_SLOTS } from '../js/race.js';
import {
  PROTO, STEP, SNAP_EVERY, COUNT_TICKS, MAX_PLAYERS, FrameInput, heldOf, NEUTRAL, stepKart, SEAT_NAMES,
} from '../js/net/shared.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

// ------------------------------------------------------------ 參數
const argv = process.argv.slice(2);
const arg = (name, def) => {
  const i = argv.indexOf('--' + name);
  return i >= 0 && argv[i + 1] !== undefined ? Number(argv[i + 1]) : def;
};
const PORT = arg('port', 8787);
const NET = { lag: arg('lag', 0), jitter: arg('jitter', 0), loss: arg('loss', 0) };
const IDLE_TO_BOT_MS = 3000; // 3 秒沒收到輸入（切到別的分頁、斷訊）就交給電腦代駕，回來自動接回
const IDLE_NEUTRAL_MS = 500; // 0.5 秒沒輸入先放開所有鍵，別讓車一直按著油門衝
const AFTER_FIRST_FINISH = 30; // 第一位真人完賽後最多再等 30 秒
const MAX_RACE_SEC = 20 * 60;
const LOAD_TIMEOUT_MS = 15000;

const log = (...a) => console.log(new Date().toTimeString().slice(0, 8), ...a);

// ------------------------------------------------------------ 靜態檔案
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.glb': 'model/gltf-binary',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
  '.webmanifest': 'application/manifest+json', '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8',
};

function serveStatic(req, res) {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p === '/') p = '/index.html';
  const file = normalize(join(ROOT, p));
  // 不准跑出 repo、不給點開頭的路徑（.git 之類）
  if (!file.startsWith(ROOT + sep) || p.split('/').some((seg) => seg.startsWith('.'))) {
    res.writeHead(403).end('forbidden');
    return;
  }
  let st;
  try { st = statSync(file); } catch (e) { st = null; }
  if (!st || !st.isFile()) { res.writeHead(404).end('not found'); return; }
  res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream', 'Content-Length': st.size, 'Cache-Control': 'no-cache' });
  createReadStream(file).pipe(res);
}

// ------------------------------------------------------------ 最小 WebSocket（RFC 6455：文字訊框、分段、ping/pong、close）
class WsSocket {
  constructor(socket) {
    this.socket = socket;
    this.buf = Buffer.alloc(0);
    this.frags = null;
    this.open = true;
    this.onmessage = null;
    this.onclose = null;
    socket.setNoDelay(true);
    socket.on('data', (d) => { this.buf = this.buf.length ? Buffer.concat([this.buf, d]) : d; this.parse(); });
    socket.on('close', () => this.closed());
    socket.on('error', () => this.closed());
  }

  parse() {
    for (;;) {
      const b = this.buf;
      if (b.length < 2) return;
      const fin = b[0] & 0x80, op = b[0] & 0x0f, masked = b[1] & 0x80;
      let len = b[1] & 0x7f, off = 2;
      if (len === 126) { if (b.length < 4) return; len = b.readUInt16BE(2); off = 4; } else if (len === 127) { if (b.length < 10) return; len = Number(b.readBigUInt64BE(2)); off = 10; }
      if (len > (1 << 20) || !masked) { this.close(1002); return; } // client 一定要遮罩；太大的訊框不收
      if (b.length < off + 4 + len) return;
      const mask = b.subarray(off, off + 4);
      const data = Buffer.from(b.subarray(off + 4, off + 4 + len));
      for (let i = 0; i < data.length; i++) data[i] ^= mask[i & 3];
      this.buf = b.subarray(off + 4 + len);
      if (op === 0x8) { this.close(1000); return; }
      if (op === 0x9) { this.frame(0xA, data); continue; }
      if (op === 0xA) continue;
      if (op === 0x1 || op === 0x2) this.frags = [data];
      else if (op === 0x0 && this.frags) this.frags.push(data);
      else continue;
      if (fin) {
        const msg = Buffer.concat(this.frags).toString('utf8');
        this.frags = null;
        if (this.onmessage) this.onmessage(msg);
      }
    }
  }

  frame(op, payload) {
    if (!this.open) return;
    const n = payload.length;
    const head = n < 126 ? Buffer.from([0x80 | op, n]) : n < 65536 ? Buffer.alloc(4) : Buffer.alloc(10);
    if (n >= 126 && n < 65536) { head[0] = 0x80 | op; head[1] = 126; head.writeUInt16BE(n, 2); }
    if (n >= 65536) { head[0] = 0x80 | op; head[1] = 127; head.writeBigUInt64BE(BigInt(n), 2); }
    this.socket.write(Buffer.concat([head, payload]));
  }

  send(text) { this.frame(0x1, Buffer.from(text, 'utf8')); }
  /** 寫不出去還堆著的位元組（慢連線判斷用） */
  get backlog() { return this.socket.writableLength; }

  close(code = 1000) {
    if (!this.open) return;
    const p = Buffer.alloc(2);
    p.writeUInt16BE(code, 0);
    this.frame(0x8, p);
    this.open = false;
    this.socket.end();
    this.closed();
  }

  closed() {
    if (this.done) return;
    this.done = true;
    this.open = false;
    if (this.onclose) this.onclose();
  }
}

// ------------------------------------------------------------ 連線（一位玩家）
let nextId = 1;
const conns = new Set();
const rooms = new Map();

class Conn {
  constructor(ws) {
    this.ws = ws;
    this.id = nextId++;
    this.name = '';
    this.ready = false; // hello 過了
    this.room = null;
    this.racer = null;
    this.q = []; // 還沒處理的輸入
    this.lastSeq = 0;
    this.ack = 0;
    this.last = NEUTRAL;
    this.lastInputAt = 0;
    this.inp = new FrameInput(NEUTRAL);
    this.downAt = 0;
    this.upAt = 0;
    ws.onmessage = (text) => this.delayed('upAt', () => this.onMessage(text));
    ws.onclose = () => this.onClose();
  }

  /** 網路模擬：延遲＋抖動，但保持先後順序 */
  delayed(key, fn) {
    if (!NET.lag && !NET.jitter) { fn(); return; }
    const now = performance.now();
    const at = Math.max(this[key], now + NET.lag + Math.random() * NET.jitter);
    this[key] = at;
    setTimeout(fn, at - now);
  }

  /** snap：快照可丟（慢連線丟舊保新、網路模擬丟包）；其他訊息（開局、結算）一定送到 */
  send(obj, snap = false) {
    if (!this.ws.open) return;
    if (snap && (this.ws.backlog > 64 * 1024 || (NET.loss && Math.random() < NET.loss))) return;
    const text = JSON.stringify(obj);
    this.delayed('downAt', () => this.ws.send(text));
  }

  error(msg, code = '') { this.send({ t: 'error', code, msg }); }

  onMessage(text) {
    let m;
    try { m = JSON.parse(text); } catch (e) { return; }
    if (!m || typeof m.t !== 'string') return;
    if (m.t === 'ping') { this.send({ t: 'pong', c: m.c }); return; }
    if (m.t === 'hello') {
      if (m.ver !== VERSION || m.proto !== PROTO) {
        this.error(`版本不一樣：server 是 v${VERSION}，你的遊戲是 v${m.ver}。請重新整理網頁（Ctrl＋F5），或改開 server 給的網址。`, 'version');
        return;
      }
      this.name = String(m.name || '').replace(/[\s<>&"']/g, '').slice(0, 12) || `玩家${this.id}`;
      this.ready = true;
      this.send({ t: 'welcome', id: this.id, name: this.name, ver: VERSION });
      this.send(roomList());
      log(`#${this.id} ${this.name} 連上`);
      return;
    }
    if (!this.ready) return;
    const room = this.room;
    switch (m.t) {
      case 'list': this.send(roomList()); break;
      case 'create': {
        this.leaveRoom();
        const r = new Room(newCode(), trackById(m.track).id);
        rooms.set(r.code, r);
        r.join(this);
        log(`#${this.id} 開房 ${r.code}（${trackById(r.trackId).name}）`);
        break;
      }
      case 'join': {
        const r = rooms.get(String(m.code));
        if (!r) { this.error('找不到這個房間'); break; }
        if (r === room) break;
        if (r.state !== 'lobby') { this.error('這間正在比賽，等這場跑完再加入'); break; }
        if (r.players.length >= MAX_PLAYERS) { this.error(`這間已經滿了（最多 ${MAX_PLAYERS} 人）`); break; }
        this.leaveRoom();
        r.join(this);
        break;
      }
      case 'leave': this.leaveRoom(); this.send(roomList()); break;
      case 'track':
        if (room && room.host === this && room.state === 'lobby') { room.trackId = trackById(m.id).id; room.broadcastRoom(); pushRooms(); }
        break;
      case 'start':
        if (room && room.host === this && room.state === 'lobby') room.prepare();
        break;
      case 'loaded':
        if (room && room.state === 'loading') room.loaded(this);
        break;
      case 'in':
        if (this.racer && Array.isArray(m.f)) {
          for (const f of m.f) {
            if (!Array.isArray(f) || f.length !== 6 || !(f[0] > this.lastSeq)) continue;
            // 不信任 client：值一律夾回合法範圍
            const g = [f[0] | 0, Math.max(-1, Math.min(1, Math.round(f[1]) || 0)), f[2] ? 1 : 0, f[3] ? 1 : 0, f[4] ? 1 : 0, (f[5] | 0) & 31];
            this.lastSeq = g[0];
            this.q.push(g);
          }
          this.lastInputAt = performance.now();
        }
        break;
      default: break;
    }
  }

  /** server 每一步取這位玩家的一筆輸入。沒收到就延用上一筆（只延用按著的鍵） */
  consume(now) {
    const q = this.q;
    if (q.length > 24) {
      // 堆太多（client 跑太快或網路卡一下之後一次湧進來）：丟到剩 6 筆，「剛按下」併進下一筆別漏掉
      let carry = 0;
      while (q.length > 6) carry |= q.shift()[5];
      q[0][5] |= carry;
    }
    const f = q.shift();
    if (f) {
      this.ack = f[0];
      this.last = f;
      return this.inp.set(f);
    }
    if (now - this.lastInputAt > IDLE_NEUTRAL_MS) this.last = NEUTRAL;
    return this.inp.set(heldOf(this.last));
  }

  leaveRoom() {
    if (this.room) this.room.leave(this);
  }

  onClose() {
    conns.delete(this);
    this.leaveRoom();
    if (this.ready) log(`#${this.id} ${this.name} 離線`);
  }
}

function newCode() {
  for (;;) {
    const c = String(1000 + Math.floor(Math.random() * 9000));
    if (!rooms.has(c)) return c;
  }
}

function roomList() {
  return { t: 'rooms', rooms: [...rooms.values()].map((r) => r.brief()) };
}
/** 房間清單有變：推給還在大廳（沒進房）的人 */
function pushRooms() {
  const msg = roomList();
  for (const c of conns) if (c.ready && !c.room) c.send(msg);
}

// ------------------------------------------------------------ 賽道資料（快取）
const trackCache = new Map();
function loadTrack(id) {
  if (!trackCache.has(id)) trackCache.set(id, new Track(JSON.parse(readFileSync(join(ROOT, 'assets', id + '_path.json'), 'utf8'))));
  return trackCache.get(id);
}

// ------------------------------------------------------------ 房間
class Room {
  constructor(code, trackId) {
    this.code = code;
    this.trackId = trackId;
    this.players = []; // 依加入順序；每人一個座位 0～3
    this.host = null;
    this.state = 'lobby'; // lobby | loading | race
    this.race = null;
  }

  brief() {
    return { code: this.code, track: this.trackId, n: this.players.length, max: MAX_PLAYERS, state: this.state, host: this.host ? this.host.name : '' };
  }

  info() {
    return {
      t: 'room', code: this.code, track: this.trackId, state: this.state, host: this.host ? this.host.id : 0,
      players: this.players.map((c) => ({ id: c.id, name: c.name, seat: c.seat })),
    };
  }

  broadcast(obj) { for (const c of this.players) c.send(obj); }
  broadcastRoom() { this.broadcast(this.info()); }

  join(c) {
    const used = new Set(this.players.map((p) => p.seat));
    c.seat = [0, 1, 2, 3].find((s) => !used.has(s));
    c.room = this;
    this.players.push(c);
    if (!this.host) this.host = c;
    this.broadcastRoom();
    pushRooms();
  }

  leave(c) {
    this.players = this.players.filter((p) => p !== c);
    c.room = null;
    if (c.racer) { c.racer.conn = null; c.racer = null; } // 比賽中離開：這台車交給電腦開完
    if (this.host === c) this.host = this.players[0] || null;
    if (!this.players.length) {
      this.stop();
      rooms.delete(this.code);
      log(`房間 ${this.code} 沒人了，關掉`);
    } else {
      if (this.state === 'loading') this.checkLoaded();
      this.broadcastRoom();
    }
    pushRooms();
  }

  /** 房主按開始：先讓大家載入賽道，全部載好（或 15 秒）才開始倒數 */
  prepare() {
    this.state = 'loading';
    this.loadedSet = new Set();
    const meta = trackById(this.trackId);
    const humans = new Map(this.players.map((c) => [c.seat, c]));
    this.seats = [0, 1, 2, 3].map((s) => (humans.has(s)
      ? { seat: s, id: humans.get(s).id, name: humans.get(s).name, bot: false }
      : { seat: s, id: 0, name: SEAT_NAMES[s], bot: true }));
    this.broadcast({ t: 'prep', track: this.trackId, laps: meta.laps, seats: this.seats });
    this.broadcastRoom();
    pushRooms();
    this.loadTimer = setTimeout(() => this.begin(), LOAD_TIMEOUT_MS);
    log(`房間 ${this.code} 開賽：${meta.name}，${this.players.length} 位真人`);
  }

  loaded(c) {
    this.loadedSet.add(c);
    this.checkLoaded();
  }

  checkLoaded() {
    if (this.players.every((p) => this.loadedSet.has(p))) this.begin();
  }

  begin() {
    if (this.state !== 'loading') return;
    clearTimeout(this.loadTimer);
    const meta = trackById(this.trackId);
    const track = loadTrack(this.trackId);
    const L = track.length;
    // 起跑格：電腦排前面、真人排後面（跟單機一樣，真人從後面追）
    const order = [...this.seats].sort((a, b) => (a.bot === b.bot ? a.seat - b.seat : a.bot ? -1 : 1));
    let botIdx = 0;
    const racers = this.seats.map((s) => {
      const kart = new Kart(track);
      const [ds, lat] = GRID_SLOTS[order.indexOf(s)];
      kart.resetRace(L + ds, lat);
      const conn = s.bot ? null : this.players.find((c) => c.id === s.id) || null;
      const r = {
        seat: s.seat, id: s.id, name: s.name, bot: s.bot, conn, kart, driver: null,
        skill: s.bot ? rivalSkill(meta.difficulty, botIdx++) : rivalSkill(Math.min(5, meta.difficulty + 1), 1),
        held: [0, 0, 0, 0], lapsDone: 0, lapStart: 0, laps: [], finishT: null, ctrl: s.bot ? 'b' : 'h',
      };
      if (s.bot) r.driver = new AutoDriver(kart, r.skill);
      if (conn) {
        conn.racer = r;
        conn.q = [];
        conn.lastSeq = 0;
        conn.ack = 0;
        conn.last = NEUTRAL;
        conn.lastInputAt = performance.now();
      }
      return r;
    });
    this.race = { track, meta, racers, tick: 0, goTick: COUNT_TICKS, clock: 0, laps: meta.laps, firstFinish: null, endAt: null, t0: performance.now() };
    this.state = 'race';
    this.broadcast({ t: 'go', goTick: COUNT_TICKS, step: STEP });
    this.broadcastRoom();
    pushRooms();
    // 單寫者迴圈：只有這裡會改比賽狀態；計時用實際經過的時間追（Windows 的計時器不準，晚到就一次多跑幾步）
    this.timer = setInterval(() => this.loop(), 2);
  }

  loop() {
    const R = this.race;
    if (!R) return;
    const now = performance.now();
    const target = Math.floor((now - R.t0) / (STEP * 1000));
    let n = 0;
    while (R.tick < target && n++ < 60) {
      try {
        this.stepOnce(now);
      } catch (e) {
        // 一間房出錯不要拖垮整台 server：記下來、結束這場
        log(`房間 ${this.code} 模擬出錯：`, e);
        this.broadcast({ t: 'error', msg: 'server 模擬出錯，這場中止' });
        this.stop();
        this.broadcastRoom();
        pushRooms();
        return;
      }
      if (!this.race) return; // 這一步剛好比完
      if (R.tick % SNAP_EVERY === 0) this.sendSnaps();
    }
    if (R.tick < target) R.t0 = now - R.tick * STEP * 1000; // 卡太久（例如電腦休眠）就不追了
  }

  stepOnce(now) {
    const R = this.race;
    const karts = R.racers.map((r) => r.kart);
    const tick = R.tick;
    const lead = Math.max(-1e9, ...R.racers.filter((r) => !r.bot && r.conn).map((r) => r.kart.dist));
    for (const r of R.racers) {
      const k = r.kart;
      let inp;
      const c = r.conn;
      const human = c && c.ws.open && r.finishT == null && now - c.lastInputAt < IDLE_TO_BOT_MS;
      if (human) {
        inp = c.consume(now);
        r.ctrl = 'h';
        k.topMul = 1;
      } else {
        // 純電腦、或真人斷線／掛機／已完賽：電腦代駕（座位連線表就是「誰在開」的唯一依據）
        if (!r.driver) r.driver = new AutoDriver(k, r.skill);
        if (c) c.consume(now); // 還連著就照樣吃掉輸入（完賽後也是），排隊才不會越堆越長
        r.driver.think(STEP, karts.filter((o) => o !== k));
        inp = r.driver.input;
        r.ctrl = r.bot ? 'b' : 'a';
        if (r.finishT != null) k.topMul = 0.85;
        else if (r.bot && lead > -1e9) k.topMul = r.skill.speed + Math.max(-0.03, Math.min(0.05, (lead - k.dist) / 600));
        else k.topMul = r.bot ? r.skill.speed : 1;
        if (r.bot && tick === R.goTick && Math.random() < 0.3 + R.meta.difficulty * 0.12) k.addBoost(P.startBoost, 1.0, 'start');
      }
      if (human && r.driver) r.driver = null; // 真人接回來了
      r.held = [inp.steer, inp.throttle ? 1 : 0, inp.braking ? 1 : 0, inp.driftHeld ? 1 : 0];
      stepKart(k, inp, tick, R.goTick);
      k.events.length = 0;
    }
    collideKarts(karts);
    for (const k of karts) k.events.length = 0;
    R.tick++;
    if (R.tick <= R.goTick) return;
    R.clock = (R.tick - R.goTick) * STEP;
    const L = R.track.length;
    for (const r of R.racers) {
      const n = Math.floor(r.kart.dist / L);
      if (n > r.lapsDone) {
        r.lapsDone = n;
        r.laps.push(R.clock - r.lapStart);
        r.lapStart = R.clock;
        if (r.lapsDone >= R.laps && r.finishT == null) {
          r.finishT = R.clock;
          // 「第一位真人完賽後 30 秒結算」只算還在房裡的真人（離開的人那台由電腦開完，不該催別人）
          if (!r.bot && r.conn && R.firstFinish == null) R.firstFinish = R.clock;
        }
      }
    }
    const humans = R.racers.filter((r) => !r.bot);
    if (R.endAt == null && humans.every((r) => r.finishT != null || !r.conn)) R.endAt = R.clock + 2;
    if (R.endAt == null && R.firstFinish != null && R.clock > R.firstFinish + AFTER_FIRST_FINISH) R.endAt = R.clock;
    if ((R.endAt != null && R.clock >= R.endAt) || R.clock > MAX_RACE_SEC) this.finish();
  }

  sendSnaps() {
    const R = this.race;
    const rs = R.racers.map((r) => [r.seat, r.kart.getState(), r.held, r.lapsDone, r.lapStart, r.finishT, r.ctrl, r.laps]);
    for (const c of this.players) {
      if (!c.racer) continue;
      c.send({ t: 'snap', k: R.tick, g: R.goTick, a: c.ack, q: c.q.length, r: rs }, true);
    }
  }

  finish() {
    const R = this.race;
    const L = R.track.length;
    const order = standingsOf(R.racers)
      .map((r) => ({ seat: r.seat, id: r.id, name: r.name, bot: r.bot, t: estimateFinishOf(r, R.laps, L, R.clock), done: r.finishT != null, laps: r.laps }))
      .sort((a, b) => a.t - b.t);
    this.stop();
    this.broadcast({ t: 'result', track: this.trackId, order });
    this.broadcastRoom();
    pushRooms();
    log(`房間 ${this.code} 比完：${order.map((o, i) => `${i + 1}.${o.name}`).join(' ')}`);
  }

  stop() {
    clearInterval(this.timer);
    clearTimeout(this.loadTimer);
    if (this.race) for (const r of this.race.racers) if (r.conn) r.conn.racer = null;
    this.race = null;
    this.state = 'lobby';
  }
}

// ------------------------------------------------------------ HTTP＋升級成 WebSocket
const server = createServer((req, res) => {
  const p = new URL(req.url, 'http://x').pathname;
  if (p === '/version') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify({ game: 'KCar', version: VERSION, proto: PROTO, rooms: rooms.size, players: [...conns].filter((c) => c.ready).length, netsim: NET }));
    return;
  }
  if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405).end(); return; }
  serveStatic(req, res);
});

server.on('upgrade', (req, socket) => {
  const p = new URL(req.url, 'http://x').pathname;
  const key = req.headers['sec-websocket-key'];
  if (p !== '/ws' || !key || String(req.headers.upgrade).toLowerCase() !== 'websocket') { socket.destroy(); return; }
  const accept = createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
  socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
  conns.add(new Conn(new WsSocket(socket)));
});

server.listen(PORT, () => {
  const ips = Object.values(networkInterfaces()).flat().filter((a) => a && a.family === 'IPv4' && !a.internal).map((a) => a.address);
  console.log(`KCar 多人連線 server v${VERSION}（協議 ${PROTO}）`);
  console.log(`  這台電腦：http://localhost:${PORT}/`);
  for (const ip of ips) console.log(`  同網路的其他裝置：http://${ip}:${PORT}/`);
  if (NET.lag || NET.jitter || NET.loss) console.log(`  網路模擬：單向延遲 ${NET.lag}ms、抖動 ${NET.jitter}ms、快照丟包 ${NET.loss * 100}%`);
  console.log(`  賽道：${TRACKS.map((t) => t.name).join('、')}；每間最多 ${MAX_PLAYERS} 人，空位電腦補`);
});
