import copy

import pytest
from pydantic import ValidationError

from app.coaching.kinematics import calculate_kinematics
from app.coaching.rule_engine import RuleConfig, evaluate_rules
from app.coaching.schemas import AnalysisOptions, SwingEvents, VisionDocument
from coaching_fixtures import MARKERS, pose_document, swing_distance


def options(**changes):
    defaults = {
        "events": SwingEvents(**MARKERS),
        "camera_view": "down_the_line",
        "camera_alignment_confirmed": True,
    }
    defaults.update(changes)
    return AnalysisOptions(**defaults)


def test_known_geometry_and_tempo_are_calculated_from_pixels_and_seconds():
    report = calculate_kinematics(pose_document(), options())
    assert report.tempo_ratio == 3
    assert report.backswing_seconds == 0.9 and report.downswing_seconds == 0.3
    assert report.baseline_spine_tilt_deg == 45
    assert report.impact_spine_tilt_deg == 45
    assert report.spine_delta_deg == 0 and report.max_posture_loss_deg == 0
    assert report.posture_eligible and report.status == "complete"
    assert not evaluate_rules(report).faults


def test_posture_loss_is_flagged_with_evidence_and_a_specific_drill():
    report = calculate_kinematics(
        pose_document(spine_at=lambda t: 25 if 1.25 <= t <= 1.5 else 45), options()
    )
    assert report.spine_delta_deg == -20 and report.max_posture_loss_deg == 20
    rules = evaluate_rules(report)
    assert rules.faults[0].code == "LOSS_OF_POSTURE"
    assert rules.faults[0].evidence["max_posture_loss_deg"] == 20
    assert rules.drills[0].id == "hip_depth_rehearsal"


def test_deeper_spine_tilt_and_standing_up_after_impact_do_not_trigger_posture_loss():
    for angle in (lambda t: 65 if 1.25 <= t <= 1.5 else 45, lambda t: 5 if t > 1.55 else 45):
        report = calculate_kinematics(pose_document(spine_at=angle), options())
        assert report.max_posture_loss_deg == 0
        assert not evaluate_rules(report).faults


def test_single_frame_pose_spike_does_not_become_a_posture_fault():
    report = calculate_kinematics(
        pose_document(spine_at=lambda t: 5 if abs(t - 1.3) < 0.001 else 45), options()
    )
    assert report.max_posture_loss_deg == 0


def test_face_on_view_does_not_enable_posture_fault_screening():
    report = calculate_kinematics(
        pose_document(spine_at=lambda t: 20 if t > 1.2 else 45),
        AnalysisOptions(events=SwingEvents(**MARKERS), camera_view="face_on"),
    )
    assert not report.posture_eligible
    assert not any(f.code == "LOSS_OF_POSTURE" for f in evaluate_rules(report).faults)


def test_occluded_or_unfiltered_points_are_excluded_from_rules():
    for flag, value in (
        ("interpolated", True),
        ("filtered", False),
        ("observed", False),
        ("confidence", 0.2),
    ):
        document = pose_document()
        for frame in document["frames"]:
            frame["landmarks"]["left_hip"][flag] = value
        report = calculate_kinematics(document, options())
        assert report.baseline_spine_tilt_deg is None and report.max_posture_loss_deg is None
        assert not report.posture_eligible


def test_missing_data_remains_unknown_and_is_not_reported_as_a_good_swing():
    document = pose_document()
    for frame in document["frames"]:
        frame["landmarks"] = {}
    report = calculate_kinematics(document)
    assert report.status == "insufficient_data" and report.tempo_ratio is None
    assert all(point.spine_tilt_deg is None for point in report.series)
    assert evaluate_rules(report).notices


def test_estimated_events_are_explicitly_labelled_and_require_a_complete_cycle():
    report = calculate_kinematics(pose_document(hand_at=swing_distance))
    assert report.event_source == "estimated"
    assert report.events is not None and 2.5 < report.tempo_ratio < 4
    assert any("not club-ball contact" in warning for warning in report.warnings)
    assert calculate_kinematics(pose_document()).events is None
    assert calculate_kinematics(pose_document(hand_at=lambda t: t)).events is None
    document = pose_document(hand_at=swing_distance)
    document["frames"][40]["landmarks"]["left_wrist"]["observed"] = False
    assert calculate_kinematics(document).events is None


def test_disabling_estimation_requires_manual_markers():
    report = calculate_kinematics(
        pose_document(hand_at=swing_distance), AnalysisOptions(estimate_events=False)
    )
    assert report.events is None and report.tempo_ratio is None


def test_tempo_reference_is_configurable_and_assumed_timing_requires_confirmation():
    document = pose_document(timestamp_source="nominal_fps_fallback")
    report = calculate_kinematics(document, options())
    assert report.tempo_ratio is None and not report.timing_reliable
    assert not evaluate_rules(report, RuleConfig(tempo_min=4, tempo_max=5)).faults
    report = calculate_kinematics(document, options(confirm_constant_frame_rate=True))
    assert (
        evaluate_rules(report, RuleConfig(tempo_min=4, tempo_max=5)).faults[0].code
        == "TEMPO_OUTSIDE_REFERENCE"
    )


def test_exact_posture_threshold_is_not_flagged():
    report = calculate_kinematics(
        pose_document(spine_at=lambda t: 35 if 1.25 <= t <= 1.5 else 45), options()
    )
    assert report.max_posture_loss_deg == 10
    assert not evaluate_rules(report).faults


def test_markers_and_vision_payloads_reject_invalid_values():
    with pytest.raises(ValidationError):
        SwingEvents(start_seconds=1, top_seconds=0.5, impact_seconds=2)
    with pytest.raises(ValueError, match="inside"):
        calculate_kinematics(
            pose_document(),
            AnalysisOptions(events=SwingEvents(start_seconds=0, top_seconds=1, impact_seconds=3)),
        )
    for mutate in (
        lambda d: d["frames"][1].update(timestamp_seconds=0),
        lambda d: d["frames"][1].update(frame_index=9),
        lambda d: d["video"].update(frame_count=3),
        lambda d: d["frames"][0]["landmarks"]["left_hip"].update(xy_px=[float("nan"), 3]),
        lambda d: d["frames"][0]["landmarks"]["left_hip"].update(observed="false"),
    ):
        document = copy.deepcopy(pose_document())
        mutate(document)
        with pytest.raises(ValidationError):
            VisionDocument.model_validate(document)
    with pytest.raises(ValueError):
        RuleConfig(tempo_min=5, tempo_max=2)
