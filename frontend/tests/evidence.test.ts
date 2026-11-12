import { test } from "node:test";
import assert from "node:assert/strict";
import {
  ballTrackSchema,
  calibrationSchema,
  evidenceRequest,
  reconstructionSchema,
} from "../src/lib/evidence-client.ts";

test("calibration imports reject malformed matrices and nonfinite geometry", () => {
  const profile = {
    version: "1.0",
    camera_id: "A",
    world_id: "rig",
    image_width: 1280,
    image_height: 720,
    camera_matrix: [
      [800, 0, 640],
      [0, 800, 360],
      [0, 0, 1],
    ],
    distortion: [0, 0, 0, 0, 0],
    rotation_world_to_camera: [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ],
    translation_world_to_camera_m: [1, 0, 0],
    calibration_rms_px: 0.2,
    reference_rms_px: 0.1,
    scale_and_orientation_verified: false,
  };
  assert.equal(calibrationSchema.safeParse(profile).success, true);
  assert.equal(
    calibrationSchema.safeParse({
      ...profile,
      translation_world_to_camera_m: [Infinity, 0, 0],
    }).success,
    false,
  );
  assert.equal(
    calibrationSchema.safeParse({ ...profile, camera_matrix: [[1, 2]] })
      .success,
    false,
  );
});
test("missing 3D joints and unconfirmed ball identities remain explicit", () => {
  const report = {
    version: "1.0",
    swing_id: "A",
    status: "insufficient_data",
    coordinate_system: "metres",
    frames: [
      {
        timestamp_seconds: -0.5,
        matching_error_ms: 0,
        joints: {},
        torso_tilt_deg: null,
      },
    ],
    accepted_joints: 0,
    rejected_joints: { occluded: 17 },
    matched_frames: 1,
    unmatched_frames: 0,
    median_reprojection_error_px: null,
    notices: [],
    evidence_token: "signed",
  };
  const parsed = reconstructionSchema.parse(report);
  assert.equal(parsed.frames[0].torso_tilt_deg, null);
  assert.deepEqual(parsed.frames[0].joints, {});
  assert.equal(
    reconstructionSchema.safeParse({
      ...report,
      median_reprojection_error_px: NaN,
    }).success,
    false,
  );
  assert.equal(
    ballTrackSchema.safeParse({
      version: "1.0",
      swing_id: "A",
      status: "candidate_track",
      width: 1280,
      height: 720,
      samples: [],
      stop_reason: "lost",
      needs_visual_confirmation: false,
      notices: [],
      evidence_token: "signed",
    }).success,
    false,
  );
});
test("evidence uploads preserve browser multipart boundaries and surface bounded errors", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, "/api/v1/ball-tracks");
      assert.equal(options?.headers, undefined);
      assert.ok(options?.body instanceof FormData);
      return Response.json(
        { error: { message: "Seed unavailable" } },
        { status: 422 },
      );
    };
    await assert.rejects(
      evidenceRequest(
        "/ball-tracks",
        new FormData(),
        ballTrackSchema,
        new AbortController().signal,
      ),
      /Seed unavailable/,
    );
  } finally {
    globalThis.fetch = original;
  }
});
