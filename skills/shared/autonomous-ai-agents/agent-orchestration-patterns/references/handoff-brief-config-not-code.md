# Handoff briefs must name config-vs-code boundaries up front

## The pattern
A hardcoded deployment-specific identity/contact literal (bot account email, webhook URL,
notification destination) can be missed by generic static checks and review. A configured
Semgrep rule may catch it; never treat automated gates as a substitute for an explicit
config-versus-code review. Credentials go in an authorized secret store, deploy-time values
in configuration, and genuine application constants can remain in source.

## What to do
When a task's raw description involves wiring a new external account/identity into an
integration (adding a bot as a meeting attendee, pointing at a notification target, adding
a webhook), the Tier-1 handoff brief to T2 must say up front: "read this value from an env
var / config, never hardcode it in source" — including when the value used for initial
testing is a real, known-safe value (e.g. the developer's own account substituting for a
not-yet-provisioned service account). Stating this in the brief costs one sentence; catching
it after the PR is already up costs a full review round-trip (a human reading the diff and
asking "why is that inside code, shouldn't it be a secret or variable").

## Reviewing after the fact
When reviewing a new external integration, inspect literal
emails/URLs/IDs/phone numbers for whether they are credentials, environment-specific
configuration, or intended constants; use configured static checks where available,
but manually verify the classification. Treat it as a standing checklist item on
integration-touching diffs, the same way you'd check for missing tests.
