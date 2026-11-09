// 音效：全部用 WebAudio 合成（不用音檔）。第一次點擊後才能啟動。

export class Sfx {
  constructor() {
    this.ctx = null;
    this.muted = false;
  }

  start() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume(); return; }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = (this.ctx = new AC());
    this.master = ctx.createGain();
    this.master.gain.value = 0.55;
    this.master.connect(ctx.destination);

    // 引擎：兩個鋸齒波＋低通
    this.engGain = ctx.createGain();
    this.engGain.gain.value = 0;
    const lp = (this.engLp = ctx.createBiquadFilter());
    lp.type = 'lowpass';
    lp.frequency.value = 900;
    this.osc1 = ctx.createOscillator();
    this.osc1.type = 'sawtooth';
    this.osc2 = ctx.createOscillator();
    this.osc2.type = 'square';
    const g2 = ctx.createGain();
    g2.gain.value = 0.35;
    this.osc1.connect(lp);
    this.osc2.connect(g2).connect(lp);
    lp.connect(this.engGain).connect(this.master);
    this.osc1.start();
    this.osc2.start();

    // 噪音（甩尾胎聲、噴射、草地）
    const len = ctx.sampleRate * 2;
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    this.noiseBuf = buf;
    const mk = (type, f, q) => {
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.loop = true;
      const bp = ctx.createBiquadFilter();
      bp.type = type;
      bp.frequency.value = f;
      bp.Q.value = q;
      const g = ctx.createGain();
      g.gain.value = 0;
      src.connect(bp).connect(g).connect(this.master);
      src.start();
      return { g, bp };
    };
    this.squeal = mk('bandpass', 1500, 6);
    this.rush = mk('bandpass', 600, 0.8);
    this.rumble = mk('lowpass', 180, 1);
    this.wind = mk('highpass', 900, 0.7); // 風切聲：隨車速變大、變尖
  }

  set(g, v, t = 0.06) {
    if (!this.ctx) return;
    g.gain.setTargetAtTime(this.muted ? 0 : v, this.ctx.currentTime, t);
  }

  update(k, active) {
    if (!this.ctx) return;
    const sp = Math.min(1.6, Math.abs(k.spd) / 34);
    // 引擎：高速段音高拉得更陡（聽起來更「催」）
    const f = 55 + sp * 110 + Math.max(0, sp - 0.6) * 90 + (k.boosting ? 30 : 0);
    const now = this.ctx.currentTime;
    this.osc1.frequency.setTargetAtTime(f, now, 0.05);
    this.osc2.frequency.setTargetAtTime(f * 0.5, now, 0.05);
    this.engLp.frequency.setTargetAtTime(500 + sp * 1600, now, 0.08);
    this.set(this.engGain, active ? 0.13 + sp * 0.08 : 0);
    const slip = Math.min(1, Math.abs(k.slip) / 0.6);
    this.set(this.squeal.g, active && k.drift && !k.onGrass ? 0.05 + slip * 0.1 : 0, 0.04);
    this.squeal.bp.frequency.setTargetAtTime(1200 + slip * 700, now, 0.05);
    this.set(this.rush.g, active && k.boosting ? 0.18 : 0, 0.08);
    this.set(this.rumble.g, active && (k.onGrass || k.onCurb) && Math.abs(k.spd) > 3 ? 0.35 : 0, 0.05);
    this.set(this.wind.g, active ? Math.pow(Math.min(1.3, sp), 2.2) * 0.22 + (k.boosting ? 0.06 : 0) : 0, 0.15);
    this.wind.bp.frequency.setTargetAtTime(700 + sp * 1300, now, 0.2);
  }

  beep(freq, dur = 0.15, type = 'square', vol = 0.25) {
    if (!this.ctx || this.muted) return;
    const o = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    o.type = type;
    o.frequency.value = freq;
    const t = this.ctx.currentTime;
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    o.connect(g).connect(this.master);
    o.start(t);
    o.stop(t + dur + 0.02);
  }

  whoosh(strength = 1) {
    if (!this.ctx || this.muted) return;
    const src = this.ctx.createBufferSource();
    src.buffer = this.noiseBuf;
    const bp = this.ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.Q.value = 1.2;
    const t = this.ctx.currentTime;
    bp.frequency.setValueAtTime(400, t);
    bp.frequency.exponentialRampToValueAtTime(2400, t + 0.35);
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(0.5 * strength, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.5);
    src.connect(bp).connect(g).connect(this.master);
    src.start(t);
    src.stop(t + 0.55);
  }

  bump(impact) {
    if (!this.ctx || this.muted) return;
    const o = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    o.type = 'triangle';
    const t = this.ctx.currentTime;
    o.frequency.setValueAtTime(120, t);
    o.frequency.exponentialRampToValueAtTime(40, t + 0.2);
    g.gain.setValueAtTime(Math.min(0.6, impact * 0.06), t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.25);
    o.connect(g).connect(this.master);
    o.start(t);
    o.stop(t + 0.3);
  }
}
