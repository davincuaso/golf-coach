# Phase 3: FastAPI and hybrid coaching

Implemented modules:

- `backend/app/coaching/kinematics.py`: typed Phase 2 JSON ingestion, 2D spine
  measurements, timestamp-based tempo and optional wrist-event estimates.
- `backend/app/coaching/rule_engine.py`: deterministic posture/tempo observations
  with evidence, versioned thresholds and a concrete drill catalog.
- `backend/app/coaching/llm_synthesizer.py`: optional request-scoped OpenAI client,
  structured response validation and graceful rule-only fallback.
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

The backend token authorizes this server; it is separate from an OpenAI key.
Every `/api/v1/*` request requires `Authorization: Bearer <backend token>`.
The local client reads this server token from your backend settings:

```sh
python scripts/analyze.py ../data/swing.mp4 --view down_the_line
python scripts/analyze.py ../data/swing.mp4 --view down_the_line --events 0.3 1.2 1.5 --overwrite
python scripts/analyze.py ../data/swing.mp4 --view down_the_line --events 0.3 1.2 1.5 --llm --overwrite
```

`--llm` prompts for the OpenAI key with hidden input. It sends the key only in
`X-OpenAI-API-Key`, never a command-line argument or environment variable. The
returned analysis is saved under ignored `data/`. Use markers measured on your
own clip; the example times are illustrative, not universal.

## Endpoint contracts

`POST /api/v1/analyses` accepts multipart data with one `video` file and an optional
`options` string containing JSON. MP4, MOV, WebM, AVI and M4V suffixes are accepted;
the actual codec must be decodable by OpenCV. Model input is decoded video,
regardless of the filename or supplied MIME type.

```json
{
  "camera_view": "down_the_line",
  "events": {"start_seconds": 0.3, "top_seconds": 1.2, "impact_seconds": 1.5},
  "estimate_events": true,
  "confirm_constant_frame_rate": false,
  "subject_point": [0.5, 0.5],
  "llm_enabled": false,
  "include_pose": true
}
```

All fields are optional. `camera_view` defaults to `unknown`. Markers are seconds
from the first decoded frame and must satisfy start < top < impact within the clip.
`subject_point` is only needed to select among people. Omit it when unnecessary.
`confirm_constant_frame_rate` is an explicit assertion about the source when
decoder timing was unavailable; leave false for unknown or variable-rate footage.

`POST /api/v1/analyses/storage` accepts JSON:

```json
{"object_path": "swings/session/swing.mp4", "options": {"camera_view": "down_the_line"}}
```

Configure `GOLF_SUPABASE_URL`, `GOLF_SUPABASE_SERVICE_KEY`, `GOLF_STORAGE_BUCKET`
and `GOLF_STORAGE_PREFIX`. With bucket `swings` and prefix `swings`, that example
means the object `swings/session/swing.mp4` inside bucket `swings`. The API uses a
private authenticated download. Redirects, encoded path traversal, other prefixes
and external URLs are rejected. The service key is only sent to the configured
HTTPS origin, and never to OpenAI or the pose worker.

`POST /api/v1/coaching` consumes existing Phase 2 JSON, avoiding repeated inference:

```json
{"vision": {"schema_version": "1.0.0", "video": "...", "frames": "..."}, "options": {"include_pose": false}}
```

The abbreviated `vision` object above must be replaced with actual Phase 2 output.
Responses contain `analysis_id`, `kinematics`, `coaching`, `llm` and optionally
`pose`. `kinematics.series` is timestamp-aligned for future charts. `pose.frames`
contains the validated landmark data for overlays. Unused Phase 2 metadata is
discarded in this API contract. Every response has `Cache-Control: no-store`.

## LLM behavior and key lifecycle

- No BYOK header: rule-only analysis; no OpenAI client is created.
- BYOK header and no explicit toggle: synthesize the flagged evidence.
- `llm_enabled: false`: always rule-only, even if a header was supplied.
- `llm_enabled: true` without a header: HTTP 422 before starting processing.
- No supported fault: synthesis is skipped, avoiding an unnecessary model call.
- Provider refusal, invalid output, auth/rate/network error or timeout: HTTP 200
  with completed metrics/rules, `llm.status="unavailable"` and no narrative.

Each enabled request creates and closes its own client with the supplied key.
There is no key field in server settings, shared client, task payload, result
file or model prompt. The fixed OpenAI endpoint ignores environment overrides,
and the HTTP transport ignores environment proxy settings. SDK debug logging is
disabled. Error responses do not include validation inputs or provider exception
text. Keys are not persisted or deliberately logged; Python cannot guarantee
zeroization of immutable strings in process memory. Terminate TLS before exposing
the API outside localhost, and configure proxies/APM to redact authorization and
BYOK headers and omit request bodies.

The synthesis input is a compact metric/rule/drill report, with no raw video,
pose trace, filenames or storage paths. Structured output can reference only
supplied fault codes and drill IDs. The API uses `store=False`; this disables
Responses storage, not all provider-side retention policies. See the official
[structured output guide](https://developers.openai.com/api/docs/guides/structured-outputs)
and [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create).

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
a declared down-the-line view. It does not diagnose early extension, pelvis
movement, or a root cause. Camera roll/perspective still affect the result.

Tempo is backswing seconds divided by downswing seconds. The default 2.5–3.5
reference range is a configurable practice choice, not a universal standard.
Nominal-FPS timing does not enable tempo screening unless CFR is confirmed.

If no markers are supplied, the heuristic requires a stable initial address,
a sufficiently large wrist departure and one unambiguous return. Missing wrists,
multiple cycles or incomplete motion leave events/tempo unknown. Estimated
impact is a wrist-return proxy and must be confirmed before technique changes.
The returned wrist speed is torso lengths per second, not clubhead speed.

## Operational boundaries

This Phase 3 server is a single-tenant API: every backend token holder can access
the configured storage prefix. It is not a multi-user identity/RLS implementation.
The future browser UI must not embed the server bearer token or Supabase service
key; a trusted Next.js server boundary or per-user backend auth is required.
The Phase 4 UI now uses a protected Next.js server route; see
[the frontend guide](phase-4-frontend.md). Browser direct-to-storage uploads and
user-owned storage policies remain separate integration work.

Default input limit is 100 MiB and 30 seconds; request bodies get an additional
1 MiB multipart allowance. There are at most four active API requests per analysis
slot. Extra analyses return 503, rather than forming an unbounded queue. Slots
are per server process; use one API worker or coordinate capacity externally.
Native decoding/model inference runs in a subprocess, with a wall deadline,
CPU/file limits on POSIX and an additional address-space cap on Linux. Worker
environments contain no server/service/BYOK credentials. Task cancellation kills
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

The API smoke test uses a temporary token and a real YOLO subprocess. Unit tests
exercise OpenAI's actual SDK against a mock HTTP transport, with no paid API call.
No live Supabase credentials or user OpenAI key were used during verification.
