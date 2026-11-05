---
title: Memory consolidation — over-pruning pitfalls
---

# Over-pruning during in-place memory compaction

Extends `hermes-memory-hygiene.md`'s "Compacting without migrating"
section. When asked to consolidate a memory store ("remove temporal
info, something no longer needed"), two categories look like transient
task-state but are NOT — dropping them is a real information loss, not
cleanup, and the user will catch it immediately.

## The two false-positive categories

1. **Tool/environment gotchas.** A config key with surprising behavior,
   an unscoped find/replace footgun, a provider quirk discovered while
   debugging something else. These read as "specific to one incident
   that's now over" but they are durable — the same tool will misbehave
   the same way again next time it's used. Test before dropping: "will
   this exact trap bite again regardless of which task is active?" If
   yes, keep it, but in the right place: if a skill loads for the
   task that uses that tool, move the gotcha into that skill. If config
   or code now makes it moot (the key is at its safe value, a launcher
   enforces it), drop it. Only cross-task gotchas stay in memory.

2. **A named project's standing identity block.** Repo name,
   stakeholders, proxy/approval chain, tracker-doc absolute path,
   recurring process/writing bugs specific to that project's artifacts.
   This is NOT the same as that project's live task status (current PR
   number, "currently fixing X", in-flight migration state — that part
   IS transient and should be dropped). Identity facts stay durable for
   the life of the project engagement; only the moment-to-moment status
   goes stale.

Live incident: a consolidation pass ("remove temporal info") dropped
both a tool gotcha (a compaction-related config trap) and an entire
project's identity block (stakeholders + tracker path + known
writing-process bugs) as "temporal project state." User caught it twice
in the same session — first "arent those generic? and project state is
needed", then after a restore attempt still asked "idk what you cut
pal" because the removal list wasn't surfaced up front.

## Fix

- Before finalizing a compaction batch that removes more than 2-3
  entries, list what's being cut in the reply — don't just report the
  before/after percentage. Cheaper to summarize proactively than to have
  the user ask "what did you cut" and have to reconstruct the diff from
  memory.
- Apply the two tests above to each candidate removal, not just "does
  this mention a specific project/incident" — mentioning a project or
  incident doesn't make an entry transient if the fact itself is a
  standing identity/gotcha rather than a status update.
