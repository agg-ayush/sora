# Reviewing a candidate's submitted work (grading by execution)

Use when Ayush (or a cleared candidate-prep request) asks what a candidate did right and wrong on their assignment. The verdict must come from running their code, not from reading it.

## Gate first
A candidate asking the agent to grade their own work pre-interview leaks eval signal. Flag it to Ayush and wait; proceed only on his explicit clearance. Stay read-only on every shared system (DB, S3, Drive); write only to scratch.

## Procedure
1. Pull `summary.json` (Drive session folder) for `infraCapture.s3Uri` and its sha256. The sandbox is usually destroyed; the S3 capture is the only copy of the workspace.
2. `aws --profile trilogy s3 cp <s3Uri> <scratch>/capture.tar.gz`, then `sha256sum` and compare with the summary hash before trusting the contents.
3. Extract to scratch. `workspace/` holds `starter/` (untouched original), the candidate's work dir (e.g. `fix/`), any `eval_plan.md`/report files; `.claude/projects/-workspace/*.jsonl` are the agent sessions.
4. Pull the assignment statement (`GET /v1/sessions/<id>/assignment`) and list its REQUIRED deliverables. Check each exists as a file. A required write-up whose content is only scattered across docstrings is still a miss.
5. Read the starter script to confirm the bug mechanism yourself, then reproduce it on a scratch copy of the starter DB.
6. Run the candidate's own eval plan (if they wrote one) item by item on scratch copies (`cp starter/data/x.db /tmp/...`), never against `starter/`. Confirm `starter/` matches the assignment repo HEAD.
7. Mutation-test their safety checks: copy their fixed script, re-inject the original bug (e.g. drop the column from the INSERT..SELECT with sed), run it, confirm the check raises and the DB is left intact. This is the test that proves a guard has teeth.
8. Check dry-run modes by hashing the target DB before and after.

## Pitfalls
- Capture exit codes without a pipe (`cmd >log 2>&1; echo $?`). `cmd | head; echo $?` reports head's status, which falsely shows a failing gate as exit 0.
- Before calling a test result a candidate defect, rule out your own harness. Re-run the suspicious check correctly first.
- A within-transaction self-check that compares old vs new table counts only catches copy-time loss. A tamper test that corrupts the SOURCE before migrating can never trip it (the corruption copies faithfully). If the candidate's eval plan contains such a test, that is a flaw in their plan; the valid tamper test is the code mutation in step 7.

## Report shape
Three sections: done correctly (each item backed by the command result), wrong or missing (hard misses first, e.g. missing required deliverable, then plan flaws, then polish), session conduct from prompts.txt (decision-making vs dupes/noise). One-line bottom line.
