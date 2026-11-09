import React from "react";

import { BrowserFrame, D, world, worldRect } from "./dash";
import { Icon, IconName } from "./icons";
import { Sh } from "./apps";
import { LogoMark } from "./kit";
import { SANS } from "./theme";

/* =====================================================================
   Help desk look-alike (content coords 1700 x 954).
   ===================================================================== */

const Z = {
  nav: "#2c3237",
  side: "#f3f4f6",
  line: "#e1e4e8",
  green: "#3aa86a",
  mention: "#2563eb",
};

const NAV_W = 78;
const OV_W = 330;
const SIDEBAR_W = 380;
const TK_X = NAV_W + OV_W; // 408
const TK_W = 1700 - TK_X - SIDEBAR_W; // 912

export type ZState = {
  noteP?: number; // bot note slide-in 0..1
  mentionHl?: number; // 0..1 pulse on mentions
  tagP?: number; // "escalated" tag pop
  ovBump?: number; // overview count 0 -> 1
  ovHl?: number;
  mailP?: number; // email toast
};

const Avatar: React.FC<{ t: string; bg: string; size?: number; icon?: IconName }> = ({ t, bg, size = 44, icon }) => (
  <div style={{ width: size, height: size, borderRadius: 99, background: bg, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.38, fontWeight: 700, flex: "none" }}>
    {icon ? <Icon n={icon} size={size * 0.55} color="#fff" /> : t}
  </div>
);

const Mention: React.FC<{ name: string; hl: number }> = ({ name, hl }) => (
  <span style={{ color: Z.mention, fontWeight: 600, background: `rgba(37,99,235,${0.08 + 0.16 * hl})`, borderRadius: 6, padding: "1px 6px", boxShadow: hl > 0 ? `0 0 0 ${3 * hl}px rgba(37,99,235,${0.18 * hl})` : undefined }}>@{name}</span>
);

const OVERVIEWS: [string, number | null][] = [
  ["My Assigned Tickets", 12],
  ["Unassigned & Open", 3],
  ["My Escalated Tickets", null],
  ["All Escalated Tickets", null],
  ["My Pending Reached", 0],
  ["Open Tickets", 41],
];

export const HelpDeskWindow: React.FC<{ s?: ZState }> = ({ s = {} }) => {
  const noteP = s.noteP ?? 0;
  const tagP = s.tagP ?? 0;
  const bump = s.ovBump ?? 0;
  return (
    <BrowserFrame url="help.example.com">
      <div style={{ position: "absolute", inset: 0, background: "#fff" }}>
        {/* nav */}
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: NAV_W, background: Z.nav }}>
          <LogoMark style={{ position: "absolute", left: 17, top: 18, width: 44, height: 38 }} />
          {(["dashboard", "list", "search", "plus"] as IconName[]).map((n, i) => (
            <div key={n} style={{ position: "absolute", left: 24, top: 96 + i * 60 }}>
              <Icon n={n} size={30} color={i === 1 ? "#e6e9ec" : "#7d8790"} />
            </div>
          ))}
          <div style={{ position: "absolute", left: 17, bottom: 22 }}>
            <Avatar t="DW" bg="#7c5cc4" size={44} />
          </div>
        </div>
        {/* overviews */}
        <div style={{ position: "absolute", left: NAV_W, top: 0, bottom: 0, width: OV_W, background: Z.side, borderRight: `1px solid ${Z.line}` }}>
          <div style={{ fontSize: 22, fontWeight: 700, padding: "26px 24px 14px" }}>Overviews</div>
          {OVERVIEWS.map(([l, n], i) => {
            const esc = i === 2 || i === 3;
            const v = esc ? Math.round(bump) : n;
            const hl = i === 2 ? s.ovHl ?? 0 : 0;
            return (
              <div key={l} style={{ position: "relative", margin: "0 10px", height: 54, borderRadius: 9, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 14px", fontSize: 19, background: i === 2 ? `rgba(220,38,38,${0.06 + 0.08 * hl})` : "transparent", color: esc ? D.fg : "#3c4752", fontWeight: esc ? 600 : 400 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  {esc && <Icon n="flame" size={18} color={D.red} />}
                  {l}
                </span>
                <span style={{ minWidth: 30, height: 28, borderRadius: 99, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, background: esc && v ? D.red : "#e1e5ea", color: esc && v ? "#fff" : "#5b6670", transform: esc ? `scale(${1 + 0.35 * Math.sin(Math.PI * Math.min(1, bump))})` : undefined, padding: "0 8px", boxSizing: "border-box" }}>{v}</span>
              </div>
            );
          })}
        </div>
        {/* ticket */}
        <div style={{ position: "absolute", left: TK_X, top: 0, width: TK_W, bottom: 0 }}>
          <div style={{ padding: "24px 32px 18px", borderBottom: `1px solid ${Z.line}` }}>
            <div style={{ fontSize: 16, color: "#6b7580" }}>#11240 · Acme Corp</div>
            <div style={{ fontSize: 28, fontWeight: 600, marginTop: 4 }}>Access request, Contoso rollout</div>
          </div>
          {/* earlier articles */}
          <Article y={120} who="Alex Carter" when="6 days ago" av={["AC", "#0ea5e9"]} lines={[560, 480, 300]} />
          <Article y={262} who="Alex Carter" when="4 days ago" av={["AC", "#0ea5e9"]} text="Following up: any update on this one?" />
          {/* the bot note */}
          <div
            style={{
              position: "absolute",
              left: 32,
              right: 32,
              top: 384,
              opacity: noteP,
              transform: `translateY(${(1 - noteP) * 60}px)`,
            }}
          >
            <div style={{ display: "flex", gap: 16, flexDirection: "row-reverse" }}>
              <Avatar t="" bg="#475569" icon="bot" />
              <div style={{ flex: 1, borderRadius: 14, border: "1.5px solid #c9dcf3", background: "#f5f9ff", padding: "18px 22px", fontSize: 20, lineHeight: 1.5 }}>
                <div style={{ fontSize: 16, color: "#6b7580", marginBottom: 8 }}>
                  <b style={{ color: D.fg }}>Support Agent</b> · just now · Escalation
                </div>
                <div style={{ fontWeight: 700 }}>Escalated by Alex Carter via the Product dashboard.</div>
                <div style={{ marginTop: 8 }}>
                  <Mention name="Dana Whitfield" hl={s.mentionHl ?? 0} />, <Mention name="Morgan Lee" hl={s.mentionHl ?? 0} />: please take a look. The requester has been waiting 4.2 business days for a reply from Support.
                </div>
                <div style={{ marginTop: 10, borderLeft: "4px solid #94a3b8", paddingLeft: 14, color: "#334155", fontStyle: "italic" }}>Customer goes live Friday. We need an answer by Thursday.</div>
                <div style={{ marginTop: 10, fontSize: 16, color: "#6b7580" }}>It stays marked as escalated until someone on the support side clears it.</div>
              </div>
            </div>
          </div>
          {/* reply box */}
          <div style={{ position: "absolute", left: 32, right: 32, bottom: 26, height: 84, borderRadius: 12, border: `1.5px solid ${Z.line}`, display: "flex", alignItems: "center", padding: "0 20px", color: "#9aa4ae", fontSize: 19 }}>Add a reply…</div>
        </div>
        {/* sidebar */}
        <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: SIDEBAR_W, background: "#fbfbfc", borderLeft: `1px solid ${Z.line}`, padding: "26px 28px", boxSizing: "border-box" }}>
          <div style={{ fontSize: 22, fontWeight: 700 }}>Ticket</div>
          {([
            ["State", "under review"],
            ["Owner", "Dana Whitfield"],
            ["Group", "Support"],
            ["Priority", "2 normal"],
          ] as const).map(([l, v]) => (
            <div key={l} style={{ marginTop: 18 }}>
              <div style={{ fontSize: 16, color: "#6b7580" }}>{l}</div>
              <div style={{ marginTop: 6, height: 46, borderRadius: 9, border: `1.5px solid ${Z.line}`, background: "#fff", display: "flex", alignItems: "center", padding: "0 14px", fontSize: 19 }}>{v}</div>
            </div>
          ))}
          <div style={{ marginTop: 22, fontSize: 16, color: "#6b7580" }}>Tags</div>
          <div style={{ marginTop: 8, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <TagChip t="access" />
            <TagChip t="onboarding" />
            {tagP > 0 && <TagChip t="escalated" red p={tagP} />}
          </div>
        </div>
      </div>
    </BrowserFrame>
  );
};

const TagChip: React.FC<{ t: string; red?: boolean; p?: number }> = ({ t, red, p = 1 }) => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "6px 13px", borderRadius: 8, fontSize: 17, fontWeight: red ? 700 : 500, background: red ? D.redChip : "#eceff3", color: red ? D.red : "#3c4752", border: red ? `1.5px solid ${D.redBd}` : "1.5px solid transparent", opacity: Math.min(1, p * 1.4), transform: `scale(${red ? 0.4 + 0.6 * p + 0.25 * Math.sin(Math.PI * p) : 1})` }}>
    <Icon n="tag" size={15} color={red ? D.red : "#6b7580"} />
    {t}
  </span>
);

const Article: React.FC<{ y: number; who: string; when: string; av: [string, string]; lines?: number[]; text?: string }> = ({ y, who, when, av, lines, text }) => (
  <div style={{ position: "absolute", left: 32, right: 32, top: y, display: "flex", gap: 16 }}>
    <Avatar t={av[0]} bg={av[1]} />
    <div style={{ position: "relative", flex: 1, borderRadius: 14, border: `1.5px solid ${Z.line}`, background: "#fff", padding: "14px 20px", minHeight: lines ? 104 : 70, boxSizing: "border-box" }}>
      <div style={{ fontSize: 16, color: "#6b7580" }}>
        <b style={{ color: D.fg }}>{who}</b> · {when}
      </div>
      {text && <div style={{ fontSize: 20, marginTop: 6 }}>{text}</div>}
      {lines?.map((w, i) => <Sh key={i} x={20} y={44 + i * 20} w={w} h={9} tone={i === 0 ? "dark" : "mid"} />)}
    </div>
  </div>
);

/* anchors */
export const Z_NOTE = worldRect(TK_X + 32, 384, TK_W - 64, 300);
export const Z_MENTIONS = worldRect(TK_X + 100, 440, 760, 90);
export const Z_TAGS = worldRect(1700 - SIDEBAR_W, 290, SIDEBAR_W, 230);
export const Z_OVERVIEW = worldRect(NAV_W, 70, OV_W, 340);
export const Z_OV_ESC = world(NAV_W + OV_W / 2, 66 + 54 * 2 + 27);

/* email toast, drawn in stage coords (on top of everything) */
export const MailToast: React.FC<{ p: number; x: number; y: number }> = ({ p, x, y }) => {
  if (p <= 0) return null;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: 680, borderRadius: 16, background: "#fff", border: "1.5px solid rgba(30,33,36,.82)", boxShadow: "0 30px 60px -24px rgba(0,0,0,.45)", padding: "20px 24px", display: "flex", gap: 18, opacity: p, transform: `translateX(${(1 - p) * 120}px)`, fontFamily: SANS }}>
      <div style={{ width: 54, height: 54, borderRadius: 14, background: "#fde3e3", display: "flex", alignItems: "center", justifyContent: "center", flex: "none" }}>
        <Icon n="mail" size={28} color={D.red} />
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 16, color: "#6b7580" }}>Product · now</div>
        <div style={{ fontSize: 22, fontWeight: 700, color: D.fg, marginTop: 2 }}>Escalated: Access request, Contoso rollout</div>
        <div style={{ fontSize: 18, color: "#475569", marginTop: 4 }}>To Dana Whitfield, Morgan Lee</div>
      </div>
    </div>
  );
};
