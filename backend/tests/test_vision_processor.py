import json
from pathlib import Path

import numpy as np
import pytest

from app.vision.vision_processor import (
    INDEX,
    Detection,
    SubjectTracker,
    VisionConfig,
    VisionError,
    frame_angles,
    joint_angle,
    process_video,
    smooth_landmarks,
    video_timestamps,
    write_json_atomic,
)


def detection(box=(10, 10, 110, 110)):
    return Detection(
        np.asarray(box, dtype=float),
        0.95,
        np.tile([60.0, 60.0], (17, 1)),
        np.full(17, 0.9),
    )


def test_joint_geometry_and_undefined_values():
    assert joint_angle(np.array([100, 0]), np.array([0, 0]), np.array([0, 50])) == 90
    assert joint_angle(np.array([-1, 0]), np.array([0, 0]), np.array([1, 0])) == 180
    assert joint_angle(np.zeros(2), np.zeros(2), np.ones(2)) is None
    assert joint_angle(np.array([np.nan, 1]), np.zeros(2), np.ones(2)) is None


def test_spine_tilt_is_relative_to_image_vertical():
    points = np.full((17, 2), np.nan)
    points[INDEX["left_shoulder"]] = [20, 10]
    points[INDEX["right_shoulder"]] = [40, 10]
    points[INDEX["left_hip"]] = [20, 60]
    points[INDEX["right_hip"]] = [40, 60]
    assert frame_angles(points)["spine_tilt_2d"] == 0
    points[[INDEX["left_shoulder"], INDEX["right_shoulder"]], 0] += 50
    assert frame_angles(points)["spine_tilt_2d"] == 45
    points[INDEX["left_hip"]] = np.nan
    assert frame_angles(points)["spine_tilt_2d"] is None


def test_filter_reduces_high_frequency_noise_without_shifting_body_motion():
    time = np.arange(360) / 60
    clean = 200 + 30 * np.sin(2 * np.pi * 1.5 * time)
    noisy = clean + 8 * np.sin(2 * np.pi * 20 * time)
    raw = np.tile(np.column_stack((noisy, noisy))[:, None, :], (1, 17, 1))
    stabilized, imputed, filtered = smooth_landmarks(raw, time, VisionConfig())
    interior = slice(30, -30)
    before = np.sqrt(np.mean((noisy[interior] - clean[interior]) ** 2))
    after = np.sqrt(np.mean((stabilized[interior, 0, 0] - clean[interior]) ** 2))
    assert after < before * 0.1
    assert np.argmax(stabilized[20:60, 0, 0]) == np.argmax(clean[20:60])
    assert filtered.all() and not imputed.any()


def test_short_gaps_interpolate_but_long_gaps_and_edges_stay_unknown():
    time = np.arange(120) / 60
    raw = np.tile(np.column_stack((10 + time, 20 + time))[:, None, :], (1, 17, 1))
    raw[:2, 0] = np.nan
    raw[20:22, 0] = np.nan
    raw[50:70, 0] = np.nan
    raw[-2:, 0] = np.nan
    stabilized, imputed, _ = smooth_landmarks(raw, time, VisionConfig())
    assert imputed[20:22, 0].all()
    assert np.isfinite(stabilized[20:22, 0]).all()
    assert np.isnan(stabilized[50:70, 0]).all()
    assert np.isnan(stabilized[:2, 0]).all() and np.isnan(stabilized[-2:, 0]).all()
    assert np.isnan(raw[20:22, 0]).all()  # Source data is not mutated.


def test_missing_and_short_spans_are_not_invented_or_mislabelled():
    raw = np.full((8, 17, 2), np.nan)
    raw[2:5, 0] = [10, 20]
    stabilized, imputed, filtered = smooth_landmarks(raw, np.arange(8) / 60, VisionConfig())
    assert not imputed.any() and not filtered.any()
    assert np.array_equal(stabilized[2:5, 0], raw[2:5, 0])
    assert np.isnan(stabilized[:, 1:]).all()


def test_variable_frame_intervals_are_resampled_in_time():
    intervals = np.tile([0.012, 0.021, 0.017], 80)
    time = np.cumsum(intervals)
    values = 100 + np.sin(2 * np.pi * time)
    raw = np.tile(values[:, None, None], (1, 17, 2))
    stabilized, _, filtered = smooth_landmarks(raw, time, VisionConfig())
    assert filtered.all()
    assert np.max(np.abs(stabilized[20:-20, 0, 0] - values[20:-20])) < 0.03


def test_invalid_filter_sampling_rate_fails_clearly():
    with pytest.raises(VisionError, match="half"):
        smooth_landmarks(np.ones((30, 17, 2)), np.arange(30) / 10, VisionConfig())
    with pytest.raises(ValueError, match="increasing"):
        smooth_landmarks(np.ones((2, 17, 2)), np.zeros(2), VisionConfig())


@pytest.mark.parametrize(
    "settings",
    [
        {"cutoff_hz": float("nan")},
        {"keypoint_confidence": 0},
        {"filter_order": 0},
        {"max_gap_seconds": -1},
        {"max_frames": 0},
        {"subject_point": (1.2, 0.5)},
    ],
)
def test_config_rejects_invalid_parameters(settings):
    with pytest.raises(ValueError):
        VisionConfig(**settings)


def test_timestamp_fallback_is_consistent_for_the_whole_clip():
    time, source = video_timestamps(np.array([2.0, 2.02, 2.07]), 30)
    assert source == "decoder_pts" and np.allclose(time, [0, 0.02, 0.07])
    time, source = video_timestamps(np.array([0.0, 0.02, 0.0]), 30)
    assert source == "nominal_fps_fallback" and np.allclose(time, np.arange(3) / 30)
    with pytest.raises(VisionError):
        video_timestamps(np.zeros(2), float("nan"))


def test_ambiguous_initial_subject_requires_selection():
    tracker = SubjectTracker(VisionConfig())
    with pytest.raises(VisionError, match="Multiple people"):
        tracker.select([detection(), detection((200, 10, 300, 110))], 0, 60, 400, 200)
    tracker = SubjectTracker(VisionConfig(subject_point=(0.15, 0.3)))
    selected = tracker.select([detection(), detection((200, 10, 300, 110))], 0, 60, 400, 200)
    assert selected is not None and selected.bbox[0] == 10


def test_tracker_does_not_switch_to_an_unrelated_or_ambiguous_person():
    tracker = SubjectTracker(VisionConfig())
    assert tracker.select([detection()], 0, 60, 400, 200) is not None
    assert tracker.select([detection((200, 10, 300, 110))], 1, 60, 400, 200) is None
    assert tracker.select([detection(), detection((15, 10, 115, 110))], 2, 60, 400, 200) is None
    assert tracker.select([detection()], 60, 60, 400, 200) is None
    assert tracker.lost
    assert tracker.select([detection()], 61, 60, 400, 200) is None


def test_json_is_strict_atomic_and_does_not_overwrite_by_default(tmp_path):
    destination = tmp_path / "analysis.json"
    write_json_atomic({"angle": None}, destination)
    with pytest.raises(FileExistsError):
        write_json_atomic({"angle": 90}, destination)
    assert json.loads(destination.read_text()) == {"angle": None}
    with pytest.raises(ValueError):
        write_json_atomic({"angle": float("nan")}, destination, overwrite=True)
    assert json.loads(destination.read_text()) == {"angle": None}
    assert not list(tmp_path.glob(".analysis-*"))
    write_json_atomic({"angle": 90}, destination, overwrite=True)
    assert json.loads(destination.read_text()) == {"angle": 90}


def test_weakly_overlapping_bystander_does_not_erase_a_clear_continuing_track():
    tracker = SubjectTracker(VisionConfig())
    assert tracker.select([detection()], 0, 60, 400, 200) is not None
    selected = tracker.select(
        [detection((80, 10, 140, 110)), detection()],
        1,
        60,
        400,
        200,
    )
    assert selected is not None and selected.bbox[0] == 10


@pytest.fixture
def video(tmp_path):
    import cv2

    path = tmp_path / "fixture.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 60, (160, 120))
    assert writer.isOpened(), "MJPG encoder is required for this integration test"
    for _ in range(50):
        writer.write(np.zeros((120, 160, 3), dtype=np.uint8))
    writer.release()
    return path


class FixtureDetector:
    def detect(self, frame):
        result = detection()
        result.xy[INDEX["left_shoulder"]] = [20, 20]
        result.xy[INDEX["left_elbow"]] = [20, 60]
        result.xy[INDEX["left_wrist"]] = [80, 60]
        result.scores[INDEX["right_wrist"]] = 0.1
        return [result]


def test_decode_filter_angle_and_json_pipeline(video, tmp_path):
    payload = process_video(video, FixtureDetector(), VisionConfig())
    assert payload["video"]["frame_count"] == 50
    assert (payload["video"]["width"], payload["video"]["height"]) == (160, 120)
    assert payload["frames"][25]["angles_deg"]["left_elbow"] == 90
    wrist = payload["frames"][25]["landmarks"]["right_wrist"]
    assert wrist["xy_px"] is None and wrist["confidence"] == 0.1
    assert not wrist["observed"] and not wrist["interpolated"]
    elbow = payload["frames"][25]["landmarks"]["left_elbow"]
    assert np.allclose(elbow["xy_normalized"], [20 / 160, 60 / 120])
    assert elbow["filtered"] and payload["frames"][25]["club"] is None
    destination = tmp_path / "out.json"
    write_json_atomic(payload, destination)
    assert json.loads(destination.read_text())["schema_version"] == "1.0.0"


def test_empty_detections_still_produce_unknown_angles(video):
    class NoDetections:
        def detect(self, frame):
            return []

    payload = process_video(video, NoDetections(), VisionConfig())
    assert payload["quality"]["observed_landmark_fraction"] == 0
    assert all(value is None for value in payload["frames"][0]["angles_deg"].values())


def test_resource_limit_is_enforced(video):
    with pytest.raises(VisionError, match="frame limit"):
        process_video(video, FixtureDetector(), VisionConfig(max_frames=5))
    with pytest.raises(VisionError, match="byte limit"):
        process_video(video, FixtureDetector(), VisionConfig(max_input_bytes=1))
    with pytest.raises(VisionError, match="existing local"):
        process_video(Path("missing-video.mp4"), FixtureDetector(), VisionConfig())


def test_selected_source_window_resets_pose_clock_and_preserves_source_offset(video):
    payload = process_video(
        video, FixtureDetector(), VisionConfig(source_start_seconds=0.2, source_end_seconds=0.6)
    )
    assert 23 <= len(payload["frames"]) <= 25
    assert abs(payload["video"]["source_start_seconds"] - 0.2) < 1 / 60
    assert payload["frames"][0]["timestamp_seconds"] == 0
    assert payload["frames"][-1]["timestamp_seconds"] <= 0.4 + 1 / 60
    assert payload["video"]["source_duration_seconds"] > 0.8


def test_source_window_validation_and_selected_limits(video):
    with pytest.raises(ValueError):
        VisionConfig(source_start_seconds=2)
    with pytest.raises(ValueError):
        VisionConfig(source_start_seconds=0, source_end_seconds=31)
    with pytest.raises(VisionError, match="beyond"):
        process_video(
            video, FixtureDetector(), VisionConfig(source_start_seconds=2, source_end_seconds=3)
        )


def test_long_source_is_decoded_only_in_the_selected_short_window(tmp_path):
    import cv2

    path = tmp_path / "long.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (160, 120))
    assert writer.isOpened()
    for _ in range(1000):
        writer.write(np.zeros((120, 160, 3), dtype=np.uint8))
    writer.release()
    payload = process_video(
        path, FixtureDetector(), VisionConfig(source_start_seconds=31, source_end_seconds=31.5)
    )
    assert 14 <= len(payload["frames"]) <= 16
    assert payload["video"]["source_start_seconds"] >= 31
