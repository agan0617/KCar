import * as THREE from 'three';
import { VERSION } from './version.js';
import { P, togglePanel, panelOpen } from './tuning.js';
import { Input } from './input.js';
import { Track } from './track.js';
import { Kart } from './kart.js';
import { createWorld } from './world.js';
import { Fx } from './fx.js';
import { Hud, fmtTime } from './hud.js';
import { Sfx } from './audio.js';

const LAPS = 3;
const STEP = 1 / 120;
const BEST_KEY = 'kracer.best.v1';

const lerpAngle = (a, b, t) => {
  let d = b - a;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return a + d * t;
};

function loadBest() {
  try { return JSON.parse(localStorage.getItem(BEST_KEY)) || {}; } catch (e) { return {}; }
}
function saveBest(b) {
  try { localStorage.setItem(BEST_KEY, JSON.stringify(b)); } catch (e) { /* 忽略 */ }
}

async function main() {
  const input = new Input();
  const sfx = new Sfx();
  const hud = await Hud.create(document.getElementById('ui'), input);
  hud.showLoading(0);
  hud.render();

  const renderer = new THREE.WebGLRenderer({ canvas: document.getElementById('game'), antialias: true, powerPreference: 'high-performance' });
  const mobile = input.isTouch;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, mobile ? 1.5 : 2));
  renderer.setSize(innerWidth, innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const camera = new THREE.PerspectiveCamera(P.fov, innerWidth / innerHeight, 0.3, 5000);
  addEventListener('resize', () => {
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
  });

  const world = await createWorld(renderer, (p) => { hud.showLoading(p); hud.render(); });
  const track = new Track(world.path);
  const kart = new Kart(track);
  const fx = new Fx(world.scene, world.kart, world.parts);

  // ------------------------------------------------------------ 狀態
  const G = {
    state: 'title', // title | countdown | race | paused | result
    mode: 'race',
    clock: 0, // 比賽計時（GO 之後）
    countT: 0,
    lapStart: 0,
    laps: [],
    lapsDone: 0,
    best: loadBest(),
    camYaw: 0,
    camPos: new THREE.Vector3(),
    shake: 0,
    wrongT: 0,
    goAt: 0,
    startBoostUsed: false,
  };

  function startRace(mode) {
    sfx.start();
    G.mode = mode;
    G.state = 'countdown';
    G.countT = 3.0;
    G.clock = 0;
    G.laps = [];
    G.lapsDone = 0;
    G.startBoostUsed = false;
    G.pendingStart = false;
    G.lastCount = 4;
    G.lastDist = undefined;
    G.wrongT = 0;
    kart.resetRace(track.length - 8, 0);
    kart.events.length = 0;
    fx.reset();
    hud.clearOverlay();
    hud.setRaceVisible(true, input.isTouch);
    hud.countdown('');
    snapCamera();
  }

  function goTitle() {
    G.state = 'title';
    hud.setRaceVisible(false, false);
    hud.countdown('');
    kart.resetRace(track.length - 8, 0);
    hud.showTitle({ version: VERSION, best: G.best, touch: input.isTouch, onStart: startRace });
  }

  function pause() {
    if (G.state !== 'race' && G.state !== 'countdown') return;
    G.prevState = G.state;
    G.state = 'paused';
    hud.setRaceVisible(false, false);
    hud.showPause({
      onResume: resume,
      onRestart: () => startRace(G.mode),
      onTuning: () => togglePanel(true),
      onHome: goTitle,
    });
  }
  function resume() {
    togglePanel(false);
    hud.clearOverlay();
    hud.setRaceVisible(true, input.isTouch);
    G.state = G.prevState || 'race';
  }
  hud.onPause = pause;
  // 切到別的 App／分頁就自動暫停（手機接電話、按返回鍵）
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });

  function finish() {
    G.state = 'result';
    hud.setRaceVisible(false, false);
    const bestLap = Math.min(...G.laps);
    const newLap = !(G.best.lap <= bestLap);
    if (newLap) G.best.lap = bestLap;
    let newTotal = false;
    if (G.mode === 'race') {
      newTotal = !(G.best.total <= G.clock);
      if (newTotal) G.best.total = G.clock;
    }
    saveBest(G.best);
    hud.showResult({
      mode: G.mode, total: G.clock, laps: G.laps, bestLap, newLap, newTotal,
      onRetry: () => startRace(G.mode), onHome: goTitle,
    });
  }

  // ------------------------------------------------------------ 事件 → 畫面／聲音回饋
  function handleEvents() {
    for (const e of kart.events) {
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
        default: break;
      }
    }
    kart.events.length = 0;
  }

  // ------------------------------------------------------------ 每個物理步
  function physics(dt) {
    if (G.state === 'countdown') {
      G.countT -= dt;
      // 起步噴：GO 前 0.25 秒到 GO 後 0.2 秒之間按下 ↑／噴
      if (input.jet && !G.startBoostUsed && G.countT < 0.25) {
        G.startBoostUsed = true;
        G.pendingStart = true;
      } else if (input.jet && G.countT >= 0.25) G.startBoostUsed = true; // 太早按就沒了
      kart.step(dt, input, false);
      if (G.countT <= 0) {
        G.state = 'race';
        G.clock = 0;
        G.lapStart = 0;
        G.goAt = 0;
        if (G.pendingStart) { kart.addBoost(P.startBoost, 1.0, 'start'); hud.popup('起步噴！', '#4cd964', 46, 1.0, 0); sfx.whoosh(1); }
        G.pendingStart = false;
      }
    } else if (G.state === 'race') {
      G.clock += dt;
      if (input.jet && !G.startBoostUsed && G.clock < 0.2) {
        G.startBoostUsed = true;
        kart.addBoost(P.startBoost, 1.0, 'start');
        hud.popup('起步噴！', '#4cd964', 46, 1.0, 0);
        sfx.whoosh(1);
      }
      kart.step(dt, input, true);
      if (input.pressed('reset')) kart.respawn();
      // 圈數
      const lapsNow = Math.floor(kart.dist / track.length);
      if (lapsNow > G.lapsDone) {
        G.lapsDone = lapsNow;
        const lt = G.clock - G.lapStart;
        G.laps.push(lt);
        G.lapStart = G.clock;
        const isBest = !(G.best.lap <= lt);
        if (G.mode === 'race' && G.lapsDone >= LAPS) { sfx.beep(1046, 0.5, 'square', 0.25); finish(); }
        else {
          hud.popup(`第 ${G.lapsDone} 圈 ${fmtTime(lt)}${isBest ? ' ★' : ''}`, '#ffffff', 34, 1.6, -80);
          if (G.mode === 'race' && G.lapsDone === LAPS - 1) hud.popup('最後一圈！', '#ffd23f', 50, 1.6, 0);
          if (G.mode === 'free' && isBest) { G.best.lap = lt; saveBest(G.best); }
          sfx.beep(880, 0.2, 'square', 0.2);
        }
      }
      // 逆向偵測
      const ds = kart.dist - (G.lastDist ?? kart.dist);
      G.lastDist = kart.dist;
      G.wrongT = ds < -0.002 && kart.spd > 3 ? G.wrongT + dt : Math.max(0, G.wrongT - dt * 2);
    }
    handleEvents();
    input.endFrame();
  }

  // ------------------------------------------------------------ 鏡頭與車的外觀
  const tmpV = new THREE.Vector3();
  const look = new THREE.Vector3();
  function snapCamera() {
    G.camYaw = kart.h;
    placeCamera(1, 1);
  }
  function placeCamera(dt, snap = 0) {
    const mix = kart.drift ? P.camDriftMix : 0.15;
    // 鏡頭方向：主要跟速度方向（甩尾時才看得到車身打橫），一部分跟車頭
    const target = lerpAngle(kart.phi, kart.h, mix);
    G.camYaw = snap ? target : lerpAngle(G.camYaw, target, 1 - Math.exp(-P.camFollow * dt));
    const boost = kart.nitroT > 0 ? 1 : kart.boostT > 0 ? 0.6 : 0;
    const dist = P.camDist + boost * 0.9;
    const fx = Math.sin(G.camYaw), fz = Math.cos(G.camYaw);
    tmpV.set(kart.x - fx * dist, kart.y + P.camHeight, kart.z - fz * dist);
    if (snap) G.camPos.copy(tmpV);
    else {
      const k = 1 - Math.exp(-12 * dt);
      G.camPos.x += (tmpV.x - G.camPos.x) * k;
      G.camPos.z += (tmpV.z - G.camPos.z) * k;
      G.camPos.y += (tmpV.y - G.camPos.y) * (1 - Math.exp(-6 * dt));
    }
    camera.position.copy(G.camPos);
    if (G.shake > 0) {
      camera.position.x += (Math.random() - 0.5) * G.shake;
      camera.position.y += (Math.random() - 0.5) * G.shake;
      G.shake = Math.max(0, G.shake - dt * 1.8);
    }
    look.set(kart.x + fx * 4, kart.y + 1.1, kart.z + fz * 4);
    camera.lookAt(look);
    const spd01 = Math.min(1.4, Math.abs(kart.spd) / P.maxSpeed);
    const fov = P.fov + spd01 * 4 + boost * P.fovBoost;
    camera.fov += (fov - camera.fov) * (1 - Math.exp(-5 * dt));
    camera.updateProjectionMatrix();
  }

  let roll = 0, lean = 0, wheelSpin = 0, bob = 0;
  function poseKart(dt, t) {
    const g = world.kart, pt = world.parts;
    g.position.set(kart.x, kart.y, kart.z);
    g.rotation.y = kart.h;
    g.rotation.x += (kart.pitch - g.rotation.x) * Math.min(1, dt * 10);
    // 側傾：轉彎時往外傾；甩尾時多一點
    const lat = kart.yawRate * Math.abs(kart.spd);
    const targetRoll = Math.max(-0.12, Math.min(0.12, -lat * 0.0035)) + (kart.drift ? kart.driftDir * 0.05 : 0);
    roll += (targetRoll - roll) * Math.min(1, dt * 8);
    g.rotation.z = roll;
    // 草地與路緣石震動
    bob = (kart.onGrass || kart.onCurb) && Math.abs(kart.spd) > 3 ? (Math.random() - 0.5) * 0.06 : 0;
    pt.model.position.y = bob;
    // 駕駛往彎內側倒
    lean += ((kart.drift ? -kart.driftDir * 0.22 : -kart.steer * 0.12) - lean) * Math.min(1, dt * 8);
    if (pt.driver) pt.driver.rotation.z = lean;
    // 輪子
    wheelSpin += kart.spd * dt / 0.31;
    const steerVis = kart.drift ? -kart.driftDir * 0.25 + kart.steer * 0.15 : kart.steer * 0.42;
    pt.wheels.forEach((w, i) => {
      if (!w) return;
      w.rotation.x = wheelSpin;
      if (i < 2) w.rotation.y = -steerVis;
    });
  }

  // ------------------------------------------------------------ 主迴圈
  let last = performance.now(), acc = 0, t = 0;
  const titleCam = { a: 0 };
  function frame(now) {
    requestAnimationFrame(frame);
    let dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    t += dt;

    if (input.pressed('tuning')) togglePanel();
    if (input.pressed('pause')) {
      if (G.state === 'paused') resume();
      else if (panelOpen()) togglePanel(false);
      else pause();
    }

    if (G.state === 'countdown' || G.state === 'race') {
      acc += dt;
      while (acc >= STEP) { physics(STEP); acc -= STEP; }
    } else {
      input.endFrame();
      acc = 0;
    }

    // 倒數顯示
    if (G.state === 'countdown') {
      const n = Math.ceil(G.countT);
      if (n !== G.lastCount && n >= 1 && n <= 3) { G.lastCount = n; sfx.beep(523, 0.18, 'square', 0.22); }
      hud.countdown(n >= 1 ? String(n) : '');
    } else if (G.state === 'race' && G.clock < 0.8) {
      if (G.lastCount !== 0) { G.lastCount = 0; sfx.beep(1046, 0.4, 'square', 0.25); }
      hud.countdown('GO!', '#4cd964');
    } else hud.countdown('');

    poseKart(dt, t);
    world.update(dt, t, world.kart.position);
    if (G.state === 'title') {
      // 首頁：鏡頭繞著起跑線慢慢轉
      titleCam.a += dt * 0.12;
      const c = world.kart.position;
      camera.position.set(c.x + Math.sin(titleCam.a) * 16, c.y + 5.5, c.z + Math.cos(titleCam.a) * 16);
      camera.lookAt(c.x, c.y + 1, c.z);
      camera.fov = P.fov;
      camera.updateProjectionMatrix();
    } else if (G.state !== 'paused') {
      placeCamera(dt);
      fx.update(dt, kart, t);
    }
    if (G.state === 'race' || G.state === 'countdown') {
      hud.updateRace({
        mode: G.mode, laps: LAPS, lap: G.lapsDone + 1, time: G.clock,
        lapTime: G.clock - G.lapStart, bestLap: G.best.lap, wrongWay: G.wrongT > 1.2,
      }, kart, dt);
    }
    sfx.update(kart, G.state === 'race' || G.state === 'countdown');
    renderer.render(world.scene, camera);
    hud.render();
  }

  goTitle();
  requestAnimationFrame(frame);
  // 讓 dev 時方便在主控台看狀態
  window.KR = { kart, track, world, G, P, start: startRace };
}

main().catch((e) => {
  console.error(e);
  const d = document.getElementById('err');
  d.hidden = false;
  d.textContent = '載入失敗：' + (e && e.message ? e.message : e);
});
