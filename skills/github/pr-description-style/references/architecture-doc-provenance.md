# Extending PR-description-style rules to architecture/integration docs

The same Exclude-list logic in SKILL.md ("no internal workflow narrative")
applies to any technical document written for another team/dev to read —
architecture references, integration guides, component READMEs — not just
PR bodies.

These documents describe **what the system is and how to use it**, never
**who wrote which part or where it came from internally**.

Strip:
- Authorship/provenance attribution for internal contributors — "vendored
  from the QC dev's standalone file", "written by X", "the other dev's
  validator". State what the component/file *does* instead: "the
  content-compliance validator: description match, label checks, vision
  layer..." The reader doesn't need to know which colleague produced which
  file.
- The same internal-workflow narration excluded from PR bodies (review
  rounds, iteration history, which agent/session built it).

Keep: genuine external lineage that affects how the reader should treat the
artifact — open-source license attribution, "this API is third-party and
rate-limited", a named upstream project the reader would need to track for
updates. Same line as PR lineage: keep what a reader needs to use the
system correctly, drop who-did-what-internally.

## Real example (script-image-gen ARCHITECTURE.md / QC-CHANGES.md, Aug 2026)

A generated architecture doc described `svg_validator.py` as "the vendored
content validator (from the QC dev's standalone file)". User flagged it
immediately: "why are you telling internal random references inside the
architecture?" Fix: rewrote to "the content-compliance validator (static
checks + vision layer)" — content and behavior only, provenance dropped
entirely. Same fix applied to a second occurrence in the same file that was
missed on the first pass — check the whole doc for the pattern, not just
the first hit.
