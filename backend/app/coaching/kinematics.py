"""Conservative 2D metrics. Estimated wrist return is not measured club impact."""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import find_peaks

from app.coaching.quality import assess_quality, usable_point
from app.coaching.schemas import (
    AnalysisOptions,
    KinematicsReport,
    SeriesPoint,
    SwingEvents,
    VisionDocument,
    VisionFrame,
)

TORSO = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
HANDS_AND_HIPS = ("left_wrist", "right_wrist", *TORSO)


def _points(
    frame: VisionFrame, names: tuple[str, ...], width: int, height: int
) -> np.ndarray | None:
    points = [usable_point(frame, name, width, height) for name in names]
    return None if any(point is None for point in points) else np.asarray(points, dtype=float)


def _spine(frame: VisionFrame, width: int, height: int) -> float:
    points = _points(frame, TORSO, width, height)
    if points is None:
        return np.nan
    vector = points[:2].mean(axis=0) - points[2:].mean(axis=0)
    length = float(np.linalg.norm(vector))
    if length < 1:
        return np.nan
    return math.degrees(math.acos(float(np.clip(-vector[1] / length, -1, 1))))


def _relative_hands(frame: VisionFrame, width: int, height: int) -> np.ndarray:
    points = _points(frame, HANDS_AND_HIPS, width, height)
    if points is None:
        return np.full(2, np.nan)
    hips = points[4:].mean(axis=0)
    shoulders = points[2:4].mean(axis=0)
    scale = float(np.linalg.norm(shoulders - hips))
    return (points[:2].mean(axis=0) - hips) / scale if scale >= 1 else np.full(2, np.nan)


def _estimate_events(times: np.ndarray, hands: np.ndarray) -> SwingEvents | None:
    """First address departure/return cycle; reject incomplete or ambiguous traces.

    Requires a stable initial address. This intentionally fails closed rather than
    assigning a top/impact to any clip containing arbitrary human movement.
    """
    if len(times) < 20 or times[-1] < 0.7:
        return None
    baseline_mask = times <= 0.2
    if baseline_mask.sum() < 3 or not np.isfinite(hands[baseline_mask]).all():
        return None
    address = np.median(hands[baseline_mask], axis=0)
    if np.max(np.linalg.norm(hands[baseline_mask] - address, axis=1)) > 0.08:
        return None
    distance = np.linalg.norm(hands - address, axis=1)
    finite = np.isfinite(distance)
    # Never interpolate missing wrists to fabricate swing events.
    end = int(np.flatnonzero(~finite)[0]) if not finite.all() else len(times)
    if end < 20:
        return None
    distance, trace_times = distance[:end], times[:end]
    peaks, _ = find_peaks(distance, prominence=0.35)
    candidates = []
    for peak in peaks:
        if distance[peak] < 0.5:
            continue
        before = np.flatnonzero((trace_times < trace_times[peak]) & (distance <= 0.1))
        if not len(before):
            continue
        start = int(before[-1])
        after = np.flatnonzero(
            (trace_times >= trace_times[peak] + 0.08)
            & (trace_times <= trace_times[peak] + 1.2)
            & (distance <= 0.15)
        )
        if not len(after):
            continue
        impact = int(after[0])
        back, down = trace_times[peak] - trace_times[start], trace_times[impact] - trace_times[peak]
        if 0.3 <= back <= 3 and 0.08 <= down <= 1.2:
            candidates.append(
                SwingEvents(
                    start_seconds=float(trace_times[start]),
                    top_seconds=float(trace_times[peak]),
                    impact_seconds=float(trace_times[impact]),
                )
            )
    # Multiple departure/return cycles could be a waggle or multiple swings.
    return candidates[0] if len(candidates) == 1 else None


def _number(value: float) -> float | None:
    return round(float(value), 5) if math.isfinite(value) else None


def calculate_kinematics(
    document: VisionDocument | dict,
    options: AnalysisOptions | None = None,
) -> KinematicsReport:
    document = VisionDocument.model_validate(document)
    options = options or AnalysisOptions()
    times = np.asarray([f.timestamp_seconds for f in document.frames])
    width, height = document.video.width, document.video.height
    spine = np.asarray([_spine(frame, width, height) for frame in document.frames])
    hands = np.asarray([_relative_hands(frame, width, height) for frame in document.frames])
    intervals = np.diff(times)
    nominal_dt = 1 / document.video.nominal_fps
    timing_reliable = (
        document.video.timestamp_source == "decoder_pts" or options.confirm_constant_frame_rate
    )
    warnings = ["All measurements are 2D projections and depend on camera position."]
    if not timing_reliable:
        warnings.append("Timing assumes nominal FPS; confirm CFR before applying tempo rules.")
    speed = np.full(len(times), np.nan)
    for i in range(1, len(times)):
        if np.isfinite(hands[i - 1 : i + 1]).all() and intervals[i - 1] <= max(
            0.1, 1.5 * nominal_dt
        ):
            speed[i] = np.linalg.norm(hands[i] - hands[i - 1]) / intervals[i - 1]

    events, source = options.events, "manual" if options.events else None
    if events and events.impact_seconds > times[-1]:
        raise ValueError("Swing markers must fall inside the clip.")
    if events is None and options.estimate_events:
        events = _estimate_events(times, hands)
        source = "estimated" if events else None
    if source == "estimated":
        warnings.append(
            "Swing events use a wrist departure/return heuristic; estimated impact is not club-ball contact."
        )
    if events is None:
        warnings.append("Supply start/top/impact markers to calculate tempo and posture change.")

    back = down = tempo = baseline = impact = delta = loss = None
    coverage = 0.0
    eligible = False
    if events:
        back = events.top_seconds - events.start_seconds
        down = events.impact_seconds - events.top_seconds
        # Reject intervals shorter than two samples; rounded markers otherwise explode ratios.
        if min(back, down) >= 2 * nominal_dt:
            tempo = back / down
        else:
            warnings.append("Swing markers are too close together for a reliable tempo ratio.")
        baseline_mask = (times >= max(0, events.start_seconds - 0.2)) & (
            times <= min(events.top_seconds, events.start_seconds + 0.1)
        )
        baseline_values = spine[baseline_mask]
        if len(baseline_values) >= 3 and np.isfinite(baseline_values).mean() >= 0.8:
            baseline = float(np.nanmedian(baseline_values))
        swing_mask = (times >= events.top_seconds) & (times <= events.impact_seconds)
        swing_times, swing_spine = times[swing_mask], spine[swing_mask]
        if len(swing_spine):
            coverage = float(np.isfinite(swing_spine).mean())
        impact_values = spine[
            (times >= events.impact_seconds - 0.1) & (times <= events.impact_seconds)
        ]
        if len(impact_values) >= 3 and np.isfinite(impact_values).mean() >= 0.8:
            impact = float(np.nanmedian(impact_values))
        if baseline is not None and impact is not None:
            delta = impact - baseline  # Negative means the torso appeared more upright.
        robust_values = []
        for i in range(len(swing_times)):
            window = swing_spine[
                (swing_times >= swing_times[i] - 0.1) & (swing_times <= swing_times[i])
            ]
            if len(window) >= 3 and np.isfinite(window).all():
                robust_values.append(float(np.median(window)))
        valid_times = swing_times[np.isfinite(swing_spine)]
        continuous = len(valid_times) >= 3 and np.all(
            np.diff(valid_times) <= max(0.1, 1.5 * nominal_dt)
        )
        if baseline is not None and robust_values and coverage >= 0.8 and continuous:
            loss = max(0.0, baseline - min(robust_values))
            eligible = options.camera_view == "down_the_line"
        if options.camera_view != "down_the_line":
            warnings.append("Posture fault screening requires a declared down-the-line view.")
        if loss is None:
            warnings.append(
                "Insufficient confident filtered torso landmarks for posture screening."
            )
    quality = assess_quality(
        document,
        options,
        events=events,
        event_source=source,
        timing_reliable=timing_reliable,
        tempo_available=tempo is not None,
        posture_available=loss is not None,
    )
    eligible = quality.posture.eligible
    if not eligible:
        baseline = impact = delta = loss = None
    if not quality.tempo.eligible:
        back = down = tempo = None
    warnings.extend(
        reason
        for reason in [*quality.posture.reasons, *quality.tempo.reasons]
        if reason not in warnings
    )
    series = [
        SeriesPoint(
            timestamp_seconds=float(t),
            spine_tilt_deg=_number(spine[i]),
            spine_delta_deg=_number(spine[i] - baseline) if baseline is not None else None,
            wrist_speed_torso_per_second=_number(speed[i]),
        )
        for i, t in enumerate(times)
    ]
    status = (
        "insufficient_data"
        if not np.isfinite(spine).any() and not np.isfinite(hands).any()
        else "partial"
    )
    if tempo is not None and loss is not None and source == "manual":
        status = "complete"
    return KinematicsReport(
        status=status,
        camera_view=options.camera_view,
        events=events,
        event_source=source,
        timing_reliable=timing_reliable,
        backswing_seconds=_number(back) if back is not None else None,
        downswing_seconds=_number(down) if down is not None else None,
        tempo_ratio=_number(tempo) if tempo is not None else None,
        baseline_spine_tilt_deg=_number(baseline) if baseline is not None else None,
        impact_spine_tilt_deg=_number(impact) if impact is not None else None,
        spine_delta_deg=_number(delta) if delta is not None else None,
        max_posture_loss_deg=_number(loss) if loss is not None else None,
        posture_valid_fraction=round(coverage, 5),
        posture_eligible=eligible,
        quality=quality,
        warnings=warnings,
        series=series,
    )
