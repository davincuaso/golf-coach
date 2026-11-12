import cv2
import numpy as np
import pytest

from app.evidence.ball_detector import associate, parse_detections
from app.evidence.ball_tracking import track_ball
from app.evidence.schemas import BallTrackOptions


def test_yolo_output_maps_letterboxed_roi_to_original_pixels_and_suppresses_duplicates():
    output = np.array(
        [[[320, 321, 500], [320, 321, 500], [20, 20, 10], [20, 20, 10], [0.9, 0.8, 0.1]]],
        dtype=np.float32,
    )
    detections = parse_detections(output, 2, (0, 80), (100, 200), (1000, 1000))
    assert len(detections) == 1
    np.testing.assert_allclose(detections[0][0], [260, 320])
    normalized = output.copy()
    normalized[:, :4] /= 640
    rescaled = parse_detections(normalized, 2, (0, 80), (100, 200), (1000, 1000), normalized=True)
    np.testing.assert_allclose(rescaled[0][0], [260, 320], atol=1e-4)
    with pytest.raises(ValueError):
        parse_detections(np.zeros((1, 84, 8400)), 1, (0, 0), (0, 0), (1000, 1000))


def test_detector_association_rejects_identity_ambiguity_and_missing_detections():
    selected, reason = associate(
        [(np.array([5.0, 0]), 0.9), (np.array([-5.0, 0]), 0.95)], np.zeros(2), 100, 12
    )
    assert selected is None and reason == "model_identity_ambiguous"
    selected, reason = associate([], np.zeros(2), 100, 12)
    assert selected is None and reason == "model_detection_lost"


def test_model_tracking_never_falls_back_to_template_or_predicted_points(tmp_path):
    path = tmp_path / "test.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 240))
    rng = np.random.default_rng(5)
    background = rng.integers(10, 40, (240, 320), dtype=np.uint8)
    for index in range(8):
        image = cv2.cvtColor(background, cv2.COLOR_GRAY2BGR)
        cv2.circle(image, (40 + index * 6, 100), 3, (255, 255, 255), -1)
        writer.write(image)
    writer.release()

    class Detector:
        sha256 = "test-detector"
        count = 0

        def detect(self, image, prediction):
            self.count += 1
            return [(np.array([40 + (self.count - 1) * 6.0, 100]), 0.9)] if self.count <= 3 else []

    options = BallTrackOptions(
        swing_id="A",
        seed_source_seconds=0,
        seed_point=(40 / 320, 100 / 240),
        radius_px=3,
        stationary_confirmed=True,
        analysis_token="test",
    )
    report = track_ball(path, options, 1024 * 1024, Detector())
    assert report.tracker_backend == "onnx_golf_detector" and len(report.samples) == 3
    assert all(point.source == "model_detection" for point in report.samples)
    assert report.stop_reason == "model_detection_lost"
