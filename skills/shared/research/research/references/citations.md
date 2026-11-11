# Citations in answers and written documents

Every claim taken from an outside source gets an inline numbered citation and a `Sources:` list. A ledger script owns the `url -> [n]` mapping, so numbers and URLs come from retrieval and never from memory: the model only emits small integers it was handed. For high-stakes work the same ledger becomes a fact-checking chain: verbatim quotes attached to each source (rejected unless they literally appear in the fetched text), model-knowledge claims flagged `[unverified]`, and a gate that fails any draft whose cited sources carry no evidence.

Covers chat answers, written documents (markdown, PDF, docx, slides) and research reports. Skip inline citations when retrieval is incidental to another task (a syntax lookup mid-coding, casual chat, creative writing). Academic BibTeX pipelines belong to the `arxiv` skill; this ledger can feed it (see Formats).

## Setup

`scripts/sources.py` is stdlib Python 3. Retrieval comes from whatever is configured (`web_search`, `web_extract`, `browser_navigate`, `terminal`). Ledger default: `$HERMES_HOME/cache/citations/ledger.json`; override with `--ledger <path>` or `HERMES_CITATION_LEDGER`.

```bash
S=~/.hermes/skills/research/research/scripts/sources.py
python "$S" reset                                  # clean ledger
python "$S" add https://example.com/a --title "A"  # prints [1]; idempotent, URL-normalised
python "$S" list                                   # ledger table
python "$S" render                                 # Sources: block
python "$S" verify draft.md                        # catch bad citations
```

| Action | Command |
|---|---|
| Register several | `sources.py add <url1> <url2> ...` |
| Register from JSON tool output | `sources.py ingest results.json` |
| Attach verbatim evidence | `sources.py quote <id> --text "exact wording" --from page.txt` |
| Render styles | `sources.py render [--style markdown\|plain\|footnotes\|bibtex\|evidence] [--only 1,3]` |
| Render only what a draft cites | `sources.py render --cited-in draft.md` |
| Rewrite a draft's Sources block in place | `sources.py render --replace-in draft.md` |
| Check a draft | `sources.py verify draft.md [--strict] [--min-coverage 0.6] [--evidence]` |

## Procedure

1. **Reset the ledger** at the start of a task that will produce a grounded answer. Skip the reset when continuing a draft whose ids already exist: reuse keeps numbering stable.
2. **Register every source at retrieval time**, before writing prose. After each search, extract or fetch, pass the URLs to `add` (or pipe raw JSON through `ingest`). Registering later from memory is the failure this exists to prevent.
3. **Cite while drafting.** The id goes right after the sentence the source supports, no space, each id in its own brackets: `Ice floats because it is less dense than liquid water.[1][2]`. At most 3 ids per sentence; cite per sentence, not in a dump at the end. Only ids the ledger returned. Claims from your own knowledge get no citation. Present conflicting sources as both readings with their own ids. Quote figures, dates and names as the source states them. Say "no source found for X" instead of smoothing a gap.
4. **Append the Sources block** with `render --cited-in <draft>` (or `--replace-in`), never by retyping URLs. Pick the `--style` for the target (Formats below).
5. **Verify before delivering.** `verify` exits non-zero on unknown ids, a Sources block that disagrees with the ledger, or (with `--min-coverage`) thinly cited prose. Fix and rerun. Read warnings even on exit 0: an uncited registered source usually means a claim lost its attribution during editing.
6. **Chat answers** follow the same steps with the draft in the reply, ending with a `Sources:` list from `render --only <ids>`.

Coverage is `sentences with declared provenance / prose sentences`. A prose sentence is a line fragment of 4 or more words after the Sources block, headings, table rows and fenced code are dropped. A `[n]` citation or an `[unverified]` marker declares provenance. Run `verify` without a threshold first and read the `info: stats:` line before choosing a number.

## Multi-platform sweeps

"What are people saying about X" is not one `web_search`. Fan out by source type, register every URL, then attribute each claim to its platform:

| Source type | Route |
|---|---|
| Open web | `web_search` then `web_extract` |
| Community discussion | `reddit-reading` skill |
| Blogs, releases, changelogs | `rss-feeds` skill |
| Video | `youtube-content` skill |
| Code and issues | `terminal` with `gh search repos` and `gh search issues` |
| X or Twitter | `xurl` (needs API access) |

Keep opinion and measurement apart: a forum thread shows that users report something, not that it is true. Pair it with a primary source or label it sentiment. Report per-platform coverage gaps ("Reddit search returned nothing newer than March") instead of silently narrowing.

## Fact-checking mode

For medical, legal, financial or safety work, disputed claims or when asked to fact-check:

1. **Attach a verbatim quote per source.** Save the extracted page text to a file, then `quote <id> --text "<sentence>" --from page.txt`. The quote is rejected unless it appears in the file (the match ignores whitespace, case and markdown markup, so you quote the sentence as a reader sees it). Copy and paste, never retype; a paraphrase is rejected by design.
2. **Flag model-knowledge claims `[unverified]`** (`The refactor likely predates 2.0.[unverified]`). Check what can be checked; the marker is for what genuinely cannot be sourced. A deliverable dominated by it should say so in its summary.
3. **Cross-check disputed facts against a second independent source.** Cite both readings with their own ids and quotes and say which you weight and why. One source is reporting; two independent sources are corroboration.
4. **Gate and render evidence:**
   ```bash
   python "$S" verify report.md --evidence --min-coverage 0.5
   python "$S" render --style evidence --replace-in report.md
   ```
   `--evidence` fails the draft if any cited source has no attached quote. The evidence style prints each source's quotes under its URL so the reader sees claim, source and exact text.

## Formats per output target

- **Markdown or chat:** inline `[n]`, end block `## Sources` (`--style plain` gives a bare `Sources:` for chat).
- **PDF via LaTeX:** `--style footnotes` mapped to `\footnote{}` at first use, or numeric markers plus an endnotes section; or `--style bibtex` (`@misc` keyed `source<N>`) with `\cite{source3}`. Do not mix numeric `[n]` and `\cite{}` in one document.
- **Word (.docx):** real footnotes beat inline brackets for human-edited prose. Keep ledger ids as footnote numbers and generate the .docx from a markdown source of truth so `verify` still works.
- **Slides (.pptx):** inline `[n]` in the bullet and one Sources slide at the end (`--style plain`). No URLs in body bullets.
- **Spreadsheets:** a `source` column holding the id plus a `Sources` sheet. No URLs in data cells.
- **Wiki or multi-page:** per-page Sources block with ids shared across pages from one ledger, so `[7]` means the same page everywhere. Do not reset between pages of one build.
- **Research papers:** export `--style bibtex` into `references.bib` and hand off to the `arxiv` skill for venue formatting and `\cite` checks.
- **Code and config:** no citations inside generated code. Put provenance in the commit message, PR body or a doc header.

## Why it works

- Hallucinated citations come from reconstructing a URL from memory. A small integer handed out at retrieval cannot be reconstructed: a wrong id is detectable and a wrong URL is impossible because `render` writes it.
- Cite while writing, not after. Post-hoc insertion invites finding a source that plausibly matches a sentence already written, which is how a citation ends up supporting something the page does not say.
- Take figures, dates and names from the source's own words. Each summarisation hop is a chance for a number to drift.
- At most 3 ids per sentence: beyond that a citation stops identifying which source carries the claim. Never cite a source you did not consult.

## Pitfalls

- Registering after writing, or renumbering mid-task. Ids are ledger identities: if a draft cites `[4]`, `[4]` stays that source. Run `reset` only between tasks.
- Retyping URLs or hand-editing the Sources block. Always `render`; a hand-typed URL is an unverified claim and a hand-sliced block gets flagged as stale or duplicated.
- Citing a search snippet as if you read the page, or quoting from a snippet. Run `web_extract`, save the text, then `quote --from` that file.
- Over-citing: a citation on every clause hides which source carries the load.
- Parallel subagents each have their own working directory: point them all at one ledger with `--ledger` or `HERMES_CITATION_LEDGER` or their ids collide.
- Using `[unverified]` as an escape hatch. If most sentences carry it, the task needed more retrieval.

## Verification

```bash
python "$S" verify report.md --strict --min-coverage 0.5
```

Green means every `[n]` exists in the ledger, the Sources block lists exactly the cited ids with the ledger's URLs, and the cited share of source-bearing sentences meets the threshold.
