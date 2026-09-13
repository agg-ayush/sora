# Forwarding real modifiers to non-shell TUI targets

The readline-escape-sequence trick in `readline-escape-sequences.md` only
applies when the receiving app is a shell / readline-emacs-mode line editor.
Many TUI targets — a chat app's input box, an editor, anything built on
Node/Ink, Textual, ratatui, etc. — have their OWN keybinding table that
checks for the literal modifier bit (`key.super` for Cmd, `key.meta` for
Option), not an escape-sequence convention borrowed from readline.

## Why the naive fix fails

Sending a raw control byte as a `SendString` guess (e.g. assuming Cmd+Z
should be `\x1f` because "that's Ctrl+_ in emacs, and emacs binds Ctrl+_ to
undo") can be flatly wrong for the target app. Symptom: the binding
registers cleanly in `wezterm show-keys --lua`, looks correct, and still
does nothing — or types a literal character — at runtime, because the
target app never had an emacs-style Ctrl+_ binding in the first place; it
has its own native Cmd+Z handler that never sees a real Cmd bit.

## Correct approach

1. **Identify the target app's actual input framework by reading its
   source**, not by guessing from "it's a CLI so it's probably X". Grep for
   how it decodes key events (e.g. `key.super`, `key.meta`, `key.ctrl`
   fields) rather than assuming prompt_toolkit / readline / raw termios.
2. **Check kitty keyboard protocol (CSI u) support on both ends.** WezTerm,
   kitty, iTerm2, and Ghostty can all advertise/emit it. CSI u can carry a
   real Cmd/Super bit that legacy escape sequences cannot express at all —
   this is the only way to forward "real Cmd", not an approximation of it.
3. **If the target's own binding table branches on the literal modifier**
   (e.g. hermes-ink's textInput checks `key.super`/`key.meta` directly for
   Cmd+Z undo/redo), bind the terminal key to forward the **actual
   modifier**, not a synthesized byte sequence:
   ```lua
   { key = "z", mods = "CMD", action = act.SendKey({ key = "z", mods = "CMD" }) },
   ```
   (WezTerm's `SendKey` re-emits the key through its own encoder, producing
   a CSI-u sequence carrying the super bit when the terminal is in kitty
   mode — vs `SendString` which sends fixed literal bytes with no modifier
   information at all.)
4. Verify registration with `wezterm show-keys --lua | grep "'z'.*SUPER"`,
   then test in the actual live target app — a clean "registered" from
   `show-keys` only proves WezTerm's table is correct, not that the
   downstream app interprets the resulting bytes as intended.

## Case study

User's WezTerm was sending `\x1f` (Ctrl+_) for Cmd+Z, intended for a shell's
readline undo. The actual target was Hermes CLI's TUI input box (an
Ink/React component, `textInput.tsx`), whose emacs-style undo logic checks
`isActionMod(key)` which is `key.meta || key.super` on macOS — it has no
Ctrl+_ path, so `\x1f` arrived as a literal underscore keypress instead of
triggering undo. Fix: switch the WezTerm binding from
`act.SendString("\x1f")` to `act.SendKey({ key = "z", mods = "CMD" })` so
the real Cmd bit reaches the app's native `mod+z` undo handler.
