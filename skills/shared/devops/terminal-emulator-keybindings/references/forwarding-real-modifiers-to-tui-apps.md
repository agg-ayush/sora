# Forwarding modifiers to non-shell TUI apps

Read the actual input handler before mapping a shortcut. Shell/readline byte sequences in `readline-escape-sequences.md` are not a universal contract: a TUI built on Ink, Textual, or another framework may test the event's `super`, `meta`, or `ctrl` bits instead. Never assume a byte such as `\x1f` means Cmd+Z undo in a particular app.

## Procedure

1. Inspect the target app's key decoder and shortcut handler. In current Hermes Ink, `ui-tui/src/lib/platform.ts` maps the macOS action modifier to `key.meta || key.super`, but `ui-tui/src/components/textInput.tsx` requires **`key.super` specifically** for Cmd+Backspace/ForwardDelete line kill so Option+Backspace remains word deletion. These details are implementation-dependent; recheck the live version rather than applying them to another TUI.
2. Check support for an extended keyboard protocol on terminal **and** receiving app (kitty keyboard protocol/CSI-u or a compatible mode). Traditional terminal byte streams cannot express Cmd/Super distinct from a guessed control sequence.
3. If the target expects a real Cmd bit and the protocol supports it, a scoped WezTerm mapping can re-emit the modifier:

   ```lua
   { key = 'z', mods = 'CMD', action = wezterm.action.SendKey { key = 'z', mods = 'CMD' } },
   ```

   `SendKey` sends a key event to the pane; `SendString` sends fixed bytes. Verify the shortcut isn't already handled by the terminal. An app that does not negotiate extended keyboard events may still receive a different representation.
4. Inspect the effective terminal mapping with `terminal(command="wezterm show-keys --lua")`, then test the behavior in the **actual running TUI**. Mapping visibility does not prove the TUI decoded the intended modifier.

## Failure example

A WezTerm Cmd+Z mapped to `SendString("\x1f")` reached Hermes Ink as a literal underscore instead of undo: the TUI did not treat that byte as its Cmd+Z event. Forwarding the original key via `SendKey` with a negotiated keyboard protocol avoids this specific mismatch, subject to a real live-app test.

Source: https://wezterm.org/config/lua/keyassignment/SendKey.html and Hermes `ui-tui/src/lib/platform.ts` / `components/textInput.tsx`.
