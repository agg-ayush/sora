# <Subject> — Independent Auditor Verdict

Branch: <branch> @ <head_sha>
Diff under audit: <base_sha>..<head_sha> (<n> commits)
Auditor: independent subagent, fresh context, read-only. All findings verified
against code on disk; test suite executed locally.

verdict: pass | fail | partial
confidence: <0-100>
suite: "<N> passed / <M> failed / <K> skipped (<duration>)"

findings:
  - id: 1
    status: CLOSED | OPEN | PARTIAL
    evidence: >
      file.py:LINE-LINE — <mechanism: what changed and why it addresses root
      cause>. Cross-referenced against <test file:line / live probe output>.

  - id: 2
    status: CLOSED
    evidence: >
      ...

new_issues: none | <list any regression or gap introduced by the fix pass itself>

## Notes / minor observations (non-blocking)
- <anything worth flagging that doesn't change the verdict>
