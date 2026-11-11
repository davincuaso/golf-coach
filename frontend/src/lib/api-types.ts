import { z } from "zod";

export const landmarkNames = [
  "nose",
  "left_eye",
  "right_eye",
  "left_ear",
  "right_ear",
  "left_shoulder",
  "right_shoulder",
  "left_elbow",
  "right_elbow",
  "left_wrist",
  "right_wrist",
  "left_hip",
  "right_hip",
  "left_knee",
  "right_knee",
  "left_ankle",
  "right_ankle",
] as const;
export type LandmarkName = (typeof landmarkNames)[number];
export type CameraView = "down_the_line" | "face_on" | "unknown";
export interface SwingEvents {
  start_seconds: number;
  top_seconds: number;
  impact_seconds: number;
}
export interface AnalysisOptions {
  camera_view: CameraView;
  events?: SwingEvents;
  estimate_events: boolean;
  confirm_constant_frame_rate: boolean;
  subject_point?: [number, number];
  llm_enabled: boolean;
  include_pose: boolean;
}
export interface Landmark {
  xy_px: [number, number] | null;
  xy_normalized?: [number, number] | null;
  raw_xy_px?: [number, number] | null;
  confidence: number | null;
  observed: boolean;
  interpolated: boolean;
  filtered: boolean;
}
export interface PoseFrame {
  frame_index: number;
  timestamp_seconds: number;
  landmarks: Partial<Record<LandmarkName, Landmark>>;
  angles_deg: Record<string, number | null>;
  person_bbox_xyxy_px?: [number, number, number, number] | null;
}
export interface VisionDocument {
  schema_version: "1.0.0";
  video: {
    width: number;
    height: number;
    nominal_fps: number;
    frame_count: number;
    timestamp_source: "decoder_pts" | "nominal_fps_fallback";
  };
  frames: PoseFrame[];
}
export interface SeriesPoint {
  timestamp_seconds: number;
  spine_tilt_deg: number | null;
  spine_delta_deg: number | null;
  wrist_speed_torso_per_second: number | null;
}
export interface Kinematics {
  version: string;
  status: "complete" | "partial" | "insufficient_data";
  camera_view: CameraView;
  events: SwingEvents | null;
  event_source: "manual" | "estimated" | null;
  timing_reliable: boolean;
  backswing_seconds: number | null;
  downswing_seconds: number | null;
  tempo_ratio: number | null;
  baseline_spine_tilt_deg: number | null;
  impact_spine_tilt_deg: number | null;
  spine_delta_deg: number | null;
  max_posture_loss_deg: number | null;
  posture_valid_fraction: number;
  posture_eligible: boolean;
  warnings: string[];
  series: SeriesPoint[];
}
export interface Fault {
  code: "LOSS_OF_POSTURE" | "TEMPO_OUTSIDE_REFERENCE";
  title: string;
  severity: "observation" | "moderate";
  explanation: string;
  evidence: Record<string, number | string>;
  drill_ids: string[];
}
export interface Drill {
  id: string;
  name: string;
  instructions: string[];
}
export interface RuleReport {
  version: string;
  faults: Fault[];
  drills: Drill[];
  notices: string[];
}
export interface CoachingNarrative {
  summary: string;
  possible_root_cause: string | null;
  priorities: { fault_code: string; explanation: string }[];
  recommended_drill_ids: string[];
  practice_plan: string;
}
export interface AnalysisResponse {
  analysis_id: string;
  kinematics: Kinematics;
  coaching: RuleReport;
  llm: {
    status: "disabled" | "complete" | "skipped" | "unavailable";
    narrative: CoachingNarrative | null;
    reason: string | null;
  };
  pose: VisionDocument | null;
}

const number = z.number().finite();
const optionalNumber = number.nullable();
const pair = z.tuple([number, number]);
const events = z.object({
  start_seconds: number.nonnegative(),
  top_seconds: number.positive(),
  impact_seconds: number.positive(),
});
const landmark = z.object({
  xy_px: pair.nullable(),
  xy_normalized: pair.nullable().optional(),
  raw_xy_px: pair.nullable().optional(),
  confidence: number.min(0).max(1).nullable(),
  observed: z.boolean(),
  interpolated: z.boolean(),
  filtered: z.boolean(),
});
export const analysisResponseSchema: z.ZodType<AnalysisResponse> = z.object({
  analysis_id: z.string(),
  kinematics: z.object({
    version: z.string(),
    status: z.enum(["complete", "partial", "insufficient_data"]),
    camera_view: z.enum(["down_the_line", "face_on", "unknown"]),
    events: events.nullable(),
    event_source: z.enum(["manual", "estimated"]).nullable(),
    timing_reliable: z.boolean(),
    backswing_seconds: optionalNumber,
    downswing_seconds: optionalNumber,
    tempo_ratio: optionalNumber,
    baseline_spine_tilt_deg: optionalNumber,
    impact_spine_tilt_deg: optionalNumber,
    spine_delta_deg: optionalNumber,
    max_posture_loss_deg: optionalNumber,
    posture_valid_fraction: number.min(0).max(1),
    posture_eligible: z.boolean(),
    warnings: z.array(z.string()),
    series: z
      .array(
        z.object({
          timestamp_seconds: number.nonnegative(),
          spine_tilt_deg: optionalNumber,
          spine_delta_deg: optionalNumber,
          wrist_speed_torso_per_second: optionalNumber,
        }),
      )
      .max(12000),
  }),
  coaching: z.object({
    version: z.string(),
    faults: z.array(
      z.object({
        code: z.enum(["LOSS_OF_POSTURE", "TEMPO_OUTSIDE_REFERENCE"]),
        title: z.string(),
        severity: z.enum(["observation", "moderate"]),
        explanation: z.string(),
        evidence: z.record(z.union([number, z.string()])),
        drill_ids: z.array(z.string()),
      }),
    ),
    drills: z.array(
      z.object({
        id: z.string(),
        name: z.string(),
        instructions: z.array(z.string()),
      }),
    ),
    notices: z.array(z.string()),
  }),
  llm: z.object({
    status: z.enum(["disabled", "complete", "skipped", "unavailable"]),
    reason: z.string().nullable(),
    narrative: z
      .object({
        summary: z.string(),
        possible_root_cause: z.string().nullable(),
        priorities: z.array(
          z.object({ fault_code: z.string(), explanation: z.string() }),
        ),
        recommended_drill_ids: z.array(z.string()),
        practice_plan: z.string(),
      })
      .nullable(),
  }),
  pose: z
    .object({
      schema_version: z.literal("1.0.0"),
      video: z.object({
        width: number.positive(),
        height: number.positive(),
        nominal_fps: number.positive(),
        frame_count: number.int().positive(),
        timestamp_source: z.enum(["decoder_pts", "nominal_fps_fallback"]),
      }),
      frames: z
        .array(
          z.object({
            frame_index: number.int().nonnegative(),
            timestamp_seconds: number.nonnegative(),
            landmarks: z.record(z.enum(landmarkNames), landmark),
            angles_deg: z.record(optionalNumber),
            person_bbox_xyxy_px: z
              .tuple([number, number, number, number])
              .nullable()
              .optional(),
          }),
        )
        .max(12000),
    })
    .nullable(),
});
