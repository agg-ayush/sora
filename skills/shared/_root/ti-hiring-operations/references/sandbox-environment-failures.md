# Sandbox environment failure triage

Use when a candidate reports the coding environment not opening, loading indefinitely, or a tool inside it (e.g. the coding CLI) not working.

## Procedure

1. Pull the session's structured events from `/ecs/ti-orchestrator` (ssh flow: `/ecs/ti-orchestrator-ssh`) with filter `{ $.sessionId = "ID" }`. Read in order: `session joined` -> `sandbox created from snapshot` (note `snapshotId`) -> `sandbox ready` -> `session entered` -> whatever repeats after.
2. Find the first recurring warn after `entered`. `pane health probe failed ... has no route for ttyd port 7681` means the terminal server has no exposed route: the editor page loads but the terminal never attaches, which is exactly "loading forever".
3. Separate frontend from sandbox: curl the access URL and its static assets. 200s at normal latency rule out frontend/CDN and put the fault inside the sandbox.
4. Quantify blast radius before answering: filter the recurring warn (e.g. `%no route for ttyd port 7681%`) over the batch window, count distinct `sessionId`s, and compare with live-session count and submitted `work_trouble` concerns. One session vs batch-wide changes the answer.
5. Answer "why only today" by finding what is shared and new: the row's sandbox backend (`legacy_vercel` vs `infra_http`), the `snapshotId` prefixes in use, and bake-time warnings. `sandbox exposes fewer ttyd ports than tabs ... reached:0` on `ti-bake-*` sandboxes means the snapshot was baked without terminal routes and every session cloned from it inherits the defect.
6. Remediation framing: snapshot-created sandboxes fix their route set at create time, so live affected sandboxes cannot be repaired in place. Fix the bake step, re-bake, re-create affected sandboxes.

## Pitfalls

- Before endorsing a claim that a specific tool inside the sandbox failed, check the precondition: if the terminal pane never had a route, the tool was never reachable. Say the framing is wrong, cite the log line, and keep the candidate's experience as real.
- `sandbox ready` / `candidate-start ready` only means the create call returned; it does not prove ttyd routes exist.
- These failures log at warn, so zero error-level events does not mean healthy.
- A `media gate fail-open fired` warn in the same timeline is unrelated to the terminal; keep it out of the environment root cause.
- CloudWatch `?a ?b` patterns are OR, not AND: `?keyword ?SESSION_ID` floods with every session. Scope keywords with the JSON selector (`{ $.sessionId = "ID" && $.msg = "*keyword*" }`) or filter by session and grep the saved JSON.
