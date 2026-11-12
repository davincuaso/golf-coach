import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.evidence.calibration import calibrate_from_observations
from app.evidence.reconstruction import reconstruct
from app.evidence.schemas import ReconstructionRequest
from app.errors import ServiceError
from app.main import create_app

SECRET = "reconstruction-test-secret-at-least-24"


def stereo_input():
    views = []
    truth = {
        "left_shoulder": [-0.2, 1.5, 5],
        "right_shoulder": [0.2, 1.5, 5],
        "left_hip": [-0.15, 1, 5],
        "right_hip": [0.15, 1, 5],
    }
    for index, tx in enumerate((1.0, -1.0)):
        k = np.array([[800.0, 0, 640], [0, 800, 360], [0, 0, 1]])
        distortion = np.array([0.03, -0.01, 0.001, -0.001, 0])
        calibration = dict(
            version="1.0",
            camera_id=f"camera-{index}",
            world_id="test-rig",
            image_width=1280,
            image_height=720,
            camera_matrix=k.tolist(),
            distortion=distortion.tolist(),
            rotation_world_to_camera=np.diag([1.0, -1.0, -1.0]).tolist(),
            translation_world_to_camera_m=[tx, 1.2, 8],
            calibration_rms_px=0.2,
            reference_rms_px=0.1,
            scale_and_orientation_verified=True,
        )
        frames = []
        for frame_index in range(31):
            landmarks = {}
            for name, point in truth.items():
                projected = (
                    cv2.projectPoints(
                        np.array([point], dtype=float),
                        cv2.Rodrigues(np.diag([1.0, -1.0, -1.0]))[0],
                        np.array([tx, 1.2, 8.0]),
                        k,
                        distortion,
                    )[0]
                    .reshape(2)
                    .tolist()
                )
                landmarks[name] = dict(
                    xy_px=projected,
                    raw_xy_px=projected,
                    observed=True,
                    interpolated=False,
                    confidence=0.99,
                    filtered=True,
                )
            frames.append(
                dict(
                    frame_index=frame_index,
                    timestamp_seconds=frame_index / 60,
                    landmarks=landmarks,
                    angles_deg={},
                )
            )
        pose = dict(
            schema_version="1.0.0",
            video=dict(
                width=1280,
                height=720,
                nominal_fps=60,
                frame_count=31,
                timestamp_source="decoder_pts",
            ),
            frames=frames,
        )
        views.append(
            dict(calibration=calibration, pose=pose, analysis_token="test", sync_anchor_seconds=0)
        )
    return dict(
        swing_id="Swing A",
        views=views,
        same_swing_stationary_confirmed=True,
        physical_timebase_confirmed=True,
        sync_uncertainty_ms=1,
    ), truth


def test_distorted_camera_points_reconstruct_known_metric_geometry():
    payload, truth = stereo_input()
    report = reconstruct(ReconstructionRequest.model_validate(payload))
    assert report.status == "reconstructed" and report.matched_frames == 31
    for name, xyz in truth.items():
        np.testing.assert_allclose(report.frames[0].joints[name].xyz_m, xyz, atol=1e-5)
    assert report.frames[0].torso_tilt_deg == pytest.approx(0, abs=1e-5)
    assert report.median_reprojection_error_px < 1e-5


@pytest.mark.parametrize(
    "change", ["world", "resolution", "scale", "sync", "same_swing", "timebase", "rms", "baseline"]
)
def test_calibration_capture_and_timing_gates(change):
    payload, _ = stereo_input()
    if change == "world":
        payload["views"][1]["calibration"]["world_id"] = "other"
    if change == "resolution":
        payload["views"][1]["calibration"]["image_width"] = 1920
    if change == "scale":
        payload["views"][1]["calibration"]["scale_and_orientation_verified"] = False
    if change == "sync":
        payload["sync_uncertainty_ms"] = 20
    if change == "same_swing":
        payload["same_swing_stationary_confirmed"] = False
    if change == "timebase":
        payload["views"][1]["pose"]["video"]["timestamp_source"] = "nominal_fps_fallback"
    if change == "rms":
        payload["views"][0]["calibration"]["calibration_rms_px"] = 4
    if change == "baseline":
        payload["views"][1]["calibration"]["translation_world_to_camera_m"] = [1.01, 1.2, 8]
    with pytest.raises(ServiceError):
        reconstruct(ReconstructionRequest.model_validate(payload))


def test_missing_and_inconsistent_correspondences_never_fill_3d_joints():
    payload, _ = stereo_input()
    payload["views"][0]["pose"]["frames"][0]["landmarks"]["left_hip"]["interpolated"] = True
    payload["views"][1]["pose"]["frames"][0]["landmarks"]["right_hip"]["raw_xy_px"][1] += 80
    report = reconstruct(ReconstructionRequest.model_validate(payload))
    assert "left_hip" not in report.frames[0].joints and "right_hip" not in report.frames[0].joints
    assert report.frames[0].torso_tilt_deg is None
    assert report.rejected_joints["reprojection_error"] >= 1


def test_api_requires_original_attested_pose_and_signs_session_evidence():
    payload, _ = stereo_input()
    with TestClient(create_app(Settings(api_token=SECRET))) as client:
        headers = {"Authorization": "Bearer " + SECRET}
        references = []
        for index, view in enumerate(payload["views"]):
            response = client.post(
                "/api/v1/coaching", headers=headers, json={"vision": view["pose"]}
            )
            assert response.status_code == 200
            analysis = response.json()
            view["pose"] = analysis["pose"]
            view["analysis_token"] = analysis["summary_token"]
            references.append(
                dict(
                    clip_id=f"view{index}",
                    swing_id="Swing A",
                    summary_token=analysis["summary_token"],
                )
            )
        response = client.post("/api/v1/reconstructions", headers=headers, json=payload)
        assert response.status_code == 200
        receipt = response.json()["evidence_token"]
        combined = client.post(
            "/api/v1/sessions",
            headers=headers,
            json={"attempted_clips": 2, "clips": references, "evidence_tokens": [receipt]},
        )
        assert combined.status_code == 200 and "calibrated_3d" in combined.json()["prompt_payload"]
        payload["views"][0]["pose"]["frames"][0]["landmarks"]["left_hip"]["raw_xy_px"][0] += 1
        assert (
            client.post("/api/v1/reconstructions", headers=headers, json=payload).status_code == 422
        )
        references[1]["swing_id"] = "Swing B"
        assert (
            client.post(
                "/api/v1/sessions",
                headers=headers,
                json={"attempted_clips": 2, "clips": references, "evidence_tokens": [receipt]},
            ).status_code
            == 422
        )


def test_checkerboard_intrinsics_and_world_reference_recover_known_camera():
    columns, rows, square = 9, 6, 0.025
    board = np.zeros((columns * rows, 3), np.float32)
    board[:, :2] = np.mgrid[:columns, :rows].T.reshape(-1, 2) * square
    k = np.array([[900.0, 0, 640], [0, 910.0, 360], [0, 0, 1]])
    observations = []
    for i in range(14):
        r = np.array([0.1 + 0.025 * i, -0.2 + 0.03 * i, 0.025 * i])
        t = np.array([-0.15 + 0.02 * i, -0.1 + 0.008 * i, 1.1 + 0.03 * i])
        observations.append(cv2.projectPoints(board, r, t, k, np.zeros(5))[0])
    ground = np.zeros_like(board)
    ground[:, 0] = board[:, 0]
    ground[:, 2] = board[:, 1]
    reference = cv2.projectPoints(
        ground, np.array([1.2, 0.1, 0.2]), np.array([-0.1, -0.1, 1.5]), k, np.zeros(5)
    )[0]
    profile = calibrate_from_observations(
        observations, (1280, 720), columns, rows, square, reference, "A", "rig"
    )
    np.testing.assert_allclose(profile.camera_matrix, k, atol=0.05)
    assert profile.reference_rms_px < 0.001
    assert not profile.scale_and_orientation_verified
    with pytest.raises(ValueError, match="varied image positions"):
        calibrate_from_observations(
            [observations[0]] * 10, (1280, 720), columns, rows, square, reference, "A", "rig"
        )
