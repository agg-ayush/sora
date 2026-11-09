import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile } from "remotion";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";

import { SceneEscalate, SceneHook, SceneOutro, SceneQueue, SceneTeam, SceneTitle } from "./scenes";
import { EASE_IN_OUT } from "./theme";
import TABLE from "./scenes.json";
import VO_DUR from "../public/vo/durations.json";

// Scene table: ids, lengths, VO placement and transitions live in scenes.json
// (also read by tl.mjs). Only the id -> component map is here.
const COMPONENTS: Record<string, React.FC> = {
  hook: SceneHook,
  title: SceneTitle,
  esc: SceneEscalate,
  queue: SceneQueue,
  team: SceneTeam,
  outro: SceneOutro,
};

const T = TABLE.transitionFrames;
type Tr = "wipe" | "slide" | "fade" | undefined;
type SceneDef = { id: string; C: React.FC; d: number; vo: [string, number][]; tr?: Tr };
export const SCENES: SceneDef[] = TABLE.scenes.map((s) => ({
  id: s.id,
  C: COMPONENTS[s.id],
  d: s.frames,
  vo: s.vo as [string, number][],
  tr: (s as { transition?: string }).transition as Tr,
}));
export const STARTS = SCENES.reduce<number[]>((acc, s, i) => [...acc, i === 0 ? 0 : acc[i - 1] + SCENES[i - 1].d - T], []);
export const TOTAL = STARTS[STARTS.length - 1] + SCENES[SCENES.length - 1].d;

const VO = SCENES.flatMap((s, i) =>
  s.vo.map(([id, off]) => ({ id, at: STARTS[i] + off, dur: Math.ceil((VO_DUR as Record<string, number>)[id] * TABLE.fps) }))
);

// Title reveal = where the music's beat should land. `dropSeconds` is the time in
// the music file of the beat to land there (see public/music/README.md).
export const REVEAL = STARTS[SCENES.findIndex((s) => s.id === TABLE.reveal.scene)] + TABLE.reveal.offsetFrames;
export const MUSIC_DROP_S = TABLE.music.dropSeconds;
const MUSIC_FROM = Math.round(REVEAL - MUSIC_DROP_S * TABLE.fps);
const MUSIC_VOL = TABLE.music.volume;

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const musicVolume = (local: number) => {
  const g = local + Math.max(0, MUSIC_FROM); // global frame
  const start = Math.max(0, MUSIC_FROM);
  const base = interpolate(g, [start, start + 15, TOTAL - 40, TOTAL - 4], [0, MUSIC_VOL, MUSIC_VOL, 0], clamp);
  let duck = 0;
  for (const v of VO) {
    const d = Math.min(interpolate(g, [v.at - 8, v.at], [0, 1], clamp), interpolate(g, [v.at + v.dur, v.at + v.dur + 12], [1, 0], clamp));
    duck = Math.max(duck, d);
  }
  return base * (1 - 0.55 * duck);
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const presentation = (t: SceneDef["tr"]): any =>
  t === "wipe" ? wipe({ direction: "from-left" }) : t === "slide" ? slide({ direction: "from-right" }) : fade();

export const Launch: React.FC = () => (
  <AbsoluteFill style={{ background: "#f4f2ed" }}>
    <TransitionSeries>
      {SCENES.flatMap(({ C, d, tr }, i) => {
        const seq = (
          <TransitionSeries.Sequence key={`s${i}`} durationInFrames={d}>
            <C />
          </TransitionSeries.Sequence>
        );
        if (i === SCENES.length - 1) return [seq];
        return [
          seq,
          <TransitionSeries.Transition key={`t${i}`} presentation={presentation(tr)} timing={linearTiming({ durationInFrames: T, easing: EASE_IN_OUT })} />,
        ];
      })}
    </TransitionSeries>

    <Sequence from={Math.max(0, MUSIC_FROM)} layout="none">
      <Audio src={staticFile(TABLE.music.file)} startFrom={Math.max(0, -MUSIC_FROM)} volume={musicVolume} />
    </Sequence>
    {VO.map((v) => (
      <Sequence key={v.id} from={v.at} durationInFrames={v.dur + 10} layout="none">
        <Audio src={staticFile(`vo/${v.id}.wav`)} volume={1} />
      </Sequence>
    ))}
    {STARTS.slice(1).map((s, i) => (
      <Sequence key={`w${i}`} from={s - 4} durationInFrames={30} layout="none">
        <Audio src={staticFile("sfx/whoosh.wav")} volume={0.32} />
      </Sequence>
    ))}
  </AbsoluteFill>
);

export const TIMELINE = { STARTS, TOTAL, VO, REVEAL, MUSIC_FROM };
