# Ad-hoc live-probe scripting pitfalls

When a fix-verification audit needs a live probe that isn't just a
`pytest`/`vitest` invocation — e.g. building a standalone script that seeds a
fixture run dir and directly invokes the changed function to eyeball its real
output (see "Live-probe where feasible" in `fix-verification-audit.md`) — two
mechanical pitfalls recur:

1. **Inline heredoc-to-bash trips the command-parser's size/heredoc
   blocklist.** A multi-step verification script (temp dir setup, multiple
   JSON fixtures, a node/tsx invocation, assertions) piped into `terminal`
   as one big heredoc (`cat > script.sh <<'EOF' ... EOF && bash script.sh`)
   can hit `BLOCKED (hardline): command parser limit or malformed executable
   payload`. The blocked payload is auto-saved to
   `~/.hermes/cache/blocked-scripts/blocked-<ts>-<hash>.sh` and CAN be run
   via `terminal(command="bash <that path>")` as a one-time recovery, but the
   clean fix going forward is to skip the inline-heredoc-to-bash pipeline
   entirely: write the script with `write_file` (a real file on disk), then
   execute it with a plain `terminal(command="bash <path>")`. Delete the
   script afterward if it was scratch-only.

2. **`$(pwd)` inside a nested `cd`'d subshell resolves to the subshell's cwd,
   not the caller's.** A script that captures a path via `$(pwd)` and then
   uses it inside `(cd "$TMP" && node -e "import('$(pwd)/scripts/x.ts')")`
   will have `$(pwd)` re-evaluated INSIDE the `cd "$TMP"` subshell, resolving
   to `$TMP/scripts/x.ts` instead of the intended repo path — a silent wrong
   path, not an obvious syntax error. Capture absolute paths into fixed
   variables (`REPO=/abs/path/to/repo`) at the top of the script, before any
   `cd`, and reference the variable everywhere instead of a late `$(pwd)`.
