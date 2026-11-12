# Accuracy improvements and ball-flight roadmap

## Implemented: camera and tracking checks

The app accepts down-the-line, face-on, oblique, rear-body, overhead, and unknown
view labels. It assesses each measurement separately. Manual tempo can remain
usable from an oblique view while posture changes are withheld. Declaring a view
does not calibrate the camera or recover depth.

Posture comparisons now require all of:

- A declared down-the-line view and explicit confirmation that the camera is
  level, stationary, and aligned down the target line.
- Usable address/downswing/impact torso measurements.
- Adequate tracking coverage without long torso gaps or abrupt torso jumps.
- No broad body-projection conflict with the declared down-the-line view.

The projection check compares shoulder/hip horizontal span with projected torso
length around address. It reports a narrow/broad/mixed/unknown hint. **It is an
engineering heuristic, not a trained camera-angle classifier, camera calibration,
or probability of correctness.** Front/rear ambiguity and perspective remain.
Conservative false rejections are possible; labelled validation is required before
treating any threshold as a golf-accuracy guarantee.

Each kinematics response now includes `quality`, with camera assessment, per-joint
and group sample coverage, interpolation fraction, border contact, longest gaps,
abrupt torso jumps, metric eligibility/reasons, and capture suggestions. Coverage
counts usable observed, confident, filtered, in-image samples. It is not pose
accuracy. If markers are available, tracking checks cover start through impact;
otherwise they cover the whole clip. Post-swing movement therefore does not pollute
a marked swing's quality score. Estimated swing markers produce provisional metrics. Technique/tempo faults are
withheld until the user reviews the events and reanalyzes with manual markers.
The descriptive 2D projection chart remains
available, but gated posture scalars and coaching faults are withheld.

The browser supports selecting the golfer by clicking their torso in the first
analyzed frame (the beginning of the selected source window in Sessions).
Selection maps through letterboxing into normalized decoded-video coordinates;
clicks on the bars are rejected. This helps ranges with nearby golfers. A missing
selected subject gets an explicit retry/selection message. Clips over 30 seconds
get an early duration warning when browser metadata is available. Byte/duration
limits remain independently enforced by the backend.

The offline CLI accepts the expanded `--view` labels and
`--confirm-camera-alignment`. Only confirm alignment for an actual down-the-line
setup. New API callers can send `camera_alignment_confirmed: true`; its default
is false. Older clients continue to analyze footage, with posture screening
withheld until explicitly confirmed. Restart backend and frontend together.

## Implemented: multi-video sessions and swing windows

Sessions accept multiple recordings and explicit source-window selection, including
several swings from one longer recording. Linked views retain one physical swing
ID; separate swings contribute independently. Reviewed, quality-gated session
statistics preserve per-metric sources and withhold conflicting readings. See
[the session guide](multi-video-sessions.md).

## Next: automatic swing preparation

Long range recordings often contain setup, multiple swings, bystanders, and camera
movement. Benchmark automatic cycle segmentation against manually marked
starts/tops/impact before replacing the explicit window selector.
Keep original timestamps and slow-motion playback metadata; re-encoding a clip
can change its timebase. Do not silently infer physical speed from a slowed export.

Improve capture guidance: a tripod, an unobstructed full-body frame with club room,
short clips, adequate light, and higher capture FPS when studying impact. More FPS
alone does not fix motion blur or dark exposures. Confirm the actual decoded FPS.

## Next: validate pose models on golf

Create a consented, private labelled dataset with varied views, lighting, clothing,
body proportions, club types, and occlusion. Split by golfer/session, not adjacent
frames, to avoid evaluation leakage. Measure per-view keypoint error, event timing
error in milliseconds, and precision/recall of coaching flags against reviewed
reference labels. Report unknown/withheld rates alongside errors.

Benchmark larger pose checkpoints and a richer landmark adapter on these same
clips before switching models. Generic COCO pose scores do not establish golf
accuracy. MediaPipe's 33 predicted landmarks/3D world coordinates are a candidate
for comparison, not calibrated ground truth. Fine-tune only with appropriate data
and licensing. Retain observed/interpolated/confidence provenance in every adapter.

For stronger cross-view body measurements, use calibrated synchronized cameras
capturing the **same swing**. Separate swings filmed from different positions do
not provide a valid stereo reconstruction. A single-view learned 3D estimate must
be presented with uncertainty and validated for golf-specific positions.

## Next: ball-flight analysis with two evidence paths

The next module should assess both direction/curve and launch/carry when evidence
supports them. Define the intended shot first: target line/corridor, target distance,
club, handedness, and desired straight/draw/fade shape. A deliberate fade is not
automatically a fault. Compare results with that intent and the measurement's
uncertainty, rather than labelling every non-straight shot incorrect.

### Video tracking

Use a dedicated small-ball detector and a temporal tracker, separate from body
pose. Start from a confirmed ball position and impact window, restrict the region
of interest, stabilize background motion, and reject nets, lights, other balls,
and another golfer's shot. Track with detection confidence, temporal consistency,
and track-loss status. Ask for confirmation when multiple candidates are plausible.

Render only observed/interpolated segments that can be supported. Stop the tracer
when the ball is lost; a guessed parabola should not look like an observed flight.
Initially report image-plane trajectory and visibility. A 2D path alone does not
establish true launch direction, spin, or full carry. A ground-plane homography
does not recover an airborne ball's depth.

At 30 fps, a ball travelling 60 m/s would move 2 m between frames. That is an
illustration, not a measured speed from the supplied footage. Exposure blur,
small apparent size, and an early exit from frame further limit these recordings.
Metric launch estimates require a calibrated camera/timebase and documented
assumptions; spin generally needs suitable dedicated measurement evidence.

### Launch-monitor fusion

Start with a vendor-neutral CSV/JSON or manual import rather than assuming a
vendor provides an accessible live API. Match every import to a shot ID and
timestamp. Map units and conventions for ball speed, launch angle, target-relative
launch direction, spin rate/axis, carry, apex, and offline distance. Preserve missing
fields, device/source, and whether each field was measured, calculated by the
monitor, or manually entered. Indoor carry may be modelled rather than observed.

Use monitor data for supported physical measurements and video for movement and
visible flight context. Cross-check disagreement; do not silently average
incompatible readings. Range balls, wind, elevation, and normalization settings
must remain explicit. Keep shot-result evidence separate from hypothesized swing
causes in the manual ChatGPT prompt.

## Verification boundaries

Synthetic geometry tests verify the gates, not real-world pose accuracy. Private
video checks test decoding, portrait orientation, subject continuity, and available
tracking across views. Manually labelled swing events, calibrated body/ball ground
truth, and monitor exports are required for an accuracy benchmark. No ball-flight
detector, measured carry/spin, or monitor integration is shipped in this first
camera-quality upgrade.

Primary references:

- [Ultralytics pose outputs and validation](https://docs.ultralytics.com/tasks/pose/)
- [MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)
- [OpenCV planar homography](https://docs.opencv.org/4.13.0/d9/dab/tutorial_homography.html)
- [Titleist launch conditions](https://www.titleist.com/learning-lab/performance/golf-shot-launch-conditions)
- [Trackman parameter definitions](https://support.trackmangolf.com/hc/en-us/articles/5089892383515-Practice-Trackman-Data-Parameter-Definitions)
