import React from "react";
import { Img, staticFile } from "remotion";

import { Icon, IconName } from "./icons";
import { SANS } from "./theme";

/* =====================================================================
   Product dashboard look-alike. Content is laid out in "content"
   coordinates (1700 x 954, below the browser bar); `world()` maps them to
   the 1920x1080 stage so cameras and cursors target real anchors.
   ===================================================================== */

export const BX = 110;
export const BY = 40;
export const BW = 1700;
export const BH = 1000;
export const BAR = 46;
export const world = (x: number, y: number) => [BX + x, BY + BAR + y] as const;
export const worldRect = (x: number, y: number, w: number, h: number) => ({ x: BX + x, y: BY + BAR + y, w, h });

export const D = {
  fg: "#0f1e2e",
  muted: "#456789",
  border: "#d6dde6",
  page: "#f8fafc",
  card: "#ffffff",
  primary: "#0d80f2",
  red: "#dc2626",
  redBg: "#fdf3f3",
  redBd: "#f2b8b8",
  redChip: "#fde3e3",
  amber: "#d97706",
  amberChip: "#fdf0d5",
  blueChip: "#e0f2fe",
  blueChipFg: "#075985",
  purple: "#7c3aed",
  purpleChip: "#ede6fd",
  green: "#16a34a",
  greenChip: "#dcf5e5",
  grey: "#94a3b8",
};

export const PADX = 110;
export const CW = 1480;

/* ------------------------------------------------------------- chrome */

export const BrowserFrame: React.FC<{ url: string; children: React.ReactNode; style?: React.CSSProperties }> = ({ url, children, style }) => (
  <div
    style={{
      position: "absolute",
      left: BX,
      top: BY,
      width: BW,
      height: BH,
      borderRadius: 18,
      background: D.page,
      border: "1.5px solid rgba(30,33,36,0.82)",
      boxShadow: "0 30px 60px -36px rgba(40,35,25,.5)",
      overflow: "hidden",
      fontFamily: SANS,
      color: D.fg,
      ...style,
    }}
  >
    <div style={{ height: BAR, display: "flex", alignItems: "center", gap: 8, padding: "0 18px", borderBottom: "1px solid #e3e6ea", background: "#fafafa" }}>
      {[0, 1, 2].map((i) => (
        <span key={i} style={{ width: 12, height: 12, borderRadius: 99, border: "1.3px solid #b9bec5" }} />
      ))}
      <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
        <div style={{ padding: "5px 22px", borderRadius: 8, background: "#f0f1f3", fontSize: 16, color: "#6b737d" }}>{url}</div>
      </div>
      <span style={{ width: 40 }} />
    </div>
    <div style={{ position: "absolute", left: 0, top: BAR, right: 0, bottom: 0 }}>{children}</div>
  </div>
);

export const AppHeader: React.FC<{ initials: string; avatar: string }> = ({ initials, avatar }) => (
  <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 80, background: "#fff", borderBottom: `1px solid ${D.border}`, display: "flex", alignItems: "center", padding: "0 44px", gap: 22 }}>
    <Img src={staticFile("logo.png")} style={{ height: 42 }} />
    <div style={{ fontSize: 24, fontWeight: 500 }}>Internal use only</div>
    <div style={{ flex: 1 }} />
    <Icon n="bell" size={24} color={D.muted} />
    <div style={{ width: 46, height: 46, borderRadius: 99, background: avatar, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 18 }}>{initials}</div>
  </div>
);

export const PageTitle: React.FC<{ title: string; sub: string; settings?: boolean; settingsPress?: number }> = ({ title, sub, settings, settingsPress = 0 }) => (
  <>
    <div style={{ position: "absolute", left: PADX, top: 108, fontSize: 46, fontWeight: 700, letterSpacing: -0.5 }}>{title}</div>
    <div style={{ position: "absolute", left: PADX, top: 168, fontSize: 21, color: D.muted }}>{sub}</div>
    <div style={{ position: "absolute", right: PADX, top: 120, display: "flex", alignItems: "center", gap: 14 }}>
      <span style={{ fontSize: 17, color: D.muted }}>Updated 9:41 AM</span>
      {settings && <Btn icon="sliders" label="Settings" w={150} press={settingsPress} />}
      <Btn icon="refresh" label="Refresh" w={150} />
    </div>
  </>
);

export const SETTINGS_BTN = world(PADX + CW - 150 - 14 - 75, 145);

export const Btn: React.FC<{
  icon?: IconName;
  label: string;
  kind?: "outline" | "primary" | "danger";
  w?: number;
  h?: number;
  press?: number;
  trailing?: IconName;
  iconColor?: string;
  style?: React.CSSProperties;
}> = ({ icon, label, kind = "outline", w, h = 50, press = 0, trailing, iconColor, style }) => {
  const primary = kind === "primary";
  return (
    <div
      style={{
        height: h,
        width: w,
        padding: w ? 0 : "0 20px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 10,
        borderRadius: 10,
        border: primary ? "none" : `1.5px solid ${D.border}`,
        background: primary ? D.primary : "#fff",
        color: primary ? "#fff" : D.fg,
        fontSize: 19,
        fontWeight: 500,
        transform: `scale(${1 - 0.06 * press})`,
        boxShadow: press > 0 ? `0 0 0 ${10 * press}px rgba(13,128,242,${0.25 * press})` : undefined,
        flex: "none",
        ...style,
      }}
    >
      {icon && <Icon n={icon} size={20} color={iconColor ?? (primary ? "#fff" : D.fg)} />}
      {label}
      {trailing && <Icon n={trailing} size={18} color={D.fg} />}
    </div>
  );
};

/* ------------------------------------------------------------- tiles */

export type TileDef = { label: string; value: number | string; hint: string; color: string; icon: IconName; selected?: boolean };

export const Tiles: React.FC<{ y: number; tiles: TileDef[]; hl?: number | null; hlP?: number; h?: number }> = ({ y, tiles, hl = null, hlP = 0, h = 124 }) => {
  const gap = 18;
  const w = (CW - gap * (tiles.length - 1)) / tiles.length;
  return (
    <>
      {tiles.map((t, i) => {
        const on = hl === i;
        const muted = t.value === 0;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: PADX + i * (w + gap),
              top: y,
              width: w,
              height: h,
              borderRadius: 16,
              background: "#fff",
              border: `1.5px solid ${t.selected ? "#9cc8f5" : D.border}`,
              boxShadow: on ? `0 0 0 ${4 * hlP}px ${t.color}33, 0 10px 24px -14px ${t.color}` : t.selected ? "0 0 0 3px #e3effc" : undefined,
              transform: on ? `translateY(${-4 * hlP}px)` : undefined,
              padding: "20px 22px",
              boxSizing: "border-box",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 20, color: D.muted }}>
              {t.label}
              <Icon n={t.icon} size={22} color={t.color} />
            </div>
            <div style={{ fontSize: 44, fontWeight: 600, color: muted ? D.grey : t.color, lineHeight: 1.15, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>{t.value}</div>
            <div style={{ fontSize: 17, color: D.muted, marginTop: 2 }}>{t.hint}</div>
          </div>
        );
      })}
    </>
  );
};

export const tileRect = (y: number, n: number, i: number, h = 124) => {
  const gap = 18;
  const w = (CW - gap * (n - 1)) / n;
  return worldRect(PADX + i * (w + gap), y, w, h);
};
export const tilesRect = (y: number, h = 124) => worldRect(PADX, y, CW, h);

/* --------------------------------------------------- search + legend */

export const SearchBar: React.FC<{ y: number }> = ({ y }) => (
  <>
    <div style={{ position: "absolute", left: PADX, top: y, width: 520, height: 52, borderRadius: 10, border: `1.5px solid ${D.border}`, background: "#fff", display: "flex", alignItems: "center", gap: 12, padding: "0 16px", boxSizing: "border-box", fontSize: 19, color: D.muted }}>
      <Icon n="search" size={20} color={D.muted} />
      Search title, number, customer, agent
    </div>
    <div style={{ position: "absolute", right: PADX, top: y + 14, display: "flex", gap: 22, fontSize: 17, color: D.muted }}>
      {([
        ["Submitted", D.grey],
        ["Support review", "#0ea5e9"],
        ["Awaiting response", "#f5b40b"],
        ["Approval", "#8b5cf6"],
        ["Done", "#22c55e"],
      ] as const).map(([l, c]) => (
        <span key={l} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 10, height: 10, borderRadius: 99, background: c }} />
          {l}
        </span>
      ))}
    </div>
  </>
);

export const SectionHead: React.FC<{ y: number; title: string; count: number; opacity?: number }> = ({ y, title, count, opacity = 1 }) => (
  <div style={{ position: "absolute", left: PADX, top: y, display: "flex", alignItems: "center", gap: 12, fontSize: 20, fontWeight: 600, opacity }}>
    {title}
    <span style={{ minWidth: 30, height: 30, borderRadius: 99, background: "#e8edf3", fontSize: 16, fontWeight: 500, color: D.muted, display: "flex", alignItems: "center", justifyContent: "center", padding: "0 8px", boxSizing: "border-box" }}>{count}</span>
  </div>
);

/* --------------------------------------------------------------- rows */

export type Seg = [string, number];
const SEG = { sub: D.grey, support: "#0ea5e9", await: "#f5b40b", sig: "#8b5cf6" };
export const strip = (...s: [keyof typeof SEG, number][]): Seg[] => s.map(([k, v]) => [SEG[k], v]);

export type RowDef = {
  title: string;
  meta: string;
  icon?: IconName;
  accent: "red" | "amber" | "none";
  chip: { text: string; tone: "blue" | "amber" | "purple" | "grey" };
  stateLabel: string;
  wait: { text: string; tone: "red" | "amber" | "muted"; bold?: boolean };
  person: string;
  strip: Seg[];
  stripW?: number;
  buttons: ("helpdesk" | "escalate" | "clear")[];
};

export type RowFx = {
  tint?: number; // 0..1 escalated red treatment
  badge?: { text: string; tone: "red" | "green"; p: number } | null;
  line?: { text: React.ReactNode; p: number } | null;
  note?: { text: string; p: number } | null;
  pressEscalate?: number;
  pressClear?: number;
  hl?: number; // 0..1 focus ring
  opacity?: number;
  dy?: number;
};

const CHIP = {
  blue: [D.blueChip, D.blueChipFg],
  amber: [D.amberChip, "#92400e"],
  purple: [D.purpleChip, "#5b21b6"],
  grey: ["#eef1f5", "#475569"],
} as const;

export const ROW_H = 132;
export const ROW_COL2 = 800;
export const ROW_COL3 = CW - 232;

export const Row: React.FC<{ y: number; h?: number; r: RowDef; fx?: RowFx }> = ({ y, h = ROW_H, r, fx = {} }) => {
  const tint = fx.tint ?? 0;
  const accent = r.accent === "red" ? D.red : r.accent === "amber" ? "#f5b40b" : "transparent";
  const mix = (a: string, b: string) => `color-mix(in srgb, ${b} ${Math.round(tint * 100)}%, ${a})`;
  const waitColor = r.wait.tone === "red" ? D.red : r.wait.tone === "amber" ? D.amber : D.muted;
  return (
    <div
      style={{
        position: "absolute",
        left: PADX,
        top: y + (fx.dy ?? 0),
        width: CW,
        height: h,
        borderRadius: 16,
        background: mix("#ffffff", D.redBg),
        border: `1.5px solid ${mix(D.border, D.redBd)}`,
        overflow: "hidden",
        opacity: fx.opacity ?? 1,
        boxShadow: fx.hl ? `0 0 0 ${5 * fx.hl}px rgba(13,128,242,${0.22 * fx.hl})` : undefined,
      }}
    >
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 6, background: accent }} />
      {/* left column */}
      <div style={{ position: "absolute", left: 28, top: 22, width: 50, height: 50, borderRadius: 12, background: "#eef2f6", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Icon n={r.icon ?? "file"} size={24} color="#7b8da3" />
      </div>
      <div style={{ position: "absolute", left: 96, top: 20, width: ROW_COL2 - 120 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 23, fontWeight: 500, whiteSpace: "nowrap" }}>{r.title}</span>
          {fx.badge && fx.badge.p > 0 && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "3px 12px",
                borderRadius: 99,
                fontSize: 16,
                fontWeight: 600,
                background: fx.badge.tone === "red" ? D.redChip : D.greenChip,
                color: fx.badge.tone === "red" ? D.red : D.green,
                opacity: fx.badge.p,
                transform: `scale(${0.6 + 0.4 * fx.badge.p})`,
                whiteSpace: "nowrap",
              }}
            >
              <Icon n={fx.badge.tone === "red" ? "flame" : "checkCheck"} size={15} color={fx.badge.tone === "red" ? D.red : D.green} />
              {fx.badge.text}
            </span>
          )}
        </div>
        <div style={{ fontSize: 17, color: D.muted, marginTop: 6 }}>{r.meta}</div>
        <div style={{ display: "flex", marginTop: 12, width: r.stripW ?? 560, height: 8, borderRadius: 99, overflow: "hidden" }}>
          {r.strip.map(([c, w], i) => (
            <div key={i} style={{ width: `${w * 100}%`, background: c }} />
          ))}
        </div>
        {fx.line && fx.line.p > 0 && (
          <div style={{ fontSize: 17, marginTop: 12, opacity: fx.line.p, transform: `translateY(${(1 - fx.line.p) * 8}px)` }}>{fx.line.text}</div>
        )}
        {fx.note && fx.note.p > 0 && (
          <div style={{ fontSize: 17, color: D.fg, marginTop: 4, opacity: fx.note.p, fontStyle: "italic" }}>“{fx.note.text}”</div>
        )}
      </div>
      {/* middle column */}
      <div style={{ position: "absolute", left: ROW_COL2, top: 22 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 17 }}>
          <span style={{ padding: "3px 12px", borderRadius: 8, background: CHIP[r.chip.tone][0], color: CHIP[r.chip.tone][1], fontWeight: 500 }}>{r.chip.text}</span>
          <span style={{ color: D.muted }}>{r.stateLabel}</span>
        </div>
        <div style={{ fontSize: 22, color: waitColor, fontWeight: r.wait.bold ? 600 : 400, marginTop: 10 }}>{r.wait.text}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 17, color: D.muted, marginTop: 8 }}>
          <Icon n="user" size={17} color={D.muted} />
          {r.person}
        </div>
      </div>
      {/* actions */}
      <div style={{ position: "absolute", left: ROW_COL3, top: 0, bottom: 0, width: 212, display: "flex", flexDirection: "column", justifyContent: "center", gap: 10 }}>
        {r.buttons.map((b) =>
          b === "helpdesk" ? (
            <Btn key={b} label="Open in Help desk" w={212} h={50} trailing="arrowUR" style={{ gap: 10 }} />
          ) : b === "escalate" ? (
            <Btn key={b} icon="flame" iconColor={D.red} label="Escalate" w={212} h={50} press={fx.pressEscalate} />
          ) : (
            <Btn key={b} icon="checkCheck" label="Clear escalation" w={212} h={50} press={fx.pressClear} />
          )
        )}
      </div>
    </div>
  );
};

/** World anchor for a row's button (index within its buttons list). */
export const rowBtn = (y: number, h: number, nButtons: number, k: number) => {
  const total = nButtons * 50 + (nButtons - 1) * 10;
  const top = y + (h - total) / 2 + k * 60;
  return world(PADX + ROW_COL3 + 106, top + 25);
};
export const rowRect = (y: number, h = ROW_H) => worldRect(PADX, y, CW, h);
export const rowWaitRect = (y: number) => worldRect(PADX + ROW_COL2 - 10, y + 12, 440, 110);

/* --------------------------------------------------- escalate dialog */

export const DLG = { x: 470, y: 170, w: 760, h: 540 };
export const NOTE_TEXT = "Customer goes live Friday. We need an answer by Thursday.";

export const EscalateDialog: React.FC<{ p: number; chars: number; press: number; ticket: string; agent: string; wait: string }> = ({ p, chars, press, ticket, agent, wait }) => {
  if (p <= 0) return null;
  const typedText = NOTE_TEXT.slice(0, chars);
  return (
    <>
      <div style={{ position: "absolute", inset: 0, background: `rgba(15,23,42,${0.45 * p})` }} />
      <div
        style={{
          position: "absolute",
          left: DLG.x,
          top: DLG.y,
          width: DLG.w,
          height: DLG.h,
          borderRadius: 18,
          background: "#fff",
          boxShadow: "0 30px 80px -20px rgba(0,0,0,.45)",
          opacity: p,
          transform: `scale(${0.92 + 0.08 * p}) translateY(${(1 - p) * 20}px)`,
          padding: "30px 34px",
          boxSizing: "border-box",
        }}
      >
        <div style={{ position: "absolute", right: 26, top: 26 }}>
          <Icon n="x" size={22} color={D.muted} />
        </div>
        <div style={{ fontSize: 27, fontWeight: 600 }}>Escalate this ticket?</div>
        <div style={{ fontSize: 19, color: D.muted, marginTop: 6 }}>{ticket}</div>
        <div style={{ fontSize: 19, color: D.muted, marginTop: 18, lineHeight: 1.45 }}>
          We'll post a note on the ticket tagging <b style={{ color: D.fg, fontWeight: 600 }}>{agent}</b> and the team lead who routed it, mark it escalated and email them. It stays escalated until someone on the support side clears it. You have been waiting on Support for {wait}.
        </div>
        <div style={{ fontSize: 19, fontWeight: 500, marginTop: 18 }}>
          Note <span style={{ color: D.muted, fontWeight: 400 }}>(optional)</span>
        </div>
        <div style={{ marginTop: 8, height: 118, borderRadius: 10, border: `2px solid ${chars > 0 ? D.primary : D.border}`, boxShadow: chars > 0 ? "0 0 0 4px rgba(13,128,242,.12)" : undefined, padding: "12px 14px", boxSizing: "border-box", fontSize: 20, lineHeight: 1.4, color: chars > 0 ? D.fg : "#8aa0b6" }}>
          {chars > 0 ? (
            <>
              {typedText}
              {chars < NOTE_TEXT.length + 8 && <span style={{ display: "inline-block", width: 2, height: 22, background: D.primary, marginLeft: 2, verticalAlign: -4 }} />}
            </>
          ) : (
            "What do you need, and by when?"
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10, fontSize: 16, color: D.muted }}>
          <span>The note is visible on the ticket to everyone on it.</span>
          <span>{typedText.length}/2000</span>
        </div>
        <div style={{ position: "absolute", right: 34, bottom: 30, display: "flex", gap: 14, alignItems: "center" }}>
          <span style={{ fontSize: 19, padding: "0 18px" }}>Cancel</span>
          <Btn kind="primary" icon="flame" label="Escalate" w={170} h={54} press={press} />
        </div>
      </div>
    </>
  );
};
export const DLG_NOTE = worldRect(DLG.x + 34, DLG.y + 300, DLG.w - 68, 130);
export const DLG_BTN = world(DLG.x + DLG.w - 34 - 85, DLG.y + DLG.h - 30 - 27);
export const DLG_RECT = worldRect(DLG.x, DLG.y, DLG.w, DLG.h);

/* ----------------------------------------------------- agent load */

export const LoadTable: React.FC<{ y: number; rows: [string, number, number, number, number, string][]; hl?: number }> = ({ y, rows, hl = 0 }) => {
  const cols = [["Open", 960], ["Their move", 1080], ["Overdue", 1210], ["Escalated", 1320], ["Longest wait", 1440]] as const;
  return (
    <div style={{ position: "absolute", left: PADX, top: y, width: CW, height: 70 + 46 + rows.length * 54, borderRadius: 16, background: "#fff", border: `1.5px solid ${D.border}`, overflow: "hidden", boxShadow: hl ? `0 0 0 ${5 * hl}px rgba(13,128,242,${0.2 * hl})` : undefined }}>
      <div style={{ height: 66, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 24px", borderBottom: `1px solid ${D.border}`, fontSize: 21, fontWeight: 600 }}>
        Agent load
        <span style={{ fontSize: 17, fontWeight: 400, color: D.muted }}>Hide</span>
      </div>
      <div style={{ position: "relative", height: 46, borderBottom: `1px solid ${D.border}`, fontSize: 17, color: D.muted }}>
        <span style={{ position: "absolute", left: 24, top: 13 }}>Agent</span>
        {cols.map(([l, x]) => (
          <span key={l} style={{ position: "absolute", right: CW - x, top: 13 }}>{l}</span>
        ))}
      </div>
      {rows.map((r, i) => (
        <div key={i} style={{ position: "relative", height: 54, borderBottom: i < rows.length - 1 ? `1px solid #eef1f5` : undefined, fontSize: 20 }}>
          <span style={{ position: "absolute", left: 24, top: 14 }}>{r[0]}</span>
          {[r[1], r[2], r[3], r[4], r[5]].map((v, k) => (
            <span
              key={k}
              style={{
                position: "absolute",
                right: CW - cols[k][1],
                top: 14,
                fontVariantNumeric: "tabular-nums",
                color: k === 2 && Number(v) > 0 ? D.red : k === 4 ? D.primary : D.fg,
                fontWeight: k === 2 && Number(v) > 0 ? 600 : 400,
              }}
            >
              {v}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
};

/* ------------------------------------------------------ settings sheet */

export const SHEET_W = 620;
const FIELDS: [string, string, number][] = [
  ["Due soon", "Amber, and listed in the digest.", 2],
  ["Overdue", "Red. Automatic reminder to the agent.", 3],
  ["Escalate", "Automatic escalation: tags the agent and the team lead.", 5],
  ["Requester slow", "Highlights tickets waiting on the requester.", 3],
  ["Unassigned", "Submitted with no agent for this long (business hours).", 4],
  ["Approval stuck", "Out for approval for this long.", 5],
];

export const SettingsSheet: React.FC<{ p: number; hlField?: number; hlP?: number }> = ({ p, hlField = -1, hlP = 0 }) => {
  if (p <= 0) return null;
  return (
    <>
      <div style={{ position: "absolute", inset: 0, background: `rgba(15,23,42,${0.4 * p})` }} />
      <div style={{ position: "absolute", top: 0, bottom: 0, right: 0, width: SHEET_W, background: "#fff", transform: `translateX(${(1 - p) * SHEET_W}px)`, boxShadow: "-20px 0 60px -30px rgba(0,0,0,.4)", padding: "34px 36px", boxSizing: "border-box" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 27, fontWeight: 600 }}>Attention settings</div>
          <Icon n="x" size={22} color={D.muted} />
        </div>
        <div style={{ fontSize: 18, color: D.muted, marginTop: 10, lineHeight: 1.45 }}>Business days skip weekends (US Central). The wait counts from the requester's last unanswered message.</div>
        {FIELDS.map(([l, h, v], i) => {
          const on = i === hlField;
          return (
            <div key={l} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 22, gap: 20 }}>
              <div>
                <div style={{ fontSize: 20, fontWeight: 600 }}>{l}</div>
                <div style={{ fontSize: 16, color: D.muted, marginTop: 3 }}>{h} (business days)</div>
              </div>
              <div style={{ width: 104, height: 50, flex: "none", borderRadius: 10, border: `2px solid ${on ? D.primary : D.border}`, boxShadow: on ? `0 0 0 ${5 * hlP}px rgba(13,128,242,.15)` : undefined, display: "flex", alignItems: "center", padding: "0 16px", boxSizing: "border-box", fontSize: 21 }}>{v}</div>
            </div>
          );
        })}
        <div style={{ position: "absolute", right: 36, bottom: 34 }}>
          <Btn kind="primary" label="Save" w={130} h={52} />
        </div>
      </div>
    </>
  );
};
export const sheetFieldsRect = () => worldRect(BW - SHEET_W, 90, SHEET_W, 560);
export const sheetRect = () => worldRect(BW - SHEET_W, 0, SHEET_W, 954);
