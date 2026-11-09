import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

import { AccentBar, Paper, RunningHead } from "./apps";
import { Cam, FULL, K, Sfx, WorldCursor, at, fit, hold, p01, pulse } from "./cam";
import {
  D,
  DLG_BTN,
  DLG_RECT,
  NOTE_TEXT,
  SETTINGS_BTN,
  rowBtn,
  rowRect,
  rowWaitRect,
  tilesRect,
  worldRect,
} from "./dash";
import { Icon } from "./icons";
import { HelpDeskLogo } from "./kit";
import { C, MONO, SANS, SERIF } from "./theme";
import TABLE from "./scenes.json";
import { AGT, AgentView, REQ, RequesterView, TEAM, TeamView } from "./views";
import { MailToast, HelpDeskWindow, Z_MENTIONS, Z_NOTE, Z_OVERVIEW, Z_TAGS } from "./helpdesk";

/** Scene lengths come from scenes.json (the single source also read by Launch.tsx and tl.mjs). */
const frames = (id: string) => TABLE.scenes.find((s) => s.id === id)!.frames;

const clampI = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/* =============================================================== HOOK */

const MSGS: [string, string, string][] = [
  ["Jordan P.", "#0ea5e9", "Any update on the Contoso access request? The customer is asking."],
  ["Riya M.", "#f59e0b", "Who's working on the Globex onboarding?"],
  ["Chris T.", "#8b5cf6", "Our vendor can't start until this is approved."],
  ["Jordan P.", "#0ea5e9", "Still nothing. Is anyone on this?"],
  ["Alex C.", "#16a34a", "Customer goes live Friday. Can someone help?"],
];
const MSG_AT = [6, 24, 50, 78, 104];
export const HOOK_FRAMES = frames("hook");

export const SceneHook: React.FC = () => {
  const f = useCurrentFrame();
  const shown = MSG_AT.filter((a) => f >= a).length;
  const push = interpolate(f, [0, HOOK_FRAMES], [1, 1.1]);
  return (
    <AbsoluteFill>
      <Paper />
      <RunningHead text="SOUND FAMILIAR?" color={D.red} opacity={p01(f, 0, 10)} />
      <AbsoluteFill style={{ transform: `scale(${push})` }}>
        <div style={{ position: "absolute", left: 330, top: 130, width: 1260, height: 820, borderRadius: 22, background: "#fff", border: `1.5px solid ${C.hair}`, boxShadow: "0 30px 60px -36px rgba(40,35,25,.5)", overflow: "hidden", fontFamily: SANS }}>
          <div style={{ height: 82, display: "flex", alignItems: "center", gap: 16, padding: "0 30px", borderBottom: "1px solid #e6e8eb" }}>
            <Icon n="message" size={30} color="#16a34a" />
            <div style={{ fontSize: 26, fontWeight: 600, color: C.ink }}>Support help</div>
            <div style={{ fontSize: 19, color: C.ink2 }}>· 214 members</div>
          </div>
          <div style={{ position: "absolute", left: 0, right: 0, top: 82, bottom: 0, overflow: "hidden" }}>
            {MSGS.slice(0, shown).map(([who, col, text], i) => {
              const p = p01(f, MSG_AT[i], 9);
              return (
                <div key={i} style={{ position: "absolute", left: 34, right: 34, top: 34 + i * 140, display: "flex", gap: 18, opacity: p, transform: `translateY(${(1 - p) * 30}px) scale(${0.96 + 0.04 * p})`, transformOrigin: "left center" }}>
                  <div style={{ width: 66, height: 66, borderRadius: 99, background: col, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 24, flex: "none" }}>{who.split(" ").map((s) => s[0]).join("")}</div>
                  <div>
                    <div style={{ fontSize: 22, color: C.ink2 }}>
                      <b style={{ color: C.ink }}>{who}</b> · {["Mon", "Tue", "Wed", "Thu", "Fri"][i]} 10:{12 + i * 7}
                    </div>
                    <div style={{ fontSize: 36, color: C.ink, marginTop: 4 }}>{text}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </AbsoluteFill>
      {MSG_AT.map((a, i) => (
        <Sfx key={i} at={a} name="pop" vol={0.35} />
      ))}
    </AbsoluteFill>
  );
};

/* ============================================================== TITLE */

export const TITLE_FRAMES = frames("title");

export const SceneTitle: React.FC = () => {
  const f = useCurrentFrame();
  const ring = p01(f, 0, 22);
  const icon = p01(f, 4, 12);
  const wipe = p01(f, 10, 18);
  const pill = p01(f, 32, 12);
  return (
    <AbsoluteFill>
      <Paper />
      <RunningHead text="NEW IN PRODUCT" opacity={p01(f, 4, 10)} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 230, display: "flex", justifyContent: "center" }}>
        <div style={{ position: "relative", width: 190, height: 190 }}>
          <svg width="190" height="190" style={{ position: "absolute", inset: 0 }}>
            <circle cx="95" cy="95" r="88" fill="none" stroke={C.primary} strokeWidth="4" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - ring} transform="rotate(-90 95 95)" />
          </svg>
          <div style={{ position: "absolute", left: 35, top: 35, width: 120, height: 120, borderRadius: 30, background: "#fff", border: `1.5px solid ${C.hair}`, display: "flex", alignItems: "center", justifyContent: "center", opacity: icon, transform: `scale(${0.6 + 0.4 * icon})` }}>
            <Icon n="dashboard" size={64} color={C.primary} width={1.8} />
          </div>
        </div>
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: 470, textAlign: "center", fontFamily: SERIF, fontWeight: 700, fontSize: 132, color: C.ink, letterSpacing: -1, clipPath: `inset(0 ${(1 - wipe) * 100}% 0 0)` }}>Ticket Dashboard</div>
      <div style={{ position: "absolute", left: 0, right: 0, top: 660, display: "flex", justifyContent: "center", opacity: pill, transform: `translateY(${(1 - pill) * 16}px)` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 30px", borderRadius: 999, background: "#fff", border: `1.5px solid ${D.redBd}`, fontFamily: SANS, fontSize: 34, fontWeight: 600, color: D.red }}>
          <Icon n="flame" size={34} color={D.red} />
          with escalation built in
        </div>
      </div>
      <Sfx at={8} name="impact" vol={0.45} len={60} />
      <Sfx at={32} name="pop" vol={0.3} />
    </AbsoluteFill>
  );
};

/* ===================================================== REQUESTER + ESC */

// VO: req @20, esc1 @186, esc2 @336 (scene-relative frames)
const R_TILES = fit(tilesRect(REQ.TILES_Y));
const R_TL = fit(worldRect(110, REQ.TILES_Y, 750, 124), 60, 2.0);
const R_TR = fit(worldRect(110 + 730, REQ.TILES_Y, 750, 124), 60, 2.0);
const R_ROW0 = fit(rowRect(REQ.ROWS[0]), 70);
const R_WAIT = { ...fit(rowWaitRect(REQ.ROWS[0])), z: 1.9 };
const R_DLG = fit(DLG_RECT, 60);
const ESC_BTN = rowBtn(REQ.ROWS[0], 132, 2, 1);
const NOTE = { ...fit(Z_NOTE, 60), z: 1.75 };
const MENT = { ...fit(Z_MENTIONS), z: 2.1 };
const TAGS = { ...fit(Z_TAGS), z: 1.9 };
const FLIP_AT = 318;
const TYPE_AT = 238;
const CLICK1 = 214;
const CLICK2 = 290;
const NOTE_IN = 350;
const TAG_AT = 470;
const MAIL_AT = 508;
export const ESC_FRAMES = frames("esc");

const ESC_CAM: K[] = [
  at(0, FULL),
  at(20, FULL),
  at(34, R_TL),
  at(54, R_TL),
  at(70, R_TR),
  at(92, R_TR),
  at(110, R_WAIT),
  at(176, R_WAIT),
  at(194, R_ROW0),
  at(216, R_ROW0),
  at(232, R_DLG),
  at(296, R_DLG),
  at(314, FULL),
  at(318, { ...FULL, z: 0.94 }),
  at(344, { ...FULL, z: 0.94 }),
  at(358, FULL),
  at(370, NOTE),
  at(384, MENT),
  at(450, MENT),
  at(466, TAGS),
  at(492, TAGS),
  at(508, FULL),
];

export const SceneEscalate: React.FC = () => {
  const f = useCurrentFrame();
  // requester side
  const tileHl = f < 30 ? null : f < 44 ? 0 : f < 56 ? 1 : f < 68 ? 2 : f < 82 ? 3 : null;
  const tileP = tileHl === null ? 0 : pulse(f, [30, 44, 56, 68][tileHl], 14);
  const dialogP = hold(f, CLICK1 + 2, CLICK2 + 4, 10);
  const chars = Math.max(0, Math.floor((f - TYPE_AT) / 0.62));
  const escalated = f >= CLICK2 + 6;
  const e = p01(f, CLICK2 + 6, 12);
  const row0 = {
    hl: pulse(f, 132, 26),
    pressEscalate: f >= CLICK1 - 2 && f < CLICK1 + 4 ? 1 : 0,
    tint: e,
    badge: escalated ? { text: "Escalated", tone: "red" as const, p: e } : null,
    line: escalated ? { p: e, text: <span><span style={{ color: D.red }}>Escalated by you just now</span><span style={{ color: D.muted }}> · waiting for Support to respond</span></span> } : null,
  };
  // flip
  const flip = p01(f, FLIP_AT, 26);
  const rot = flip * 180;
  const lift = Math.sin(Math.PI * flip);
  // helpdesk side
  const z = {
    noteP: p01(f, NOTE_IN, 14),
    mentionHl: pulse(f, 392, 34) + pulse(f, 426, 24) * 0.7,
    tagP: p01(f, TAG_AT, 12),
    ovBump: p01(f, TAG_AT + 10, 10),
    ovHl: hold(f, TAG_AT + 10, 9999, 8),
  };
  const keyFrames = Array.from({ length: Math.ceil(NOTE_TEXT.length * 0.62 / 3) }, (_, i) => TYPE_AT + i * 3);
  return (
    <AbsoluteFill>
      <Paper />
      <Cam keys={ESC_CAM}>
        <AbsoluteFill style={{ perspective: 2800 }}>
          <AbsoluteFill style={{ transformStyle: "preserve-3d", transform: `translateZ(${-260 * lift}px) rotateY(${rot}deg)` }}>
            <AbsoluteFill style={{ backfaceVisibility: "hidden" }}>
              <RequesterView tileHl={tileHl} tileP={tileP} row0={row0} escalated={escalated} dialog={{ p: dialogP, chars: Math.min(chars, NOTE_TEXT.length), press: f >= CLICK2 - 2 && f < CLICK2 + 4 ? 1 : 0 }} />
            </AbsoluteFill>
            <AbsoluteFill style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}>
              <HelpDeskWindow s={z} />
            </AbsoluteFill>
          </AbsoluteFill>
        </AbsoluteFill>
      </Cam>
      <WorldCursor
        cam={ESC_CAM}
        from={186}
        to={FLIP_AT - 4}
        keys={[
          { f: 186, x: ESC_BTN[0] - 260, y: ESC_BTN[1] + 140 },
          { f: 210, x: ESC_BTN[0], y: ESC_BTN[1] },
          { f: 230, x: ESC_BTN[0] - 40, y: ESC_BTN[1] - 60 },
          { f: 274, x: DLG_BTN[0] - 120, y: DLG_BTN[1] - 40 },
          { f: 287, x: DLG_BTN[0], y: DLG_BTN[1] },
        ]}
        clicks={[CLICK1, CLICK2]}
      />
      {/* side label for the flip */}
      <SideTag f={f} a={FLIP_AT + 18} b={ESC_FRAMES} text="Meanwhile, in Help desk" />
      <MailToast p={p01(f, MAIL_AT, 12)} x={1160} y={64} />
      <Sfx at={CLICK1} name="click" vol={0.6} />
      <Sfx at={CLICK1 + 2} name="thwip" vol={0.3} />
      {keyFrames.map((k, i) => (
        <Sfx key={k} at={k} name={`key${i % 5}`} vol={0.22} len={8} />
      ))}
      <Sfx at={CLICK2} name="click" vol={0.6} />
      <Sfx at={CLICK2 + 8} name="pop" vol={0.3} />
      <Sfx at={FLIP_AT} name="whoosh" vol={0.55} />
      <Sfx at={NOTE_IN} name="thwip" vol={0.35} />
      <Sfx at={TAG_AT} name="pop" vol={0.4} />
      <Sfx at={MAIL_AT} name="chime" vol={0.4} len={60} />
    </AbsoluteFill>
  );
};

const SideTag: React.FC<{ f: number; a: number; b: number; text: string }> = ({ f, a, b, text }) => {
  const p = hold(f, a, b - 10, 10);
  if (p <= 0) return null;
  return (
    <div style={{ position: "absolute", left: 60, bottom: 46, display: "flex", alignItems: "center", gap: 12, padding: "12px 22px", borderRadius: 999, background: "#fff", border: `1.5px solid ${C.hair}`, boxShadow: "0 14px 30px -18px rgba(0,0,0,.4)", fontFamily: SANS, fontSize: 24, fontWeight: 600, color: C.ink, opacity: p, transform: `translateY(${(1 - p) * 20}px)` }}>
      <HelpDeskLogo size={30} />
      {text}
    </div>
  );
};

/* ============================================================ QUEUE */

// VO queue @14: "Escalations stay pinned" @98, "until they.re cleared" @156
const A_TOP = fit(worldRect(110, 108, 1480, 560), 50);
const A_ROW_L = { ...fit(worldRect(110, AGT.ROW0, 780, AGT.ROW0_H)), z: 1.85 };
const A_ROW_R = { ...fit(worldRect(110 + 760, AGT.ROW0, 720, AGT.ROW0_H)), z: 1.85 };
const CLEAR_BTN = rowBtn(AGT.ROW0, AGT.ROW0_H, 2, 1);
const CLEAR_AT = 160;
export const QUEUE_FRAMES = frames("queue");

const A_ROW = fit(worldRect(110, AGT.ROW0 - 300, 1480, AGT.ROW0_H + 300), 50);
const AGT_CAM: K[] = [at(0, FULL), at(14, FULL), at(30, A_TOP), at(92, A_TOP), at(108, A_ROW_L), at(138, A_ROW_L), at(150, A_ROW_R), at(168, A_ROW_R), at(186, A_ROW)];

export const SceneQueue: React.FC = () => {
  const f = useCurrentFrame();
  const cleared = f >= CLEAR_AT + 2;
  const c = p01(f, CLEAR_AT + 2, 12);
  const row0 = {
    tint: 1 - c,
    hl: pulse(f, 104, 28),
    pressClear: f >= CLEAR_AT - 2 && f < CLEAR_AT + 4 ? 1 : 0,
    badge: cleared ? { text: "Cleared", tone: "green" as const, p: c } : { text: "Escalated", tone: "red" as const, p: 1 },
    line: cleared
      ? { p: c, text: <span style={{ color: D.green }}>Cleared by you just now</span> }
      : { p: 1, text: <span><span style={{ color: D.red }}>Escalated by Alex Carter 2 minutes ago</span><span style={{ color: D.muted }}> · waiting for Support to respond</span></span> },
    note: { p: 1, text: NOTE_TEXT },
  };
  const tileHl = f >= 34 && f < 60 ? 0 : null;
  return (
    <AbsoluteFill>
      <Paper />
      <Cam keys={AGT_CAM}>
        <AgentView escalated={cleared && c > 0.5 ? 0 : 1} tileHl={tileHl} tileP={pulse(f, 34, 26)} row0={row0} merge={p01(f, CLEAR_AT + 24, 14)} />
      </Cam>
      <WorldCursor cam={AGT_CAM} from={136} to={CLEAR_AT + 12} keys={[{ f: 136, x: CLEAR_BTN[0] - 200, y: CLEAR_BTN[1] + 120 }, { f: 157, x: CLEAR_BTN[0], y: CLEAR_BTN[1] }]} clicks={[CLEAR_AT]} />
      <Sfx at={CLEAR_AT} name="click" vol={0.6} />
      <Sfx at={CLEAR_AT + 4} name="chime" vol={0.3} len={60} />
    </AbsoluteFill>
  );
};

/* ================================================================ TEAM */

// VO team @12: overdue @95, unassigned @130, load @164, thresholds @213
const T_TILES = fit(tilesRect(TEAM.TILES_Y));
const T_TL = fit(worldRect(110, TEAM.TILES_Y, 900, 124), 60, 2.0);
const T_TABLE = fit(worldRect(110, TEAM.TABLE_Y, 1480, TEAM.TABLE_H), 60);
const T_TOPR = { x: SETTINGS_BTN[0] - 200, y: SETTINGS_BTN[1] + 120, z: 1.5 };
const T_SHEET = fit(worldRect(1700 - 620, 0, 620, 660), 40);
const SET_AT = 200;
export const TEAM_FRAMES = frames("team");

const TEAM_CAM: K[] = [at(0, FULL), at(12, FULL), at(28, T_TILES), at(80, T_TILES), at(94, T_TL), at(148, T_TL), at(164, T_TABLE), at(184, T_TABLE), at(198, T_TOPR), at(206, T_TOPR), at(224, T_SHEET)];

export const SceneTeam: React.FC = () => {
  const f = useCurrentFrame();
  const tileHl = f >= 90 && f < 124 ? 0 : f >= 126 && f < 160 ? 2 : null;
  const tileP = tileHl === 0 ? pulse(f, 90, 34) : tileHl === 2 ? pulse(f, 126, 34) : 0;
  return (
    <AbsoluteFill>
      <Paper />
      <Cam keys={TEAM_CAM}>
        <TeamView tileHl={tileHl} tileP={tileP} tableHl={pulse(f, 166, 30)} settingsPress={f >= SET_AT - 2 && f < SET_AT + 4 ? 1 : 0} sheet={p01(f, SET_AT + 2, 14)} fieldHl={f > 226 ? 2 : -1} fieldP={pulse(f, 228, 30)} />
      </Cam>
      <WorldCursor cam={TEAM_CAM} from={180} to={SET_AT + 10} keys={[{ f: 180, x: SETTINGS_BTN[0] - 160, y: SETTINGS_BTN[1] + 200 }, { f: 197, x: SETTINGS_BTN[0], y: SETTINGS_BTN[1] }]} clicks={[SET_AT]} />
      <Sfx at={SET_AT} name="click" vol={0.6} />
      <Sfx at={SET_AT + 3} name="thwip" vol={0.35} />
    </AbsoluteFill>
  );
};

/* =============================================================== OUTRO */

export const OUTRO_FRAMES = frames("outro");

export const SceneOutro: React.FC = () => {
  const f = useCurrentFrame();
  const out = interpolate(f, [OUTRO_FRAMES - 22, OUTRO_FRAMES], [1, 0], clampI);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <Paper />
      <RunningHead text="LIVE NOW" color={D.green} opacity={p01(f, 4, 10)} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 250, display: "flex", justifyContent: "center", opacity: p01(f, 0, 10) }}>
        <AccentBar p={p01(f, 2, 14)} w={70} />
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: 290, textAlign: "center", fontFamily: SERIF, fontWeight: 700, fontSize: 120, color: C.ink, ...rise(f, 4) }}>Ticket Dashboard</div>
      <div style={{ position: "absolute", left: 0, right: 0, top: 470, display: "flex", justifyContent: "center", ...rise(f, 14) }}>
        <div style={{ fontFamily: MONO, fontSize: 40, color: C.ink, padding: "18px 36px", borderRadius: 14, background: "#fff", border: `1.5px solid ${C.hair}` }}>app.example.com/dashboard</div>
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: 620, display: "flex", justifyContent: "center", gap: 26, ...rise(f, 24) }}>
        <Chip>
          <Icon n="dashboard" size={30} color={C.primary} /> On the Product home page
        </Chip>
        <Chip>
          <HelpDeskLogo size={30} /> Ticket Dashboard link in Help desk
        </Chip>
      </div>
    </AbsoluteFill>
  );
};

const rise = (f: number, a: number) => {
  const p = p01(f, a, 14);
  return { opacity: p, transform: `translateY(${(1 - p) * 26}px)` };
};

const Chip: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 26px", borderRadius: 999, background: "#fbfaf7", border: `1.5px solid ${C.hair}`, fontFamily: SANS, fontSize: 27, fontWeight: 500, color: C.ink }}>{children}</div>
);

export { Z_OVERVIEW };
