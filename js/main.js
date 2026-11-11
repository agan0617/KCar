import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';

// 放射狀動態模糊：從消失點往外拉，中間清楚、四周糊（越快越明顯；只有高畫質才有）
const ZoomBlurShader = {
  uniforms: { tDiffuse: { value: null }, strength: { value: 0 }, center: { value: new THREE.Vector2(0.5, 0.52) } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: `uniform sampler2D tDiffuse; uniform float strength; uniform vec2 center; varying vec2 vUv;
    void main(){
      vec2 d = vUv - center;
      float amt = strength * smoothstep(0.24, 0.75, length(d)); // 車在畫面中下，0.24 以內不糊
      vec4 acc = vec4(0.0);
      for (int i = 0; i < 10; i++) { acc += texture2D(tDiffuse, vUv - d * amt * (float(i) / 9.0)); }
      gl_FragColor = acc / 10.0;
    }`,
};
import { VERSION } from './version.js';
import { P, DEFS, DEFAULTS, togglePanel, panelOpen } from './tuning.js';
import { Input } from './input.js';
import { Track } from './track.js';
import { Race, RIVALS } from './race.js';
import { TRACKS, trackById, aiLevel } from './tracks.js';
import { createWorld } from './world.js';
import { Fx, Wind } from './fx.js';
import { Hud, fmtTime } from './hud.js';
import { Sfx } from './audio.js';
import { openHelp, openKeySettings, closeDialog, onKeysChange } from './controls.js';
import { Lobby } from './net/lobby.js';
import { OnlineRace } from './net/client.js';
import { SEAT_COLORS } from './net/shared.js';
import { Recorder, Replay, ReplayBar } from './replay.js';

const STEP = 1 / 120;
const BEST_KEY = 'kcar.best.v2'; // { [賽道 id]: { lap, total } }
const TRACK_KEY = 'kcar.track';
const QUALITY_KEY = 'kcar.quality';

// 連線比賽時暫停輸入（暫停選單開著）：車照樣在跑（比賽不能停），只是放開所有鍵
const NO_INPUT = { steer: 0, throttle: 0, braking: false, driftHeld: false, jet: false, pressed: () => false };
// 連線比賽一律用預設的操控參數（server 用預設值算，client 預測要跟它一樣）；鏡頭參數不影響物理，照個人設定
const CAM_KEYS = new Set(DEFS.find(([g]) => g === '鏡頭')[1].map((i) => i[0]));

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
  // Neutral：保留原本的色相與飽和度（卡通風要鮮豔），只把過亮的地方柔和壓下來
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;

  const camera = new THREE.PerspectiveCamera(P.fov, innerWidth / innerHeight, 0.3, 5000);
  addEventListener('resize', () => {
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    if (composer) { composer.setPixelRatio(renderer.getPixelRatio()); composer.setSize(innerWidth, innerHeight); }
  });

  const world = await createWorld(renderer, (p) => { hud.showLoading(p); hud.render(); });

  // ------------------------------------------------------------ 畫質：高（MSAA＋泛光＋高解析陰影）／省電（直接畫）
  let composer = null, bloom = null, zoomBlur = null;
  let quality = store.get(QUALITY_KEY, 'high');
  function setQuality(q) {
    quality = q;
    store.set(QUALITY_KEY, q);
    const dpr = window.devicePixelRatio || 1;
    renderer.setPixelRatio(Math.min(dpr, q === 'high' ? 2 : 1.25));
    world.setShadowSize(q === 'high' ? 2048 : 1024);
    if (composer) { composer.dispose(); composer = null; bloom = null; zoomBlur = null; }
    if (q === 'high') {
      const rt = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 });
      composer = new EffectComposer(renderer, rt);
      composer.addPass(new RenderPass(world.scene, camera));
      bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth / 2, innerHeight / 2), 0.25, 0.4, 0.9);
      composer.addPass(bloom);
      zoomBlur = new ShaderPass(ZoomBlurShader);
      zoomBlur.enabled = false;
      composer.addPass(zoomBlur);
      composer.addPass(new OutputPass());
      composer.setPixelRatio(renderer.getPixelRatio());
      composer.setSize(innerWidth, innerHeight);
    }
    applyLook();
  }
  /** 依主題設曝光與泛光 */
  function applyLook() {
    const th = world.theme;
    renderer.toneMappingExposure = th.exposure ?? 1;
    if (bloom && th.bloom) [bloom.strength, bloom.radius, bloom.threshold] = th.bloom;
  }
  function draw() {
    if (composer) composer.render();
    else renderer.render(world.scene, camera);
  }
  setQuality(quality);
  // 高畫質跑不動就自動降到省電（比賽中連續 4 秒平均低於 40fps）
  const perf = { t: 0, n: 0, done: false };
  function watchFps(dt) {
    if (perf.done || quality !== 'high' || G.state !== 'race') { perf.t = 0; perf.n = 0; return; }
    perf.t += dt;
    perf.n++;
    if (perf.t >= 4) {
      if (perf.n / perf.t < 40) {
        perf.done = true;
        setQuality('low');
        hud.popup('畫面不夠順，已自動切到省電畫質（可在設定改回）', '#ffffff', 22, 3, 140);
      }
      perf.t = 0;
      perf.n = 0;
    }
  }
  // 四台車的外觀：玩家＋三位對手（換色）；Fx 各自一份
  const looks = [null, ...RIVALS].map((c) => {
    const v = world.makeKart(c);
    v.fx = new Fx(world.scene, v.group, v.parts);
    return v;
  });
  const playerLook = looks[0];
  const wind = new Wind(world.scene);
  // 連線比賽照座位挑車（座位 0～3＝Komugi 紅／Mochi 藍／Azuki 綠／Kinako 紫）
  const lookOf = (r) => (r.seat != null ? looks[r.seat] : r.isPlayer ? playerLook : looks[1 + RIVALS.findIndex((x) => x.name === r.name)]);

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

  function selectTrack(id) {
    G.loadPromise = loadTrackInner(id);
    return G.loadPromise;
  }
  /** 連線：確定已經載好這條賽道 */
  async function ensureTrack(id) {
    if (G.trackReady === id) return;
    if (G.trackId === id && G.loadPromise) { await G.loadPromise; if (G.trackReady === id) return; }
    await selectTrack(id);
  }
  async function loadTrackInner(id) {
    const seq = ++G.loadSeq;
    G.trackReady = null;
    G.trackId = id;
    G.meta = trackById(id);
    store.set(TRACK_KEY, id);
    G.state = 'loading';
    showTitle(true);
    const path = await world.loadTrack(id, (p) => { if (seq === G.loadSeq) hud.setTitleLoading(p); });
    if (seq !== G.loadSeq) return; // 載入途中又換了別條
    G.track = new Track(path);
    G.trackReady = id;
    hud.setTrack(G.track);
    applyLook();
    G.race = new Race(G.track, { mode: 'race', laps: G.meta.laps, difficulty: aiLevel(G.meta) });
    syncLooks();
    for (const v of looks) v.fx.reset();
    if (G.online) return; // 載入途中連線比賽已經開始（不該發生，保險）
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
      onOnline: () => lobby.open(),
      online: lobby.connected,
    });
  }

  const help = () => openHelp({ touch: input.isTouch });
  const settings = () => openKeySettings({
    onTuning: () => openTuning(),
    quality: { get: () => quality, set: (q) => { perf.done = true; setQuality(q); } },
  });
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
    G.race = new Race(G.track, { mode, laps: G.meta.laps, difficulty: aiLevel(G.meta) });
    syncLooks();
    for (const v of looks) v.fx.reset();
    closeReplay();
    G.rec = new Recorder(G.track, G.race.racers, { trackName: G.meta.name, laps: G.race.laps === Infinity ? 99 : G.race.laps });
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

  function openTuning() {
    if (G.online) { hud.popup('連線比賽用預設的操控參數，不能調', '#ffd23f', 26, 1.6, 120); return; }
    togglePanel(true);
  }

  function goTitle() {
    togglePanel(false);
    closeReplay();
    G.race = new Race(G.track, { mode: 'race', laps: G.meta.laps, difficulty: aiLevel(G.meta) });
    syncLooks();
    G.state = 'title';
    showTitle(false);
  }

  function pause() {
    if (G.state !== 'race' && G.state !== 'countdown') return;
    G.prevState = G.state;
    G.state = 'paused';
    hud.setRaceVisible(false, false);
    if (G.online) {
      // 連線比賽停不下來：選單蓋上去，車放開所有鍵繼續跑
      hud.showPause({ title: '選單', onResume: resume, onRestart: null, onHelp: help, onSettings: settings, homeLabel: '離開比賽', onHome: () => { closeDialog(); leaveOnline(true); } });
      return;
    }
    hud.showPause({ onResume: resume, onRestart: () => { closeDialog(); startRace(G.mode); }, onHelp: help, onSettings: settings, onHome: () => { closeDialog(); goTitle(); } });
  }
  function resume() {
    closeDialog();
    togglePanel(false);
    hud.clearOverlay();
    hud.setRaceVisible(true, input.isTouch);
    G.state = G.online ? (G.race.phase === 'race' ? 'race' : 'countdown') : G.prevState || 'race';
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
    showResult({
      mode: G.mode, track: G.meta.name, total: me.finishT ?? race.clock, laps: me.laps, bestLap, newLap, newTotal, order,
      onRetry: () => startRace(G.mode), onHome: goTitle,
    });
    if (G.mode === 'race') {
      const place = order.findIndex((o) => o.isPlayer) + 1;
      sfx.beep(place === 1 ? 1318 : 660, 0.6, 'square', 0.25);
    }
  }

  // ------------------------------------------------------------ 多人連線（大廳在 net/lobby.js、預測在 net/client.js）
  const netInfo = document.createElement('div');
  netInfo.id = 'netinfo';
  netInfo.hidden = true;
  document.body.appendChild(netInfo);
  const lobby = new Lobby({
    getTrack: () => G.trackId,
    // 房主換賽道：背景跟著換、順便先載好
    onRoomTrack: (id) => { if (!G.online && id !== G.trackId && (G.state === 'title' || G.state === 'loading')) selectTrack(id); },
    onPrep: async (m) => {
      G.prep = m;
      if (G.online) exitOnline();
      await ensureTrack(m.track);
      if (lobby.net) lobby.net.send({ t: 'loaded' });
    },
    onGo: (m) => startOnline(m),
    onSnap: (m) => { if (G.online) G.race.onSnap(m); },
    onResult: (m) => onlineResult(m),
    onDisconnect: () => {
      if (G.online) { exitOnline(); goTitle(); } else if (G.state === 'title') showTitle(false);
      hud.popup('跟 server 的連線斷了', '#ff9f6b', 30, 2.5, 120);
    },
  });

  function usePhysicsDefaults(on) {
    if (on) {
      G.savedP = { ...P };
      for (const k in DEFAULTS) if (!CAM_KEYS.has(k)) P[k] = DEFAULTS[k];
    } else if (G.savedP) {
      for (const k in G.savedP) if (!CAM_KEYS.has(k)) P[k] = G.savedP[k];
      G.savedP = null;
    }
  }

  async function startOnline(m) {
    const prep = G.prep;
    if (!prep || !lobby.net) return;
    await ensureTrack(prep.track);
    closeDialog();
    togglePanel(false);
    sfx.start();
    usePhysicsDefaults(true);
    G.online = { code: lobby.room ? lobby.room.code : '' };
    G.mode = 'race';
    G.race = new OnlineRace(G.track, lobby.net, { seats: prep.seats, laps: prep.laps, goTick: m.goTick, myId: lobby.net.id });
    closeReplay();
    G.rec = new Recorder(G.track, G.race.racers, { trackName: trackById(prep.track).name, laps: prep.laps });
    syncLooks();
    for (const v of looks) v.fx.reset();
    G.state = 'countdown';
    G.lastCount = 4;
    G.lastDist = undefined;
    G.wrongT = 0;
    acc = 0;
    hud.clearOverlay();
    hud.setRaceVisible(true, input.isTouch);
    hud.countdown('');
    snapCamera();
    netInfo.hidden = false;
  }

  /** 離開連線比賽的畫面狀態（不管連線本身） */
  function exitOnline() {
    G.online = null;
    netInfo.hidden = true;
    usePhysicsDefaults(false);
  }

  /** 選單「離開比賽」：退出房間回首頁（連線留著，首頁「多人」可以再進大廳） */
  function leaveOnline(leaveRoom) {
    if (leaveRoom) lobby.leave();
    exitOnline();
    goTitle();
  }

  function onlineResult(m) {
    if (!G.online) return;
    const race = G.race;
    exitOnline();
    G.state = 'result';
    hud.setRaceVisible(false, false);
    const myId = lobby.net ? lobby.net.id : -1;
    const order = m.order.map((o) => ({ name: o.name, color: SEAT_COLORS[o.seat], isPlayer: !o.bot && o.id === myId, t: o.t, done: o.done }));
    const mine = m.order.filter((o) => !o.bot && o.id === myId)[0];
    const laps = mine ? mine.laps : race.player.laps;
    showResult({
      mode: 'race', track: trackById(m.track).name, laps, bestLap: laps.length ? Math.min(...laps) : null, newLap: false, order,
      note: '（多人連線：成績不列入個人紀錄）',
      retryLabel: '回房間', homeLabel: '離開房間',
      onRetry: () => { goTitle(); lobby.open(); },
      onHome: () => { lobby.leave(); goTitle(); },
    });
    const place = order.findIndex((o) => o.isPlayer) + 1;
    sfx.beep(place === 1 ? 1318 : 660, 0.6, 'square', 0.25);
  }

  function onlinePhysics() {
    const race = G.race, me = race.player, k = me.kart;
    race.step(G.state === 'paused' ? NO_INPUT : input);
    if (race.phase === 'race') {
      if (G.state === 'countdown') G.state = 'race';
      if (G.prevState === 'countdown') G.prevState = 'race';
    }
    for (const e of race.lapQueue.splice(0)) {
      if (e.finished) {
        hud.popup('完賽！等其他人跑完…', '#ffd23f', 50, 3, 0);
        sfx.beep(1318, 0.4, 'square', 0.25);
      } else {
        hud.popup(`第 ${e.lap} 圈 ${fmtTime(e.time)}`, '#ffffff', 34, 1.6, -80);
        if (race.laps - e.lap === 1) hud.popup('最後一圈！', '#ffd23f', 50, 1.6, 0);
        sfx.beep(880, 0.2, 'square', 0.2);
      }
    }
    const ds = k.dist - (G.lastDist ?? k.dist);
    G.lastDist = k.dist;
    G.wrongT = me.finishT == null && ds < -0.002 && k.spd > 3 ? G.wrongT + STEP : Math.max(0, G.wrongT - STEP * 2);
    handleEvents(k);
    input.endFrame();
  }

  function updateNetInfo() {
    const race = G.race, net = lobby.net;
    if (!net) return;
    const me = race.player;
    const who = me.ctrl === 'a' && me.finishT == null ? '　電腦代駕中（按任何鍵接回）' : '';
    netInfo.textContent = `房間 ${G.online.code}　延遲 ${Math.round(net.rtt)} ms${who}`;
  }

  // ------------------------------------------------------------ 重播（replay.js：比賽中每 1/30 秒記一筆，成績頁按「重播」從頭播）
  const replayBar = new ReplayBar({
    onExit: () => exitReplay(),
    onSeek: () => { for (const v of looks) v.fx.reset(); snapCamera(); },
    onTarget: () => snapCamera(),
  });

  /** 成績頁：記下參數（重播完回來要再顯示一次），有紀錄就多一顆「重播」 */
  function showResult(args) {
    G.lastResult = args;
    hud.showResult({ ...args, onReplay: G.rec && !G.rec.empty ? startReplay : null });
  }

  function startReplay() {
    if (!G.rec || G.rec.empty) return;
    closeDialog();
    G.replay = new Replay(G.rec);
    G.state = 'replay';
    hud.clearOverlay();
    hud.setRaceVisible(false, false);
    for (const v of looks) { v.group.visible = false; v.fx.reset(); }
    for (const r of G.rec.racers) lookOf(r).group.visible = true;
    replayBar.show(G.replay);
    snapCamera();
  }

  function exitReplay() {
    closeReplay();
    G.state = 'result';
    syncLooks();
    for (const v of looks) v.fx.reset();
    if (G.lastResult) hud.showResult({ ...G.lastResult, onReplay: startReplay });
  }

  /** 收掉重播（開新比賽、回首頁時） */
  function closeReplay() {
    if (replayBar.visible) replayBar.hide();
    G.replay = null;
    if (G.state === 'replay') G.state = 'result';
  }

  /** 重播的一幀：播放時間往前、車照紀錄擺、鏡頭跟選中的那台 */
  function replayFrame(dt, t) {
    const rp = G.replay;
    const dv = rp.advance(dt);
    const k = rp.karts[rp.target];
    G.rec.racers.forEach((r, i) => {
      poseKart(lookOf(r), rp.karts[i], dv);
      lookOf(r).fx.update(dv, rp.karts[i], t);
    });
    world.update(dt, t, lookOf(G.rec.racers[rp.target]).group.position);
    placeCamera(dv || 1e-4, 0, k); // 鏡頭用重播時間追：4 倍速時才跟得上車，暫停時停住
    const f = Math.max(0, Math.min(1, (Math.abs(k.spd) / P.maxSpeed - 0.6) / 0.4));
    wind.update(dv, k, rp.playing ? Math.max(f, k.nitroT > 0 ? 1.3 : k.boostT > 0 ? 1 : 0) * P.speedFx : 0);
    sfx.update(k, rp.playing && rp.speed <= 2);
    replayBar.render(rp.ended !== G.replayEnded);
    G.replayEnded = rp.ended;
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
        case 'pad': sfx.whoosh(0.9); G.shake = Math.max(G.shake, 0.12); break;
        case 'fall': hud.popup(e.hazard ? '掉進去了！' : '掉出賽道！', '#ff9f6b', 40, 1.0, 0); break;
        case 'respawn': snapCamera(); break;
        case 'land': if (e.impact > 2.5) { sfx.bump(Math.min(12, e.impact * 0.8)); G.shake = Math.max(G.shake, Math.min(0.35, (e.impact - 2) * 0.03)); } break;
        case 'start': startBoostFx(); break;
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
    startBoostFx();
  }
  function startBoostFx() {
    hud.popup('起步噴！', '#4cd964', 46, 1.0, 0);
    sfx.whoosh(1);
  }

  // ------------------------------------------------------------ 鏡頭與車的外觀
  const tmpV = new THREE.Vector3();
  const look = new THREE.Vector3();
  const camTarget = () => (G.replay ? G.replay.karts[G.replay.target] : G.race.player.kart);
  function snapCamera() {
    const k = camTarget();
    G.camYaw = k.h;
    G.lastSpd = undefined;
    placeCamera(1, 1, k);
  }
  function placeCamera(dt, snap = 0, kk = null) {
    const k = kk || G.race.player.kart;
    const mix = k.drift ? P.camDriftMix : 0.15;
    // 鏡頭方向：主要跟速度方向（甩尾時才看得到車身打橫），一部分跟車頭
    const target = lerpAngle(k.phi, k.h, mix);
    G.camYaw = snap ? target : lerpAngle(G.camYaw, target, 1 - Math.exp(-P.camFollow * dt));
    const boost = k.nitroT > 0 ? 1 : k.boostT > 0 ? 0.6 : 0;
    // 加速感：速度往上衝時鏡頭被甩開一點（拉遠），之後慢慢追回來；噴射期間也拉遠
    const dv = snap ? 0 : (k.spd - (G.lastSpd ?? k.spd)) / Math.max(dt, 1e-3);
    G.lastSpd = k.spd;
    const kickT = Math.max(0, Math.min(1, dv / 30)) * P.camKick + boost * P.camKick;
    G.kick = snap ? 0 : (G.kick || 0) + (kickT - (G.kick || 0)) * (1 - Math.exp(-(kickT > G.kick ? 6 : 1.8) * dt));
    const dist = P.camDist + G.kick;
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
    const spd01 = Math.min(1.4, Math.abs(k.spd) / P.maxSpeed);
    // 高速細微震動（越接近極速越明顯，噴射時更強）
    const sh = P.camShake * (Math.pow(Math.min(1.2, spd01), 3) + boost * 0.8);
    if (sh > 0 && !snap) {
      camera.position.x += (Math.random() - 0.5) * sh;
      camera.position.y += (Math.random() - 0.5) * sh;
    }
    // 看向車前方較遠、較高的點：車子落在畫面下方三分之一，前方路面看得多
    look.set(k.x + fx * P.camLookAhead, k.y + P.camLookHeight, k.z + fz * P.camLookAhead);
    camera.lookAt(look);
    // 動態模糊：接近極速開始出現，噴射時最強
    if (zoomBlur) {
      const fast = Math.max(0, Math.min(1, (spd01 - 0.8) / 0.2));
      const s = (fast * 0.06 + (k.nitroT > 0 ? 0.13 : k.boostT > 0 ? 0.08 : 0)) * P.speedFx;
      const u = zoomBlur.uniforms.strength;
      u.value += (s - u.value) * (1 - Math.exp(-6 * dt));
      zoomBlur.enabled = u.value > 0.003;
    }
    // 視角隨車速放大（低速 P.fov，極速多 fovSpeed 度），噴射再加 fovBoost
    const fov = P.fov + Math.pow(Math.min(1, spd01), 1.5) * P.fovSpeed + boost * P.fovBoost;
    camera.fov += (fov - camera.fov) * (1 - Math.exp(-5 * dt));
    camera.updateProjectionMatrix();
  }

  function poseKart(v, k, dt) {
    const g = v.group, pt = v.parts;
    g.position.set(k.x, k.y, k.z);
    g.rotation.y = k.h;
    // 地形俯仰（空中車頭慢慢跟著上下速度擺）
    const pitchT = k.air ? Math.max(-0.35, Math.min(0.35, -k.vy * 0.025)) : k.pitch;
    g.rotation.x += (pitchT - g.rotation.x) * Math.min(1, dt * (k.air ? 4 : 10));
    // 懸吊：車身俯仰（加速抬頭、煞車點頭）、側傾（離心）、上下（落地壓縮）都是彈簧阻尼，會晃一下才停
    const s = v.susp || (v.susp = { p: 0, pv: 0, r: 0, rv: 0, y: 0, yv: 0, ls: k.spd, air: false, vy: 0 });
    const idt = 1 / Math.max(dt, 1e-3);
    const along = Math.max(-80, Math.min(80, (k.spd - s.ls) * idt));
    s.ls = k.spd;
    const lat = k.yawRate * Math.abs(k.spd);
    const pT = k.air ? 0 : Math.max(-0.07, Math.min(0.07, -along * 0.0028));
    const rT = Math.max(-0.14, Math.min(0.14, -lat * 0.004)) + (k.drift ? k.driftDir * 0.06 : 0);
    if (s.air && !k.air) s.yv -= Math.min(2.2, 0.35 + s.vy * 0.12); // 落地：往下壓
    if (!s.air && k.air && k.vy > 0) s.yv += 0.6; // 起跳：彈起
    s.air = k.air;
    if (k.air) s.vy = Math.max(0, -k.vy);
    const sub = Math.min(4, Math.ceil(dt / 0.005)), h = dt / sub;
    for (let i = 0; i < sub; i++) {
      s.pv += ((pT - s.p) * 220 - s.pv * 13) * h; s.p += s.pv * h;
      s.rv += ((rT - s.r) * 160 - s.rv * 11) * h; s.r += s.rv * h;
      s.yv += (-s.y * 260 - s.yv * 12) * h; s.y += s.yv * h;
    }
    s.y = Math.max(-0.22, Math.min(0.18, s.y));
    // 路面側傾（傾斜彎）：模型的 +x 是車的左手邊，右側高要往負方向轉
    v.bank = (v.bank || 0) + (-(k.roll || 0) - (v.bank || 0)) * Math.min(1, dt * 12);
    g.rotation.z = v.bank + s.r * 0.35;
    pt.model.rotation.z = s.r * 0.65;
    pt.model.rotation.x = s.p;
    pt.model.scale.y = 1 + Math.max(-0.12, Math.min(0.08, s.y * 0.6));
    pt.model.position.y = s.y + ((k.onGrass || k.onCurb) && !k.air && Math.abs(k.spd) > 3 ? (Math.random() - 0.5) * 0.06 : 0);
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
    if (input.pressed('tuning')) { if (G.online) openTuning(); else togglePanel(); }
    if (input.pressed('pause')) {
      if (G.state === 'paused') resume();
      else if (panelOpen()) togglePanel(false);
      else pause();
    }
    if (!G.race) { input.endFrame(); hud.render(); return; }
    if (G.state === 'replay' && G.replay) {
      input.endFrame();
      replayFrame(dt, t);
      draw();
      hud.render();
      return;
    }

    if (G.online) {
      // 連線：照 server 回報的輸入排隊長度微調快慢（rate 0.97～1.03），自己的車預測、對手前推
      acc += dt * G.race.rate;
      while (acc >= STEP && G.online) { onlinePhysics(); acc -= STEP; }
      if (G.online) {
        G.race.updateView(dt);
        G.race.flush();
        if ((G.netT = (G.netT || 0) + dt) > 0.5) { G.netT = 0; updateNetInfo(); }
      }
    } else if (G.state === 'countdown' || G.state === 'race') {
      acc += dt;
      while (acc >= STEP && (G.state === 'countdown' || G.state === 'race')) { physics(STEP); acc -= STEP; }
    } else {
      input.endFrame();
      acc = 0;
    }

    // 重播紀錄：比賽進行中（連線的選單開著也算，比賽沒停）每 1/30 秒記一筆
    if (G.rec && (G.state === 'countdown' || G.state === 'race' || (G.online && G.state === 'paused'))) G.rec.tick(dt, G.race.clock);
    if (G.state === 'countdown') {
      const n = Math.ceil(G.online ? G.race.countLeft : G.countT);
      if (n !== G.lastCount && n >= 1 && n <= 3) { G.lastCount = n; sfx.beep(523, 0.18, 'square', 0.22); }
      hud.countdown(n >= 1 ? String(n) : '');
    } else if (G.state === 'race' && G.race.clock < 0.8) {
      if (G.lastCount !== 0) { G.lastCount = 0; sfx.beep(1046, 0.4, 'square', 0.25); }
      hud.countdown('GO!', '#4cd964');
    } else hud.countdown('');

    const race = G.race, me = race.player, k = me.kart;
    for (const r of race.racers) poseKart(lookOf(r), r.kart, dt);
    const meLook = lookOf(me);
    world.update(dt, t, meLook.group.position);
    if (G.state === 'title' || G.state === 'loading') {
      titleCam.a += dt * 0.12;
      const c = meLook.group.position;
      camera.position.set(c.x + Math.sin(titleCam.a) * 18, c.y + 6, c.z + Math.cos(titleCam.a) * 18);
      camera.lookAt(c.x, c.y + 1, c.z);
      camera.fov = P.fov;
      camera.updateProjectionMatrix();
    } else if (G.state !== 'paused' || G.online) {
      placeCamera(dt);
      for (const r of race.racers) lookOf(r).fx.update(dt, r.kart, t);
      // 風線：過了六成極速才出現，越快越濃；噴射時最濃
      const f = Math.max(0, Math.min(1, (Math.abs(k.spd) / P.maxSpeed - 0.6) / 0.4));
      wind.update(dt, k, Math.max(f, k.nitroT > 0 ? 1.3 : k.boostT > 0 ? 1 : 0) * P.speedFx);
    } else {
      wind.update(dt, k, 0);
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
    sfx.update(k, G.state === 'race' || G.state === 'countdown' || !!G.online);
    watchFps(dt);
    draw();
    hud.render();
  }

  requestAnimationFrame(frame);
  await selectTrack(G.trackId);
  // 從 GitHub Pages／App 轉到 server 的網頁（網址帶 #mp=名字）：直接打開大廳連這台 server
  if (location.hash.startsWith('#mp=')) {
    const name = decodeURIComponent(location.hash.slice(4));
    history.replaceState(null, '', location.pathname + location.search);
    lobby.autoConnect(name);
  }
  window.KR = { world, G, P, start: startRace, select: selectTrack, snap: snapCamera, lobby };
}

main().catch((e) => {
  console.error(e);
  const d = document.getElementById('err');
  d.hidden = false;
  d.textContent = '載入失敗：' + (e && e.message ? e.message : e);
});
