"""Temporary media lifecycle, worker cancellation and local prompt generation."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from uuid import uuid4

from starlette.datastructures import UploadFile

from app.coaching.kinematics import calculate_kinematics
from app.coaching.llm_synthesizer import generate_coaching_prompt
from app.coaching.rule_engine import evaluate_rules
from app.coaching.schemas import AnalysisOptions, AnalysisResponse, VisionDocument
from app.config import BACKEND_ROOT, Settings
from app.errors import ServiceError
from app.storage import VIDEO_SUFFIXES, download_private_video, validate_object_path
from app.vision.vision_processor import VisionConfig


async def _kill_worker(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
    await process.wait()


class AnalysisService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._slots = asyncio.Semaphore(settings.max_concurrent_analyses)

    @asynccontextmanager
    async def _slot(self):
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=0.1)
        except TimeoutError:
            raise ServiceError(
                503, "analysis_busy", "Analysis capacity is full. Try again shortly."
            ) from None
        try:
            yield
        finally:
            self._slots.release()

    async def _run_worker(self, source: Path, folder: Path, options: AnalysisOptions) -> dict:
        weights = self.settings.pose_weights.resolve()
        if not weights.is_file() or weights.suffix.lower() != ".pt":
            raise ServiceError(
                503, "model_not_ready", "A trusted local pose checkpoint must be configured."
            )
        output, error, job_path = folder / "pose.json", folder / "error.txt", folder / "job.json"
        config = VisionConfig(
            image_size=self.settings.pose_image_size,
            device=self.settings.pose_device,
            cutoff_hz=self.settings.filter_cutoff_hz,
            max_input_bytes=self.settings.max_video_bytes,
            subject_point=options.subject_point,
        )
        from dataclasses import asdict

        job = {
            "input": str(source),
            "output": str(output),
            "error": str(error),
            "weights": str(weights),
            "config": asdict(config),
            "timeout_seconds": self.settings.worker_timeout_seconds,
            "memory_mb": self.settings.worker_memory_mb,
            "result_bytes": self.settings.max_result_bytes,
        }
        job_path.write_text(json.dumps(job, allow_nan=False))
        # A strict environment allowlist keeps API/service credentials out of the child.
        allowed = (
            "PATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "SYSTEMROOT",
            "WINDIR",
            "LD_LIBRARY_PATH",
            "DYLD_LIBRARY_PATH",
            "CUDA_VISIBLE_DEVICES",
        )
        environment = {key: os.environ[key] for key in allowed if key in os.environ}
        environment.update(
            {"YOLO_CONFIG_DIR": str(folder / "yolo"), "MPLCONFIGDIR": str(folder / "matplotlib")}
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.vision.worker",
            "--job",
            str(job_path),
            cwd=BACKEND_ROOT,
            env=environment,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=os.name == "posix",
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=self.settings.worker_timeout_seconds)
        except TimeoutError:
            await _kill_worker(process)
            raise ServiceError(
                504,
                "analysis_timeout",
                "Video processing exceeded the time limit. Trim the clip or use a smaller pose model.",
            ) from None
        except BaseException:
            await _kill_worker(process)
            raise
        if process.returncode != 0:
            if (
                error.is_file()
                and error.stat().st_size < 100
                and error.read_text() == "invalid_video"
            ):
                raise ServiceError(
                    422,
                    "invalid_video",
                    "The video could not be analyzed. Check the codec, clip limits, subject selection and filter frame rate.",
                )
            raise ServiceError(
                500,
                "processing_failed",
                "The pose worker failed. Check server model and resource configuration.",
            )
        if not output.is_file() or output.stat().st_size > self.settings.max_result_bytes:
            raise ServiceError(
                500, "invalid_worker_result", "Pose output was missing or exceeded its limit."
            )
        return await asyncio.to_thread(lambda: json.loads(output.read_text()))

    async def _finish(
        self,
        payload: VisionDocument | dict,
        options: AnalysisOptions,
    ) -> AnalysisResponse:
        def compute():
            document = VisionDocument.model_validate(payload)
            metrics = calculate_kinematics(document, options)
            return document, metrics, evaluate_rules(metrics)

        try:
            document, metrics, rules = await asyncio.to_thread(compute)
        except ValueError:
            raise ServiceError(
                422, "invalid_analysis", "Pose data or swing markers are invalid for this clip."
            ) from None
        return AnalysisResponse(
            analysis_id=str(uuid4()),
            kinematics=metrics,
            coaching=rules,
            prompt_payload=generate_coaching_prompt(metrics, rules),
            pose=document if options.include_pose else None,
        )

    async def analyze_document(
        self,
        document: VisionDocument,
        options: AnalysisOptions,
    ) -> AnalysisResponse:
        async with self._slot():
            return await self._finish(document, options)

    async def analyze_upload(
        self,
        video: UploadFile,
        options: AnalysisOptions,
    ) -> AnalysisResponse:
        suffix = Path(video.filename or "").suffix.lower()
        if suffix not in VIDEO_SUFFIXES:
            raise ServiceError(
                415, "unsupported_video", "Choose an MP4, MOV, WebM, AVI or M4V video."
            )
        async with self._slot():
            with tempfile.TemporaryDirectory(prefix="golf-analysis-") as directory:
                folder = Path(directory)
                source, size = folder / ("input" + suffix), 0
                with source.open("xb") as handle:
                    while chunk := await video.read(1024 * 1024):
                        size += len(chunk)
                        if size > self.settings.max_video_bytes:
                            raise ServiceError(
                                413, "video_too_large", "Video exceeds the configured byte limit."
                            )
                        handle.write(chunk)
                if size == 0:
                    raise ServiceError(422, "empty_video", "The uploaded video is empty.")
                payload = await self._run_worker(source, folder, options)
                return await self._finish(payload, options)

    async def analyze_storage(
        self,
        object_path: str,
        options: AnalysisOptions,
    ) -> AnalysisResponse:
        validate_object_path(object_path, self.settings.storage_prefix)
        async with self._slot():
            with tempfile.TemporaryDirectory(prefix="golf-analysis-") as directory:
                folder = Path(directory)
                source = folder / ("input" + Path(object_path).suffix.lower())
                await download_private_video(object_path, source, self.settings)
                payload = await self._run_worker(source, folder, options)
                return await self._finish(payload, options)
