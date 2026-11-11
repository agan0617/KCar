// 賽道碰撞（Blender 腳本輸出的 *_col.json，格式見 tools/blender/TRACK_V2.md）：
// 地面三角形（含地面種類）與護牆線段，用 XZ 平面的格子索引查。
// 瀏覽器與 Node（server、模擬工具）共用，不依賴 three.js。

export const SURF = { ROAD: 0, CURB: 1, GRASS: 2, BOOST: 3, DIRT: 4, HAZARD: 5, SAND: 6 };

function decode(b64, Type) {
  const bin = atob(b64);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return Type === Uint8Array ? u8 : new Type(u8.buffer);
}

const CELL = 8;
const key = (ix, iz) => (ix + 32768) * 65536 + (iz + 32768);

export class Collision {
  constructor(data) {
    this.tris = decode(data.tris, Float32Array);
    this.surf = decode(data.surf, Uint8Array);
    this.walls = decode(data.walls || '', Float32Array);
    this.killY = data.killY ?? -50;
    this.tGrid = new Map();
    this.wGrid = new Map();
    const T = this.tris;
    const nt = T.length / 9;
    // 預先算好每個三角形的法向量（Y 朝上）
    this.norm = new Float32Array(nt * 3);
    for (let t = 0; t < nt; t++) {
      const o = t * 9;
      const ax = T[o + 3] - T[o], ay = T[o + 4] - T[o + 1], az = T[o + 5] - T[o + 2];
      const bx = T[o + 6] - T[o], by = T[o + 7] - T[o + 1], bz = T[o + 8] - T[o + 2];
      let nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
      if (ny < 0) { nx = -nx; ny = -ny; nz = -nz; }
      const l = Math.hypot(nx, ny, nz) || 1;
      this.norm[t * 3] = nx / l; this.norm[t * 3 + 1] = ny / l; this.norm[t * 3 + 2] = nz / l;
      const x0 = Math.min(T[o], T[o + 3], T[o + 6]), x1 = Math.max(T[o], T[o + 3], T[o + 6]);
      const z0 = Math.min(T[o + 2], T[o + 5], T[o + 8]), z1 = Math.max(T[o + 2], T[o + 5], T[o + 8]);
      this.add(this.tGrid, x0, z0, x1, z1, t);
    }
    const W = this.walls, R = 1.2;
    for (let w = 0; w < W.length / 6; w++) {
      const o = w * 6;
      this.add(this.wGrid, Math.min(W[o], W[o + 2]) - R, Math.min(W[o + 1], W[o + 3]) - R,
        Math.max(W[o], W[o + 2]) + R, Math.max(W[o + 1], W[o + 3]) + R, w);
    }
    this.stamp = new Uint32Array(Math.max(1, W.length / 6));
    this.tick = 0;
  }

  add(grid, x0, z0, x1, z1, id) {
    for (let ix = Math.floor(x0 / CELL); ix <= Math.floor(x1 / CELL); ix++) {
      for (let iz = Math.floor(z0 / CELL); iz <= Math.floor(z1 / CELL); iz++) {
        const k = key(ix, iz);
        let a = grid.get(k);
        if (!a) grid.set(k, (a = []));
        a.push(id);
      }
    }
  }

  /**
   * (x, z) 往下找地面：取 yTop 以下最高的那一面（橋下的車找得到下層路面）。
   * 找到就寫進 out（y、法向量 nx ny nz、地面種類 surf）並回傳 out，找不到回傳 null。
   */
  ground(x, z, yTop, out) {
    const list = this.tGrid.get(key(Math.floor(x / CELL), Math.floor(z / CELL)));
    if (!list) return null;
    const T = this.tris;
    let best = -Infinity, bt = -1;
    for (let n = 0; n < list.length; n++) {
      const t = list[n], o = t * 9;
      const x0 = T[o], z0 = T[o + 2], x1 = T[o + 3], z1 = T[o + 5], x2 = T[o + 6], z2 = T[o + 8];
      const d = (z1 - z2) * (x0 - x2) + (x2 - x1) * (z0 - z2);
      if (Math.abs(d) < 1e-9) continue;
      const a = ((z1 - z2) * (x - x2) + (x2 - x1) * (z - z2)) / d;
      if (a < -1e-4) continue;
      const b = ((z2 - z0) * (x - x2) + (x0 - x2) * (z - z2)) / d;
      if (b < -1e-4) continue;
      const c = 1 - a - b;
      if (c < -1e-4) continue;
      const y = a * T[o + 1] + b * T[o + 4] + c * T[o + 7];
      if (y <= yTop && y > best) { best = y; bt = t; }
    }
    if (bt < 0) return null;
    out.y = best;
    out.nx = this.norm[bt * 3]; out.ny = this.norm[bt * 3 + 1]; out.nz = this.norm[bt * 3 + 2];
    out.surf = this.surf[bt];
    return out;
  }

  /** 對 (x, z) 半徑 r、高度 y 的圓，逐一回呼附近穿進去的護牆：fn(法向量 nx, nz（從牆指向車）, 穿入深度) */
  eachWallHit(x, z, y, r, fn) {
    const list = this.wGrid.get(key(Math.floor(x / CELL), Math.floor(z / CELL)));
    if (!list) return;
    const W = this.walls;
    if (++this.tick === 0xffffffff) { this.stamp.fill(0); this.tick = 1; }
    for (let n = 0; n < list.length; n++) {
      const w = list[n];
      if (this.stamp[w] === this.tick) continue;
      this.stamp[w] = this.tick;
      const o = w * 6;
      if (y < W[o + 4] - 0.6 || y > W[o + 5]) continue;
      const ax = W[o], az = W[o + 1], ex = W[o + 2] - ax, ez = W[o + 3] - az;
      const l2 = ex * ex + ez * ez;
      let u = l2 > 0 ? ((x - ax) * ex + (z - az) * ez) / l2 : 0;
      u = u < 0 ? 0 : u > 1 ? 1 : u;
      const px = ax + ex * u, pz = az + ez * u;
      let dx = x - px, dz = z - pz;
      const d = Math.hypot(dx, dz);
      if (d >= r) continue;
      if (d < 1e-6) { const l = Math.sqrt(l2) || 1; dx = -ez / l; dz = ex / l; } else { dx /= d; dz /= d; }
      fn(dx, dz, r - d);
    }
  }
}
