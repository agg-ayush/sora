import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";

import { CLAUDE_PATH } from "./claude-path";
import { C, H, MONO, SANS, W, keyed, prog } from "./theme";

/* ---------------------------------------------------------------- icons */

export const ClaudeMark: React.FC<{ size?: number; color?: string }> = ({
  size = 24,
  color = C.claude,
}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={color} fillRule="evenodd">
    <path d={CLAUDE_PATH} />
  </svg>
);

const KNOT = [
  "M25 97.8528L92.8823 29.9706C102.255 20.598 117.451 20.598 126.823 29.9706V29.9706C136.196 39.3431 136.196 54.5391 126.823 63.9117L75.5581 115.177",
  "M76.2653 114.47L126.823 63.9117C136.196 54.5391 151.392 54.5391 160.765 63.9117L161.118 64.2652C170.491 73.6378 170.491 88.8338 161.118 98.2063L99.7248 159.6C96.6006 162.724 96.6006 167.789 99.7248 170.913L112.331 183.52",
  "M109.853 46.9411L59.6482 97.1457C50.2757 106.518 50.2757 121.714 59.6482 131.087V131.087C69.0208 140.459 84.2168 140.459 93.5894 131.087L143.794 80.8822",
];

/** The MCP knot. `draw` 0→1 animates the strokes being drawn. */
export const McpKnot: React.FC<{ size?: number; color?: string; draw?: number; width?: number }> = ({
  size = 48,
  color = "currentColor",
  draw = 1,
  width = 12,
}) => (
  <svg width={size} height={size} viewBox="14 14 164 178" fill="none" stroke={color} strokeWidth={width} strokeLinecap="round">
    {KNOT.map((d, i) => {
      const local = Math.max(0, Math.min(1, draw * 1.6 - i * 0.3));
      return <path key={i} d={d} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - local} />;
    })}
  </svg>
);

export const ScaleIcon: React.FC<{ size?: number; color?: string; width?: number }> = ({
  size = 24,
  color = "currentColor",
  width = 2,
}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round">
    <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
    <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
    <path d="M7 21h10" />
    <path d="M12 3v18" />
    <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
  </svg>
);

export const Check: React.FC<{ size?: number; color?: string; draw?: number }> = ({
  size = 20,
  color = "currentColor",
  draw = 1,
}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12.5l4.5 4.5L19 7.5" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} />
  </svg>
);

export const Wrench: React.FC<{ size?: number; color?: string }> = ({ size = 16, color = "currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
);

export const GoogleG: React.FC<{ size?: number }> = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48">
    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
    <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
  </svg>
);

export const HelpDeskLogo: React.FC<{ size?: number }> = ({ size = 28 }) => (
  <Img src={staticFile("logo.png")} style={{ width: size, height: size * 0.86, objectFit: "contain" }} />
);

/* --------------------------------------------------------- Clawd mascot */

// Pixel-art Claude mascot. X = body, E = eye.
const CLAWD = [
  "..XXXXXXXX..",
  "..XEXXXXEX..",
  "..XEXXXXEX..",
  "XXXXXXXXXXXX",
  "XXXXXXXXXXXX",
  "..XXXXXXXX..",
  "..X.X..X.X..",
  "..X.X..X.X..",
];

export const Clawd: React.FC<{
  size?: number; // width in px
  blink?: boolean;
  walk?: number; // phase; legs alternate when set
  wave?: number; // 0..1 raises the right arm
}> = ({ size = 120, blink = false, walk, wave = 0 }) => {
  const cell = size / 12;
  const rects: React.ReactNode[] = [];
  CLAWD.forEach((row, y) =>
    [...row].forEach((ch, x) => {
      if (ch === ".") return;
      const isEye = ch === "E";
      if (isEye && blink && y === 1) {
        rects.push(<rect key={`${x}-${y}`} x={x * cell} y={y * cell} width={cell} height={cell} fill={C.claude} />);
        return;
      }
      let dy = 0;
      if (y >= 6 && walk !== undefined) {
        const pair = x === 2 || x === 7 ? 0 : 1;
        dy = Math.sin(walk + pair * Math.PI) > 0 ? -cell * 0.45 : 0;
      }
      // right arm (x=10,11 rows 3-4) lifts with wave
      if ((x === 10 || x === 11) && (y === 3 || y === 4) && wave > 0) {
        dy = -cell * 1.1 * wave * (x === 11 ? 1.3 : 1);
      }
      rects.push(
        <rect
          key={`${x}-${y}`}
          x={x * cell}
          y={y * cell + dy}
          width={cell + 0.5}
          height={cell + 0.5}
          fill={isEye ? "#000" : C.claude}
        />
      );
    })
  );
  return (
    <svg width={size} height={(size / 12) * 8.5} viewBox={`0 ${-cell * 2} ${size} ${cell * 10.5}`} style={{ overflow: "visible" }}>
      {rects}
    </svg>
  );
};

/* ----------------------------------------------------------- person */

export const Person: React.FC<{ size?: number; mood: "tired" | "happy"; sweat?: number }> = ({
  size = 220,
  mood,
  sweat = 0,
}) => (
  <svg width={size} height={size} viewBox="0 0 200 200">
    <defs>
      <linearGradient id="shirt" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#3b8cf0" />
        <stop offset="1" stopColor="#1e5fbf" />
      </linearGradient>
    </defs>
    <path d="M30 200 C30 150 60 128 100 128 C140 128 170 150 170 200 Z" fill="url(#shirt)" />
    <rect x="88" y="108" width="24" height="26" rx="8" fill="#e9b48f" />
    <circle cx="100" cy="80" r="42" fill="#f2c6a0" />
    <path d="M58 76 C58 46 80 34 102 34 C126 34 144 48 142 74 C134 60 120 54 100 56 C82 58 68 64 58 76 Z" fill="#2a2f3a" />
    {mood === "tired" ? (
      <>
        <path d="M78 84 h14" stroke="#2a2f3a" strokeWidth="4" strokeLinecap="round" />
        <path d="M108 84 h14" stroke="#2a2f3a" strokeWidth="4" strokeLinecap="round" />
        <path d="M76 76 l16 4" stroke="#2a2f3a" strokeWidth="3" strokeLinecap="round" />
        <path d="M124 76 l-16 4" stroke="#2a2f3a" strokeWidth="3" strokeLinecap="round" />
        <path d="M88 106 q12 -8 24 0" stroke="#7a3b2e" strokeWidth="4" fill="none" strokeLinecap="round" />
        <path
          d="M140 50 q8 12 0 18 q-8 -6 0 -18 Z"
          fill="#7cc6ff"
          opacity={sweat}
          transform={`translate(0 ${sweat * 6})`}
        />
      </>
    ) : (
      <>
        <path d="M78 86 q7 -8 14 0" stroke="#2a2f3a" strokeWidth="4" fill="none" strokeLinecap="round" />
        <path d="M108 86 q7 -8 14 0" stroke="#2a2f3a" strokeWidth="4" fill="none" strokeLinecap="round" />
        <path d="M84 100 q16 16 32 0" stroke="#7a3b2e" strokeWidth="4" fill="#fff" strokeLinecap="round" />
        <circle cx="72" cy="96" r="6" fill="#f59f9f" opacity="0.5" />
        <circle cx="128" cy="96" r="6" fill="#f59f9f" opacity="0.5" />
      </>
    )}
  </svg>
);

/* ------------------------------------------------------------ cursor */

export type CursorKey = { f: number; x: number; y: number };

export const Cursor: React.FC<{ keys: CursorKey[]; clicks?: number[]; visibleFrom?: number }> = ({
  keys,
  clicks = [],
  visibleFrom = 0,
}) => {
  const f = useCurrentFrame();
  if (f < visibleFrom) return null;
  const x = keyed(f, keys.map((k) => [k.f, k.x]));
  const y = keyed(f, keys.map((k) => [k.f, k.y]));
  const active = clicks.find((c) => f >= c && f < c + 16);
  const press = clicks.some((c) => f >= c - 2 && f < c + 4) ? 0.82 : 1;
  const ring = active !== undefined ? (f - active) / 16 : -1;
  return (
    <div style={{ position: "absolute", left: x, top: y, pointerEvents: "none", zIndex: 50 }}>
      {ring >= 0 && (
        <div
          style={{
            position: "absolute",
            left: -26,
            top: -26,
            width: 52,
            height: 52,
            borderRadius: 999,
            border: `4px solid ${C.primary}`,
            opacity: 1 - ring,
            transform: `scale(${0.4 + ring * 1.3})`,
          }}
        />
      )}
      <svg width="34" height="40" viewBox="0 0 17 20" style={{ transform: `scale(${press})`, transformOrigin: "0 0", filter: "drop-shadow(0 4px 6px rgba(0,0,0,.35))" }}>
        <path d="M1 1 L1 16 L5 12.2 L7.6 18.4 L10.2 17.3 L7.7 11.3 L13 11.3 Z" fill="#111" stroke="#fff" strokeWidth="1.3" strokeLinejoin="round" />
      </svg>
    </div>
  );
};

/* ------------------------------------------------------------ camera */

export type CamKey = { f: number; x: number; y: number; z: number };

/** Children are laid out in 1920x1080 space; the camera centres (x,y) at zoom z. */
export const Camera: React.FC<{ keys: CamKey[]; children: React.ReactNode }> = ({ keys, children }) => {
  const f = useCurrentFrame();
  const z = keyed(f, keys.map((k) => [k.f, k.z]));
  // Never pan past the frame edge: keep the visible window inside 1920x1080.
  const hx = W / 2 / z;
  const hy = H / 2 / z;
  const clampTo = (v: number, lo: number, hi: number) => (lo > hi ? (lo + hi) / 2 : Math.min(hi, Math.max(lo, v)));
  const x = clampTo(keyed(f, keys.map((k) => [k.f, k.x])), hx, W - hx);
  const y = clampTo(keyed(f, keys.map((k) => [k.f, k.y])), hy, H - hy);
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          transform: `translate(${W / 2}px, ${H / 2}px) scale(${z}) translate(${-x}px, ${-y}px)`,
          transformOrigin: "0 0",
        }}
      >
        {children}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/* -------------------------------------------------------- backgrounds */

export const NightBg: React.FC<{ hue?: "blue" | "magic" | "claude" }> = ({ hue = "blue" }) => {
  const f = useCurrentFrame();
  const a = hue === "claude" ? C.claude : C.primary;
  const b = hue === "blue" ? C.magic : hue === "magic" ? C.primary : C.magic;
  return (
    <AbsoluteFill style={{ background: `radial-gradient(1200px 800px at 50% 40%, ${C.night2}, ${C.night})` }}>
      <div
        style={{
          position: "absolute",
          width: 900,
          height: 900,
          borderRadius: 999,
          left: 200 + Math.sin(f / 70) * 80,
          top: -260 + Math.cos(f / 90) * 60,
          background: a,
          opacity: 0.22,
          filter: "blur(160px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 800,
          height: 800,
          borderRadius: 999,
          right: 120 + Math.cos(f / 80) * 90,
          bottom: -300 + Math.sin(f / 60) * 50,
          background: b,
          opacity: 0.2,
          filter: "blur(160px)",
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage: "radial-gradient(rgba(255,255,255,0.07) 1.2px, transparent 1.2px)",
          backgroundSize: "36px 36px",
          maskImage: "radial-gradient(ellipse at center, black 30%, transparent 75%)",
        }}
      />
    </AbsoluteFill>
  );
};

export const LightBg: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.page }}>
      <div style={{ position: "absolute", width: 1000, height: 700, left: -200 + Math.sin(f / 80) * 40, top: -300, background: C.primary, opacity: 0.1, filter: "blur(140px)", borderRadius: 999 }} />
      <div style={{ position: "absolute", width: 900, height: 700, right: -200, bottom: -300 + Math.cos(f / 70) * 40, background: C.magic, opacity: 0.1, filter: "blur(140px)", borderRadius: 999 }} />
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------- UI primitives */

export const Window: React.FC<{
  x: number;
  y: number;
  w: number;
  h: number;
  title?: React.ReactNode;
  children?: React.ReactNode;
  style?: React.CSSProperties;
  bg?: string;
}> = ({ x, y, w, h, title, children, style, bg = C.card }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: w,
      height: h,
      borderRadius: 22,
      background: bg,
      border: `1px solid ${C.border}`,
      boxShadow: "0 40px 120px -40px rgba(0,0,0,.55), 0 10px 30px -15px rgba(0,0,0,.3)",
      overflow: "hidden",
      fontFamily: SANS,
      color: C.fg,
      ...style,
    }}
  >
    <div style={{ height: 48, display: "flex", alignItems: "center", gap: 9, padding: "0 20px", borderBottom: `1px solid ${C.border}`, background: "rgba(255,255,255,.7)" }}>
      <span style={{ width: 13, height: 13, borderRadius: 99, background: "#ff5f57" }} />
      <span style={{ width: 13, height: 13, borderRadius: 99, background: "#febc2e" }} />
      <span style={{ width: 13, height: 13, borderRadius: 99, background: "#28c840" }} />
      <div style={{ marginLeft: 16, fontSize: 17, color: C.muted, fontWeight: 500 }}>{title}</div>
    </div>
    <div style={{ position: "relative", height: h - 48 }}>{children}</div>
  </div>
);

export const Pill: React.FC<{ children: React.ReactNode; color?: string; bg?: string; style?: React.CSSProperties }> = ({
  children,
  color = C.primary,
  bg = C.primarySoft,
  style,
}) => (
  <span
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 8,
      padding: "6px 14px",
      borderRadius: 999,
      background: bg,
      color,
      fontWeight: 600,
      fontSize: 18,
      fontFamily: SANS,
      ...style,
    }}
  >
    {children}
  </span>
);

/** Kinetic headline: each word rises in with a stagger. */
export const Words: React.FC<{
  text: string;
  start: number;
  stagger?: number;
  style?: React.CSSProperties;
  highlight?: Record<string, string>;
}> = ({ text, start, stagger = 3, style, highlight = {} }) => {
  const f = useCurrentFrame();
  return (
    <div style={{ fontFamily: SANS, display: "flex", flexWrap: "wrap", justifyContent: "center", columnGap: "0.28em", ...style }}>
      {text.split(" ").map((w, i) => {
        const p = prog(f, start + i * stagger, 16);
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              opacity: p,
              transform: `translateY(${(1 - p) * 40}px)`,
              filter: `blur(${(1 - p) * 8}px)`,
              color: highlight[w] ?? undefined,
            }}
          >
            {w}
          </span>
        );
      })}
    </div>
  );
};

export const Caret: React.FC<{ color?: string; h?: number }> = ({ color = C.primary, h = 1 }) => {
  const f = useCurrentFrame();
  return (
    <span
      style={{
        display: "inline-block",
        width: 4,
        height: `${h}em`,
        marginLeft: 4,
        background: color,
        verticalAlign: "-0.12em",
        opacity: Math.floor(f / 15) % 2 === 0 ? 1 : 0,
      }}
    />
  );
};

export const mono = MONO;
