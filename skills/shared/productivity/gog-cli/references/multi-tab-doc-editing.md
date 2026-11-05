# Editing a specific tab in a multi-tab Google Doc

Use CLI-native tabs first; raw Docs API only for missing operations. Current `gog docs write --help` says `--tab` accepts a title or ID; prefer a fresh ID from this document. Never reuse an ID from another doc.

1. `gog -a <acct> docs list-tabs <docId> -j` (also `docs tabs list`); verify each tab's contents with `docs cat <docId> --tab <id>`.
2. `docs add-tab <docId> --title "<title>" -j` returns the new ID. `rename-tab` and `delete-tab --force` exist; re-list after each edit.
3. `docs write <docId> --replace --markdown --check-orphans --tab <fresh-tab-id> --file <path>` for full-tab rewrites. Omitting `--tab` on default can erase siblings. If `--check-orphans` blocks, don't disable it: use `find-replace --tab` on a unique marker, or ask to resolve comments.
4. Build sibling tabs before main. After each replacement, re-list tabs and read back target and siblings. Check `docs structure -j`: markdown rendering can be flat or inherit bullets.
5. A terminal newline may retain the old last paragraph's bullet preset and make all replacement paragraphs bullets. End markdown with an ordinary non-bullet paragraph; if affected, clear bullets in the scoped tab via raw Docs batchUpdate, retry and verify structure.

## Raw Docs API fallback

Export a token only to a private process environment (see `raw-docs-api-via-exported-token.md`); never print it. GET `https://docs.googleapis.com/v1/documents/<id>?includeTabsContent=true`, then inspect `tabs[].tabProperties.tabId` and `tabs[].documentTab.body.content`. Otherwise non-default tab content may be missed.

For `insertText`, `deleteContentRange`, `updateParagraphStyle`, put the target `tabId` in every `location`/`range`; omission writes to default tab. Compute indices from `docs structure -j` or the insert response, exclude terminal newline from deletes, and verify target text and anchored comments after each request. See `index-based-edit-and-style-drift-pitfalls.md` for precise section edits.

Read the actual contents before editing a tab with a plausible title: it may have been repurposed. If title lookup fails, re-list THIS doc's tabs, use ID, and retry without an unnecessary `--client` before chasing auth.
