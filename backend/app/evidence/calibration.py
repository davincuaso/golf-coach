"""Create an OpenCV pinhole profile from checkerboard observations."""

import cv2
import numpy as np

from app.evidence.schemas import CameraCalibration


def calibrate_from_observations(
    image_points, image_size, columns, rows, square_m, reference_corners, camera_id, world_id
):
    if (
        not 10 <= len(image_points) <= 60
        or not 3 <= columns <= 20
        or not 3 <= rows <= 20
        or not 0.005 <= square_m <= 0.2
    ):
        raise ValueError(
            "Use 10–60 varied checkerboard images, 3–20 inner corners per dimension, and a measured square size in metres."
        )
    board = np.zeros((columns * rows, 3), np.float32)
    board[:, :2] = np.mgrid[:columns, :rows].T.reshape(-1, 2) * square_m
    observations = [np.asarray(points, np.float32).reshape(-1, 1, 2) for points in image_points]
    if any(len(points) != len(board) or not np.isfinite(points).all() for points in observations):
        raise ValueError("Every calibration image needs the complete board.")
    centers = np.array([points.reshape(-1, 2).mean(axis=0) for points in observations])
    if np.linalg.norm(np.ptp(centers, axis=0) / image_size) < 0.05:
        raise ValueError(
            "Move the checkerboard across varied image positions; repeated near-identical views are insufficient."
        )
    rms, k, distortion, rotations, _ = cv2.calibrateCamera(
        [board] * len(observations), observations, image_size, None, None
    )
    normals = np.array([cv2.Rodrigues(rotation)[0][:, 2] for rotation in rotations])
    separation = np.degrees(np.arccos(np.clip(normals @ normals.T, -1, 1)))
    if np.max(separation) < 10:
        raise ValueError(
            "Vary checkerboard tilt by at least 10 degrees; translation-only views do not sufficiently constrain the lens."
        )
    # Ground reference: columns point right of target (+X), rows down target (+Z).
    ground = np.zeros_like(board)
    ground[:, 0], ground[:, 2] = board[:, 0], board[:, 1]
    reference = np.asarray(reference_corners, np.float32).reshape(-1, 1, 2)
    if reference.shape != observations[0].shape:
        raise ValueError("Reference board corners are incomplete.")
    success, rvec, translation = cv2.solvePnP(ground, reference, k, distortion)
    if not success:
        raise ValueError("Reference camera pose could not be solved.")
    predicted = cv2.projectPoints(ground, rvec, translation, k, distortion)[0]
    reference_rms = float(np.sqrt(np.mean(np.sum((predicted - reference) ** 2, axis=2))))
    return CameraCalibration(
        camera_id=camera_id,
        world_id=world_id,
        image_width=image_size[0],
        image_height=image_size[1],
        camera_matrix=k.tolist(),
        distortion=distortion.ravel().tolist(),
        rotation_world_to_camera=cv2.Rodrigues(rvec)[0].tolist(),
        translation_world_to_camera_m=translation.ravel().tolist(),
        calibration_rms_px=rms,
        reference_rms_px=reference_rms,
        scale_and_orientation_verified=False,
    )
