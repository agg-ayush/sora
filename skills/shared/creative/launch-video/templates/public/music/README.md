# Music

Three royalty-free tracks are bundled, all "Happy Beats / Business Moves" by Sascha Ende ([ende.app](https://ende.app/en)), licensed [CC BY 4.0](https://ende.app/en/standard-license). They are not covered by this skill's MIT license.

**Credit required.** Put this line in the video description or end credits whenever a bundled track is used:

> Music: Sascha Ende, ende.app (CC BY 4.0)

| File | Length | Tempo | Verified `dropSeconds` | Notes |
|---|---|---|---|---|
| `happy-beats-vol-10.mp3` | 1:00 | 110 BPM | **7.79** | Drums are in from 0s; the "drop" is the horns/full-layer entry. Shortest track, suits a 45-50s video |
| `happy-beats-vol-11.mp3` | 1:28 | 115 BPM | **16.86** | Default. Synth intro, light beat from ~4s, full groove at 16.86 |
| `happy-beats-vol-12.mp3` | 1:58 | 110 BPM | **8.74** | Guitar intro, then bass and full drums at 8.74 |

## How the drops were verified

Each value is an energy rise from `audio-tools/music_drop.py`, pinned to the sharpest 20 ms hit, snapped to the beat grid in `cues/`, and checked by the audio-understanding route (`music_drop.py --listen`, plus a re-ask on a short clip around the candidate; Gemini answers to ~0.1-0.3s and sometimes whole seconds, so it confirms the section, the grid gives the exact beat).

| Track | Energy rise | Sharpest hit | Beat grid / strong cue | Listen (first 30s; short-clip re-ask) | Chosen |
|---|---|---|---|---|---|
| vol-10 | +3.4 dB at 7.75s (also +8.6 dB at 25.25s) | 7.50-7.78s | beat 7.79, strong cue 7.92 | "main groove, horns enter" at 8s; 8.1s | 7.79 |
| vol-11 | +7.6 dB at 16.75s | 16.84s | beat 16.86 = strong cue 16.86 (16.34 is the beat before: 15 frames early) | "main groove drop with full beat" at 16s; 16.0s | 16.86 |
| vol-12 | +4.5 dB at 8.50s | 8.72s | beat 8.74 = strong cue 8.74 | "bass and full drums enter" at 8.8s; 7.8-8.0s | 8.74 |

The old vol-11 value (16.75, a raw RMS bucket) was 0.11s (3 frames) before the real hit; the beat grid and the 20 ms onset agree on 16.86.

`cues/<track>.music-cues.json` / `.md` list beat times and the strongest hits (first 25s). Use them to land the title reveal on a beat.

## Syncing the beat to the title reveal

`src/scenes.json` has `music.file` and `music.dropSeconds`. `Launch.tsx` starts the track so that second `dropSeconds` of the file lines up with the reveal frame (`reveal.scene` + `reveal.offsetFrames`). To change tracks: set `file`, then set `dropSeconds` to the verified value in the table above. For another point in a bundled track, run `python3 audio-tools/music_drop.py public/music/<track>.mp3 --listen` and take a beat-snapped candidate that the energy rise and the listen answer agree on. After rendering, `python3 audio-tools/check_mix.py out/video.mp4` measures the real alignment.

## Using your own track

Drop any mp3 into `public/music/` and point `music.file` at it. Find where the music really starts, without listening:

```bash
ffmpeg -i public/music/mytrack.mp3 -af silencedetect=noise=-35dB:d=0.2 -f null - 2>&1 | grep silence_
# the first silence_end is the first audible sound; use it (or a bar after it) as dropSeconds
```

To find the drop, run `python3 audio-tools/music_drop.py public/music/mytrack.mp3 --listen`; it prints energy rises snapped to the beat (the tempo is estimated from onset autocorrelation when there is no cue file, so treat it as approximate), and the audio-understanding answer to confirm the section. Pick the beat they agree on. Prefer a track at least as long as the video. Credit whatever licence your track carries (CC BY needs attribution; "no attribution" libraries do not). Do not use music you cannot license.
