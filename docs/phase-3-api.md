# FastAPI, rule-based coaching, and prompt generation

Implemented modules:

- `backend/app/coaching/kinematics.py`: typed Phase 2 JSON ingestion, 2D spine
  measurements, timestamp-based tempo and optional wrist-event estimates.
- `backend/app/coaching/rule_engine.py`: deterministic posture/tempo observations
  with evidence, versioned thresholds and a concrete drill catalog.
- `backend/app/coaching/llm_synthesizer.py`: deterministic, local ChatGPT prompt
  generation using full computed metrics/rules and a bounded raw trace preview.
- `backend/app/main.py`, `api/routes.py`, `api/middleware.py`: HTTP endpoints,
  early authorization, bounded uploads, CORS and private responses.
- `backend/app/services/analysis.py`, `vision/worker.py`: one isolated process per
  video, bounded concurrency, deadlines, task cancellation and temporary cleanup.
- `backend/app/storage.py`: streamed private Supabase downloads from a configured
  bucket/prefix. No arbitrary URLs or server file paths are accepted.

## Start locally

From the project root:

```sh
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
python backend/scripts/init_env.py
cd backend
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

The configuration helper creates `backend/.env` with mode 0600 and a random
backend bearer token. It preserves an existing file. Adjust `GOLF_POSE_WEIGHTS`
if needed; an existing local, trusted `.pt` pose checkpoint is required. Relative
weight paths resolve against `backend/`. No model is downloaded by an API request.
Use `GOLF_POSE_DEVICE=mps` or `0` only on a tested accelerator configuration.

Interactive API documentation: `http://127.0.0.1:8000/docs`.
Liveness: `GET /health`. Liveness does not certify that a model checkpoint loads.

The backend bearer token authorizes access to this analysis service. It is not an
AI provider key. No AI provider credentials are required.
Every `/api/v1/*` request requires `Authorization: Bearer <backend token>`.
The local client reads this server token from your backend settings:

```sh
python scripts/analyze.py ../data/swing.mp4 --view down_the_line
python scripts/analyze.py ../data/swing.mp4 --view down_the_line --events 0.3 1.2 1.5 --overwrite
```

The CLI saves metrics, rule-based observations, pose data, and `prompt_payload`
under ignored `data/`. Copy the generated prompt into your own ChatGPT conversation
when you choose. Use markers measured on your clip; example times are illustrative.

## Endpoint contracts

`POST /api/v1/analyses` accepts multipart data with one `video` file and an optional
`options` string containing JSON. MP4, MOV, WebM, AVI and M4V suffixes are accepted;
the actual codec must be decodable by OpenCV. Model input is decoded video,
regardless of the filename or supplied MIME type.

```json
{
  "camera_view": "down_the_line",
  "camera_alignment_confirmed": true,
  "events": { "start_seconds": 0.3, "top_seconds": 1.2, "impact_seconds": 1.5 },
  "estimate_events": true,
  "confirm_constant_frame_rate": false,
  "subject_point": [0.5, 0.5],
  "include_pose": true
}
```

Camera views also include `face_on`, `oblique`, `rear`, `overhead`, and `unknown`.
`camera_alignment_confirmed` defaults to false; only confirm a level, stationary,
aligned down-the-line camera. Posture values and faults are withheld when the
view/quality gates do not pass. `kinematics.quality` explains every gate.

All fields are optional. `camera_view` defaults to `unknown`. Markers are seconds
from the first decoded frame and must satisfy start < top < impact within the clip.
`subject_point` is only needed to select among people. Omit it when unnecessary.
`confirm_constant_frame_rate` is an explicit assertion about the source when
decoder timing was unavailable; leave false for unknown or variable-rate footage.

`POST /api/v1/analyses/storage` accepts JSON:

```json
{
  "object_path": "swings/session/swing.mp4",
  "options": { "camera_view": "down_the_line" }
}
```

Configure `GOLF_SUPABASE_URL`, `GOLF_SUPABASE_SERVICE_KEY`, `GOLF_STORAGE_BUCKET`
and `GOLF_STORAGE_PREFIX`. With bucket `swings` and prefix `swings`, that example
means the object `swings/session/swing.mp4` inside bucket `swings`. The API uses a
private authenticated download. Redirects, encoded path traversal, other prefixes
and external URLs are rejected. The service key is only sent to the configured
HTTPS origin and never to the pose worker or generated prompt.

`POST /api/v1/coaching` consumes existing Phase 2 JSON, avoiding repeated inference:

```json
{
  "vision": { "schema_version": "1.0.0", "video": "...", "frames": "..." },
  "options": { "include_pose": false }
}
```

The abbreviated `vision` object above must be replaced with actual Phase 2 output.
Responses contain `analysis_id`, `summary_token`, `kinematics`, `coaching`, `prompt_payload` and optionally
`pose`. `kinematics.series` is timestamp-aligned for future charts. `pose.frames`
contains the validated landmark data for overlays. Unused Phase 2 metadata is
discarded in this API contract. Every response has `Cache-Control: no-store`.

## Calibrated geometry and shot evidence

Authenticated `/api/v1/reconstructions`, `/api/v1/ball-tracks`, and
`/api/v1/shot-imports` extend session evidence. Source analyses now sign a pose
digest and, for uploaded/storage videos, a media digest. Reconstruction rejects
modified poses; ball tracking rejects a different source file. Signed evidence
summaries can be included through `evidence_tokens` in `/api/v1/sessions`.
See [the measurement and setup contract](calibration-and-shot-evidence.md) and
OpenAPI for typed payloads, separate body caps and capture requirements.

## Prompt generation workflow

Every successful analysis returns a nonempty `prompt_payload` string, including
analyses with no faults or insufficient data. The application makes no AI provider
request. The former `llm` response, `llm_enabled` request option, AI model/timeout
configuration, and provider key validation have been removed. Old clients that send
`llm_enabled` receive HTTP 422 because the request schema rejects unknown options.
Legacy provider headers are ignored by FastAPI and stripped by the frontend proxy.

The prompt asks ChatGPT to act as a master golf professional, distinguish measured
observations from tentative root-cause hypotheses, cite supplied evidence, select
catalog drills, and propose a focused practice plan. It includes all scalar
kinematics, flags, evidence, quality warnings, notices, and drill instructions.
Null measurements remain null and uncertainties remain explicit.

Raw kinematic samples use compact columnar JSON. Up to 121 uniformly indexed rows
plus the samples before/after each swing event are included (at most 127). Numeric
precision and nulls are preserved. Sampling is disclosed, and the instructions
prohibit making quality/fault decisions from the preview alone. The original
`kinematics.series` remains complete in the response and JSON export. Prompt size
is bounded independently of video FPS; no pose landmarks, video, filenames,
request headers, storage paths, or server credentials enter the prompt.

The browser only opens `https://chatgpt.com` in a new tab. It does not submit data
there. Copy/paste and sending the message are deliberate user actions. See
[the prompt workflow and migration guide](prompt-workflow.md).

## Metric definitions and limits

Spine tilt is recomputed in image pixels from confident, observed, filtered
shoulders and hips. Interpolated, low-confidence, degenerate and unfiltered
measurements are excluded. Address tilt is a robust median near the supplied
start; impact tilt uses the final 0.1 seconds before impact. `spine_delta_deg`
is impact minus address; a negative value means a more upright projected torso.
`max_posture_loss_deg` compares address with short rolling medians during the
downswing only. Follow-through standing and single-frame spikes are excluded.
Coverage must be at least 80%, with no long gap in the usable downswing trace.

The posture rule flags **possible** loss of posture above 10 degrees only with
a confirmed level/stationary down-the-line view, reviewed manual swing markers,
and passing tracking/projection checks. It does not diagnose early extension, pelvis
movement, or a root cause. Camera roll/perspective still affect the result.

Tempo is backswing seconds divided by downswing seconds. The default 2.5–3.5
reference range is a configurable practice choice, not a universal standard.
Nominal-FPS timing does not enable tempo screening unless CFR is confirmed.
Fault screening also requires reviewed manual markers; estimated timings remain
provisional and do not generate actionable technique/tempo faults.

If no markers are supplied, the heuristic requires a stable initial address,
a sufficiently large wrist departure and one unambiguous return. Missing wrists,
multiple cycles or incomplete motion leave events/tempo unknown. Estimated
impact is a wrist-return proxy and must be confirmed before technique changes.
The returned wrist speed is torso lengths per second, not clubhead speed.

For detailed tracking gates, the expanded camera contract, and ball-flight plans,
see [the accuracy roadmap](accuracy-and-ball-flight.md).

## Operational boundaries

This Phase 3 server is a single-tenant API: every backend token holder can access
the configured storage prefix. It is not a multi-user identity/RLS implementation.
The browser UI does not embed the server bearer token or Supabase service
key. It uses a protected Next.js server route; see
[the frontend guide](phase-4-frontend.md). Browser direct-to-storage uploads and
user-owned storage policies remain separate integration work.

Default source upload limit is 250 MiB; request bodies get an additional
1 MiB multipart allowance. Whole-clip analyses remain limited to 30 seconds.
Longer sources require `source_start_seconds` and `source_end_seconds` selecting
a window of at most 30 seconds. Markers are relative to that window; decoded
source offset metadata aligns the overlay. `POST /api/v1/sessions` combines up to
eight signed reports without uploading their media again to that endpoint.
See [multi-video sessions](multi-video-sessions.md) for the complete contract,
reviewed aggregation rules, export behavior, and 24-hour summary-token lifetime.
There are at most four active API requests per analysis slot. Extra analyses
return 503, rather than forming an unbounded queue. Slots
are per server process; use one API worker or coordinate capacity externally.
Native decoding/model inference runs in a subprocess, with a wall deadline,
CPU/file limits on POSIX and an additional address-space cap on Linux. Worker
environments contain no server/service credentials. Task cancellation kills
the child process group and temporary folders are cleaned after success/failure.
Clients disconnecting do not necessarily cancel an ASGI request; the hard worker
deadline remains enforced. Temporary media and results are not retained by this
server; `analysis_id` is a response identifier, not a persisted job handle.

For deployment, enforce container memory/CPU/disk quotas, a read-only model mount,
ingress upload/time limits and HTTPS. Subprocess separation is not a security
sandbox for a hostile native codec. macOS address-space limits are unreliable;
hard memory isolation must come from the deployment environment. Models are loaded
per analysis for isolation, so sustained throughput will need a supervised warm
worker design. The earlier optional MediaPipe wheel metadata caveat still applies.

## Verify

```sh
../.venv/bin/python -m pytest -q
../.venv/bin/python scripts/smoke_pose.py
../.venv/bin/python scripts/smoke_api.py
```

The API smoke test uses a temporary token and a real YOLO subprocess. Prompt tests
block network connections and check evidence fidelity, nulls, trace bounds, event
neighbors, and deterministic output. No AI provider package or credentials are
needed. Private storage is tested with mock HTTP transports.
