"""Public API contracts. Neither request keys nor provider errors enter responses."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.security import HTTPBearer
from pydantic import Field, SecretStr, ValidationError
from starlette.datastructures import UploadFile

from app.coaching.schemas import AnalysisOptions, AnalysisResponse, StrictModel, VisionDocument
from app.errors import ServiceError
from app.services.analysis import AnalysisService

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


def byok_key(
    request: Request,
    raw: Annotated[
        str | None,
        Header(
            alias="X-OpenAI-API-Key",
            description="Optional request-only OpenAI key. Never persisted.",
        ),
    ] = None,
) -> SecretStr | None:
    if len(request.headers.getlist("X-OpenAI-API-Key")) > 1:
        raise ServiceError(400, "invalid_byok_header", "Supply at most one OpenAI key header.")
    if raw is None:
        return None
    value = raw.strip()
    if not value or len(value) > 1024 or any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise ServiceError(400, "invalid_byok_header", "The OpenAI key header is invalid.")
    return SecretStr(value)


def validate_llm_request(options: AnalysisOptions, key: SecretStr | None) -> None:
    if options.llm_enabled is True and key is None:
        raise ServiceError(
            422, "byok_required", "LLM coaching was enabled but no OpenAI key header was provided."
        )


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
    key: Annotated[SecretStr | None, Depends(byok_key)],
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
        validate_llm_request(options, key)
        return await analysis.analyze_upload(video, options, key)


@router.post("/analyses/storage", response_model=AnalysisResponse)
async def analyze_storage(
    body: StorageAnalysisRequest,
    analysis: Annotated[AnalysisService, Depends(service)],
    key: Annotated[SecretStr | None, Depends(byok_key)],
) -> AnalysisResponse:
    validate_llm_request(body.options, key)
    return await analysis.analyze_storage(body.object_path, body.options, key)


@router.post("/coaching", response_model=AnalysisResponse)
async def coach_existing_pose(
    body: CoachingRequest,
    analysis: Annotated[AnalysisService, Depends(service)],
    key: Annotated[SecretStr | None, Depends(byok_key)],
) -> AnalysisResponse:
    validate_llm_request(body.options, key)
    return await analysis.analyze_document(body.vision, body.options, key)
