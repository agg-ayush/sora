// Print the scene/VO timeline from the same scene table Launch.tsx uses (src/scenes.json).
import fs from "fs";
const table = JSON.parse(fs.readFileSync("src/scenes.json", "utf8"));
const d = JSON.parse(fs.readFileSync("public/vo/durations.json", "utf8"));
const { fps, transitionFrames: T } = table;
let st = 0;
for (const { id, frames: len, vo } of table.scenes) {
  console.log(`${id.padEnd(6)} ${st}-${st + len} (${(st / fps).toFixed(1)}s)`);
  for (const [v, o] of vo) {
    if (d[v] == null) { console.log(`   vo ${v.padEnd(6)} MISSING from public/vo/durations.json (run make_vo.py)`); continue; }
    const a = st + o, n = Math.ceil(d[v] * fps), e = a + n;
    console.log(`   vo ${v.padEnd(6)} ${a}-${e}  scene-rel ${o}-${o + n} ${e > st + len ? "SPILL" : ""}`);
  }
  st += len - T;
}
const total = st + T;
console.log("total", total, (total / fps).toFixed(1) + "s");
