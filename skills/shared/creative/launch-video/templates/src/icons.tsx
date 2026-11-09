import React from "react";

// Lucide icon geometry (24x24, stroke). Strings are paths; tuples are
// circles [cx, cy, r]; objects are rects.
type Part = string | [number, number, number] | { x: number; y: number; w: number; h: number; r?: number };

const I: Record<string, Part[]> = {
  flame: [
    "M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z",
  ],
  hourglass: [
    "M5 22h14",
    "M5 2h14",
    "M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22",
    "M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2",
  ],
  checkCircle: [[12, 12, 10], "m9 12 2 2 4-4"],
  pencil: [
    "M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z",
    "m15 5 4 4",
  ],
  alert: ["m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3", "M12 9v4", "M12 17h.01"],
  userX: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", [9, 7, 4], "m17 8 5 5", "m22 8-5 5"],
  inbox: [
    "M22 12h-6l-2 3h-4l-2-3H2",
    "M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z",
  ],
  clock: [[12, 12, 10], "M12 6v6l4 2"],
  search: [[11, 11, 8], "m21 21-4.3-4.3"],
  arrowUR: ["M7 7h10v10", "M7 17 17 7"],
  user: ["M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2", [12, 7, 4]],
  mail: [{ x: 2, y: 4, w: 20, h: 16, r: 2 }, "m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"],
  sliders: ["M20 7h-9", "M14 17H5", [17, 17, 3], [7, 7, 3]],
  refresh: [
    "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8",
    "M21 3v5h-5",
    "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16",
    "M8 16H3v5",
  ],
  checkCheck: ["M18 6 7 17l-5-5", "m22 10-7.5 7.5L13 16"],
  dashboard: [
    { x: 3, y: 3, w: 7, h: 9, r: 1 },
    { x: 14, y: 3, w: 7, h: 5, r: 1 },
    { x: 14, y: 12, w: 7, h: 9, r: 1 },
    { x: 3, y: 16, w: 7, h: 5, r: 1 },
  ],
  x: ["M18 6 6 18", "m6 6 12 12"],
  tag: [
    "M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z",
    [7.5, 7.5, 0.6],
  ],
  bot: ["M12 8V4H8", { x: 4, y: 8, w: 16, h: 12, r: 2 }, "M2 14h2", "M20 14h2", "M15 13v2", "M9 13v2"],
  file: ["M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z", "M14 2v4a2 2 0 0 0 2 2h4", "M10 13h4", "M10 17h4"],
  scale: [
    "m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z",
    "m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z",
    "M7 21h10",
    "M12 3v18",
    "M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2",
  ],
  message: ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"],
  bell: ["M10.268 21a2 2 0 0 0 3.464 0", "M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"],
  home: ["M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8", "M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"],
  list: ["M3 12h.01", "M3 18h.01", "M3 6h.01", "M8 12h13", "M8 18h13", "M8 6h13"],
  plus: ["M5 12h14", "M12 5v14"],
  chevronDown: ["m6 9 6 6 6-6"],
};

export type IconName = keyof typeof I;

export const Icon: React.FC<{ n: IconName; size?: number; color?: string; width?: number; style?: React.CSSProperties }> = ({
  n,
  size = 20,
  color = "currentColor",
  width = 2,
  style,
}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" style={{ flex: "none", ...style }}>
    {I[n].map((p, i) =>
      typeof p === "string" ? (
        <path key={i} d={p} />
      ) : Array.isArray(p) ? (
        <circle key={i} cx={p[0]} cy={p[1]} r={p[2]} />
      ) : (
        <rect key={i} x={p.x} y={p.y} width={p.w} height={p.h} rx={p.r ?? 0} />
      )
    )}
  </svg>
);
