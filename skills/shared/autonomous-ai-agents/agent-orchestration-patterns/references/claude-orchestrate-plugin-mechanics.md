# Claude orchestrate plugin: IDs, phase gates, and ownership

The `claude_orchestrate` session identifier is not the kanban card ID. Pass the correct identifier to status/steer/gate, and inspect the actual tool schema before sending a nested tool call (the wrapper requires a `name` field). If a wrapper rejects gate arguments, use the documented direct CLI with its current `--help`, not a private plugin function. Inspect the result and gate artifacts before claiming completion.

In design, steer a human correction into the live author *before* reviewer dispatch; keep reviewer inputs in the reviewer's own workdir, and identify which constraints can be assessed before a pending mockup or external decision. At a hold-after-design boundary, record the design result, notify through an authorized channel, and stop further implementation until the explicitly required go-ahead. Do not try to fake the gate by manipulating a kanban status.

If the plugin's PR-description helper or body-style template is unavailable, write the proposed PR body to a file and use the supported `gh pr create/edit --body-file` route after inspecting the installed command's help. Read back the created PR body. Verify any external API effect against the exact target; redact credentials and tokens from commands, logs, and reports. A plugin session does not automatically own a board claim: verify the inherited claim/worker and avoid launching a second writer on the same worktree.

For first-run menus and retry diagnosis, load `claude-orchestrate-permission-prompts-and-crash-retry.md` rather than assuming a stalled status means a crash.
