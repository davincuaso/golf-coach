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
  // AVI readers ignore trailing padding. Exceed Next middleware's 10 MiB clone
  // limit so this smoke also catches accidental truncation of large uploads.
  new File([video, new Uint8Array(11 * 1024 * 1024)], "smoke.avi", {
    type: "video/x-msvideo",
  }),
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
const sessionResponse = await fetch(`${origin}/api/v1/sessions`, {
  method: "POST",
  headers: { Origin: origin, "Content-Type": "application/json" },
  body: JSON.stringify({
    attempted_clips: 1,
    clips: [
      {
        clip_id: "smoke",
        swing_id: "Swing 1",
        summary_token: result.summary_token,
      },
    ],
  }),
});
assert.equal(sessionResponse.status, 200);
const session = await sessionResponse.json();
assert.equal(session.analyzed_clips, 1);
assert.equal(session.unique_swings, 1);
assert.equal(session.tempo.median, null);
assert.ok(session.prompt_payload.includes("SESSION_JSON"));
console.log(
  "Web smoke passed: >10 MiB streaming upload → FastAPI → isolated YOLO → 24 validated pose/chart frames → signed session summary; local ChatGPT prompts generated.",
);
