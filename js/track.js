// 賽道中心線（Blender 腳本輸出的 *_path.json）：把車的位置投影到中心線上，
// 得到沿線距離 s、橫向偏移 d（右正）、該處路面高度與切線。

export class Track {
  constructor(data) {
    this.name = data.name;
    this.step = data.step;
    this.length = data.length;
    this.halfWidth = data.halfWidth;
    this.curb = data.curb;
    this.wall = data.wall;
    this.wallT = data.wallThickness;
    const p = data.pts;
    const n = (this.n = p.length / 3);
    this.x = new Float32Array(n);
    this.y = new Float32Array(n);
    this.z = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      this.x[i] = p[i * 3];
      this.y[i] = p[i * 3 + 1];
      this.z[i] = p[i * 3 + 2];
    }
    this.tx = new Float32Array(n);
    this.tz = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const a = (i - 1 + n) % n, b = (i + 1) % n;
      let dx = this.x[b] - this.x[a], dz = this.z[b] - this.z[a];
      const l = Math.hypot(dx, dz) || 1;
      this.tx[i] = dx / l;
      this.tz[i] = dz / l;
    }
    // 粗格子索引：投影猜測失準時（重生、第一次）才用
    this.cell = 25;
    this.grid = new Map();
    for (let i = 0; i < n; i++) {
      const k = this.key(Math.floor(this.x[i] / this.cell), Math.floor(this.z[i] / this.cell));
      if (!this.grid.has(k)) this.grid.set(k, []);
      this.grid.get(k).push(i);
    }
  }

  key(a, b) { return a * 100003 + b; }

  nearestIndex(x, z) {
    const cx = Math.floor(x / this.cell), cz = Math.floor(z / this.cell);
    let best = Infinity, bi = 0;
    for (let r = 1; r <= 8 && best === Infinity; r++) {
      for (let gx = cx - r; gx <= cx + r; gx++) {
        for (let gz = cz - r; gz <= cz + r; gz++) {
          const list = this.grid.get(this.key(gx, gz));
          if (!list) continue;
          for (const i of list) {
            const d = (this.x[i] - x) ** 2 + (this.z[i] - z) ** 2;
            if (d < best) { best = d; bi = i; }
          }
        }
      }
    }
    return bi;
  }

  /**
   * 投影。hint 是上一幀的取樣索引（-1 表示不知道）。
   * 回傳寫進 out：{ i, s, d, y, tx, tz }
   */
  project(x, z, hint, out) {
    const n = this.n;
    let center = hint >= 0 ? hint : this.nearestIndex(x, z);
    let best = Infinity;
    const R = hint >= 0 ? 14 : 30;
    for (let k = -R; k <= R; k++) {
      const i = (center + k + n) % n, j = (i + 1) % n;
      const ax = this.x[i], az = this.z[i];
      const ex = this.x[j] - ax, ez = this.z[j] - az;
      const l2 = ex * ex + ez * ez;
      let u = ((x - ax) * ex + (z - az) * ez) / l2;
      u = u < 0 ? 0 : u > 1 ? 1 : u;
      const px = ax + ex * u, pz = az + ez * u;
      const d2 = (x - px) ** 2 + (z - pz) ** 2;
      if (d2 < best) {
        best = d2;
        out.i = i;
        out.u = u;
        out.px = px;
        out.pz = pz;
      }
    }
    if (hint >= 0 && best > 40 * 40) return this.project(x, z, -1, out);
    const i = out.i, j = (i + 1) % n, u = out.u;
    let tx = this.tx[i] * (1 - u) + this.tx[j] * u;
    let tz = this.tz[i] * (1 - u) + this.tz[j] * u;
    const l = Math.hypot(tx, tz) || 1;
    tx /= l; tz /= l;
    out.tx = tx;
    out.tz = tz;
    // 右手邊 = (-tz, tx)
    out.d = (x - out.px) * -tz + (z - out.pz) * tx;
    out.y = this.y[i] * (1 - u) + this.y[j] * u;
    out.s = (i + u) * this.step;
    // 坡度：沿切線方向每公尺升高多少
    out.grade = (this.y[j] - this.y[i]) / this.step;
    return out;
  }

  /** 沿線距離 s 處的中心點、切線（重生、起跑格用） */
  pointAt(s) {
    const n = this.n;
    s = ((s % this.length) + this.length) % this.length;
    const f = s / this.step;
    const i = Math.floor(f) % n, j = (i + 1) % n, u = f - Math.floor(f);
    return {
      x: this.x[i] + (this.x[j] - this.x[i]) * u,
      y: this.y[i] + (this.y[j] - this.y[i]) * u,
      z: this.z[i] + (this.z[j] - this.z[i]) * u,
      tx: this.tx[i], tz: this.tz[i], i,
    };
  }
}
