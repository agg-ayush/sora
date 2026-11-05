# Model Alias Troubleshooting

Governs: diagnosing and fixing a Hermes model switch that silently lands
on the wrong model, and adding/correcting `model.aliases` entries.

## The silent-fallback failure mode

A `/model <name>` switch (or a user asking in chat to switch) that isn't
an exact match for a defined alias is NOT rejected with a clear error —
it gets passed to the provider literally as the model string. If the
provider doesn't recognize it (typo, extra/missing character, wrong
separator, wrong `p`-for-`.` convention), the API call 404s and the
runtime auto-falls-back to the next entry in `hermes fallback list`,
often on a completely different provider. The conversation keeps
responding normally — nothing user-visible breaks — so the requested
model is silently NOT the one actually serving the chat.

**Diagnosis:**
- Check `~/.hermes/logs/agent.log` for the line `Fallback activated:
  <requested> → <actual> (<provider>)` — this is the definitive signal
  of what model is actually serving the conversation right now, not what
  was asked for.
- A repeated `API call failed ... error_type=NotFoundError ... Model not
  found, inaccessible, and/or not deployed` for the same model string
  right before a `Fallback activated` line confirms the alias never
  resolved — it was sent to the provider as a raw (wrong) model ID.
- Don't trust a model name carried over from earlier in the conversation
  as ground truth for "what's active now" — a later system runtime
  metadata message, or a fresh `hermes doctor`, is the source of truth,
  and even that can just be reporting the fallback target.

**Fix:**
- List the real aliases: `hermes config get model.aliases` or read the
  `model.aliases` block in `~/.hermes/config.yaml` directly. Switch to
  the exact existing key — don't guess a shortened/lengthened variant of
  the model's marketing name (e.g. provider naming conventions like
  `p` standing in for `.` in a version number are easy to get wrong,
  and "flash"/"fast"/"mini" suffixes are easy to add or drop by mistake).
- If the user's preferred short name genuinely isn't defined yet, add it
  as a new `model.aliases` entry (mapped to the correct full provider
  model path) instead of repeatedly retrying variations of the typo.
- After fixing, confirm the fix actually took: the next turn's runtime
  metadata should name the intended model/provider, and `agent.log`
  should show no further `Fallback activated` line for that alias.
