import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import {
  Camera,
  Caret,
  Check,
  ClaudeMark,
  Clawd,
  Cursor,
  GoogleG,
  McpKnot,
  Pill,
  ScaleIcon,
  Window,
  Words,
  Wrench,
  HelpDeskLogo,
} from "./kit";
import { AccentBar, Paper, RunningHead } from "./apps";
import { Sfx, Typing } from "./scenes-new";
import { OPENAI_PATH } from "./openai-path";

const OpenAIMark: React.FC<{ size?: number }> = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={C.ink}>
    <path d={OPENAI_PATH} />
  </svg>
);
import { C, MONO, SANS, SERIF, pop, prog, rise, typed } from "./theme";

/* =====================================================================
   SCENE 4 — just ask: a Claude chat using the Product tools
   ===================================================================== */

const ToolChip: React.FC<{ name: string; start: number; done: number }> = ({ name, start, done }) => {
  const f = useCurrentFrame();
  const isDone = f >= done;
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 12, padding: "10px 18px", borderRadius: 14, border: `1px solid ${C.border}`, background: "#f6f7f9", fontFamily: MONO, fontSize: 21, color: C.muted, ...rise(f, start, 12, 12) }}>
      <Wrench size={20} color={C.muted} />
      support-intake · {name}
      {isDone ? (
        <span style={{ display: "inline-flex", width: 26, height: 26, borderRadius: 99, background: "rgba(47,191,120,.15)", alignItems: "center", justifyContent: "center" }}>
          <Check size={18} color={C.success} draw={prog(f, done, 10)} />
        </span>
      ) : (
        <span style={{ display: "inline-flex", gap: 5 }}>
          {[0, 1, 2].map((k) => (
            <span key={k} style={{ width: 7, height: 7, borderRadius: 9, background: C.muted, opacity: 0.25 + 0.75 * ((Math.sin((f - k * 4) / 3) + 1) / 2) }} />
          ))}
        </span>
      )}
    </div>
  );
};

const TicketCard: React.FC<{ n: string; title: string; start: number }> = ({ n, title, start }) => {
  const f = useCurrentFrame();
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 22px", border: `1px solid ${C.border}`, borderRadius: 16, background: "#fff", width: 760, ...rise(f, start, 14, 18) }}>
      <span style={{ fontSize: 24 }}>
        <span style={{ fontFamily: MONO, color: C.muted }}>#{n}</span> <span style={{ fontWeight: 600 }}>{title}</span>
      </span>
      <Pill color="#b58300" bg="rgba(232,178,31,.16)" style={{ fontSize: 17 }}>
        Waiting on you
      </Pill>
    </div>
  );
};

export const SceneChat: React.FC = () => {
  const f = useCurrentFrame();
  const q1 = "Which of my tickets are waiting on me?";
  const q2 = "Reply on the Acme NDA: approved, please send it for signature.";
  const q1Sent = f >= 62;
  const q2Start = 140;
  const q2Sent = f >= 196;
  const composer = !q1Sent ? typed(q1, f, 18, 1.1) : f < q2Start ? "" : !q2Sent ? typed(q2, f, q2Start, 0.85) : "";

  const bubble = (text: string, start: number, top: number) => (
    <div style={{ position: "absolute", right: 48, top, ...rise(f, start, 12, 14) }}>
      <div style={{ maxWidth: 820, padding: "18px 24px", borderRadius: 22, borderBottomRightRadius: 6, background: "#ebe8df", fontSize: 25, color: C.fg }}>{text}</div>
    </div>
  );

  return (
    <AbsoluteFill>
      <Paper />
      <RunningHead text="JUST ASK" color={C.claudeInk} />
      <div style={{ position: "absolute", top: 40, left: 0, right: 0, textAlign: "center", ...rise(f, 4, 16, 16) }}>
        <span style={{ fontFamily: SERIF, fontSize: 54, fontWeight: 700, color: C.ink, letterSpacing: -0.8 }}>Just ask. </span>
        <span style={{ fontFamily: SERIF, fontSize: 54, fontWeight: 700, color: C.claudeInk, letterSpacing: -0.8 }}>Your agent does the clicking.</span>
      </div>
      <Camera
        keys={[
          { f: 0, x: 960, y: 540, z: 1 },
          { f: 290, x: 960, y: 540, z: 1 },
        ]}
      >
        <div style={{ ...rise(f, 0, 18, 70) }}>
          <Window
            x={330}
            y={150}
            w={1260}
            h={900}
            bg={C.claudeBg}
            title={
              <span style={{ display: "inline-flex", alignItems: "center", gap: 10, color: C.fg }}>
                <ClaudeMark size={22} /> Claude
              </span>
            }
          >
            {q1Sent && bubble(q1, 62, 34)}
            {f >= 72 && (
              <div style={{ position: "absolute", left: 48, top: 130 }}>
                <ToolChip name="list_tickets" start={72} done={100} />
              </div>
            )}
            {f >= 104 && (
              <div style={{ position: "absolute", left: 48, top: 204, display: "grid", gap: 14, fontFamily: SANS }}>
                <div style={{ fontSize: 26, ...rise(f, 104, 12, 10) }}>Two tickets need your reply:</div>
                <TicketCard n="36029" title="Acme mutual NDA" start={112} />
                <TicketCard n="36041" title="Contoso vendor MSA" start={120} />
              </div>
            )}
            {q2Sent && bubble(q2, 196, 452)}
            {f >= 206 && (
              <div style={{ position: "absolute", left: 48, top: 548 }}>
                <ToolChip name="add_comment" start={206} done={228} />
              </div>
            )}
            {f >= 232 && (
              <div style={{ position: "absolute", left: 48, top: 622, display: "flex", alignItems: "center", gap: 14, fontFamily: SANS, fontSize: 26, ...rise(f, 232, 12, 10) }}>
                Done. Posted your reply on <b>#36029</b>, as you.
                <Pill color={C.magic} bg={C.magicSoft} style={{ fontSize: 18 }}>
                  <HelpDeskLogo size={22} /> in the help desk
                </Pill>
              </div>
            )}

            {/* composer */}
            <div style={{ position: "absolute", left: 40, right: 40, bottom: 34, height: 118, borderRadius: 24, background: "#fff", border: `1px solid ${C.border}`, boxShadow: "0 8px 24px -16px rgba(0,0,0,.3)", padding: "20px 26px", fontFamily: SANS }}>
              <div style={{ fontSize: 25, color: composer ? C.fg : "#9aa5b1", height: 34 }}>
                {composer || "Reply to Claude…"}
                {composer && <Caret color={C.claude} />}
              </div>
              <div style={{ position: "absolute", left: 26, bottom: 16 }}>
                <Pill color={C.success} bg="rgba(47,191,120,.12)" style={{ fontSize: 16, padding: "4px 12px" }}>
                  <span style={{ width: 8, height: 8, borderRadius: 9, background: C.success }} /> Product
                </Pill>
              </div>
              <div style={{ position: "absolute", right: 18, bottom: 14, width: 46, height: 46, borderRadius: 14, background: C.claude, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26, fontWeight: 700 }}>↑</div>
            </div>
          </Window>
        </div>
      </Camera>
      <Typing from={18} to={60} every={2} v={0.18} />
      <Sfx at={61} name="click" v={0.4} />
      <Sfx at={100} name="pop" v={0.3} />
      <Typing from={140} to={194} every={2} v={0.18} />
      <Sfx at={195} name="click" v={0.4} />
      <Sfx at={228} name="pop" v={0.3} />
    </AbsoluteFill>
  );
};

/* =====================================================================
   SCENE 5 — the landing card with the typing agent names
   ===================================================================== */

/** Type, hold, backspace through `words`; the last one stays. */
function typewriter(words: string[], f: number, start: number) {
  const TYPE = 2.5;
  const DEL = 1.5;
  const HOLD = 8;
  const GAP = 4;
  let t = start;
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    const typeEnd = t + w.length * TYPE;
    if (f < typeEnd) return w.slice(0, Math.max(0, Math.floor((f - t) / TYPE)));
    if (i === words.length - 1) return w;
    const holdEnd = typeEnd + HOLD;
    if (f < holdEnd) return w;
    const delEnd = holdEnd + w.length * DEL;
    if (f < delEnd) return w.slice(0, w.length - Math.floor((f - holdEnd) / DEL));
    t = delEnd + GAP;
  }
  return words[words.length - 1];
}

export const SceneCard: React.FC = () => {
  const f = useCurrentFrame();
  const word = typewriter(["Claude", "ChatGPT", "any agent"], f, 24);
  return (
    <AbsoluteFill>
      <Paper />
      <RunningHead text="ANY AGENT" />
      <Camera
        keys={[
          { f: 0, x: 960, y: 560, z: 0.92 },
          { f: 26, x: 960, y: 560, z: 0.92 },
          { f: 52, x: 700, y: 470, z: 1.42 },
          { f: 190, x: 720, y: 470, z: 1.46 },
          { f: 222, x: 960, y: 560, z: 1 },
        ]}
      >
        <div style={{ position: "absolute", left: 160, top: 240, width: 1600, height: 620, borderRadius: 60, background: "#fff", border: `1.5px solid ${C.hair}`, boxShadow: "0 40px 90px -60px rgba(40,35,25,.55)", overflow: "hidden", fontFamily: SANS, ...rise(f, 0, 20, 40) }}>
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(135deg, rgba(217,119,87,.07), transparent 45%, rgba(13,128,242,.10))" }} />
          <div style={{ position: "absolute", left: 90, top: 96, width: 860 }}>
            <Pill style={{ fontSize: 22 }}>
              <McpKnot size={20} color={C.primary} width={16} /> New · API &amp; MCP
            </Pill>
            <div style={{ marginTop: 40, fontSize: 64, fontWeight: 700, letterSpacing: -1.5, color: C.fg, lineHeight: 1.15, height: 160 }}>
              Use Product from
              <br />
              <span style={{ color: C.primary, whiteSpace: "nowrap" }}>{word}<Caret /></span>
            </div>
            <div style={{ marginTop: 6, fontSize: 28, color: C.muted, lineHeight: 1.5 }}>
              Connect Claude or any MCP client and just ask: start a request, check what&apos;s waiting on you, reply on a ticket.
            </div>
            <div style={{ marginTop: 30, display: "flex", gap: 14 }}>
              <Pill color={C.muted} bg="#f2f5f8" style={{ fontSize: 19, border: `1px solid ${C.border}` }}>
                <McpKnot size={18} color={C.muted} width={16} /> MCP
              </Pill>
              <Pill color={C.muted} bg="#f2f5f8" style={{ fontSize: 19, border: `1px solid ${C.border}`, fontFamily: MONO }}>
                {"{ }"} REST API
              </Pill>
            </div>
            <div style={{ marginTop: 36, fontSize: 28, fontWeight: 600, color: C.primary }}>Set it up →</div>
          </div>
          {/* mini chat on the right */}
          <div style={{ position: "absolute", right: 90, top: 110, width: 520, borderRadius: 26, border: `1px solid ${C.border}`, background: "rgba(255,255,255,.9)", boxShadow: "0 30px 60px -30px rgba(0,0,0,.35)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 22px", borderBottom: `1px solid ${C.border}`, fontSize: 21, fontWeight: 600 }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                <ClaudeMark size={20} /> Claude
              </span>
              <Pill color={C.success} bg="rgba(47,191,120,.12)" style={{ fontSize: 15 }}>● Product</Pill>
            </div>
            <div style={{ padding: 22, display: "grid", gap: 14, fontSize: 19 }}>
              <div style={{ justifySelf: "end", background: C.primary, color: "#fff", padding: "10px 16px", borderRadius: 16 }}>Which of my tickets are waiting on me?</div>
              <div style={{ justifySelf: "start", fontFamily: MONO, fontSize: 16, color: C.muted, border: `1px solid ${C.border}`, borderRadius: 10, padding: "6px 12px" }}>support-intake · list_tickets</div>
              {["#36029 Acme mutual NDA", "#36041 Contoso vendor MSA"].map((t) => (
                <div key={t} style={{ display: "flex", justifyContent: "space-between", border: `1px solid ${C.border}`, borderRadius: 12, padding: "10px 14px", fontSize: 17 }}>
                  {t}
                  <span style={{ color: "#b58300", fontSize: 14, background: "rgba(232,178,31,.16)", borderRadius: 99, padding: "2px 10px" }}>Waiting on you</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Camera>
      <div style={{ position: "absolute", bottom: 60, left: 0, right: 0, textAlign: "center", fontFamily: SERIF, fontSize: 46, fontWeight: 600, color: C.ink, ...rise(f, 200, 16, 16) }}>
        Live on the Product home page.
      </div>
      <Sfx at={26} name="whoosh" v={0.2} />
      <Typing from={24} to={39} every={2.5} v={0.15} />
      <Typing from={60} to={78} every={2.5} v={0.15} />
      <Typing from={100} to={122} every={2.5} v={0.15} />
      <Sfx at={190} name="whoosh" v={0.18} />
    </AbsoluteFill>
  );
};

/* =====================================================================
   SCENE 6 — connect it in Claude: Customize → Connectors → + → URL → sign in
   ===================================================================== */

const MCP_URL = "https://app.example.com/api/mcp/mcp";

const StepChip: React.FC = () => {
  const f = useCurrentFrame();
  const steps = [
    { s: 0, n: "1", t: "Open Connectors" },
    { s: 140, n: "2", t: "Paste the server URL" },
    { s: 292, n: "3", t: "Sign in & approve" },
    { s: 400, n: "✓", t: "Connected. That's it." },
  ];
  const cur = [...steps].reverse().find((s) => f >= s.s)!;
  const p = prog(f, cur.s, 14);
  return (
    <div style={{ position: "absolute", bottom: 34, left: "50%", transform: `translateX(-50%) translateY(${(1 - p) * 14}px)`, opacity: p, zIndex: 80, display: "flex", alignItems: "center", gap: 22, padding: "16px 34px 16px 26px", background: "#fbfaf7", border: `1.5px solid ${C.hair}`, color: C.ink, boxShadow: "0 18px 40px -26px rgba(40,35,25,.5)" }}>
      <span style={{ fontFamily: SERIF, fontSize: 40, fontWeight: 700, color: cur.n === "✓" ? C.success : C.claudeInk, minWidth: 28, textAlign: "center" }}>{cur.n}</span>
      <span style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <AccentBar color={cur.n === "✓" ? C.success : C.claudeInk} w={34} />
        <span style={{ fontFamily: SERIF, fontSize: 34, fontWeight: 600 }}>{cur.t}</span>
      </span>
    </div>
  );
};

const SideItem: React.FC<{ y: number; label: string; active?: boolean; icon?: string }> = ({ y, label, active, icon = "○" }) => (
  <div style={{ position: "absolute", left: 22, top: y - 24, width: 256, height: 48, borderRadius: 12, display: "flex", alignItems: "center", gap: 14, padding: "0 16px", fontSize: 22, background: active ? "#e6e2d6" : "transparent", color: C.fg, fontWeight: active ? 600 : 500 }}>
    <span style={{ color: C.muted, width: 22, textAlign: "center" }}>{icon}</span>
    {label}
  </div>
);

const ConnectorRow: React.FC<{ y: number; name: string; icon: React.ReactNode; right: React.ReactNode; style?: React.CSSProperties }> = ({ y, name, icon, right, style }) => (
  <div style={{ position: "absolute", left: 620, top: y, width: 1120, height: 76, display: "flex", alignItems: "center", gap: 20, padding: "0 24px", borderRadius: 16, border: `1px solid ${C.border}`, background: "#fff", fontSize: 24, fontWeight: 600, ...style }}>
    {icon}
    <span style={{ flex: 1 }}>{name}</span>
    {right}
  </div>
);

const sq = (bg: string, ch: string) => (
  <span style={{ width: 42, height: 42, borderRadius: 10, background: bg, color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 20 }}>{ch}</span>
);

const Field: React.FC<{ label: string; value: string; focus?: boolean; mono?: boolean }> = ({ label, value, focus, mono }) => (
  <div style={{ marginTop: 22 }}>
    <div style={{ fontSize: 19, fontWeight: 600, color: C.muted, marginBottom: 8 }}>{label}</div>
    <div style={{ height: 56, borderRadius: 12, border: `2px solid ${focus ? C.claude : C.border}`, display: "flex", alignItems: "center", padding: "0 16px", fontSize: mono ? 19 : 22, fontFamily: mono ? MONO : SANS, color: C.fg, whiteSpace: "nowrap", overflow: "hidden" }}>
      {value}
      {focus && <Caret color={C.claude} h={0.9} />}
    </div>
  </div>
);

export const SceneSetup: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();

  const page = f < 52 ? "home" : "connectors";
  const listIn = prog(f, 60, 14);
  const dropdown = f >= 116 && f < 140;
  const modalP = spring({ frame: f - 140, fps, config: { damping: 18 } }) * (f < 278 ? 1 : 1 - prog(f, 278, 10));
  const name = typed("Product", f, 160, 2.2);
  const url = typed(MCP_URL, f, 196, 1.15);
  const newRow = f >= 284;
  const popupP = f >= 312 && f < 396 ? spring({ frame: f - 312, fps, config: { damping: 16 } }) * (1 - prog(f, 388, 8)) : 0;
  const consent = f >= 352;
  const connected = f >= 398;

  const rowsY = [330, 414, 498];
  const shift = newRow ? prog(f, 284, 14) * 84 : 0;

  return (
    <AbsoluteFill>
      <Paper />
      <Camera
        keys={[
          { f: 0, x: 960, y: 540, z: 1 },
          { f: 24, x: 960, y: 540, z: 1 },
          { f: 46, x: 520, y: 420, z: 1.45 },
          { f: 92, x: 600, y: 400, z: 1.3 },
          { f: 112, x: 1250, y: 380, z: 1.45 },
          { f: 138, x: 1250, y: 380, z: 1.45 },
          { f: 156, x: 960, y: 560, z: 1.55 },
          { f: 270, x: 960, y: 560, z: 1.55 },
          { f: 292, x: 1180, y: 420, z: 1.3 },
          { f: 314, x: 960, y: 560, z: 1.12 },
          { f: 392, x: 960, y: 560, z: 1.12 },
          { f: 410, x: 1180, y: 380, z: 1.45 },
          { f: 470, x: 1180, y: 380, z: 1.45 },
          { f: 500, x: 960, y: 540, z: 1 },
        ]}
      >
        <Window
          x={60}
          y={60}
          w={1800}
          h={960}
          bg={C.claudeBg}
          title={
            <span style={{ display: "inline-flex", alignItems: "center", gap: 10, color: C.fg }}>
              <ClaudeMark size={20} /> claude.ai
            </span>
          }
          style={{ ...rise(f, 0, 16, 40) }}
        >
          {/* sidebar (content coords: window content origin = (60,108)) */}
          <div style={{ position: "absolute", left: 0, top: 0, width: 300, bottom: 0, background: "#efece3", borderRight: `1px solid ${C.border}`, fontFamily: SANS }}>
            <div style={{ position: "absolute", left: 30, top: 26, display: "flex", alignItems: "center", gap: 12, fontSize: 28, fontWeight: 700 }}>
              <ClaudeMark size={30} /> Claude
            </div>
            <SideItem y={142} label="New chat" icon="+" />
            <SideItem y={196} label="Chats" icon="☰" />
            <SideItem y={250} label="Projects" icon="▢" />
            <SideItem y={304} label="Artifacts" icon="◇" />
            <SideItem y={358} label="Customize" icon="⚙" active={f >= 40} />
          </div>

          {/* main */}
          <div style={{ position: "absolute", left: 300, top: 0, right: 0, bottom: 0, fontFamily: SANS }}>
            {page === "home" ? (
              <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 30 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 18, fontSize: 52, fontFamily: "Georgia, serif", color: C.fg }}>
                  <ClaudeMark size={48} /> Good evening, investor
                </div>
                <div style={{ width: 860, height: 130, borderRadius: 26, background: "#fff", border: `1px solid ${C.border}`, padding: 24, fontSize: 24, color: "#9aa5b1" }}>How can I help you today?</div>
              </div>
            ) : (
              <>
                <div style={{ position: "absolute", left: 60, top: 40, fontSize: 40, fontWeight: 700 }}>Customize</div>
                {[
                  ["Profile", 132],
                  ["Connectors", 186],
                  ["Skills", 240],
                  ["Styles", 294],
                ].map(([l, y]) => (
                  <div key={l as string} style={{ position: "absolute", left: 50, top: (y as number) - 22, width: 220, height: 44, borderRadius: 10, display: "flex", alignItems: "center", padding: "0 14px", fontSize: 22, fontWeight: l === "Connectors" && f >= 82 ? 700 : 500, background: l === "Connectors" && f >= 82 ? "#e6e2d6" : "transparent" }}>
                    {l}
                  </div>
                ))}
                {f >= 82 && (
                  <div style={{ opacity: listIn }}>
                    <div style={{ position: "absolute", left: 260, top: 112, fontSize: 32, fontWeight: 700 }}>Connectors</div>
                    <div style={{ position: "absolute", left: 1328, top: 104, width: 52, height: 52, borderRadius: 14, border: `1px solid ${C.border}`, background: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 34, fontWeight: 400 }}>+</div>
                  </div>
                )}
              </>
            )}
          </div>
        </Window>

        {/* connector rows live in global coords */}
        {f >= 82 && (
          <div style={{ opacity: listIn, fontFamily: SANS, color: C.fg }}>
            {newRow && (
              <ConnectorRow
                y={rowsY[0]}
                name="Product"
                icon={<span style={{ width: 42, height: 42, borderRadius: 10, background: C.primarySoft, display: "inline-flex", alignItems: "center", justifyContent: "center" }}><ScaleIcon size={26} color={C.primary} /></span>}
                style={{ opacity: prog(f, 290, 12), boxShadow: connected ? `0 0 0 3px ${C.success}55` : `0 0 0 3px ${C.claude}44` }}
                right={
                  connected ? (
                    <Pill color={C.success} bg="rgba(47,191,120,.14)" style={{ fontSize: 20, ...pop(f, 398, 12) }}>
                      <Check size={20} color={C.success} draw={prog(f, 400, 10)} /> Connected
                    </Pill>
                  ) : (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 14 }}>
                      <span style={{ fontSize: 15, fontWeight: 700, color: C.muted, border: `1px solid ${C.border}`, borderRadius: 8, padding: "3px 10px" }}>CUSTOM</span>
                      <span style={{ padding: "10px 22px", borderRadius: 12, background: C.fg, color: "#fff", fontSize: 20 }}>Connect</span>
                    </span>
                  )
                }
              />
            )}
            <ConnectorRow y={rowsY[0] + shift} name="Google Drive" icon={sq("#1fa463", "D")} right={<span style={{ color: C.muted, fontSize: 20, fontWeight: 500 }}>Connected</span>} />
            <ConnectorRow y={rowsY[1] + shift} name="Gmail" icon={sq("#ea4335", "M")} right={<span style={{ color: C.muted, fontSize: 20, fontWeight: 500 }}>Connected</span>} />
            <ConnectorRow y={rowsY[2] + shift} name="GitHub" icon={sq("#24292f", "G")} right={<span style={{ color: C.muted, fontSize: 20, fontWeight: 500 }}>Connect</span>} />
          </div>
        )}

        {dropdown && (
          <div style={{ position: "absolute", left: 1440, top: 268, width: 300, borderRadius: 16, background: "#fff", border: `1px solid ${C.border}`, boxShadow: "0 24px 50px -20px rgba(0,0,0,.35)", padding: 8, fontSize: 21, fontFamily: SANS, color: C.fg, zIndex: 20, ...pop(f, 116, 8) }}>
            <div style={{ padding: "12px 14px" }}>Browse connectors</div>
            <div style={{ padding: "12px 14px", borderRadius: 10, background: f >= 128 ? "#f1eee6" : "transparent", fontWeight: 600 }}>Add custom connector</div>
          </div>
        )}

        {/* add-custom-connector modal */}
        {modalP > 0.01 && (
          <>
            <div style={{ position: "absolute", left: 60, top: 60, width: 1800, height: 960, borderRadius: 22, background: `rgba(10,12,18,${0.38 * modalP})` }} />
            <div style={{ position: "absolute", left: 580, top: 300, width: 760, height: 520, borderRadius: 26, background: "#fff", boxShadow: "0 40px 90px -30px rgba(0,0,0,.6)", padding: "34px 40px", fontFamily: SANS, color: C.fg, opacity: modalP, transform: `scale(${0.9 + 0.1 * modalP})` }}>
              <div style={{ fontSize: 32, fontWeight: 700 }}>Add custom connector</div>
              <div style={{ fontSize: 19, color: C.muted, marginTop: 6 }}>Connect Claude to a remote MCP server.</div>
              <Field label="Name" value={name} focus={f >= 156 && f < 192} />
              <Field label="Remote MCP server URL" value={url} focus={f >= 192 && f < 262} mono />
              <div style={{ marginTop: 20, fontSize: 18, color: C.muted }}>▸ Advanced settings</div>
              <div style={{ position: "absolute", right: 40, bottom: 34, display: "flex", gap: 14 }}>
                <span style={{ padding: "12px 26px", borderRadius: 12, border: `1px solid ${C.border}`, fontSize: 21 }}>Cancel</span>
                <span style={{ padding: "12px 34px", borderRadius: 12, background: C.fg, color: "#fff", fontSize: 21, fontWeight: 600, transform: f >= 266 && f < 272 ? "scale(.94)" : undefined }}>Add</span>
              </div>
            </div>
          </>
        )}

        {/* Product sign-in / consent popup */}
        {popupP > 0.01 && (
          <div style={{ position: "absolute", left: 600, top: 250, width: 720, height: 520, opacity: popupP, transform: `translateY(${(1 - popupP) * 50}px)` }}>
            <Window x={0} y={0} w={720} h={520} title="app.example.com">
              <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 34, fontFamily: SANS, color: C.fg }}>
                <Img src={staticFile("logo.png")} style={{ height: 64 }} />
                {!consent ? (
                  <>
                    <div style={{ marginTop: 30, fontSize: 34, fontWeight: 700 }}>Sign in to Product</div>
                    <div style={{ marginTop: 10, fontSize: 21, color: C.muted }}>Use your work account</div>
                    <div style={{ marginTop: 40, width: 440, height: 64, borderRadius: 14, border: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "center", gap: 14, fontSize: 23, fontWeight: 600, transform: f >= 340 && f < 346 ? "scale(.96)" : undefined }}>
                      <GoogleG size={26} /> Continue with Google
                    </div>
                  </>
                ) : (
                  <div style={{ ...rise(f, 352, 12, 12), display: "flex", flexDirection: "column", alignItems: "center" }}>
                    <div style={{ marginTop: 26, fontSize: 34, fontWeight: 700, display: "flex", alignItems: "center", gap: 12 }}>
                      Authorize <ClaudeMark size={30} /> Claude
                    </div>
                    <div style={{ marginTop: 10, fontSize: 21, color: C.muted }}>Claude will act as you in Product.</div>
                    <div style={{ marginTop: 26, display: "grid", gap: 10, fontSize: 21 }}>
                      {["Your requests and tickets", "Reply and share, like you can"].map((t) => (
                        <div key={t} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <Check size={20} color={C.success} /> {t}
                        </div>
                      ))}
                    </div>
                    <div style={{ marginTop: 34, display: "flex", gap: 18 }}>
                      <span style={{ padding: "14px 34px", borderRadius: 12, border: `1px solid ${C.border}`, fontSize: 22 }}>Deny</span>
                      <span style={{ padding: "14px 40px", borderRadius: 12, background: C.primary, color: "#fff", fontSize: 22, fontWeight: 700, transform: f >= 378 && f < 384 ? "scale(.94)" : undefined }}>Approve</span>
                    </div>
                  </div>
                )}
              </div>
            </Window>
          </div>
        )}

        {/* calm success ring on connect */}
        {connected &&
          [0, 1].map((k) => {
            const t = prog(f, 400 + k * 10, 34);
            if (t <= 0 || t >= 1) return null;
            return (
              <div key={k} style={{ position: "absolute", left: 620 - 8 * t * 6, top: rowsY[0] - 8 * t * 6, width: 1120 + 16 * t * 6, height: 76 + 16 * t * 6, borderRadius: 16 + t * 20, border: `2px solid ${C.success}`, opacity: (1 - t) * 0.7 }} />
            );
          })}

        <Cursor
          visibleFrom={14}
          keys={[
            { f: 14, x: 960, y: 760 },
            { f: 36, x: 190, y: 468 },
            { f: 46, x: 190, y: 468 },
            { f: 70, x: 470, y: 296 },
            { f: 86, x: 470, y: 296 },
            { f: 104, x: 1714, y: 238 },
            { f: 120, x: 1714, y: 238 },
            { f: 130, x: 1600, y: 352 },
            { f: 150, x: 1180, y: 640 },
            { f: 196, x: 1180, y: 640 },
            { f: 256, x: 1235, y: 752 },
            { f: 268, x: 1245, y: 764 },
            { f: 296, x: 1660, y: 368 },
            { f: 304, x: 1666, y: 370 },
            { f: 330, x: 970, y: 586 },
            { f: 342, x: 970, y: 586 },
            { f: 368, x: 1030, y: 656 },
            { f: 382, x: 1030, y: 656 },
            { f: 420, x: 1300, y: 520 },
          ]}
          clicks={[42, 84, 114, 132, 268, 304, 342, 380]}
        />
      </Camera>
      <StepChip />
      {[42, 84, 114, 132, 268, 304, 342, 380].map((c) => (
        <Sfx key={c} at={c} name="click" v={0.55} />
      ))}
      <Sfx at={140} name="whoosh" v={0.22} />
      <Typing from={160} to={186} every={2.2} v={0.2} />
      <Typing from={196} to={250} every={1.2} v={0.17} />
      <Sfx at={290} name="pop" v={0.3} />
      <Sfx at={312} name="whoosh" v={0.18} />
      <Sfx at={398} name="chime" v={0.42} />
    </AbsoluteFill>
  );
};

/* =====================================================================
   SCENE 7 — outro: try it now
   ===================================================================== */

export const SceneOutro: React.FC = () => {
  const f = useCurrentFrame();
  const fadeOut = prog(f, 256, 30);
  const p = (d: number) => rise(f, d, 18, 16);
  return (
    <AbsoluteFill>
      <Paper />
      <RunningHead text="TRY IT" opacity={1 - fadeOut} />
      <AbsoluteFill style={{ alignItems: "center", fontFamily: SANS, opacity: 1 - fadeOut }}>
        <div style={{ marginTop: 132, ...p(4) }}>
          <Clawd size={120} blink={f % 90 > 86} />
        </div>
        <div style={{ marginTop: 26, display: "flex", flexDirection: "column", alignItems: "center", gap: 14, ...p(10) }}>
          <AccentBar p={prog(f, 10, 16)} />
          <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: 6, color: C.primary }}>PRODUCT MCP</div>
        </div>
        <div style={{ marginTop: 14, fontFamily: SERIF, fontSize: 150, fontWeight: 700, letterSpacing: -5, color: C.ink, ...p(60) }}>Try it now.</div>
        <div style={{ ...p(92), marginTop: 8, fontSize: 38, color: C.ink2, fontWeight: 500 }}>
          Profile menu <span style={{ color: C.ink }}>→</span> <b style={{ color: C.ink }}>API &amp; MCP</b>
        </div>
        <div style={{ ...p(108), marginTop: 34, display: "flex", alignItems: "center", gap: 18, padding: "18px 30px", background: "#fbfaf7", border: `1.5px solid ${C.hair}` }}>
          <McpKnot size={34} color={C.ink} width={13} />
          <span style={{ fontFamily: MONO, fontSize: 32, color: C.ink }}>{MCP_URL}</span>
        </div>
        <div style={{ ...p(124), marginTop: 30, display: "flex", gap: 14 }}>
          {[
            [<ClaudeMark key="c" size={24} />, "Claude"],
            [<OpenAIMark key="o" size={22} />, "ChatGPT"],
            [<McpKnot key="m" size={22} color={C.ink} width={14} />, "Any MCP agent"],
          ].map(([icon, label]) => (
            <span key={label as string} style={{ display: "inline-flex", alignItems: "center", gap: 10, padding: "10px 22px", border: "1px solid rgba(30,33,36,.25)", borderRadius: 999, fontSize: 25, color: C.ink, background: "rgba(255,255,255,.5)" }}>
              {icon} {label}
            </span>
          ))}
        </div>
        <div style={{ position: "absolute", bottom: 54, ...p(140) }}>
          <Img src={staticFile("logo.png")} style={{ height: 78 }} />
        </div>
      </AbsoluteFill>
      <Sfx at={60} name="impact" v={0.32} />
    </AbsoluteFill>
  );
};

export { interpolate };
