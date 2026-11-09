import * as THREE from 'three';
import { VERSION } from './version.js';
import { P, togglePanel, panelOpen } from './tuning.js';
import { Input } from './input.js';
import { Track } from './track.js';
import { Race, RIVALS } from './race.js';
import { TRACKS, trackById } from './tracks.js';
import { createWorld } from './world.js';
import { Fx } from './fx.js';
import { Hud, fmtTime } from './hud.js';
import { Sfx } from './audio.js';
import { openHelp, openKeySettings, closeDialog, onKeysChange } from './controls.js';

const STEP = 1 / 120;
const BEST_KEY = 'kcar.best.v2'; // { [賽道 id]: { lap, total } }
const TRACK_KEY = 'kcar.track';

const lerpAngle = (a, b, t) => {
  let d = b - a;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return a + d * t;
};
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* 忽略 */ } },
};

async function main() {
  const input = new Input();
  const sfx = new Sfx();
  const hud = await Hud.create(document.getElementById('ui'), input);
  hud.showLoading(0);
  hud.render();

  const renderer = new THREE.WebGLRenderer({ canvas: document.getElementById('game'), antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, input.isTouch ? 1.5 : 2));
  renderer.setSize(innerWidth, innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;

  const camera = new THREE.PerspectiveCamera(P.fov, innerWidth / innerHeight, 0.3, 5000);
  addEventListener('resize', () => {
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
  });

  const world = await createWorld(renderer, (p) => { hud.showLoading(p); hud.render(); });
  // 四台車的外觀：玩家＋三位對手（換色）；Fx 各自一份
  const looks = [null, ...RIVALS].map((c) => {
    const v = world.makeKart(c);
    v.fx = new Fx(world.scene, v.group, v.parts);
    return v;
  });
  const playerLook = looks[0];
  const lookOf = (r) => (r.isPlayer ? playerLook : looks[1 + RIVALS.findIndex((x) => x.name === r.name)]);

  // ------------------------------------------------------------ 狀態
  const G = {
    state: 'loading', // loading | title | countdown | race | paused | result
    mode: 'race',
    trackId: trackById(store.get(TRACK_KEY, 'beach')).id,
    meta: null,
    track: null,
    race: null,
    best: store.get(BEST_KEY, {}),
    camYaw: 0,
    camPos: new THREE.Vector3(),
    shake: 0,
    wrongT: 0,
    countT: 0,
    startBoostUsed: false,
    loadSeq: 0,
  };
  const bestOf = (id) => G.best[id] || (G.best[id] = {});

  async function selectTrack(id) {
    const seq = ++G.loadSeq;
    G.trackId = id;
    G.meta = trackById(id);
    store.set(TRACK_KEY, id);
    G.state = 'loading';
    showTitle(true);
    const path = await world.loadTrack(id, (p) => { if (seq === G.loadSeq) hud.setTitleLoading(p); });
    if (seq !== G.loadSeq) return; // 載入途中又換了別條
    G.track = new Track(path);
    hud.setTrack(G.track);
    G.race = new Race(G.track, { mode: 'race', laps: G.meta.laps, difficulty: G.meta.difficulty });
    syncLooks();
    for (const v of looks) v.fx.reset();
    G.state = 'title';
    showTitle(false);
  }

  function showTitle(loading) {
    hud.setRaceVisible(false, false);
    hud.countdown('');
    hud.showTitle({
      version: VERSION, tracks: TRACKS, selected: G.trackId, best: G.best, touch: input.isTouch, loading,
      onSelect: (id) => { if (id !== G.trackId) selectTrack(id); },
      onStart: (mode) => { if (G.state === 'title') startRace(mode); },
      onHelp: help,
      onSettings: settings,
    });
  }

  const help = () => openHelp({ touch: input.isTouch });
  const settings = () => openKeySettings({ onTuning: () => togglePanel(true) });
  // 改了按鍵：首頁底下那行說明跟著換
  onKeysChange(() => { if (G.state === 'title') showTitle(false); });

  function syncLooks() {
    for (const v of looks) v.group.visible = false;
    for (const r of G.race.racers) lookOf(r).group.visible = true;
  }

  function startRace(mode) {
    closeDialog();
    sfx.start();
    G.mode = mode;
    G.race = new Race(G.track, { mode, laps: G.meta.laps, difficulty: G.meta.difficulty });
    syncLooks();
    for (const v of looks) v.fx.reset();
    G.state = 'countdown';
    G.countT = 3.0;
    G.startBoostUsed = false;
    G.pendingStart = false;
    G.lastCount = 4;
    G.lastDist = undefined;
    G.wrongT = 0;
    hud.clearOverlay();
    hud.setRaceVisible(true, input.isTouch);
    hud.countdown('');
    snapCamera();
  }

  function goTitle() {
    togglePanel(false);
    G.race = new Race(G.track, { mode: 'race', laps: G.meta.laps, difficulty: G.meta.difficulty });
    syncLooks();
    G.state = 'title';
    showTitle(false);
  }

  function pause() {
    if (G.state !== 'race' && G.state !== 'countdown') return;
    G.prevState = G.state;
    G.state = 'paused';
    hud.setRaceVisible(false, false);
    hud.showPause({ onResume: resume, onRestart: () => { closeDialog(); startRace(G.mode); }, onHelp: help, onSettings: settings, onHome: () => { closeDialog(); goTitle(); } });
  }
  function resume() {
    closeDialog();
    togglePanel(false);
    hud.clearOverlay();
    hud.setRaceVisible(true, input.isTouch);
    G.state = G.prevState || 'race';
  }
  hud.onPause = pause;
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });

  function finish() {
    const race = G.race, me = race.player;
    G.state = 'result';
    hud.setRaceVisible(false, false);
    const b = bestOf(G.trackId);
    const bestLap = Math.min(...me.laps);
    const newLap = !(b.lap <= bestLap);
    if (newLap) b.lap = bestLap;
    let newTotal = false;
    if (G.mode !== 'free') {
      newTotal = !(b.total <= me.finishT);
      if (newTotal) b.total = me.finishT;
    }
    store.set(BEST_KEY, G.best);
    const order = race.racers
      .map((r) => ({ name: r.name, color: r.color, isPlayer: r.isPlayer, t: race.estimateFinish(r), done: r.finishT != null }))
      .sort((a, c) => a.t - c.t);
    hud.showResult({
      mode: G.mode, track: G.meta.name, total: me.finishT ?? race.clock, laps: me.laps, bestLap, newLap, newTotal, order,
      onRetry: () => startRace(G.mode), onHome: goTitle,
    });
    if (G.mode === 'race') {
      const place = order.findIndex((o) => o.isPlayer) + 1;
      sfx.beep(place === 1 ? 1318 : 660, 0.6, 'square', 0.25);
    }
  }

  // ------------------------------------------------------------ 事件 → 畫面／聲音回饋（只看玩家的車）
  function handleEvents(k) {
    for (const e of k.events) {
      switch (e.type) {
        case 'jet': {
          const txt = { perfect: '完美小噴！', good: '小噴', early: '小噴（太早）' }[e.q];
          const col = { perfect: '#4cd964', good: '#ffd23f', early: '#ff9f6b' }[e.q];
          hud.popup(txt, col, e.q === 'perfect' ? 50 : 40, 1.0, 0);
          sfx.whoosh(e.q === 'perfect' ? 1 : 0.7);
          break;
        }
        case 'dj': hud.popup('雙噴！', '#7fe0ff', 52, 1.0, 50); sfx.whoosh(1.1); break;
        case 'djEarly': hud.popup(e.t < P.djMin ? '雙噴太快' : '雙噴太慢', '#ff9f6b', 30, 0.8, 50); break;
        case 'jetMiss': hud.popup('錯過小噴', 'rgba(255,255,255,0.75)', 26, 0.7, 0); break;
        case 'nitro': hud.popup('氮氣！', '#7fd3ff', 56, 0.9, -40); sfx.whoosh(1.4); G.shake = 0.25; break;
        case 'nitroReady': hud.popup('集氣完成 +1 氮氣', '#34d6ff', 28, 0.9, 100); sfx.beep(1320, 0.12, 'sine', 0.2); break;
        case 'wall': sfx.bump(e.impact); G.shake = Math.min(0.6, e.impact * 0.05); break;
        case 'bump': if (e.impact > 2) { sfx.bump(e.impact); G.shake = Math.min(0.4, e.impact * 0.04); } break;
        default: break;
      }
    }
    k.events.length = 0;
  }

  // ------------------------------------------------------------ 每個物理步
  function physics(dt) {
    const race = G.race, me = race.player, k = me.kart;
    if (G.state === 'countdown') {
      G.countT -= dt;
      // 起步噴：GO 前 0.25 秒到 GO 後 0.2 秒之間按下 ↑／噴
      if (input.jet && !G.startBoostUsed) {
        G.startBoostUsed = true;
        if (G.countT < 0.25) G.pendingStart = true;
      }
      race.step(dt, input, false);
      if (G.countT <= 0) {
        G.state = 'race';
        if (G.pendingStart) startBoost(k);
        // 電腦也會起步噴（看難度）
        for (const r of race.racers) if (!r.isPlayer && Math.random() < 0.3 + G.meta.difficulty * 0.12) r.kart.addBoost(P.startBoost, 1.0, 'start');
      }
    } else if (G.state === 'race') {
      if (input.jet && !G.startBoostUsed && race.clock < 0.2) { G.startBoostUsed = true; startBoost(k); }
      race.step(dt, input, true);
      if (input.pressed('reset')) k.respawn();
      if (me.lapEvent) {
        me.lapEvent = false;
        const lt = me.laps[me.laps.length - 1];
        const b = bestOf(G.trackId);
        const isBest = !(b.lap <= lt);
        if (me.finishT != null) { finish(); input.endFrame(); return; }
        hud.popup(`第 ${me.lapsDone} 圈 ${fmtTime(lt)}${isBest ? ' ★' : ''}`, '#ffffff', 34, 1.6, -80);
        if (race.laps - me.lapsDone === 1) hud.popup('最後一圈！', '#ffd23f', 50, 1.6, 0);
        if (G.mode === 'free' && isBest) { b.lap = lt; store.set(BEST_KEY, G.best); }
        sfx.beep(880, 0.2, 'square', 0.2);
      }
      const ds = k.dist - (G.lastDist ?? k.dist);
      G.lastDist = k.dist;
      G.wrongT = ds < -0.002 && k.spd > 3 ? G.wrongT + dt : Math.max(0, G.wrongT - dt * 2);
    }
    handleEvents(k);
    input.endFrame();
  }

  function startBoost(k) {
    k.addBoost(P.startBoost, 1.0, 'start');
    hud.popup('起步噴！', '#4cd964', 46, 1.0, 0);
    sfx.whoosh(1);
  }

  // ------------------------------------------------------------ 鏡頭與車的外觀
  const tmpV = new THREE.Vector3();
  const look = new THREE.Vector3();
  function snapCamera() {
    const k = G.race.player.kart;
    G.camYaw = k.h;
    placeCamera(1, 1);
  }
  function placeCamera(dt, snap = 0) {
    const k = G.race.player.kart;
    const mix = k.drift ? P.camDriftMix : 0.15;
    // 鏡頭方向：主要跟速度方向（甩尾時才看得到車身打橫），一部分跟車頭
    const target = lerpAngle(k.phi, k.h, mix);
    G.camYaw = snap ? target : lerpAngle(G.camYaw, target, 1 - Math.exp(-P.camFollow * dt));
    const boost = k.nitroT > 0 ? 1 : k.boostT > 0 ? 0.6 : 0;
    const dist = P.camDist + boost * 0.9;
    const fx = Math.sin(G.camYaw), fz = Math.cos(G.camYaw);
    tmpV.set(k.x - fx * dist, k.y + P.camHeight, k.z - fz * dist);
    if (snap) G.camPos.copy(tmpV);
    else {
      const a = 1 - Math.exp(-12 * dt);
      G.camPos.x += (tmpV.x - G.camPos.x) * a;
      G.camPos.z += (tmpV.z - G.camPos.z) * a;
      G.camPos.y += (tmpV.y - G.camPos.y) * (1 - Math.exp(-6 * dt));
    }
    camera.position.copy(G.camPos);
    if (G.shake > 0) {
      camera.position.x += (Math.random() - 0.5) * G.shake;
      camera.position.y += (Math.random() - 0.5) * G.shake;
      G.shake = Math.max(0, G.shake - dt * 1.8);
    }
    look.set(k.x + fx * 4, k.y + 1.1, k.z + fz * 4);
    camera.lookAt(look);
    const spd01 = Math.min(1.4, Math.abs(k.spd) / P.maxSpeed);
    const fov = P.fov + spd01 * 4 + boost * P.fovBoost;
    camera.fov += (fov - camera.fov) * (1 - Math.exp(-5 * dt));
    camera.updateProjectionMatrix();
  }

  function poseKart(v, k, dt) {
    const g = v.group, pt = v.parts;
    g.position.set(k.x, k.y, k.z);
    g.rotation.y = k.h;
    g.rotation.x += (k.pitch - g.rotation.x) * Math.min(1, dt * 10);
    const lat = k.yawRate * Math.abs(k.spd);
    const targetRoll = Math.max(-0.12, Math.min(0.12, -lat * 0.0035)) + (k.drift ? k.driftDir * 0.05 : 0);
    v.roll += (targetRoll - v.roll) * Math.min(1, dt * 8);
    g.rotation.z = v.roll;
    pt.model.position.y = (k.onGrass || k.onCurb) && Math.abs(k.spd) > 3 ? (Math.random() - 0.5) * 0.06 : 0;
    v.lean += ((k.drift ? -k.driftDir * 0.22 : -k.steer * 0.12) - v.lean) * Math.min(1, dt * 8);
    if (pt.driver) pt.driver.rotation.z = v.lean;
    v.spin += k.spd * dt / 0.31;
    const steerVis = k.drift ? -k.driftDir * 0.25 + k.steer * 0.15 : k.steer * 0.42;
    pt.wheels.forEach((w, i) => {
      if (!w) return;
      w.rotation.x = v.spin;
      if (i < 2) w.rotation.y = -steerVis;
    });
  }

  // 對手頭上的名牌：投影到螢幕
  const proj = new THREE.Vector3();
  function nameTags() {
    const out = [];
    for (const r of G.race.racers) {
      if (r.isPlayer) continue;
      const k = r.kart;
      proj.set(k.x, k.y + 2.4, k.z);
      const dist = proj.distanceTo(camera.position);
      if (dist > 90) continue;
      proj.project(camera);
      if (proj.z > 1 || Math.abs(proj.x) > 1.1 || Math.abs(proj.y) > 1.1) continue;
      out.push({ x: (proj.x + 1) / 2 * innerWidth, y: (1 - proj.y) / 2 * innerHeight, name: r.name, color: r.color, a: Math.min(1, (90 - dist) / 25) });
    }
    return out;
  }

  // ------------------------------------------------------------ 主迴圈
  let last = performance.now(), acc = 0, t = 0;
  const titleCam = { a: 0 };
  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    t += dt;
    if (input.pressed('tuning')) togglePanel();
    if (input.pressed('pause')) {
      if (G.state === 'paused') resume();
      else if (panelOpen()) togglePanel(false);
      else pause();
    }
    if (!G.race) { input.endFrame(); hud.render(); return; }

    if (G.state === 'countdown' || G.state === 'race') {
      acc += dt;
      while (acc >= STEP && (G.state === 'countdown' || G.state === 'race')) { physics(STEP); acc -= STEP; }
    } else {
      input.endFrame();
      acc = 0;
    }

    if (G.state === 'countdown') {
      const n = Math.ceil(G.countT);
      if (n !== G.lastCount && n >= 1 && n <= 3) { G.lastCount = n; sfx.beep(523, 0.18, 'square', 0.22); }
      hud.countdown(n >= 1 ? String(n) : '');
    } else if (G.state === 'race' && G.race.clock < 0.8) {
      if (G.lastCount !== 0) { G.lastCount = 0; sfx.beep(1046, 0.4, 'square', 0.25); }
      hud.countdown('GO!', '#4cd964');
    } else hud.countdown('');

    const race = G.race, me = race.player, k = me.kart;
    for (const r of race.racers) poseKart(lookOf(r), r.kart, dt);
    world.update(dt, t, playerLook.group.position);
    if (G.state === 'title' || G.state === 'loading') {
      titleCam.a += dt * 0.12;
      const c = playerLook.group.position;
      camera.position.set(c.x + Math.sin(titleCam.a) * 18, c.y + 6, c.z + Math.cos(titleCam.a) * 18);
      camera.lookAt(c.x, c.y + 1, c.z);
      camera.fov = P.fov;
      camera.updateProjectionMatrix();
    } else if (G.state !== 'paused') {
      placeCamera(dt);
      for (const r of race.racers) lookOf(r).fx.update(dt, r.kart, t);
    }
    if (G.state === 'race' || G.state === 'countdown') {
      const st = race.standings();
      hud.updateRace({
        mode: G.mode, laps: race.laps, lap: me.lapsDone + 1, time: race.clock,
        lapTime: race.clock - me.lapStart, bestLap: bestOf(G.trackId).lap, wrongWay: G.wrongT > 1.2,
        place: st.indexOf(me) + 1,
        standings: G.mode === 'race' ? st.map((r) => ({ name: r.name, color: r.color, isPlayer: r.isPlayer })) : null,
        others: race.racers.filter((r) => !r.isPlayer).map((r) => ({ x: r.kart.x, z: r.kart.z, color: r.color })),
        tags: nameTags(),
      }, k, dt);
    }
    sfx.update(k, G.state === 'race' || G.state === 'countdown');
    renderer.render(world.scene, camera);
    hud.render();
  }

  requestAnimationFrame(frame);
  await selectTrack(G.trackId);
  window.KR = { world, G, P, start: startRace, select: selectTrack, snap: snapCamera };
}

main().catch((e) => {
  console.error(e);
  const d = document.getElementById('err');
  d.hidden = false;
  d.textContent = '載入失敗：' + (e && e.message ? e.message : e);
});
