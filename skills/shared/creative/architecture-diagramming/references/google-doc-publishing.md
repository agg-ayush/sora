# Publishing a diagram doc to Google Docs (gog)

Order matters; each step verifies before the next.

1. Write the contract/explainer as markdown in scratch. Put a unique placeholder line where each diagram goes (e.g. `SCHEDULING_SEQUENCE_IMAGE`, `TEARDOWN_SEQUENCE_IMAGE`). Mark proposed endpoints PROPOSED inline; no "draft under revision" banners in what gets sent.
2. Render two PNGs per panel: an inline one (`d2 --layout elk --scale 0.4 ...`, target < ~2000 px wide) and a full-resolution one (no scale) for reading labels.
3. Upload full-res panels: `gog --account <acct> drive upload <png> --name '<title>.png' -j`; keep the returned file ids.
4. Create a NEW doc from the markdown: `gog --account <acct> docs create '<title>' --file <md> -j`. Never full-replace an existing doc that has reviewer comments (it orphans them).
5. Read back with `gog --readonly docs cat <docId>` and assert every placeholder and key endpoint string is present.
6. Insert each inline image at its marker: `gog docs insert-image <docId> --file <png> --name <n>.png --at <PLACEHOLDER> --width 290-310 --force -j`. It temporarily makes the uploaded image anyone-with-link and revokes after insert; confirm `"revoked": true` in the output.
7. Append a "Full-resolution sequence diagrams" section with the Drive view links (`docs insert --tab 'Tab 1' --markdown --file -`).
8. Final verification: Docs API `documents.get` with `includeTabsContent` and count `inlineObjectElement`s == number of panels; placeholders gone; `drive permissions <id>` on the doc and every image shows no `anyone`/`domain` grants.
9. Tell the user the doc and images are private to them and must be shared with the recipient; do not share on their behalf.

When a design decision changed in the same session, also patch the decision/tracker doc tabs with `docs find-replace --tab <tab>` after asserting the old string occurs exactly once, then read back.
