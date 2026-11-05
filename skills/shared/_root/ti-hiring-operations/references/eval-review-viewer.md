# Eval review viewer (transcript-eval)

Viewer mechanics. For the cohort filter-and-serve procedure (which eval block to filter on, port layout, ssh handoff) see `references/eval-review-sets.md`.

## Getting the reports

- Eval reports live in the GCS bucket `<gcs-bucket>`, one folder per candidate/assignment. Download them to a local cache dir (e.g. `/home/ubuntu/<cohort>-eval-cache`) with the transcript-eval repo's own GCS client (`NODE_PATH=<repo>/transcript-eval/node_modules node <script>`) when the gcloud CLI needs interactive re-auth; it uses its own credentials. Run the download as a background job with notify, never a long foreground timeout or sleep loop.
- Pattern values: `shows`, `mixed`, `does_not_show`, `not_exercised`. "Yellow" = `mixed`.

## Serving the list

- The list-capable viewer is the version of `transcript-eval/tools/review-viewer/server.mjs` that has `listRunsFromLocal` and an `/api/runs` route; its index page renders every candidate with eval patterns (from the `combined` block), triage route and review state. A newer revision scoped the viewer to explicit `--candidate/--assignment` IDs and removed listing. Check `grep -n listRunsFromLocal` across checkouts (and `git log` on the file) before concluding the viewer cannot list.
- Deep links: the list-capable version boots a run from `#<candidate_id>/<assignment_id>` (its `runKey`); query params do nothing there. The ID-scoped version uses `?candidate_id=&assignment_id=`. Match the link format to the version you are serving. The ID-scoped version reads both query params at boot (`initReviewViewer`), its `/api/runs` 400s without them, and it serves artifacts at `/runs/<candidate>/<assignment>/report.json`; it binds 127.0.0.1 only.
- Run: `node tools/review-viewer/server.mjs --root <cache dir> --port <port> --bucket <gcs-bucket> --source local --layout flat` as a background process, then verify with `curl -s localhost:<port>/api/runs` that the run count matches the cache.
- Before starting, free the port (kill the previous `server.mjs`); an EADDRINUSE crash leaves the old viewer serving and looks like success.
- When Ayush says a tool can do something, find the version that does it before building a substitute (a one-off list page was rejected). If the capability was removed on main, say so and offer a card to restore it.
