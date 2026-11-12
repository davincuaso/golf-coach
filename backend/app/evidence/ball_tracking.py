"""Conservative user-seeded ball candidate tracking, never a flight simulator.

An optional local ONNX detector or a fixed-camera appearance baseline produces
candidates. Every trace requires visual confirmation; missed detections stop it.
"""

from pathlib import Path

import cv2
import numpy as np

from app.evidence.schemas import BallSample, BallTrackOptions, BallTrackResponse
from app.evidence.ball_detector import associate, MODEL_SHA256, MODEL_URL
from app.vision.vision_processor import VisionError


def track_ball(
    path: Path, options: BallTrackOptions, max_bytes: int, detector=None
) -> BallTrackResponse:
    if not options.stationary_confirmed and detector is None:
        raise VisionError("A fixed camera is required.")
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise VisionError("Invalid source size.")
    capture = cv2.VideoCapture(str(path))
    samples, width, height = [], 0, 0
    reason = "source_ended"
    camera_motion = False
    try:
        if not capture.isOpened():
            raise VisionError("Cannot decode source.")
        capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        if options.seed_source_seconds and not capture.set(
            cv2.CAP_PROP_POS_MSEC, options.seed_source_seconds * 1000
        ):
            raise VisionError("Cannot seek source.")
        template, previous_background = None, None
        position = None
        last_time = -1
        for index in range(480):
            ok, image = capture.read()
            if not ok:
                break
            stamp = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            if not np.isfinite(stamp) or stamp <= last_time:
                reason = "decoder_timing_unavailable"
                break
            last_time = stamp
            if stamp + 0.04 < options.seed_source_seconds:
                continue
            if stamp > options.seed_source_seconds + options.duration_seconds:
                reason = "requested_window_ended"
                break
            height, width = image.shape[:2]
            if width * height > 3840 * 2160:
                raise VisionError("Resolution exceeds limit.")
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            background = cv2.resize(gray, (max(32, width // 8), max(32, height // 8))).astype(
                np.float32
            )
            radius = options.radius_px
            if position is None:
                if abs(stamp - options.seed_source_seconds) > 0.06:
                    raise VisionError("Seed time is not decodable precisely enough.")
                x, y = (round(options.seed_point[0] * width), round(options.seed_point[1] * height))
                if x < radius or y < radius or x + radius >= width or y + radius >= height:
                    raise VisionError("Ball seed too near image boundary.")
                position = np.array([x, y], dtype=float)
                if detector:
                    selected, reason = associate(
                        detector.detect(image, position),
                        position,
                        max(12, radius * 4),
                        max(6, radius * 2),
                    )
                    if selected is None:
                        break
                    position, score = selected
                    samples.append(
                        BallSample(
                            source_seconds=stamp,
                            xy_px=tuple(position),
                            similarity=score,
                            source="model_detection",
                        )
                    )
                else:
                    template = gray[y - radius : y + radius + 1, x - radius : x + radius + 1].copy()
                    if float(template.std()) < 8:
                        reason = "seed_has_insufficient_contrast"
                        break
                    samples.append(
                        BallSample(
                            source_seconds=stamp,
                            xy_px=tuple(position),
                            similarity=1,
                            source="manual_seed",
                        )
                    )
                previous_background = background
                continue
            shift, response = cv2.phaseCorrelate(previous_background, background)
            if response < 0.15 or np.linalg.norm(shift) * 8 > 6:
                camera_motion = True
                if detector is None:
                    reason = "camera_motion_or_background_change"
                    break
            previous_background = background
            if detector:
                prediction = position.copy()
                if len(samples) >= 2:
                    previous, latest = samples[-2:]
                    delta = latest.source_seconds - previous.source_seconds
                    if delta > 0:
                        prediction += (
                            (np.asarray(latest.xy_px) - previous.xy_px)
                            / delta
                            * (stamp - latest.source_seconds)
                        )
                selected, reason = associate(
                    detector.detect(image, prediction), prediction, 320, max(12, radius * 3)
                )
                if selected is None:
                    break
                position, score = selected
                samples.append(
                    BallSample(
                        source_seconds=stamp,
                        xy_px=tuple(position),
                        similarity=score,
                        source="model_detection",
                    )
                )
                continue
            search = min(320, max(48, radius * 20))
            x, y = np.round(position).astype(int)
            left, top = max(0, x - search), max(0, y - search)
            right, bottom = min(width, x + search), min(height, y + search)
            roi = gray[top:bottom, left:right]
            if min(roi.shape) < len(template):
                reason = "left_frame"
                break
            scores = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, best = cv2.minMaxLoc(scores)
            bx, by = best
            other = scores.copy()
            other[
                max(0, by - radius * 2) : by + radius * 2 + 1,
                max(0, bx - radius * 2) : bx + radius * 2 + 1,
            ] = -1
            if not np.isfinite(score) or score < 0.85 or score - float(other.max()) < 0.08:
                reason = "appearance_lost_or_ambiguous"
                break
            position = np.array([left + bx + radius, top + by + radius], dtype=float)
            samples.append(
                BallSample(source_seconds=stamp, xy_px=tuple(position), similarity=score)
            )
        else:
            reason = "frame_limit"
    finally:
        capture.release()
    moving = (
        len(samples) >= 3
        and max(np.linalg.norm(np.asarray(point.xy_px) - samples[0].xy_px) for point in samples)
        >= options.radius_px * 3
    )
    return BallTrackResponse(
        swing_id=options.swing_id,
        status="candidate_track" if moving else "insufficient_data",
        width=width,
        height=height,
        samples=samples,
        stop_reason=reason,
        tracker_backend="onnx_golf_detector" if detector else "appearance_baseline",
        model_sha256=detector.sha256 if detector else None,
        model_source=MODEL_URL
        if detector and detector.sha256 == MODEL_SHA256
        else "Configured local ONNX model"
        if detector
        else None,
        camera_motion_detected=camera_motion,
        stationary_confirmed=options.stationary_confirmed,
        notices=[
            "Model-detected ball candidates require visual review; confidence is not a golf-accuracy probability."
            if detector
            else "User-seeded appearance candidates only. Visually confirm the whole trace; other balls, lights and blur can fool this tracker.",
            "Local ONNX detection with explicit seed association. No synthetic points or automatic appearance fallback are added after a missed detection."
            if detector
            else "The first point is your manual seed. Later points pass appearance/ambiguity checks, not a trained ball classifier.",
            "Image pixels only: no measured launch direction, ball speed, spin, carry, or extrapolated flight.",
            "Tracking stops at the first unreliable match. A short or stationary track is insufficient flight evidence.",
            "Camera/background motion was detected. Source-image positions include that motion and do not establish launch or curve."
            if camera_motion
            else "Camera stability was not confirmed. Source-image positions may include camera movement."
            if not options.stationary_confirmed
            else "Camera stability is user-declared. Pixel displacement alone does not prove ball launch.",
        ],
    )
