import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";

import { C, H, MONO, SANS, W, keyed, prog } from "./theme";

/* ---------------------------------------------------------------- icons */

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

/** Neutral placeholder brand mark (rounded tile + chevron). Swap for the real logo. */
export const LogoMark: React.FC<{ style?: React.CSSProperties; color?: string }> = ({ style, color = C.primary }) => (
  <svg viewBox="0 0 24 24" style={style}>
    <rect x="1" y="1" width="22" height="22" rx="6" fill={color} />
    <path d="M8 8.5l4 3.5-4 3.5M13.5 15.5h3" fill="none" stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const HelpDeskLogo: React.FC<{ size?: number }> = ({ size = 28 }) => <LogoMark style={{ width: size, height: size }} />;

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

export const NightBg: React.FC<{ hue?: "blue" | "magic" | "warm" }> = ({ hue = "blue" }) => {
  const f = useCurrentFrame();
  const a = hue === "warm" ? C.warm : C.primary;
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
