# Readline / zsh emacs-mode escape sequences

These are the byte sequences zsh (emacs keymap, default) and GNU readline
already bind to standard line-editing actions. Terminal emulator keybinding
fixes should send these via `SendString`/equivalent rather than inventing
new behavior — the shell already knows what to do with them.

| Action | Sequence (escaped) | Readline/zsh bind name |
|---|---|---|
| Word back | `\x1bb` (ESC b) | `backward-word` |
| Word forward | `\x1bf` (ESC f) | `forward-word` |
| Delete word back (whitespace-delimited) | `\x17` (Ctrl+W) | `unix-word-rubout` |
| Delete word back (word-char-delimited) | `\x1b\x7f` (ESC DEL) | `backward-kill-word` |
| Delete word forward | `\x1bd` (ESC d) | `kill-word` |
| Line start | `\x1b[H` or `\x01` (Ctrl+A) | `beginning-of-line` |
| Line end | `\x1b[F` or `\x05` (Ctrl+E) | `end-of-line` |
| Kill to line start | `\x15` (Ctrl+U) | `unix-line-discard` |
| Kill to line end | `\x0b` (Ctrl+K) | `kill-line` |
| Delete char forward | `\x1b[3~` | what an unmodified Delete/Fn+Backspace key already sends |

## Word-boundary nuance

`unix-word-rubout` (Ctrl+W) and `backward-kill-word` (ESC DEL) are NOT the
same: Ctrl+W stops at whitespace only, so `/path/to/file` is one word and
gets deleted in one shot. ESC DEL stops at non-alphanumeric characters, so
the same path deletes one segment (`file`, then `to`, then `path`) per
keypress. Ask the user which behavior they want for Opt+Backspace /
Ctrl+Backspace if precision matters — default recommendation is Ctrl+W for
Opt+Backspace (matches most GUI text editors' "delete word" feel) and ESC
DEL for Ctrl+Backspace (finer-grained), but this is a judgment call, not a
fixed rule.

## WezTerm-specific notes

- `wezterm show-keys --lua` prints the full **effective** table (defaults +
  overrides merged) — use it to check what's actually bound before adding a
  duplicate binding.
- `wezterm --config-file <path> ls-fonts` (or any subcommand) will fail
  loudly if the Lua config has a syntax error — no separate Lua interpreter
  needed to validate.
- Config changes take effect via WezTerm's own file-watcher; no restart
  required.
