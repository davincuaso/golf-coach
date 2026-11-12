import { z } from "zod";
import type {
  AnalysisOptions,
  AnalysisResponse,
  CameraView,
} from "./api-types.ts";
import { parseSwingMarkers } from "./capture.ts";

export const MAX_SESSION_CLIPS = 8;
const numeric = z.number().finite();
const statistic = z.object({
  swings: numeric.int().nonnegative(),
  median: numeric.nullable(),
  minimum: numeric.nullable(),
  maximum: numeric.nullable(),
});
export const sessionResponseSchema = z.object({
  session_id: z.string(),
  status: z.enum(["complete", "partial"]),
  attempted_clips: numeric.int(),
  analyzed_clips: numeric.int(),
  unique_swings: numeric.int(),
  swings: z.array(
    z.object({
      swing_id: z.string(),
      clip_ids: z.array(z.string()),
      tempo_ratio: numeric.nullable(),
      max_posture_loss_deg: numeric.nullable(),
      tempo_source: z.string().nullable(),
      posture_source: z.string().nullable(),
      fault_codes: z.array(z.string()),
      conflicts: z.array(z.string()),
    }),
  ),
  tempo: statistic,
  posture_loss: statistic,
  patterns: z.array(
    z.object({
      code: z.string(),
      swing_count: numeric.int(),
      swing_ids: z.array(z.string()),
    }),
  ),
  notices: z.array(z.string()),
  prompt_payload: z.string().min(1),
  additional_evidence: z.array(z.record(z.unknown())).default([]),
});
export type SessionResponse = z.infer<typeof sessionResponseSchema>;
export interface SessionEntry {
  id: string;
  file: File;
  swingId: string;
  start: string;
  end: string;
  duration?: number;
  cameraView: CameraView;
  alignment: boolean;
  markers: [string, string, string];
  subject: [string, string];
  analysis?: AnalysisResponse;
  status: "ready" | "uploading" | "analyzing" | "done" | "failed";
  error?: string;
}
export function sessionOptions(
  entry: Pick<
    SessionEntry,
    | "start"
    | "end"
    | "duration"
    | "cameraView"
    | "alignment"
    | "markers"
    | "subject"
    | "swingId"
  >,
): AnalysisOptions {
  if (!entry.start.trim() || !entry.end.trim())
    throw new Error("Choose a source start and end time.");
  const start = Number(entry.start),
    end = Number(entry.end);
  if (
    !Number.isFinite(start) ||
    !Number.isFinite(end) ||
    start < 0 ||
    end <= start ||
    end - start > 30
  )
    throw new Error(
      "Each analysis window must be longer than zero and at most 30 seconds.",
    );
  if (entry.duration !== undefined && end > entry.duration + 0.01)
    throw new Error("The selected window extends beyond this recording.");
  if (!/^[A-Za-z0-9 _-]{1,40}$/.test(entry.swingId.trim()))
    throw new Error(
      "Use a short swing ID with letters, numbers, spaces, hyphens, or underscores.",
    );
  let point: [number, number] | undefined;
  if (entry.subject.some((value) => value.trim() !== "")) {
    if (
      entry.subject.some(
        (value) =>
          value.trim() === "" ||
          !Number.isFinite(Number(value)) ||
          Number(value) < 0 ||
          Number(value) > 1,
      )
    )
      throw new Error("Choose both golfer coordinates between 0 and 1.");
    point = [Number(entry.subject[0]), Number(entry.subject[1])];
  }
  const events = parseSwingMarkers(entry.markers, end - start);
  return {
    camera_view: entry.cameraView,
    camera_alignment_confirmed:
      entry.cameraView === "down_the_line" && entry.alignment,
    source_start_seconds: start,
    source_end_seconds: end,
    events,
    estimate_events: !events,
    confirm_constant_frame_rate: false,
    subject_point: point,
    include_pose: true,
  };
}

export function readSourceDuration(file: File): Promise<number | undefined> {
  return new Promise((resolve) => {
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);
    const timer = setTimeout(() => finish(undefined), 10000);
    let settled = false;
    const finish = (value: number | undefined) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      video.onloadedmetadata = null;
      video.onerror = null;
      video.removeAttribute("src");
      video.load();
      URL.revokeObjectURL(url);
      resolve(value);
    };
    video.preload = "metadata";
    video.onloadedmetadata = () =>
      finish(
        Number.isFinite(video.duration) && video.duration > 0
          ? video.duration
          : undefined,
      );
    video.onerror = () => finish(undefined);
    video.src = url;
  });
}

export async function combineSession(
  entries: SessionEntry[],
  attempted: number,
  signal: AbortSignal,
  evidenceTokens: string[] = [],
): Promise<SessionResponse> {
  const response = await fetch("/api/v1/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    cache: "no-store",
    body: JSON.stringify({
      attempted_clips: attempted,
      evidence_tokens: evidenceTokens,
      clips: entries
        .filter((entry) => entry.analysis)
        .map((entry) => ({
          clip_id: entry.id,
          swing_id: entry.swingId.trim(),
          summary_token: entry.analysis!.summary_token,
        })),
    }),
  });
  if (!response.ok)
    throw new Error(
      "The session could not be combined. Retry the session report or reanalyze expired clips.",
    );
  const parsed = sessionResponseSchema.safeParse(await response.json());
  if (!parsed.success) throw new Error("The session result was incomplete.");
  return parsed.data;
}
