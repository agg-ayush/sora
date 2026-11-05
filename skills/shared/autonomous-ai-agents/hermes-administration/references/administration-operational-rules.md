# Host and runtime operational rules

Use the relevant rule below when administering Hermes; verify version-sensitive commands against current help/docs. Preserve live chats and do not print secrets.

## Always-on rules
- **Never modify installed Hermes source to change behavior or UI** (no
  patching `~/.hermes/hermes-agent`, no TUI `npm run build` of edited
  `.tsx`). Look for a native config key or slash command first; if none
  exists, say so plainly and ask before touching code. Before proposing a
  local patch for a real bug, check whether upstream `origin/main` (and open
  PRs) already fixed it. When the user approves a patch or hands one over:
  apply it on every host, run only the targeted tests (whole-dir runs trip
  the home-I/O guard), record files/functions/why in the setup repo's
  `docs/local-upstream-mods.md`, and set `hermes update --set-channel main` (check current help before use)
  so updates keep it. Installed-tree edits
  also leave the checkout on a non-main branch that blocks `hermes update`.
  If source was already changed, revert with `git restore` plus rebuild of
  the original bundle, return the checkout to clean `main`, and remove any
  temp branches/worktrees created for it.
  This rule bans shortcut patches for small behavior tweaks; it does not ban
  replacing a whole subsystem with a coherent alternative. When the user
  adopts a new architecture (e.g. an external memory store replacing
  built-in memory), build it on the native extension seam (out-of-tree
  plugin under `~/.hermes/plugins/`, e.g. a `MemoryProvider`), activate it
  via config, and script the install in the setup repo so every host gets
  it. Don't refuse the replacement by citing this rule.
  A `MemoryProvider` plugin can also hook tool calls: the memory-plugin
  loader forwards `register_hook` to the real PluginManager, so register
  `post_tool_call` from the provider itself, no companion general plugin.
  When the external system ships an official integration for another agent
  (e.g. Claude Code hooks), audit the Hermes adapter behavior by behavior
  against it (session-start injection, per-turn recall, action capture,
  commit linkage, session/actor identity, redaction, fail-open, tool
  surface), citing the reference source per row, close real gaps in code
  with e2e tests, and label each remaining gap as upstream-owned or our
  deliberate choice. "Wired in" without that table is an unverified claim.
- Display preference: hide thinking but keep tool activity visible with
  `/reasoning show` + `/details thinking hidden` (persist the matching
  `display` settings in `config.yaml` on every host). Minor footers such as
  the per-turn token total have no native toggle; leave them. Do not
  suggest `/reasoning hide` or a source patch to remove one; that fights
  the preference above. The tool-panel `Σ ~N total` row appears only when a
  turn reports both reasoning and tool tokens, so it shows up or vanishes
  with the model/provider, not with any config change.
- `/reasoning` has two groups: effort levels (`none|minimal|low|medium|
  high|xhigh|max|ultra`, session-scoped unless `--global`) and display
  toggles saved to config (`show`/`hide` = whole reasoning block;
  `full`/`clamp` = uncapped vs first 10 lines of the scrollback reasoning
  box, default clamp). Display toggles never change what the model does.
  Answer these from this list in one reply instead of re-grepping source.
- Busy input: `display.busy_input_mode` (`interrupt` default, `queue`,
  `steer`; `/busy <mode>` switches it) sets what plain Enter does mid-run.
  To queue one message while the default stays `steer`, type
  `/queue <message>`; `/queue list|rm N|edit N …|move A B` manage the
  pending queue mid-run. No hotkey queues; Shift+Enter inserts a newline.
- Answer TUI keybinding/input-behavior questions from
  `~/.hermes/hermes-agent/website/docs/user-guide/cli.md` (or the source),
  read before replying. Never offer an unverified hotkey; a guessed one that
  does something else costs a correction round.
- After ANY programmatic `config.yaml` write, grep the file on that host
  for masked or blanked secrets (`***`, `''` on `api_key`/`x-*` header
  lines). Some config readers return secrets redacted, and writing that
  dict back saves the mask over the real value. Every provider using it
  then fails (401 "missing caller key") and silently falls back. Prefer a
  targeted text edit of the one block being changed, keep secrets as
  `${VAR}` refs to `.env`, and back up first
  (`config.yaml.bak-<timestamp>-<label>`).
- Never print process command lines raw: `ps -o args`, `ps eww` and
  `/proc/<pid>/cmdline` can carry tokens a launcher typed inline (`export
  X=tfy_pat_...`). Pipe through `sed -E 's/(tfy_pat_|sk-|ghp_)[A-Za-z0-9_-]+/\1[REDACTED]/g'`,
  or compare fingerprints (sha256 prefix) against `.env` values instead.
  A tmux server's argv keeps the FIRST session's launch command for its
  whole life, so a token there survives that session ending; that PID is
  the server for every pane, so never kill it to clear the token.
- Before recommending a credential rotation, size the actual exposure:
  a token visible only to the same single login user that can already
  read `.env` (same fingerprint) is not a new leak. Rotation is warranted
  when it reached another principal (another account, a shared log, a
  transcript sent off-machine). State that reasoning, don't default to
  "rotate it".
- Test failover/breakage only on a throwaway copy on the local Mac
  (`HERMES_HOME=<scratch copy>` holding copied `config.yaml` + `.env`, with
  a `trap` that deletes it, since the copy holds keys). Break the route by
  pointing its URL at a `.invalid` host. Never break config, keys or the
  gateway on the remote host: it runs live workers and user chats. Recipe
  (per-tier breakage, hang guards, what to grep) in
  `references/model-routing-and-latency.md` "Verifying the main fallback
  chain".
- Remote-host sessions freeze their config at start: a later `config.yaml`
  secret or fallback change does not reach open chats, and a changed
  secret makes them refuse turns (`launch_credentials_unavailable`). Fix
  and recovery steps in `references/model-routing-and-latency.md`
  "Frozen session policy"; tell the user which open sessions keep the old
  chain instead of claiming the change is live everywhere.
- Revertible config experiments (new providers, aliases, routing trials):
  once the user says to try it, run the whole thing without asking at each
  step and report only when it works or is blocked. Track every key
  written so the end state has no leftover settings: revert them, or list
  each one as residual in the final report.
- Keep small UI/config asks small: one native-setting check, then answer.
  Long silent investigation on a cosmetic request reads as being stuck.
- The user's own tooling repo (the tier/orchestration setup repo, the
  claude-orchestrate plugin) is edited directly in the main session. The
  delegate-all-code rule covers product/target repos, not our own harness;
  handing a small plugin fix to a subagent draws a correction.
- Fixing a harness repo's test suite: capture the baseline failures on HEAD
  first; a test class for a deliberately deleted script is stale and gets
  deleted with its now-unused helpers; a test broken by a new guard (for
  example a phase gate) gets the precondition set up, never the guard
  weakened. Run with `python -m unittest discover -s tests -p 'test_*.py'`
  (the tests dir is not a package) on every host that holds a copy.
  Never pipe a test or gate run through `tail`/`head` before `&&` or a
  commit step: the pipe's exit code replaces the test's, so a failing run
  still lets the commit through. Redirect to a log file, check `$?`, then
  show the tail. When a script parses `hermes` CLI output that changes
  between releases (for example a flag only newer builds accept), give it
  a fallback path and test both paths, one on each host, before calling
  it fixed.
- Check Hermes optional features (STT/TTS engines, audio I/O, provider
  extras) against the Hermes venv interpreter
  (`~/.hermes/hermes-agent/venv/bin/python -c 'import faster_whisper'`),
  never bare `python3`: extras install into that venv, so a system-python
  import check reports "not installed" falsely. The in-repo package manager
  `pm` lives at `~/.hermes/hermes-agent/pm` and only imports with the repo
  root on `sys.path`; prefer `hermes tools`/`hermes setup` to add extras.
- Questions about "the Hermes status bar"/UI chrome refer to the Hermes TUI,
  not a Claude Code pane shown earlier: read the renderer
  (`ui-tui/src/components/appChrome.tsx`) and explain from it, never from
  memory of another tool's status line. If a screenshot is given, look at it
  first.
- A missing dashboard tab (Kanban and others) is usually a native dashboard
  plugin (`plugins/<name>/dashboard/manifest.json`), not a page in
  `web/src/App.tsx`. Check `GET /api/dashboard/plugins` and the dashboard
  journal for plugin load errors before concluding the feature is absent or
  was a dropped local mod; restart the dashboard service if the process
  predates the last update (stale modules cause plugin ImportErrors).
- `cannot import name X from agent.<module>` mid-turn, when X is present in
  the source tree, means a long-running process loaded its modules before
  the last update and now mixes old and new code. Confirm with a
  fresh-interpreter import using the Hermes venv python (it succeeds), then
  find the failing process from `~/.hermes/logs/agent.log` (`tui turn
  finished ... failure_reason=ImportError` gives the `agent_session_id`).
  Restart only that process. Restarting the gateway does nothing for a
  long-lived tmux TUI session (`tui_gateway.entry`). Ask before bouncing a
  user's live interactive session. Don't blame install snapshots or
  half-updated trees until the fresh import actually fails.
- To see which host a `localhost:<port>` dashboard URL serves, check the
  listening process (`lsof -i :<port>`, then `ps -p <pid> -o command=`). An
  `ssh -L <port>:127.0.0.1:<port> <host>` forward means it is that host's
  dashboard.
- Before diagnosing a warning banner ("almost out of memory", etc.), pin
  down which surface showed it (host, this session, a kanban worker card).
  Checking host RAM for a kanban-card warning answers the wrong question.
- Kanban CLI verbs on the remote host can stall on a held write lock and
  self-clear within minutes. Probe with `timeout 10 hermes kanban list`
  and a direct read-only SQLite query; do not restart the host or gateway
  for it unless the stall persists and the user asks.
- When `config.yaml` was copied between hosts, grep it for the other host's
  home prefix (`/Users/ayush` on Linux, `/home/ubuntu` on Mac): hook
  `command:` entries and script paths are absolute, so a copied path fails
  silently as "command not found" in the hook log. Fix the path on that
  host only, `bash -n` the target script, and note the change takes effect
  at the next gateway/session start.
- Rebuilding the TUI bundle: `cd ~/.hermes/hermes-agent/ui-tui && npm run
  build` (`npm run build:ink` for only the vendored Ink package);
  `hermes --tui-dev` runs the TS sources via tsx with no build. Running TUIs
  keep the old bundle until restarted. This answers "how do I rebuild"; it
  does not license editing source (see the first rule).
- Missing chats after a state.db repair/migration: recover by dump/reload
  from the preserved original, never assume data is gone — see
  `references/sqlite-wal-reads.md` (also covers live read-only access).
- For recent-session friction audits spanning SQLite, tasks, rotated logs,
  and Claude JSONL, follow `references/recent-session-friction-audit.md`:
  count the complete time window, deduplicate replays/mirrored streams,
  and report retention gaps.
- Run probes (API calls, config reads, gateway model lists) on the local
  machine by default; go to the remote host only when the question is about
  that host. Tracing which model a run used: see
  `references/model-routing-and-latency.md`.
- Before relying on a new cron job, run `hermes cron status`: "no gateway"
  or "ticker STALLED" means jobs silently never fire (cron runs inside the
  host gateway). On macOS start it with `launchctl kickstart -k
  gui/$(id -u)/ai.hermes.gateway`; the stale heartbeat warning persists for
  ~1 minute after restart, so recheck after 60-70s before restarting again.
- Telegram `getUpdates` conflict / watchdog "telegram fatal" alerts: first
  check whether two hosts share the bot token. The poller can be a TUI
  wrapper, not the gateway, and the fix is scrubbing the token from the
  non-owner's `.env`. For alerts from a host that must not receive
  (send-only), relay through the owner host; enabling the platform there
  always starts polling — see `references/gateway-telegram-troubleshooting.md`.
- Host audits (crons, watchdogs, plugins): for every job you recommend
  deleting, fixing or keeping, state in one line what it does, what it
  reads/writes and why it is dead or broken (last success, failure count,
  root cause). Recommending "remove the X cron" without saying what X is
  forces a follow-up question. Check whether its target project is
  finished before proposing a path fix; a dead job gets deleted, not
  repaired.
- Updating Hermes on a host with local source mods: first save `git -C
  ~/.hermes/hermes-agent diff` to `~/.hermes/cache/hermes-local-mods-<host>-<ts>.patch`,
  then run `hermes update --plan` (it lists the services it will restart).
  Run `hermes update --yes --backup` with `background=true, notify=true`,
  logging to a file and appending the exit code. It takes minutes, so a
  foreground call times out. It also kickstarts the launchd gateway, which
  can briefly drop the user's TUI; warn them. Afterwards, check each file
  listed in the setup repo's `docs/local-upstream-mods.md` against the saved
  patch to confirm the autostash was re-applied.
  Subagents running at the same time must not touch
  `config.yaml` or the install tree until the update log shows its exit line.
- An installed MCP server with near-zero real calls (count tool-call rows in
  `state.db`, excluding your own audit greps) is usually unreachable, not
  unwanted. Check three things: are its tools deferred behind `tool_search`
  with no skill naming them? Does it need a project or session activated
  first, which a gateway started from `~/.hermes` never has? Does its own
  config (for example Serena's `agent_interface`) differ between hosts? The
  fix is a when-to-use line in the governing skill plus config parity, not
  removing the server.
- Exempting one repo from a global `core.hooksPath` pre-commit
  main-branch block: key the exemption on `git rev-parse --show-toplevel`
  matching that repo's path. Back up the hook, `bash -n` it, then check that
  the exempt repo exits 0 and a different repo on `main` is still refused.
- Background-process or subagent completions showing as `❯` user prompts
  (live vs after `/resume` are different causes), and phantom commit/cron
  notifications — see `references/stale-notification-triage.md`.