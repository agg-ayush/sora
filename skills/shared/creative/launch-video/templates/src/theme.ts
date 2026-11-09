import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { loadFont as loadSerif } from "@remotion/google-fonts/SourceSerif4";
import { Easing, interpolate } from "remotion";

export const { fontFamily: SANS } = loadInter("normal", {
  weights: ["400", "500", "600", "700", "800"],
  subsets: ["latin"],
});
export const { fontFamily: SERIF } = loadSerif("normal", {
  weights: ["400", "600", "700"],
  subsets: ["latin"],
});
export const { fontFamily: MONO } = loadMono("normal", {
  weights: ["400", "600"],
  subsets: ["latin"],
});

// Neutral design tokens (light theme). Change `primary` to the product accent.
export const C = {
  night: "#060a14",
  night2: "#0b1324",
  page: "#f5f7fb",
  card: "#ffffff",
  border: "#d6dde6",
  fg: "#0f1e2e",
  muted: "#456789",
  primary: "#0d80f2",
  primarySoft: "rgba(13,128,242,0.10)",
  magic: "#b247ef",
  magicSoft: "rgba(178,71,239,0.10)",
  success: "#2fbf78",
  warning: "#e8b21f",
  warm: "#D97757",
  warmBg: "#f5f4ee",
  // paper / infographic palette
  paper: "#f4f2ed",
  ink: "#1e2124",
  ink2: "#5b636c",
  hair: "rgba(30,33,36,0.82)",
  warmInk: "#b8572f",
  helpdesk: "#3aa86a", // help-desk accent
};

export const FPS = 30;
export const W = 1920;
export const H = 1080;

export const EASE = Easing.bezier(0.22, 1, 0.36, 1);
export const EASE_IN_OUT = Easing.bezier(0.65, 0, 0.35, 1);

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** 0→1 progress between start and start+dur, eased. */
export const prog = (f: number, start: number, dur = 18, easing = EASE) =>
  interpolate(f, [start, start + dur], [0, 1], { ...clamp, easing });

/** Fade + rise-in style. */
export const rise = (f: number, start: number, dur = 18, dist = 28) => {
  const p = prog(f, start, dur);
  return { opacity: p, transform: `translateY(${(1 - p) * dist}px)` };
};

/** Pop-in (scale) style. */
export const pop = (f: number, start: number, dur = 16) => {
  const p = prog(f, start, dur, Easing.bezier(0.34, 1.56, 0.64, 1));
  return { opacity: Math.min(1, p * 1.5), transform: `scale(${0.6 + 0.4 * p})` };
};

/** Characters of `text` typed so far at `framesPerChar`. */
export const typed = (text: string, f: number, start: number, framesPerChar = 2) =>
  text.slice(0, Math.max(0, Math.min(text.length, Math.floor((f - start) / framesPerChar))));

/** Piecewise eased interpolation over keyframes of numbers. */
export function keyed(f: number, keys: [number, number][], easing = EASE_IN_OUT) {
  if (f <= keys[0][0]) return keys[0][1];
  for (let i = 0; i < keys.length - 1; i++) {
    const [f0, v0] = keys[i];
    const [f1, v1] = keys[i + 1];
    if (f <= f1) return interpolate(f, [f0, f1], [v0, v1], { ...clamp, easing });
  }
  return keys[keys.length - 1][1];
}
