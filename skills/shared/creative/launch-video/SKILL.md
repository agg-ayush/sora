---
name: launch-video
description: "Use when asked for a demo, launch, promo or stakeholder video of a product or feature. Builds a short animated Remotion video with voiceover, music and SFX."
version: 2.0.0
author: investor
license: MIT
metadata:
  hermes:
    tags: [video, demo, launch, promo, stakeholder, remotion, animation, voiceover, music]
    adapted: "Adapted from investor's launch-video skill: generic template, TrueFoundry voice and transcription, bundled CC BY music, one project template."
---

# launch-video: short, punchy, fully animated product videos

Paper-style, code-animated (Remotion) demo, launch or stakeholder videos with Gemini voiceover (via TrueFoundry), a royalty-free music bed and synthesized SFX. Every frame is drawn in code: no screenshots, no screen recording.

## 0. Pacing: short and punchy by default

The brief that works: "short and punchy, so it should show what is launched and how it can help you in a quick manner with fast animations and transitions, it should not feel slow." It holds attention and gets the idea across fast. **Build every video this way unless a longer explainer is explicitly asked for.**

| | Default (the target) | Explainer (too slow) |
|---|---|---|
| Length | 47.1s | 101.5s |
| Scenes | 6 | 9 |
| VO lines / words | 8 / 118 | 16 / 217 |
| VO coverage | 39.5s of 47.1s (84%) | 75.2s of 101.5s (74%) |
| Speech rate | 2.99 words/s | 2.89 words/s |
| Transitions | 10-frame slide/wipe + whoosh | 15-frame fades |
| Music | ~115 BPM, punchy | ~100 BPM, soft piano |

The pace comes from **structure, not faster speech**:
- **Aim for 40-60s.** One idea per scene, one VO line per beat. Cut anything that doesn't show what shipped or how it helps.
- **Open on a hook, not a build-up.** A 5s problem hook (customer-voice messages popping in + one VO question). Product title on screen by ~5s.
- **No silent holds.** Keep VO near-continuous (>=80% coverage). The gap between lines is the time one camera move or click takes.
- **Fast motion (@30fps):** transitions 10 frames; camera moves 12-16; opening hold 12-14; cursor travel 13-25 per keyframe; pop-ins ~9; the 3D flip 26.
- **Show, then move on:** zoom to the control, click, show the result, cut. Schedule actions on `silencedetect` phrase starts so the picture lands with the words.
- **Upbeat music bed**, ducked under the voice (§4). "Calm, editorial" in §1 describes the **look**, not the pace.

## When to use
- "Make a demo / stakeholder / launch / promo / announcement video" for a feature or product.
- Editing or extending a video built this way.

## Layout

- `templates/`: the one default project (Remotion 4.0.290, React/TS, ~47s). Helpers worth reusing: `src/cam.tsx` (`Cam` with log-space zoom, `fit(rect)`, `WorldCursor` drawn in screen space so it doesn't grow with zoom, `Sfx`), `src/dash.tsx` (anchors via `world()`/`worldRect()`), `src/apps.tsx` (look-alike windows with named anchors), `src/kit.tsx` (`Camera`, `Cursor`, `Words`, `Caret`, `LogoMark`), `src/theme.ts`.
- `templates/src/scenes.json`: the **single scene table** (ids, frame lengths, VO placement, transitions, music file and drop). `Launch.tsx` and `tl.mjs` both read it; add a scene by adding a row and a component in `Launch.tsx`'s `COMPONENTS` map.
- `templates/audio-tools/`: `make_vo.py` + `gemini.py` (TrueFoundry TTS, transcription, mix review), `sfx.js`, `music_drop.py` (beat-snapped, optionally audio-verified drop times), `check_mix.py` (final-render audio check), `vo.json` (the script).
- `templates/public/music/`: three bundled CC BY tracks with beat cues and a README (credit line!).
- `examples/explainer/`: reference snippets for the ~100s explainer (scenes, kit extras, 16-line script). Not a runnable project; read `README.md` there.

## Quick start
```bash
cp -R <this-skill-dir>/templates <newdir> && cd <newdir>
npm install && git init && git add -A && git commit -m v0
python3 audio-tools/make_vo.py --silent    # silent stand-ins so it previews before the voice exists
node audio-tools/sfx.js                    # synthesized SFX -> public/sfx
node stills.mjs 60 300 600                 # stills -> out/s/<frame>.png (review with vision)
node tl.mjs                                # VO timeline + spill check
# edit audio-tools/vo.json (script), then record + verify every line:
python3 audio-tools/make_vo.py
npx remotion render src/index.ts Launch out/video.mp4 --concurrency=8 --crf=16 --audio-bitrate=256k
```
Needs Node, Python 3 (3.9+, stdlib only) and `ffmpeg`. `public/vo/durations.json` ships with the sample timings so the project compiles before you record; `make_vo.py` overwrites it. Re-run `node tl.mjs` after any change to lengths or VO.

**Adapting it:** replace the sample product ("Product", "Help desk", Dana/Alex tickets) in `scenes.tsx`, `views.tsx`, `dash.tsx`, `helpdesk.tsx`, `apps.tsx` and `vo.json` with the real product, keeping the helpers and style. `public/logo.png` is a placeholder and `LogoMark` in `kit.tsx` is a neutral brand tile; swap in the real logo (§1). Change `C.primary` in `theme.ts` to the product accent.

## 1. Style rules (apply from the first draft)

Calm, editorial, precise "paper-style infographic". That is the look; the pacing is §0.

- **Light paper background everywhere.** Off-white `#f4f2ed` with faint mottling, rendered ONCE to `public/paper.png` (`src/PaperTexture.tsx`, composition `PaperTexture`; regenerate with `npx remotion still src/index.ts PaperTexture public/paper.png --frame=0`). **Never** dark backgrounds, gradients, glow blobs or neon.
- **Typography:** serif headlines (Source Serif 4, 600-700), Inter for UI/body, JetBrains Mono for code/URLs. Each section heading has a short coloured **accent bar** above it; a small tracked-uppercase **running head** top-right.
- **Cards:** flat, white/`#fbfaf7`, 1.5px dark hairline border, soft low shadow. Dashed borders for "old/incomplete", solid for "the new thing".
- **Not kid-like.** No cartoon people, confetti, bouncy emoji or rainbow colours. Success = a calm check / ring pulse + soft chime.
- **Show the real product as a recognisable look-alike** (nav, tabs, tables, thread, sidebar fields, logo). When the video is about information (tiles, wait times, chips), use **real UI labels with fictional tickets, people and counts** (shimmer placeholders make zoom-ins meaningless) and say so in the report. Keep shimmer for secondary content. Use two side-by-side windows or a 3D flip when the story spans two systems.
- **Minimal symbolic graphics:** a rounded tile with the app's icon/logo; no sub-labels inside tiles.
- **Real logos for real brands**, from the product's own assets or Simple Icons (`cdn.jsdelivr.net/npm/simple-icons@latest/icons/<name>.svg`). Never ship a placeholder glyph for a brand you are naming.
- Stat counters (clicks, keystrokes, days) are a professional way to dramatise effort. In explainers only, let a pivot line breathe with a few seconds of silence.

## 2. Story structure

**Default, fast (~47s; frame counts @30fps), as in `scenes.json`:**
1. **Hook (150f, 5s):** the problem in the customer's own voice (chat messages popping in); running head SOUND FAMILIAR?; one VO question.
2. **Title (118f, ~4s):** product name reveal; **the music's beat lands here** (`reveal` in `scenes.json`).
3. **Hero flow (575f, ~19s):** the main action end to end, including its effect in the other system (3D flip with a "Meanwhile, in ..." tag). 2-3 VO lines.
4. **One scene per audience / secondary benefit (215-275f, 7-9s each):** camera hops between 2-4 framings, one click each.
5. **Outro (130f, ~4s):** name + where it's live.

**Explainer (~100s, only when asked):** problem montage, pivot question, product reveal, how it works, "just ask" chat, before/now consolidation, where to find it, setup walkthrough, outro. See `examples/explainer/`.

## 3. Build mechanics

- Remotion 4.0.290, 1920x1080@30, `TransitionSeries`. VO `<Sequence>`s are placed from `scenes.json`, so changing a duration re-times audio automatically. Fast default: 10-frame `slide`/`wipe` with a whoosh at each cut.
- `theme.ts` has `prog/rise/pop/typed/keyed` and the palette. Cursors target **named anchors**, never hand-typed pixels.
- **Camera zoom on a full-width row is capped (~1.2x).** For a highlight, frame half the row (or a pair of tiles) at 1.8-2.0x and pan.
- **3D flip:** parent `perspective: 2800`, child `transformStyle: preserve-3d` + `rotateY`, two faces with `backfaceVisibility: hidden` (back one pre-rotated 180deg), plus `translateZ(-260*sin)` for depth. Renders fine in headless Chrome.
- Overlays (menus/modals/toasts) must be drawn in the same coordinate layer as what they cover and **later in the tree**. Anything outside `BrowserFrame` must set `fontFamily: SANS`, or it falls back to serif.
- Iterate with `node stills.mjs <frames...>` and inspect with vision; full render only for candidates. Frames sampled inside a transition look overlapped; resample before "fixing".

## 4. Audio

Everything goes through **TrueFoundry** (`TRUEFOUNDRY_API_KEY` from the environment, else `~/.hermes/.env`; read inside the scripts, never printed or passed on a command line). `audio-tools/gemini.py` is stdlib-only. If only `GEMINI_API_KEY` is set it falls back to direct Gemini.

- **Voiceover:** Gemini TTS `gemini-3.8-flash-tts`, voice **Charon**, one clip per beat, script in `audio-tools/vo.json`. Send **plain text only**: a style preamble made a 4.5s line take 11.5s. Account is `gemini-primary` (`gemini-group` fails for TTS); override with `LAUNCH_VIDEO_TTS_ACCOUNT` / `LAUNCH_VIDEO_TTS_MODEL`. The gateway needs a non-default `User-Agent` (Cloudflare 1010), which `gemini.py` sets. Output is raw 24 kHz PCM, wrapped as WAV, silence-trimmed, `loudnorm=I=-16`. The OpenAI-style `/audio/speech` route is not available.
- **Verify every clip by transcription** (`make_vo.py` does it: `gemini-group/gemini-3.5-flash` on the chat route; `gemini-3.5-transcribe` returns empty) and re-record until no extra or misheard words. Digits the transcriber writes for spoken numbers show up as extra words: noise. Real misreads ("one in three" -> "one and three"): rephrase the line rather than retrying. Use `silencedetect` to sync on-screen events to spoken phrases.
- **Music:** pick a bundled track (`public/music/`, README lists a verified drop per track) or your own; set `music.file` and `music.dropSeconds` in `scenes.json` so the full beat lands on the title reveal. **The drop must be beat-snapped and verified, not eyeballed from an RMS rise:** `python3 audio-tools/music_drop.py <mp3> --listen` prints energy rises snapped to the beat grid (cue file, or an estimated tempo for your own track), the sharpest hit, and Gemini's section/drop timestamps; use the beat the energy rise and the listen answer agree on. **Bundled tracks are CC BY 4.0: put "Music: Sascha Ende, ende.app (CC BY 4.0)" in the video description or credits.** Any user-supplied track can replace them; license and credit it accordingly. No AI music generation.
- **SFX:** synthesized by `audio-tools/sfx.js` into `public/sfx/` (click, key taps, thwip, whoosh, pop, chime, riser, impact). Deterministic, nothing to license.
- **Mix:** music 0.26, ducked 55% under VO (8/12-frame ramps via the `volume` callback in `Launch.tsx`). Run `node tl.mjs` to catch VO overlaps and lines spilling past scene ends. A full render of the default lands at -16.9 LUFS, -3.8 dBTP with no extra mastering; if yours is outside -17 +-2 LUFS or above -1 dBTP, lower or raise `music.volume` (or the duck) and re-render.
- **Final-render audio check, before delivering:** `python3 audio-tools/check_mix.py out/video.mp4` measures loudness (ebur128), transcribes the mixed audio back through TrueFoundry and word-diffs it against `vo.json`, and compares the reveal time with the nearest onset in the mix and with the audio-understanding answer (the onset is the tight check; the model jitters ~0.1s). Fix what fails and re-render. For a second opinion on the mix, `python3 audio-tools/gemini.py review mix.mp3`.

## 5. Environment pitfalls

- If Remotion's Chrome Headless Shell download fails ("No browser found"), put the path of a local Chrome Headless Shell in a `.browser` file (`stills.mjs` reads it) and pass `--browser-executable=$(cat .browser)` to `remotion render`.
- Use the template's pinned `typescript`/Remotion versions; `npx tsc` outside the project resolves to an unrelated package. Run `npx tsc --noEmit` after `npm install`. If `NODE_ENV=production` is set, `npm install` skips dev dependencies (the template keeps TypeScript in `dependencies` for that reason).
- `make_vo.py` shells out to `ffmpeg`; make sure a working one is first on PATH.
- On slow or shared hosts, do not render there: build and render on a workstation.

## 6. Process

- **Checkpoint before each round of changes:** the project is a git repo; commit, `git tag vN`, copy the mp4 to `checkpoints/`.
- Self-review stills of every new/changed scene plus an ffmpeg contact sheet of the final render (`-vf fps=1/2,scale=480:-1,tile=5x5`) before delivering, and run the §4 audio check. Check length against §0; if it's drifting past ~60s, cut before polishing.
- Report honestly: audio was checked by measurement and AI review, not by ear; data shown is fictional or illustrative; name the music credit.
- Deliver the mp4 with a short scene-by-scene summary.
