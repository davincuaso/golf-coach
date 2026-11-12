import asyncio
import json

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.errors import ServiceError
from app.main import create_app
from coaching_fixtures import MARKERS, pose_document

TOKEN = "test-backend-token-that-is-long-enough"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def application():
    return create_app(Settings(api_token=TOKEN, max_video_bytes=1024))


@pytest.fixture
def client(application):
    with TestClient(application, raise_server_exceptions=False) as value:
        yield value


def coaching_body(**options):
    return {
        "vision": pose_document(spine_at=lambda t: 20 if t > 1.25 else 45),
        "options": {
            "camera_view": "down_the_line",
            "camera_alignment_confirmed": True,
            "events": MARKERS,
            **options,
        },
    }


def test_health_openapi_authentication_and_origin_checks(client):
    assert client.get("/health").json()["status"] == "ok"
    schema = client.get("/openapi.json").json()
    assert "/api/v1/analyses" in schema["paths"]
    assert client.post("/api/v1/coaching", content=b"bad json").status_code == 401
    assert (
        client.post(
            "/api/v1/coaching",
            headers={**AUTH, "Origin": "https://attacker.invalid"},
            json=coaching_body(),
        ).status_code
        == 403
    )
    preflight = client.options(
        "/api/v1/coaching",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_coaching_returns_metrics_rules_and_a_local_prompt(client):
    response = client.post("/api/v1/coaching", headers=AUTH, json=coaching_body(include_pose=False))
    assert response.status_code == 200
    data = response.json()
    assert data["kinematics"]["tempo_ratio"] == 3
    assert data["coaching"]["faults"][0]["code"] == "LOSS_OF_POSTURE"
    assert "master golf professional" in data["prompt_payload"]
    assert "LOSS_OF_POSTURE" in data["prompt_payload"]
    assert "llm" not in data and data["pose"] is None
    assert response.headers["cache-control"] == "no-store"


def test_retired_headers_are_ignored_and_never_enter_the_prompt(client):
    for raw in ("obsolete private key", "x" * 1025):
        response = client.post(
            "/api/v1/coaching", headers={**AUTH, "X-OpenAI-API-Key": raw}, json=coaching_body()
        )
        assert response.status_code == 200
        assert raw not in response.text


def test_schema_exposes_prompt_generation_without_ai_options_or_headers(client):
    schema = client.get("/openapi.json").json()
    assert "llm_enabled" not in schema["components"]["schemas"]["AnalysisOptions"]["properties"]
    response = schema["components"]["schemas"]["AnalysisResponse"]
    assert "prompt_payload" in response["required"]
    assert "llm" not in response["properties"]
    assert "X-OpenAI-API-Key" not in json.dumps(schema)
    assert (
        client.post(
            "/api/v1/coaching", headers=AUTH, json=coaching_body(llm_enabled=True)
        ).status_code
        == 422
    )


def test_validation_errors_do_not_echo_input(client):
    response = client.post(
        "/api/v1/coaching", headers=AUTH, json={"vision": "private-invalid-input"}
    )
    assert response.status_code == 422 and "private-invalid-input" not in response.text


def test_upload_runs_pipeline_and_deletes_temporary_files(client, application, monkeypatch):
    sources = []

    async def worker(source, folder, options):
        assert source.read_bytes() == b"video-fixture"
        assert source.name == "input.mp4"  # User filename never becomes a filesystem path.
        sources.append(source)
        return pose_document()

    monkeypatch.setattr(application.state.analysis_service, "_run_worker", worker)
    response = client.post(
        "/api/v1/analyses",
        headers=AUTH,
        files={"video": ("../../private.mp4", b"video-fixture", "video/mp4")},
        data={"options": json.dumps({"events": MARKERS, "include_pose": False})},
    )
    assert response.status_code == 200
    assert response.json()["kinematics"]["tempo_ratio"] == 3
    assert response.json()["prompt_payload"].strip()
    assert "private.mp4" not in response.json()["prompt_payload"]
    assert not sources[0].exists() and not sources[0].parent.exists()


def test_upload_validation_size_and_cleanup_on_failure(client, application, monkeypatch):
    cases = [("video.exe", b"x", 415), ("video.mp4", b"", 422), ("video.mp4", b"x" * 1025, 413)]
    for filename, content, status in cases:
        assert (
            client.post(
                "/api/v1/analyses", headers=AUTH, files={"video": (filename, content)}
            ).status_code
            == status
        )
    assert (
        client.post(
            "/api/v1/analyses",
            headers=AUTH,
            files=[("video", ("a.mp4", b"x")), ("video", ("b.mp4", b"x"))],
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/analyses",
            headers=AUTH,
            files={"video": ("a.mp4", b"x")},
            data={"options": "not-json"},
        ).status_code
        == 422
    )
    directories = []

    async def worker(source, folder, options):
        directories.append(folder)
        raise ServiceError(504, "analysis_timeout", "Analysis timed out.")

    monkeypatch.setattr(application.state.analysis_service, "_run_worker", worker)
    assert (
        client.post("/api/v1/analyses", headers=AUTH, files={"video": ("a.mp4", b"x")}).status_code
        == 504
    )
    assert not directories[0].exists()


def test_streamed_body_limit_applies_without_content_length(application):
    async def run():
        async def body():
            for _ in range(20):
                yield b"x" * 100_000

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as client:
            return await client.post(
                "/api/v1/coaching",
                headers={**AUTH, "Content-Type": "application/json"},
                content=body(),
            )

    assert asyncio.run(run()).status_code == 413


def test_interrupted_multipart_upload_closes_spooled_files(application, monkeypatch):
    import starlette.formparsers

    opened = []
    original = starlette.formparsers.SpooledTemporaryFile

    def tracked(*args, **kwargs):
        file = original(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", tracked)

    async def run():
        async def body():
            yield b'--golf\r\nContent-Disposition: form-data; name="video"; filename="swing.mp4"\r\nContent-Type: video/mp4\r\n\r\n'
            yield b"x" * 600_000
            yield b"x" * 600_000

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as client:
            return await client.post(
                "/api/v1/analyses",
                headers={**AUTH, "Content-Type": "multipart/form-data; boundary=golf"},
                content=body(),
            )

    assert asyncio.run(run()).status_code == 413
    assert opened and all(file.closed for file in opened)


def test_storage_rejects_arbitrary_urls_local_paths_and_unconfigured_storage(client):
    for path in (
        "https://127.0.0.1/private.mp4",
        "/etc/passwd",
        "swings/../secret.mp4",
        "other/swing.mp4",
    ):
        assert (
            client.post(
                "/api/v1/analyses/storage", headers=AUTH, json={"object_path": path}
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/api/v1/analyses/storage", headers=AUTH, json={"object_path": "swings/test.mp4"}
        ).status_code
        == 503
    )


def test_unexpected_errors_do_not_escape_to_server_tracebacks(
    client, application, monkeypatch, caplog
):
    async def broken(*args):
        raise RuntimeError("sk-secret-in-an-unexpected-error")

    monkeypatch.setattr(application.state.analysis_service, "analyze_document", broken)
    response = client.post("/api/v1/coaching", headers=AUTH, json=coaching_body())
    assert response.status_code == 500
    assert "sk-secret" not in response.text + caplog.text


def test_server_requires_a_nonplaceholder_token_and_normalizes_model_path():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(api_token="short")
    with pytest.raises(ValidationError):
        Settings(api_token="replace-with-a-random-token-at-least-24-characters")
    assert Settings(api_token=TOKEN, pose_weights="models/test.pt").pose_weights.is_absolute()
