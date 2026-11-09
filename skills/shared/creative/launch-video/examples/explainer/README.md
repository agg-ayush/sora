# Explainer reference snippets (~100s, only on request)

Reference material for the longer explainer style (nine scenes, 15-frame fades, soft music). These files are **not a runnable project**: they import `apps`, `theme`, `icons` and the scene helpers from `../../templates/src/`. Copy what you need into your project's `src/`.

| File | What it is |
|---|---|
| `Launch.explainer.tsx` | Scene table + VO placement + music ducking for the 9-scene, 15-frame-fade timeline |
| `scenes-new.tsx` | Hook (UI click-counting problem), "what if" pivot, intro logo reveal, agent "web strands" scene |
| `scenes-b.tsx` | Chat with tool-call chips, product card + typewriter, third-party setup walkthrough, outro |
| `scene-consolidate.tsx` | Before -> Now: dashed half-built cards pulled into one solid card |
| `kit.tsx` | Full kit including the pieces dropped from the default template: `McpKnot`, `Clawd` mascot, `Person`, `ClaudeMark`, `GoogleG`, `NightBg` |
| `claude-path.ts`, `openai-path.ts` | Brand-mark SVG paths (Simple Icons) used when the explainer is about MCP clients |
| `vo.json` | The explainer's 16-line script, as a pacing reference (217 words) |

The default template's `audio-tools/` (TTS, transcription, SFX) is shared; use its `make_vo.py` with this `vo.json`.
