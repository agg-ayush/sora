# Music

Three royalty-free tracks are bundled, all "Happy Beats / Business Moves" by Sascha Ende ([ende.app](https://ende.app/en)), licensed [CC BY 4.0](https://ende.app/en/standard-license). They are not covered by this skill's MIT license.

**Credit required.** Put this line in the video description or end credits whenever a bundled track is used:

> Music: Sascha Ende, ende.app (CC BY 4.0)

| File | Length | Tempo | Notes |
|---|---|---|---|
| `happy-beats-vol-10.mp3` | 1:00 | 110 BPM | Shortest; energy lifts at ~7.75s and again at ~25s. Set `dropSeconds` to 7.75 to use it for a 45-50s video |
| `happy-beats-vol-11.mp3` | 1:28 | 115 BPM | Default. Beat is steady from ~1.6s; energy lifts at 16.75s (the shipped `dropSeconds`) |
| `happy-beats-vol-12.mp3` | 1:58 | 110 BPM | Slower build; first strong hit at 8.7s |

`cues/<track>.music-cues.json` / `.md` list beat times and the strongest hits (first 25s). Use them to land the title reveal on a beat.

## Syncing the beat to the title reveal

`src/scenes.json` has `music.file` and `music.dropSeconds`. `Launch.tsx` starts the track so that second `dropSeconds` of the file lines up with the reveal frame (`reveal.scene` + `reveal.offsetFrames`). To change tracks: set `file`, then set `dropSeconds` to a strong beat from that track's cue file (see "Reveal Candidates"), or to an energy rise from `music_drop.py`. Check with `node tl.mjs` and a still around the reveal.

## Using your own track

Drop any mp3 into `public/music/` and point `music.file` at it. Find where the music really starts, without listening:

```bash
ffmpeg -i public/music/mytrack.mp3 -af silencedetect=noise=-35dB:d=0.2 -f null - 2>&1 | grep silence_
# the first silence_end is the first audible sound; use it (or a bar after it) as dropSeconds
```

To find the biggest energy rises (candidate drops) instead, run `python3 audio-tools/music_drop.py public/music/mytrack.mp3`; it prints the first audible moment and the strongest jumps, in seconds. Snap the chosen time to a beat if you have a cue file. Prefer a track at least as long as the video. Credit whatever licence your track carries (CC BY needs attribution; "no attribution" libraries do not). Do not use music you cannot license.
