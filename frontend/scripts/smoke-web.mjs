// Run after backend/scripts/smoke_pose.py, with both development servers running.
import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import { analysisResponseSchema } from "../src/lib/api-types.ts";

const origin = "http://127.0.0.1:3000";
const document = JSON.parse(
  await readFile(
    new URL("../../data/smoke.analysis.json", import.meta.url),
    "utf8",
  ),
);
const video = await readFile(new URL("../../data/smoke.avi", import.meta.url));
const form = new FormData();
form.append(
  "video",
  new File([video], "smoke.avi", { type: "video/x-msvideo" }),
);
form.append(
  "options",
  JSON.stringify({
    camera_view: "down_the_line",
    subject_point: document.processing.config.subject_point,
    include_pose: true,
  }),
);
const response = await fetch(`${origin}/api/v1/analyses`, {
  method: "POST",
  headers: { Origin: origin },
  body: form,
  signal: AbortSignal.timeout(300000),
});
assert.equal(response.status, 200, `Analysis returned HTTP ${response.status}`);
assert.equal(response.headers.get("cache-control"), "no-store");
const result = analysisResponseSchema.parse(await response.json());
assert.equal(result.pose.video.frame_count, 24);
assert.equal(result.kinematics.series.length, 24);
assert.ok(result.prompt_payload.includes("master golf professional"));
assert.ok(!("llm" in result));
assert.equal(result.kinematics.events, null); // A still sample is not a golf swing.
console.log(
  "Web smoke passed: Next.js proxy → FastAPI → isolated YOLO → 24 validated pose/chart frames; local ChatGPT prompt generated.",
);
