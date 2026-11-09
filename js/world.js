// 3D 場景：載入 Blender 產的 GLB，換成卡通材質（toon），加天空、光影、程式畫的路面與草地紋理。

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const SKY_TOP = new THREE.Color('#3d9bff');
const SKY_HORIZON = new THREE.Color('#d9f1ff');

function canvasTex(w, h, draw, repeat = true) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  if (repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

function rand(seed) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

// 路面：u 橫跨路寬（0..1），v 沿路每 8 公尺一個循環
function roadTexture() {
  return canvasTex(512, 512, (g, w, h) => {
    g.fillStyle = '#6a7080';
    g.fillRect(0, 0, w, h);
    const r = rand(7);
    for (let i = 0; i < 9000; i++) {
      const v = 90 + r() * 50;
      g.fillStyle = `rgba(${v},${v + 4},${v + 14},${0.25 + r() * 0.3})`;
      g.fillRect(r() * w, r() * h, 1 + r() * 2, 1 + r() * 2);
    }
    // 兩側白線
    g.fillStyle = '#f4f4f4';
    g.fillRect(w * 0.022, 0, w * 0.022, h);
    g.fillRect(w * 0.956, 0, w * 0.022, h);
    // 中央虛線（每 8m 一段 4m）
    g.fillStyle = 'rgba(255,255,255,0.85)';
    g.fillRect(w * 0.494, 0, w * 0.012, h * 0.5);
  });
}

function grassTexture() {
  return canvasTex(256, 256, (g, w, h) => {
    g.fillStyle = '#7ccf52';
    g.fillRect(0, 0, w, h);
    const r = rand(11);
    for (let i = 0; i < 2600; i++) {
      const k = r();
      g.fillStyle = k < 0.5 ? 'rgba(90,170,60,0.55)' : k < 0.85 ? 'rgba(150,220,95,0.5)' : 'rgba(70,140,50,0.6)';
      const x = r() * w, y = r() * h;
      g.fillRect(x, y, 2, 3 + r() * 4);
    }
  });
}

function gradientMap() {
  const data = new Uint8Array([120, 120, 120, 255, 200, 200, 200, 255, 255, 255, 255, 255]);
  const t = new THREE.DataTexture(data, 3, 1, THREE.RGBAFormat);
  t.minFilter = t.magFilter = THREE.NearestFilter;
  t.needsUpdate = true;
  return t;
}

export async function createWorld(renderer, onProgress = () => {}) {
  const scene = new THREE.Scene();
  scene.background = SKY_HORIZON.clone();
  scene.fog = new THREE.Fog(SKY_HORIZON.clone(), 380, 1500);

  // 天空：漸層球
  const sky = new THREE.Mesh(
    new THREE.SphereGeometry(2400, 32, 16),
    new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      fog: false,
      uniforms: { top: { value: SKY_TOP }, bottom: { value: SKY_HORIZON } },
      vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: 'uniform vec3 top; uniform vec3 bottom; varying vec3 vP; void main(){ float h = normalize(vP).y; float t = pow(clamp(h*1.6+0.02,0.0,1.0),0.7); gl_FragColor = vec4(mix(bottom, top, t),1.0); }',
    }),
  );
  sky.renderOrder = -1;
  scene.add(sky);

  const hemi = new THREE.HemisphereLight('#dff1ff', '#5f8f3f', 1.35);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight('#fffaf0', 2.4);
  const sunDir = new THREE.Vector3(-0.45, 1, 0.3).normalize();
  sun.castShadow = true;
  const mobile = matchMedia('(pointer: coarse)').matches;
  sun.shadow.mapSize.set(mobile ? 1024 : 2048, mobile ? 1024 : 2048);
  const sc = sun.shadow.camera;
  sc.left = -45; sc.right = 45; sc.top = 45; sc.bottom = -45; sc.near = 10; sc.far = 260;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.03;
  scene.add(sun, sun.target);

  // ---------------------------------------------------------- 載入
  const loader = new GLTFLoader();
  let done = 0;
  const tick = () => onProgress(++done / 3);
  const [trackG, kartG, path] = await Promise.all([
    loader.loadAsync('assets/track1.glb').then((g) => (tick(), g)),
    loader.loadAsync('assets/kart.glb').then((g) => (tick(), g)),
    fetch('assets/track1_path.json').then((r) => r.json()).then((j) => (tick(), j)),
  ]);

  const grad = gradientMap();
  const roadTex = roadTexture();
  roadTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const grassTex = grassTexture();
  grassTex.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  const cache = new Map();

  function toon(m) {
    if (cache.has(m)) return cache.get(m);
    let out;
    const name = m.name || '';
    if (name === 'Water') {
      out = new THREE.MeshPhongMaterial({ color: '#46b9f2', specular: '#ffffff', shininess: 90, transparent: true, opacity: 0.88 });
    } else if (name === 'Cloud') {
      out = new THREE.MeshLambertMaterial({ color: '#ffffff', emissive: '#d6e6f5', fog: false });
    } else {
      out = new THREE.MeshToonMaterial({ color: m.color, gradientMap: grad, side: m.side });
      if (m.emissive && m.emissiveIntensity > 0 && m.emissive.getHex() !== 0) {
        out.emissive = m.emissive.clone();
        out.emissiveIntensity = 0.35;
      }
      if (name === 'Road') { out.map = roadTex; out.color.set('#ffffff'); }
      if (name === 'Grass') { out.map = grassTex; out.color.set('#ffffff'); }
    }
    out.name = name;
    cache.set(m, out);
    return out;
  }

  const track = trackG.scene;
  const anim = { blades: null, balloons: [], clouds: null };
  track.traverse((o) => {
    if (o.isMesh) {
      o.material = Array.isArray(o.material) ? o.material.map(toon) : toon(o.material);
      const nm = o.material.name;
      o.receiveShadow = nm !== 'Cloud';
      o.castShadow = !['Road', 'Grass', 'Water', 'Cloud', 'CurbRed', 'CurbWhite', 'CheckBlack', 'CheckWhite'].includes(nm) && !/^Mountain|^Snow/.test(nm);
      if (nm === 'Grass' && !o.geometry.attributes.uv) {
        // 地形沒存 UV：用世界座標每 8 公尺一格
        const pos = o.geometry.attributes.position;
        const uv = new Float32Array(pos.count * 2);
        for (let i = 0; i < pos.count; i++) {
          uv[i * 2] = pos.getX(i) / 8;
          uv[i * 2 + 1] = pos.getZ(i) / 8;
        }
        o.geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
      }
      if (nm === 'Road' || nm === 'Grass') o.material.polygonOffset = false;
    }
    if (o.name === 'Windmill_Blades') anim.blades = o;
    if (/^Balloon_\d+$/.test(o.name)) anim.balloons.push({ o, y: o.position.y, ph: Math.random() * 6 });
    if (o.name === 'Clouds') anim.clouds = o;
  });
  scene.add(track);

  // ---------------------------------------------------------- 車
  const kart = new THREE.Group();
  const model = kartG.scene;
  model.traverse((o) => {
    if (o.isMesh) {
      o.material = Array.isArray(o.material) ? o.material.map(toon) : toon(o.material);
      o.castShadow = true;
      o.receiveShadow = true;
    }
  });
  kart.add(model);
  kart.rotation.order = 'YXZ';
  const parts = {
    model,
    body: model.getObjectByName('Body'),
    driver: model.getObjectByName('Driver'),
    wheels: ['FL', 'FR', 'RL', 'RR'].map((k) => model.getObjectByName('Wheel_' + k)),
    exhaust: ['Exhaust_L', 'Exhaust_R'].map((k) => model.getObjectByName(k)),
  };
  for (const w of parts.wheels) if (w) w.rotation.order = 'YXZ';
  parts.driverBase = parts.driver ? parts.driver.position.clone() : null;
  scene.add(kart);

  function update(dt, t, focus) {
    if (anim.blades) anim.blades.rotation.z += dt * 0.9;
    for (const b of anim.balloons) b.o.position.y = b.y + Math.sin(t * 0.5 + b.ph) * 2.5;
    if (anim.clouds) anim.clouds.rotation.y += dt * 0.004;
    // 陰影相機跟著車走（貼齊格點避免陰影閃爍）
    const snap = 2;
    const fx = Math.round(focus.x / snap) * snap, fz = Math.round(focus.z / snap) * snap;
    sun.target.position.set(fx, focus.y, fz);
    sun.position.set(fx + sunDir.x * 120, focus.y + sunDir.y * 120, fz + sunDir.z * 120);
    sky.position.copy(focus);
  }

  return { scene, sun, kart, parts, path, update };
}
