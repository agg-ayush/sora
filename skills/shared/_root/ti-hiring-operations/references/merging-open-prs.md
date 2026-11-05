# Merging open PRs

The standing auto-merge for this repo covers only PRs produced by our own cards or asks.

1. Before merging anything from the open list, match each PR to a card or an explicit ask from the session (card metadata `published_pr`, branch name, PR body).
2. List unmatched PRs separately as "not ours" (editor tweaks, snapshot re-bakes, dependabot, stale smoke PRs) and leave them alone unless the user names them. "Merge em" means our PRs, never the whole open list; merging someone else's PR can't be cleanly undone.
3. For ours: confirm exact-head CI green and `mergeStateStatus` CLEAN, then merge without asking.
4. When reporting "is everything done", separate flow PRs (merged) from non-flow open PRs, and ask about non-flow ones instead of offering to merge them by default.

## UI preview gate (default, not on request)

Any card that changes what the user sees in the wrapper (copy, layout, error screens, palette) carries a show-before-merge gate by default: the worker pushes the branch, serves it locally (or posts screenshots of every affected screen), and the PR waits for the user's sign-off. Put the gate in the card body at creation time for every UI card, including follow-ups spun off an earlier gated card; standing auto-merge does not override it, because a UI PR that merges while the user is still testing it can't be reviewed in context.

- Never merge a PR the user is actively testing locally, even when it goes green.
- Backend/orchestrator cards stay on standing auto-merge.

## Parallel deliverables are not dropped when un-gated

When the user says a side deliverable (RCA doc, writeup) should not block a merge, it still has to exist. Before accepting the card as done, check the deliverable landed; if the worker closed the card on the merge alone, write it yourself right away instead of asking whether to. RCA shape and workflow: `references/rca-docs.md`.
