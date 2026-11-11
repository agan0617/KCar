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

// 照片材質（Poly Haven CC0，用 KCar_assets_src/_scripts/make_tex.py 先處理成「細節圖」：線性空間每色版平均 0.5，shader 乘 2 後平均＝1，
// 顏色由主題底色×Blender 頂點色決定，照片只給紋路）。值＝每格幾公尺（世界座標 UV）
const DETAIL = { grass: 3, sand: 4, snow: 5, dirt: 3, rock: 6, ash: 4, leaves: 3, pavement: 4, wood: 3 };
// 紋路強度（1＝照處理好的細節圖；大於 1 加強明暗起伏，兩層混合後會變淡要補回來）
const DETAIL_K = { grass: 1.9, sand: 1.5, snow: 1.3, dirt: 1.6, rock: 1.6, ash: 1.4, leaves: 1.5, pavement: 1.5, wood: 1.5 };
// Blender 材質 → 細節圖、投影方式（top＝由上往下投；box＝依面法線挑軸，給垂直面用）
const DETAIL_MAT = {
  EdgeSand: ['sand', 'top'], EdgeSnow: ['snow', 'top'], EdgeDirt: ['dirt', 'top'], DirtRoad: ['dirt', 'top'],
  Cliff: ['rock', 'box'], Bridge: ['pavement', 'box'], BridgePier: ['pavement', 'box'],
  Boardwalk: ['wood', 'box'], TunnelPortal: ['rock', 'box'],
};

// 細節圖的取樣：兩個尺度（第二層旋轉＋放大）混合＋一層很低頻的明暗，遠處看不出重複；
// map2（選用）：頂點色不偏綠的地方（Blender 算的磨損帶、沙土路肩）換成第二張細節圖
function detailShader(sh, mat) {
  const two = !!mat.userData.map2;
  if (two) sh.uniforms.map2 = { value: mat.userData.map2 };
  sh.uniforms.detailK = { value: mat.userData.detailK };
  sh.fragmentShader = sh.fragmentShader
    .replace('#include <map_pars_fragment>', `#include <map_pars_fragment>\nuniform float detailK;\n${two ? 'uniform sampler2D map2;' : ''}`)
    .replace('#include <map_fragment>', `
#ifdef USE_MAP
  vec2 dUvB = mat2( 0.8, -0.6, 0.6, 0.8 ) * vMapUv * 0.29 + vec2( 0.31, 0.17 );
  vec3 det = mix( texture2D( map, vMapUv ).rgb, texture2D( map, dUvB ).rgb, 0.4 );
  ${two ? `#ifdef USE_COLOR
  float dW = smoothstep( 0.03, -0.05, vColor.g - max( vColor.r, vColor.b ) );
  if ( dW > 0.001 ) det = mix( det, mix( texture2D( map2, vMapUv ).rgb, texture2D( map2, dUvB ).rgb, 0.4 ), dW );
  #endif` : ''}
  float dM = texture2D( map, vMapUv * 0.043 + vec2( 0.5, 0.2 ) ).g * 2.0;
  det = max( 1.0 + ( det * 2.0 - 1.0 ) * detailK, 0.15 );
  diffuseColor.rgb *= det * mix( 1.0, dM, 0.35 );
#endif`);
}

/** 用世界座標給頂點 UV（每 scale 公尺一格）；box：垂直面改用 xy／zy 投影，避免拉伸 */
function worldUV(o, scale, box) {
  const g = o.geometry;
  const pos = g.attributes.position, nor = g.attributes.normal;
  const m = o.matrixWorld, nm = new THREE.Matrix3().getNormalMatrix(m);
  const v = new THREE.Vector3(), n = new THREE.Vector3();
  const uv = new Float32Array(pos.count * 2);
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i).applyMatrix4(m);
    let a = v.x, b = v.z;
    if (box && nor) {
      n.fromBufferAttribute(nor, i).applyMatrix3(nm);
      if (Math.abs(n.y) < 0.6) { if (Math.abs(n.x) > Math.abs(n.z)) { a = v.z; b = v.y; } else { a = v.x; b = v.y; } }
    }
    uv[i * 2] = a / scale;
    uv[i * 2 + 1] = b / scale;
  }
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
}

// 路面：u 橫跨路寬（0..1），v 沿路每 8 公尺一個循環。asphalt：柏油灰階細節圖（有就用 overlay 疊在底色上，沒有就撒點）
function roadTexture(th, asphalt) {
  const r = th.road;
  return canvasTex(1024, 1024, (g, w, h) => {
    g.fillStyle = r.base;
    g.fillRect(0, 0, w, h);
    if (!asphalt) {
      const rnd = rand(7);
      for (let i = 0; i < 36000; i++) {
        const v = r.speck[0] + rnd() * (r.speck[1] - r.speck[0]);
        g.fillStyle = `rgba(${v},${v + 4},${v + 14},${0.25 + rnd() * 0.3})`;
        g.fillRect(rnd() * w, rnd() * h, 1 + rnd() * 4, 1 + rnd() * 4);
      }
    }
    // 輪胎磨過的兩條深色帶（行車線）
    for (const c of [0.3, 0.7]) {
      const grd = g.createLinearGradient(w * (c - 0.09), 0, w * (c + 0.09), 0);
      grd.addColorStop(0, 'rgba(0,0,0,0)'); grd.addColorStop(0.5, 'rgba(0,0,0,0.07)'); grd.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = grd;
      g.fillRect(w * (c - 0.09), 0, w * 0.18, h);
    }
    g.fillStyle = r.edge;
    g.fillRect(w * 0.022, 0, w * 0.022, h);
    g.fillRect(w * 0.956, 0, w * 0.022, h);
    // 中央虛線：每 4 公尺一段 2 公尺（越密地面掠過感越強）
    g.fillStyle = r.center;
    g.fillRect(w * 0.494, 0, w * 0.012, h * 0.25);
    g.fillRect(w * 0.494, h * 0.5, w * 0.012, h * 0.25);
    // 兩側車道的淡色補丁（瀝青修補痕），給路面多一點會往後流的紋路
    const rp = rand(31);
    for (let i = 0; i < 10; i++) {
      g.fillStyle = `rgba(0,0,0,${0.025 + rp() * 0.03})`;
      const x = w * (0.08 + rp() * 0.8), y = rp() * h;
      if (Math.abs(x - w * 0.5) < w * 0.06) continue;
      g.fillRect(x, y, w * (0.03 + rp() * 0.06), h * (0.03 + rp() * 0.07));
    }
    // 柏油照片：路寬約 15 公尺、v 一格 8 公尺 → 橫 6 格、縱 3 格（約 2.5 公尺一格，整數格才接得起來）
    if (asphalt) {
      g.globalCompositeOperation = 'overlay';
      const tw = w / 6, tht = h / 3;
      for (let i = 0; i < 6; i++) for (let j = 0; j < 3; j++) g.drawImage(asphalt, i * tw, j * tht, tw, tht);
      g.globalCompositeOperation = 'source-over';
    }
  });
}

// 加速帶：往前的箭頭（v 方向往前，材質 offset 捲動）
function boostTexture() {
  return canvasTex(128, 256, (g, w, h) => {
    g.fillStyle = '#1a6dff';
    g.fillRect(0, 0, w, h);
    for (let k = 0; k < 2; k++) {
      const y0 = k * h / 2;
      const grd = g.createLinearGradient(0, y0, 0, y0 + h / 2);
      grd.addColorStop(0, '#fff6a0'); grd.addColorStop(1, '#ff9a1a');
      g.fillStyle = grd;
      g.beginPath();
      g.moveTo(w * 0.12, y0 + h * 0.16); g.lineTo(w * 0.5, y0 + h * 0.34); g.lineTo(w * 0.88, y0 + h * 0.16);
      g.lineTo(w * 0.88, y0 + h * 0.06); g.lineTo(w * 0.5, y0 + h * 0.24); g.lineTo(w * 0.12, y0 + h * 0.06);
      g.closePath(); g.fill();
    }
  });
}

// 捷徑土路：深淺斑點的泥土
function dirtTexture() {
  return canvasTex(256, 256, (g, w, h) => {
    g.fillStyle = '#8a6440';
    g.fillRect(0, 0, w, h);
    const rnd = rand(11);
    for (let i = 0; i < 5000; i++) {
      const v = rnd();
      g.fillStyle = v < 0.5 ? `rgba(70,48,28,${0.2 + rnd() * 0.3})` : `rgba(176,140,98,${0.2 + rnd() * 0.3})`;
      g.fillRect(rnd() * w, rnd() * h, 1 + rnd() * 3, 1 + rnd() * 3);
    }
    g.fillStyle = 'rgba(60,40,22,0.35)';
    g.fillRect(w * 0.22, 0, w * 0.1, h);
    g.fillRect(w * 0.68, 0, w * 0.1, h);
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

const NO_SHADOW = new Set(['Boardwalk', 'DirtRoad', 'EdgeSand', 'EdgeSnow', 'EdgeDirt', 'Cliff', 'Fence', 'Road', 'Ground', 'Water', 'Ice', 'Lava', 'Choco', 'Cloud', 'AshCloud', 'CurbA', 'CurbB', 'CheckBlack', 'CheckWhite']);
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
  sun.shadow.radius = 2; // PCF 取樣半徑（texel）：大一點陰影邊比較柔
  let shadowAhead = 0; // 陰影範圍往車頭方向挪多少公尺（鏡頭在車後，車後面的陰影大多看不到）
  const lastFocus = new THREE.Vector3(), aheadDir = new THREE.Vector3(0, 0, 1);
  scene.add(sun, sun.target);
  // 夜間賽道：跟著車的補光（像路燈照到車上），白天關掉
  const carLight = new THREE.PointLight('#ffe2b8', 0, 18, 1.6);
  scene.add(carLight);

  const loader = new GLTFLoader();
  const texLoader = new THREE.TextureLoader();
  const maxAniso = renderer.capabilities.getMaxAnisotropy();
  let tex = { road: null, ground: null };
  let cache = new Map();

  // 照片細節圖（換賽道不丟，下次直接用）
  const detailCache = new Map();
  function loadDetail(name) {
    if (!detailCache.has(name)) {
      const p = Promise.all([texLoader.loadAsync(`assets/tex/${name}.jpg`), texLoader.loadAsync(`assets/tex/${name}_n.jpg`)]).then(([map, nor]) => {
        map.colorSpace = THREE.SRGBColorSpace;
        for (const t of [map, nor]) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = Math.min(8, maxAniso); }
        return { map, nor, name };
      }).catch(() => null);
      detailCache.set(name, p);
    }
    return detailCache.get(name);
  }
  const detail = {}; // 這條賽道用到的（已載入）
  let asphaltImg = null, roadNor = null;
  const asphaltP = new Promise((res) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => res(null); im.src = 'assets/tex/road.jpg'; });
  const roadNorP = texLoader.loadAsync('assets/tex/road_n.jpg').then((t) => { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(6, 3); t.anisotropy = Math.min(8, maxAniso); return t; }).catch(() => null);

  // 天空：Poly Haven HDRI 調色後的 equirect JPG（assets/sky/<主題>.jpg）；沒有就用上面的漸層球
  let skyTex = null, skyId = null;
  async function loadSky(id) {
    if (id === skyId) return skyTex;
    let t = null;
    try {
      t = await texLoader.loadAsync(`assets/sky/${id}.jpg`);
      t.colorSpace = THREE.SRGBColorSpace;
      t.mapping = THREE.EquirectangularReflectionMapping;
    } catch (e) { t = null; }
    if (skyTex) skyTex.dispose();
    skyTex = t;
    skyId = id;
    return t;
  }

  // 環境光照（PBR 材質的反射、柔和的補光）：用這條賽道自己的天空做（夜城反射夜空、火山反射紅天），
  // 地平線以下換成地面色（天空圖下半是地平線色，拿來當反射會像站在鏡面上）。
  // 不用 three 內建的攝影棚環境——那裡面的燈板太亮，車身反射到會整片發白
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envU = {
    top: { value: new THREE.Color() }, mid: { value: new THREE.Color() }, bottom: { value: new THREE.Color() },
    sunDir: { value: new THREE.Vector3() }, sunCol: { value: new THREE.Color() }, sky: { value: null }, useSky: { value: 0 },
  };
  const envScene = new THREE.Scene();
  envScene.add(new THREE.Mesh(new THREE.SphereGeometry(10, 64, 32), new THREE.ShaderMaterial({
    side: THREE.BackSide, uniforms: envU,
    vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: `uniform vec3 top; uniform vec3 mid; uniform vec3 bottom; uniform vec3 sunDir; uniform vec3 sunCol; uniform sampler2D sky; uniform float useSky; varying vec3 vP;
      void main(){ vec3 d = normalize(vP);
        vec3 c;
        if (useSky > 0.5) {
          float u = atan(d.z, d.x) * 0.15915494 + 0.5;
          vec3 s = texture2D(sky, vec2(u, asin(clamp(d.y, -1.0, 1.0)) * 0.31830989 + 0.5)).rgb;
          vec3 h = texture2D(sky, vec2(u, 0.51)).rgb;
          c = d.y > 0.0 ? s : mix(h, bottom, smoothstep(0.0, 0.3, -d.y));
        } else {
          c = d.y > 0.0 ? mix(mid, top, pow(d.y, 0.6)) : mix(mid, bottom, pow(-d.y, 0.4));
        }
        c += sunCol * pow(max(dot(d, sunDir), 0.0), 64.0) * 1.5;
        gl_FragColor = vec4(c, 1.0); }`,
  })));
  let envTex = null;
  function makeEnv(th, sky) {
    envU.top.value.set(th.skyTop);
    envU.mid.value.set(th.horizon);
    envU.bottom.value.set(th.hemi[1]);
    envU.sunDir.value.set(...th.sunDir).normalize();
    envU.sunCol.value.set(th.sun[0]).multiplyScalar(th.night ? 0.2 : 1);
    envU.sky.value = sky;
    envU.useSky.value = sky ? 1 : 0;
    if (envTex) envTex.dispose();
    envTex = pmrem.fromScene(envScene, 0.02).texture;
    scene.environment = envTex;
  }

  // 車身烤漆：亮面＋透明漆層
  const PAINT = new Set(['KartRed', 'KartWhite', 'KartYellow', 'Hoodie', 'HeadphoneAccent']);

  /** 材質掛上照片細節圖（UV 由 loadTrack 用世界座標補） */
  function useDetail(out, d, d2) {
    out.map = d.map;
    out.userData.detailK = DETAIL_K[d.name] ?? 1.4;
    out.normalMap = d.nor;
    out.normalScale.set(0.7, 0.7);
    out.metalness = 0;
    out.userData.map2 = d2 ? d2.map : null;
    out.userData.detail = true;
    out.onBeforeCompile = (sh) => detailShader(sh, out);
    out.customProgramCacheKey = () => (d2 ? 'detail2' : 'detail1');
    out.needsUpdate = true;
  }

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
      if (name === 'Road') {
        out.map = tex.road; out.color.set('#ffffff'); out.roughness = 0.8;
        if (roadNor) { out.normalMap = roadNor; out.normalScale.set(0.6, 0.6); }
      }
      if (name === 'Ground') {
        const gd = detail[theme.ground.tex];
        if (gd) {
          // 照片細節 × 主題底色 × Blender 頂點色（保留算好的深淺與磨損帶）
          useDetail(out, gd, theme.ground.tex2 && detail[theme.ground.tex2]);
          out.color.set(theme.ground.base);
        } else { out.map = tex.ground; out.color.set('#ffffff'); }
        out.roughness = 1;
      }
      if (name === 'Boost') { out.map = tex.boost; out.color.set('#ffffff'); out.emissive.set('#3a5cff'); out.emissiveIntensity = 0.6; out.emissiveMap = tex.boost; out.roughness = 0.4; }
      if (name === 'DirtRoad') {
        if (detail.dirt) useDetail(out, detail.dirt); // 顏色照 Blender
        else { out.map = tex.dirt; out.color.set('#ffffff'); }
        out.roughness = 1;
      }
      if (DETAIL_MAT[name] && name !== 'DirtRoad' && detail[DETAIL_MAT[name][0]]) {
        useDetail(out, detail[DETAIL_MAT[name][0]]); // 顏色照 Blender
        out.roughness = Math.max(out.roughness, 0.85);
      }
      if (name === 'TunnelLight') { out.emissive.set('#fff1c8'); out.emissiveIntensity = 1.4; }
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
  // 接觸陰影：車底一片柔邊的暗影（陰影貼圖解析度不夠時，車還是「坐」在地上），兩檔畫質都有
  const kartBox = new THREE.Box3().setFromObject(kartTemplate);
  const blobTex = canvasTex(64, 64, (g, w, h) => {
    const grd = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.55, 'rgba(255,255,255,0.75)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, w, h);
  });
  blobTex.wrapS = blobTex.wrapT = THREE.ClampToEdgeWrapping;
  const blobMat = new THREE.MeshBasicMaterial({
    color: '#000000', alphaMap: blobTex, transparent: true, opacity: 0.42, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
  });
  const blobGeo = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);

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
    const blob = new THREE.Mesh(blobGeo, blobMat);
    const ks = kartBox.getSize(new THREE.Vector3()), kc = kartBox.getCenter(new THREE.Vector3());
    blob.scale.set(ks.x * 1.25, 1, ks.z * 1.15);
    blob.position.set(kc.x, kartBox.min.y + 0.04, kc.z);
    blob.renderOrder = 1;
    group.add(blob);
    group.rotation.order = 'YXZ';
    // 車身（輪子以外的全部）另外包一層，懸吊的俯仰、側傾、上下只動車身，輪子留在地上
    const root = model.children.length === 1 && !/^Wheel_/.test(model.children[0].name) && model.children[0].children.length > 1 ? model.children[0] : model;
    const body = new THREE.Group();
    body.name = 'Body';
    for (const c of [...root.children]) if (!/^Wheel_/.test(c.name)) body.add(c);
    root.add(body);
    const parts = {
      model: body,
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

  function applyTheme(th, skyMap) {
    theme = th;
    skyU.top.value.set(th.skyTop);
    skyU.bottom.value.set(th.horizon);
    if (skyMap) {
      scene.background = skyMap;
      scene.backgroundIntensity = th.skyGain ?? 1;
      sky.visible = false;
    } else {
      scene.background = new THREE.Color(th.horizon);
      sky.visible = true;
    }
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
    makeEnv(th, skyMap);
    carLight.intensity = th.night ? 22 : 0;
    scene.environmentIntensity = th.env ?? 0.55;
    for (const k of ['road', 'ground']) if (tex[k]) tex[k].dispose();
    tex = { road: roadTexture(th, asphaltImg), ground: groundTexture(th), boost: tex.boost || boostTexture(), dirt: tex.dirt || dirtTexture() };
    tex.road.anisotropy = maxAniso;
    tex.ground.anisotropy = Math.min(8, maxAniso);
  }

  async function loadTrack(id, progress = () => {}) {
    const [g, path] = await Promise.all([
      loader.loadAsync(`assets/${id}.glb`, (e) => { if (e.total) progress(e.loaded / e.total); }),
      fetch(`assets/${id}_path.json`).then((r) => r.json()),
    ]);
    // v2 賽道（有逐點路寬 hw）另有碰撞資料
    if (path.hw) path.col = await fetch(`assets/${id}_col.json`).then((r) => r.json());
    // 主題的天空與照片材質（第一次載入要下載，之後走快取）
    const th = THEMES[path.theme] || THEMES.hills;
    const need = new Set(Object.values(DETAIL_MAT).map((v) => v[0]));
    if (th.ground.tex) need.add(th.ground.tex);
    if (th.ground.tex2) need.add(th.ground.tex2);
    const [skyMap, aImg, rN, ...ds] = await Promise.all([loadSky(path.theme || 'hills'), asphaltP, roadNorP, ...[...need].map(loadDetail)]);
    asphaltImg = aImg; roadNor = rN;
    for (const k of Object.keys(detail)) delete detail[k];
    [...need].forEach((k, i) => { if (ds[i]) detail[k] = ds[i]; });
    if (trackObj) { scene.remove(trackObj); disposeTree(trackObj); }
    for (const m of cache.values()) m.dispose();
    cache = new Map();
    applyTheme(th, skyMap);
    anim.spinZ = []; anim.spinY = []; anim.bob = []; anim.clouds = null; anim.lava = [];
    g.scene.updateMatrixWorld(true);
    g.scene.traverse((o) => {
      if (o.isMesh) {
        o.material = Array.isArray(o.material) ? o.material.map(toon) : toon(o.material);
        const nm = o.material.name;
        o.receiveShadow = nm !== 'Cloud';
        o.castShadow = !NO_SHADOW.has(nm) && !/^Mountain|^Snow$|^Island/.test(nm);
        if (o.material.userData.detail) {
          // 照片材質：一律用世界座標 UV（原本沒 UV，或 UV 的比例不是公尺）
          const key = nm === 'Ground' ? th.ground.tex : DETAIL_MAT[nm][0];
          worldUV(o, DETAIL[key], nm !== 'Ground' && DETAIL_MAT[nm][1] === 'box');
        } else if (nm === 'Ground' && !o.geometry.attributes.uv) {
          // 地形沒存 UV：用世界座標每 8 公尺一格
          const pos = o.geometry.attributes.position;
          const uv = new Float32Array(pos.count * 2);
          for (let i = 0; i < pos.count; i++) { uv[i * 2] = pos.getX(i) / 8; uv[i * 2 + 1] = pos.getZ(i) / 8; }
          o.geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
        }
        if (nm === 'Lava') anim.lava.push(o.material);
        // 有照片天空時，模型裡的白雲（Cloud）拿掉：天空圖本身就有雲，兩種疊在一起很假（火山的灰雲 AshCloud 留著）
        if (nm === 'Cloud' && skyMap) o.visible = false;
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
    if (tex.boost) tex.boost.offset.y = -((t * 1.6) % 1); // 加速帶箭頭往前流
    // 熔岩：顏色超過 1，泛光才吃得到（高畫質會發光暈）
    for (const m of anim.lava) m.color.setHSL(0.04 + Math.sin(t * 1.3) * 0.015, 1, 0.5 + Math.sin(t * 2.1) * 0.06).multiplyScalar(1.6);
    // 陰影相機跟著車走，往行進方向挪一些（貼齊格點避免陰影閃爍）
    const mv = lastFocus.distanceToSquared(focus);
    if (mv > 1e-4 && mv < 100) {
      const dx = focus.x - lastFocus.x, dz = focus.z - lastFocus.z, l = Math.hypot(dx, dz) || 1;
      const k = Math.min(1, dt * 2);
      aheadDir.x += (dx / l - aheadDir.x) * k;
      aheadDir.z += (dz / l - aheadDir.z) * k;
    }
    lastFocus.copy(focus);
    const al = Math.hypot(aheadDir.x, aheadDir.z) || 1;
    const snap = 2;
    const fx = Math.round((focus.x + aheadDir.x / al * shadowAhead) / snap) * snap, fz = Math.round((focus.z + aheadDir.z / al * shadowAhead) / snap) * snap;
    sun.target.position.set(fx, focus.y, fz);
    sun.position.set(fx + sunDir.x * 120, focus.y + sunDir.y * 120, fz + sunDir.z * 120);
    sky.position.copy(focus);
    carLight.position.set(focus.x, focus.y + 6, focus.z);
  }

  function setShadowSize(n) {
    if (sun.shadow.mapSize.x === n) return;
    sun.shadow.mapSize.set(n, n);
    if (sun.shadow.map) { sun.shadow.map.dispose(); sun.shadow.map = null; }
  }

  /** 畫質：high＝2048 陰影、範圍大一圈、邊更柔；low＝1024、原本的範圍 */
  function setQuality(q) {
    const high = q === 'high';
    setShadowSize(high ? 2048 : 1024);
    const ext = high ? 58 : 45;
    sc.left = -ext; sc.right = ext; sc.top = ext; sc.bottom = -ext;
    sc.updateProjectionMatrix();
    sun.shadow.radius = high ? 2.5 : 1.5;
    shadowAhead = high ? 22 : 15;
  }

  return { scene, makeKart, loadTrack, update, setShadowSize, setQuality, get theme() { return theme; } };
}
