// 3D 場景：載入 Blender 產的 GLB，換成卡通材質（toon），依賽道主題換天空、霧、燈光、路面與地面紋理。
// 卡丁車模型只載一次，四台車用 clone＋換色。

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { THEMES } from './themes.js';

function canvasTex(w, h, draw) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

function rand(seed) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

// 路面：u 橫跨路寬（0..1），v 沿路每 8 公尺一個循環
function roadTexture(th) {
  const r = th.road;
  return canvasTex(512, 512, (g, w, h) => {
    g.fillStyle = r.base;
    g.fillRect(0, 0, w, h);
    const rnd = rand(7);
    for (let i = 0; i < 9000; i++) {
      const v = r.speck[0] + rnd() * (r.speck[1] - r.speck[0]);
      g.fillStyle = `rgba(${v},${v + 4},${v + 14},${0.25 + rnd() * 0.3})`;
      g.fillRect(rnd() * w, rnd() * h, 1 + rnd() * 2, 1 + rnd() * 2);
    }
    g.fillStyle = r.edge;
    g.fillRect(w * 0.022, 0, w * 0.022, h);
    g.fillRect(w * 0.956, 0, w * 0.022, h);
    g.fillStyle = r.center;
    g.fillRect(w * 0.494, 0, w * 0.012, h * 0.5);
  });
}

function groundTexture(th) {
  const gr = th.ground;
  return canvasTex(256, 256, (g, w, h) => {
    g.fillStyle = gr.base;
    g.fillRect(0, 0, w, h);
    const rnd = rand(11);
    for (let i = 0; i < 2600; i++) {
      const k = rnd();
      g.fillStyle = gr.dots[k < 0.5 ? 0 : k < 0.85 ? 1 : 2];
      if (gr.blade) g.fillRect(rnd() * w, rnd() * h, 2, 3 + rnd() * 4);
      else g.fillRect(rnd() * w, rnd() * h, 2 + rnd() * 3, 2 + rnd() * 3);
    }
  });
}

function disposeTree(obj) {
  obj.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    const ms = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
    for (const m of ms) m.dispose();
  });
}

const NO_SHADOW = new Set(['Road', 'Ground', 'Water', 'Ice', 'Lava', 'Cloud', 'AshCloud', 'CurbA', 'CurbB', 'CheckBlack', 'CheckWhite']);
// 換色用：卡丁車材質名稱 → 對手設定的欄位
const RECOLOR = { KartRed: 'kart', Hoodie: 'hoodie', ShibaFur: 'fur', ShibaCream: 'cream' };

export async function createWorld(renderer, onProgress = () => {}) {
  const scene = new THREE.Scene();
  const skyU = {
    top: { value: new THREE.Color() }, bottom: { value: new THREE.Color() },
    sunDir: { value: new THREE.Vector3(0, 1, 0) }, sunCol: { value: new THREE.Color() }, sunAmt: { value: 1 },
  };
  // 天空：上下漸層＋太陽（月亮）光暈；亮度超過 1 的部分會被泛光吃到
  const sky = new THREE.Mesh(
    new THREE.SphereGeometry(2400, 32, 16),
    new THREE.ShaderMaterial({
      side: THREE.BackSide, depthWrite: false, fog: false, uniforms: skyU,
      vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: `uniform vec3 top; uniform vec3 bottom; uniform vec3 sunDir; uniform vec3 sunCol; uniform float sunAmt; varying vec3 vP;
        void main(){
          vec3 d = normalize(vP);
          float t = pow(clamp(d.y*1.6+0.02,0.0,1.0),0.7);
          vec3 c = mix(bottom, top, t);
          float s = max(dot(d, sunDir), 0.0);
          c += sunCol * (pow(s, 900.0) * 6.0 + pow(s, 24.0) * 0.35) * sunAmt;
          gl_FragColor = vec4(c, 1.0);
        }`,
    }),
  );
  sky.renderOrder = -1;
  scene.add(sky);
  scene.fog = new THREE.Fog(0xffffff, 400, 1500);

  const hemi = new THREE.HemisphereLight();
  scene.add(hemi);
  const sun = new THREE.DirectionalLight();
  const sunDir = new THREE.Vector3();
  sun.castShadow = true;
  const mobile = matchMedia('(pointer: coarse)').matches;
  sun.shadow.mapSize.set(mobile ? 1024 : 2048, mobile ? 1024 : 2048);
  const sc = sun.shadow.camera;
  sc.left = -45; sc.right = 45; sc.top = 45; sc.bottom = -45; sc.near = 10; sc.far = 260;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.03;
  scene.add(sun, sun.target);
  // 夜間賽道：跟著車的補光（像路燈照到車上），白天關掉
  const carLight = new THREE.PointLight('#ffe2b8', 0, 18, 1.6);
  scene.add(carLight);

  const loader = new GLTFLoader();
  const maxAniso = renderer.capabilities.getMaxAnisotropy();
  let tex = { road: null, ground: null };
  let cache = new Map();

  // 環境光照（PBR 材質的反射、柔和的補光）：用這條賽道自己的天空顏色做（夜城反射夜空、火山反射紅天），
  // 不用 three 內建的攝影棚環境——那裡面的燈板太亮，車身反射到會整片發白
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envU = { top: { value: new THREE.Color() }, mid: { value: new THREE.Color() }, bottom: { value: new THREE.Color() }, sunDir: { value: new THREE.Vector3() }, sunCol: { value: new THREE.Color() } };
  const envScene = new THREE.Scene();
  envScene.add(new THREE.Mesh(new THREE.SphereGeometry(10, 32, 16), new THREE.ShaderMaterial({
    side: THREE.BackSide, uniforms: envU,
    vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: `uniform vec3 top; uniform vec3 mid; uniform vec3 bottom; uniform vec3 sunDir; uniform vec3 sunCol; varying vec3 vP;
      void main(){ vec3 d = normalize(vP);
        vec3 c = d.y > 0.0 ? mix(mid, top, pow(d.y, 0.6)) : mix(mid, bottom, pow(-d.y, 0.4));
        c += sunCol * pow(max(dot(d, sunDir), 0.0), 64.0) * 1.5;
        gl_FragColor = vec4(c, 1.0); }`,
  })));
  let envTex = null;
  function makeEnv(th) {
    envU.top.value.set(th.skyTop);
    envU.mid.value.set(th.horizon);
    envU.bottom.value.set(th.hemi[1]);
    envU.sunDir.value.set(...th.sunDir).normalize();
    envU.sunCol.value.set(th.sun[0]).multiplyScalar(th.night ? 0.2 : 1);
    if (envTex) envTex.dispose();
    envTex = pmrem.fromScene(envScene, 0.02).texture;
    scene.environment = envTex;
  }

  // 車身烤漆：亮面＋透明漆層
  const PAINT = new Set(['KartRed', 'KartWhite', 'KartYellow', 'Hoodie', 'HeadphoneAccent']);

  /** Blender 匯出的材質 → 遊戲用材質（PBR；水、熔岩、雲另外做） */
  function pbr(m) {
    if (cache.has(m)) return cache.get(m);
    let out;
    const name = m.name || '';
    if (name === 'Water') {
      out = new THREE.MeshStandardMaterial({ color: '#1f9be0', roughness: 0.06, metalness: 0.0, transparent: true, opacity: 0.86 });
    } else if (name === 'Ice') {
      out = new THREE.MeshStandardMaterial({ color: '#d4efff', roughness: 0.04, metalness: 0.15 });
    } else if (name === 'Lava') {
      out = new THREE.MeshBasicMaterial({ color: '#ff5a1f' });
    } else if (name === 'Cloud' || name === 'AshCloud') {
      out = new THREE.MeshStandardMaterial({ color: m.color, roughness: 1, emissive: name === 'Cloud' ? '#dfe9f5' : '#000000', emissiveIntensity: 0.55, fog: false });
    } else if (PAINT.has(name)) {
      out = new THREE.MeshPhysicalMaterial({ color: m.color, roughness: 0.32, metalness: 0.05, clearcoat: 1, clearcoatRoughness: 0.08 });
    } else {
      out = m; // GLTFLoader 已經是 MeshStandardMaterial（顏色、粗糙度、金屬度、自發光都照 Blender）
      if (name === 'Road') { out.map = tex.road; out.color.set('#ffffff'); out.roughness = 0.88; }
      if (name === 'Ground') { out.map = tex.ground; out.color.set('#ffffff'); out.roughness = 1; }
      if (/^Curb/.test(name)) out.roughness = 0.55;
      if (out.emissiveIntensity > 0 && out.emissive && out.emissive.getHex() !== 0) out.emissiveIntensity = Math.min(1.6, out.emissiveIntensity);
    }
    out.name = name;
    cache.set(m, out);
    return out;
  }
  const toon = pbr; // 舊名稱（下面沿用）

  // ---------------------------------------------------------- 卡丁車
  const kartG = await loader.loadAsync('assets/kart.glb');
  onProgress(0.15);
  const kartTemplate = kartG.scene;
  const kartMats = new Map();
  kartTemplate.traverse((o) => {
    if (o.isMesh) {
      o.material = Array.isArray(o.material) ? o.material.map(toon) : toon(o.material);
      o.castShadow = true;
      o.receiveShadow = true;
    }
  });
  cache = new Map(); // 卡丁車材質留著（換賽道不能丟），之後的賽道另開快取
  void kartMats;

  /** colors：對手設定（kart/hoodie/fur/cream），不給就是 Komugi 原色 */
  function makeKart(colors) {
    const model = kartTemplate.clone(true);
    if (colors) {
      const own = new Map();
      model.traverse((o) => {
        if (!o.isMesh) return;
        const swap = (m) => {
          const key = RECOLOR[m.name];
          if (!key || !colors[key]) return m;
          if (!own.has(m)) { const c = m.clone(); c.color.set(colors[key]); own.set(m, c); }
          return own.get(m);
        };
        o.material = Array.isArray(o.material) ? o.material.map(swap) : swap(o.material);
      });
    }
    const group = new THREE.Group();
    group.add(model);
    group.rotation.order = 'YXZ';
    const parts = {
      model,
      driver: model.getObjectByName('Driver'),
      wheels: ['FL', 'FR', 'RL', 'RR'].map((k) => model.getObjectByName('Wheel_' + k)),
      exhaust: ['Exhaust_L', 'Exhaust_R'].map((k) => model.getObjectByName(k)),
    };
    for (const w of parts.wheels) if (w) w.rotation.order = 'YXZ';
    scene.add(group);
    return { group, parts, roll: 0, lean: 0, spin: 0 };
  }

  // ---------------------------------------------------------- 賽道
  let trackObj = null;
  const anim = { spinZ: [], spinY: [], bob: [], clouds: null, lava: [] };
  let theme = THEMES.hills;

  function applyTheme(th) {
    theme = th;
    skyU.top.value.set(th.skyTop);
    skyU.bottom.value.set(th.horizon);
    scene.background = new THREE.Color(th.horizon);
    scene.fog.color.set(th.horizon);
    scene.fog.near = th.fog[0];
    scene.fog.far = th.fog[1];
    hemi.color.set(th.hemi[0]);
    hemi.groundColor.set(th.hemi[1]);
    hemi.intensity = th.hemi[2] * 0.75; // PBR 另有環境光照補光，天空光減半免得整片發白
    sun.color.set(th.sun[0]);
    sun.intensity = th.sun[1];
    sunDir.set(...th.sunDir).normalize();
    skyU.sunDir.value.copy(sunDir);
    skyU.sunCol.value.set(th.sun[0]);
    skyU.sunAmt.value = th.night ? 0.35 : 1;
    makeEnv(th);
    carLight.intensity = th.night ? 60 : 0;
    scene.environmentIntensity = th.env ?? 0.55;
    for (const k of ['road', 'ground']) if (tex[k]) tex[k].dispose();
    tex = { road: roadTexture(th), ground: groundTexture(th) };
    tex.road.anisotropy = maxAniso;
    tex.ground.anisotropy = Math.min(8, maxAniso);
  }

  async function loadTrack(id, progress = () => {}) {
    const [g, path] = await Promise.all([
      loader.loadAsync(`assets/${id}.glb`, (e) => { if (e.total) progress(e.loaded / e.total); }),
      fetch(`assets/${id}_path.json`).then((r) => r.json()),
    ]);
    if (trackObj) { scene.remove(trackObj); disposeTree(trackObj); }
    for (const m of cache.values()) m.dispose();
    cache = new Map();
    applyTheme(THEMES[path.theme] || THEMES.hills);
    anim.spinZ = []; anim.spinY = []; anim.bob = []; anim.clouds = null; anim.lava = [];
    g.scene.traverse((o) => {
      if (o.isMesh) {
        o.material = Array.isArray(o.material) ? o.material.map(toon) : toon(o.material);
        const nm = o.material.name;
        o.receiveShadow = nm !== 'Cloud';
        o.castShadow = !NO_SHADOW.has(nm) && !/^Mountain|^Snow$|^Island/.test(nm);
        if (nm === 'Ground' && !o.geometry.attributes.uv) {
          // 地形沒存 UV：用世界座標每 8 公尺一格
          const pos = o.geometry.attributes.position;
          const uv = new Float32Array(pos.count * 2);
          for (let i = 0; i < pos.count; i++) { uv[i * 2] = pos.getX(i) / 8; uv[i * 2 + 1] = pos.getZ(i) / 8; }
          o.geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
        }
        if (nm === 'Lava') anim.lava.push(o.material);
      }
      if (/^Spin_Windmill/.test(o.name)) anim.spinZ.push(o);
      else if (/^Spin_/.test(o.name)) anim.spinY.push(o);
      if (/^Bob_/.test(o.name)) anim.bob.push({ o, y: o.position.y, ph: Math.random() * 6 });
      if (o.name === 'Clouds') anim.clouds = o;
    });
    trackObj = g.scene;
    scene.add(trackObj);
    return path;
  }

  function update(dt, t, focus) {
    for (const o of anim.spinZ) o.rotation.z += dt * 0.9;
    for (const o of anim.spinY) o.rotation.y += dt * 0.05;
    for (const b of anim.bob) b.o.position.y = b.y + Math.sin(t * 0.5 + b.ph) * 2.5;
    if (anim.clouds) anim.clouds.rotation.y += dt * 0.004;
    for (const m of anim.lava) m.color.setHSL(0.04 + Math.sin(t * 1.3) * 0.015, 1, 0.5 + Math.sin(t * 2.1) * 0.06);
    // 陰影相機跟著車走（貼齊格點避免陰影閃爍）
    const snap = 2;
    const fx = Math.round(focus.x / snap) * snap, fz = Math.round(focus.z / snap) * snap;
    sun.target.position.set(fx, focus.y, fz);
    sun.position.set(fx + sunDir.x * 120, focus.y + sunDir.y * 120, fz + sunDir.z * 120);
    sky.position.copy(focus);
    carLight.position.set(focus.x, focus.y + 4, focus.z);
  }

  function setShadowSize(n) {
    if (sun.shadow.mapSize.x === n) return;
    sun.shadow.mapSize.set(n, n);
    if (sun.shadow.map) { sun.shadow.map.dispose(); sun.shadow.map = null; }
  }

  return { scene, makeKart, loadTrack, update, setShadowSize, get theme() { return theme; } };
}
