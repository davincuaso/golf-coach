import { z } from "zod";
const finite = z.number().finite();
const vector = z.tuple([finite, finite, finite]);
const matrix = z.tuple([vector, vector, vector]);
export const calibrationSchema = z
  .object({
    version: z.literal("1.0"),
    camera_id: z.string().min(1).max(50),
    world_id: z.string().min(1).max(80),
    image_width: finite.int().min(100).max(4096),
    image_height: finite.int().min(100).max(4096),
    camera_matrix: matrix,
    distortion: z
      .array(finite)
      .refine((values) => [4, 5, 8].includes(values.length)),
    rotation_world_to_camera: matrix,
    translation_world_to_camera_m: vector,
    calibration_rms_px: finite.min(0).max(20),
    reference_rms_px: finite.min(0).max(20),
    scale_and_orientation_verified: z.boolean(),
  })
  .strict();
export type CameraCalibration = z.infer<typeof calibrationSchema>;
export const reconstructionSchema = z.object({
  version: z.literal("1.0"),
  swing_id: z.string(),
  status: z.enum(["reconstructed", "insufficient_data"]),
  coordinate_system: z.string(),
  accepted_joints: finite.int(),
  rejected_joints: z.record(finite.int()),
  matched_frames: finite.int(),
  unmatched_frames: finite.int(),
  median_reprojection_error_px: finite.nullable(),
  frames: z.array(
    z.object({
      timestamp_seconds: finite,
      matching_error_ms: finite,
      joints: z.record(
        z.object({
          xyz_m: vector,
          reprojection_error_px: finite,
          ray_angle_deg: finite,
        }),
      ),
      torso_tilt_deg: finite.nullable(),
    }),
  ),
  notices: z.array(z.string()),
  evidence_token: z.string().min(1),
});
export type Reconstruction = z.infer<typeof reconstructionSchema>;
export const ballTrackSchema = z.object({
  version: z.literal("1.0"),
  swing_id: z.string(),
  status: z.enum(["candidate_track", "insufficient_data"]),
  width: finite.int(),
  height: finite.int(),
  stop_reason: z.string(),
  needs_visual_confirmation: z.literal(true),
  samples: z.array(
    z.object({
      source_seconds: finite,
      xy_px: z.tuple([finite, finite]),
      similarity: finite,
      source: z
        .enum(["manual_seed", "model_detection", "appearance_match"])
        .default("appearance_match"),
    }),
  ),
  notices: z.array(z.string()),
  evidence_token: z.string().min(1),
  tracker_backend: z
    .enum(["onnx_golf_detector", "appearance_baseline"])
    .default("appearance_baseline"),
  model_sha256: z.string().nullable().optional(),
  model_source: z.string().nullable().optional(),
  camera_motion_detected: z.boolean().default(false),
  stationary_confirmed: z.boolean().default(false),
});
export type BallTrack = z.infer<typeof ballTrackSchema>;
export const shotImportSchema = z.object({
  version: z.literal("1.0"),
  device: z.string(),
  conditions: z.string(),
  shots: z.array(
    z.object({
      shot_id: z.string(),
      swing_id: z.string(),
      recorded_at: z.string().nullable(),
      metrics: z.record(
        z.object({
          value: finite,
          unit: z.string(),
          original_value: finite,
          original_unit: z.string(),
          method: z.enum([
            "measured",
            "device_calculated",
            "manual",
            "unknown",
          ]),
        }),
      ),
      checks: z.array(
        z.object({
          metric: z.string(),
          status: z.enum(["within_intent", "outside_intent", "unavailable"]),
          explanation: z.string(),
        }),
      ),
    }),
  ),
  intent: z.object({
    carry_min_m: finite.nullable(),
    carry_max_m: finite.nullable(),
    launch_direction_min_deg: finite,
    launch_direction_max_deg: finite,
    offline_tolerance_m: finite,
    desired_shape: z.string(),
    handedness: z.string(),
    straight_spin_axis_tolerance_deg: finite,
  }),
  notices: z.array(z.string()),
  evidence_token: z.string().min(1),
});
export type ShotImport = z.infer<typeof shotImportSchema>;
export interface EvidenceArtifact {
  kind: "calibrated_3d" | "launch_monitor_import" | "ball_candidate_track";
  result: Reconstruction | ShotImport | BallTrack;
}

export async function evidenceRequest<S extends z.ZodTypeAny>(
  path: "/reconstructions" | "/shot-imports" | "/ball-tracks",
  body: unknown | FormData,
  schema: S,
  signal: AbortSignal,
): Promise<z.output<S>> {
  const multipart = body instanceof FormData;
  const response = await fetch(`/api/v1${path}`, {
    method: "POST",
    headers: multipart ? undefined : { "Content-Type": "application/json" },
    body: multipart ? body : JSON.stringify(body),
    signal,
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(
      typeof payload?.error?.message === "string"
        ? payload.error.message
        : "The evidence check could not finish. Check the inputs and try again.",
    );
  }
  return schema.parse(await response.json());
}
export function downloadJson(name: string, value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const monitorTemplate = [
  {
    shot_id: "shot-1",
    swing_id: "Swing 1",
    recorded_at: "",
    ball_speed: "",
    ball_speed_unit: "mph",
    ball_speed_method: "unknown",
    launch_angle: "",
    launch_angle_unit: "deg",
    launch_angle_method: "unknown",
    launch_direction: "",
    launch_direction_unit: "deg",
    launch_direction_method: "unknown",
    carry: "",
    carry_unit: "yd",
    carry_method: "unknown",
    offline: "",
    offline_unit: "yd",
    offline_method: "unknown",
    spin_axis: "",
    spin_axis_unit: "deg",
    spin_axis_method: "unknown",
    spin_rate: "",
    spin_rate_unit: "rpm",
    spin_rate_method: "unknown",
  },
];
