import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";

import { LogoMark } from "./kit";
import { C, SANS, SERIF } from "./theme";

/* ------------------------------------------------------------ paper + type */

export const Paper: React.FC = () => (
  <AbsoluteFill>
    <Img src={staticFile("paper.png")} style={{ width: 1920, height: 1080 }} />
  </AbsoluteFill>
);

/** Small tracked uppercase label (top-right running head in the reference style). */
export const RunningHead: React.FC<{ text: string; color?: string; opacity?: number }> = ({ text, color = C.primary, opacity = 1 }) => (
  <div style={{ position: "absolute", right: 72, top: 50, fontFamily: SANS, fontSize: 19, fontWeight: 600, letterSpacing: 3, color, opacity }}>
    {text}
  </div>
);

export const AccentBar: React.FC<{ color?: string; w?: number; p?: number; style?: React.CSSProperties }> = ({ color = C.primary, w = 46, p = 1, style }) => (
  <div style={{ width: w * p, height: 5, borderRadius: 3, background: color, ...style }} />
);

export const Stat: React.FC<{ label: string; value: string; color?: string; x: number; y: number; opacity?: number }> = ({
  label,
  value,
  color = C.ink,
  x,
  y,
  opacity = 1,
}) => (
  <div style={{ position: "absolute", left: x, top: y, opacity, fontFamily: SANS }}>
    <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: 2.5, color: C.ink2 }}>{label}</div>
    <div style={{ fontFamily: SERIF, fontSize: 58, fontWeight: 600, color, lineHeight: 1.05, fontVariantNumeric: "tabular-nums" }}>{value}</div>
  </div>
);

/* ------------------------------------------------------------ shimmer */

type Tone = "light" | "mid" | "dark" | "blue" | "white" | "navy";
const TONES: Record<Tone, [string, string]> = {
  light: ["#eceff3", "#f7f9fb"],
  mid: ["#dfe4ea", "#eef1f5"],
  dark: ["#c9d0d9", "#e1e6ec"],
  blue: ["#bcd8f7", "#dcebfb"],
  white: ["rgba(255,255,255,.55)", "rgba(255,255,255,.95)"],
  navy: ["#454d56", "#5a636d"],
};

export const Sh: React.FC<{ x: number; y: number; w: number; h?: number; tone?: Tone; r?: number; style?: React.CSSProperties }> = ({
  x,
  y,
  w,
  h = 10,
  tone = "light",
  r,
  style,
}) => {
  const f = useCurrentFrame();
  const [a, b] = TONES[tone];
  const pos = ((f * 14 + x * 0.6) % 900) - 300;
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: Math.max(0, w),
        height: h,
        borderRadius: r ?? h / 2,
        backgroundImage: `linear-gradient(90deg, ${a} 0px, ${b} 120px, ${a} 240px)`,
        backgroundColor: a,
        backgroundSize: "600px 100%",
        backgroundRepeat: "no-repeat",
        backgroundPositionX: pos,
        ...style,
      }}
    />
  );
};

/* ------------------------------------------------------------ browser frame */

export const Browser: React.FC<{ w: number; h: number; url: string; children: React.ReactNode }> = ({ w, h, url, children }) => (
  <div
    style={{
      position: "absolute",
      left: 0,
      top: 0,
      width: w,
      height: h,
      borderRadius: 16,
      background: "#fff",
      border: `1.5px solid ${C.hair}`,
      boxShadow: "0 24px 50px -34px rgba(40,35,25,.45)",
      overflow: "hidden",
      fontFamily: SANS,
    }}
  >
    <div style={{ height: 46, display: "flex", alignItems: "center", gap: 8, padding: "0 18px", borderBottom: "1px solid #e3e6ea", background: "#fafafa" }}>
      <span style={{ width: 11, height: 11, borderRadius: 99, border: "1.3px solid #b9bec5" }} />
      <span style={{ width: 11, height: 11, borderRadius: 99, border: "1.3px solid #b9bec5" }} />
      <span style={{ width: 11, height: 11, borderRadius: 99, border: "1.3px solid #b9bec5" }} />
      <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
        <div style={{ padding: "4px 18px", borderRadius: 8, background: "#f0f1f3", fontSize: 14, color: "#7a828c" }}>{url}</div>
      </div>
      <span style={{ width: 33 }} />
    </div>
    <div style={{ position: "absolute", left: 0, top: 46, right: 0, bottom: 0 }}>{children}</div>
  </div>
);

/* ===================================================================
   Product app window — 840 x 740, layout coords include the 46px bar
   =================================================================== */

export const APP_W = 840;
export const APP_H = 740;
const ROW_Y = (r: number) => 334 + 58 * r; // top of row r (window coords)

export const APPA = {
  tabDrafts: [100, 266] as const,
  tabSubmitted: [235, 266] as const,
  search: [210, 216] as const,
  newBtn: [730, 140] as const,
  rowName: (r: number) => [150, ROW_Y(r) + 29] as const,
  status: (r: number) => [537, ROW_Y(r) + 29] as const,
  rowBtn: (r: number) => [746, ROW_Y(r) + 29] as const,
};

export type AppState = {
  tab?: "drafts" | "submitted";
  searchChars?: number; // typed characters in the search box
  searchFocus?: boolean;
  hlRow?: number | null;
  rowFlash?: number; // 0..1 highlight pulse on hlRow
  statusOverride?: Record<number, "draft" | "support" | "done">;
  contentOpacity?: number;
  resetFlash?: number; // 0..1 white refresh flash
};

const STATUS_STYLE = {
  draft: { bg: "#eef0f3", bd: "#d8dce1", bar: "mid" as Tone },
  support: { bg: "#e5f0fd", bd: "#bcd8f7", bar: "blue" as Tone },
  done: { bg: "#e2f5eb", bd: "#b5e3c9", bar: "mid" as Tone },
};

export const AppWindow: React.FC<{ s?: AppState }> = ({ s = {} }) => {
  const tab = s.tab ?? "drafts";
  const rows = [0, 1, 2, 3, 4, 5];
  const baseStatus: ("draft" | "support" | "done")[] =
    tab === "drafts" ? ["draft", "draft", "draft", "draft", "draft", "draft"] : ["support", "done", "support", "support", "done", "support"];
  return (
    <Browser w={APP_W} h={APP_H} url="app.example.com">
      <div style={{ position: "absolute", inset: 0, opacity: s.contentOpacity ?? 1 }}>
        {/* app header */}
        <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 66, borderBottom: "1px solid #e8ebef", background: "linear-gradient(90deg,#f6f9ff,#fbf7ff)" }}>
          <Img src={staticFile("logo.png")} style={{ position: "absolute", left: 26, top: 15, height: 34 }} />
          <Sh x={120} y={27} w={200} h={12} tone="mid" />
          <span style={{ position: "absolute", left: 690, top: 22, width: 22, height: 22, borderRadius: 99, border: "1.5px solid #b9c1ca" }} />
          <span style={{ position: "absolute", left: 732, top: 22, width: 22, height: 22, borderRadius: 99, border: "1.5px solid #b9c1ca" }} />
          <span style={{ position: "absolute", left: 772, top: 13, width: 40, height: 40, borderRadius: 99, background: "#ecdff8" }} />
        </div>
        {/* page heading (window coords minus 46 for this inner layer) */}
        <Sh x={40} y={98} w={210} h={22} tone="dark" r={6} />
        <Sh x={40} y={132} w={380} h={10} tone="light" />
        <div style={{ position: "absolute", left: 660, top: 74, width: 140, height: 40, borderRadius: 10, background: C.primary }}>
          <Sh x={30} y={15} w={80} h={10} tone="white" />
        </div>
        {/* search */}
        <div style={{ position: "absolute", left: 40, top: 150, width: 360, height: 40, borderRadius: 10, border: `1.5px solid ${s.searchFocus ? C.primary : "#d8dde3"}`, background: "#fff" }}>
          <span style={{ position: "absolute", left: 13, top: 12, width: 13, height: 13, borderRadius: 99, border: "2px solid #9aa4ae" }} />
          {s.searchChars ? <Sh x={36} y={15} w={Math.min(300, s.searchChars * 13)} h={10} tone="dark" /> : <Sh x={36} y={15} w={150} h={9} tone="light" />}
          {s.searchFocus && <span style={{ position: "absolute", left: 40 + Math.min(300, (s.searchChars ?? 0) * 13), top: 10, width: 2, height: 20, background: C.primary }} />}
        </div>
        {/* tabs */}
        <div style={{ position: "absolute", left: 40, right: 40, top: 236, height: 1, background: "#e3e6ea" }} />
        {(["drafts", "submitted"] as const).map((t, i) => {
          const active = tab === t;
          const x = i === 0 ? 40 : 172;
          return (
            <div key={t} style={{ position: "absolute", left: x, top: 200, width: i === 0 ? 116 : 130, height: 37, borderBottom: active ? `3px solid ${C.primary}` : "3px solid transparent" }}>
              {i === 1 ? (
                <LogoMark style={{ position: "absolute", left: 8, top: 9, width: 16, height: 14 }} />
              ) : (
                <span style={{ position: "absolute", left: 9, top: 9, width: 13, height: 15, borderRadius: 2, border: "1.6px solid #9aa4ae" }} />
              )}
              <Sh x={32} y={13} w={i === 0 ? 46 : 62} h={10} tone={active ? "dark" : "mid"} />
              <span style={{ position: "absolute", left: i === 0 ? 86 : 102, top: 9, width: 22, height: 18, borderRadius: 9, background: active ? "#dcebfb" : "#eef0f3" }} />
            </div>
          );
        })}
        {/* table */}
        <div style={{ position: "absolute", left: 40, top: 250, width: 760, height: 400, borderRadius: 12, border: "1px solid #e3e6ea", overflow: "hidden" }}>
          <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 38, background: "#f5f7f9", borderBottom: "1px solid #e3e6ea" }}>
            <Sh x={16} y={14} w={70} h={8} tone="mid" />
            <Sh x={258} y={14} w={56} h={8} tone="mid" />
            <Sh x={455} y={14} w={52} h={8} tone="mid" />
            <Sh x={565} y={14} w={60} h={8} tone="mid" />
          </div>
          {rows.map((r) => {
            const y = 38 + 58 * r;
            const st = s.statusOverride?.[r] ?? baseStatus[r];
            const ss = STATUS_STYLE[st];
            const hl = s.hlRow === r;
            return (
              <div key={r} style={{ position: "absolute", left: 0, right: 0, top: y, height: 58, borderBottom: "1px solid #eef0f3", background: hl ? `rgba(13,128,242,${0.06 + 0.1 * (s.rowFlash ?? 0)})` : "transparent" }}>
                {hl && <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: C.primary }} />}
                <Sh x={16} y={15} w={[200, 160, 220, 180, 150, 210][r]} h={11} tone="dark" />
                <Sh x={16} y={34} w={44} h={8} tone="light" />
                <span style={{ position: "absolute", left: 258, top: 17, width: 24, height: 24, borderRadius: 7, background: "#f1f3f6", border: "1px solid #e1e5ea" }} />
                <Sh x={292} y={24} w={[120, 90, 130, 110, 100, 125][r]} h={10} tone="mid" />
                <div style={{ position: "absolute", left: 455, top: 17, width: 84, height: 24, borderRadius: 12, background: ss.bg, border: `1px solid ${ss.bd}` }}>
                  <Sh x={14} y={8} w={54} h={7} tone={ss.bar} />
                </div>
                <Sh x={565} y={24} w={70} h={9} tone="light" />
                <div style={{ position: "absolute", left: 670, top: 13, width: 74, height: 32, borderRadius: 9, border: "1.5px solid #d3d8de", background: "#fff" }}>
                  {tab === "submitted" && <LogoMark style={{ position: "absolute", left: 9, top: 8, width: 15, height: 13 }} />}
                  <Sh x={tab === "submitted" ? 30 : 16} y={11} w={tab === "submitted" ? 30 : 40} h={8} tone="mid" />
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {(s.resetFlash ?? 0) > 0 && <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: s.resetFlash }} />}
    </Browser>
  );
};

/* ===================================================================
   Help desk window — 840 x 740
   =================================================================== */

export const HD_W = 840;
export const HD_H = 740;
const B = 46; // browser bar height; anchors below are in window coords

export const HDA = {
  overview: (i: number) => [172, B + 52 + 64 * i + 29] as const,
  article: (i: number) => [450, B + 96 + 108 * i + 44] as const,
  thread: [450, B + 300] as const,
  compose: [450, B + 594] as const,
  stateSelect: [730, B + 128] as const,
  stateOption: (k: number) => [730, B + 152 + 34 * k + 17] as const,
  updateBtn: [730, B + 605] as const,
  title: [420, B + 36] as const,
};

export type HDState = {
  selected?: number | null;
  loaded?: number; // 0..1 ticket view opacity
  scroll?: number; // px
  composeChars?: number;
  composeFocus?: boolean;
  dropdown?: boolean;
  stateValue?: number; // 0 open, 1 pending, 2 ready for approval, 3 closed
  stateFlash?: number;
  updatePulse?: number;
  newArticle?: number; // 0..1
  readSweep?: number | null; // y of reading highlight band (thread coords)
  check?: number;
  contentOpacity?: number;
  resetFlash?: number;
};

const STATE_DOT = ["#9aa4ae", "#e8b21f", "#2f80ed", "#3aa86a"];

export const HDWindow: React.FC<{ s?: HDState }> = ({ s = {} }) => {
  const loaded = s.loaded ?? 1;
  const scroll = s.scroll ?? 0;
  const articles = [
    { side: "l", lines: [220, 200, 140] },
    { side: "r", lines: [210, 230, 120] },
    { side: "l", lines: [230, 170, 190] },
    { side: "r", lines: [200, 150, 0] },
    { side: "l", lines: [220, 210, 160] },
    { side: "r", lines: [190, 220, 100] },
  ];
  const sv = s.stateValue ?? 0;
  return (
    <Browser w={HD_W} h={HD_H} url="help.example.com">
      <div style={{ position: "absolute", inset: 0, opacity: s.contentOpacity ?? 1 }}>
        {/* dark nav */}
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 64, background: "#2c3237" }}>
          <LogoMark style={{ position: "absolute", left: 13, top: 14, width: 38, height: 33 }} />
          {[84, 132, 180, 228].map((y, i) => (
            <span key={y} style={{ position: "absolute", left: 21, top: y, width: 22, height: 22, borderRadius: i === 0 ? 6 : 99, border: `2px solid ${i === 1 ? "#cfd5db" : "#69727c"}` }} />
          ))}
          <span style={{ position: "absolute", left: 16, bottom: 18, width: 32, height: 32, borderRadius: 99, background: "#4b545d" }} />
        </div>
        {/* overview list */}
        <div style={{ position: "absolute", left: 64, top: 0, bottom: 0, width: 216, background: "#f4f5f7", borderRight: "1px solid #e1e4e8" }}>
          <Sh x={16} y={22} w={110} h={12} tone="dark" />
          <span style={{ position: "absolute", left: 172, top: 18, width: 26, height: 20, borderRadius: 10, background: "#e1e5ea" }} />
          {Array.from({ length: 9 }, (_, i) => {
            const sel = s.selected === i;
            return (
              <div key={i} style={{ position: "absolute", left: 6, right: 6, top: 52 + 64 * i, height: 58, borderRadius: 8, background: sel ? "#fff" : "transparent", boxShadow: sel ? "0 1px 3px rgba(0,0,0,.08)" : undefined }}>
                {sel && <div style={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 3, borderRadius: 2, background: C.helpdesk }} />}
                <span style={{ position: "absolute", left: 12, top: 12, width: 9, height: 9, borderRadius: 99, background: STATE_DOT[(i * 3) % 4] }} />
                <Sh x={30} y={11} w={[140, 120, 150, 110, 135, 125, 145, 105, 130][i]} h={10} tone={sel ? "dark" : "mid"} />
                <Sh x={30} y={32} w={[90, 110, 70, 100, 85, 95, 75, 105, 80][i]} h={8} tone="light" />
              </div>
            );
          })}
        </div>
        {/* ticket zoom */}
        <div style={{ position: "absolute", left: 280, top: 0, width: 340, bottom: 0, opacity: loaded }}>
          <Sh x={16} y={20} w={250} h={18} tone="dark" r={5} />
          <Sh x={16} y={48} w={160} h={8} tone="light" />
          <div style={{ position: "absolute", left: 0, right: 0, top: 70, height: 1, background: "#e6e9ed" }} />
          <div style={{ position: "absolute", left: 0, right: 0, top: 72, height: 450, overflow: "hidden" }}>
            {s.readSweep != null && (
              <div style={{ position: "absolute", left: 0, right: 0, top: s.readSweep - 30, height: 60, background: "linear-gradient(180deg, transparent, rgba(217,119,87,.12), transparent)" }} />
            )}
            {[...articles, ...(s.newArticle ? [{ side: "r", lines: [230, 210, 170], fresh: true }] : [])].map((a, i) => {
              const top = 24 + 108 * i - scroll;
              const left = a.side === "l";
              const fresh = "fresh" in a;
              return (
                <div key={i} style={{ position: "absolute", top, left: left ? 14 : 60, width: 266, height: 90, opacity: fresh ? s.newArticle : 1, transform: fresh ? `translateY(${(1 - (s.newArticle ?? 0)) * 20}px)` : undefined }}>
                  <span style={{ position: "absolute", [left ? "left" : "right"]: -2, top: 0, width: 24, height: 24, borderRadius: 99, background: left ? "#e2e6ea" : fresh ? "#f3d5c8" : "#d6e9de" } as React.CSSProperties} />
                  <div style={{ position: "absolute", left: left ? 32 : 0, right: left ? 0 : 32, top: 0, bottom: 0, borderRadius: 10, background: left ? "#fff" : fresh ? "#fbefe9" : "#eef7f1", border: `1px solid ${left ? "#e1e5ea" : fresh ? "#f0cdbd" : "#d3eadb"}` }}>
                    {a.lines.map((w, k) => (w ? <Sh key={k} x={14} y={16 + 22 * k} w={w * 0.82} h={9} tone={k === 0 ? "dark" : "mid"} /> : null))}
                  </div>
                </div>
              );
            })}
          </div>
          {/* compose */}
          <div style={{ position: "absolute", left: 14, right: 14, top: 532, height: 132, borderRadius: 10, border: `1.5px solid ${s.composeFocus ? C.helpdesk : "#d8dde3"}`, background: "#fff" }}>
            {s.composeChars ? (
              [0, 1, 2, 3].map((k) => {
                const w = Math.max(0, Math.min(270, (s.composeChars ?? 0) * 7 - k * 270));
                return w > 0 ? <Sh key={k} x={14} y={16 + 24 * k} w={w} h={10} tone="dark" /> : null;
              })
            ) : (
              <Sh x={14} y={16} w={130} h={9} tone="light" />
            )}
            {s.composeFocus && (() => {
              const c = (s.composeChars ?? 0) * 7;
              const line = Math.min(3, Math.floor(c / 270));
              const x = 16 + Math.min(270, c - line * 270);
              return <span style={{ position: "absolute", left: x, top: 12 + 24 * line, width: 2, height: 18, background: C.helpdesk }} />;
            })()}
          </div>
        </div>
        {/* attribute sidebar */}
        <div style={{ position: "absolute", left: 620, top: 0, right: 0, bottom: 0, borderLeft: "1px solid #e1e4e8", background: "#fbfbfc", opacity: loaded }}>
          {[0, 1, 2, 3, 4].map((k) => {
            const isState = k === 1;
            return (
              <div key={k}>
                <Sh x={16} y={22 + 70 * k} w={[60, 44, 56, 50, 48][k]} h={8} tone="mid" />
                <div style={{ position: "absolute", left: 16, top: 40 + 70 * k, width: 188, height: 36, borderRadius: 8, border: `1.5px solid ${isState && s.dropdown ? C.helpdesk : "#d8dde3"}`, background: isState && (s.stateFlash ?? 0) > 0 ? `rgba(58,168,106,${0.18 * (s.stateFlash ?? 0)})` : "#fff" }}>
                  {isState && <span style={{ position: "absolute", left: 12, top: 13, width: 10, height: 10, borderRadius: 99, background: STATE_DOT[sv] }} />}
                  <Sh x={isState ? 30 : 12} y={14} w={isState ? [70, 84, 120, 60][sv] : [110, 0, 70, 96, 80][k]} h={9} tone={isState ? "dark" : "mid"} />
                  <span style={{ position: "absolute", right: 12, top: 12, width: 8, height: 8, borderRight: "2px solid #9aa4ae", borderBottom: "2px solid #9aa4ae", transform: "rotate(45deg)" }} />
                </div>
              </div>
            );
          })}
          {/* update button */}
          <div style={{ position: "absolute", left: 16, top: 584, width: 188, height: 42, borderRadius: 9, background: C.helpdesk, boxShadow: (s.updatePulse ?? 0) > 0 ? `0 0 0 ${8 * (s.updatePulse ?? 0)}px rgba(58,168,106,${0.35 * (1 - (s.updatePulse ?? 0))})` : undefined }}>
            <Sh x={60} y={16} w={68} h={10} tone="white" />
          </div>
          {(s.check ?? 0) > 0 && (
            <svg width="34" height="34" viewBox="0 0 24 24" style={{ position: "absolute", left: 172, top: 538 }}>
              <circle cx="12" cy="12" r="11" fill="#e2f5eb" opacity={s.check} />
              <path d="M6.5 12.5l3.5 3.5 7.5-8" stroke={C.helpdesk} strokeWidth={2.6} fill="none" strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - (s.check ?? 0)} />
            </svg>
          )}
        </div>
        {/* state dropdown (drawn last so it overlaps the fields below) */}
        {s.dropdown && (
          <div style={{ position: "absolute", left: 636, top: 148, width: 188, borderRadius: 9, background: "#fff", border: "1px solid #d8dde3", boxShadow: "0 16px 30px -14px rgba(0,0,0,.3)", padding: "4px 0" }}>
            {[0, 1, 2, 3].map((k) => (
              <div key={k} style={{ position: "relative", height: 34, background: k === sv ? "#eef7f1" : "transparent" }}>
                <span style={{ position: "absolute", left: 12, top: 12, width: 10, height: 10, borderRadius: 99, background: STATE_DOT[k] }} />
                <Sh x={30} y={13} w={[70, 84, 120, 60][k]} h={8} tone="mid" />
              </div>
            ))}
          </div>
        )}
      </div>
      {(s.resetFlash ?? 0) > 0 && <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: s.resetFlash }} />}
    </Browser>
  );
};
