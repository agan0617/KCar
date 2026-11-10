// 多人連線大廳（HTML 對話框）：連線 → 房間清單 → 房間（房主選賽道、開始；空位電腦補）。
// 比賽本身由 main.js 接手（onPrep／onGo／onSnap／onResult）。

import { openDialog, closeDialog, dialogOpen } from '../controls.js';
import { TRACKS, trackById } from '../tracks.js';
import { Net, defaultServer, hostOf, needsServerPage } from './client.js';
import { SEAT_COLORS, SEAT_NAMES, MAX_PLAYERS } from './shared.js';

const NAME_KEY = 'kcar.name';
const SERVER_KEY = 'kcar.server';
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 忽略 */ } },
};
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export class Lobby {
  /** h：getTrack()、onRoomTrack(id)、onPrep(m)、onGo(m)、onSnap(m)、onResult(m)、onDisconnect() */
  constructor(h) {
    this.h = h;
    this.net = null;
    this.rooms = [];
    this.room = null;
    this.view = 'connect';
    this.msg = '';
  }

  get connected() { return !!this.net && this.net.connected; }
  get inRoom() { return !!this.room; }
  get isHost() { return !!this.room && this.net && this.room.host === this.net.id; }

  open() {
    if (!this.connected) this.showConnect();
    else if (this.room) this.showRoom();
    else this.showList();
  }

  // ---------------------------------------------------------- 連線
  /** 從 GitHub Pages／App 轉過來的（網址帶 #mp=名字）：直接用那個名字連這台 server */
  autoConnect(name) {
    store.set(NAME_KEY, name);
    store.set(SERVER_KEY, '');
    this.showConnect(true);
  }

  showConnect(auto = false) {
    this.view = 'connect';
    const { body, bar } = openDialog('多人連線');
    body.innerHTML = `
      <p class="dlg-note">最多 ${MAX_PLAYERS} 人同場，空位由電腦補滿。先在一台電腦開 server（說明在下面），大家連同一台。</p>
      <form class="lb-form">
        <label>名字</label><input name="name" maxlength="12" autocomplete="off">
        <label>Server</label><input name="addr" placeholder="${esc(defaultServer())}" autocomplete="off">
      </form>
      <p class="dlg-note ${this.msg ? 'warn' : ''}" data-msg>${esc(this.msg)}</p>
      <h4>怎麼開 server</h4>
      <p>在放 KCar 的電腦上執行 <kbd>node server/server.mjs</kbd>（或雙擊 <kbd>server\\start.bat</kbd>），
      畫面會列出網址。同一個網路的其他電腦、手機（含 KCar App），Server 欄填那台的 IP（例如 <kbd>192.168.1.5</kbd>），
      會自動改開 server 供應的網頁；也可以直接用瀏覽器開 <kbd>http://那台的 IP:8787/</kbd>。
      開 server 的那台電腦自己玩，Server 欄留空（＝<kbd>localhost:8787</kbd>）。</p>`;
    const form = body.querySelector('form');
    form.name.value = store.get(NAME_KEY, '');
    form.addr.value = store.get(SERVER_KEY, '');
    const go = () => this.connect(form.name.value.trim(), form.addr.value.trim(), body.querySelector('[data-msg]'), ok);
    form.onsubmit = (e) => { e.preventDefault(); go(); };
    const ok = button('連線', go, 'primary');
    bar.append(button('取消', closeDialog), ok);
    setTimeout(() => (form.name.value ? ok : form.name).focus(), 0);
    if (auto && form.name.value) go();
  }

  async connect(name, addr, msgEl, okBtn) {
    if (!name) { msgEl.textContent = '先取個名字'; msgEl.className = 'dlg-note warn'; return; }
    store.set(NAME_KEY, name);
    store.set(SERVER_KEY, addr);
    if (needsServerPage(addr)) {
      msgEl.textContent = `改開 server 的網頁（http://${hostOf(addr)}/）…`;
      msgEl.className = 'dlg-note';
      location.href = `http://${hostOf(addr)}/#mp=${encodeURIComponent(name)}`;
      return;
    }
    msgEl.textContent = '連線中…';
    msgEl.className = 'dlg-note';
    okBtn.disabled = true;
    const net = new Net();
    this.bind(net);
    try {
      await net.connect(addr, name);
    } catch (e) {
      okBtn.disabled = false;
      msgEl.textContent = e.message;
      msgEl.className = 'dlg-note warn';
      return;
    }
    this.net = net;
    this.msg = '';
    this.showList();
  }

  bind(net) {
    net.on('rooms', (m) => { this.rooms = m.rooms; if (this.view === 'list' && dialogOpen()) this.renderList(); });
    net.on('room', (m) => {
      const prevTrack = this.room && this.room.track;
      this.room = m;
      if (m.track !== prevTrack) this.h.onRoomTrack(m.track);
      if (this.view === 'room' && dialogOpen()) this.renderRoom();
    });
    net.on('error', (m) => {
      this.msg = m.msg;
      const el = document.querySelector('.dlg [data-msg]');
      if (el) { el.textContent = m.msg; el.className = 'dlg-note warn'; }
    });
    net.on('prep', (m) => this.h.onPrep(m));
    net.on('go', (m) => { closeDialog(); this.h.onGo(m); });
    net.on('snap', (m) => this.h.onSnap(m));
    net.on('result', (m) => this.h.onResult(m));
    net.on('close', () => {
      this.net = null;
      this.room = null;
      this.msg = '跟 server 的連線斷了';
      this.h.onDisconnect();
    });
  }

  disconnect() {
    if (this.net) this.net.close();
    this.net = null;
    this.room = null;
  }

  // ---------------------------------------------------------- 房間清單
  showList() {
    this.view = 'list';
    const { body, bar } = openDialog('多人連線　房間');
    body.innerHTML = `
      <p class="dlg-note">已連上 <b>${esc(this.net.name)}</b>　延遲 <span data-rtt>…</span></p>
      <div class="lb-row">
        <select data-track>${TRACKS.map((t) => `<option value="${t.id}">${esc(t.name)}　${'★'.repeat(t.difficulty)}</option>`).join('')}</select>
        <button class="lb-btn go" data-create>開新房間</button>
      </div>
      <form class="lb-row"><input name="code" inputmode="numeric" maxlength="4" placeholder="輸入 4 位數房號"><button class="lb-btn">加入</button></form>
      <h4>開著的房間</h4>
      <div class="lb-list" data-list></div>
      <p class="dlg-note ${this.msg ? 'warn' : ''}" data-msg>${esc(this.msg)}</p>`;
    const sel = body.querySelector('[data-track]');
    sel.value = this.h.getTrack();
    body.querySelector('[data-create]').onclick = () => { this.msg = ''; this.net.send({ t: 'create', track: sel.value }); this.showRoom(); };
    const form = body.querySelector('form');
    form.onsubmit = (e) => { e.preventDefault(); const c = form.code.value.trim(); if (c) this.join(c); };
    bar.append(button('斷線', () => { this.disconnect(); closeDialog(); }), button('關閉', closeDialog, 'primary'));
    this.renderList();
    this.net.send({ t: 'list' });
    this.rttTimer(body);
  }

  join(code) {
    this.msg = '';
    this.net.send({ t: 'join', code });
    this.showRoom();
  }

  renderList() {
    const list = document.querySelector('.dlg [data-list]');
    if (!list) return;
    list.innerHTML = '';
    if (!this.rooms.length) { list.innerHTML = '<div class="dlg-note">還沒有人開房，開一間吧</div>'; return; }
    for (const r of this.rooms) {
      const row = document.createElement('div');
      row.className = 'lb-room';
      const st = r.state === 'lobby' ? (r.n >= r.max ? '滿了' : '等待中') : '比賽中';
      row.innerHTML = `<b>${esc(r.code)}</b><span>${esc(trackById(r.track).name)}　${r.n}/${r.max} 人　房主 ${esc(r.host)}　<small>${st}</small></span>`;
      const b = button('加入', () => this.join(r.code), 'lb-btn');
      b.disabled = r.state !== 'lobby' || r.n >= r.max;
      row.appendChild(b);
      list.appendChild(row);
    }
  }

  // ---------------------------------------------------------- 房間
  showRoom() {
    this.view = 'room';
    const { body, bar } = openDialog('多人連線　房間');
    body.innerHTML = '<div data-room><p class="dlg-note">進房中…</p></div><p class="dlg-note" data-msg></p>';
    this.roomBar = bar;
    this.renderRoom();
    this.rttTimer(body);
  }

  renderRoom() {
    const box = document.querySelector('.dlg [data-room]');
    if (!box) return;
    const msgEl = document.querySelector('.dlg [data-msg]');
    if (msgEl) { msgEl.textContent = this.msg; msgEl.className = `dlg-note${this.msg ? ' warn' : ''}`; }
    const r = this.room;
    const bar = this.roomBar;
    bar.innerHTML = '';
    if (!r) {
      bar.append(button('回房間清單', () => this.showList()));
      return;
    }
    const host = this.isHost;
    const bySeat = new Map(r.players.map((p) => [p.seat, p]));
    const seats = [0, 1, 2, 3].map((s) => {
      const p = bySeat.get(s);
      const tag = p ? `${p.id === r.host ? '<small>房主</small>' : ''}${p.id === this.net.id ? '<small>（你）</small>' : ''}` : '';
      return `<div class="lb-seat ${p ? '' : 'lb-empty'}"><i class="lb-dot" style="background:${SEAT_COLORS[s]}"></i><span>${p ? esc(p.name) : `電腦 ${SEAT_NAMES[s]}`}</span>${tag}</div>`;
    }).join('');
    const loading = r.state !== 'lobby';
    box.innerHTML = `
      <div class="lb-row"><span>房號</span><span class="lb-code">${esc(r.code)}</span><span class="dlg-note">延遲 <span data-rtt>…</span></span></div>
      <div class="lb-row"><span>賽道</span>${host && !loading
        ? `<select data-track>${TRACKS.map((t) => `<option value="${t.id}">${esc(t.name)}　${'★'.repeat(t.difficulty)}</option>`).join('')}</select>`
        : `<b>${esc(trackById(r.track).name)}　${'★'.repeat(trackById(r.track).difficulty)}</b>`}</div>
      ${seats}
      <p class="dlg-note">${loading ? '比賽準備中…' : host ? '人到齊就按「開始比賽」，空位電腦補。' : '等房主開始…'}</p>`;
    const sel = box.querySelector('[data-track]');
    if (sel) {
      sel.value = r.track;
      sel.onchange = () => this.net.send({ t: 'track', id: sel.value });
    }
    bar.append(button('離開房間', () => { this.leave(); this.showList(); }));
    if (host) {
      const go = button('開始比賽', () => { this.msg = ''; this.net.send({ t: 'start' }); }, 'primary');
      go.disabled = loading;
      bar.append(go);
    }
  }

  leave() {
    if (this.net) this.net.send({ t: 'leave' });
    this.room = null;
  }

  rttTimer(body) {
    const tick = () => {
      const el = body.querySelector('[data-rtt]') || document.querySelector('.dlg [data-rtt]');
      if (!el || !body.isConnected || !this.net) { clearInterval(t); return; }
      el.textContent = this.net.rtt ? `${Math.round(this.net.rtt)} ms` : '…';
    };
    const t = setInterval(tick, 500);
    tick();
  }
}

function button(text, onClick, cls = '') {
  const b = document.createElement('button');
  b.textContent = text;
  b.className = cls;
  b.type = 'button';
  b.onclick = onClick;
  return b;
}
