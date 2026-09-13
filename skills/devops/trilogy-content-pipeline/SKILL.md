---
name: trilogy-content-pipeline
description: Trilogy content pipeline documentation and data layers.
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [trilogy, content-repo, pipeline, architecture, docs]
---

# Trilogy Content Pipeline

Umbrella for working in the Trilogy content-generation pipeline repo (`alpha-learn-content-gen`, local clone `/Users/ayush/Trilogy/content`): finding/maintaining its architecture docs, and auditing its data layers (Supabase, hosted S3, QC bucket, Review API).

## When to Use

- Asked "where's the doc for X", "do we have a design doc/ITD/IPD for Y", or to attach/audit docs against house style.
- Asked to audit lesson state across environments, compare assets (videos/images/JSON) between dev and prod or Supabase and S3, or answer "is X in sync".
- Asked "why isn't lesson X showing up" anywhere in the pipeline.

## Procedure

### Documentation map (references/content-repo-docs-map.md)

Docs are NOT all under `docs/` — check the live tree, don't assume. Where they actually live:
1. **`docs/architecture/`** — numbered stage-by-stage pipeline architecture (`00-overview.md` … `07-qc.md`). Read the numbered file matching the stage in question first.
2. **`docs/info/`** — operational knowledge: `01-running-tests.md`, `02-validating-changes.md`, `03-deployment-layers.md` (canonical map of all five data layers), `DebugLesson.md`.
3. **`docs/brainlifts/`** — educational source-of-truth specs (what a good lesson looks like).
4. **`docs/superpowers/specs/` and `docs/superpowers/plans/`** — dated design-spec + implementation-plan archive (`YYYY-MM-DD-<feature>-design.md`).
5. **Component-level docs — NOT under `docs/`** — will not show up in a `docs/` search:
   - `ppt-generator/architecture.md` (ITD)
   - `components/lesson-qc-auto-checker/design/architecture.md` + `healer-architecture.md` + `design/adr/001..009-*.md`
   - `components/qti-converter/docs/IMPLEMENTATION_SUMMARY.md`, `FIELD_MAPPING.md`
   - `infra/article-generation/RUNBOOK.md`, `infra/script-generation/RUNBOOK.md`, `infra/render/RENDER_FLEET.md` (per-fleet ops runbooks)
   - `lesson-dashboard-architecture.md` (repo root)

When asked "all docs related to X", always also check the component's own directory for `architecture.md`, `design/`, `docs/`, or `RUNBOOK.md` next to the code it documents.

### Data-layer audits (references/content-pipeline-data-layers.md)

**Read `/Users/ayush/Trilogy/content/docs/info/03-deployment-layers.md` first** — it is the canonical map of all five layers. Key facts that matter for every audit:
- Hosted bucket key layout: `lesson-plans/{id}.json`, `visuals/{id}/{step}/{slide}/{slide}.mp4`.
- Buckets: `alpha-learn-content-hosted-dev` / `-prod` (hosted/runtime), `alpha-learn-qc` (QC/iteration history, only S3 copy of source PPTX).
- Lesson IDs contain a literal `+` — passed as-is in S3 keys and Supabase queries; only URL-encoded as `%2B` inside lesson-plan `video_path` fields.
- Supabase REST: `{SUPABASE_URL}/rest/v1/{table}` with `apikey` + `Bearer` headers both set to `SUPABASE_ANON_KEY` (from repo `.env`).

**Never guess a Supabase status/enum string — discover it.** Real values are human-authored (e.g. `'Uploaded to Athena'`, not `uploaded_to_athena`). Pull distinct values with counts before filtering:

```bash
set -a; source .env; set +a
curl -s "${SUPABASE_URL%/}/rest/v1/lessons?select=status" \
  -H "apikey: $SUPABASE_ANON_KEY" -H "Authorization: Bearer $SUPABASE_ANON_KEY" \
  | python3 -c "import sys,json,collections; d=json.load(sys.stdin); print(collections.Counter(r.get('status') for r in d).most_common())"
```

URL-encode spaces as `%20` (not `+`) in query strings.

**Cross-bucket asset diffs:** list objects under the same prefix in both buckets, match by key *relative to the prefix*, then compare. **ETag alone is not sufficient proof of drift** — multipart uploads get hash-of-part-hashes ETags, so byte-identical content uploaded with different chunking can have different ETags. Compare in order: ETag equal → same; else size + content-range fetch.

## Pitfalls

- Assuming `docs/` is exhaustive — component-level `architecture.md`/`design/`/`RUNBOOK.md` files live next to the code, not under `docs/`.
- Guessing a Supabase status string — always discover via a `select=status` + Counter first.
- Treating an ETag mismatch as drift without checking multipart-upload chunking — false positive.
- Forgetting the `+` in lesson IDs — passes as-is in S3/Supabase but must be `%2B` inside `video_path` URL fields.
- Re-deriving bucket names/key layouts from scratch instead of reading `docs/info/03-deployment-layers.md` first.

## Verification

- Doc audit: every claimed doc location verified against the live tree (`ls`/`find`), not just the docs map.
- Data audit: status value pulled live from Supabase (not assumed); bucket diff filtered down to app-manifest-referenced files where relevant; both buckets' relative-key sets enumerated before comparing.

## References

- `references/content-repo-docs-map.md` — full per-component doc inventory, conventions for attaching new docs, git-archaeology for stale docs.
- `references/content-pipeline-data-layers.md` — full S3 cross-bucket diff procedure, Review API notes, false-positive-safe verification patterns.
