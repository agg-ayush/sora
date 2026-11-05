# Board status reporting (blocked/open cards)

When asked "what's blocked and why" or "status on the cards":

1. Read each card's body and latest block reason fresh from the kanban DB before explaining it. Block notes go stale fast: a card blocked on a bug another card already fixed, or on expired creds mid-investigation, is really done.
2. Close stale-but-done cards (work merged or verified elsewhere) instead of listing them as blocked. Park credential/permission blockers the user defers, then drop them from the report.
3. Explain each remaining card in one or two plain sentences: what it is, what it actually waits on (a decision, a credential, another card). Don't just quote the card title or its internal jargon; the user asks "what is this? explain simpler" otherwise.
4. Say whether a card involves code or only data/ops (e.g. "direct DB cleanup, no code"), and whether any change is already decided or it's measure-first (e.g. load test before any scaling change; never change scaling before telling the user).
5. Separate a card's scope from nearby working features it sounds like. Say plainly when a live-verified feature is NOT what the card touches, and check the code for how the feature actually gets its signal (webhook vs poll) before claiming a dependency.
6. For "release" cards when prod is already live, spell out what's actually left (merge order, exact-head CI, final real-browser verification). Don't imply prod doesn't exist yet.
7. When the user approves a card they already approved earlier, act on it. Don't ask again.
8. Board-echo notifications ("t_x -> done/blocked") for transitions you just made need at most one line, no "Next step:" filler. Don't pad status replies with a deferred next step for something obvious; just do it.
9. Before saying a card is running, check its gating matches the user's intent: cards that touch shared auth/infra (Workspace credentials, scaling) must sit blocked until the user says go, even if dispatch picked them up.

## Card stuck on a trivial live check
Fix proven live by the main session: close the card yourself (see "Close the card once the fix is proven live" in `orchestrator-ops-routing.md`).

If the code half merged and the card spins on a small live verification (send one test mail, book one row), close the loop yourself from the main session with the admin helper instead of waiting on the worker. If the check can't run in that environment (route flag off, missing permission), report that concrete reason rather than marking it verified.

## Reporting a running card's real progress
Heartbeat freshness only proves the worker process is alive. For "status" or "is it actually working", read the latest heartbeat `note` from `task_events` plus whether a branch/PR exists and its CI state, and report that ("PR up, 7/8 green, preview served on :<port>"). A fresh heartbeat with no note and no pushed branch means still in build, say so.

When the user says a card "seems idle", check for real activity before answering: `pgrep -af <task_id>` shows whether the worker and its claude run are alive, and a recent tmux `send-keys` steer in that list shows what it is doing right now (e.g. fixing a CI lint error). Report that concrete state. If there is no live process or the pane hasn't changed across checks, treat it as stalled and re-steer or restart instead of reassuring.

## Worker died before pushing
A card can look alive (fresh heartbeat) while its worktree holds an unpushed fix commit. Check `git status`/`git log origin/main..HEAD` in the card's worktree and whether a remote branch exists. If the commit is complete, run its tests and typecheck, confirm the diff is exactly the asked change, then push and open the PR (pushing finished worker output is not writing code). Don't wait on the dead worker when the task is urgent.

## Green is not correct
When the user asks for the fix to be correct, not just green: read the diff before merging and explain the mechanism in plain terms against their exact rule. If they probe a condition as a possible tautology, show from the code where the flag is set and what state it reflects, rather than restating that tests pass.

## Carding wrapper UI changes
1. Locate the exact render site first: `git grep` on `origin/main` for the visible string or view name (e.g. the `view === "summary"` branch in `assessment-client.tsx`), then read the JSX. Put the file, the branch, and the exact element to change in the card body so the worker doesn't re-hunt.
2. Every candidate-facing UI card carries the show-first gate at creation: push the branch, serve a local preview (or screenshots), and do not merge until the user confirms. The blanket merge authority on this repo does NOT cover UI the user wants to eyeball; a UI PR merging mid-review forces a follow-up PR for every tweak.
3. When the user adds a vague layout complaint ("feels out of place"), card it as a presentation-only pass matching the app's existing patterns (centered page, heading hierarchy, list styled as content) and state explicitly which functional pieces (textareas, error notes, submit actions) must stay untouched.
4. Several small UI asks on the same screen go in one card; separate screens get separate cards.
5. Previews you or workers served (wrapper `next dev` on 3000/894x, python mockup servers) are throwaway: kill them once the user has checked the screen or the PR merged, and confirm the ports are down (`ss -tlnp`). Don't leave them for the user to notice.

## Diagnose before carding
When the user says "check why it happens before carding":
1. Read the actual code path on `origin/main` (route -> handler -> gate function) and quote the lines that decide the behavior. Label each claim as read-from-code or inferred; don't present a guessed mechanism ("probably stale projection rows") as the traced root cause.
2. Present the mechanism in two or three plain sentences, then ask for or propose the fix direction. The user often prescribes the fix; put their exact rule in the card body as the acceptance criterion.
3. When the user lists several issues in one message (including "one other unrelated issue"), account for every one before replying: carded, folded into a card, or explicitly asked about. Unrelated screens get their own card; never silently drop the trailing item.

## Media gate product rules
- The gate mixes seen-once latches (a leave only flips state, never clears the row) with current-state signals (phone camera connected now). Continue re-runs the gate server-side (`handleEntered`), so a client-hidden button is not the enforcement point.
- Once a candidate has satisfied the gate for a session (joined with phone + laptop), a leave and rejoin must re-open it from the recorded DB state. Don't re-require live phone proof and don't re-flag the candidate.
- Provisioning starts at `POST /v1/sessions/:id/join` (page join); `POST /entered` (Continue) only runs the gate and arms the timer. Answer "when does it provision" from these routes, not memory.

## Carding stakeholder copy changes
When a stakeholder asks to change a candidate-facing message to new text, the new text REPLACES the old heading/body. Don't append it after the existing copy: a new line tacked on under the old heading reads as "you added another message", not a change. Put in the card that the old strings must be removed, the new copy must be the first and only message, and tests must assert the old headings are absent.
