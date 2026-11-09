// Render several stills from one bundle: node stills.mjs 100 250 400 ...
// Writes out/s/<frame>.png at half scale; frames are GLOBAL Launch frames.
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import fs from "fs";
import path from "path";

const frames = process.argv.slice(2).map(Number);
// Optional: put a Chrome Headless Shell path in .browser if Remotion can't download its own.
const browserExecutable = fs.existsSync(".browser") ? fs.readFileSync(".browser", "utf8").trim() : undefined;
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });
const composition = await selectComposition({ serveUrl, id: "Launch", browserExecutable });
fs.mkdirSync("out/s", { recursive: true });
for (const frame of frames) {
  await renderStill({ composition, serveUrl, frame, output: `out/s/${frame}.png`, scale: 0.5, browserExecutable });
  console.log("still", frame);
}
