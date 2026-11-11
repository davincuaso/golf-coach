"""Run: python -m uvicorn app.main:create_app --factory --no-access-log"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.api.middleware import PRIVATE_HEADERS, RequestGuards
from app.api.routes import router
from app.config import Settings
from app.errors import ServiceError
from app.services.analysis import AnalysisService

LOGGER = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Golf Coach API", version="0.5.0")
    app.state.settings = settings
    app.state.analysis_service = AnalysisService(settings)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}},
            error.status_code,
            headers=PRIVATE_HEADERS,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # Default errors may contain the original input. Never echo it.
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request fields are invalid. Check the API schema and swing markers.",
                }
            },
            422,
            headers=PRIVATE_HEADERS,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return JSONResponse(
            {"error": {"code": "http_error", "message": "The request could not be accepted."}},
            error.status_code,
            headers={**PRIVATE_HEADERS, **(error.headers or {})},
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        LOGGER.error("Request failed with %s", type(error).__name__)
        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "The server could not complete this request.",
                }
            },
            500,
            headers=PRIVATE_HEADERS,
        )

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "version": "0.5.0"}

    app.include_router(router)
    app.add_middleware(RequestGuards, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["POST", "GET"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
        max_age=600,
    )
    return app
