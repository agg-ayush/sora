// Synthesizes the UI sound effects as 48 kHz mono WAVs (deterministic, seeded).
const fs = require("fs");
const path = require("path");
const SR = 48000;
const OUT = path.join(__dirname, "../public/sfx");
fs.mkdirSync(OUT, { recursive: true });

let seed = 7;
const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296) * 2 - 1;

function write(name, buf, gain = 1) {
  let peak = 0;
  for (const v of buf) peak = Math.max(peak, Math.abs(v));
  const norm = peak > 0 ? (0.89 * gain) / peak : 0;
  const data = Buffer.alloc(44 + buf.length * 2);
  data.write("RIFF", 0);
  data.writeUInt32LE(36 + buf.length * 2, 4);
  data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16);
  data.writeUInt16LE(1, 20);
  data.writeUInt16LE(1, 22);
  data.writeUInt32LE(SR, 24);
  data.writeUInt32LE(SR * 2, 28);
  data.writeUInt16LE(2, 32);
  data.writeUInt16LE(16, 34);
  data.write("data", 36);
  data.writeUInt32LE(buf.length * 2, 40);
  buf.forEach((v, i) => data.writeInt16LE(Math.round(Math.max(-1, Math.min(1, v * norm)) * 32767), 44 + i * 2));
  fs.writeFileSync(path.join(OUT, name + ".wav"), data);
}

const N = (s) => Math.floor(s * SR);
// one-pole lowpass / highpass helpers
function lp(buf, cutoffAt) {
  let y = 0;
  return buf.map((x, i) => {
    const fc = typeof cutoffAt === "function" ? cutoffAt(i / SR) : cutoffAt;
    const a = 1 - Math.exp((-2 * Math.PI * fc) / SR);
    y += a * (x - y);
    return y;
  });
}
function hp(buf, fc) {
  const low = lp(buf, fc);
  return buf.map((x, i) => x - low[i]);
}

// Mouse click: a tiny high tick + soft body.
function click(name, pitch = 1) {
  const n = N(0.06);
  const b = new Array(n).fill(0).map((_, i) => {
    const t = i / SR;
    const tick = rnd() * Math.exp(-t / 0.0015);
    const body = Math.sin(2 * Math.PI * 2100 * pitch * t) * Math.exp(-t / 0.008) * 0.5;
    const low = Math.sin(2 * Math.PI * 180 * pitch * t) * Math.exp(-t / 0.012) * 0.35;
    return tick + body + low;
  });
  write(name, hp(b, 120), 0.7);
}
click("click");
click("click2", 0.88);

// Keyboard taps: short damped noise + thump, 5 variations.
for (let k = 0; k < 5; k++) {
  const n = N(0.07);
  const f0 = 140 + k * 25;
  const b = new Array(n).fill(0).map((_, i) => {
    const t = i / SR;
    return rnd() * Math.exp(-t / (0.004 + k * 0.0006)) * 0.8 + Math.sin(2 * Math.PI * f0 * t) * Math.exp(-t / 0.015) * 0.5;
  });
  write(`key${k}`, lp(lp(hp(b, 200), 3800), 4200), 0.5);
}

// Whoosh: filtered noise swell with a rising then falling cutoff.
{
  const d = 0.8;
  const n = N(d);
  const raw = new Array(n).fill(0).map(() => rnd());
  const cut = (t) => 300 + 3200 * Math.sin(Math.PI * Math.min(1, t / d));
  const f = lp(lp(raw, cut), cut);
  const b = f.map((x, i) => {
    const t = i / SR;
    const env = Math.pow(Math.sin(Math.PI * Math.min(1, t / d)), 1.6);
    return x * env;
  });
  write("whoosh", b, 0.6);
}

// Thwip: a web strand shooting out — quick rising zip.
{
  const d = 0.16;
  const n = N(d);
  let ph = 0;
  const b = new Array(n).fill(0).map((_, i) => {
    const t = i / SR;
    const freq = 700 + 3600 * (t / d);
    ph += (2 * Math.PI * freq) / SR;
    const env = Math.min(1, t / 0.006) * Math.exp(-t / 0.05);
    return (Math.sin(ph) * 0.45 + rnd() * 0.55) * env;
  });
  write("thwip", hp(lp(b, 7000), 400), 0.45);
}

// Soft pluck: action completed.
function bell(name, notes, gap, decay = 0.5, gain = 0.6) {
  const d = gap * notes.length + decay * 2;
  const n = N(d);
  const b = new Array(n).fill(0);
  notes.forEach((hz, j) => {
    const s = N(gap * j);
    for (let i = s; i < n; i++) {
      const t = (i - s) / SR;
      const env = Math.min(1, t / 0.004) * Math.exp(-t / decay);
      b[i] += (Math.sin(2 * Math.PI * hz * t) + 0.35 * Math.sin(2 * Math.PI * hz * 2 * t) + 0.12 * Math.sin(2 * Math.PI * hz * 3.01 * t)) * env;
    }
  });
  write(name, b, gain);
}
bell("pop", [1318.5], 0, 0.18, 0.4);
bell("chime", [659.25, 987.77, 1318.5], 0.09, 0.6, 0.6);

// Title reveal: soft sub impact + airy tail.
{
  const d = 2.2;
  const n = N(d);
  const raw = new Array(n).fill(0).map(() => rnd());
  const air = lp(hp(raw, 2500), 9000);
  const b = new Array(n).fill(0).map((_, i) => {
    const t = i / SR;
    const sub = Math.sin(2 * Math.PI * (52 + 30 * Math.exp(-t / 0.08)) * t) * Math.exp(-t / 0.55);
    return sub * 0.9 + air[i] * Math.exp(-t / 0.7) * 0.25;
  });
  write("impact", b, 0.8);
}

// Riser into the title: noise with rising cutoff and level.
{
  const d = 1.4;
  const n = N(d);
  const raw = new Array(n).fill(0).map(() => rnd());
  const f = lp(raw, (t) => 200 + 5000 * Math.pow(t / d, 2));
  const b = f.map((x, i) => x * Math.pow(i / n, 2.2));
  write("riser", b, 0.5);
}
console.log(fs.readdirSync(OUT).join(" "));
