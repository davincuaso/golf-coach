import { after, test } from "node:test";
import assert from "node:assert/strict";
import { uploadAnalysis } from "../src/lib/analysis-client.ts";
import {
  analysisResponseSchema,
  type AnalysisOptions,
  type AnalysisResponse,
} from "../src/lib/api-types.ts";

const result: AnalysisResponse = {
  analysis_id: "test-analysis",
  summary_token: "test-only-summary-token",
  pose: null,
  kinematics: {
    version: "1.0.0",
    status: "insufficient_data",
    camera_view: "unknown",
    events: null,
    event_source: null,
    timing_reliable: false,
    backswing_seconds: null,
    downswing_seconds: null,
    tempo_ratio: null,
    baseline_spine_tilt_deg: null,
    impact_spine_tilt_deg: null,
    spine_delta_deg: null,
    max_posture_loss_deg: null,
    posture_valid_fraction: 0,
    posture_eligible: false,
    quality: {
      version: "1.0.0",
      status: "insufficient",
      window_start_seconds: 0,
      window_end_seconds: 0,
      window_source: "whole_clip",
      camera: {
        declared_view: "unknown",
        alignment_confirmed: false,
        assessment: "needs_confirmation",
        projection_hint: "unknown",
        projected_width_torso_ratio: null,
        note: "Not calibrated",
      },
      tracking: {
        evaluated_frames: 0,
        detected_fraction: 0,
        torso_valid_fraction: 0,
        wrist_pair_valid_fraction: 0,
        full_body_valid_fraction: 0,
        border_contact_fraction: 0,
        interpolated_fraction: 0,
        largest_torso_gap_seconds: 0,
        largest_wrist_gap_seconds: 0,
        torso_jump_count: 0,
        keypoint_coverage: {},
      },
      tempo: { eligible: false, reasons: ["Need markers"] },
      posture: { eligible: false, reasons: ["Need view"] },
      issues: [],
    },
    warnings: ["No usable movement"],
    series: [],
  },
  coaching: { version: "1.0.0", faults: [], drills: [], notices: [] },
  prompt_payload: "Act as a master golf professional. Test-only prompt.",
};
const options: AnalysisOptions = {
  camera_view: "unknown",
  camera_alignment_confirmed: false,
  estimate_events: true,
  confirm_constant_frame_rate: false,
  include_pose: true,
};
class FakeXHR {
  static instances: FakeXHR[] = [];
  static hold = false;
  static response: unknown = result;
  headers = new Headers();
  body: FormData | null = null;
  status = 200;
  responseText = "";
  timeout = 0;
  upload: { onprogress?: (event: ProgressEvent) => void; onload?: () => void } =
    {};
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  constructor() {
    FakeXHR.instances.push(this);
  }
  open(method: string, url: string) {
    assert.equal(method, "POST");
    assert.equal(url, "/api/v1/analyses");
  }
  setRequestHeader(key: string, value: string) {
    this.headers.set(key, value);
  }
  send(body: FormData) {
    this.body = body;
    if (!FakeXHR.hold)
      queueMicrotask(() => {
        this.responseText = JSON.stringify(FakeXHR.response);
        this.upload.onload?.();
        this.onload?.();
      });
  }
  abort() {
    this.onabort?.();
  }
}
const original = globalThis.XMLHttpRequest;
globalThis.XMLHttpRequest = FakeXHR as unknown as typeof XMLHttpRequest;
after(() => {
  globalThis.XMLHttpRequest = original;
});
const file = new File(["test-only"], "swing.webm", { type: "video/webm" });

test("browser uploads require no AI credential and return the generated prompt", async () => {
  const phases: string[] = [];
  const response = await uploadAnalysis(
    file,
    options,
    new AbortController().signal,
    (progress) => phases.push(progress.phase),
  );
  const xhr = FakeXHR.instances.at(-1)!;
  assert.equal(xhr.headers.get("X-OpenAI-API-Key"), null);
  assert.equal(xhr.headers.get("Authorization"), null);
  assert.equal(xhr.headers.get("Content-Type"), null); // Browser must generate the multipart boundary.
  assert.ok(!("llm_enabled" in JSON.parse(String(xhr.body?.get("options")))));
  assert.equal(response.prompt_payload, result.prompt_payload);
  assert.ok(xhr.body?.get("video") instanceof File);
  assert.deepEqual(phases, ["uploading", "analyzing"]);
  assert.equal(response.analysis_id, result.analysis_id);
});
test("canceling an active transfer rejects with AbortError", async () => {
  FakeXHR.hold = true;
  try {
    const abort = new AbortController();
    const promise = uploadAnalysis(file, options, abort.signal, () => {});
    abort.abort();
    await assert.rejects(promise, { name: "AbortError" });
  } finally {
    FakeXHR.hold = false;
  }
});
test("invalid server payloads never enter dashboard state", async () => {
  FakeXHR.response = { analysis_id: "incomplete" };
  try {
    await assert.rejects(
      uploadAnalysis(file, options, new AbortController().signal, () => {}),
      /incomplete/,
    );
  } finally {
    FakeXHR.response = result;
  }
  assert.equal(
    analysisResponseSchema.safeParse({ ...result, prompt_payload: " " })
      .success,
    false,
  );
  assert.equal(
    analysisResponseSchema.safeParse({ ...result, prompt_payload: undefined })
      .success,
    false,
  );
  assert.equal(
    analysisResponseSchema.safeParse({
      ...result,
      kinematics: { ...result.kinematics, tempo_ratio: Infinity },
    }).success,
    false,
  );
});

test("response validation preserves prompt whitespace for exact copying", () => {
  const prompt = "Act as a master golf professional.\nKINEMATIC_JSON\n{}\n";
  assert.equal(
    analysisResponseSchema.parse({ ...result, prompt_payload: prompt })
      .prompt_payload,
    prompt,
  );
});
