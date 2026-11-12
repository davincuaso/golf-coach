# Open-source model evaluation for single-camera golf clips

The current user capture is one angle per swing, with varied angles across a
session, and no launch monitor. Keep those swings separate. Calibrated stereo
needs simultaneous views of the same swing; it cannot combine these into one 3D
motion. Ball tracking is the primary available path for the existing recordings.

## Installed experimental detector

Source: [notjulietxd/golf-ball-tracker](https://huggingface.co/notjulietxd/golf-ball-tracker).
The publisher provides a YOLOv8-nano ONNX checkpoint and labels its model card
Apache-2.0. Training mixes sports-ball images and synthetic golf balls; the card
explicitly says night/low-light conditions were not specifically trained. Its
reported benchmark is a publisher claim, not a validation on this app's footage.
Model/data/upstream licensing still needs deployment review; no binary is committed.

Install the exact evaluated file, from the project root:

```sh
.venv/bin/python backend/scripts/download_ball_model.py
```

The script pins file revision `d8c3317b211bb7c0592d97111d79519a610fd775`, bounds
download size, checks SHA-256, and never uploads media or executes hub Python code.
The file is about 12.4 MB and lives in ignored `backend/models/`.

Published [file checksum](https://huggingface.co/notjulietxd/golf-ball-tracker/blob/main/best.onnx):
`9e948135c9898c2b0e4194fa992308a0bbb478e21f6407dda12cb49e3e91ac22`.

Restart the backend after installing. The default installed file is detected
automatically. OpenCV DNN runs the ONNX locally; no extra model runtime or paid API
is needed. A configured missing model returns an error. With no installed model,
the app exposes its fixed-camera appearance baseline explicitly.

The adapter was checked against actual model inference: output is `(1, 5, 8400)`
with **normalized** XYWH, unlike a typical pixel-coordinate YOLO export. The
adapter scales correctly, letterboxes cropped input, applies NMS, associates with
the selected seed, rejects ambiguous candidates, and stops on the first missed
detection. It never fills in a predicted trajectory. Every point retains its
source (model, appearance match, manual seed). Confidence is not an accuracy score.

For a different trusted single-class YOLOv8 ONNX export, set server-only
`GOLF_BALL_WEIGHTS` and explicitly declare `GOLF_BALL_COORDINATE_UNITS=pixels` or
`normalized`. Unknown custom export units are rejected. No arbitrary checkpoint
or model URL can be supplied through an analysis request.

## What the private clip check established

A local check on a night-range recording located the visible ball around address/
impact and then lost detection as the shot began. The result remained
`insufficient_data`: the short, near-stationary observations did not establish a
flight path. Camera/background motion was also flagged. This is a smoke check,
not a labelled detection/trajectory accuracy benchmark. Private frames/traces
remain under ignored `data/`; they are not sent to the hub or published.

The model path permits handheld image-plane tracking, while flagging camera or
background movement. Such a trace includes camera movement and cannot establish
true launch angle or curve. The appearance baseline still requires a fixed camera.

## Alternatives researched

- [TrackNetV5-Golf](https://github.com/carnhy/tracknetv5-golf): a temporal approach
  aimed at golf broadcast tracer overlays, using consecutive frames and candidate
  association. It is a candidate for a trained golf-flight adapter, but a reusable
  checkpoint and reuse license were not verified in the inspected repository
  listing. Its broadcast results do not establish performance on handheld night
  range clips. No code or weights from that project were installed.
- [PiTrac](https://github.com/PiTracLM/PiTrac): a DIY camera-based launch monitor,
  requiring its capture hardware/setup rather than just ordinary phone clips.
  Its [model license](https://github.com/PiTracLM/PiTrac/blob/main/LICENSE.MODEL.md)
  is separate from its open-source software license. Its trained models are not a
  freely interchangeable software-only dependency for this app.
- [GCFive](https://github.com/VGLALALA/GCFive): high-speed camera capture, ball
  detection, spin work and trajectory simulation. Useful reference architecture;
  its specialised camera images and supplied launch conditions differ from a
  distant ball in normal-speed range footage. A simulator needs launch inputs;
  it does not measure missing inputs from a video.
- [Where Is The Ball](https://where-is-the-ball.github.io/): monocular 3D trajectory
  research. The inspected project page still labels code/data as coming soon and
  does not establish a deployable golf launch estimator. Learned reconstruction
  would require a separate uncertainty/validation path, not a metric-calibration label.

## What single-camera footage can support

Start with reviewed visible pixel positions, tracking loss, camera-motion notices,
and shot identity. Do not convert screen-space slopes into a physical launch angle
or imply that a predicted arc was observed. Spin needs suitable measurement
evidence; carry requires observed/validated distance information or an explicitly
labelled model with independently supplied launch conditions. No such physical
estimator is claimed here.

The next accuracy step is a consented labelled set of real flight frames, including
night footage and hard negatives. Split evaluation by swing/session, benchmark
detector precision/recall and track errors, and then compare temporal models or
fine-tune. Better lighting, sharp high-frame-rate capture, a stationary view and
keeping the ball in frame are practical capture improvements. The current app
keeps unsupported values unknown instead of inventing launch-monitor readings.
