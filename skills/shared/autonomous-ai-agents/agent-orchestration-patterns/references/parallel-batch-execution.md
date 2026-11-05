# Running N independent jobs in parallel under real deadline pressure

## When this applies
The user hands you a set of N independent items (candidate submissions, files,
records) that each need the same pipeline/script run, wants results fast, and
is explicit about time pressure ("I need this today", "why is this taking so
long"). This is different from a leisurely batch job — every extra minute of
you debugging infra costs visible wall-clock time the user is watching.

## Isolation is non-negotiable
If the pipeline keeps any state on disk relative to its own working directory
(`.flow/`, lockfiles, a state DB, npm's `_npx` cache dir, etc.), N parallel
invocations from ONE shared directory WILL race — state-file corruption,
`ENOTEMPTY` on shared caches, partial output from the wrong run bleeding into
another's result. Symptoms look like flaky/random failures, not a clean error,
which burns time misdiagnosing.

Fix: stage N isolated working directories under the configured scratch path
(e.g. `$TMPDIR/job-1` .. `$TMPDIR/job-N`) and launch each job from its own directory. Cheap in disk, saves
you a debugging cycle.

**Pitfall when doing the copy under time pressure**: a fast copy-loop (`for i
in 1 2 3; do cp -R "$src" "$TMPDIR/job-$i"; done`) is easy to get wrong when you're
also staging per-item input (e.g. copying each candidate's submission files
into their own job dir) in the same breath — a copy/paste error can put item 1's
input into every job dir. After staging, always verify per-dir input differs
(`diff` the staged input files pairwise, or grep a per-item identifier out of
each dir) before launching — don't just trust the loop ran.

## One watcher, not N polling loops
Don't hand-poll every background process yourself turn by turn — set up a
single watcher (a background terminal script on a short tick, e.g. 30s) that
checks all N processes' liveness/log tails and reports. This is what lets you
say "here's the real state of all 8 jobs" in one shot instead of grep-hunting
each one when the user asks "status?". Kill the watcher when the batch is
done.

## Reusable across-job fixes
When a fix (e.g. an upstream bug in a shared script the pipeline uses) is
found mid-batch by debugging ONE job's failure, that fix needs to reach every
OTHER isolated copy too, not just the one you were debugging — copy the fixed
file into every sibling job dir (and re-verify per-dir, since a stale grep
pattern can make you think a copy already has a fix it doesn't — always
re-check the actual file contents in each dir, not just a fast substring
grep that might miss due to whitespace/regex differences).

## Local vs. remote worker split, and when to abandon the remote
It's common to split the batch across local machine + a remote box (more
parallelism than the local machine alone can carry). If the remote box turns
out to be flaky, the instinct to "fix the remote properly"
before proceeding is usually wrong under time pressure:

- Set a hard cap (~2-3 min) on remote-recovery attempts before you fall back.
- Hand the remote recovery to a background subagent so it doesn't block you —
  it might still succeed and you can slot late items onto it if it does.
- Meanwhile keep making progress on what doesn't need the remote at all —
  usually "run everything locally instead" once you know the local machine
  can actually carry the load.
- **But respect an explicit instruction on the split.** If the user said "run
  one locally, the rest on the devpod, use subagents if you need to — but get
  it running through the normal path, not a workaround", that means: keep
  trying the real remote path (via a subagent so it doesn't block), don't
  unilaterally decide "all local" just because the remote is being difficult.
  Ask or wait for a real go-ahead before overriding a stated split, even if
  the remote is annoying. This was a direct correction in one session — the
  orchestrating agent kept flip-flopping between "all local" and "split" based
  on which one was blocked at that moment, which the user explicitly called
  out as worse than picking one and being transparent about the tradeoff.

## Behavioral rules when the user is time-pressured (direct corrections from real sessions)
These are not optional politeness — they were explicit user corrections:

- **When a user says "don't run anything, just tell me," stop new work**
  and report what is already known, labeling the last observation's age.
  If the remaining state cannot be confirmed without a tool call, say so
  instead of pretending a stale observation is live.
- **Don't narrate a plan and then get stuck re-litigating it turn after
  turn.** Under time pressure, "I keep flip-flopping and burning your time" is
  the exact failure the user will call out. Pick one path, say what you're
  doing, do it. If it fails, say so plainly and pick the next path — don't
  cycle back to a path you already tried and abandoned without new
  information.
- **When asked "can we determine success before wasting N minutes waiting?"
  — go check ground truth (process state, actual API/exit codes, `docker ps`,
  file timestamps) instead of continuing to wait out a timeout you already
  started.** A running wait/poll is not itself evidence of anything; the user
  wants you to interrupt it with a real diagnostic check when asked.
- **Give literal, falsifiable status, not reassurance.** "It's progressing" is
  not an answer under time pressure — say exactly which step each job is on,
  whether that's expected to be slow (e.g. "opus on 11 sessions IS the slow
  step, it's not stuck"), and how you know (checked live process list / log
  timestamp, not just "the timeout hasn't fired yet").
- **When you have to change something outside plan (e.g. force a new
  container, switch a run to root vs non-root, change which box a job runs
  on), say so and why in one line, don't ask permission for each micro-step**
  — but DO surface it, because the user will ask "why did you even do X" and
  expects a real causal answer, not "the previous plan wasn't working."
