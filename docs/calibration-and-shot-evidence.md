# Calibrated 3D and shot-result evidence

Open **Sessions**, analyze the relevant windows, then expand **Movement. Launch.
Result.** Three evidence tools feed the combined session prompt and JSON export.
There is no paid AI API or automatic submission to ChatGPT.

## 1. Capture and calibrate two cameras

3D reconstruction needs the **same physical swing**, recorded simultaneously by
two fixed cameras. A collection of separate swings from different angles cannot
be triangulated into one swing. The previously supplied range clips have no
shared camera calibration or verified synchronization; the app cannot recover
calibrated 3D from those alone.

Use a pinhole-compatible lens with fixed zoom/focus, matching resolution and
decoded orientation throughout calibration and the swing. Disable electronic
stabilization, reframing, mirroring, and slow-motion time stretching. Camera
movement, focus breathing, rolling shutter, and exposure blur remain error sources.
Keep both cameras above the level ground reference, with clear views and a useful
baseline; do not place them nearly along the same viewing ray.

For each camera:

1. Photograph a complete, flat checkerboard in **10–60 varied positions and
   orientations**, covering the image area. Use a physically measured square size.
   `columns` and `rows` below count **inner corners**, not squares.
2. Without moving either camera, place the checkerboard flat on level ground in
   a shared reference position. Photograph this same stationary board from both
   cameras. Columns run right of the target (+X), rows run down the target (+Z),
   and +Y is vertically up. The reference origin is inner corner 0.
3. Create a manifest per camera. Paths are relative to the manifest directory:

```json
{
  "camera_id": "camera-a",
  "world_id": "range-session-rig-1",
  "columns": 9,
  "rows": 6,
  "square_size_m": 0.025,
  "images": ["calibration-01.jpg", "calibration-02.jpg", "...replace with 10–60 actual paths..."],
  "world_reference_image": "shared-ground-reference.jpg",
  "reverse_reference_order": false
}
```

Run from the project root with the existing Python environment:

```sh
.venv/bin/python backend/scripts/calibrate_camera.py data/calibration/a/manifest.json --output data/calibration/camera-a.json
.venv/bin/python backend/scripts/calibrate_camera.py data/calibration/b/manifest.json --output data/calibration/camera-b.json
```

The tool uses OpenCV checkerboard corners, lens calibration, distortion parameters,
and a ground-board `solvePnP` reference pose. Near-identical board positions and
sets with less than 10° of estimated board-normal variation are rejected as
insufficient calibration views; these guards do not certify calibration accuracy.
Each output has a labelled
`.reference.jpg`. **Check that labelled corner IDs identify the exact same physical
corners in both reference images.** A symmetric checkerboard can be detected
180° apart. If necessary, reverse one reference ordering and regenerate to a new
output path. Mark the physical origin and row/column directions to resolve this
ambiguity. A shared `world_id` is a label, not proof of a shared coordinate system.

Outputs default to `scale_and_orientation_verified: false`. The browser's explicit
verification checkbox enables use after you inspect the labelled references and
confirm the square size, level ground, axes and camera positions. Existing output
files are protected from overwrite. Keep calibration images/profiles under ignored
`data/`, rather than publishing them.

## 2. Synchronize and reconstruct

Add both videos, assign the same Swing ID, and analyze them. Select each profile
against the corresponding camera. Enter a shared flash/trigger event's time in
seconds **relative to each selected video window**. These are synchronization
anchors, not the estimated swing-impact markers. Confirm original physical timing.

Supply a defensible synchronization uncertainty of at most **10 ms**. A single
frame match at 30 fps (about 33 ms per frame) cannot establish that precision on
its own. Use verified timing hardware or a timing signal/capture method with
known uncertainty; do not enter a small number just to enable reconstruction.
No automatic flash detector, audio synchronization, or rolling-shutter correction
is implemented.

The engine:

- Requires two distinct, server-attested analyses of the same declared swing.
- Validates camera matrices, rotations, shared reference, matching decoded
  dimensions, scale/orientation confirmation, calibration/reference RMS ≤2 px,
  camera heights 0.2–5 m, and baseline 0.2–20 m.
- Uses raw observed landmarks (confidence ≥0.6); interpolated and absent raw
  observations are excluded. Independent 2D smoothing does not enter triangulation.
- Matches each second-camera frame at most once. Timestamp mismatch plus declared
  synchronization uncertainty must be ≤20 ms. Decoder timestamps are required.
- Undistorts points and triangulates with metric extrinsics. Rejects negative
  camera depth, near-parallel rays (<3°), >4 px reprojection error, and points
  outside a 30 m capture volume. It fills no gaps and extrapolates nothing.
- Returns individual joint XYZ estimates, rejection counts, timing mismatch,
  reprojection errors, and descriptive 3D torso tilt. The viewer supports frame
  selection and rotation; exports retain the complete reconstructed trace.

Limits: two cameras, 1,800 frames per view, 16 MiB request body. These thresholds
are engineering safeguards, not an accuracy certification. Low reprojection error
does not prove correct anatomical landmarks. There are no validated 3D technique
rules, pelvis diagnoses, clubhead-speed calculations, or 3D ball-flight estimates
in this release. Hardware/camera ground-truth validation remains necessary.

## 3. Visible-ball candidate tracking

Choose the source video, pause at or immediately before impact, select the ball,
and supply its approximate radius in **decoded pixels** (2–20). Declare camera
stability accurately; a fixed camera gives clearer motion evidence. The source is uploaded again; its SHA-256 must match the signed source
analysis, preventing accidental mixing of recordings.

Install the experimental local detector with
`.venv/bin/python backend/scripts/download_ball_model.py`, then restart the backend.
The pinned ONNX model runs through OpenCV DNN, with seed association, confidence,
nonmaximum suppression and ambiguity checks. It retains model provenance and point
sources. No clips are uploaded to a model service. See [the model evaluation](open-source-ball-models.md)
for the checked file hash, export-coordinate handling, training limitations and
alternatives researched.

Choose up to five seconds; the worker also stops at 480 decoded frames or its hard
wall deadline. It stops on the first missed/ambiguous detection rather than adding
predicted points. Handheld traces remain in source-image coordinates, and camera/
background movement is flagged. They cannot establish physical launch or curvature.

Without an installed model, a clearly labelled fixed-camera appearance baseline
is available. It requires the stationary confirmation, checks contrast and template
uniqueness, and stops on camera/background change. Every trace still needs visual
review: similar balls, lights, motion blur and changing apparent size can defeat
both approaches. No binary model is committed to the repository.

The result is explicitly `candidate_track` or `insufficient_data`. It preserves
source timestamps, pixel coordinates, match scores and the stop reason. The app
draws no guessed continuation and computes no physical speed, carry, spin or launch
direction from a monocular pixel path. The supplied night-range clips may have too
little ball visibility for a useful trace. A golf-specific labelled detector and
validated tracker are needed before treating this as reliable automatic ball ID.

## 4. Launch-monitor import and intent checks

Use the downloadable CSV/JSON template, or **Enter one shot**. Import one to eight
rows, with one monitor shot per physical Swing ID. Every row requires a unique
`shot_id` and `swing_id`. Optional `recorded_at` uses ISO 8601 with a timezone.
Matching is explicit by Swing ID; no timestamp-nearest guess assigns your shots.

The format is deliberately vendor-neutral. Vendor exports must be mapped to it;
there are no undocumented vendor API calls or guessed column/unit mappings.
CSV column names and equivalent flat JSON row keys:

```csv
shot_id,swing_id,recorded_at,ball_speed,ball_speed_unit,ball_speed_method,launch_direction,launch_direction_unit,launch_direction_method,carry,carry_unit,carry_method
shot-1,Swing 1,,150,mph,measured,1,deg,measured,160,yd,device_calculated
```

That row is an illustrative format example, not a reading from your footage.
For any populated metric, add `<metric>_unit` and `<metric>_method`:

- Speed: `ball_speed`, with `m/s`, `mph`, or `km/h`.
- Distances: `carry`, `total_distance`, `apex`, `offline`, with `m`, `yd`, or `ft`.
- Angles: `launch_angle`, `launch_direction`, `spin_axis`, with `deg`.
- Spin: `spin_rate`, with `rpm`.
- Method: `measured`, `device_calculated`, `manual`, or `unknown`. Missing methods
  stay unknown and do not support within/outside-intent checks.

Unknown columns, duplicate shot/swing IDs, malformed dates, incompatible/missing
units, nonfinite values, and implausible ranges are rejected. Limits after unit
conversion: speed 0–120 m/s; launch angle −20–90°; direction ±90°; spin 0–20,000 rpm;
spin axis ±180°; carry 0–500 m; total 0–600 m; apex 0–150 m; offline ±200 m.
Original values/units and per-field methods remain in the response. Imports are
user-supplied readings, not authenticated live device telemetry.

Set source conditions (outdoor, indoor, normalized, unknown) and verify the vendor's
sign conventions. Canonical launch direction/offline is positive right of target.
Spin-axis sign is separate: explicitly choose what positive means for curve tendency,
or leave it unknown. Handedness changes the draw/fade interpretation. Shape is only
a **spin-axis tendency**, with a configurable straightness tolerance (UI default 5°),
not an observed downrange curve. Wind and other conditions can change actual flight.

Set your intended carry range (metres), launch-direction range, landing corridor,
shape and handedness. Carry assessment is unavailable until both target bounds are
set. A deliberate draw/fade is compared with that intent, not automatically called
a fault. Imported carry/offline is displayed as landing dispersion; no ballistic
parabola is presented as observed flight. Modelled/normalized carry remains labelled.

## API, privacy and session integration

All endpoints require the existing backend bearer authentication; the browser uses
fixed same-origin server proxies. API paths bypass body-cloning page middleware.

- `POST /api/v1/reconstructions`: JSON `ReconstructionRequest` (OpenAPI schema),
  with two camera profiles, original pose documents, signed `analysis_token`s,
  synchronization anchors and capture confirmations.
- `POST /api/v1/ball-tracks`: multipart `video` and JSON `options` containing
  `swing_id`, `analysis_token`, normalized `seed_point`, `seed_source_seconds`,
  `radius_px`, `duration_seconds` (≤5 at API level), and `stationary_confirmed` (optional camera-stability declaration for the model, required by the appearance baseline).
  Video processing uses the existing isolated worker, resource limits and cleanup.
- `POST /api/v1/shot-imports`: JSON `format`, `content`, `device`,
  `positive_direction`, `positive_spin_axis_curve`, `conditions`, and `intent`.
  Request body ≤1 MiB and content ≤500,000 characters.
- `POST /api/v1/sessions`: optional `evidence_tokens` array includes the signed
  summaries returned above. Signatures expire after 24 hours or secret rotation.
  Mismatched/replaced analysis IDs or moved swing groups are rejected. Tokens do
  not grant endpoint access. They authenticate summaries, not the truth of supplied
  calibration, sync claims, or imported monitor readings.

Changing evidence inputs invalidates the attached result. Reanalyzing a source
clears attached evidence. Refresh the session report to include completed evidence
in `additional_evidence` and the manual coaching prompt. Save session also exports
full 3D and pixel traces. As before, sessions live in memory until exported.

Tests validate synthetic metric geometry with lens distortion, calibration solving,
timing/view gates, pose/source attestation, ball-loss/ambiguity behavior, units,
provenance, handedness, intent, malformed imports, and authenticated routes. They
do not establish golf-specific accuracy or certify a physical camera rig.

Primary references: [OpenCV calibration and triangulation](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html),
[OpenCV checkerboard calibration](https://docs.opencv.org/4.13.0/d4/d94/tutorial_camera_calibration.html),
[Titleist launch conditions](https://www.titleist.com/learning-lab/performance/golf-shot-launch-conditions),
[Trackman measurement definitions](https://support.trackmangolf.com/hc/en-us/articles/5089892383515-Practice-Trackman-Data-Parameter-Definitions).
