"""Credential-free, single-analysis process. Only the parent invokes this module."""

import argparse
import json
import math
import os
from pathlib import Path
import sys


def _limits(timeout_seconds: float, memory_mb: int, result_bytes: int) -> None:
    if os.name != "posix":
        return
    import resource

    seconds = math.ceil(timeout_seconds)
    resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (result_bytes, result_bytes))
    # macOS does not reliably enforce address-space limits. Container memory limits
    # remain required for deployment; Linux also gets an address-space ceiling.
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024**2, memory_mb * 1024**2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    job = json.loads(args.job.read_text())
    _limits(job["timeout_seconds"], job["memory_mb"], job["result_bytes"])
    # Limit native thread fanout when several server processes are deployed.
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    from app.vision.vision_processor import (
        VisionConfig,
        VisionError,
        YoloPoseDetector,
        process_video,
        write_json_atomic,
    )

    try:
        config = VisionConfig(**job["config"])
        weights = Path(job["weights"])
        detector = YoloPoseDetector(weights, config)
        payload = process_video(Path(job["input"]), detector, config)
        write_json_atomic(payload, Path(job["output"]))
        return 0
    except VisionError:
        Path(job["error"]).write_text("invalid_video")
        return 2
    except Exception:
        Path(job["error"]).write_text("processing_failed")
        return 3


if __name__ == "__main__":
    sys.exit(main())
