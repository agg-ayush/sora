import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";

import { EASE_IN_OUT, H, W } from "./theme";

/* World-coordinate camera shared by the content layer and the screen-space
   cursor, so the cursor stays a constant size while the camera zooms. */

export type K = { f: number; x: number; y: number; z: number };
export type Rect = { x: number; y: number; w: number; h: number };

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

function seg(f: number, keys: [number, number][]) {
  if (f <= keys[0][0]) return keys[0][1];
  for (let i = 0; i < keys.length - 1; i++) {
    const [f0, v0] = keys[i];
    const [f1, v1] = keys[i + 1];
    if (f <= f1) return interpolate(f, [f0, f1], [v0, v1], { ...clamp, easing: EASE_IN_OUT });
  }
  return keys[keys.length - 1][1];
}

export function camAt(keys: K[], f: number) {
  // Interpolate zoom in log space so push-ins feel even.
  const z = Math.exp(seg(f, keys.map((k) => [k.f, Math.log(k.z)])));
  let x = seg(f, keys.map((k) => [k.f, k.x]));
  let y = seg(f, keys.map((k) => [k.f, k.y]));
  if (z >= 1) {
    const hx = W / 2 / z;
    const hy = H / 2 / z;
    x = Math.min(W - hx, Math.max(hx, x));
    y = Math.min(H - hy, Math.max(hy, y));
  }
  return { x, y, z };
}

export const FULL = { x: W / 2, y: H / 2, z: 1 };

/** Camera framing that fits `r` (plus padding) fully on screen. */
export function fit(r: Rect, pad = 70, max = 2.6) {
  const z = Math.max(1, Math.min(max, (W - 2 * pad) / r.w, (H - 2 * pad) / r.h));
  return { x: r.x + r.w / 2, y: r.y + r.h / 2, z };
}

export const at = (f: number, c: { x: number; y: number; z: number }): K => ({ f, ...c });

export const Cam: React.FC<{ keys: K[]; children: React.ReactNode }> = ({ keys, children }) => {
  const f = useCurrentFrame();
  const { x, y, z } = camAt(keys, f);
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `translate(${W / 2}px, ${H / 2}px) scale(${z}) translate(${-x}px, ${-y}px)`, transformOrigin: "0 0" }}>{children}</AbsoluteFill>
    </AbsoluteFill>
  );
};

export type CK = { f: number; x: number; y: number };

/** Cursor positioned in world coords, drawn in screen space at a fixed size. */
export const WorldCursor: React.FC<{ cam: K[]; keys: CK[]; clicks?: number[]; from: number; to?: number; color?: string }> = ({ cam, keys, clicks = [], from, to = 1e9, color = "#0d80f2" }) => {
  const f = useCurrentFrame();
  if (f < from || f > to) return null;
  const c = camAt(cam, f);
  const wx = seg(f, keys.map((k) => [k.f, k.x]));
  const wy = seg(f, keys.map((k) => [k.f, k.y]));
  const sx = (wx - c.x) * c.z + W / 2;
  const sy = (wy - c.y) * c.z + H / 2;
  const active = clicks.find((k) => f >= k && f < k + 16);
  const press = clicks.some((k) => f >= k - 2 && f < k + 4) ? 0.82 : 1;
  const ring = active !== undefined ? (f - active) / 16 : -1;
  const appear = interpolate(f, [from, from + 6], [0, 1], clamp);
  return (
    <div style={{ position: "absolute", left: sx, top: sy, pointerEvents: "none", opacity: appear }}>
      {ring >= 0 && (
        <div style={{ position: "absolute", left: -30, top: -30, width: 60, height: 60, borderRadius: 999, border: `4px solid ${color}`, opacity: 1 - ring, transform: `scale(${0.4 + ring * 1.3})` }} />
      )}
      <svg width="40" height="47" viewBox="0 0 17 20" style={{ transform: `scale(${press})`, transformOrigin: "0 0", filter: "drop-shadow(0 4px 6px rgba(0,0,0,.35))" }}>
        <path d="M1 1 L1 16 L5 12.2 L7.6 18.4 L10.2 17.3 L7.7 11.3 L13 11.3 Z" fill="#111" stroke="#fff" strokeWidth="1.3" strokeLinejoin="round" />
      </svg>
    </div>
  );
};

/* timing helpers */
export const p01 = (f: number, a: number, d = 12) => interpolate(f, [a, a + d], [0, 1], { ...clamp, easing: EASE_IN_OUT });
export const pulse = (f: number, a: number, d = 18) => (f < a || f > a + d ? 0 : Math.sin((Math.PI * (f - a)) / d));
export const hold = (f: number, a: number, b: number, d = 8) => Math.min(p01(f, a, d), 1 - p01(f, b, d));

/* sound effect at a scene-relative frame */
export const Sfx: React.FC<{ at: number; name: string; vol?: number; len?: number }> = ({ at, name, vol = 0.5, len = 45 }) => (
  <Sequence from={Math.round(at)} durationInFrames={len} layout="none">
    <Audio src={staticFile(`sfx/${name}.wav`)} volume={vol} />
  </Sequence>
);
