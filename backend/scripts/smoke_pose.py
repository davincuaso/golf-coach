"""Explicit online smoke test: downloads small official YOLO weights, uses bundled imagery.

Run from backend/: ../.venv/bin/python scripts/smoke_pose.py
Not a golf-accuracy benchmark. Generated video/results stay in ignored data/.
"""

import os
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / "data" / ".ultralytics"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / ".matplotlib"))


def main():
    import cv2
    import numpy as np
    from ultralytics import YOLO
    from ultralytics.utils import ASSETS

    from app.vision.vision_processor import (
        VisionConfig,
        YoloPoseDetector,
        process_video,
        write_json_atomic,
    )

    weights = BACKEND / "models" / "yolov8n-pose.pt"
    if not weights.exists():
        # Official Ultralytics download, deliberately separate from offline processing.
        previous = Path.cwd()
        try:
            os.chdir(weights.parent)
            YOLO(weights.name)
        finally:
            os.chdir(previous)
    image = cv2.imread(str(ASSETS / "bus.jpg"))
    if image is None:
        raise RuntimeError("Ultralytics bundled test image is missing.")
    config = VisionConfig(image_size=640)
    detector = YoloPoseDetector(weights, config)
    detections = detector.detect(image)
    if not detections:
        raise RuntimeError("No people detected in the bundled test image.")
    # Crop around one detected person to exercise the conservative subject selector.
    target = max(detections, key=lambda d: float(np.prod(d.bbox[2:] - d.bbox[:2])))
    x1, y1, x2, y2 = np.rint(target.bbox).astype(int)
    height, width = image.shape[:2]
    crop = image[max(0, y1) : min(height, y2), max(0, x1) : min(width, x2)]
    crop = cv2.resize(crop, (320, 640))
    crop_detections = detector.detect(crop)
    target = max(crop_detections, key=lambda d: float(np.prod(d.bbox[2:] - d.bbox[:2])))
    subject_point = None
    for fx in (0.5, 0.3, 0.7):
        for fy in (0.5, 0.7, 0.3):
            point = target.bbox[:2] + [fx, fy] * (target.bbox[2:] - target.bbox[:2])
            nearby = [
                d
                for d in crop_detections
                if np.all(point >= d.bbox[:2] - 8) and np.all(point <= d.bbox[2:] + 8)
            ]
            if len(nearby) == 1:
                subject_point = tuple(float(v) for v in point / [320, 640])
                break
        if subject_point is not None:
            break
    if subject_point is None:
        raise RuntimeError("Cannot isolate a test subject in bundled sample imagery.")
    config = replace(config, subject_point=subject_point)
    destination = ROOT / "data" / "smoke.avi"
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 640))
    if not writer.isOpened():
        raise RuntimeError("MJPG encoder unavailable.")
    try:
        for _ in range(24):
            writer.write(crop)
    finally:
        writer.release()
    payload = process_video(destination, detector, config)
    assert payload["video"]["frame_count"] == 24
    assert payload["quality"]["observed_landmark_fraction"] > 0.2
    assert any(v is not None for v in payload["frames"][12]["angles_deg"].values())
    output = ROOT / "data" / "smoke.analysis.json"
    write_json_atomic(payload, output, overwrite=True)
    print(
        f"Real YOLO inference passed: 24 frames; observed landmarks "
        f"{payload['quality']['observed_landmark_fraction']:.1%}; result: {output}"
    )


if __name__ == "__main__":
    main()
