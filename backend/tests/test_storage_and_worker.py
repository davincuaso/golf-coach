import asyncio
import io
import json
from pathlib import Path

import httpx
import pytest
from starlette.datastructures import UploadFile

from app.coaching.schemas import AnalysisOptions
from app.config import Settings
from app.errors import ServiceError
from app.services.analysis import AnalysisService
from app.storage import download_private_video
from coaching_fixtures import pose_document

TOKEN = "test-backend-token-that-is-long-enough"


def test_private_download_uses_fixed_origin_and_server_credentials(tmp_path):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(200, content=b"video")

    settings = Settings(
        api_token=TOKEN, supabase_url="https://golf.supabase.co", supabase_service_key="server-key"
    )
    factory = lambda **kwargs: httpx.AsyncClient(**kwargs, transport=httpx.MockTransport(handler))
    path = tmp_path / "input.mp4"
    asyncio.run(
        download_private_video("swings/user/swing.mp4", path, settings, client_factory=factory)
    )
    assert path.read_bytes() == b"video"
    assert (
        str(requests[0].url)
        == "https://golf.supabase.co/storage/v1/object/authenticated/swings/swings/user/swing.mp4"
    )
    assert requests[0].headers["Authorization"] == "Bearer server-key"


@pytest.mark.parametrize(
    "status,headers,body,expected",
    [
        (302, {"Location": "https://attacker.invalid"}, b"", 502),
        (404, {}, b"not found", 404),
        (200, {"Content-Length": "2048"}, b"x", 413),
        (200, {}, b"x" * 2048, 413),
        (200, {}, b"", 422),
        (200, {"Content-Encoding": "gzip"}, b"", 502),
    ],
)
def test_download_errors_redirects_and_oversized_bodies_are_bounded(
    tmp_path, status, headers, body, expected
):
    settings = Settings(
        api_token=TOKEN,
        supabase_url="https://golf.supabase.co",
        supabase_service_key="server-key",
        max_video_bytes=1024,
    )
    factory = lambda **kwargs: httpx.AsyncClient(
        **kwargs,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, headers=headers, content=body)
        ),
    )
    with pytest.raises(ServiceError) as raised:
        asyncio.run(
            download_private_video(
                "swings/test.mp4", tmp_path / "input.mp4", settings, client_factory=factory
            )
        )
    assert raised.value.status_code == expected


def test_worker_job_and_environment_do_not_contain_credentials(tmp_path, monkeypatch):
    weights = tmp_path / "trusted.pt"
    weights.write_bytes(b"placeholder")
    service = AnalysisService(Settings(api_token=TOKEN, pose_weights=weights))
    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-environment-secret")
    monkeypatch.setenv("GOLF_SUPABASE_SERVICE_KEY", "storage-secret")

    async def spawn(*args, **kwargs):
        captured.update(kwargs)
        job = json.loads(Path(args[-1]).read_text())
        captured["job"] = job
        Path(job["output"]).write_text(json.dumps(pose_document()))

        class Process:
            returncode = 0

            async def wait(self):
                return 0

        return Process()

    monkeypatch.setattr("app.services.analysis.asyncio.create_subprocess_exec", spawn)
    asyncio.run(service._run_worker(tmp_path / "input.mp4", tmp_path, AnalysisOptions()))
    assert (
        "OPENAI_API_KEY" not in captured["env"]
        and "GOLF_SUPABASE_SERVICE_KEY" not in captured["env"]
    )
    assert TOKEN not in json.dumps(captured["job"]) and "secret" not in json.dumps(captured["env"])


def test_worker_timeout_and_cancellation_kill_the_process(tmp_path, monkeypatch):
    weights = tmp_path / "trusted.pt"
    weights.write_bytes(b"placeholder")
    service = AnalysisService(
        Settings(api_token=TOKEN, pose_weights=weights, worker_timeout_seconds=0.03)
    )
    killed = []

    class Process:
        returncode = None

        async def wait(self):
            await asyncio.sleep(5)

    async def spawn(*args, **kwargs):
        return Process()

    async def kill(process):
        killed.append(process)

    monkeypatch.setattr("app.services.analysis.asyncio.create_subprocess_exec", spawn)
    monkeypatch.setattr("app.services.analysis._kill_worker", kill)
    with pytest.raises(ServiceError) as raised:
        asyncio.run(service._run_worker(tmp_path / "input.mp4", tmp_path, AnalysisOptions()))
    assert raised.value.status_code == 504 and len(killed) == 1

    async def cancel():
        service.settings.worker_timeout_seconds = 10
        task = asyncio.create_task(
            service._run_worker(tmp_path / "input.mp4", tmp_path, AnalysisOptions())
        )
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    assert len(killed) == 2


def test_busy_slot_rejects_work_and_releases_after_failure():
    service = AnalysisService(Settings(api_token=TOKEN))

    async def run():
        async with service._slot():
            with pytest.raises(ServiceError) as raised:
                async with service._slot():
                    pass
            assert raised.value.status_code == 503
        async with service._slot():
            pass

    asyncio.run(run())
