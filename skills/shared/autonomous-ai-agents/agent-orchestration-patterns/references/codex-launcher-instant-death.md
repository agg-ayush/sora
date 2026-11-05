# Diagnose an instant coding-CLI launcher exit

When `claude_orchestrate` exits an executor immediately with no useful artifact, inspect plugin status, pane and launch logs, then run a harmless **standalone CLI probe** using the same model, workdir and authorized credentials. A working standalone CLI narrows the fault to launch arguments, PTY, working-directory trust, environment inheritance or plugin state; it does not by itself prove a permanent launcher bug. Confirm the model identifier uses the executor's native format, not a Hermes-prefixed alias, and inspect actual TUI prompts before sending input.

Preserve the current worktree/branch and one-writer rule. Retry once only after correcting a plausible cause; otherwise choose an authorized executor/`delegate_task` fallback, mark the alternate path on the card, and independently verify its actual output. Do not describe a single failed launch as provider outage or switch billing/permissions routes without the applicable approval.
