import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile } from "remotion";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";

import { SceneCard, SceneChat, SceneOutro, SceneSetup } from "./scenes-b";
import { SceneAgent, SceneAsk, SceneHook, SceneIntro } from "./scenes-new";
import { CONSOLIDATE_FRAMES, SceneConsolidate } from "./scene-consolidate";
import VO_DUR from "../public/vo/durations.json";

const T = 15;
type SceneDef = { id: string; C: React.FC; d: number; vo: [string, number][] };
export const SCENES: SceneDef[] = [
  { id: "hook", C: SceneHook, d: 420, vo: [["hook", 12]] },
  { id: "ask", C: SceneAsk, d: 225, vo: [["ask", 20]] },
  { id: "intro", C: SceneIntro, d: 190, vo: [["intro", 30]] },
  { id: "agent", C: SceneAgent, d: 520, vo: [["webs", 36], ["acts", 346]] },
  { id: "chat", C: SceneChat, d: 290, vo: [["chat1", 4], ["chat2", 100], ["chat3", 198]] },
  { id: "consolidate", C: SceneConsolidate, d: CONSOLIDATE_FRAMES, vo: [["consol1", 8], ["consol2", 312]] },
  { id: "card", C: SceneCard, d: 260, vo: [["card", 14]] },
  { id: "setup", C: SceneSetup, d: 510, vo: [["setup1", 6], ["setup2", 150], ["setup3", 300], ["setup4", 402]] },
  { id: "outro", C: SceneOutro, d: 290, vo: [["outro", 10]] },
];
export const STARTS = SCENES.reduce<number[]>((acc, s, i) => [...acc, i === 0 ? 0 : acc[i - 1] + SCENES[i - 1].d - T], []);
export const TOTAL = STARTS[STARTS.length - 1] + SCENES[SCENES.length - 1].d;

const VO = SCENES.flatMap((s, i) =>
  s.vo.map(([id, off]) => ({ id, at: STARTS[i] + off, dur: Math.ceil((VO_DUR as Record<string, number>)[id] * 30) }))
);

// The music's beat enters at 22.0s; land it on the "Product MCP" reveal.
const REVEAL = STARTS[2] + 40;
const MUSIC_OFFSET = Math.max(0, 22 * 30 - REVEAL);

const musicVolume = (f: number) => {
  const base = interpolate(f, [0, 30, TOTAL - 75, TOTAL - 5], [0, 0.2, 0.2, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  // duck under the voice with 8-frame ramps
  let duck = 0;
  for (const v of VO) {
    const d = Math.min(interpolate(f, [v.at - 8, v.at], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }), interpolate(f, [v.at + v.dur, v.at + v.dur + 12], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
    duck = Math.max(duck, d);
  }
  return base * (1 - 0.55 * duck);
};

export const Launch: React.FC = () => (
  <AbsoluteFill>
    <TransitionSeries>
      {SCENES.flatMap(({ C, d }, i) => {
        const seq = (
          <TransitionSeries.Sequence key={`s${i}`} durationInFrames={d}>
            <C />
          </TransitionSeries.Sequence>
        );
        if (i === SCENES.length - 1) return [seq];
        return [seq, <TransitionSeries.Transition key={`t${i}`} presentation={fade()} timing={linearTiming({ durationInFrames: T })} />];
      })}
    </TransitionSeries>

    <Audio src={staticFile("music/bed.mp3")} startFrom={MUSIC_OFFSET} volume={musicVolume} />
    {VO.map((v) => (
      <Sequence key={v.id} from={v.at} durationInFrames={v.dur + 10} layout="none">
        <Audio src={staticFile(`vo/${v.id}.wav`)} volume={1} />
      </Sequence>
    ))}
    <Sequence from={REVEAL - 42} durationInFrames={50} layout="none">
      <Audio src={staticFile("sfx/riser.wav")} volume={0.3} />
    </Sequence>
    <Sequence from={REVEAL} durationInFrames={70} layout="none">
      <Audio src={staticFile("sfx/impact.wav")} volume={0.5} />
    </Sequence>
  </AbsoluteFill>
);

export const TIMELINE = { STARTS, TOTAL, VO, REVEAL, MUSIC_OFFSET };
