import { test } from "node:test";
import assert from "node:assert/strict";
import {
  sessionOptions,
  sessionResponseSchema,
} from "../src/lib/session-client.ts";

const base = {
  start: "40",
  end: "46",
  duration: 91.76,
  cameraView: "oblique" as const,
  alignment: false,
  markers: ["", "", ""] as [string, string, string],
  subject: ["", ""] as [string, string],
  swingId: "Swing A",
};
test("session windows select long sources without removing per-job limits", () => {
  const options = sessionOptions(base);
  assert.equal(options.source_start_seconds, 40);
  assert.equal(options.source_end_seconds, 46);
  assert.equal(options.camera_view, "oblique");
  assert.equal(options.camera_alignment_confirmed, false);
  for (const patch of [
    { end: "80" },
    { start: "47", end: "46" },
    { end: "" },
    { end: "95" },
    { swingId: "bad/id" },
  ])
    assert.throws(() => sessionOptions({ ...base, ...patch }));
});
test("manual markers are relative to the selected window, not the original recording", () => {
  const options = sessionOptions({
    ...base,
    markers: ["1", "2", "2.3"],
    subject: ["0.4", "0.5"],
  });
  assert.equal(options.events?.impact_seconds, 2.3);
  assert.deepEqual(options.subject_point, [0.4, 0.5]);
  assert.throws(() =>
    sessionOptions({ ...base, markers: ["41", "42", "42.3"] }),
  );
});
test("session responses reject nonfinite or missing combined evidence", () => {
  assert.equal(sessionResponseSchema.safeParse({}).success, false);
});
