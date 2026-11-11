# Deep tier: Sherlock + Parallel + verifier

Use when the decision is expensive or hard to reverse, the standard result came back thin or the owner asks for a survey. Expected 20 to 40 minutes and about USD 3 to 6 on metered routes plus the Parallel run. Sherlock itself is unmetered on the Seatbelt route.

## Procedure

1. **Write the brief once.** Exact question, field and exclusions, one in-scope and one out-of-scope example, as-of date, spend cap. Use it unchanged for every engine so their outputs merge.
2. **Fan out in parallel** (both start together):
   - **Sherlock** (`skill_view(name='sherlock')`): give it the brief split into buckets, one research question per bucket: (a) official marketplaces and large skill or agent collections, (b) whole-stage frameworks, (c) narrow lenses or critics for one gap, (d) papers and forums. A 14-bead budget finished in about 10 minutes in the trial. Sherlock's own VERIFY phase re-fetches claims in separate validation beads; keep it on.
   - **Parallel Task run** at `pro` (about USD 0.10, 6 to 11 minutes) or `ultra` (about USD 0.30, about 16 minutes) as an independent index. It found repos the other runs did not and its `api.github.com` citations gave exact stars. Do not use `core` for discovery (2 of 4 tier-1, one wrong headline claim). No confidential content in the brief.
   - Optionally the standard tier (`evidence-ledger-method.md`) as a third pass, which is what supplies the tree walk.
3. **Merge.** Build one candidate list keyed by lowercase `owner/repo` with a column per engine that found it. Keep the per-engine lists so the report can show the union and the unique finds.
4. **Verify the merged list with the standard verifier.** Run the batch `gh api` loop over every merged repo, drop `NOT_FOUND`, re-check stars and licence on any row taken from a hosted summary, then walk the trees of the top repos and run the expected-but-absent probe (steps 3, 5 and 6 of `evidence-ledger-method.md`). Put each decision-driving claim through the ledger and run the verifier (steps 7 and 9).
5. **Spot-check by hand.** The verifier checks consistency, not truth. Re-fetch at least the three claims that drive the recommendation.
6. **Report** with header (tiers used, models, queries or beads, stop reason), the union table with which engine found each row, the tree-walk hits, the named misses, the spend table (billed, list price or estimate, per tool) and the UNVERIFIED list.

## Parallel API notes

From the trial scripts that ran; confirm against docs.parallel.ai before relying on a field.

- Key: `PARALLEL_API_KEY` in `~/.hermes/.env`. Read it inside the script and never print it, log it or put it in a brief.
- **Task API** (best for the independent index): `POST https://api.parallel.ai/v1/tasks/runs` with header `x-api-key`, body `{"input": <brief>, "processor": "pro", "task_spec": {"output_schema": {"type": "text", "description": "<deliverable format>"}}}`. It returns a `run_id`. Poll `GET /v1/tasks/runs/{run_id}/result?timeout=300` and retry on HTTP 408, 504, 404 and 202 until it returns. The text is in `output.content`; `output.basis` holds the per-field citations. The trial scripts sent a browser-style `User-Agent`.
- **Responses API** (one-call quick alternative): `POST /v1/responses` with `{"model": "parallel", "input": <brief>, "reasoning": {"effort": "high"}}`. Answer text is in the `message` output items; `url_citation` annotations carry the sources. Use `high` or `medium` only; `low` failed.
- List prices per run: Task `core` 0.025, `pro` 0.10, `ultra` 0.30; Responses `low` 0.01, `medium` 0.05, `high` 0.25 (USD). Search and Extract are billed per 1000 calls. These are list prices, not billed amounts: say so in the spend table.

Minimal runner (key read in-script, result written to a file):

```python
import json, os, time, urllib.request, urllib.error

def key():
    for line in open(os.path.expanduser("~/.hermes/.env")):
        if line.startswith("PARALLEL_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")

def call(method, path, body=None):
    req = urllib.request.Request(
        "https://api.parallel.ai" + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"x-api-key": key(), "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=900))

def run_task(brief, processor="pro", out="parallel-report.md", budget_s=1800):
    run = call("POST", "/v1/tasks/runs", {"input": brief, "processor": processor,
        "task_spec": {"output_schema": {"type": "text", "description": "Complete markdown deliverable as the brief specifies."}}})
    start = time.time()
    while time.time() - start < budget_s:
        try:
            res = call("GET", f"/v1/tasks/runs/{run['run_id']}/result?timeout=300")
            break
        except urllib.error.HTTPError as e:
            if e.code not in (202, 404, 408, 504):
                raise
            time.sleep(5)
    else:
        raise SystemExit("timed out")
    content = res["output"]["content"]
    open(out, "w").write(content if isinstance(content, str) else json.dumps(content, indent=1))
```

## Gaps to state in the report

- Sherlock's flat graph at a small bead budget can skip its REFINE step: say if it did.
- Union recall is not completeness: five second-tier tools in the trial were found by no engine. The tree walk and the expected-but-absent list are what close that, so they are required inputs here, not optional extras.
- Parallel found different repos than Sherlock but listed fewer; treat it as a cross-check, not the primary.
