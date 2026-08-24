# Worked example: full audit-and-apply pass

Real session outcome (Aug 2026), kept as a concrete before/after reference.

## Disabled (enabled but zero telemetry, no fit to actual workflow)

evaluating-llms-harness, serving-llms-vllm, weights-and-biases,
segment-anything-model, jupyter-live-kernel, llm-wiki,
research-paper-writing, pretext, comfyui, design-md, humanizer, himalaya,
simplify-code, pptx-measured-design, petdex

(plus a pre-existing disabled set already in config — airtable,
apple-notes, apple-reminders, arxiv, ascii-art, ascii-video,
audiocraft-audio-generation, baoyu-infographic, blogwatcher, excalidraw,
gif-search, heartmula, huggingface-hub, imessage, llama-cpp, manim-video,
maps, obsidian, opencode, openhue, p5js, polymarket, songsee,
songwriting-and-ai-music, teams-meeting-pipeline, touchdesigner-mcp,
youtube-content, yuanbao)

## Kept despite zero/low telemetry (user said "might use" / "core")

popular-web-designs, node-inspect-debugger, python-debugpy,
hermes-desktop-plugins, ocr-and-documents, findmy — user explicitly wanted
these retained even though usage was 0-1. Lesson: don't auto-disable on
telemetry alone, always let the user veto per item.

## Installed from optional catalog (not previously installed)

```
echo "y" | hermes skills install official/devops/docker-management
echo "y" | hermes skills install official/devops/watchers
echo "y" | hermes skills install official/software-development/rest-graphql-debug
echo "y" | hermes skills install official/software-development/code-wiki
echo "y" | hermes skills install official/research/duckduckgo-search
echo "y" | hermes skills install official/communication/one-three-one-rule
echo "y" | hermes skills install official/software-development/subagent-driven-development
```

## The bug caught mid-session

```bash
# WRONG — writes a comma-joined STRING, not a YAML list. Reports success but silently no-ops.
hermes config set skills.disabled "a,b,c,d"

# Verify with:
python3 -c "import yaml; d=yaml.safe_load(open('/Users/ayush/.hermes/config.yaml')); print(type(d['skills']['disabled']))"
# <class 'str'>   <-- wrong, should be <class 'list'>

# FIX — rewrite as a real YAML list:
python3 -c "
import yaml
p = '/Users/ayush/.hermes/config.yaml'
d = yaml.safe_load(open(p))
d['skills']['disabled'] = ['a', 'b', 'c', 'd']
yaml.safe_dump(d, open(p, 'w'), default_flow_style=False, sort_keys=False)
"
```

Final verification pattern — grep the touched names directly out of
`hermes skills list` output and check the enabled/disabled column, rather
than trusting `config set`'s own success message.
