// Render several stills from one bundle: node stills.mjs 100 250 400 ...
// Writes out/s/<frame>.png at half scale; frames are GLOBAL Launch frames.
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import fs from "fs";
import os from "os";
import path from "path";

const frames = process.argv.slice(2).map(Number);
// Optional: put a Chrome Headless Shell path in .browser if Remotion can't download its own.
const browserExecutable = fs.existsSync(".browser") ? fs.readFileSync(".browser", "utf8").trim() : undefined;
// Bundle into a private dir (bundle() without outDir leaves ~64 MB in TMPDIR) and always delete it:
// normal exit, error, SIGINT/SIGTERM/SIGHUP. SIGKILL cannot be trapped.
const bundleDir = fs.mkdtempSync(path.join(os.tmpdir(), "remotion-webpack-bundle-"));
let cleaned = false;
const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  fs.rmSync(bundleDir, { recursive: true, force: true });
};
process.on("exit", cleanup);
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sig, () => {
    cleanup();
    process.exit(128 + os.constants.signals[sig]);
  });
}
try {
  const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts"), outDir: bundleDir });
  const composition = await selectComposition({ serveUrl, id: "Launch", browserExecutable });
  fs.mkdirSync("out/s", { recursive: true });
  for (const frame of frames) {
    await renderStill({ composition, serveUrl, frame, output: `out/s/${frame}.png`, scale: 0.5, browserExecutable });
    console.log("still", frame);
  }
} finally {
  cleanup();
}
