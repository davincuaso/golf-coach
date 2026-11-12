"""Authenticated analysis endpoints with locally generated coaching prompts."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBearer
from pydantic import Field, ValidationError
from starlette.datastructures import UploadFile

from app.coaching.schemas import AnalysisOptions, AnalysisResponse, StrictModel, VisionDocument
from app.errors import ServiceError
from app.services.analysis import AnalysisService
from app.services.sessions import (
    SessionRequest,
    SessionResponse,
    summarize_session,
    verify_pose,
    verify_video_source,
)
from app.evidence.schemas import (
    ReconstructionRequest,
    ReconstructionResponse,
    BallTrackOptions,
    BallTrackResponse,
)
from app.evidence.reconstruction import reconstruct
from app.evidence.launch_monitor import ShotImportRequest, ShotImportResponse, import_shots
from app.evidence.tokens import sign_evidence

router = APIRouter(
    prefix="/api/v1", dependencies=[Depends(HTTPBearer(scheme_name="BackendBearer"))]
)


class StorageAnalysisRequest(StrictModel):
    object_path: str = Field(min_length=1, max_length=1024)
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)


class CoachingRequest(StrictModel):
    vision: VisionDocument
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)


def service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


@router.post(
    "/analyses",
    response_model=AnalysisResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["video"],
                        "properties": {
                            "video": {"type": "string", "format": "binary"},
                            "options": {
                                "type": "string",
                                "description": "JSON-encoded AnalysisOptions",
                                "default": "{}",
                            },
                        },
                    }
                }
            },
        },
    },
)
async def analyze_video(
    request: Request,
    analysis: Annotated[AnalysisService, Depends(service)],
) -> AnalysisResponse:
    async with request.form(max_files=1, max_fields=1, max_part_size=16_384) as form:
        if (
            set(form) - {"video", "options"}
            or len(form.getlist("video")) != 1
            or len(form.getlist("options")) > 1
        ):
            raise ServiceError(422, "invalid_form", "Supply one video and optional JSON options.")
        video, encoded_options = form.get("video"), form.get("options", "{}")
        if not isinstance(video, UploadFile) or not isinstance(encoded_options, str):
            raise ServiceError(422, "invalid_form", "Supply one video file and JSON options.")
        try:
            options = AnalysisOptions.model_validate_json(encoded_options)
        except ValidationError:
            raise ServiceError(422, "invalid_options", "Analysis options are invalid.") from None
        return await analysis.analyze_upload(video, options)


@router.post("/analyses/storage", response_model=AnalysisResponse)
async def analyze_storage(
    body: StorageAnalysisRequest,
    analysis: Annotated[AnalysisService, Depends(service)],
) -> AnalysisResponse:
    return await analysis.analyze_storage(body.object_path, body.options)


@router.post("/coaching", response_model=AnalysisResponse)
async def coach_existing_pose(
    body: CoachingRequest,
    analysis: Annotated[AnalysisService, Depends(service)],
) -> AnalysisResponse:
    return await analysis.analyze_document(body.vision, body.options)


@router.post("/sessions", response_model=SessionResponse)
async def combine_session(body: SessionRequest, request: Request) -> SessionResponse:
    return summarize_session(body, request.app.state.settings.api_token.get_secret_value())


@router.post("/reconstructions", response_model=ReconstructionResponse)
def reconstruct_swing(body: ReconstructionRequest, request: Request) -> ReconstructionResponse:
    secret = request.app.state.settings.api_token.get_secret_value()
    identifiers = [verify_pose(view.analysis_token, view.pose, secret) for view in body.views]
    if len(set(identifiers)) != 2:
        raise ServiceError(422, "duplicate_view", "Use two independently analyzed camera views.")
    report = reconstruct(body)
    summary = report.model_dump(mode="json", exclude={"frames", "evidence_token"})
    tilts = [frame.torso_tilt_deg for frame in report.frames if frame.torso_tilt_deg is not None]
    summary["torso_tilt_range_deg"] = [min(tilts), max(tilts)] if tilts else None
    report.evidence_token = sign_evidence(
        "calibrated_3d", [body.swing_id], identifiers, summary, secret
    )
    return report


@router.post("/shot-imports", response_model=ShotImportResponse)
def analyze_shot_import(body: ShotImportRequest, request: Request) -> ShotImportResponse:
    report = import_shots(body)
    report.evidence_token = sign_evidence(
        "launch_monitor_import",
        [shot.swing_id for shot in report.shots],
        [],
        report.model_dump(mode="json", exclude={"evidence_token"}),
        request.app.state.settings.api_token.get_secret_value(),
    )
    return report


@router.post("/ball-tracks", response_model=BallTrackResponse)
async def track_visible_ball(
    request: Request, analysis: Annotated[AnalysisService, Depends(service)]
) -> BallTrackResponse:
    async with request.form(max_files=1, max_fields=1, max_part_size=64000) as form:
        if (
            set(form) != {"video", "options"}
            or len(form.getlist("video")) != 1
            or len(form.getlist("options")) != 1
        ):
            raise ServiceError(422, "invalid_form", "Supply one video and ball tracking options.")
        video, raw = form.get("video"), form.get("options")
        if not isinstance(video, UploadFile) or not isinstance(raw, str):
            raise ServiceError(422, "invalid_form", "Supply one video and JSON options.")
        try:
            options = BallTrackOptions.model_validate_json(raw)
        except ValidationError:
            raise ServiceError(
                422,
                "invalid_ball_options",
                "Check the seed time, radius, point and source analysis.",
            ) from None
        secret = request.app.state.settings.api_token.get_secret_value()
        identifier, digest = verify_video_source(options.analysis_token, secret)
        report = await analysis.analyze_ball_upload(video, options, digest)
        report.evidence_token = sign_evidence(
            "ball_candidate_track",
            [options.swing_id],
            [identifier],
            {
                **report.model_dump(mode="json", exclude={"samples", "evidence_token"}),
                "candidate_samples": len(report.samples),
                "tracked_span_seconds": report.samples[-1].source_seconds
                - report.samples[0].source_seconds
                if len(report.samples) > 1
                else 0,
            },
            secret,
        )
        return report
