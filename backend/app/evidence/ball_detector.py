"""Local single-class YOLOv8 ONNX inference with aspect-correct ROI letterboxing.

Uses OpenCV DNN, not downloaded Python code or pickle checkpoints. Model accuracy
must be evaluated on the user's capture conditions; detections remain candidates.
"""

from pathlib import Path
import hashlib

import cv2
import numpy as np

MODEL_URL = "https://huggingface.co/notjulietxd/golf-ball-tracker"
MODEL_SHA256 = "9e948135c9898c2b0e4194fa992308a0bbb478e21f6407dda12cb49e3e91ac22"


def parse_detections(output, scale, padding, origin, image_size, confidence=0.5, normalized=False):
    predictions = np.asarray(output)
    if predictions.ndim != 3 or predictions.shape[0] != 1 or predictions.shape[1] != 5:
        raise ValueError("Expected a single-class YOLOv8 output shaped (1, 5, N).")
    boxes, scores, centers = [], [], []
    for cx, cy, width, height, score in predictions[0].T:
        if (
            not np.isfinite([cx, cy, width, height, score]).all()
            or not confidence <= score <= 1
            or width <= 0
            or height <= 0
        ):
            continue
        if normalized:
            cx, cy, width, height = np.asarray([cx, cy, width, height]) * 640
        point = np.array(
            [(cx - padding[0]) / scale + origin[0], (cy - padding[1]) / scale + origin[1]]
        )
        size = np.array([width, height]) / scale
        if not (0 <= point[0] < image_size[0] and 0 <= point[1] < image_size[1]):
            continue
        boxes.append(
            [
                float(point[0] - size[0] / 2),
                float(point[1] - size[1] / 2),
                float(size[0]),
                float(size[1]),
            ]
        )
        centers.append(point)
        scores.append(float(score))
    keep = cv2.dnn.NMSBoxes(boxes, scores, confidence, 0.4)
    return [(centers[int(i)], scores[int(i)]) for i in np.asarray(keep).ravel()]


class OnnxGolfBallDetector:
    def __init__(self, path: Path, coordinate_units: str | None = None):
        if (
            path.suffix.lower() != ".onnx"
            or not path.is_file()
            or path.stat().st_size > 100 * 1024 * 1024
        ):
            raise ValueError("Configure an existing trusted ONNX ball detector under 100 MiB.")
        with path.open("rb") as handle:
            self.sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
        # This pinned export produces normalized xywh, verified by actual inference.
        # Never silently infer custom model units from the current detections.
        self.coordinate_units = coordinate_units or (
            "normalized" if self.sha256 == MODEL_SHA256 else None
        )
        if self.coordinate_units not in ("pixels", "normalized"):
            raise ValueError("Declare output coordinate units for a custom ONNX model.")
        self.net = cv2.dnn.readNetFromONNX(str(path))

    def detect(self, image, prediction):
        height, width = image.shape[:2]
        left = max(0, min(width - 1, int(prediction[0]) - 320))
        top = max(0, min(height - 1, int(prediction[1]) - 320))
        right = min(width, left + 640)
        bottom = min(height, top + 640)
        crop = image[top:bottom, left:right]
        scale = min(640 / crop.shape[1], 640 / crop.shape[0])
        resized = cv2.resize(crop, (round(crop.shape[1] * scale), round(crop.shape[0] * scale)))
        pad = ((640 - resized.shape[1]) // 2, (640 - resized.shape[0]) // 2)
        padded = np.full((640, 640, 3), 114, dtype=np.uint8)
        padded[pad[1] : pad[1] + resized.shape[0], pad[0] : pad[0] + resized.shape[1]] = resized
        self.net.setInput(cv2.dnn.blobFromImage(padded, 1 / 255, (640, 640), swapRB=True))
        return parse_detections(
            self.net.forward(),
            scale,
            pad,
            (left, top),
            (width, height),
            normalized=self.coordinate_units == "normalized",
        )


def associate(candidates, prediction, gate, ambiguity):
    choices = sorted(
        [
            (float(np.linalg.norm(point - prediction)), point, score)
            for point, score in candidates
            if np.linalg.norm(point - prediction) <= gate
        ],
        key=lambda item: item[0],
    )
    if not choices:
        return None, "model_detection_lost"
    if len(choices) > 1 and choices[1][0] - choices[0][0] < ambiguity:
        return None, "model_identity_ambiguous"
    return (choices[0][1], choices[0][2]), "accepted"
