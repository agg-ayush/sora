import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame } from "remotion";

import { AccentBar, Paper, RunningHead } from "./apps";
import { Check, McpKnot } from "./kit";
import { Sfx } from "./scenes-new";
import { C, MONO, SANS, SERIF, prog } from "./theme";

/* Timeline (frames, scene-local). VO "consol1" starts at 8:
   pieces are named at ~3.06s / 5.02s / 7.35s into the clip. */
const CARD_IN = [100, 159, 229];
const LASSO = [296, 326];
const MERGE = [330, 368];
const UNIFIED = 356;

type Piece = {
  title: string;
  kind: string;
  icon: React.ReactNode;
  tools: string[];
  slots: number;
  coverage: number;
  gap: string;
};

const PIECES: Piece[] = [
  {
    title: "Old MCP",
    kind: "MCP server",
    icon: <McpKnot size={34} color={C.ink} width={13} />,
    tools: ["search_entities", "get_entity"],
    slots: 5,
    coverage: 0.08,
    gap: "Support entities only",
  },
  {
    title: "App API",
    kind: "REST · /api/v1",
    icon: <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, color: C.ink }}>{"{ }"}</span>,
    tools: ["POST /requests", "POST /uploads", "POST …/submit-to-support"],
    slots: 5,
    coverage: 0.42,
    gap: "Stops at submission",
  },
  {
    title: "Help desk API",
    kind: "Help desk REST",
    icon: <Img src={staticFile("logo.png")} style={{ width: 36, height: 31, objectFit: "contain" }} />,
    tools: ["GET /tickets", "POST /ticket_articles", "PUT /tickets/{id}"],
    slots: 5,
    coverage: 0.45,
    gap: "Separate API, separate login",
  },
];

const CARD_W = 470;
const CARD_H = 440;
const CARD_X = [140, 725, 1310];
const CARD_Y = 336;

const PieceCard: React.FC<{ p: Piece; i: number }> = ({ p, i }) => {
  const f = useCurrentFrame();
  const inP = prog(f, CARD_IN[i], 20);
  const m = prog(f, MERGE[0] + i * 3, MERGE[1] - MERGE[0], Easing.inOut(Easing.cubic));
  const cx = CARD_X[i] + CARD_W / 2;
  const dx = (960 - cx) * m;
  const dy = (560 - (CARD_Y + CARD_H / 2)) * m;
  const sc = 1 - 0.55 * m;
  const fill = prog(f, CARD_IN[i] + 14, 26) * p.coverage;
  return (
    <div
      style={{
        position: "absolute",
        left: CARD_X[i],
        top: CARD_Y,
        width: CARD_W,
        height: CARD_H,
        opacity: inP * (1 - prog(f, MERGE[1] - 14, 12)),
        transform: `translate(${dx}px, ${dy + (1 - inP) * 34}px) scale(${sc}) rotate(${(i - 1) * 2 * (1 - inP) + (i - 1) * -6 * m}deg)`,
        background: "#fbfaf7",
        border: `2px dashed rgba(30,33,36,.45)`,
        borderRadius: 18,
        padding: "26px 28px",
        fontFamily: SANS,
        color: C.ink,
        boxShadow: "0 22px 44px -34px rgba(40,35,25,.5)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ width: 58, height: 58, borderRadius: 14, border: "1.5px solid rgba(30,33,36,.25)", display: "inline-flex", alignItems: "center", justifyContent: "center", background: "#fff" }}>{p.icon}</span>
        <div>
          <div style={{ fontFamily: SERIF, fontSize: 34, fontWeight: 700, lineHeight: 1.05 }}>{p.title}</div>
          <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: 2, color: C.ink2, marginTop: 4 }}>{p.kind.toUpperCase()}</div>
        </div>
      </div>
      <div style={{ marginTop: 22, display: "grid", gap: 9 }}>
        {Array.from({ length: p.slots }, (_, k) => {
          const t = p.tools[k];
          const rp = prog(f, CARD_IN[i] + 8 + k * 3, 10);
          return t ? (
            <div key={k} style={{ height: 34, borderRadius: 8, background: "#fff", border: "1px solid rgba(30,33,36,.18)", display: "flex", alignItems: "center", padding: "0 12px", fontFamily: MONO, fontSize: 17, opacity: rp }}>
              {t}
            </div>
          ) : (
            <div key={k} style={{ height: 34, borderRadius: 8, border: "1.5px dashed rgba(30,33,36,.22)", opacity: rp * 0.9 }} />
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 28, right: 28, bottom: 26 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 15, fontWeight: 600, letterSpacing: 2, color: C.ink2 }}>
          <span>COVERAGE</span>
          <span style={{ fontVariantNumeric: "tabular-nums" }}>{Math.round(fill * 100)}%</span>
        </div>
        <div style={{ marginTop: 8, height: 8, borderRadius: 4, background: "rgba(30,33,36,.08)" }}>
          <div style={{ width: `${fill * 100}%`, height: 8, borderRadius: 4, background: C.claudeInk }} />
        </div>
        <div style={{ marginTop: 12, fontSize: 20, fontWeight: 600, color: C.claudeInk, opacity: prog(f, CARD_IN[i] + 26, 12) }}>✕ {p.gap}</div>
      </div>
    </div>
  );
};

const CAPS = [
  "Requests & drafts",
  "Documents & AI review",
  "Submit to Support",
  "Tickets & threads",
  "Replies & internal notes",
  "Attachments",
  "Sharing",
  "Ticket state & owner",
];

const Unified: React.FC = () => {
  const f = useCurrentFrame();
  const p = prog(f, UNIFIED, 22, Easing.bezier(0.34, 1.3, 0.64, 1));
  const bar = prog(f, UNIFIED + 16, 34, Easing.inOut(Easing.cubic));
  return (
    <div
      style={{
        position: "absolute",
        left: 960 - 470,
        top: 330,
        width: 940,
        height: 440,
        opacity: Math.min(1, p * 1.4),
        transform: `scale(${0.82 + 0.18 * p})`,
        background: "#fff",
        border: `2px solid ${C.ink}`,
        borderRadius: 22,
        padding: "34px 40px",
        fontFamily: SANS,
        color: C.ink,
        boxShadow: "0 40px 80px -50px rgba(13,128,242,.55)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <span style={{ width: 74, height: 74, borderRadius: 18, background: C.primarySoft, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
          <McpKnot size={44} color={C.primary} width={13} />
        </span>
        <div>
          <div style={{ fontFamily: SERIF, fontSize: 46, fontWeight: 700, lineHeight: 1.05 }}>Product MCP + API</div>
          <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: 2.5, color: C.primary, marginTop: 6 }}>ONE SIGN-IN · YOUR PERMISSIONS</div>
        </div>
      </div>
      <div style={{ marginTop: 30, display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 30, rowGap: 16 }}>
        {CAPS.map((c, k) => {
          const cp = prog(f, UNIFIED + 12 + k * 4, 12);
          return (
            <div key={c} style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 27, opacity: cp, transform: `translateX(${(1 - cp) * 14}px)` }}>
              <span style={{ width: 30, height: 30, borderRadius: 99, background: "#e2f5eb", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                <Check size={18} color={C.success} draw={prog(f, UNIFIED + 16 + k * 4, 10)} />
              </span>
              {c}
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 40, right: 40, bottom: 32 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 16, fontWeight: 600, letterSpacing: 2, color: C.ink2 }}>
          <span>COVERAGE</span>
          <span style={{ color: C.success, fontVariantNumeric: "tabular-nums" }}>{Math.round(bar * 100)}%</span>
        </div>
        <div style={{ marginTop: 8, height: 10, borderRadius: 5, background: "rgba(30,33,36,.08)" }}>
          <div style={{ width: `${bar * 100}%`, height: 10, borderRadius: 5, background: C.success }} />
        </div>
      </div>
    </div>
  );
};

/** Hand-inked loop drawn around the three pieces. */
const Lasso: React.FC = () => {
  const f = useCurrentFrame();
  const d = prog(f, LASSO[0], LASSO[1] - LASSO[0], Easing.inOut(Easing.cubic));
  const shrink = prog(f, MERGE[0], MERGE[1] - MERGE[0], Easing.inOut(Easing.cubic));
  const fade = 1 - prog(f, MERGE[1] - 16, 14);
  if (d <= 0) return null;
  const sx = 1 - 0.55 * shrink;
  return (
    <svg width={1920} height={1080} style={{ position: "absolute", inset: 0, opacity: fade }}>
      <g transform={`translate(960 556) scale(${sx}) translate(-960 -556)`}>
        <path
          d="M 900 290 C 1400 270, 1862 320, 1868 552 C 1874 778, 1440 834, 960 830 C 480 826, 56 776, 60 556 C 64 336, 480 284, 1010 296"
          fill="none"
          stroke={C.primary}
          strokeWidth={5}
          strokeLinecap="round"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - d}
        />
      </g>
    </svg>
  );
};

export const SceneConsolidate: React.FC = () => {
  const f = useCurrentFrame();
  const beforeOut = prog(f, MERGE[0], 16);
  const nowIn = prog(f, UNIFIED + 4, 16);
  const head = (text: string, o: number, color: string) => (
    <div style={{ position: "absolute", left: 100, top: 74, opacity: o }}>
      <AccentBar color={color} />
      <div style={{ marginTop: 18, fontFamily: SERIF, fontSize: 52, fontWeight: 600, color: C.ink, letterSpacing: -0.6 }}>{text}</div>
    </div>
  );
  return (
    <AbsoluteFill>
      <Paper />
      <RunningHead text={f < UNIFIED ? "BEFORE" : "NOW"} color={f < UNIFIED ? C.claudeInk : C.primary} />
      {head("Before: three half-built pieces.", prog(f, 6, 16) * (1 - beforeOut), C.claudeInk)}
      {head("Now: one MCP and API for everything.", nowIn, C.primary)}
      {PIECES.map((p, i) => (
        <PieceCard key={p.title} p={p} i={i} />
      ))}
      <Lasso />
      <Unified />
      {/* flash ring at the merge point */}
      {(() => {
        const t = prog(f, MERGE[1] - 8, 26);
        if (t <= 0 || t >= 1) return null;
        return <div style={{ position: "absolute", left: 960 - 60 - 360 * t, top: 560 - 60 - 220 * t, width: 120 + 720 * t, height: 120 + 440 * t, borderRadius: 30, border: `2px solid ${C.primary}`, opacity: (1 - t) * 0.6 }} />;
      })()}

      {CARD_IN.map((c) => (
        <Sfx key={c} at={c} name="pop" v={0.3} />
      ))}
      <Sfx at={LASSO[0]} name="whoosh" v={0.18} />
      <Sfx at={MERGE[0] - 6} name="riser" v={0.12} />
      <Sfx at={MERGE[1] - 6} name="chime" v={0.26} />
    </AbsoluteFill>
  );
};

export const CONSOLIDATE_FRAMES = 460;
export { interpolate };
