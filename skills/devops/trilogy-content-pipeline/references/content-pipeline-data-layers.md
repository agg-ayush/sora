---
name: content-pipeline-data-layers
description: "Query and cross-check the alpha-learn-content-gen pipeline's data layers (Supabase lesson tracking, hosted S3 dev/prod buckets, QC/iteration bucket) — use whenever asked to audit lesson state, compare assets (videos/images/JSON) across environments, or answer 'is X in sync between dev and prod / Supabase and S3'. Covers correct status-value discovery, S3 cross-bucket diffing, filtering diffs down to app-manifest-referenced files, and false-positive-safe verification."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [supabase, s3, aws, content-pipeline, alpha-learn, data-audit, trilogy]
    related_skills: [aws-iam-credential-rotation, content-repo-docs-map]
---

# Content Pipeline Data-Layer Audits (alpha-learn-content-gen)

Class of task: answer questions that span the content pipeline's data layers —
Supabase (lesson tracking/status), the hosted S3 bucket (dev + prod, what the
app actually serves), the QC/iteration bucket (source-of-truth PPTX/yaml
history), and the Review API. Typical asks: "for every lesson in state X,
check whether asset Y matches between dev and prod", "is this lesson's video
in sync with its lesson-plan JSON", "why isn't lesson X showing up".

**Read `/Users/ayush/Trilogy/content/docs/info/03-deployment-layers.md` first**
— it is the canonical map of all five layers (what each holds, key patterns,
which layer answers which question, known gotchas). Don't re-derive bucket
names or key layouts from scratch; that doc already has them. Key facts
repeated here because they matter for every audit of this shape:

- Hosted bucket key layout: `lesson-plans/{id}.json`, `visuals/{id}/{step}/{slide}/{slide}.mp4`.
- Buckets: `alpha-learn-content-hosted-dev` / `alpha-learn-content-hosted-prod` (hosted/runtime), `alpha-learn-qc` (QC/iteration history, only S3 copy of source PPTX).
- Lesson IDs contain a literal `+` — passed as-is in S3 keys and Supabase queries; only URL-encoded as `%2B` inside lesson-plan `video_path` fields.
- Supabase: REST at `{SUPABASE_URL}/rest/v1/{table}` with `apikey` + `Bearer` headers both set to `SUPABASE_ANON_KEY` (from repo `.env`).

## 1. Never guess a Supabase status/enum string — discover it

Status values are human-authored strings, not the snake_case you'd guess
(e.g. the real value is `'Uploaded to Athena'`, not `uploaded_to_athena`).
Before filtering, pull the distinct values with counts:

```bash
set -a; source .env; set +a
curl -s "${SUPABASE_URL%/}/rest/v1/lessons?select=status" \
  -H "apikey: $SUPABASE_ANON_KEY" -H "Authorization: Bearer $SUPABASE_ANON_KEY" \
  | python3 -c "import sys,json,collections; d=json.load(sys.stdin); print(collections.Counter(r.get('status') for r in d).most_common())"
```

Then fetch the actual id list for the confirmed value (URL-encode spaces as
`%20` in the query string, not `+`).

## 2. Diffing assets across two S3 buckets (dev vs prod, or hosted vs QC)

Pattern: list objects under the same prefix in both buckets, match by the key
*relative to the prefix* (not the full key — the prefix itself differs), then
compare.

**ETag alone is not sufficient to prove drift.** Multipart-uploaded objects
get an ETag that is a hash-of-part-hashes, not a hash of the whole object —
two buckets can hold byte-identical content uploaded via different multipart
chunking and get *different* ETags. Compare in this order:
1. ETag equal → same content, done.
2. ETag differs but size equal → **do not conclude drift.** Download both and
   MD5 the actual bytes before reporting a difference. In practice this
   resolves to "identical" the overwhelming majority of the time — it's a
   multipart-boundary artifact, not real content drift.
3. Size differs, or key only exists on one side → genuine drift, report it.

A statically re-runnable version of this whole flow (list + diff + MD5
fallback, parallelized) is at `scripts/s3_cross_bucket_diff.py` — copy it,
point `BUCKET_A`/`BUCKET_B`/the prefix template at your case, and feed it a
newline-delimited id list. It also holds the aggregate-summary pattern
(status counter + a JSON dump for programmatic follow-up) that's worth
reusing for any "check N things, summarize + link full detail" audit.

## 3. Verification discipline for this class of task

- Run diffs with the **admin/assumed-role identity** for read-only
  cross-bucket audits rather than provisioning or reusing a service
  credential — it's read-only, low-risk, and avoids permission gaps between
  dev/prod credential sets.
- When you find "differs", **always sample-verify a few, then verify the
  full set** before reporting — don't extrapolate from one spot-check. In one
  audit, MD5-verifying only a 3-item sample would have still left 52
  unverified same-size/different-etag files; verifying all of them (55 total)
  is what turned "looks fine" into "confirmed fine."
- Report counts by category (identical / same-content-different-etag / real
  diff) plus the concrete list of what's *actually* different — don't bury
  the 20 real-drift lessons inside a summary that only says "197/217 match."
- **`aws s3api get-object ... /dev/stdout` output is not clean JSON** — the
  CLI appends its own response-metadata JSON right after the object body, so
  `json.loads(stdout)` raises `JSONDecodeError: Extra data`. If that's caught
  by a broad `try/except: return None` (or the caller treats "no refs found"
  as a legitimate empty result), the script silently degrades to reporting
  *zero drift everywhere* — this actually happened in one audit: all 20
  flagged lessons came back "extras only, no real drift" until a manual
  spot-check contradicted it. Parse with
  `json.JSONDecoder().raw_decode(stdout)` and take only the first document.
  Treat "manifest parsed but yielded zero expected references" as an error
  to surface loudly, not a clean result — a suspiciously-perfect aggregate
  ("0 real issues" / "all in sync") is a signal to spot-check by hand before
  reporting, not a result to trust outright.

## 4. Filtering a raw bucket diff down to what an app-level manifest references

Raw S3 diffs (section 2) surface *every* difference under a prefix, but not
every differing file is something the app actually serves — buckets
accumulate orphaned/unreferenced assets (old renders, abandoned variants)
never wired into the manifest. Before reporting "N lessons differ," narrow
to files the manifest actually links — the "latest state" JSON (e.g.
`lesson-plans/{id}.json`, sourced from **prod**, the source of truth for what
ships) governs, not raw bucket enumeration:

1. Fetch the manifest from the environment that's the source of truth
   (usually prod).
2. Walk the manifest recursively collecting every string value matching the
   asset suffix (e.g. `*.mp4`) — don't assume a single fixed field name;
   manifests nest these under varying keys (`video_path` and others).
3. Normalize: URL-decode (`%2B` → `+`, etc.) and strip the manifest's
   embedding prefix (e.g. `visuals/{id}/`) so the reference set uses the same
   relative-key space as the bucket-diff `key`/`only_in_*` fields.
4. Intersect the normalized reference set with the raw diff's differing
   keys. Only the intersection is real drift; the rest is unreferenced noise
   — report both counts, but only escalate the intersection.

A reusable version of this filter (fetch manifest, walk + normalize refs,
intersect with a prior `s3_cross_bucket_diff.py` output) is at
`scripts/filter_diff_by_manifest.py`.

## 5. Google Drive as a fourth layer (via rclone on the QC host)

Some audits need Drive (the reviewer-facing lesson folders), not just
Supabase/S3. Drive has no local rclone remote — the `athena:` remote only
exists inside the QC host's docker container. Run all Drive reads/writes
over SSH into that container (see
`/Users/ayush/Trilogy/docs/agent-notes/qc-dashboard.md` for host/key), e.g.:

```bash
ssh -i <qc-key> ubuntu@<qc-host> \
  'docker exec <qc-container> sh -c "rclone md5sum \"athena:Grade 3/<lesson_id>/videos_per_slide\" --include \"*.mp4\""'
```

Pitfalls specific to this layer:

- **Lesson-ID → grade parsing**: don't assume grade is a fixed split index.
  `CCSS.MATH.CONTENT.3.MD.B.3+5` has grade at `split(".")[3][0]`, not `[2]`
  (`[2]` is the literal string `CONTENT`). Verify against a real Drive path
  before trusting any derived `Grade {n}` folder name.
- **Tracker sheet column ambiguity**: the lesson-status tracker (Google
  Sheet, one tab per grade) does not reliably have a column literally named
  `Lesson ID` — it can be `Substandard ID` instead, alongside decoy columns
  like `Lesson Order`/`Lesson ID` that hold something else (e.g. `1.0`,
  `2.0` floats, not CCSS strings). Accept either header name and sanity-check
  the parsed values look like real lesson IDs before using them.
- **Don't assume a Drive/S3 byte mismatch is a false positive, but don't
  assume it's real staleness either — check the video stream, not just the
  file.** This is the opposite default from the S3-vs-S3 case in section 2
  (same-size-different-ETag is usually a multipart artifact there): here a
  raw file-md5/size mismatch is common even for identical content, because
  the hosted publish pipeline remuxes the MP4 container and re-encodes audio
  on its way to S3 while Drive keeps the raw PowerPoint export. A sweep that
  reported 104/109 lessons as "content differs" by file md5 dropped to only
  13/109 lessons (29 files) with a genuine content difference once each
  mismatch was re-checked by extracting and hashing just the video stream
  (`ffmpeg -map v -c copy -f md5 -`). Always run that stream-level check
  before reporting a Drive/S3 video mismatch as real staleness — see
  `references/drive-s3-video-audit-notes.md` for the exact command and the
  nested-SSH/docker-exec quoting pitfall that check runs into.
- **Before repairing anything, confirm which side is stale — don't assume
  Drive is always behind.** A confirmed genuine mismatch only says the two
  sides differ; it doesn't say which direction to push. Compare Drive
  `ModTime` vs. S3 `LastModified` per file: the common case is Drive older
  (safe to push S3→Drive), but a re-render can land on Drive without ever
  being republished to S3/prod — then Drive is *newer* and pushing S3→Drive
  would regress it. That's a publish gap (needs `deploy.py publish`), not a
  sync gap (don't touch Drive). In one sweep, 27 of 123 mismatched files
  were this reversed case. Partition the mismatch list by direction and get
  explicit sign-off before writing anything to Drive.

See `references/drive-s3-video-audit-notes.md` for the full adapter recipe
(tracker parsing, rclone-over-SSH command shape, S3 key derivation,
classification rules), the S3→Drive repair-push recipe (reusing the same
nested-shell base64 trick as the read path), the direction-check that must
precede any repair, and the ad-hoc verification approach for this class of
script.

## 6. "Lesson generated but not showing up" — check whether the pipeline's publish stage was actually invoked, not just data sync

A distinct failure shape from sections 1-5: a lesson can succeed all the way
through generation (build, QC, even a Drive upload) and still be invisible on
the app/Learn UI — not because of a sync/drift bug between two data stores,
but because **the caller (worker/CLI) never invoked the pipeline's publish
stage in the first place**. Pipelines built as an ordered stage list (e.g.
`ingest → build → qc → publish`) commonly gate the expensive/side-effecting
final stage (deploy-to-CDN + register-in-DB) behind an explicit flag
(`--publish`) that a producer's own subprocess invocation can simply omit —
silently, with no error, because every stage it DID request succeeded.

Before treating "not showing up" as a data-sync/drift bug (sections 1-5),
check the stage-invocation chain directly:

1. Find the exact command the worker/producer shells out to run the pipeline
   (its subprocess arg list) and diff it against the pipeline CLI's full flag
   set (`--help` or the arg parser source). A flag present in the CLI but
   absent from the caller's invocation is a real candidate — don't assume the
   caller passes everything the pipeline supports.
2. Trace what that missing flag actually gates (read the stage's
   implementation, not just its `--help` text) — confirm it's the one doing
   the CDN/DB write, and confirm what upstream gate it respects (e.g. a
   publish stage that correctly refuses to run while a QC report holds a
   blocker — that gate should stay intact when you add the flag).
3. Don't conflate two separate artifacts as the same "done" signal — a
   worker's own best-effort Drive upload succeeding does NOT mean the
   pipeline's publish stage (CDN deploy + DB registration) ran; they can be
   fully independent code paths writing to different destinations.
4. Fix is normally: add the missing flag to the caller's invocation, make
   the downstream effect best-effort (a CDN/DB write failure should not fail
   an otherwise-successful generation job — log and continue), and verify the
   QC/blocker gate still holds. Then republish already-generated-but-unpublished
   items (publish-only, no regen needed — the built artifacts already exist)
   rather than only fixing it prospectively.
