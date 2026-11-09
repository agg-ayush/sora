import React from "react";
import { Composition } from "remotion";

import { Launch, TOTAL } from "./Launch";
import { PaperTexture } from "./PaperTexture";

export const Root: React.FC = () => (
  <>
    <Composition id="Launch" component={Launch} durationInFrames={TOTAL} fps={30} width={1920} height={1080} />
    <Composition id="PaperTexture" component={PaperTexture} durationInFrames={1} fps={30} width={1920} height={1080} />
  </>
);
