import { test } from "node:test";
import assert from "node:assert/strict";
import {
  formatMetric,
  linePath,
  nearestPoseFrame,
} from "../src/lib/visualization.ts";
import {
  bestRecordingMime,
  MAX_VIDEO_BYTES,
  parseSwingMarkers,
  validateVideo,
} from "../src/lib/capture.ts";
import type { PoseFrame } from "../src/lib/api-types.ts";
import { videoPointFromClick } from "../src/lib/visualization.ts";
import { validateVideoDuration } from "../src/lib/capture.ts";
const frames: PoseFrame[] = [0, 0.04, 0.19, 0.23].map(
  (timestamp_seconds, frame_index) => ({
    timestamp_seconds,
    frame_index,
    landmarks: {},
    angles_deg: {},
  }),
);

test("subject selection accounts for portrait/landscape letterboxing and rejects bars", () => {
  assert.deepEqual(
    videoPointFromClick(200, 150, 400, 300, 1920, 1080),
    [0.5, 0.5],
  );
  assert.equal(videoPointFromClick(200, 10, 400, 300, 1920, 1080), null);
  assert.equal(videoPointFromClick(10, 150, 400, 300, 1080, 1920), null);
  assert.deepEqual(
    videoPointFromClick(200, 150, 400, 300, 1080, 1920),
    [0.5, 0.5],
  );
  assert.equal(videoPointFromClick(0, 0, 0, 0, 0, 0), null);
});

test("long supplied recordings are flagged before upload, while unknown duration stays server-validated", () => {
  assert.match(validateVideoDuration(91.76) || "", /Open Sessions to choose a swing window/);
  assert.match(validateVideoDuration(47.03) || "", /30 seconds/);
  assert.equal(validateVideoDuration(6.37), null);
  assert.equal(validateVideoDuration(undefined), null);
  assert.equal(validateVideoDuration(Infinity), null);
});
test("overlay uses nearest decoded timestamp, handles VFR, seeks and gaps", () => {
  assert.equal(nearestPoseFrame(frames, 0.18), 2);
  assert.equal(nearestPoseFrame(frames, 0.045), 1);
  assert.equal(nearestPoseFrame(frames, 2), -1);
  assert.equal(nearestPoseFrame(frames, 0.12, 0.03), -1);
  assert.equal(nearestPoseFrame([], 0), -1);
  assert.equal(nearestPoseFrame(frames, NaN), -1);
});
test("chart paths break through missing tracking instead of drawing fabricated values", () => {
  const path = linePath(
    [
      { time: 0, value: 2 },
      { time: 1, value: 3 },
      { time: 2, value: null },
      { time: 3, value: 4 },
    ],
    (v) => v * 10,
    (v) => v,
  );
  assert.equal(path, "M0.00,2.00 L10.00,3.00  M30.00,4.00");
  assert.equal(formatMetric(null, "°"), "—");
  assert.equal(formatMetric(0, "°"), "0.0°");
});
test("marker validation accepts blanks or a complete ordered in-video triplet", () => {
  assert.equal(parseSwingMarkers(["", "", ""]), undefined);
  assert.deepEqual(parseSwingMarkers(["0", "0.9", "1.2"], 1.2), {
    start_seconds: 0,
    top_seconds: 0.9,
    impact_seconds: 1.2,
  });
  for (const values of [
    ["", "1", "2"],
    ["-1", "1", "2"],
    ["0", "2", "1"],
    ["0", "1", "Infinity"],
    ["0", "1", "3"],
  ])
    assert.throws(() =>
      parseSwingMarkers(values as [string, string, string], 2),
    );
});
test("upload and recorder limits are checked before transfer", () => {
  assert.equal(
    validateVideo({ name: "swing.MOV", size: MAX_VIDEO_BYTES }),
    null,
  );
  for (const file of [
    { name: "bad.exe", size: 1 },
    { name: "empty.mp4", size: 0 },
    { name: "big.mp4", size: MAX_VIDEO_BYTES + 1 },
  ])
    assert.ok(validateVideo(file));
  assert.equal(
    bestRecordingMime({ isTypeSupported: (value) => value === "video/mp4" }),
    "video/mp4",
  );
  assert.equal(bestRecordingMime({ isTypeSupported: () => false }), undefined);
});
