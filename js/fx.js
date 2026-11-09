// 特效：甩尾火花、輪胎痕、煙塵、排氣管噴火。

import * as THREE from 'three';

function softDot() {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,255,1)');
  gr.addColorStop(0.35, 'rgba(255,255,255,0.8)');
  gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr;
  g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c);
  return t;
}

class Particles {
  constructor(scene, max, { size, additive, tex, opacity = 1 }) {
    this.max = max;
    this.pos = new Float32Array(max * 3);
    this.col = new Float32Array(max * 3);
    this.vel = new Float32Array(max * 3);
    this.life = new Float32Array(max);
    this.maxLife = new Float32Array(max);
    this.base = new Float32Array(max * 3);
    this.next = 0;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('color', new THREE.BufferAttribute(this.col, 3).setUsage(THREE.DynamicDrawUsage));
    this.geo = g;
    const m = new THREE.PointsMaterial({
      size, map: tex, vertexColors: true, transparent: true, opacity,
      depthWrite: false, blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    });
    this.points = new THREE.Points(g, m);
    this.points.frustumCulled = false;
    scene.add(this.points);
    this.gravity = 0;
    this.drag = 0;
    for (let i = 0; i < max; i++) this.pos[i * 3 + 1] = -9999;
  }

  emit(x, y, z, vx, vy, vz, color, life) {
    const i = this.next;
    this.next = (this.next + 1) % this.max;
    this.pos.set([x, y, z], i * 3);
    this.vel.set([vx, vy, vz], i * 3);
    this.base.set([color.r, color.g, color.b], i * 3);
    this.life[i] = this.maxLife[i] = life;
  }

  update(dt) {
    const k = Math.exp(-this.drag * dt);
    for (let i = 0; i < this.max; i++) {
      if (this.life[i] <= 0) continue;
      this.life[i] -= dt;
      const j = i * 3;
      if (this.life[i] <= 0) { this.pos[j + 1] = -9999; continue; }
      this.vel[j] *= k; this.vel[j + 1] = this.vel[j + 1] * k - this.gravity * dt; this.vel[j + 2] *= k;
      this.pos[j] += this.vel[j] * dt;
      this.pos[j + 1] += this.vel[j + 1] * dt;
      this.pos[j + 2] += this.vel[j + 2] * dt;
      const f = this.life[i] / this.maxLife[i];
      this.col[j] = this.base[j] * f;
      this.col[j + 1] = this.base[j + 1] * f;
      this.col[j + 2] = this.base[j + 2] * f;
    }
    this.geo.attributes.position.needsUpdate = true;
    this.geo.attributes.color.needsUpdate = true;
  }
}

class Skid {
  constructor(scene, max = 700) {
    this.max = max;
    this.pos = new Float32Array(max * 4 * 3);
    const idx = [];
    for (let i = 0; i < max; i++) { const b = i * 4; idx.push(b, b + 1, b + 2, b, b + 2, b + 3); }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setIndex(idx);
    this.geo = g;
    const m = new THREE.MeshBasicMaterial({ color: '#1a1a1a', transparent: true, opacity: 0.32, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
    this.mesh = new THREE.Mesh(g, m);
    this.mesh.frustumCulled = false;
    scene.add(this.mesh);
    this.next = 0;
    this.last = [null, null];
  }

  /** wheel: 0/1；p: 世界座標；rx,rz: 車的右手邊；active=false 會斷開線段 */
  add(wheel, p, rx, rz, active) {
    const prev = this.last[wheel];
    if (!active) { this.last[wheel] = null; return; }
    const w = 0.16;
    const cur = { x: p.x, y: p.y + 0.03, z: p.z, rx, rz };
    if (prev && (prev.x - cur.x) ** 2 + (prev.z - cur.z) ** 2 > 0.25) {
      const i = this.next;
      this.next = (this.next + 1) % this.max;
      this.pos.set([
        prev.x - prev.rx * w, prev.y, prev.z - prev.rz * w,
        prev.x + prev.rx * w, prev.y, prev.z + prev.rz * w,
        cur.x + rx * w, cur.y, cur.z + rz * w,
        cur.x - rx * w, cur.y, cur.z - rz * w,
      ], i * 12);
      this.geo.attributes.position.needsUpdate = true;
      this.last[wheel] = cur;
    } else if (!prev) this.last[wheel] = cur;
  }

  clear() {
    this.pos.fill(0);
    this.geo.attributes.position.needsUpdate = true;
    this.last = [null, null];
  }
}

const C_SPARK = new THREE.Color('#ffb03a');
const C_READY = new THREE.Color('#7fe0ff');
const C_SMOKE = new THREE.Color('#e9ecef');
const C_DUST = new THREE.Color('#b8a27a');
const C_NITRO = new THREE.Color('#5fb8ff');
const C_JET = new THREE.Color('#ff8a2a');

export class Fx {
  constructor(scene, kart, parts) {
    const tex = softDot();
    this.sparks = new Particles(scene, 500, { size: 0.32, additive: true, tex });
    this.sparks.gravity = 9;
    this.sparks.drag = 1.5;
    this.smoke = new Particles(scene, 300, { size: 1.6, additive: false, tex, opacity: 0.55 });
    this.smoke.gravity = -0.6;
    this.smoke.drag = 2.2;
    this.skid = new Skid(scene);
    this.kart = kart;
    this.parts = parts;
    this.acc = 0;
    // 排氣管噴火：外焰＋白芯
    this.flames = parts.exhaust.map((ex) => {
      const g = new THREE.Group();
      const outer = new THREE.Mesh(new THREE.ConeGeometry(0.16, 1, 10, 1, true),
        new THREE.MeshBasicMaterial({ color: C_JET, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false }));
      const inner = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.6, 8, 1, true),
        new THREE.MeshBasicMaterial({ color: '#fff6d8', transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false }));
      for (const m of [outer, inner]) { m.rotation.x = -Math.PI / 2; m.position.z = -0.5; }
      inner.position.z = -0.3;
      g.add(outer, inner);
      g.visible = false;
      (ex || parts.model).add(g);
      return { g, outer, inner };
    });
    this.tmp = new THREE.Vector3();
  }

  wheelWorld(i, out) {
    const w = this.parts.wheels[i];
    w.getWorldPosition(out);
    out.y -= w.position.y - 0.02;
    return out;
  }

  update(dt, k, t) {
    const sin = Math.sin(k.h), cos = Math.cos(k.h);
    const rx = -cos, rz = sin; // 右手邊
    const fwdx = sin, fwdz = cos;
    const ready = k.drift && k.driftT >= 0.35;
    this.acc += dt;
    const p = this.tmp;
    // 甩尾火花＋白煙＋胎痕
    for (let wi = 0; wi < 2; wi++) {
      this.wheelWorld(2 + wi, p);
      const slipping = k.drift || (Math.abs(k.slip) > 0.12 && k.spd > 8);
      this.skid.add(wi, p, rx, rz, slipping && !k.onGrass);
      if (k.drift && !k.onGrass) {
        const n = Math.random() < dt * 70 ? 2 : 0;
        for (let s = 0; s < n; s++) {
          const side = wi === 0 ? 1 : -1;
          this.sparks.emit(p.x, p.y + 0.1, p.z,
            -fwdx * (2 + Math.random() * 3) + rx * side * (Math.random() * 2) + (Math.random() - 0.5),
            2 + Math.random() * 3,
            -fwdz * (2 + Math.random() * 3) + rz * side * (Math.random() * 2) + (Math.random() - 0.5),
            ready ? C_READY : C_SPARK, 0.25 + Math.random() * 0.2);
        }
        if (Math.random() < dt * 14) this.smoke.emit(p.x, p.y + 0.3, p.z, -fwdx * 2, 0.8, -fwdz * 2, C_SMOKE, 0.9);
      }
      if (k.onGrass && Math.abs(k.spd) > 4 && Math.random() < dt * 18) {
        this.smoke.emit(p.x, p.y + 0.3, p.z, -fwdx * 3 + (Math.random() - 0.5) * 2, 1.2, -fwdz * 3 + (Math.random() - 0.5) * 2, C_DUST, 0.8);
      }
    }
    this.sparks.update(dt);
    this.smoke.update(dt);

    // 噴火
    const nitro = k.nitroT > 0;
    const boost = k.boostT > 0;
    const on = nitro || boost;
    const strength = nitro ? 1.6 : boost ? (k.boostKind === 'dj' ? 1.3 : 1.0) : 0;
    for (const f of this.flames) {
      f.g.visible = on;
      if (!on) continue;
      const flick = 0.8 + Math.random() * 0.4;
      f.g.scale.set(1, 1, strength * flick);
      f.outer.material.color.copy(nitro ? C_NITRO : C_JET);
    }
  }

  reset() { this.skid.clear(); }
}
