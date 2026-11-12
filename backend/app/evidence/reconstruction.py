"""Two-view metric triangulation, with distortion, timing and geometry gates."""

from bisect import bisect_left
from collections import Counter

import cv2
import numpy as np

from app.errors import ServiceError
from app.evidence.schemas import (
    CameraCalibration,
    ReconstructedJoint,
    ReconstructionFrame,
    ReconstructionRequest,
    ReconstructionResponse,
)
from app.vision.vision_processor import LANDMARKS


def camera_arrays(camera: CameraCalibration):
    return (
        np.asarray(camera.camera_matrix, dtype=float),
        np.asarray(camera.distortion, dtype=float),
        np.asarray(camera.rotation_world_to_camera, dtype=float),
        np.asarray(camera.translation_world_to_camera_m, dtype=float),
    )


def triangulate(a, b, cameras) -> tuple[ReconstructedJoint | None, str]:
    normalized, projections, centers = [], [], []
    for point, (k, distortion, rotation, translation) in zip((a, b), cameras, strict=True):
        normalized.append(
            cv2.undistortPoints(np.array([[point]], dtype=float), k, distortion).reshape(2)
        )
        projections.append(np.column_stack((rotation, translation)))
        centers.append(-rotation.T @ translation)
    homogeneous = cv2.triangulatePoints(
        projections[0], projections[1], normalized[0].reshape(2, 1), normalized[1].reshape(2, 1)
    ).ravel()
    if abs(homogeneous[3]) < 1e-9:
        return None, "unstable_depth"
    xyz = homogeneous[:3] / homogeneous[3]
    if not np.isfinite(xyz).all() or np.linalg.norm(xyz) > 30:
        return None, "outside_capture_volume"
    rays = [xyz - center for center in centers]
    cosine = float(np.dot(*rays) / (np.linalg.norm(rays[0]) * np.linalg.norm(rays[1]) + 1e-15))
    angle = float(np.degrees(np.arccos(np.clip(cosine, -1, 1))))
    if min(angle, 180 - angle) < 3:
        return None, "narrow_ray_angle"
    errors = []
    for point, (k, distortion, rotation, translation) in zip((a, b), cameras, strict=True):
        if (rotation @ xyz + translation)[2] <= 0:
            return None, "behind_camera"
        projected = cv2.projectPoints(
            xyz.reshape(1, 3), cv2.Rodrigues(rotation)[0], translation, k, distortion
        )[0].reshape(2)
        errors.append(float(np.linalg.norm(projected - point)))
    if max(errors) > 4:
        return None, "reprojection_error"
    return ReconstructedJoint(
        xyz_m=tuple(float(x) for x in xyz), reprojection_error_px=max(errors), ray_angle_deg=angle
    ), "accepted"


def reconstruct(request: ReconstructionRequest) -> ReconstructionResponse:
    views = request.views
    if not request.same_swing_stationary_confirmed or not request.physical_timebase_confirmed:
        raise ServiceError(
            422,
            "capture_confirmation_required",
            "Confirm the same swing, fixed cameras, and original physical playback timing.",
        )
    if request.sync_uncertainty_ms > 10:
        raise ServiceError(
            422,
            "sync_uncertain",
            "Synchronization uncertainty must be at most 10 ms. Use a shared flash or hardware trigger.",
        )
    if (
        views[0].calibration.camera_id == views[1].calibration.camera_id
        or views[0].calibration.world_id != views[1].calibration.world_id
    ):
        raise ServiceError(
            422, "rig_mismatch", "Use distinct cameras calibrated to the same world reference."
        )
    arrays = [camera_arrays(view.calibration) for view in views]
    centers = [-r.T @ t for _, _, r, t in arrays]
    if any(not 0.2 <= center[1] <= 5 for center in centers):
        raise ServiceError(
            422,
            "camera_height_invalid",
            "Check the ground reference: cameras must be 0.2–5 metres above its Y=0 plane.",
        )
    if not 0.2 <= np.linalg.norm(centers[0] - centers[1]) <= 20:
        raise ServiceError(
            422,
            "baseline_invalid",
            "The calibrated camera baseline must be between 0.2 and 20 metres.",
        )
    for view in views:
        camera, video = view.calibration, view.pose.video
        if (
            not camera.scale_and_orientation_verified
            or max(camera.calibration_rms_px, camera.reference_rms_px) > 2
            or (camera.image_width, camera.image_height) != (video.width, video.height)
        ):
            raise ServiceError(
                422,
                "calibration_invalid",
                "Check calibration scale/orientation, matching decoded resolution, and RMS error (at most 2 px).",
            )
        if (
            video.timestamp_source != "decoder_pts"
            or view.sync_anchor_seconds > view.pose.frames[-1].timestamp_seconds
        ):
            raise ServiceError(
                422,
                "timing_invalid",
                "Use decoder timestamps and an in-window synchronization anchor.",
            )
        if len(view.pose.frames) > 1800:
            raise ServiceError(
                422,
                "reconstruction_limit",
                "Select a shorter window with at most 1,800 frames per view.",
            )
    second_times = [
        frame.timestamp_seconds - views[1].sync_anchor_seconds for frame in views[1].pose.frames
    ]
    frames, errors, rejected = [], [], Counter()
    unmatched = accepted = 0
    used = set()
    for first in views[0].pose.frames:
        common = first.timestamp_seconds - views[0].sync_anchor_seconds
        index = bisect_left(second_times, common)
        candidates = [i for i in (index - 1, index) if 0 <= i < len(second_times)]
        index = min(candidates, key=lambda i: abs(second_times[i] - common))
        mismatch = abs(second_times[index] - common) * 1000
        if index in used or mismatch + request.sync_uncertainty_ms > 20:
            unmatched += 1
            continue
        used.add(index)
        second = views[1].pose.frames[index]
        joints = {}
        for name in LANDMARKS:
            points = []
            for frame, view in zip((first, second), views, strict=True):
                joint = frame.landmarks.get(name)
                if (
                    not joint
                    or not joint.observed
                    or joint.interpolated
                    or joint.confidence is None
                    or joint.confidence < 0.6
                    or joint.raw_xy_px is None
                ):
                    break
                point = joint.raw_xy_px
                if (
                    not 0 <= point[0] < view.pose.video.width
                    or not 0 <= point[1] < view.pose.video.height
                ):
                    break
                points.append(point)
            if len(points) != 2:
                rejected["missing_or_unreliable_observation"] += 1
                continue
            joint, reason = triangulate(*points, arrays)
            if joint:
                joints[name] = joint
                errors.append(joint.reprojection_error_px)
                accepted += 1
            else:
                rejected[reason] += 1
        torso = None
        if all(
            name in joints for name in ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
        ):
            vector = (
                sum(
                    (np.asarray(joints[name].xyz_m) for name in ("left_shoulder", "right_shoulder"))
                )
                / 2
                - sum((np.asarray(joints[name].xyz_m) for name in ("left_hip", "right_hip"))) / 2
            )
            if np.linalg.norm(vector) > 0.1:
                torso = float(
                    np.degrees(np.arccos(np.clip(vector[1] / np.linalg.norm(vector), -1, 1)))
                )
        frames.append(
            ReconstructionFrame(
                timestamp_seconds=common,
                matching_error_ms=mismatch,
                joints=joints,
                torso_tilt_deg=torso,
            )
        )
    return ReconstructionResponse(
        swing_id=request.swing_id,
        status="reconstructed" if accepted else "insufficient_data",
        frames=frames,
        accepted_joints=accepted,
        rejected_joints=dict(rejected),
        matched_frames=len(frames),
        unmatched_frames=unmatched,
        median_reprojection_error_px=float(np.median(errors)) if errors else None,
        notices=[
            "Triangulated estimates from raw observed 2D landmarks; low reprojection error does not prove landmark accuracy.",
            "No missing joints are filled or extrapolated. Anatomy labels and shared-world orientation still need review.",
            "3D torso tilt is descriptive; no validated 3D technique diagnosis or clubhead speed is produced.",
            "Timing tolerance, 3-degree ray angle and 4-pixel reprojection gates are engineering safeguards, not an accuracy certification.",
        ],
    )
