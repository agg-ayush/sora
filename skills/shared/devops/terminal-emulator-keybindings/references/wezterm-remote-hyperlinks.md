# WezTerm hyperlinks in remote panes

## Mechanism

With a WezTerm SSH domain / mux connection, rendering and hyperlink detection happen in the **local GUI**, even if `wezterm-mux-server` and the shell are remote. Plain `ssh` inside a local pane also produces text rendered locally. Clicks on recognized URLs therefore use the local browser by default; do not install a browser on the remote host or forward `open` over SSH just to make them clickable.

## Diagnose before changing config

1. Test a full `https://example.com` URL in a local pane and in the remote pane. If both click in the local browser, nothing needs changing.
2. If a URL is not recognized, distinguish plain text matching from an OSC 8 link or tmux mouse capture. WezTerm's `open-uri` default already opens recognized links in the browser; a custom handler calling `wezterm.open_with(uri)` and returning `false` is usually redundant.
3. If a bare domain such as `example.com` must be clickable, preserve the built-in rules when customizing `hyperlink_rules` (that setting replaces defaults):

   ```lua
   config.hyperlink_rules = wezterm.default_hyperlink_rules()
   table.insert(config.hyperlink_rules, {
     regex = [[\b[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+\b]],
     format = 'https://$0',
   })
   ```

   The `format` **must include a protocol**; `format = '$0'` on a bare domain is not a valid web URL. This broad regex can also match unwanted domain-like text, so test the exact link target and narrow it for the user's actual output if needed. Use `[=[...]=]` instead of `[[...]]` if a regex embeds `]]`.
4. On a scratch copy, parse-check with `terminal(command="wezterm --config-file <scratch-config-path> ls-fonts")`. Only update the approved live config after checking the matched target. WezTerm reloads on save.

## tmux mouse mode

When tmux has `mouse on`, it can capture clicks before WezTerm handles links. WezTerm's default `SHIFT` bypasses app mouse reporting: try Shift+Click, or inspect `bypass_mouse_reporting_modifiers` if it was customized. This is distinct from hyperlink detection.

Sources: https://wezterm.org/config/lua/config/hyperlink_rules.html ; https://wezterm.org/config/lua/window-events/open-uri.html ; https://wezterm.org/config/mouse.html .
