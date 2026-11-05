# Reviewing pending Hermes updates

Use when the user asks "any Hermes updates worth taking?". The deliverable is
a short recommendation grounded in the actual upstream commits, filtered to
what this user runs — not a changelog dump and not a blind `hermes update`.

## Procedure

1. `hermes --version` — shows installed version, build date, install method
   (git vs package) and whether an update is available.
2. For a git install (`~/.hermes/hermes-agent`):
   ```bash
   cd ~/.hermes/hermes-agent && git fetch -q
   git log --oneline HEAD..origin/main | wc -l          # how far behind
   git log --format='%s' HEAD..origin/main | grep -E '^(feat|perf)' \
     | grep -viE 'plugin-catalog|ci|release|desktop|test|evals'   # user-facing features
   git log --format='%s' HEAD..origin/main | grep -ciE '^fix'     # fix volume
   git log --format='%s' HEAD..origin/main \
     | grep -iE 'kanban|delegat|compress|gateway|telegram|<provider>'
   ```
   Commit count alone is not a reason to update.
3. Grep for the subsystems this user actually depends on: compression,
   delegate/kanban orchestration, gateway/Telegram, the active provider
   (read the current model config), TUI. Desktop, image-gen, catalog plugin
   bumps and CI/release plumbing are usually noise for him.
4. Report in three buckets: relevant to his setup (with one-line why it
   matters), new-but-probably-not-for-you, and a call (update or not).
5. Do NOT run `hermes update` without asking: it pulls and restarts
   processes, which ends the current session and any gateway turns in
   flight. Offer it and let the user pick the moment.

## After the update

6. Verify the update actually landed even if the terminal call timed out:
   `git -C ~/.hermes/hermes-agent rev-parse HEAD origin/main` should match,
   `git status` clean, `hermes --version` shows the new build. A tool timeout
   during `hermes update` usually means it finished in the background.
7. Run every local script that parses Hermes CLI output, especially
   the installed host watchdog script (`$HERMES_HOME/scripts/watchdog.py`) (systemd user timer
   `hermes-watchdog.timer`, every 30 min): run the installed watchdog read-only or under its normal scheduler and inspect exit status.
   Upstream changes CLI output formats without notice, and these scripts
   start false-alarming to Telegram on the very next run because the CLI is
   re-executed fresh while the gateway keeps running old code.

## Watchdog false alarms after an update

- Symptom `could not find the Gateway Service status block`: plain
  `hermes status` is now a compact summary; the `◆ Gateway Service` section
  only appears under `hermes status --full`. The watchdog must call
  `hermes status --full`. Confirm the gateway itself is fine with
  `hermes status --full | grep -A4 'Gateway Service'` before touching code.
- Diagnose with `journalctl --user -u hermes-watchdog.service --since <time> --no-pager`;
  the on-disk watchdog log can be stale and misleading.
- The watchdog self-checks that `~/.hermes/scripts/*` matches
  `~/hermes-setup/scripts/`. Any fix to an installed script
  must be copied into that repo and committed on a non-main branch, or the
  next run flags drift. Re-run the watchdog until it exits 0
  (`watchdog: ok — gateway up, N cron job(s) healthy`).
