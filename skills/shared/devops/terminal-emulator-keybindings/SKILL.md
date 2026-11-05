---
name: terminal-emulator-keybindings
description: "Diagnose terminal keys and WezTerm link/mux behavior."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [terminal, keybindings, wezterm, links, tui]
---

# Terminal Keybindings and WezTerm Config

Diagnose which layer owns a shortcut: terminal emulator, shell line editor, tmux, or a TUI app. For remote-pane URL clicks see `references/wezterm-remote-hyperlinks.md`; for shell editing byte sequences see `references/readline-escape-sequences.md`; for modifier-aware TUI apps see `references/forwarding-real-modifiers-to-tui-apps.md`.

## When to Use

- Terminal shortcuts, word/line navigation or deletion, or a TUI's Cmd/Option shortcuts fail.
- WezTerm config or remote-mux hyperlink clicks behave unexpectedly.

## Procedure

1. **Identify the receiving layer.** Check the active app and its input framework: shell/readline/zsh, tmux, or a modifier-aware TUI. Check the terminal config and the app's actual key handlers before mapping keys. Done when the expected action and the layer consuming the key are known.
2. **Inspect effective bindings.** For WezTerm use `terminal(command="wezterm show-keys --lua")` (or its app-bundle binary on macOS), and inspect `config.keys` plus `disable_default_key_bindings`. A `config.keys` entry **extends or overrides individual defaults**; it does *not* erase the whole default table. Only `disable_default_key_bindings = true` clears it. Kitty also retains defaults unless `clear_all_shortcuts` is set; inspect the target emulator's actual documentation rather than assuming Alacritty/kitty behave like WezTerm. A missing shell-editing key may never have been a terminal-native default. Done when presence/override is established instead of inferred from a symptom.
3. **Audit related failures.** Check word jump/delete, line jump/delete, and Home/End together when the issue is line editing; report unrelated native UI bindings separately, without silently changing them. For unmapped plain keys, observe what bytes already reach the app before adding a duplicate mapping. Done when neighboring affected shortcuts are identified.
4. **Apply the right translation only when needed.** For zsh emacs mode or GNU readline, send the existing byte sequence from `references/readline-escape-sequences.md` via `SendString` (verify shell keymap first). For a TUI whose handler tests `key.super`/`key.meta`, do not guess a control byte: consult `references/forwarding-real-modifiers-to-tui-apps.md` and test actual modifier forwarding in its keyboard protocol. Done when the intended action occurs in the real target app.
5. **Validate a scoped config edit.** Use the terminal's own parser on a scratch copy first: `terminal(command="wezterm --config-file <scratch-config-path> ls-fonts")`, then inspect `wezterm show-keys --lua` against the same config and test the live app only if a live change was approved. WezTerm normally reloads a saved config; registration alone does not prove downstream behavior. Done when syntax and actual action both pass.

## Pitfalls

- WezTerm **`hyperlink_rules`**, unlike `keys`, *does* replace all default hyperlink rules; begin with `wezterm.default_hyperlink_rules()` before adding custom matches. See the hyperlink reference.
- Lua `[[...]]` ends at the first `]]`; use `[=[...]=]` if a regex contains that sequence.
- Shell `SendString` sequences cannot preserve a genuine Cmd/Super bit for a modifier-aware TUI.
- `show-keys` shows the terminal table, not the shell's or TUI's keybinding table.

## Verification

- [ ] Effective terminal mapping, target keymap, and actual behavior were distinguished.
- [ ] Config syntax is valid; sibling shortcuts and unintended UI overrides were checked.
- [ ] Links and modifiers were tested in the receiving app, not merely in a config dump.

WezTerm defaults/override documentation: https://wezterm.org/config/keys.html and https://wezterm.org/config/default-keys.html.
