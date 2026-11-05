# UI preferences

Standing design preferences for every screen this flow builds. They rank below the user's explicit brief for the current task and above PRODUCT.md, DESIGN.md and the advice of the individual style skills.

Each item has an id. The shape brief must say how the screen meets the items that apply, and the review phase checks every item as pass, fail or not applicable.

## P1. No overloaded pages
One page does one job. When a screen collects unrelated information or several workflows, split it into separate linked pages instead of stacking everything into one view.

## P2. Clear action hierarchy
The few primary actions on a screen are prominent calls to action. Everything else is present but visually quiet. Actions that are siblings (two ways to reach the same goal, such as creating something new versus linking something existing) get equal visual weight; one must not look like a footnote to the other.

## P3. Little scrolling, few clicks
- Use the available horizontal space: columns, grouped sections and dropdowns before long full-width rows.
- Open on a compact summary of the defaults with an edit control per section, so the common case takes one action and unusual cases expand only the part they change. The summary stays visible next to the primary action.
- Highlight the options people change often; tuck rare or advanced options into dropdowns or collapsible groups.
- Every capability stays reachable. Simplicity comes from layout and defaults, never from removing options.

## P4. Consistent controls
- Dropdowns, pickers and date controls share one visual language. No native browser `<select>` or native date input styling that looks foreign to the rest of the interface; use a styled custom control with full keyboard support.
- Inline edits use a small edit affordance (a pencil icon) that opens the field in place, not a separate always-visible input or a heavy button.

## P5. Disabled controls explain themselves
- A control that cannot be used right now is shown disabled (use `aria-disabled`, not the `disabled` attribute, so it stays focusable) with a short reason.
- The reason is reachable on hover, keyboard focus and tap.
- The wording is professional and specific, and says when the limit comes from another system rather than this product (for example "This can't be edited after the order is submitted. The payment provider locks it once created.").

## P6. Every state is designed
Loading, empty, error, partial, disabled and success states are designed, not left as bare text. An empty state says what the area is for and offers the next useful action.

## P7. Unambiguous labels
- No two sections or fields on one screen share a label.
- Every input that sends something says where it goes and who will see it (for example "internal note, visible to your team only" versus "message emailed to the customer").
- Use the product's own words; no internal codes, ids or system jargon in visible copy.

## P8. Facts only, nothing hidden
- Show what is known for certain. Do not guess or infer facts the data does not state (for example do not derive a person's name from an email address, or guess which party a person belongs to).
- A summary or roll-up must never hide an individual item; when several items share a parent, each one stays visible with its own state.
- Activity is phrased as what happened and what it means ("viewed 2 days ago, no reply yet"), not as raw system event names.

## P9. Links go to the exact place
A link to another system opens the specific record it refers to, never that system's home page. If no specific target exists, say so in the label.

## P10. Plain, minimal copy
Plain language, short sentences, no marketing tone. Show only what the reader needs to act; if removing a detail would not change what they do, remove it. The same applies to generated content such as documents and emails.

## P11. Proportional sizing
- Size with relative units: `rem`, `em`, `%`, `fr`, `ch`, viewport units or `clamp()`. This covers widths, heights, control heights, spacing, gaps and type.
- Fixed `px` is acceptable only for hairline detail: 1 to 2 px borders, outlines, focus rings, dividers and shadows.
- Use the full width on large screens (check at 1440 and 1920 wide) instead of a narrow centred column with empty margins, while keeping line length readable for prose.

## P12. Mockups stay plain
For mockups, concepts and throwaway comparisons, use minimal styling (white background, simple borders, grey text) unless polish is explicitly requested. Visual polish belongs to the real build.
