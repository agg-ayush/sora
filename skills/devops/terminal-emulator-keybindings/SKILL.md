---
name: terminal-emulator-keybindings
description: Fix terminal keybindings broken by config.keys overrides.
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [terminal-emulator-keybindings]
---

# Terminal emulator keybindings

## Root cause pattern

Most terminal emulators' custom key-binding config (`config.keys` in WezTerm,
`keybindings` in kitty, `key_bindings` in Alacritty) **fully replaces** the
built-in default table the moment the user defines ANY entry — it does not
merge. This means one custom binding for e.g. Cmd+Enter silently drops every
other default: word-jump, line-jump, tab switching, font size, clear
scrollback, etc. Confirmed on WezTerm; verify per-tool if unsure ("does
setting `config.keys` disable the rest of the defaults" is the doc question
to answer before touching anything else).

The symptom is never "one key is broken" — it's "an entire category of keys
silently does nothing" (all OS-standard line-editing shortcuts at once).

## Diagnostic workflow

1. **Confirm it's an override, not a missing feature.** For WezTerm:
   ```
   /Applications/WezTerm.app/Contents/MacOS/wezterm show-keys --lua
   ```
   prints the FULL effective key table (defaults + your overrides merged
   into what's actually active). Grep it for the key in question — if it's
   truly absent, that confirms the override wiped the default.

2. **Audit the whole class, not just the reported key.** If Opt+Backspace is
   dead, check ALL of these in the same pass — they die together because
   they were all defaults before the override:
   - Word jump: Opt+Left / Opt+Right
   - Line jump: Cmd+Left / Cmd+Right, Home / End
   - Word delete: Opt+Backspace, Ctrl+Backspace, Opt+Delete (fwd)
   - Line delete: Cmd+Backspace
   - Tool-native defaults unrelated to line editing (new tab, search, clear
     scrollback, font size, tab switching) — list these for the user and let
     them pick which to restore; don't silently re-add UI/window shortcuts
     nobody asked about.

3. **Verify config syntax without assuming a language interpreter is
   installed.** `lua`/`luac` are commonly absent on macOS. Don't install
   them just to syntax-check — the terminal binary itself will refuse to
   start (or `show-keys`/`ls-fonts` will error) on a broken config:
   ```
   /Applications/WezTerm.app/Contents/MacOS/wezterm --config-file <path> ls-fonts
   ```
   Exit 0 + sane output = config parses. No restart needed afterward if the
   app watches the config file for changes (WezTerm does).

## Fix pattern: send readline/zsh sequences, don't fight the OS

Don't try to make the terminal emulator reproduce native macOS text-field
behavior. Instead bind the key to `SendString` (WezTerm) / equivalent with
the **exact byte sequence the shell's line editor already binds** to that
action (zsh emacs-mode and GNU readline share these). See
`references/readline-escape-sequences.md` for the full table — it covers
word jump/delete both directions, line start/end, kill-to-start, and notes
on Ctrl+W vs Esc+DEL word-boundary differences (whitespace-delimited vs
word-char-delimited).

## Pitfalls

- When one key fix is requested, proactively check for siblings in the same
  category before declaring done — the user will come back with "any other
  keys that got rekt like that?" if you only fix the one reported.
- Don't reflexively restore lost tool-native defaults (new tab, search,
  etc.) without asking — only the line-editing/shell-interaction keys are
  clearly wanted; window/UI shortcuts are a separate judgment call for the
  user.
- A key with `mods = "NONE"` (e.g. plain Home/End) only needs a binding if
  the key produces no escape sequence on its own — check `show-keys --lua`
  for what's already mapped before adding a duplicate.
