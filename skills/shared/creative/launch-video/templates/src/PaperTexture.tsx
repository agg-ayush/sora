import React from "react";
import { AbsoluteFill } from "remotion";

import { C } from "./theme";

// Deterministic PRNG so the texture is identical on every render.
let s = 1234567;
const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);

const FIBERS = Array.from({ length: 1400 }, () => {
  const x = r() * 1920;
  const y = r() * 1080;
  const len = 4 + r() * 14;
  const a = r() * Math.PI * 2;
  const bend = (r() - 0.5) * 6;
  const x2 = x + Math.cos(a) * len;
  const y2 = y + Math.sin(a) * len;
  const cx = (x + x2) / 2 + Math.cos(a + Math.PI / 2) * bend;
  const cy = (y + y2) / 2 + Math.sin(a + Math.PI / 2) * bend;
  const dark = r() < 0.18;
  return { d: `M${x.toFixed(1)} ${y.toFixed(1)} Q${cx.toFixed(1)} ${cy.toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`, dark, w: 0.5 + r() * 0.6 };
});
const SPECKS = Array.from({ length: 420 }, () => ({ x: r() * 1920, y: r() * 1080, rr: 0.4 + r() * 1.1, o: 0.15 + r() * 0.5 }));

/** Off-white paper: soft mottling, fine fibres and specks (rendered once to public/paper.png). */
export const PaperTexture: React.FC = () => (
  <AbsoluteFill style={{ background: C.paper }}>
    <svg width={1920} height={1080}>
      <defs>
        <filter id="mottle" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.0045" numOctaves={4} seed={3} />
          <feColorMatrix type="matrix" values="0 0 0 0 0.45  0 0 0 0 0.42  0 0 0 0 0.37  0 0 0 0.085 0" />
        </filter>
        <filter id="grain" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={9} />
          <feColorMatrix type="matrix" values="0 0 0 0 0.3  0 0 0 0 0.28  0 0 0 0 0.25  0 0 0 0.05 0" />
        </filter>
      </defs>
      <rect width="1920" height="1080" filter="url(#mottle)" />
      <rect width="1920" height="1080" filter="url(#grain)" />
      {FIBERS.map((f, i) => (
        <path key={i} d={f.d} stroke={f.dark ? "rgba(70,62,52,0.45)" : "rgba(150,138,120,0.32)"} strokeWidth={f.w} fill="none" strokeLinecap="round" />
      ))}
      {SPECKS.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={p.rr} fill={`rgba(45,40,35,${p.o})`} />
      ))}
    </svg>
  </AbsoluteFill>
);
