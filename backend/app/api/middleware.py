"""Authenticate before parsing uploads and enforce streaming request limits."""

import asyncio
import secrets
import time

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.config import Settings

PRIVATE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


class RequestGuards:
    def __init__(self, app, settings: Settings):
        self.app, self.settings = app, settings
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {}
        for name, value in scope["headers"]:
            headers.setdefault(name.lower(), []).append(value)
        protected = scope["path"].startswith("/api/v1")

        async def reject(status, code, message):
            response = JSONResponse(
                {"error": {"code": code, "message": message}},
                status,
                headers={
                    **PRIVATE_HEADERS,
                    **({"WWW-Authenticate": "Bearer"} if status == 401 else {}),
                },
            )
            await response(scope, receive, send)

        if protected:
            credentials = headers.get(b"authorization", [])
            expected = self.settings.api_token.get_secret_value().encode()
            scheme, _, supplied = (
                credentials[0].partition(b" ") if len(credentials) == 1 else (b"", b"", b"")
            )
            if scheme.lower() != b"bearer" or not secrets.compare_digest(supplied, expected):
                return await reject(
                    401, "unauthorized", "A valid backend bearer token is required."
                )
            origins = headers.get(b"origin", [])
            if origins and (
                len(origins) != 1 or origins[0].decode("latin-1") not in self.settings.cors_origins
            ):
                return await reject(403, "origin_forbidden", "This browser origin is not allowed.")
            if self.active >= self.settings.max_concurrent_analyses * 4:
                return await reject(
                    503, "server_busy", "Request capacity is full. Try again shortly."
                )

        limit = {
            "/api/v1/sessions": 1024 * 1024,
            "/api/v1/shot-imports": 1024 * 1024,
            "/api/v1/reconstructions": 16 * 1024 * 1024,
        }.get(scope["path"], self.settings.max_video_bytes + 1024 * 1024)
        lengths = headers.get(b"content-length", [])
        if len(lengths) > 1 or (lengths and not lengths[0].isdigit()):
            return await reject(400, "invalid_content_length", "Invalid Content-Length header.")
        if lengths and (len(lengths[0]) > 20 or int(lengths[0]) > limit):
            return await reject(
                413, "request_too_large", "The request exceeds the configured byte limit."
            )
        total, start = 0, time.monotonic()
        response_started = False

        async def limited_receive():
            nonlocal total
            remaining = self.settings.upload_timeout_seconds - (time.monotonic() - start)
            if remaining <= 0:
                raise HTTPException(408, "Upload time limit exceeded.")
            try:
                message = await asyncio.wait_for(receive(), timeout=remaining)
            except TimeoutError:
                raise HTTPException(408, "Upload time limit exceeded.") from None
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise HTTPException(413, "The request exceeds the configured byte limit.")
            return message

        async def private_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                response_headers = list(message.get("headers", []))
                for name, value in PRIVATE_HEADERS.items():
                    lowered = name.lower().encode()
                    response_headers = [
                        (key, val) for key, val in response_headers if key.lower() != lowered
                    ]
                    response_headers.append((lowered, value.encode()))
                message = {**message, "headers": response_headers}
            await send(message)

        if protected:
            self.active += 1
        try:
            await self.app(scope, limited_receive, private_send)
        except HTTPException as error:
            if not response_started:
                await reject(
                    error.status_code, "request_rejected", "The request could not be accepted."
                )
        except Exception:
            # Do not allow the ASGI server to log an input-bearing traceback.
            if not response_started:
                await reject(500, "internal_error", "The server could not complete this request.")
        finally:
            if protected:
                self.active -= 1
