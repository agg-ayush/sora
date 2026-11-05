# Parallel design review and source verification

Use when a design needs several independent reviewers. Give each reviewer a distinct lens (mechanism, trust boundary, operability, data migration), the same current artifact and hard requirements; do not ask all reviewers the same open-ended question and count identical findings as independent evidence. Record a newly discovered non-negotiable requirement in the governing design/brief before dispatch, rather than only in a side-channel prompt.

While review runs, inspect the one or two code/API claims on which the proposed implementation depends. Resolve a source-answerable question with a cited file/line, CLI `--help`, or tested API response, then send that *settled* result to the author and reviewers. Do not preempt an unresolved design trade-off as a factual correction or edit a live T2's artifact yourself. If a user-provided mockup or approval is still pending, explicitly scope the review to what can be assessed now; revisit the dependent part after the input arrives.

For a proposed remediation, check executability on a safe isolated instance or a non-destructive dry run; see `design-remediation-executability-check.md`. A reviewer's approval is not a substitute for exercising a risky command or verifying its rollback.
