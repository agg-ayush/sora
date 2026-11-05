---
name: architecture-diagramming
description: Use when drawing ownership/architecture diagrams for Ayush.
---
# Architecture diagramming for Ayush

## Tooling
- Use **d2** (`d2 --layout elk file.d2 out.png`), not mermaid. Mermaid's auto-layout tangles edges on anything with >2 subgraphs and crossing flows; d2+elk lays out cleanly with minimal fighting.
- Google Docs does not render mermaid or d2 natively — always render to PNG and embed the image (`gog docs insert-image <docId> --url <driveShareUrl>`), or upload to Drive and share the link.
- Google Docs rejects images wider than ~2000px inline. Use `direction: down` (vertical stack) in the d2 file so the render stays narrow and full-resolution instead of a wide strip that has to be downscaled into blur. `d2 --scale 0.4-0.5` after switching to vertical layout usually lands under the width cap while staying crisp.

## Ownership clarity (the recurring gap)
When a diagram spans two owners/teams (e.g. Ayush's module vs a collaborator's), an unlabeled shared box (like an API contract) floating between them reads as ownerless. Fixes that actually work:
- Color-code every box to match its owner's established color (e.g. blue = Ayush, green = collaborator) — including boxes that represent a *contract* or *seam*, not just components.
- Put the owner's name directly in the box title/subtitle ("CONTRACT A — scheduling · admin — AYUSH owns this"), don't rely on color alone.
- If a contract/seam has split ownership (webapp side vs backend side), say so explicitly in the label rather than picking one color.
- Split a single overloaded contract into separate boxes when it mixes concerns (e.g. admin/scheduling calls vs live-session calls) — ask the user which split they want before merging concepts that don't share a lifecycle.

## Workflow discipline
- Don't hand-roll diagram layout fixes indefinitely. If mermaid keeps tangling after 2-3 attempts, stop and switch tools (search for/install a proper diagramming CLI like d2) rather than continuing to patch text positions.
- Iterate one fix at a time against explicit user feedback ("still not clear", "add X") — regenerate, re-screenshot via vision_analyze, confirm before moving to the next fix. Don't batch multiple structural changes without checking the intermediate render.
- Before calling a diagram final, do an explicit audit pass: ask vision_analyze targeted questions like "is ownership unmistakable", "are all edges/directions correct", "any remaining tangles or ambiguity a fresh reader would hit" — don't just eyeball it yourself.
- Ground every arrow/data-label in actual code (read the real request/response shapes, actual field names) before drawing it — never invent plausible-looking API contracts. Mark new endpoints and return shapes **PROPOSED**, separate from deployed routes.
- For sequence diagrams use D2 `shape: sequence_diagram` and verify event order programmatically as well as visually (assert `src.index(a) < src.index(b)` on the .d2 source for every gate, plus negative asserts like `'infra -> postgres' not in src` for boundary claims). An event that satisfies a gate must precede the gate read and Continue action, and a destructive step (destroy/delete) must follow an acknowledged durable write, not just a request for one. Keep alternative retry/error branches explicitly conditional (group them under an `alt`-labelled frame) rather than drawn inline after the happy path, where they read as mandatory steps.
- Before calling a sequence diagram done, list every decision settled in the conversation (including side remarks like "those comments get sent to X") and trace each user-produced artifact to its final store: every artifact needs a drawn path from origin to sink (e.g. candidate concern -> orchestrator -> DB -> Drive folder), and the accompanying contract text must name the same endpoint and ack semantics. A diagram that stops at the UI action misses a sink the reader expects.
- Draw a timeout as a caller-side note/self-message ("no response within Ns"), never as a return arrow from the callee: a return arrow claims the callee answered, which conflates an error response with silence.
- When a diagram answers a boundary objection from a reviewer ("module X should not touch the DB/Recall/Drive"), make the boundary provable from the picture: every call into the constrained lane comes from the owning orchestrator, the lane itself only calls its own provider, and any owner/deployment label is present on EVERY lane (including third-party ones), not just the internal ones. Same-service module boundaries are fine when the objection is testability; say "one deployed service, separate HTTP module" explicitly.
- A single 7-9-actor sequence becomes too wide and tiny inside a Google Doc. Split by lifecycle phase, embed overview PNGs below ~2000 px wide and provide full-resolution Drive links for reading the endpoint labels. Verify both inline image count and link readback. Do not publish a diagram whose labels are unreadable at doc width without full-resolution links.
- Publishing a diagram-plus-contract doc to Google Docs: follow `references/google-doc-publishing.md` (placeholder markers, insert-image at marker, permission check, readback).
- Render with the `d2` CLI directly in the foreground (sub-second). Do not hand diagram edits to a background coding-agent process: it stalls silently and the user notices before you do. If an edit needs reasoning, make it yourself in the .d2 file and re-render.
- Clean up stale intermediate renders (local scratch files, old Drive uploads) once a version is superseded — don't leave 5 generations of the same diagram floating on Drive.
