import cv2
import numpy as np
import hashlib
import json
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.coaching.schemas import VisionDocument, AnalysisOptions
from app.coaching.kinematics import calculate_kinematics
from app.coaching.rule_engine import evaluate_rules
from app.services.sessions import sign_analysis
from coaching_fixtures import pose_document
from app.evidence.ball_tracking import track_ball
from app.evidence.schemas import BallTrackOptions


def ball_video(path, *, disappear=False, ambiguous=False):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 240))
    assert writer.isOpened()
    rng = np.random.default_rng(4)
    background = rng.integers(10, 40, (240, 320), dtype=np.uint8)
    for i in range(20):
        frame = cv2.cvtColor(background, cv2.COLOR_GRAY2BGR)
        if not disappear or i < 6:
            cv2.circle(frame, (40 + i * 6, 100), 3, (255, 255, 255), -1)
        if ambiguous:
            cv2.circle(frame, (40 + i * 6, 125), 3, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def options():
    return BallTrackOptions(
        swing_id="A",
        seed_source_seconds=0,
        seed_point=(40 / 320, 100 / 240),
        radius_px=5,
        stationary_confirmed=True,
        analysis_token="test",
    )


def test_candidate_tracks_known_pixels_and_stops_on_loss(tmp_path):
    path = tmp_path / "ball.avi"
    ball_video(path, disappear=True)
    report = track_ball(path, options(), 1024 * 1024)
    assert report.needs_visual_confirmation
    assert 2 <= len(report.samples) <= 6
    for sample in report.samples:
        np.testing.assert_allclose(sample.xy_px, (40 + sample.source_seconds * 30 * 6, 100), atol=1)
    assert report.stop_reason == "appearance_lost_or_ambiguous"
    assert "carry" not in report.model_dump()


def test_ambiguous_similar_balls_are_not_silently_followed(tmp_path):
    path = tmp_path / "crowded.avi"
    ball_video(path, ambiguous=True)
    report = track_ball(path, options(), 1024 * 1024)
    assert report.status == "insufficient_data"
    assert len(report.samples) == 1


def test_ball_endpoint_runs_isolated_worker_and_rejects_a_different_source(tmp_path):
    path = tmp_path / "source.avi"
    ball_video(path, disappear=True)
    secret = "ball-worker-test-token-at-least-24"
    pose = VisionDocument.model_validate(pose_document())
    metrics = calculate_kinematics(pose, AnalysisOptions())
    token = sign_analysis(
        "source-id",
        metrics,
        evaluate_rules(metrics),
        secret,
        pose,
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    config = options().model_copy(update={"analysis_token": token}).model_dump(mode="json")
    with TestClient(
        create_app(Settings(api_token=secret, pose_weights=tmp_path / "no-model-required.pt"))
    ) as client:
        headers = {"Authorization": "Bearer " + secret}
        with path.open("rb") as video:
            response = client.post(
                "/api/v1/ball-tracks",
                headers=headers,
                data={"options": json.dumps(config)},
                files={"video": ("source.avi", video, "video/x-msvideo")},
            )
        assert response.status_code == 200 and response.json()["evidence_token"]
        assert response.json()["needs_visual_confirmation"]
        response = client.post(
            "/api/v1/ball-tracks",
            headers=headers,
            data={"options": json.dumps(config)},
            files={"video": ("source.avi", b"different-video", "video/x-msvideo")},
        )
        assert response.status_code == 422 and response.json()["error"]["code"] == "source_mismatch"
