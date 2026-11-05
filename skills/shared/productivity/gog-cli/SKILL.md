---
name: gog-cli
description: Use gog for Google Docs, Drive, Sheets, Gmail and Chat.
version: 2.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Google, Docs, Drive, Sheets, Gmail, Calendar, gog, CLI]
---

# gog CLI

Use authenticated `gog` on either host for Docs/Drive/Sheets/Gmail/Calendar/Chat when the account and scopes cover the task. Prefer it to `gws` for these workflows. Discover available accounts with `gog auth list -j` and specify the resource owner with `--account`.

## When to Use
Any task that reads or writes Google Docs, Drive files, Sheets, Gmail, or
Calendar from the terminal.

## Always-on rules

- Every command takes `--account <email>` (or `-a`); add `-j` for JSON, `-p`
  for plain TSV. Discover flags with `gog <noun> --help` — the surface is
  large; don't guess a flag.
- The Linux binary is at `/home/ubuntu/.local/bin/gog` (`/opt/homebrew/bin/gog`
  is macOS-only), and Google commands need `GOG_KEYRING_PASSWORD` exported on
  the Linux box (unlocks the file keyring):
  Load that variable into the process environment from the existing secret store without printing the value, passing it as a command argument or embedding it in a document. A TTY does not replace the variable for unattended work.
- **Don't assume gog's JSON shape matches gws's.** `docs create` returns
  `{file: {id, ...}}` — parse `.file.id`, not a top-level `documentId`. Don't
  cross-apply field names between the two tools.
- A 403 on one account can mean "wrong account", not "broken auth": retry with
  the resource owner's account before chasing a token/scope fix.

## Docs: create, insert, edit

- **Create**: `gog docs create <title> -j` — title is a positional arg, no
  `--title` flag. `docs insert --markdown --file f.md` converts markdown to
  native formatting; verify actual content with `docs cat` and styles with `docs structure`; `docs get` is metadata only.
- **Find/replace**: the preferred verb is `docs find-replace` (`docs edit` is an alias on current builds), positionals are
  `<docId> <find> [<replace>]`, docId FIRST; flags (`--account`, `--tab`) go
  before positionals. Check `replacements` is non-zero before assuming the
  edit landed. On multi-tab docs pass `--tab` explicitly — without it the
  search silently covers only the default tab.
- **Full-body rewrite**: `gog docs write --markdown --replace <docId> --file
  f.md` — `--markdown` requires `--replace`/`--append` (it doesn't imply
  where content goes) and must be passed explicitly (a `--replace` without it
  lands plain text silently). `docs update --file` inserts markdown LITERALLY
  (no rendering) — don't use it to push markdown; recreate the doc instead.
- **Multi-tab docs**: `docs write --replace` without `--tab` can delete sibling tabs. Always pass `--tab <id>` from THIS doc's fresh `docs list-tabs`, including for the default tab; current CLI help accepts title or ID but ID is unambiguous. Verify target and siblings after each replace; build sibling tabs first, main last. `--check-orphans` protects anchored reviewer comments; if it blocks, use targeted edits or ask, never bypass it.
- **Docs with images/formatting**: the markdown-recreate flow silently drops
  inline images and rich formatting. Duplicate-then-edit-in-place instead —
  see `references/table-editing-and-shared-doc-pitfalls.md`. For
  shorten/format-preserving asks the default is 100% formatting preservation;
  confirm image count and length before/after as part of the deliverable.
- **Ordered lists**: markdown `1. 2. 3.` renders as bullets or resets to "all
  1s" after conversion. For stable numbered references write the number as
  bold text starting the line (`**1. Title.** body`), and verify after every
  rewrite (`gog docs cat --tab <name> <id> | grep -cE "^[0-9]+\\."` equals the
  item count).
- **`docs get` returns metadata, not body**; there is no one-call full-body
  diff. For a structural rewrite of a plain doc, create a fresh copy and verify it; delete the old document only when replacement/deletion is explicitly within the user's scope.
- `docs write ... --pageless` switches the doc to pageless mode (doc-wide);
  the output prints `pageless\ttrue`.

## Docs: images and diagrams

- `docs insert-image <docId> --file <local.png> --at <placeholder> --width
  <points> --force -j` inserts at a unique placeholder (appends at the end
  without `--at`). Verify the placeholder is gone, the inline count rose, and
  the response has `fallbackLink: false` and `revoked: true` — `--force`
  grants temporary public read; do not leave the image publicly shared.
- For iterative mockup/diagram updates, **replace in place**:
  `docs images list <docId> -j` → `docs replace-image <docId> --object-id
  <id> --file <new.png> --force -j`; require `replaced: true` and
  `revoked: true`, then read back. Docs crops to the old aspect ratio
  (`CENTER_CROP`) — match the old ratio with a clean crop, or add a
  full-height image at a new placeholder. On 400 `problem retrieving the
  image`, retry once, then check `drive ls --query "name = '<name>'"` and
  `drive permissions` to confirm no failed-attempt upload stays public.
- Clickable full-res links under each image: upload the PNG to Drive, grant
  reviewers reader access, insert a markdown link at the image-paragraph
  boundary, then `docs format --match '<label>' --named-style NORMAL_TEXT`
  (insertion can inherit the next heading's style). Insert from the last
  image upward or recompute indexes after every write.
- Mermaid does not render live in Docs — render to PNG (mmdc) and insert the
  image. If the destination renders mermaid natively (e.g. Notion), write the
  fenced block only, stripped of framing text.

## Doc authoring style (this user)

Never put a live secret or an encoded equivalent in a shareable Google Doc; use the secret store and link retrieval instructions instead.

Content/style class rules — code-citation permalinks, bug-handoff reports,
access/credential docs, decision-doc phrasing, long-running tracker structure:
`references/doc-authoring-and-style-rules.md`.

## Sheets

See `references/sheets-cli-patterns.md` for read/write patterns including the
snapshot → diff-only payload → chunked batch-update → full read-back
procedure for conditional bulk column fills, and resyncing mirror sheets.

## Drive

- Verbs: `drive search "<text or Drive query>"` (full-text also matches file
  CONTENTS, so a name can hit a JSON whose filename lacks it),
  `drive ls --parent <folderId>` (not `--folder`), `drive get <id> -j` (name,
  parents, webViewLink — use it to hand back a folder link), `drive download
  <id>` (no `drive cat`; saves to `~/.config/gogcli/drive-downloads/<id>_<name>`
  and prints the path; there is no `--dir`, use `--output <path>` or `mv` the
  printed path; it errors `file exists` if that cache file is already there, so
  reuse the existing file). Cross-account folder copy: download as the owner,
  `drive mkdir "<name>"` + `drive upload <f> --parent <newId>` as the target
  account, verify sizes with `drive ls --parent <newId> -j`. Search results can omit `parents` — use `.get()`
  when parsing.
- Drive-batch jobs (mount-vs-API completeness check, resumable/idempotent
  rewrite loops): `references/drive-batch-operations.md`.
- When the ask is a gdoc as the sole deliverable ("put this in a gdoc"),
  create → insert → verify → delete the local scratch file (and its empty
  parent dir) → hand back the webViewLink, not a summary.

## Gmail

- Thread searches under tight quota, SENT-template pollution, bounce handling,
  and the `.thread.messages[]` JSON shape:
  `references/gmail-issue-thread-searches.md`.

## Google Chat (reading)

- Chat history lives in Google Chat, not Gmail. Gmail only holds sporadic
  chat notification emails, so "nothing new in Gmail" says nothing about
  recent chats. When asked for chats with someone, go straight to `gog chat`.
- DM space: `gog -a <me> chat dm space <their-email> -j` → `.space.name`
  (`spaces/XXXX`). Group spaces: `chat spaces find "<name>"`.
- `chat messages list <space>` returns OLDEST-first and caps at `--max=50`,
  so on a long DM the newest messages are silently missing. For recent
  activity always pass `--order "createTime desc" --max N` (or `--all`).
  Check the newest `createTime` against today before claiming "nothing new".
- JSON shape: `.messages[]` with `sender` as a plain display-name STRING
  (not an object), plus `text`, `createTime`, `thread`.
- `chat messages search` can return zero hits even for terms that certainly
  exist, and `chat spaces list` / `spaces find` can miss spaces the user IS a
  member of. Never conclude "you're not in that space" from them; ask the user
  for the space link. A web URL `chat.google.com/app/chat/<ID>` (or
  `/room/<ID>`) maps directly to `spaces/<ID>` for `chat messages list`.
- Sending: see `references/google-chat-send.md`.

## Unattended status refresh in a commented multi-tab Doc

Keep human prose and comment anchors untouched: unique per-item status
markers, read the tab ID and its comments first, then targeted
`docs find-replace --tab` only when that tab has no comments (require exactly
one replacement + readback). With comments, append a timestamped transition
and verify the readback count of the exact new line increased. Advance a
checked timestamp only after every status write is verified; never full-tab
`docs write --replace` for routine refresh. On local hosts prefer a
deterministic OS-cron script (explicit venv/PATH/HOME, flock, restricted log
perms, tested under `env -i`) over an agent cron, which can report `ok` with
zero tool calls; local-only cron delivers no chat notifications.

## Reviewer comments

The verb is `docs comments list` (`docs comments <docId>` fails). Text is in
`.comments[].content`, anchored passage in `.comments[].quotedFileContent.value`,
replies under `.replies`. `drive comments list/get` also work (plain output
shows `quoted`). When the user says "I left comments" and the newest doc
returns none, check every doc created/edited earlier in the session — the
comments are usually on an older doc.

## Escape hatch: raw API

For metadata not exposed as a first-class verb (e.g. listing a spreadsheet's
tabs), check `gog api list` and call the raw method:

```bash
gog api call sheets v4 spreadsheets.get \
  --params '{"spreadsheetId":"<id>","fields":"sheets(properties(title,sheetId))"}' \
  --account <acct>
```

The returned `sheetId` equals the `gid=` in the tab's browser URL. Use
`--fields` to keep the response small. See also
`references/raw-docs-api-via-exported-token.md` and
`references/gmail-thread-id-resolution.md` for deeper escape-hatch patterns.

Other reference files: `references/multi-tab-doc-editing.md`,
`references/checking-workspace-edition-without-admin-access.md`,
`references/unconfirmed-user-edit-claims.md`,
`references/google-chat-send.md`, `references/gmail-web-link-no-context.md`,
`references/iterative-review-cycles-live-edits-and-comments.md`,
`references/index-based-edit-and-style-drift-pitfalls.md`.
