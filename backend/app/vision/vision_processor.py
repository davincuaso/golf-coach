"""Offline COCO-17 pose extraction, gap-aware filtering and 2D joint angles.

Run from backend/: python -m app.vision.vision_processor --help
No HTTP server, coaching rules, credentials or cloud uploads are implemented here.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import logging
import math
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray
from scipy.signal import butter, sosfiltfilt

FloatArray = NDArray[np.float64]
LOGGER = logging.getLogger(__name__)
LANDMARKS = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)
INDEX = {name: index for index, name in enumerate(LANDMARKS)}
SKELETON = (
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),
    (5, 6),
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (5, 11),
    (6, 12),
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
)
ANGLE_JOINTS = {
    "left_elbow": ("left_shoulder", "left_elbow", "left_wrist"),
    "right_elbow": ("right_shoulder", "right_elbow", "right_wrist"),
    "left_shoulder": ("left_elbow", "left_shoulder", "left_hip"),
    "right_shoulder": ("right_elbow", "right_shoulder", "right_hip"),
    "left_hip": ("left_shoulder", "left_hip", "left_knee"),
    "right_hip": ("right_shoulder", "right_hip", "right_knee"),
    "left_knee": ("left_hip", "left_knee", "left_ankle"),
    "right_knee": ("right_hip", "right_knee", "right_ankle"),
}


class VisionError(RuntimeError):
    """Input or analysis failure safe to describe to a CLI user."""


@dataclass(frozen=True)
class VisionConfig:
    detection_confidence: float = 0.35
    keypoint_confidence: float = 0.5
    cutoff_hz: float = 8.0
    filter_order: int = 4
    max_gap_seconds: float = 0.1
    track_timeout_seconds: float = 0.75
    min_track_iou: float = 0.15
    track_ambiguity_margin: float = 0.2
    max_frames: int = 12_000
    max_duration_seconds: float = 30.0
    max_pixels: int = 3840 * 2160
    max_input_bytes: int = 500 * 1024 * 1024
    image_size: int = 960
    device: str = "cpu"
    subject_point: tuple[float, float] | None = None
    source_start_seconds: float = 0
    source_end_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "detection_confidence",
            "keypoint_confidence",
            "min_track_iou",
            "track_ambiguity_margin",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{name} must be in (0, 1].")
        for name in ("cutoff_hz", "max_duration_seconds", "track_timeout_seconds"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive.")
        if not math.isfinite(self.max_gap_seconds) or self.max_gap_seconds < 0:
            raise ValueError("max_gap_seconds must be finite and nonnegative.")
        if not 1 <= self.filter_order <= 10:
            raise ValueError("filter_order must be between 1 and 10.")
        for name in ("max_frames", "max_pixels", "max_input_bytes", "image_size"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive.")
        if (
            not math.isfinite(self.source_start_seconds)
            or not 0 <= self.source_start_seconds <= 86_400
        ):
            raise ValueError("Source start is invalid.")
        if self.source_end_seconds is not None and (
            not math.isfinite(self.source_end_seconds)
            or not 0
            < self.source_end_seconds - self.source_start_seconds
            <= self.max_duration_seconds
        ):
            raise ValueError("Source window must fit the analysis duration limit.")
        if self.source_start_seconds > 0 and self.source_end_seconds is None:
            raise ValueError("A nonzero source start requires an end.")
        if self.subject_point is not None and (
            len(self.subject_point) != 2
            or any(not math.isfinite(v) or not 0 <= v <= 1 for v in self.subject_point)
        ):
            raise ValueError("subject_point must contain two normalized coordinates in [0, 1].")


@dataclass(frozen=True)
class Detection:
    bbox: FloatArray  # xyxy in decoded image pixels
    confidence: float
    xy: FloatArray  # (17, 2), anatomical left/right as labelled by the model
    scores: FloatArray  # (17,)


class PoseDetector(Protocol):
    def detect(self, frame: NDArray[Any]) -> list[Detection]: ...


class YoloPoseDetector:
    """Load trusted local pose weights once per worker; no implicit downloads."""

    def __init__(self, weights: Path, config: VisionConfig):
        from ultralytics import YOLO

        if not weights.is_file() or weights.suffix.lower() != ".pt":
            raise VisionError("Supply an existing, trusted local .pt pose checkpoint.")
        self.model = YOLO(str(weights), task="pose")
        if self.model.task != "pose":
            raise VisionError("The supplied checkpoint is not a pose model.")
        self.config = config

    def detect(self, frame: NDArray[Any]) -> list[Detection]:
        result = self.model.predict(
            source=frame,
            conf=self.config.detection_confidence,
            imgsz=self.config.image_size,
            device=self.config.device,
            classes=[0],
            max_det=20,
            verbose=False,
        )[0]
        if result.boxes is None or len(result.boxes) == 0:
            return []
        if result.keypoints is None or result.keypoints.conf is None:
            raise VisionError("Pose model returned no keypoint confidence values.")
        xy = result.keypoints.xy.cpu().numpy().astype(np.float64)
        scores = result.keypoints.conf.cpu().numpy().astype(np.float64)
        if xy.shape[1:] != (17, 2) or scores.shape != xy.shape[:2]:
            raise VisionError("This adapter requires a COCO-17 human pose model.")
        boxes = result.boxes.xyxy.cpu().numpy().astype(np.float64)
        confidences = result.boxes.conf.cpu().numpy()
        return [
            Detection(box, float(confidence), points, score)
            for box, confidence, points, score in zip(boxes, confidences, xy, scores, strict=True)
        ]


def box_iou(a: FloatArray, b: FloatArray) -> float:
    intersection = float(
        np.prod(np.maximum(0.0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2])))
    )
    area_a = float(np.prod(np.maximum(0.0, a[2:] - a[:2])))
    area_b = float(np.prod(np.maximum(0.0, b[2:] - b[:2])))
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


class SubjectTracker:
    """Conservative box continuity for a fixed camera, not person re-identification.

    Ambiguous matches remain missing. A timed-out track never switches to a new
    person. For crowded scenes supply a point in the golfer's first bounding box.
    """

    def __init__(self, config: VisionConfig):
        self.config = config
        self.previous: FloatArray | None = None
        self.last_seen: int | None = None
        self.lost = False

    def select(
        self,
        detections: list[Detection],
        frame_index: int,
        fps: float,
        width: int,
        height: int,
    ) -> Detection | None:
        if self.lost:
            return None
        candidates = [
            d
            for d in detections
            if math.isfinite(d.confidence)
            and d.confidence >= self.config.detection_confidence
            and d.bbox.shape == (4,)
            and np.isfinite(d.bbox).all()
            and np.all(d.bbox[2:] > d.bbox[:2])
        ]
        if self.previous is None:
            if self.config.subject_point is not None:
                point = np.asarray(self.config.subject_point) * [width, height]
                candidates = [
                    d
                    for d in candidates
                    if np.all(point >= d.bbox[:2]) and np.all(point <= d.bbox[2:])
                ]
            if len(candidates) > 1:
                raise VisionError(
                    "Multiple people found. Crop the clip or use --subject-point X Y."
                )
        else:
            assert self.last_seen is not None
            if (frame_index - self.last_seen) / fps > self.config.track_timeout_seconds:
                self.lost = True
                return None
            matches = sorted(
                ((box_iou(self.previous, d.bbox), d) for d in candidates),
                key=lambda match: match[0],
                reverse=True,
            )
            matches = [match for match in matches if match[0] >= self.config.min_track_iou]
            if len(matches) > 1:
                # Ignore weak bystander overlaps; near-ties stay unknown.
                if matches[0][0] - matches[1][0] < self.config.track_ambiguity_margin:
                    return None
                matches = matches[:1]
            candidates = [match[1] for match in matches]
        if len(candidates) != 1:
            return None
        selected = candidates[0]
        self.previous = selected.bbox.copy()
        self.last_seen = frame_index
        return selected


def video_timestamps(pts_seconds: FloatArray, fps: float) -> tuple[FloatArray, str]:
    """Use decoder timestamps as a whole, or fall back to nominal CFR as a whole."""
    if not math.isfinite(fps) or not 1 <= fps <= 1000:
        raise VisionError("Video must report a valid frame rate between 1 and 1000 FPS.")
    if len(pts_seconds) > 1 and np.isfinite(pts_seconds).all() and np.all(np.diff(pts_seconds) > 0):
        return pts_seconds - pts_seconds[0], "decoder_pts"
    return np.arange(len(pts_seconds), dtype=np.float64) / fps, "nominal_fps_fallback"


def smooth_landmarks(
    raw: FloatArray,
    timestamps: FloatArray,
    config: VisionConfig,
) -> tuple[FloatArray, NDArray[np.bool_], NDArray[np.bool_]]:
    """Interpolate bounded interior gaps and filter each continuous landmark span.

    Resample to a uniform time grid before filtering, then map back to source PTS.
    Never extrapolate, bridge long occlusions, or pass NaNs into SciPy. Short spans
    keep their measurements and expose filtered=False rather than inventing data.
    """
    if raw.ndim != 3 or raw.shape[1:] != (17, 2) or raw.shape[0] != len(timestamps):
        raise ValueError("Expected coordinates (frames, 17, 2) and matching timestamps.")
    if len(timestamps) == 0 or not np.isfinite(timestamps).all():
        raise ValueError("At least one finite timestamp is required.")
    if len(timestamps) > 1 and not np.all(np.diff(timestamps) > 0):
        raise ValueError("Timestamps must be strictly increasing.")
    smooth = raw.copy()
    observed = np.isfinite(raw).all(axis=2)
    smooth[~observed] = np.nan
    interpolated = np.zeros(raw.shape[:2], dtype=bool)
    filtered = np.zeros_like(interpolated)
    if len(timestamps) < 2:
        return smooth, interpolated, filtered
    nominal_dt = float(np.median(np.diff(timestamps)))
    if config.cutoff_hz >= 0.5 / nominal_dt:
        raise VisionError("Filter cutoff must be below half the effective video frame rate.")

    for joint in range(17):
        valid_indices = np.flatnonzero(observed[:, joint])
        for left, right in zip(valid_indices[:-1], valid_indices[1:], strict=True):
            if right - left > 1 and timestamps[right] - timestamps[left] <= config.max_gap_seconds:
                for axis in range(2):
                    smooth[left + 1 : right, joint, axis] = np.interp(
                        timestamps[left + 1 : right],
                        timestamps[[left, right]],
                        raw[[left, right], joint, axis],
                    )
                interpolated[left + 1 : right, joint] = True

        finite = np.flatnonzero(np.isfinite(smooth[:, joint]).all(axis=1))
        if len(finite) == 0:
            continue
        # A discontinuity in time also breaks a span, even if no frames are missing.
        cuts = (
            np.flatnonzero(
                (np.diff(finite) > 1)
                | (np.diff(timestamps[finite]) > max(config.max_gap_seconds, 1.5 * nominal_dt))
            )
            + 1
        )
        for span in np.split(finite, cuts):
            if len(span) < 3:
                continue
            times = timestamps[span]
            count = max(2, int(round((times[-1] - times[0]) / nominal_dt)) + 1)
            # Bound allocations for pathological timestamp discontinuities.
            if count > config.max_frames:
                raise VisionError("Timestamp span exceeds the resampling resource limit.")
            grid = np.linspace(times[0], times[-1], count)
            sample_rate = (count - 1) / (times[-1] - times[0])
            if config.cutoff_hz >= sample_rate / 2:
                continue
            sos = butter(config.filter_order, config.cutoff_hz, fs=sample_rate, output="sos")
            padlen = 3 * (
                2 * len(sos)
                + 1
                - min(
                    int((sos[:, 2] == 0).sum()),
                    int((sos[:, 5] == 0).sum()),
                )
            )
            if count <= padlen + 1:
                continue
            uniform = np.column_stack(
                [np.interp(grid, times, smooth[span, joint, axis]) for axis in range(2)]
            )
            stabilized = sosfiltfilt(sos, uniform, axis=0, padlen=padlen)
            for axis in range(2):
                smooth[span, joint, axis] = np.interp(times, grid, stabilized[:, axis])
            filtered[span, joint] = True
    return smooth, interpolated, filtered


def joint_angle(a: FloatArray, b: FloatArray, c: FloatArray) -> float | None:
    """Interior angle ABC in degrees, computed in image pixels, not distorted UV."""
    if not np.isfinite(np.concatenate((a, b, c))).all():
        return None
    u, v = a - b, c - b
    denominator = float(np.linalg.norm(u) * np.linalg.norm(v))
    if denominator < 1e-8:
        return None
    cosine = float(np.clip(np.dot(u, v) / denominator, -1.0, 1.0))
    return round(math.degrees(math.acos(cosine)), 4)


def frame_angles(points: FloatArray) -> dict[str, float | None]:
    angles = {
        name: joint_angle(*(points[INDEX[joint]] for joint in joints))
        for name, joints in ANGLE_JOINTS.items()
    }
    torso = points[
        [
            INDEX[n]
            for n in (
                "left_shoulder",
                "right_shoulder",
                "left_hip",
                "right_hip",
            )
        ]
    ]
    spine_tilt = None
    if np.isfinite(torso).all():
        vector = torso[:2].mean(axis=0) - torso[2:].mean(axis=0)
        length = float(np.linalg.norm(vector))
        if length > 1e-8:
            spine_tilt = round(
                math.degrees(math.acos(float(np.clip(-vector[1] / length, -1, 1)))), 4
            )
    angles["spine_tilt_2d"] = spine_tilt
    return angles


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def process_video(
    video_path: Path,
    detector: PoseDetector,
    config: VisionConfig,
) -> dict[str, Any]:
    """Decode one local video. Keep coordinates, never decoded frames, in memory."""
    import cv2

    if not video_path.is_file():
        raise VisionError("Input must be an existing local video file.")
    if video_path.stat().st_size > config.max_input_bytes:
        raise VisionError("Input exceeds the configured byte limit.")
    capture = cv2.VideoCapture(str(video_path))
    coordinates, confidences, boxes, pts = [], [], [], []
    tracker = SubjectTracker(config)
    width = height = 0
    source_origin = 0.0
    source_duration = None
    windowed = config.source_end_seconds is not None
    try:
        if not capture.isOpened():
            raise VisionError("OpenCV could not open this video or its codec.")
        if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
            capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        video_timestamps(np.array([], dtype=np.float64), fps)  # Validate metadata.
        expected_frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        source_duration = (
            expected_frames / fps
            if math.isfinite(expected_frames) and expected_frames > 0
            else None
        )
        if windowed:
            if (
                source_duration is not None
                and config.source_end_seconds > source_duration + 1 / fps
            ):
                raise VisionError("Selected window extends beyond the source video.")
            if config.source_start_seconds and not capture.set(
                cv2.CAP_PROP_POS_MSEC, config.source_start_seconds * 1000
            ):
                raise VisionError("This video cannot seek to the selected window; trim it first.")
        if not windowed and math.isfinite(expected_frames) and expected_frames > config.max_frames:
            raise VisionError("Input exceeds the configured frame limit.")
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            raw_pts = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            source_frame = float(capture.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            source_time = (
                raw_pts
                if math.isfinite(raw_pts) and (raw_pts > 0 or config.source_start_seconds == 0)
                else source_frame / fps
            )
            if windowed:
                if not math.isfinite(source_time) or source_time < 0:
                    raise VisionError(
                        "Source timing is unavailable; trim this video before analysis."
                    )
                if source_time + 1e-6 < config.source_start_seconds:
                    continue
                if source_time > config.source_end_seconds + 1e-6:
                    break
                if not coordinates:
                    source_origin = source_time
            index = len(coordinates)
            if index >= config.max_frames or index / fps > config.max_duration_seconds:
                raise VisionError("Input exceeds the frame or duration limit; trim the clip.")
            frame_height, frame_width = frame.shape[:2]
            if frame_width * frame_height > config.max_pixels:
                raise VisionError("Decoded frame exceeds the configured pixel limit.")
            if index == 0:
                width, height = frame_width, frame_height
            elif (width, height) != (frame_width, frame_height):
                raise VisionError(
                    "Video changes resolution midstream; normalize it before analysis."
                )
            selected = tracker.select(detector.detect(frame), index, fps, width, height)
            points = np.full((17, 2), np.nan)
            scores = np.full(17, np.nan)
            bbox = None
            if selected is not None:
                if selected.xy.shape != (17, 2) or selected.scores.shape != (17,):
                    raise VisionError("Detector returned an incompatible landmark layout.")
                valid_scores = (
                    np.isfinite(selected.scores) & (selected.scores >= 0) & (selected.scores <= 1)
                )
                scores[valid_scores] = selected.scores[valid_scores]
                valid = (
                    valid_scores
                    & (scores >= config.keypoint_confidence)
                    & np.isfinite(selected.xy).all(axis=1)
                    & (selected.xy >= 0).all(axis=1)
                    & (selected.xy < [width, height]).all(axis=1)
                )
                points[valid] = selected.xy[valid]
                bbox = [round(float(v), 4) for v in selected.bbox]
            coordinates.append(points)
            confidences.append(scores)
            boxes.append(bbox)
            pts.append(raw_pts)
    finally:
        capture.release()
    if not coordinates:
        raise VisionError("Video contains no decodable frames.")
    if (
        not windowed
        and math.isfinite(expected_frames)
        and expected_frames - len(coordinates) > max(2, expected_frames * 0.01)
    ):
        raise VisionError(
            "Decoding ended before the reported frame count; repair or re-encode the video."
        )
    timestamps, timestamp_source = video_timestamps(np.asarray(pts), fps)
    if timestamps[-1] > config.max_duration_seconds:
        raise VisionError("Decoded timestamps exceed the configured duration limit.")
    raw = np.asarray(coordinates)
    scores_array = np.asarray(confidences)
    stabilized, interpolated, filtered = smooth_landmarks(raw, timestamps, config)
    frames = []
    for i, points in enumerate(stabilized):
        joints = {}
        for j, name in enumerate(LANDMARKS):
            observed = bool(np.isfinite(raw[i, j]).all())
            available = bool(np.isfinite(points[j]).all())
            score = float(scores_array[i, j]) if np.isfinite(scores_array[i, j]) else None
            joints[name] = {
                "xy_px": [round(float(v), 4) for v in points[j]] if available else None,
                "xy_normalized": [round(float(v), 7) for v in points[j] / [width, height]]
                if available
                else None,
                "raw_xy_px": [round(float(v), 4) for v in raw[i, j]] if observed else None,
                "confidence": round(score, 5) if score is not None else None,
                "observed": observed,
                "interpolated": bool(interpolated[i, j]),
                "filtered": bool(filtered[i, j]),
            }
        frames.append(
            {
                "frame_index": i,
                "timestamp_seconds": round(float(timestamps[i]), 7),
                "person_bbox_xyxy_px": boxes[i],
                "landmarks": joints,
                "angles_deg": frame_angles(points),
                "club": None,
            }
        )
    observed_count = int(np.isfinite(raw).all(axis=2).sum())
    warnings = [
        "Angles are 2D camera projections, not 3D biomechanics or diagnoses.",
        "COCO-17 has no club landmarks; club tracking and physical speed are unavailable.",
        "The body filter can suppress fast motion; validate its cutoff on representative clips.",
    ]
    if timestamp_source != "decoder_pts":
        warnings.append(
            "Decoder timestamps unavailable; time assumes a constant nominal frame rate."
        )
    if tracker.lost:
        warnings.append(
            "Subject track timed out; later detections were suppressed to avoid switching people."
        )
    if observed_count == 0:
        warnings.append("No confident body landmarks were found; all angles are unknown.")
    if np.any(np.isfinite(stabilized).all(axis=2) & ~filtered):
        warnings.append("Some valid landmark spans were too short or slow to filter.")
    return {
        "schema_version": "1.0.0",
        "video": {
            "filename": video_path.name,
            "width": width,
            "height": height,
            "nominal_fps": fps,
            "frame_count": len(frames),
            "last_frame_timestamp_seconds": round(float(timestamps[-1]), 7),
            "timestamp_source": timestamp_source,
            "source_start_seconds": source_origin,
            "source_duration_seconds": source_duration,
            "coordinate_system": "decoded image pixels; origin top-left; x right; y down",
        },
        "processing": {
            "config": asdict(config),
            "filter": "Butterworth SOS forward-backward, offline",
            "versions": {
                p: _version(p) for p in ("numpy", "scipy", "opencv-python", "ultralytics")
            },
        },
        "quality": {
            "observed_landmark_fraction": observed_count / (len(frames) * 17),
            "interpolated_landmarks": int(interpolated.sum()),
            "filtered_landmarks": int(filtered.sum()),
            "subject_track_lost": tracker.lost,
        },
        "skeleton_edges": [[LANDMARKS[a], LANDMARKS[b]] for a, b in SKELETON],
        "warnings": warnings,
        "frames": frames,
    }


def write_json_atomic(payload: dict[str, Any], destination: Path, overwrite: bool = False) -> None:
    """Strict JSON; same-directory temporary file; no partially written result."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=".analysis-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, allow_nan=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)  # Atomic create; refuses an existing destination.
    finally:
        if temporary is not None:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, type=Path, help="Local MP4, MOV, WebM or other supported video"
    )
    parser.add_argument("--output", required=True, type=Path, help="Destination JSON file")
    parser.add_argument(
        "--weights", required=True, type=Path, help="Trusted local COCO-17 pose .pt file"
    )
    parser.add_argument("--device", default="cpu", help="cpu, mps, or a CUDA device such as 0")
    parser.add_argument("--image-size", type=int, default=960)
    parser.add_argument("--cutoff-hz", type=float, default=8.0)
    parser.add_argument("--filter-order", type=int, default=4)
    parser.add_argument("--keypoint-confidence", type=float, default=0.5)
    parser.add_argument("--detection-confidence", type=float, default=0.35)
    parser.add_argument("--max-gap-seconds", type=float, default=0.1)
    parser.add_argument("--subject-point", type=float, nargs=2, metavar=("X", "Y"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        if (
            args.input.resolve() == args.output.resolve()
            or args.weights.resolve() == args.output.resolve()
        ):
            raise VisionError("Output cannot replace the input video or model checkpoint.")
        if args.output.exists() and not args.overwrite:
            raise VisionError("Output exists; choose another file or pass --overwrite.")
        config = VisionConfig(
            device=args.device,
            image_size=args.image_size,
            cutoff_hz=args.cutoff_hz,
            filter_order=args.filter_order,
            keypoint_confidence=args.keypoint_confidence,
            detection_confidence=args.detection_confidence,
            max_gap_seconds=args.max_gap_seconds,
            subject_point=tuple(args.subject_point) if args.subject_point else None,
        )
        if not args.input.is_file() or args.input.stat().st_size > config.max_input_bytes:
            raise VisionError("Input is missing or exceeds the configured byte limit.")
        detector = YoloPoseDetector(args.weights, config)
        payload = process_video(args.input, detector, config)
        payload["processing"]["model"] = {
            "filename": args.weights.name,
            "sha256": _sha256(args.weights),
        }
        payload["video"]["sha256"] = _sha256(args.input)
        write_json_atomic(payload, args.output, overwrite=args.overwrite)
        LOGGER.info("Wrote %d frames to %s", payload["video"]["frame_count"], args.output)
        return 0
    except (VisionError, ValueError, OSError, ImportError) as error:
        LOGGER.error("Analysis failed: %s", error)
        return 1
    except Exception:
        LOGGER.exception("Unexpected pose inference failure")
        return 1


if __name__ == "__main__":
    sys.exit(main())
