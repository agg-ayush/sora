# Background conductor for a bounded protocol

When a multi-phase protocol does not need further user input and the user wants the main chat free, delegate a **self-contained** bounded conductor. Supply the settled goal, all required paths/context, exact output artifact and verification bar, authorization boundaries, and the required skill name so the child can load it itself. A child does not inherit the parent's conversation, but it may have `skill_view` if granted; do not assume either guaranteed access or guaranteed absence.

Check the **current** `delegate_task` schema and depth/concurrency configuration before promising fan-out. In a shallow delegation tree, an orchestrator child may be unable to spawn more descendants even if its role supports it; run the protocol inline or restructure the task when depth is exhausted. Bounded children are not durable across an agent process/session exit; use an appropriate durable scheduler or tracked background job for work that must survive it.

If the protocol still requires a human choice, handle that phase in the main conversation first. A named protocol must be followed, not replaced by a vaguely similar generic subagent. On completion, read the reported artifact and independently run a cheap verification before claiming success. When background delivery requires ending this turn, stop rather than polling.
