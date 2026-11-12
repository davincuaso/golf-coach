"""View-aware measurement gates. Pose geometry is a hint, not camera calibration.

Thresholds are conservative engineering guards, not validated probabilities of
golf accuracy. Each metric has its own eligibility; manual timing can remain
usable when occluded joints prevent posture screening.
"""

from __future__ import annotations

import math
import numpy as np

from app.coaching.schemas import (
    AnalysisOptions,
    AnalysisQuality,
    CameraAssessment,
    MeasurementGate,
    QualityIssue,
    SwingEvents,
    TrackingQuality,
    VisionDocument,
    VisionFrame,
)

TORSO = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
HANDS = (*TORSO, "left_wrist", "right_wrist")
BODY = (*TORSO, "left_ankle", "right_ankle")


def usable_point(frame: VisionFrame, name: str, width: int, height: int) -> np.ndarray | None:
    joint = frame.landmarks.get(name)
    if (
        joint is None
        or joint.xy_px is None
        or not joint.observed
        or joint.interpolated
        or not joint.filtered
        or joint.confidence is None
        or joint.confidence < 0.5
    ):
        return None
    point = np.asarray(joint.xy_px, dtype=float)
    return (
        point
        if np.isfinite(point).all() and np.all(point >= 0) and np.all(point < [width, height])
        else None
    )


def largest_gap(times: np.ndarray, valid: np.ndarray, start: float, end: float, dt: float) -> float:
    present = times[valid]
    if not len(present):
        return round(max(0.0, end - start), 5)
    inner = np.diff(present) - dt
    return round(
        max(
            0.0,
            float(inner.max()) if len(inner) else 0.0,
            float(present[0] - start),
            float(end - present[-1]),
        ),
        5,
    )


def _camera(
    document: VisionDocument, options: AnalysisOptions, events: SwingEvents | None
) -> CameraAssessment:
    start = max(0, events.start_seconds - 0.1) if events else 0
    end = min(events.top_seconds, events.start_seconds + 0.1) if events else 0.3
    ratios = []
    for frame in document.frames:
        if not start <= frame.timestamp_seconds <= end:
            continue
        points = [
            usable_point(frame, name, document.video.width, document.video.height) for name in TORSO
        ]
        if any(point is None for point in points):
            continue
        shoulder_left, shoulder_right, hip_left, hip_right = points
        scale = np.linalg.norm((shoulder_left + shoulder_right - hip_left - hip_right) / 2)
        if scale >= 1:
            ratios.append(
                float(
                    (abs(shoulder_left[0] - shoulder_right[0]) + abs(hip_left[0] - hip_right[0]))
                    / (2 * scale)
                )
            )
    ratio = float(np.median(ratios)) if len(ratios) >= 3 else None
    hint = (
        "unknown"
        if ratio is None
        else "narrow"
        if ratio < 0.5
        else "broad"
        if ratio > 0.85
        else "mixed"
    )
    view = options.camera_view
    if view != "down_the_line":
        state = "needs_confirmation" if view == "unknown" else "unsupported_view"
    elif hint == "broad":
        state = "projection_conflict"
    else:
        state = "user_confirmed" if options.camera_alignment_confirmed else "needs_confirmation"
    return CameraAssessment(
        declared_view=view,
        alignment_confirmed=options.camera_alignment_confirmed,
        assessment=state,
        projection_hint=hint,
        projected_width_torso_ratio=round(ratio, 5)
        if ratio is not None and math.isfinite(ratio)
        else None,
        note="Body projection is a heuristic check around address; it cannot distinguish front from rear or establish camera azimuth, height, roll, or 3D alignment.",
    )


def assess_quality(
    document: VisionDocument,
    options: AnalysisOptions,
    *,
    events: SwingEvents | None,
    event_source: str | None,
    timing_reliable: bool,
    tempo_available: bool,
    posture_available: bool,
) -> AnalysisQuality:
    all_times = np.array([frame.timestamp_seconds for frame in document.frames])
    start, end = (
        (events.start_seconds, events.impact_seconds) if events else (0.0, float(all_times[-1]))
    )
    indices = np.flatnonzero((all_times >= start) & (all_times <= end))
    frames = [document.frames[int(i)] for i in indices]
    times = all_times[indices]
    width, height = document.video.width, document.video.height
    names = tuple(dict.fromkeys(name for frame in document.frames for name in frame.landmarks))
    points = [
        {name: usable_point(frame, name, width, height) for name in names} for frame in frames
    ]
    group = lambda keys: np.array(
        [all(row.get(name) is not None for name in keys) for row in points], dtype=bool
    )
    torso, wrists, body = group(TORSO), group(HANDS), group(BODY)
    fraction = lambda values: round(float(np.mean(values)), 5) if len(values) else 0.0
    detected, border = [], []
    interpolated = total = jumps = 0
    previous = None
    for frame, row, time in zip(frames, points, times, strict=True):
        box = frame.person_bbox_xyxy_px
        has_box = box is not None and box[2] > box[0] and box[3] > box[1]
        detected.append(has_box or any(point is not None for point in row.values()))
        touches = has_box and (
            box[0] <= 0.01 * width
            or box[1] <= 0.01 * height
            or box[2] >= 0.99 * width
            or box[3] >= 0.99 * height
        )
        border.append(
            bool(
                touches
                or any(
                    point is not None
                    and (
                        np.any(point < [0.01 * width, 0.01 * height])
                        or np.any(point > [0.99 * width, 0.99 * height])
                    )
                    for name, point in row.items()
                    if name in TORSO
                )
            )
        )
        total += len(frame.landmarks)
        interpolated += sum(joint.interpolated for joint in frame.landmarks.values())
        if all(row.get(name) is not None for name in TORSO):
            # Raw torso centers expose jumps that smoothing might hide. Wrists
            # are excluded because a fast downswing can legitimately move far.
            raw = [
                np.asarray(frame.landmarks[name].raw_xy_px or frame.landmarks[name].xy_px)
                for name in TORSO
            ]
            center = np.mean(raw, axis=0)
            scale = max(1.0, float(np.linalg.norm((raw[0] + raw[1] - raw[2] - raw[3]) / 2)) * 2.5)
            if previous is not None:
                old_time, old_center, old_scale = previous
                dt = float(time - old_time)
                if dt <= 0.1 and np.linalg.norm(center - old_center) / max(scale, old_scale) > max(
                    0.15, 4 * dt
                ):
                    jumps += 1
            previous = (time, center, scale)
        else:
            previous = None
    dt = (
        float(np.median(np.diff(all_times)))
        if len(all_times) > 1
        else 1 / document.video.nominal_fps
    )
    tracking = TrackingQuality(
        evaluated_frames=len(frames),
        detected_fraction=fraction(detected),
        torso_valid_fraction=fraction(torso),
        wrist_pair_valid_fraction=fraction(wrists),
        full_body_valid_fraction=fraction(body),
        border_contact_fraction=fraction(border),
        interpolated_fraction=round(interpolated / total, 5) if total else 0.0,
        largest_torso_gap_seconds=largest_gap(times, torso, start, end, dt),
        largest_wrist_gap_seconds=largest_gap(times, wrists, start, end, dt),
        torso_jump_count=jumps,
        keypoint_coverage={
            name: fraction([row.get(name) is not None for row in points]) for name in names
        },
    )
    camera = _camera(document, options, events)
    posture_reasons, tempo_reasons = [], []
    if options.camera_view != "down_the_line":
        posture_reasons.append(
            "Posture change requires a down-the-line view; this camera perspective supports descriptive 2D playback only."
        )
    elif not options.camera_alignment_confirmed:
        posture_reasons.append(
            "Confirm that the camera is level, stationary, and aligned down the target line before posture screening."
        )
    if camera.assessment == "projection_conflict":
        posture_reasons.append(
            "The broad body projection conflicts with a down-the-line declaration. Recheck the camera perspective before posture screening."
        )
    if not posture_available:
        posture_reasons.append(
            "Usable address/downswing/impact torso measurements are required for posture change."
        )
    if tracking.torso_valid_fraction < 0.8 or tracking.largest_torso_gap_seconds > max(
        0.1, 1.5 * dt
    ):
        posture_reasons.append(
            "Torso tracking has insufficient coverage or a long gap during the evaluated swing."
        )
    if jumps:
        posture_reasons.append(
            "Abrupt torso-position jumps suggest tracking or camera movement; posture screening is withheld."
        )
    if not events or not tempo_available:
        tempo_reasons.append(
            "Set valid start/top/impact markers or obtain a complete, trackable swing cycle."
        )
    if not timing_reliable:
        tempo_reasons.append(
            "Reliable decoded timestamps or explicit constant-frame-rate confirmation are required for tempo."
        )
    if event_source == "estimated" and (
        tracking.wrist_pair_valid_fraction < 0.9
        or tracking.largest_wrist_gap_seconds > max(0.1, 1.5 * dt)
        or jumps
    ):
        tempo_reasons.append(
            "Automatically estimated swing markers need continuous wrist/torso tracking without jumps; use manual markers instead."
        )
    issues = []
    if tracking.detected_fraction == 0:
        issues.append(
            QualityIssue(
                code="SUBJECT_NOT_FOUND",
                severity="blocking",
                message="No selected golfer could be tracked. Select a point inside your torso in the first frame, or crop out other people and try again.",
            )
        )
    if options.camera_view == "unknown":
        issues.append(
            QualityIssue(
                code="VIEW_UNKNOWN",
                severity="warning",
                message="Choose the camera perspective; body keypoints alone cannot reliably identify every filming angle.",
            )
        )
    if camera.assessment == "projection_conflict":
        issues.append(
            QualityIssue(
                code="VIEW_CONFLICT",
                severity="blocking",
                message=posture_reasons[-1]
                if len(posture_reasons) == 1
                else "Check the camera view: the body projection is broad while down-the-line was selected.",
            )
        )
    if tracking.torso_valid_fraction < 0.8:
        issues.append(
            QualityIssue(
                code="TORSO_OCCLUSION",
                severity="warning",
                message="Shoulder/hip tracking is incomplete. Improve lighting, keep the torso visible, and avoid occlusion.",
            )
        )
    if tracking.wrist_pair_valid_fraction < 0.9:
        issues.append(
            QualityIssue(
                code="WRIST_OCCLUSION",
                severity="warning",
                message="Wrist tracking is incomplete. Manual swing markers may recover tempo without inventing hidden hand positions.",
            )
        )
    if tracking.border_contact_fraction > 0.05 or tracking.full_body_valid_fraction < 0.8:
        issues.append(
            QualityIssue(
                code="FRAMING",
                severity="warning",
                message="Some body anchors are missing or the golfer touches the frame edge. Keep head, feet, and the full swing inside a wider frame.",
            )
        )
    if jumps:
        issues.append(
            QualityIssue(
                code="TRACKING_JUMP",
                severity="blocking",
                message="Abrupt torso movement was detected between adjacent frames. Verify the selected golfer and use a stationary camera.",
            )
        )
    if document.video.nominal_fps < 60:
        issues.append(
            QualityIssue(
                code="LIMITED_FRAME_RATE",
                severity="info",
                message="This clip is below 60 fps. Body timing may be usable, but fast impact/club/ball motion needs higher-frame-rate footage and adequate light.",
            )
        )
    if not events:
        issues.append(
            QualityIssue(
                code="MARKERS_REQUIRED",
                severity="warning",
                message="No complete swing cycle was identified. Add start/top/impact markers to evaluate the swing rather than setup or follow-through.",
            )
        )
    status = (
        "insufficient"
        if tracking.torso_valid_fraction == 0 and tracking.wrist_pair_valid_fraction == 0
        else "limited"
        if posture_reasons or tempo_reasons or any(issue.severity != "info" for issue in issues)
        else "usable"
    )
    return AnalysisQuality(
        status=status,
        window_start_seconds=round(start, 5),
        window_end_seconds=round(end, 5),
        window_source="swing" if events else "whole_clip",
        camera=camera,
        tracking=tracking,
        tempo=MeasurementGate(eligible=not tempo_reasons, reasons=tempo_reasons),
        posture=MeasurementGate(eligible=not posture_reasons, reasons=posture_reasons),
        issues=issues,
    )
