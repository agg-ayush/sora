import React from "react";
import { AbsoluteFill, Audio, Easing, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";

import { AccentBar, APPA, AppState, AppWindow, APP_H, APP_W, Paper, RunningHead, Stat, HDA, HDState, HDWindow, HD_H, HD_W } from "./apps";
import { Clawd, Cursor, CursorKey, McpKnot, ScaleIcon, HelpDeskLogo } from "./kit";
import { C, EASE, SANS, SERIF, keyed, prog } from "./theme";

/* ------------------------------------------------------------ audio helpers */

export const Sfx: React.FC<{ at: number; name: string; v?: number }> = ({ at, name, v = 0.5 }) => (
  <Sequence from={Math.round(at)} durationInFrames={90} layout="none">
    <Audio src={staticFile(`sfx/${name}.wav`)} volume={v} />
  </Sequence>
);

/** Key taps for a typing range (one tap every `every` frames). */
export const Typing: React.FC<{ from: number; to: number; every?: number; v?: number }> = ({ from, to, every = 2, v = 0.21 }) => (
  <>
    {Array.from({ length: Math.max(0, Math.floor((to - from) / every)) }, (_, i) => (
      <Sfx key={i} at={from + i * every} name={`key${(i * 3) % 5}`} v={v * (0.8 + ((i * 7) % 5) * 0.08)} />
    ))}
  </>
);

/* ------------------------------------------------------------ shared bits */

const Heading: React.FC<{ text: string; start: number; x?: number; y?: number; size?: number; underline?: [number, number]; maxW?: number; accent?: string }> = ({
  text,
  start,
  x = 100,
  y = 74,
  size = 54,
  maxW = 1150,
  accent = C.primary,
}) => {
  const f = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: x, top: y, maxWidth: maxW }}>
      <AccentBar p={prog(f, start, 14)} color={accent} />
      <div style={{ marginTop: 18, fontFamily: SERIF, fontSize: size, fontWeight: 600, color: C.ink, lineHeight: 1.12, letterSpacing: -0.6 }}>
        {text.split(" ").map((w, i) => {
          const p = prog(f, start + 4 + i * 2.2, 14);
          return (
            <span key={i} style={{ display: "inline-block", marginRight: "0.26em", opacity: p, transform: `translateY(${(1 - p) * 14}px)` }}>
              {w}
            </span>
          );
        })}
      </div>
    </div>
  );
};

const pt = (o: readonly [number, number], k: number, a: readonly [number, number]) => [o[0] + a[0] * k, o[1] + a[1] * k] as [number, number];

/** Persistent faint click marks. */
const ClickMarks: React.FC<{ marks: { f: number; x: number; y: number }[] }> = ({ marks }) => {
  const f = useCurrentFrame();
  return (
    <>
      {marks
        .filter((m) => f >= m.f)
        .map((m, i) => {
          const p = prog(f, m.f, 8);
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: m.x - 11,
                top: m.y - 11,
                width: 22,
                height: 22,
                borderRadius: 99,
                border: `2px solid ${C.primary}`,
                opacity: 0.85 - 0.55 * p,
                transform: `scale(${1.8 - 0.8 * p})`,
                zIndex: 40,
              }}
            />
          );
        })}
    </>
  );
};

/* =====================================================================
   1. HOOK — doing everything by hand across two apps
   ===================================================================== */

const LI_O = [100, 282] as const;
const ZM_O = [980, 282] as const;
type Ev = { f: number; w: "li" | "zm"; at: readonly [number, number]; kind: string; k?: number };

const MAIN: Ev[] = [
  { f: 34, w: "li", at: APPA.tabSubmitted, kind: "tabS" },
  { f: 52, w: "li", at: APPA.search, kind: "search" },
  { f: 90, w: "li", at: APPA.tabDrafts, kind: "tabD" },
  { f: 112, w: "li", at: APPA.rowBtn(2), kind: "row", k: 2 },
  { f: 150, w: "zm", at: HDA.overview(1), kind: "ov", k: 1 },
  { f: 218, w: "zm", at: HDA.compose, kind: "compose" },
  { f: 256, w: "zm", at: HDA.stateSelect, kind: "select" },
  { f: 270, w: "zm", at: HDA.stateOption(2), kind: "option", k: 2 },
  { f: 284, w: "zm", at: HDA.updateBtn, kind: "update" },
];
const MONTAGE_START = 300;
const CYCLE: ((k: number) => Omit<Ev, "f">)[] = [
  () => ({ w: "li", at: APPA.tabSubmitted, kind: "tabS" }),
  () => ({ w: "li", at: APPA.search, kind: "search" }),
  (k) => ({ w: "li", at: APPA.rowBtn(k % 6), kind: "row", k: k % 6 }),
  (k) => ({ w: "zm", at: HDA.overview((k * 2) % 9), kind: "ov", k: (k * 2) % 9 }),
  () => ({ w: "zm", at: HDA.compose, kind: "compose" }),
  () => ({ w: "zm", at: HDA.stateSelect, kind: "select" }),
  (k) => ({ w: "zm", at: HDA.stateOption(k % 4), kind: "option", k: k % 4 }),
  () => ({ w: "zm", at: HDA.updateBtn, kind: "update" }),
];
const MONTAGE: Ev[] = Array.from({ length: 19 }, (_, i) => ({ f: MONTAGE_START + i * 6, ...CYCLE[i % 8](Math.floor(i / 8) + i) }));
const ALL = [...MAIN, ...MONTAGE];
const gpos = (e: Ev) => {
  const o = e.w === "li" ? LI_O : ZM_O;
  const jitter = e.f >= MONTAGE_START ? [((e.f * 37) % 15) - 7, ((e.f * 53) % 11) - 5] : [0, 0];
  return [o[0] + e.at[0] + jitter[0], o[1] + e.at[1] + jitter[1]] as [number, number];
};

const HOOK_DUR = 420;
const typedSearch = (f: number) => Math.max(0, Math.min(14, Math.floor((f - 55) / 2)));
const typedCompose = (f: number) => Math.max(0, Math.min(28, f - 222));

function hookState(f: number): { li: AppState; zm: HDState; clicks: number; keys: number; day: number } {
  const clicks = ALL.filter((e) => e.f <= f).length;
  const montageTypes = MONTAGE.filter((e) => e.f <= f && (e.kind === "search" || e.kind === "compose")).length;
  const keys = typedSearch(f) + typedCompose(f) + montageTypes * 23 + Math.max(0, Math.min(6, f - MONTAGE_START) * 0);
  if (f < MONTAGE_START) {
    const li: AppState = {
      tab: f >= 35 && f < 91 ? "submitted" : "drafts",
      searchFocus: f >= 52 && f < 112,
      searchChars: typedSearch(f),
      hlRow: f >= 113 ? 2 : null,
      rowFlash: f >= 113 ? 1 - prog(f, 113, 18) : 0,
    };
    const composeChars = f >= 290 ? 0 : typedCompose(f);
    const zm: HDState = {
      selected: f >= 150 ? 1 : null,
      loaded: f >= 150 ? prog(f, 152, 12) : 0,
      scroll: f < 290 ? interpolate(f, [186, 212], [0, 220], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE }) : interpolate(f, [290, 306], [220, 330], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE }),
      composeFocus: f >= 218 && f < 290,
      composeChars,
      dropdown: f >= 257 && f < 271,
      stateValue: f >= 271 ? 2 : 0,
      stateFlash: f >= 271 ? 1 - prog(f, 271, 16) : 0,
      updatePulse: f >= 285 && f < 302 ? prog(f, 285, 16) : 0,
      newArticle: f >= 290 ? prog(f, 290, 12) : 0,
    };
    return { li, zm, clicks, keys, day: 1 };
  }
  // montage: every 8 clicks is "another day"
  const idx = MONTAGE.filter((e) => e.f <= f).length - 1;
  const last = MONTAGE[Math.max(0, idx)];
  const dayIdx = Math.floor(Math.max(0, idx) / 8);
  const dayStart = MONTAGE_START + dayIdx * 48;
  const lastOf = (kind: string) => [...MONTAGE].reverse().find((e) => e.f <= f && e.kind === kind);
  const li: AppState = {
    tab: lastOf("tabS") && (lastOf("tabS")!.f > (lastOf("row")?.f ?? -1)) ? "submitted" : "drafts",
    searchFocus: last.kind === "search",
    searchChars: last.kind === "search" ? Math.min(14, (f - last.f) * 4) : 0,
    hlRow: lastOf("row")?.k ?? null,
    rowFlash: lastOf("row") ? 1 - prog(f, lastOf("row")!.f, 8) : 0,
    resetFlash: 1 - prog(f, dayStart, 8),
  };
  const zm: HDState = {
    selected: lastOf("ov")?.k ?? null,
    loaded: lastOf("ov") ? prog(f, lastOf("ov")!.f, 5) : 0,
    composeFocus: last.kind === "compose",
    composeChars: last.kind === "compose" ? Math.min(30, (f - last.f) * 6) : 0,
    dropdown: last.kind === "select",
    stateValue: lastOf("option")?.k ?? 0,
    stateFlash: lastOf("option") ? 1 - prog(f, lastOf("option")!.f, 8) : 0,
    updatePulse: last.kind === "update" ? prog(f, last.f, 6) : 0,
    resetFlash: 1 - prog(f, dayStart, 8),
  };
  return { li, zm, clicks, keys, day: 2 + dayIdx };
}

export const SceneHook: React.FC = () => {
  const f = useCurrentFrame();
  const st = hookState(f);
  const keysCursor: CursorKey[] = [{ f: 8, x: 960, y: 1060 }];
  ALL.forEach((e) => {
    const [x, y] = gpos(e);
    const lead = e.f >= MONTAGE_START ? 3 : 6;
    keysCursor.push({ f: e.f - lead, x, y }, { f: e.f + 1, x, y });
    if (e.kind === "ov" && e.f < MONTAGE_START) {
      const t = [ZM_O[0] + HDA.thread[0], ZM_O[1] + HDA.thread[1]];
      keysCursor.push({ f: 180, x: t[0], y: t[1] }, { f: 212, x: t[0], y: t[1] });
    }
  });
  keysCursor.sort((a, b) => a.f - b.f);
  const marks = ALL.map((e) => ({ f: e.f, x: gpos(e)[0], y: gpos(e)[1] }));
  const dim = prog(f, 402, 18);
  const winIn = (d: number) => {
    const p = prog(f, d, 22);
    return { opacity: p, transform: `translateY(${(1 - p) * 40}px)` };
  };
  return (
    <AbsoluteFill>
      <Paper />
      <RunningHead text="THE PROBLEM" />
      <Heading text="Tired of clicking through the UI for every little thing?" start={8} size={52} maxW={1080} />
      <Stat label="DAY" value={String(st.day)} x={1330} y={96} opacity={prog(f, 20, 14)} />
      <Stat label="CLICKS" value={String(st.clicks)} x={1470} y={96} opacity={prog(f, 24, 14)} />
      <Stat label="KEYSTROKES" value={String(st.keys)} x={1630} y={96} opacity={prog(f, 28, 14)} />
      <div style={{ position: "absolute", left: LI_O[0], top: LI_O[1], width: APP_W, height: APP_H, ...winIn(0) }}>
        <AppWindow s={st.li} />
      </div>
      <div style={{ position: "absolute", left: ZM_O[0], top: ZM_O[1], width: HD_W, height: HD_H, ...winIn(6) }}>
        <HDWindow s={st.zm} />
      </div>
      <ClickMarks marks={marks} />
      <Cursor keys={keysCursor} clicks={ALL.map((e) => e.f)} visibleFrom={10} />
      <AbsoluteFill style={{ background: C.paper, opacity: dim * 0.35 }} />

      {/* sound */}
      {ALL.map((e, i) => (
        <Sfx key={`c${i}`} at={e.f} name={i % 3 ? "click" : "click2"} v={e.f >= MONTAGE_START ? 0.42 : 0.6} />
      ))}
      <Typing from={55} to={83} every={2} />
      <Typing from={222} to={250} every={1.5} />
      {MONTAGE.filter((e) => e.kind === "search" || e.kind === "compose").map((e, i) => (
        <Typing key={`t${i}`} from={e.f + 1} to={e.f + 5} every={1} v={0.2} />
      ))}
      {[188, 194, 200, 206].map((t) => (
        <Sfx key={t} at={t} name="key4" v={0.12} />
      ))}
    </AbsoluteFill>
  );
};
export const HOOK_FRAMES = HOOK_DUR;

/* =====================================================================
   2. ASK — let it breathe
   ===================================================================== */

export const SceneAsk: React.FC = () => {
  const f = useCurrentFrame();
  const words1 = "What if your AI could".split(" ");
  const words2 = "just do it for you?".split(" ");
  const word = (w: string, i: number, base: number, color = C.ink) => {
    const p = prog(f, base + i * 3.2, 18);
    return (
      <span key={w + i} style={{ display: "inline-block", marginRight: "0.24em", opacity: p, transform: `translateY(${(1 - p) * 18}px)`, color }}>
        {w}
      </span>
    );
  };
  const ul = prog(f, 96, 28, Easing.inOut(Easing.cubic));
  const push = interpolate(f, [0, 225], [1, 1.035]);
  return (
    <AbsoluteFill>
      <Paper />
      <RunningHead text="WHAT IF" color={C.claudeInk} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", transform: `scale(${push})` }}>
        <AccentBar color={C.claudeInk} p={prog(f, 10, 14)} w={56} />
        <div style={{ marginTop: 34, fontFamily: SERIF, fontWeight: 600, fontSize: 96, color: C.ink, letterSpacing: -1.5, lineHeight: 1.12, textAlign: "center" }}>
          <div>
            {words1.map((w, i) => word(w, i, 20, w === "AI" ? C.claudeInk : C.ink))}
          </div>
          <div style={{ position: "relative", display: "inline-block" }}>
            {words2.map((w, i) => word(w, i, 72))}
            <svg width="760" height="40" viewBox="0 0 760 40" style={{ position: "absolute", left: "50%", bottom: -30, transform: "translateX(-52%)" }}>
              <path d="M8 24 C 140 12, 300 30, 440 18 S 680 14, 752 20" stroke={C.claudeInk} strokeWidth={6} fill="none" strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - ul} />
            </svg>
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/* =====================================================================
   3. INTRODUCING
   ===================================================================== */

export const SceneIntro: React.FC = () => {
  const f = useCurrentFrame();
  const badge = prog(f, 36, 22, Easing.bezier(0.34, 1.4, 0.64, 1));
  const ring = prog(f, 36, 30, Easing.inOut(Easing.cubic));
  const title = prog(f, 44, 26);
  return (
    <AbsoluteFill>
      <Paper />
      <RunningHead text="INTRODUCING" />
      <AbsoluteFill style={{ alignItems: "center" }}>
        <div style={{ marginTop: 150, position: "relative", width: 280, height: 280, opacity: Math.min(1, badge * 1.4), transform: `scale(${0.7 + 0.3 * badge})` }}>
          <svg width="280" height="280" viewBox="0 0 280 280" style={{ position: "absolute", inset: 0 }}>
            <circle cx="140" cy="140" r="122" fill="rgba(13,128,242,0.07)" />
            <circle cx="140" cy="140" r="122" fill="none" stroke={C.primary} strokeWidth={16} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - ring} transform="rotate(-90 140 140)" />
            <circle cx="140" cy="140" r="100" fill="none" stroke={C.hair} strokeWidth={2} opacity={prog(f, 50, 14)} />
          </svg>
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: C.ink }}>
            <McpKnot size={130} color={C.ink} width={12} draw={prog(f, 44, 46, Easing.inOut(Easing.cubic))} />
          </div>
        </div>
        <div style={{ marginTop: 56, display: "flex", flexDirection: "column", alignItems: "center", gap: 14, opacity: prog(f, 8, 14) }}>
          <AccentBar p={prog(f, 8, 16)} />
          <div style={{ fontFamily: SANS, fontSize: 22, fontWeight: 600, letterSpacing: 6, color: C.primary }}>INTRODUCING</div>
        </div>
        <div style={{ marginTop: 18, fontFamily: SERIF, fontSize: 124, fontWeight: 700, color: C.ink, letterSpacing: -3, clipPath: `inset(0 ${(1 - title) * 100}% 0 0)`, transform: `translateY(${(1 - title) * 10}px)` }}>
          Product MCP
        </div>
        <div style={{ marginTop: 12, fontFamily: SANS, fontSize: 40, fontWeight: 500, color: C.ink2, opacity: prog(f, 110, 18), transform: `translateY(${(1 - prog(f, 110, 18)) * 12}px)` }}>
          Plug your agent straight into Product.
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/* =====================================================================
   4. THE AGENT — webs into both apps, does the work, then "acts as you"
   ===================================================================== */

const K = 0.78;
const A_LI = [150, 410] as const;
const A_ZM = [1115, 410] as const;
const M0 = [960, 232] as const; // mascot centre during the web phase
const M1 = [960, 560] as const; // mascot centre in the tiles layout
const TILE = 236;
const T_LI = [600, 600] as const;
const T_ZM = [1320, 600] as const;

const LI_ANCH = [APPA.tabSubmitted, APPA.search, APPA.rowName(1), APPA.status(2), APPA.rowBtn(2), APPA.rowName(4), APPA.newBtn];
const ZM_ANCH = [HDA.overview(1), HDA.overview(4), HDA.article(0), HDA.article(2), HDA.compose, HDA.stateSelect, HDA.updateBtn];

type Strand = { side: -1 | 1; j: number; a0: [number, number]; a1: [number, number]; shoot: number };
const STRANDS: Strand[] = [
  ...LI_ANCH.map((a, j) => ({ side: -1 as const, j, a0: pt(A_LI, K, a), a1: [T_LI[0] + TILE / 2 - 4, T_LI[1] - 66 + j * 22] as [number, number], shoot: 30 + j * 8 })),
  ...ZM_ANCH.map((a, j) => ({ side: 1 as const, j, a0: pt(A_ZM, K, a), a1: [T_ZM[0] - TILE / 2 + 4, T_ZM[1] - 66 + j * 22] as [number, number], shoot: 34 + j * 8 })),
];

// Actions: pulse arrives at `f` on strand (side, j)
const ACTIONS = [
  { f: 150, side: -1, j: 0 },
  { f: 168, side: -1, j: 1 },
  { f: 190, side: -1, j: 3 },
  { f: 210, side: 1, j: 0 },
  { f: 232, side: 1, j: 2 },
  { f: 256, side: 1, j: 4 },
  { f: 280, side: 1, j: 5 },
  { f: 294, side: 1, j: 6 },
];

const MORPH = [314, 352] as const;
const bz = (a: number[], c: number[], b: number[], t: number) => [
  (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t ** 2 * b[0],
  (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t ** 2 * b[1],
];

function agentState(f: number) {
  const li: AppState = {
    tab: f >= 150 ? "submitted" : "drafts",
    searchFocus: f >= 168 && f < 190,
    searchChars: f >= 168 ? Math.min(12, Math.floor((f - 168) * 1.2)) : 0,
    hlRow: f >= 190 ? 2 : null,
    rowFlash: f >= 190 ? 1 - prog(f, 190, 20) : 0,
  };
  const zm: HDState = {
    selected: f >= 210 ? 1 : null,
    loaded: f >= 210 ? prog(f, 212, 12) : 0,
    readSweep: f >= 232 && f < 258 ? interpolate(f, [232, 256], [40, 420]) : null,
    scroll: f < 272 ? interpolate(f, [232, 256], [0, 110], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE }) : interpolate(f, [272, 290], [110, 330], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE }),
    composeFocus: f >= 256 && f < 272,
    composeChars: f >= 256 && f < 272 ? Math.min(38, (f - 256) * 3) : 0,
    newArticle: f >= 272 ? prog(f, 272, 12) : 0,
    stateValue: f >= 280 ? 2 : 0,
    stateFlash: f >= 280 ? 1 - prog(f, 280, 16) : 0,
    updatePulse: f >= 294 && f < 312 ? prog(f, 294, 16) : 0,
    check: prog(f, 298, 12),
  };
  return { li, zm };
}

export const SceneAgent: React.FC = () => {
  const f = useCurrentFrame();
  const { li, zm } = agentState(f);
  const m = prog(f, MORPH[0], MORPH[1] - MORPH[0], Easing.inOut(Easing.cubic));
  const content = 1 - prog(f, MORPH[0] + 16, 16);
  const mx = interpolate(m, [0, 1], [M0[0], M1[0]]);
  const my = interpolate(m, [0, 1], [M0[1], M1[1]]) + Math.sin(f / 14) * 4;
  const msize = interpolate(m, [0, 1], [176, 168]);

  const winRect = (o: readonly [number, number], t: readonly [number, number]) => {
    const w0 = APP_W * K;
    const h0 = APP_H * K;
    return {
      left: interpolate(m, [0, 1], [o[0], t[0] - TILE / 2]),
      top: interpolate(m, [0, 1], [o[1], t[1] - TILE / 2]),
      width: interpolate(m, [0, 1], [w0, TILE]),
      height: interpolate(m, [0, 1], [h0, TILE]),
      radius: interpolate(m, [0, 1], [14, 46]),
    };
  };
  const tile = (o: readonly [number, number], t: readonly [number, number], kind: "li" | "zm", inDelay: number) => {
    const r = winRect(o, t);
    const appear = prog(f, inDelay, 22);
    return (
      <div style={{ position: "absolute", left: r.left, top: r.top + (1 - appear) * 30, width: r.width, height: r.height, opacity: appear, borderRadius: r.radius, overflow: "hidden", background: "#fff", border: `1.5px solid ${C.hair}`, boxShadow: "0 24px 50px -34px rgba(40,35,25,.45)" }}>
        <div style={{ position: "absolute", left: 0, top: 0, width: APP_W, height: APP_H, transform: `scale(${(r.width / APP_W)}, ${(r.height / APP_H)})`, transformOrigin: "0 0", opacity: content }}>
          {kind === "li" ? <AppWindow s={li} /> : <HDWindow s={zm} />}
        </div>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", opacity: prog(f, MORPH[1] - 8, 14), transform: `scale(${0.85 + 0.15 * prog(f, MORPH[1] - 8, 14)})` }}>
          {kind === "li" ? (
            <div style={{ width: 128, height: 128, borderRadius: 34, background: C.primarySoft, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <ScaleIcon size={76} color={C.primary} width={1.7} />
            </div>
          ) : (
            <HelpDeskLogo size={124} />
          )}
        </div>
      </div>
    );
  };

  const origin = (s: Strand) => [mx + s.side * (34 + s.j * 4), my + 22 + (s.j - 3) * 7];
  const end = (s: Strand) => [interpolate(m, [0, 1], [s.a0[0], s.a1[0]]), interpolate(m, [0, 1], [s.a0[1], s.a1[1]])];
  const ctrl = (a: number[], b: number[], k = 0) => [(a[0] + b[0]) / 2 + k * 14, (a[1] + b[1]) / 2 + (1 - m) * 46 + 14 + k * 10];

  const acts = [
    { t: "It acts as you.", at: 346, size: 72, serif: true, color: C.ink },
    { t: "Exactly the permissions you have in the app.", at: 384, size: 34, serif: false, color: C.ink2 },
  ];

  return (
    <AbsoluteFill>
      <Paper />
      <RunningHead text="HOW IT WORKS" color={C.claudeInk} />
      <div style={{ opacity: 1 - prog(f, MORPH[0], 12) }}>
        <Heading text="Your agent does the work." start={140} size={48} accent={C.claudeInk} />
        <Stat label="YOUR CLICKS" value="0" color={C.success} x={1450} y={96} opacity={prog(f, 150, 14)} />
        <Stat label="YOUR KEYSTROKES" value="0" color={C.success} x={1630} y={96} opacity={prog(f, 156, 14)} />
      </div>

      {tile(A_LI, T_LI, "li", 0)}
      {tile(A_ZM, T_ZM, "zm", 6)}

      {/* web strands */}
      <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
        {STRANDS.map((s, i) => {
          const a = origin(s);
          const b = end(s);
          const d = prog(f, s.shoot, 7, Easing.out(Easing.quad));
          if (d <= 0) return null;
          const c1 = ctrl(a, b, 0);
          const c2 = ctrl(a, b, s.side);
          return (
            <g key={i}>
              <path d={`M${a[0]} ${a[1]} Q${c1[0]} ${c1[1]} ${b[0]} ${b[1]}`} stroke={C.ink} strokeOpacity={0.55} strokeWidth={1.5} fill="none" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - d} />
              <path d={`M${a[0]} ${a[1]} Q${c2[0]} ${c2[1]} ${b[0]} ${b[1]}`} stroke={C.ink} strokeOpacity={0.25} strokeWidth={0.8} fill="none" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - d} />
              {d >= 1 && (
                <>
                  <circle cx={b[0]} cy={b[1]} r={4} fill={C.claude} />
                  <circle cx={b[0]} cy={b[1]} r={4 + 10 * prog(f, s.shoot + 7, 12)} fill="none" stroke={C.claude} strokeOpacity={1 - prog(f, s.shoot + 7, 12)} strokeWidth={2} />
                </>
              )}
            </g>
          );
        })}
        {/* action pulses */}
        {ACTIONS.map((ac, i) => {
          const t = prog(f, ac.f - 16, 16, Easing.inOut(Easing.quad));
          if (t <= 0 || t >= 1) return null;
          const s = STRANDS.find((x) => x.side === ac.side && x.j === ac.j)!;
          const a = origin(s);
          const b = end(s);
          const [x, y] = bz(a, ctrl(a, b), b, t);
          return <circle key={i} cx={x} cy={y} r={7} fill={C.claude} style={{ filter: "drop-shadow(0 0 6px rgba(217,119,87,.8))" }} />;
        })}
        {/* steady relay once in tiles layout */}
        {f > MORPH[1] &&
          STRANDS.filter((_, i) => i % 2 === 0).map((s, i) => {
            const tt = (((f - MORPH[1]) / 40 + i * 0.27) % 1 + 1) % 1;
            const a = origin(s);
            const b = end(s);
            const t = i % 4 === 0 ? 1 - tt : tt;
            const [x, y] = bz(a, ctrl(a, b), b, t);
            return <circle key={`r${i}`} cx={x} cy={y} r={5} fill={C.claude} opacity={Math.sin(tt * Math.PI) * prog(f, MORPH[1], 10)} />;
          })}
      </svg>

      {/* mascot */}
      <div style={{ position: "absolute", left: mx - msize / 2, top: my - msize * 0.36, opacity: prog(f, 4, 16), transform: `translateY(${(1 - prog(f, 4, 20)) * 30}px)` }}>
        <Clawd size={msize} blink={f % 80 > 76} />
      </div>

      {/* acts as you */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 790, textAlign: "center" }}>
        {acts.map((a) => {
          const p = prog(f, a.at, 18);
          return (
            <div key={a.t} style={{ fontFamily: a.serif ? SERIF : SANS, fontSize: a.size, fontWeight: a.serif ? 700 : 500, color: a.color, opacity: p, transform: `translateY(${(1 - p) * 14}px)`, letterSpacing: a.serif ? -1 : 0, marginBottom: 10 }}>
              {a.t}
              {!a.serif && (
                <span style={{ color: C.claudeInk, fontWeight: 600, opacity: prog(f, 460, 14) }}> Nothing more.</span>
              )}
            </div>
          );
        })}
      </div>

      {/* sound */}
      {STRANDS.map((s, i) => (
        <Sfx key={`w${i}`} at={s.shoot} name="thwip" v={0.16 + (i % 3) * 0.03} />
      ))}
      {ACTIONS.map((a, i) => (
        <Sfx key={`a${i}`} at={a.f} name="pop" v={0.28} />
      ))}
      <Sfx at={MORPH[0] + 2} name="whoosh" v={0.32} />
    </AbsoluteFill>
  );
};
