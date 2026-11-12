"""Typed contracts shared by offline coaching, the API and the frontend."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictBool, model_validator

LandmarkName = Literal[
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
]
CameraView = Literal["down_the_line", "face_on", "oblique", "rear", "overhead", "unknown"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Landmark(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    xy_px: tuple[FiniteFloat, FiniteFloat] | None = None
    xy_normalized: tuple[FiniteFloat, FiniteFloat] | None = None
    raw_xy_px: tuple[FiniteFloat, FiniteFloat] | None = None
    confidence: FiniteFloat | None = Field(default=None, ge=0, le=1)
    observed: StrictBool = False
    interpolated: StrictBool = False
    filtered: StrictBool = False


class VisionFrame(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    frame_index: int = Field(ge=0)
    timestamp_seconds: FiniteFloat = Field(ge=0)
    landmarks: dict[LandmarkName, Landmark] = Field(max_length=17)
    angles_deg: dict[str, FiniteFloat | None] = Field(default_factory=dict, max_length=9)
    person_bbox_xyxy_px: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat] | None = None


class VideoMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    width: int = Field(gt=0, le=16_384)
    height: int = Field(gt=0, le=16_384)
    nominal_fps: FiniteFloat = Field(ge=1, le=1000)
    frame_count: int = Field(ge=1, le=12_000)
    timestamp_source: Literal["decoder_pts", "nominal_fps_fallback"]
    source_start_seconds: FiniteFloat = Field(default=0, ge=0)
    source_duration_seconds: FiniteFloat | None = Field(default=None, ge=0)


class VisionDocument(BaseModel):
    """Accept Phase 2 JSON and discard unused metadata before coaching."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    schema_version: Literal["1.0.0"]
    video: VideoMetadata
    frames: list[VisionFrame] = Field(min_length=1, max_length=12_000)

    @model_validator(mode="after")
    def ordered_frames(self):
        if self.video.frame_count != len(self.frames):
            raise ValueError("Frame count must match the number of frames.")
        for index, frame in enumerate(self.frames):
            if frame.frame_index != index:
                raise ValueError("Frame indices must be consecutive and start at zero.")
            if index and frame.timestamp_seconds <= self.frames[index - 1].timestamp_seconds:
                raise ValueError("Frame timestamps must be strictly increasing.")
        if self.frames[0].timestamp_seconds > 0.001:
            raise ValueError("Frame timestamps must start at zero.")
        if self.frames[-1].timestamp_seconds > 30:
            raise ValueError("Only clips up to 30 seconds are supported.")
        return self


class SwingEvents(StrictModel):
    start_seconds: FiniteFloat = Field(ge=0)
    top_seconds: FiniteFloat = Field(gt=0)
    impact_seconds: FiniteFloat = Field(gt=0)

    @model_validator(mode="after")
    def chronological(self):
        if not self.start_seconds < self.top_seconds < self.impact_seconds:
            raise ValueError("Swing markers must satisfy start < top < impact.")
        return self


class AnalysisOptions(StrictModel):
    camera_view: CameraView = "unknown"
    camera_alignment_confirmed: StrictBool = False
    events: SwingEvents | None = None
    estimate_events: StrictBool = True
    confirm_constant_frame_rate: StrictBool = False
    subject_point: tuple[FiniteFloat, FiniteFloat] | None = None
    include_pose: StrictBool = True
    source_start_seconds: FiniteFloat = Field(default=0, ge=0, le=86_400)
    source_end_seconds: FiniteFloat | None = Field(default=None, gt=0, le=86_400)

    @model_validator(mode="after")
    def valid_subject_point(self):
        if (
            self.source_end_seconds is not None
            and not 0 < self.source_end_seconds - self.source_start_seconds <= 30
        ):
            raise ValueError("Choose a source window longer than zero and at most 30 seconds.")
        if self.source_start_seconds > 0 and self.source_end_seconds is None:
            raise ValueError("A nonzero source start requires an explicit end.")
        if self.subject_point and any(not 0 <= v <= 1 for v in self.subject_point):
            raise ValueError("Subject coordinates must be in [0, 1].")
        return self


class SeriesPoint(StrictModel):
    timestamp_seconds: float
    spine_tilt_deg: float | None
    spine_delta_deg: float | None
    wrist_speed_torso_per_second: float | None


class MeasurementGate(StrictModel):
    eligible: bool
    reasons: list[str]


class CameraAssessment(StrictModel):
    declared_view: CameraView
    alignment_confirmed: bool
    assessment: Literal[
        "user_confirmed", "needs_confirmation", "unsupported_view", "projection_conflict"
    ]
    projection_hint: Literal["narrow", "broad", "mixed", "unknown"]
    projected_width_torso_ratio: float | None
    note: str


class TrackingQuality(StrictModel):
    evaluated_frames: int
    detected_fraction: float
    torso_valid_fraction: float
    wrist_pair_valid_fraction: float
    full_body_valid_fraction: float
    border_contact_fraction: float
    interpolated_fraction: float
    largest_torso_gap_seconds: float
    largest_wrist_gap_seconds: float
    torso_jump_count: int
    keypoint_coverage: dict[LandmarkName, float]


class QualityIssue(StrictModel):
    code: str
    severity: Literal["info", "warning", "blocking"]
    message: str


class AnalysisQuality(StrictModel):
    version: str = "1.0.0"
    status: Literal["usable", "limited", "insufficient"]
    window_start_seconds: float
    window_end_seconds: float
    window_source: Literal["swing", "whole_clip"]
    camera: CameraAssessment
    tracking: TrackingQuality
    tempo: MeasurementGate
    posture: MeasurementGate
    issues: list[QualityIssue]


class KinematicsReport(StrictModel):
    version: str = "1.1.0"
    status: Literal["complete", "partial", "insufficient_data"]
    camera_view: CameraView
    events: SwingEvents | None
    event_source: Literal["manual", "estimated"] | None
    timing_reliable: bool
    backswing_seconds: float | None
    downswing_seconds: float | None
    tempo_ratio: float | None
    baseline_spine_tilt_deg: float | None
    impact_spine_tilt_deg: float | None
    spine_delta_deg: float | None
    max_posture_loss_deg: float | None
    posture_valid_fraction: float
    posture_eligible: bool
    quality: AnalysisQuality
    warnings: list[str]
    series: list[SeriesPoint]


class Drill(StrictModel):
    id: str
    name: str
    instructions: list[str]


class Fault(StrictModel):
    code: Literal["LOSS_OF_POSTURE", "TEMPO_OUTSIDE_REFERENCE"]
    title: str
    severity: Literal["observation", "moderate"]
    explanation: str
    evidence: dict[str, float | str]
    drill_ids: list[str]


class RuleReport(StrictModel):
    version: str = "1.1.0"
    faults: list[Fault]
    drills: list[Drill]
    notices: list[str]


class AnalysisResponse(StrictModel):
    analysis_id: str
    summary_token: str = ""
    kinematics: KinematicsReport
    coaching: RuleReport
    prompt_payload: str = Field(min_length=1)
    pose: VisionDocument | None
