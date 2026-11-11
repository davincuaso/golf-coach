# Vision output v1.0.0

The CLI writes a single strict JSON document, not NDJSON. Missing numeric values
are `null`; JSON never contains NaN or Infinity. Frames appear in decode order.

- `video`: original basename, SHA-256 (CLI only), decoded width/height, nominal
  FPS, decoded frame count, last-frame timestamp and timestamp source.
- `processing`: the complete configuration, dependency versions and local model
  basename/SHA-256 (CLI only). Filtering is offline and uses future frames.
- `quality`: observed landmark fraction, interpolation/filter counts and track loss.
- `skeleton_edges`: named COCO-17 connections for a future canvas overlay.
- `warnings`: limitations and data quality findings.
- `frames[]`: frame index, timestamp, person box, named landmarks, angles and club.

Each landmark includes raw pixels, stabilized pixels, normalized coordinates,
the original frame's detector confidence, and `observed`, `interpolated`,
`filtered` flags. Confidence is never copied into an occluded frame. A low
confidence measurement may be rejected but still have its original confidence
reported. An interpolated point is an estimate, even if it was later filtered.

Image coordinates use origin at the top left, x right, y down. Normalized x is
x/width and normalized y is y/height. Filtering may slightly overshoot the image
bounds; coordinates are deliberately not clamped, which would change the angles.
The future overlay must use the actual displayed video content rectangle and
account for letterboxing, CSS mirroring, and decoded video orientation. Left/right
names are anatomical model labels, not screen directions.

Angles are calculated in pixel coordinates to preserve image aspect ratio:

- `left_elbow`, `right_elbow`: shoulder–elbow–wrist, interior angle.
- `left_shoulder`, `right_shoulder`: elbow–shoulder–hip, interior angle.
- `left_hip`, `right_hip`: shoulder–hip–knee, interior angle.
- `left_knee`, `right_knee`: hip–knee–ankle, interior angle.
- `spine_tilt_2d`: shoulder-midpoint relative to hip-midpoint, angle to image-up.
  Zero is upright; a side view of an inclined torso gives a larger angle.

All angle values are degrees. Missing/degenerate required landmarks yield null.
Angle reliability comes from the contributing landmark confidence and flags;
angles using interpolated or unfiltered points are not independent measurements.

The Butterworth filter uses second-order sections, forward/backward filtering,
and a uniform time grid within each continuous span. Only short bounded gaps
are interpolated; leading/trailing and long gaps remain missing. Short spans
remain unfiltered. The 8 Hz default is a starting point for body motion and must
be validated against golf footage. It is unsuitable as an assumed club filter.

Strictly increasing decoder timestamps are preferred. If unavailable, the entire
clip uses nominal constant-frame-rate timing, explicitly marked as a fallback.
Do not use fallback timing for a variable-frame-rate tempo benchmark. Tracking
timeouts currently use nominal frame rate; resample problematic clips to CFR.

`club` is always null in this version. COCO-17 does not detect a golf club. No
physical swing speed, swing phase, tempo, diagnostic rule or 3D angle is inferred
in Phase 2. Early extension requires evidence about pelvis movement and camera
view; a threshold on this 2D spine angle alone cannot establish it. Physical
speed also requires a tracked clubhead, timebase, spatial calibration and a
validated projection model.

The tracker assumes a stationary camera and a clearly selected golfer. Bounding
box continuity is not identity recognition; crossings/overlapping people can
still defeat it. Use a cropped, single-golfer clip for dependable analysis.

Local decode limits bound file bytes, frame count, duration and decoded pixels.
They do not sandbox a native codec or impose a wall-clock inference deadline.
Phase 3 adds isolated worker processes and bounded uploads; see
[the server contract](phase-3-api.md) for platform limits and deployment requirements.
