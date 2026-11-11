# Standard tier: the evidence-ledger method

Attribution: adapted, in our own words, from github.com/convyrtech/claude-evidence-research (`skills/research/` files at commit 698c198793ccc7b69bc5c6be4db67c79e80e52b7, MIT licence, alpha, 0 stars). Nothing from that repo is installed or required. The seeding and tree-walk steps come from what the best trial run and the earlier survey did, not from that repo's text.

Use for "what exists for X" and prior art that feeds a decision. Run it as one Opus-class researcher with a self-contained brief (exact question, exclusions, in-scope and out-of-scope examples, the output contract below). About 15 minutes, USD 2 to 4 of model spend on a metered route and nothing extra on Seatbelt.

## Workspace

Create `$TMPDIR/research-<slug>/` (slug is lowercase `a-z0-9-` only) and keep every artifact there so an interrupted run resumes instead of restarting:

- `question.md`: the user's question verbatim. Never rewrite it silently.
- `plan.md`: decision to be made, scope and as-of date, 2 to 6 falsifiable subquestions, what would change the conclusion, exclusions, stop conditions.
- `seed.txt`, `seed-verified.tsv`, `tree-hits.tsv`, `ledger.jsonl`, `captures/`, `report.md`.

Pass research text through files, never through shell command strings.

## Steps

1. **Frame.** Write `question.md` and `plan.md`. Ask one clarifying question only if interpretations would change the research materially; otherwise state the interpretation and go.
2. **Seed.** Write about 50 `owner/repo` names you already know that might fit, one per line, into `seed.txt`. Add names from awesome lists and marketplaces you fetch.
3. **Batch-verify.** One loop checks every candidate (rule 2):
   ```bash
   while read -r r; do
     out=$(gh api "repos/$r" --jq '[.full_name,.stargazers_count,.pushed_at,(.license.spdx_id // "none"),.archived]|@tsv' 2>/dev/null) \
       && printf '%s\n' "$out" || printf '%s\tNOT_FOUND\n' "$r"
   done < seed.txt > seed-verified.tsv
   ```
   A `NOT_FOUND` row is a finding, not an error: drop it from the table and list it under misses. Never keep a name that failed.
4. **Search in independent tracks**, not paraphrases of one query: repo and code search, registries and marketplaces, official docs, papers, forums and issue trackers, plus credible criticism. Snowball names and vocabulary into each new round. Run `gh api` on every new repo.
5. **Walk trees** for the top 5 repos and each large marketplace:
   ```bash
   gh api "repos/<o>/<r>/git/trees/HEAD?recursive=1" --jq '.tree[].path' | grep -iE 'review|critic|plan|analy|audit|design'
   ```
   If the response says `truncated: true`, walk the relevant subdirectory trees instead. Read the matched files themselves: a README is not evidence of what a prompt does.
6. **Expected-but-absent probe.** Name 10 tools or settings you would expect to exist, check each then record each one not found by name.
7. **Ledger.** For each decision-changing claim, append one JSON line to `ledger.jsonl` and save the page text under `captures/`:
   ```json
   {"id":"C001","claim":"...","status":"documented","confidence":"medium","source":"https://...","capture":"captures/S001.md","root":"origin-key","quote":"exact sentence from the capture","relation":"supports"}
   ```
   - `status`: `observed`, `documented`, `inferred`, `disputed` or `unknown`. Never upgrade uncertainty during synthesis.
   - `relation`: `supports`, `partial`, `contradicts` or `context`.
   - `root`: the origin of the fact. Pages that repeat one press release, benchmark or README share a root and are not independent confirmation.
   - A high-confidence claim needs two independent roots, or one directly reproduced observation with the method and output saved. `inferred` and `disputed` claims are never high confidence.
8. **Disconfirm.** Search against the leading conclusion once. Keep credible dissent in the report with the conditions under which each side is right.
9. **Verify.** Run the verifier before drafting the final table:
   ```python
   import json, re, sys
   norm = lambda s: re.sub(r"[\s\W_]+", " ", s).lower().strip()
   bad = 0
   for line in open("ledger.jsonl"):
       row = json.loads(line)
       text = norm(open(row["capture"], encoding="utf-8").read())
       if norm(row["quote"]) not in text:
           bad += 1; print("QUOTE NOT IN CAPTURE:", row["id"])
   sys.exit(1 if bad else 0)
   ```
   Fix the smallest broken claim and rerun; do not regenerate the report. Passing proves quotes exist in captured pages, not that the pages are right.
10. **Adversarial pass.** Read the draft as a hostile reviewer: does a citation support only a nearby topic, did wording get stronger than the quote, was a date or scope qualifier dropped, are two sources one root, is a recommendation dressed as fact.
11. **Stop** when the last two independent roots added nothing decision-changing, or after three materially different failed queries on one gap (record the gap), or at the 15-minute cap. Say which fired.

## Output contract

A header (model, tier, queries run, stop reason), then:

1. Findings table: name, link, stars, last push, licence, archived, what it does (from the read file), mode (adopt, adapt, patterns or skip).
2. Tree-walk results: files found inside large repos.
3. Searched and not found: queries and sources covered, plus the named misses from step 6.
4. UNVERIFIED items.
5. Ledger path and verifier result.

## Source roles

Weight by role, not by rank: primary or official for what an entity specifies, secondary for interpretation and comparison, vendor for the vendor's own feature but weak for superiority, community for failure modes but weak for prevalence, aggregators for leads only. Verify an academic paper's identity (DOI, title, year, retraction status) separately from whether it supports the claim.
