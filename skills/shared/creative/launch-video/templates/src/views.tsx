import React from "react";

import {
  AppHeader,
  BrowserFrame,
  D,
  EscalateDialog,
  LoadTable,
  PADX,
  PageTitle,
  ROW_H,
  Row,
  RowDef,
  RowFx,
  SearchBar,
  SectionHead,
  SettingsSheet,
  TileDef,
  Tiles,
  strip,
} from "./dash";
import { SANS } from "./theme";

const URL = "app.example.com/dashboard";

/* -------------------------------------------------------- requester */

export const REQ = { TILES_Y: 222, SEC_Y: 446, ROWS: [486, 632, 778] };

export const ACCESS: RowDef = {
  title: "Access request, Contoso rollout",
  meta: "#11240 · Request 1240 · Acme Corp · Contoso",
  accent: "red",
  chip: { text: "With Support", tone: "blue" },
  stateLabel: "Under review",
  wait: { text: "Waiting on Support for 4.2 bd", tone: "red" },
  person: "Dana Whitfield",
  strip: strip(["sub", 0.06], ["support", 0.94]),
  buttons: ["helpdesk", "escalate"],
};

const REQ_ROWS: RowDef[] = [
  ACCESS,
  {
    title: "Enterprise onboarding: SSO and seat limits",
    meta: "#11236 · Request 1236 · Acme Corp · Globex",
    accent: "amber",
    chip: { text: "With Support", tone: "blue" },
    stateLabel: "Under review",
    wait: { text: "Waiting on Support for 2.1 bd", tone: "amber" },
    person: "Priya Shah",
    strip: strip(["sub", 0.08], ["support", 0.4], ["await", 0.2], ["support", 0.32]),
    buttons: ["helpdesk", "escalate"],
  },
  {
    title: "Integration setup, EMEA partner",
    meta: "#11229 · Request 1229 · Acme Corp · Initech",
    accent: "none",
    chip: { text: "With Support", tone: "blue" },
    stateLabel: "Under review",
    wait: { text: "Support replied 3 hours ago", tone: "muted" },
    person: "Sam Ortiz",
    strip: strip(["sub", 0.05], ["support", 0.3], ["await", 0.25], ["support", 0.4]),
    stripW: 460,
    buttons: ["helpdesk", "escalate"],
  },
];

export const REQ_TILES: TileDef[] = [
  { label: "Needs your input", value: 1, hint: "Support is waiting on you", color: D.amber, icon: "pencil" },
  { label: "With Support", value: 3, hint: "An agent's move", color: D.primary, icon: "scale" },
  { label: "In approval", value: 1, hint: "Out for approval", color: D.purple, icon: "hourglass" },
  { label: "Completed", value: 6, hint: "Last 30 days", color: D.green, icon: "checkCircle" },
];

export const RequesterView: React.FC<{
  tileHl?: number | null;
  tileP?: number;
  row0?: RowFx;
  escalated?: boolean;
  dialog?: { p: number; chars: number; press: number };
}> = ({ tileHl = null, tileP = 0, row0 = {}, escalated = false, dialog }) => (
  <BrowserFrame url={URL}>
    <AppHeader initials="AC" avatar="#0ea5e9" />
    <PageTitle title="My tickets" sub="Where each of your tickets stands, whose move it is and for how long." />
    <Tiles y={REQ.TILES_Y} tiles={REQ_TILES} hl={tileHl} hlP={tileP} />
    <SearchBar y={372} />
    <SectionHead y={REQ.SEC_Y} title="With Support" count={3} />
    {REQ_ROWS.map((r, i) => (
      <Row key={i} y={REQ.ROWS[i]} r={i === 0 && escalated ? { ...r, buttons: ["helpdesk"] } : r} fx={i === 0 ? row0 : {}} />
    ))}
    {dialog && <EscalateDialog p={dialog.p} chars={dialog.chars} press={dialog.press} ticket="#11240 · Access request, Contoso rollout" agent="Dana Whitfield" wait="4.2 bd" />}
  </BrowserFrame>
);

/* --------------------------------------------------------- agent */

export const AGT = { TILES_Y: 222, SEC1: 446, ROW0: 486, ROW0_H: 176, SEC2: 690, ROWS: [730, 876] };

export const AGT_ESC_ROW: RowDef = {
  ...ACCESS,
  chip: { text: "Support's move", tone: "blue" },
  wait: { text: "Requester waiting 4.2 bd for a reply", tone: "red", bold: true },
  person: "Dana Whitfield · routed by Morgan Lee",
  buttons: ["helpdesk", "clear"],
};

const AGT_ROWS: RowDef[] = [
  {
    title: "Billing question, mobile app",
    meta: "#11231 · Request 1231 · Acme Corp · Hooli",
    accent: "red",
    chip: { text: "Support's move", tone: "blue" },
    stateLabel: "Under review",
    wait: { text: "Requester waiting 3.4 bd for a reply", tone: "red" },
    person: "Dana Whitfield · routed by Morgan Lee",
    strip: strip(["sub", 0.1], ["support", 0.9]),
    buttons: ["helpdesk"],
  },
  {
    title: "Feature request, Austin office",
    meta: "#11244 · Request 1244 · Acme Corp · Greenway",
    accent: "amber",
    chip: { text: "Support's move", tone: "blue" },
    stateLabel: "Under review",
    wait: { text: "Requester waiting 2.1 bd for a reply", tone: "amber" },
    person: "Dana Whitfield · routed by Morgan Lee",
    strip: strip(["sub", 0.1], ["support", 0.35], ["await", 0.2], ["support", 0.35]),
    buttons: ["helpdesk"],
  },
];

export const attTiles = (escalated: number): TileDef[] => [
  { label: "Escalated", value: escalated, hint: "A requester escalated it", color: D.red, icon: "flame" },
  { label: "Your move", value: 4, hint: "Waiting on you", color: D.primary, icon: "scale" },
  { label: "Overdue", value: 2, hint: "Past the reply threshold", color: D.red, icon: "alert" },
  { label: "Waiting on requester", value: 1, hint: "You asked; they owe a reply", color: D.amber, icon: "clock" },
  { label: "In approval", value: 2, hint: "Out for approval", color: D.purple, icon: "hourglass" },
];

export const AgentView: React.FC<{ escalated: number; tileHl?: number | null; tileP?: number; row0: RowFx; merge?: number }> = ({ escalated, tileHl = null, tileP = 0, row0, merge = 0 }) => (
  <BrowserFrame url={URL}>
    <AppHeader initials="DW" avatar="#7c5cc4" />
    <PageTitle title="My queue" sub="Your tickets, most urgent first. Escalations stay pinned until the support side clears them." />
    <Tiles y={AGT.TILES_Y} tiles={attTiles(escalated)} hl={tileHl} hlP={tileP} />
    <SearchBar y={372} />
    {/* after Clear, the ticket drops out of "Escalated" into "Your move" */}
    <SectionHead y={AGT.SEC1} title="Escalated" count={1} opacity={1 - merge} />
    <SectionHead y={AGT.SEC2 - merge * (AGT.SEC2 - AGT.SEC1)} title="Your move" count={merge > 0.5 ? 5 : 4} />
    <Row y={AGT.ROW0} h={AGT.ROW0_H} r={escalated ? AGT_ESC_ROW : { ...AGT_ESC_ROW, buttons: ["helpdesk"] }} fx={row0} />
    {AGT_ROWS.map((r, i) => (
      <Row key={i} y={AGT.ROWS[i] - merge * 54} r={r} />
    ))}
  </BrowserFrame>
);

/* ------------------------------------------------------------- team */

export const TEAM = { TABS_Y: 222, TILES_Y: 292, TABLE_Y: 446, TABLE_H: 70 + 46 + 4 * 54, SEC: 800, ROW: 840 };

export const TEAM_TILES: TileDef[] = [
  { label: "Overdue", value: 6, hint: "Requester waiting past threshold", color: D.red, icon: "alert" },
  { label: "Escalated", value: 1, hint: "Flagged until Support clears it", color: D.red, icon: "flame" },
  { label: "Unassigned", value: 2, hint: "No agent yet", color: D.fg, icon: "userX" },
  { label: "In approval", value: 3, hint: "Out for approval", color: D.purple, icon: "hourglass" },
  { label: "All open", value: 41, hint: "Every open ticket", color: D.fg, icon: "inbox", selected: true },
];

export const TeamView: React.FC<{ tileHl?: number | null; tileP?: number; tableHl?: number; settingsPress?: number; sheet?: number; fieldHl?: number; fieldP?: number }> = ({
  tileHl = null,
  tileP = 0,
  tableHl = 0,
  settingsPress = 0,
  sheet = 0,
  fieldHl = -1,
  fieldP = 0,
}) => (
  <BrowserFrame url={URL}>
    <AppHeader initials="ML" avatar="#16a34a" />
    <PageTitle title="Team dashboard" sub="Every open ticket, who it is waiting on, and for how long." settings settingsPress={settingsPress} />
    <div style={{ position: "absolute", left: PADX, top: TEAM.TABS_Y, height: 52, borderRadius: 12, background: "#e8edf3", display: "flex", alignItems: "center", padding: 5, gap: 4, boxSizing: "border-box", fontFamily: SANS, fontSize: 19 }}>
      <span style={{ background: "#fff", borderRadius: 9, padding: "8px 18px", fontWeight: 500 }}>Team</span>
      <span style={{ padding: "8px 18px", color: D.muted }}>My tickets</span>
    </div>
    <Tiles y={TEAM.TILES_Y} tiles={TEAM_TILES} hl={tileHl} hlP={tileP} />
    <LoadTable
      y={TEAM.TABLE_Y}
      hl={tableHl}
      rows={[
        ["Dana Whitfield", 14, 9, 3, 1, "4.2 bd"],
        ["Priya Shah", 11, 6, 2, 0, "3.6 bd"],
        ["Sam Ortiz", 9, 4, 1, 0, "3.1 bd"],
        ["Rachel Kim", 7, 3, 0, 0, "1.8 bd"],
      ]}
    />
    <SectionHead y={TEAM.SEC} title="Escalated" count={1} />
    <Row y={TEAM.ROW} r={{ ...AGT_ESC_ROW, buttons: ["helpdesk", "clear"] }} fx={{ tint: 1, badge: { text: "Escalated", tone: "red", p: 1 } }} />
    <SettingsSheet p={sheet} hlField={fieldHl} hlP={fieldP} />
  </BrowserFrame>
);

export { ROW_H };
