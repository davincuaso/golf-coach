"""Offline checkerboard calibration; the JSON manifest uses local image paths."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from app.evidence.calibration import calibrate_from_observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if args.output.exists() or args.output.with_suffix(".reference.jpg").exists():
        parser.error("Output already exists; choose a new path.")
    root = args.manifest.parent
    columns, rows = manifest["columns"], manifest["rows"]
    size = None

    def corners(path):
        nonlocal size
        image = cv2.imread(str(root / path))
        if image is None or image.shape[0] * image.shape[1] > 3840 * 2160:
            raise ValueError("Cannot read image or resolution exceeds 4K.")
        current = (image.shape[1], image.shape[0])
        if size is not None and current != size:
            raise ValueError("Use identical decoded orientation and resolution in every image.")
        size = current
        found, points = cv2.findChessboardCornersSB(
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY),
            (columns, rows),
            cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY,
        )
        if not found:
            raise ValueError("Complete checkerboard not found: " + str(path))
        return image, points

    paths = manifest["images"]
    if not 10 <= len(paths) <= 60:
        parser.error("Provide 10–60 varied calibration images.")
    observations = [corners(path)[1] for path in paths]
    image, reference = corners(manifest["world_reference_image"])
    if manifest.get("reverse_reference_order", False):
        reference = reference[::-1].copy()
    profile = calibrate_from_observations(
        observations,
        size,
        columns,
        rows,
        manifest["square_size_m"],
        reference,
        manifest["camera_id"],
        manifest["world_id"],
    )
    for index in (0, columns - 1, (rows - 1) * columns, rows * columns - 1):
        point = tuple(np.round(reference[index, 0]).astype(int))
        cv2.circle(image, point, 8, (0, 0, 255), 2)
        cv2.putText(image, str(index), point, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(profile.model_dump_json(indent=2))
    cv2.imwrite(str(args.output.with_suffix(".reference.jpg")), image)
    print(
        "Saved profile and labelled reference image. Verify shared physical corner IDs, target axes and square scale before enabling scale_and_orientation_verified."
    )


if __name__ == "__main__":
    main()
