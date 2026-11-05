"""Fallback text/notes extractor for .pptx reference decks.

Use when `python -m markitdown file.pptx` fails to extract pptx text (the
'pptx' extra isn't always present on markitdown installs — pip may warn
"does not provide the extra 'pptx'" and the command then emits nothing).

Setup:
    python3 -m venv /tmp/pptxenv
    /tmp/pptxenv/bin/pip install -q python-pptx

Usage:
    /tmp/pptxenv/bin/python dump_pptx.py file1.pptx [file2.pptx ...]

Prints shape text, table cells, image placeholders, and speaker notes per
slide — everything needed to read a batch of reference/competitor decks for
structure and content before drafting your own (see SKILL.md,
"Eliciting personal/narrative deliverables").
"""
import sys
from pptx import Presentation

for f in sys.argv[1:]:
    print("=" * 78)
    print("DECK:", f)
    print("=" * 78)
    prs = Presentation(f)
    for i, slide in enumerate(prs.slides, 1):
        print(f"\n--- SLIDE {i} ---")
        for shape in slide.shapes:
            if shape.has_text_frame:
                t = shape.text_frame.text.strip()
                if t:
                    print(t)
            if shape.has_table:
                for row in shape.table.rows:
                    print(" | ".join(c.text.strip() for c in row.cells))
            if shape.shape_type == 13:
                print("[IMAGE]")
        if slide.has_notes_slide:
            n = slide.notes_slide.notes_text_frame.text.strip()
            if n:
                print("[NOTES]", n[:600])
    print()
