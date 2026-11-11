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
    warnings: ["No usable movement"],
    series: [],
  },
  coaching: { version: "1.0.0", faults: [], drills: [], notices: [] },
  llm: { status: "disabled", narrative: null, reason: null },
};
const options: AnalysisOptions = {
  camera_view: "unknown",
  estimate_events: true,
  confirm_constant_frame_rate: false,
  llm_enabled: false,
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

test("the browser omits a remembered key whenever synthesis is off", async () => {
  const phases: string[] = [];
  const response = await uploadAnalysis(
    file,
    options,
    "sk-remembered-test",
    new AbortController().signal,
    (progress) => phases.push(progress.phase),
  );
  const xhr = FakeXHR.instances.at(-1)!;
  assert.equal(xhr.headers.get("X-OpenAI-API-Key"), null);
  assert.equal(xhr.headers.get("Authorization"), null);
  assert.equal(xhr.headers.get("Content-Type"), null); // Browser must generate the multipart boundary.
  assert.equal(JSON.parse(String(xhr.body?.get("options"))).llm_enabled, false);
  assert.ok(xhr.body?.get("video") instanceof File);
  assert.deepEqual(phases, ["uploading", "analyzing"]);
  assert.equal(response.analysis_id, result.analysis_id);
});
test("enabled synthesis sends the dynamic key in the header, never in form data", async () => {
  await uploadAnalysis(
    file,
    { ...options, llm_enabled: true },
    "sk-request-test",
    new AbortController().signal,
    () => {},
  );
  const xhr = FakeXHR.instances.at(-1)!;
  assert.equal(xhr.headers.get("X-OpenAI-API-Key"), "sk-request-test");
  assert.doesNotMatch(String(xhr.body?.get("options")), /sk-request-test/);
  await assert.rejects(
    uploadAnalysis(
      file,
      { ...options, llm_enabled: true },
      undefined,
      new AbortController().signal,
      () => {},
    ),
    /Add your OpenAI key/,
  );
  assert.equal(FakeXHR.instances.at(-1)!.body, null);
});
test("canceling an active transfer rejects with AbortError", async () => {
  FakeXHR.hold = true;
  try {
    const abort = new AbortController();
    const promise = uploadAnalysis(
      file,
      options,
      undefined,
      abort.signal,
      () => {},
    );
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
      uploadAnalysis(
        file,
        options,
        undefined,
        new AbortController().signal,
        () => {},
      ),
      /incomplete/,
    );
  } finally {
    FakeXHR.response = result;
  }
  assert.equal(
    analysisResponseSchema.safeParse({
      ...result,
      kinematics: { ...result.kinematics, tempo_ratio: Infinity },
    }).success,
    false,
  );
});
