# Pulling a candidate's session artifacts (assignment, prompts, workspace)

Use for interview prep packs, session review or grading. Read-only everywhere: only local scratch writes.

## Procedure

1. **Find the session.** `GET /v1/sessions?limit=100` returns a bare JSON list (not wrapped in `sessions`/`data`) and returns the full table. Filter on `candidateEmail` AND `candidateName` by a distinctive fragment (surname or Telegram username), never a first name alone: common first names match many candidates. Prefer rows with `status: ended` and non-null `joinedAt`; forfeited rows have no artifacts.
2. **Read `/v1/sessions/:id/detail`.** It returns a flat snake_case object (`candidate_email`, `drive_folder_id`, `prompts_url`, `infra_capture_s3_uri`, `infra_capture_sha256`, `infra_video_url`, `transcript_stats`), so camelCase key lookups silently return null. Dump the keys first.
3. **Get the workspace.** `aws --profile trilogy s3 cp <infra_capture_s3_uri> /home/ubuntu/.hermes/cache/scratch/<name>-capture.tar.gz`, verify `sha256sum` equals `infra_capture_sha256`, then extract. Layout: `workspace/` (candidate files) and `.claude/projects/-workspace/*.jsonl` (agent transcripts).
4. **Get the prompts.** If `prompts_url` is null and the Drive folder has no prompts.txt, extract from the capture JSONLs: take `type == "user"` records, read `message.content` (string, or list of `type: text` parts), drop text starting with `<` (tool results, system tags), then merge ALL jsonl files and sort by `timestamp`. A session can have several parallel Claude conversations; reading one file loses prompts and order.
5. **Get the assignment.** `GET /v1/admin/assignments/<slug>` (slug = session `assignment`); the markdown is in `statementMd`.

## Prep pack shape

One markdown file sent via `MEDIA:` with three parts: (1) full assignment statement, (2) every prompt verbatim in order with times, (3) interview coaching: what they did well to defend, where the interviewer will push (grounded in gaps visible in the prompts, e.g. session froze before implementation), deliverables to know cold, answer-format tip. Then a short message addressed to the candidate summarising the three parts.

## Grading a session

When asked for a verdict on a candidate's session, grade the decision trail in the prompts (requirements read, conflicts surfaced, prioritisation, verification gates), not code quality, unless code is explicitly requested. Cite prompt numbers as evidence.
