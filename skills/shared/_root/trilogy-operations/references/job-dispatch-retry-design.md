---
name: job-dispatch-retry-design
description: "Design/fix retry logic for a queue-backed job dispatch CLI."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [retry, job-dispatch, sqs, s3, aws, worker-fleet, verification]
    related_skills: [no-test-suite-verification, python-monorepo-worktree-testing, content-pipeline-data-layers]
---

# Job Dispatch Retry Design

Class of task: a CLI that submits jobs to a queue-backed worker (SQS job
message, S3 `_DONE`/status marker for terminal state — the shape used by this
repo's worker fleets: script-generation, article-gen, render) needs automatic
retry-on-failure, and/or a webhook notification on terminal state.

## When to use

- Adding `--retries`/`--webhook` to a job submitter CLI.
- Fixing a retry loop that resubmits everything on any "failed" status.
- Auditing whether a dispatch CLI's retry predicate is too broad.

## The core bug this class of task invites

A naive retry loop treats every non-`ok`/`passed` terminal state as
retryable and resubmits. This is wrong whenever the worker's failure space
includes **deterministic content rejections** — the pipeline looked at this
exact input and refused it for a reason that resubmitting the identical
input cannot change (a format/lint rule violation, a QC gate blocking the
content). Retrying those just burns worker time and queue capacity to
reproduce the same rejection every time.

Before writing (or fixing) the retry predicate:

1. **Grep the producer for the exact terminal-reason text, don't guess it.**
   The failure reason string usually doesn't live in the dispatch CLI itself
   — it's written by the pipeline/worker/QC layer into the terminal marker
   (e.g. an S3 `_DONE` object body, a status field). Find the literal
   producing line (`search_files` for a distinctive fragment of the message)
   before assuming a status enum or prefix convention.
2. **Classify every terminal-failure reason into retryable vs terminal-by-design**
   before deciding the predicate:
   - Retryable: transient/infra failures — worker crash, timeout, stalled
     job, no terminal marker within a deadline.
   - Terminal-by-design: content-level rejections computed from the exact
     input given — format-rule violations, QC blocks, anything where a
     human would have to change the *input* (script, config, asset) for a
     retry to have any chance of succeeding.
3. **Check sibling components for the established convention first.** If
   this repo has multiple worker fleets with dispatch CLIs (e.g. one per
   content type), check whether a sibling's dispatch/watch code already
   encodes this reason-text classification — don't re-derive the convention
   from scratch if a working precedent exists.

## Retry loop shape

A reasonable, minimal contract for this class of feature:
- `--retries N` (cap) and `--retry-backoff S` (seconds between attempts).
- Each retry re-enqueues under a **fresh job id** (don't reuse the failed
  job's id — the worker/queue infra usually assumes one id = one lifecycle).
- Retry only on the retryable-failure classification above; terminal-by-design
  failures return non-zero immediately, no retry attempted.
- `--webhook URL` posts `{job_id, lesson_id/task_id, status, reason,
  <result_link>, attempt}` on **every** terminal state (each retry attempt
  and the final outcome) — best-effort: a webhook POST failure logs a
  warning and continues, it must never fail the batch/exit code.

## Ad hoc verification without hitting real AWS

If the new retry/webhook logic isn't directly exercised by the existing test
suite (or there's no time to extend fixtures), a fake-client harness proves
the real code path without real S3/SQS calls. Monkeypatch `boto3.client` to
return in-memory fakes, and patch any module-level nondeterminism (job-id
generator, `requests.post`) so behavior is fully observable:

```python
class FakeS3:
    def __init__(self): self.objects = {}
    def put_object(self, *, Key, Body, **_): self.objects[Key] = Body
    def get_object(self, *, Key, **_):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}

class FakeSQS:
    def __init__(self): self.sent = []
    def send_message(self, **kwargs):
        self.sent.append(kwargs); return {"MessageId": f"m-{len(self.sent)}"}

dispatch.boto3.client = lambda service, **_: {"s3": s3, "sqs": sqs, "logs": FakeLogs()}[service]
dispatch.new_job_id = lambda: next(fresh_ids)          # deterministic retry ids
dispatch.requests = type("R", (), {"post": staticmethod(lambda url, *, json, timeout: posts.append((url, json, timeout)))})()
```

Seed `FakeS3.objects` with the terminal marker (`_DONE` key -> reason bytes)
each attempt should see, then call the module's real watch/retry function
(not a re-implementation) and assert on `sqs.sent` (what got re-enqueued and
with what dedup/job ids) and `posts` (webhook payload shape, one per terminal
attempt). Cover: pass-first-try, fail-then-pass-within-retry-cap, exhaust
retries (nonzero exit), and each terminal-by-design reason NOT retried
(`sqs.sent == []`). See `no-test-suite-verification` for the general
ad-hoc-verification discipline (report as ad hoc, not suite-green; extract
the real function; clean up the script after running).

## Pitfalls

- Don't classify by string-matching a generic `"failed"` prefix alone — a
  terminal-by-design rejection often also starts with `failed:`; the
  distinguishing signal is the specific reason text, not the top-level
  status.
- Don't let `sys.exit`/module-level side effects in the CLI's real entry
  point run for real during ad hoc verification if it performs any live
  mutation (real SQS send, real webhook) — patch those out first, per the
  harness above.
- A webhook or retry bug here is invisible in a green pytest run if the
  existing suite only covers the single-shot happy path — when adding
  retry/webhook to an existing dispatch CLI, check whether the suite
  actually exercises multi-attempt/failure-reason branches before trusting
  "tests pass" as coverage for the new logic.
