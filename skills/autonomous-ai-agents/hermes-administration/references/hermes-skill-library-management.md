---
name: hermes-skill-library-management
description: "Audit, prune, and grow the set of enabled Hermes skills — cross-reference enabled/disabled state against usage telemetry and the bundled+optional catalogs, then apply changes via the correct non-interactive mechanics. Use whenever asked to audit skills, find dead-weight/unused skills, disable skills, or install/enable skills from the catalog."
version: 1.0.0
author: agent
metadata:
  hermes:
    tags: [hermes, skills, config, audit, cli]
    related_skills: [hermes-agent, hermes-agent-skill-authoring]
---

# Hermes Skill Library Management

Governs the class of task: "review what's enabled/disabled in the Hermes
skill library, decide what to keep/cut/add, and apply it." This is
distinct from `hermes-agent-skill-authoring` (writing a SKILL.md's content)
and from the bundled `hermes-agent` skill (general Hermes reference).

## Workflow: auditing the library

Cross-reference three sources before recommending any change:

1. **Enabled/disabled state** — `hermes skills list` (or read
   `skills.disabled` in `~/.hermes/config.yaml` directly).
2. **Usage telemetry** — `~/.hermes/skills/.usage.json` holds per-skill
   `use_count`, `view_count`, `patch_count`, `last_activity_at`. Zero
   `use_count` + old/absent `last_activity_at` is the strongest "not useful
   to this workflow" signal — much stronger than guessing from the name.
3. **Full catalog** — the bundled catalog (`hermes skills list` shows all
   installed, enabled or not) plus the **optional** catalog documented at
   the Hermes skills-catalog docs page (skills not even installed yet).
   Cross-reference against the user's actual recurring work (check
   `skills_list()` categories already in heavy use, past session topics)
   to find "useful but missing" gaps.

Present findings as three buckets: enabled-but-unused (candidates to
disable), useful-but-missing (candidates to install), and healthy/keep.
Let the user pick per-item rather than applying a blanket cut — people
often want to keep a skill for a stated future use even at zero telemetry.

## Applying changes — mechanics and pitfalls

**`hermes skills config` is interactive-only.** It takes zero CLI args/flags
— running `hermes skills config --disable <name>` or similar fails with
`unrecognized arguments`. There is no non-interactive disable/enable
subcommand. To change enablement non-interactively, edit
`~/.hermes/config.yaml`'s `skills.disabled` key directly.

**`skills.disabled` MUST be a YAML list, not a string — this is the #1
pitfall.** `hermes config set skills.disabled "a,b,c"` (comma-joined
string) reports `✓ Set skills.disabled = a,b,c` and looks like it worked,
but it writes the value as a raw YAML **string**, not a list. The skill
loader expects a list; a string value silently fails to disable anything
(no error surfaces at set-time — you only discover it by checking the
type afterward). Correct approach:

```python
import yaml
p = '/Users/ayush/.hermes/config.yaml'   # confirm actual path via `hermes config path`
d = yaml.safe_load(open(p))
d['skills']['disabled'] = ['skill-one', 'skill-two', 'skill-three']  # real list, not comma string
yaml.safe_dump(d, open(p, 'w'), default_flow_style=False, sort_keys=False)
```

Always verify the type after writing:
```bash
python3 -c "import yaml; d=yaml.safe_load(open('/Users/ayush/.hermes/config.yaml')); v=d['skills']['disabled']; print(type(v).__name__, len(v))"
```
Expect `list N`, not `str`.

**Config file location**: don't assume a named profile's config lives
under `~/.hermes/profiles/<name>/config.yaml` — that file may not exist.
`~/.hermes/config.yaml` (the base file) can be the one actually governing
the active profile. Check with `hermes config get skills.disabled` and
confirm the returned value's file with `hermes config path` before editing
— don't guess which file to touch.

**`hermes skills install official/<category>/<name>` prompts an
interactive y/N confirmation** with no `--yes`/`-y` flag observed. Pipe
confirmation to make it non-interactive:
```bash
echo "y" | hermes skills install official/<category>/<name>
```
The `<category>/<name>` path matches the category shown in the optional
skills catalog docs (e.g. `devops/docker-management`,
`software-development/code-wiki`).

**Verification step (don't skip):** after any batch of disables/installs,
re-run `hermes skills list` and grep for the exact names touched, checking
the `enabled`/`disabled` column directly — don't trust the `config set`
success message alone, since it can mask the string-vs-list bug above.

## Reference

Full transcript of a real audit-and-apply pass (disable list, install
list, the string-vs-list bug caught mid-session and fixed) is in
`references/audit-session-example.md`.
