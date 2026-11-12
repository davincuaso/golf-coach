from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field, FiniteFloat, StrictBool, model_validator

from app.coaching.schemas import StrictModel, VisionDocument

Vec3 = tuple[FiniteFloat, FiniteFloat, FiniteFloat]
Matrix3 = tuple[Vec3, Vec3, Vec3]


class CameraCalibration(StrictModel):
    version: Literal["1.0"] = "1.0"
    camera_id: str = Field(min_length=1, max_length=50)
    world_id: str = Field(min_length=1, max_length=80)
    image_width: int = Field(ge=100, le=4096)
    image_height: int = Field(ge=100, le=4096)
    camera_matrix: Matrix3
    distortion: list[FiniteFloat] = Field(min_length=4, max_length=8)
    rotation_world_to_camera: Matrix3
    translation_world_to_camera_m: Vec3
    calibration_rms_px: FiniteFloat = Field(ge=0, le=20)
    reference_rms_px: FiniteFloat = Field(ge=0, le=20)
    scale_and_orientation_verified: StrictBool = False

    @model_validator(mode="after")
    def physical_camera(self):
        k = np.asarray(self.camera_matrix)
        rotation = np.asarray(self.rotation_world_to_camera)
        if (
            len(self.distortion) not in (4, 5, 8)
            or k[0, 0] <= 0
            or k[1, 1] <= 0
            or not np.allclose(k[2], [0, 0, 1])
            or abs(k[0, 1]) > 1e-6
            or abs(k[1, 0]) > 1e-6
            or not 0 <= k[0, 2] <= self.image_width
            or not 0 <= k[1, 2] <= self.image_height
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5)
            or abs(np.linalg.det(rotation) - 1) > 1e-5
        ):
            raise ValueError("Invalid pinhole camera calibration or rotation.")
        return self


class ReconstructionView(StrictModel):
    calibration: CameraCalibration
    pose: VisionDocument
    analysis_token: str = Field(min_length=1, max_length=32000)
    sync_anchor_seconds: FiniteFloat = Field(ge=0, le=30)


class ReconstructionRequest(StrictModel):
    swing_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9 _-]+$")
    views: list[ReconstructionView] = Field(min_length=2, max_length=2)
    same_swing_stationary_confirmed: StrictBool = False
    physical_timebase_confirmed: StrictBool = False
    sync_uncertainty_ms: FiniteFloat = Field(ge=0, le=1000)


class ReconstructedJoint(StrictModel):
    xyz_m: Vec3
    reprojection_error_px: FiniteFloat
    ray_angle_deg: FiniteFloat


class ReconstructionFrame(StrictModel):
    timestamp_seconds: FiniteFloat
    matching_error_ms: FiniteFloat
    joints: dict[str, ReconstructedJoint]
    torso_tilt_deg: FiniteFloat | None


class ReconstructionResponse(StrictModel):
    version: Literal["1.0"] = "1.0"
    swing_id: str
    status: Literal["reconstructed", "insufficient_data"]
    coordinate_system: str = "metres; X right of target, Y up, Z down target line"
    frames: list[ReconstructionFrame]
    accepted_joints: int
    rejected_joints: dict[str, int]
    matched_frames: int
    unmatched_frames: int
    median_reprojection_error_px: FiniteFloat | None
    notices: list[str]
    evidence_token: str = ""


class BallTrackOptions(StrictModel):
    swing_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9 _-]+$")
    seed_source_seconds: FiniteFloat = Field(ge=0, le=86400)
    seed_point: tuple[FiniteFloat, FiniteFloat]
    radius_px: int = Field(ge=2, le=20)
    duration_seconds: FiniteFloat = Field(default=2, gt=0, le=5)
    stationary_confirmed: StrictBool = False
    analysis_token: str = Field(min_length=1, max_length=32000)

    @model_validator(mode="after")
    def normalized_seed(self):
        if any(not 0 <= value <= 1 for value in self.seed_point):
            raise ValueError("Ball seed must be normalized.")
        return self


class BallSample(StrictModel):
    source_seconds: FiniteFloat
    xy_px: tuple[FiniteFloat, FiniteFloat]
    similarity: FiniteFloat
    source: Literal["manual_seed", "model_detection", "appearance_match"] = "appearance_match"


class BallTrackResponse(StrictModel):
    version: Literal["1.0"] = "1.0"
    swing_id: str
    status: Literal["candidate_track", "insufficient_data"]
    width: int
    height: int
    samples: list[BallSample]
    stop_reason: str
    needs_visual_confirmation: Literal[True] = True
    notices: list[str]
    evidence_token: str = ""
    tracker_backend: Literal["onnx_golf_detector", "appearance_baseline"] = "appearance_baseline"
    model_sha256: str | None = None
    model_source: str | None = None
    camera_motion_detected: bool = False
    stationary_confirmed: bool = False
