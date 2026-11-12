import pytest

from app.coaching.kinematics import calculate_kinematics
from app.coaching.rule_engine import RuleConfig, evaluate_rules
from app.coaching.schemas import AnalysisOptions, SwingEvents
from coaching_fixtures import MARKERS, pose_document, swing_distance


def options(**changes):
    values = dict(
        camera_view="down_the_line", camera_alignment_confirmed=True, events=SwingEvents(**MARKERS)
    )
    values.update(changes)
    return AnalysisOptions(**values)


@pytest.mark.parametrize("view", ["face_on", "oblique", "rear", "overhead", "unknown"])
def test_other_views_keep_manual_tempo_but_withhold_posture_values_and_faults(view):
    report = calculate_kinematics(
        pose_document(spine_at=lambda t: 20 if t >= 1.25 else 45), options(camera_view=view)
    )
    assert report.tempo_ratio == 3 and report.quality.tempo.eligible
    assert report.spine_delta_deg is None and report.max_posture_loss_deg is None
    assert report.baseline_spine_tilt_deg is None and report.impact_spine_tilt_deg is None
    assert all(point.spine_delta_deg is None for point in report.series)
    assert not report.posture_eligible and not report.quality.posture.eligible
    assert not any(fault.code == "LOSS_OF_POSTURE" for fault in evaluate_rules(report).faults)


def test_selecting_down_the_line_does_not_silently_confirm_alignment():
    report = calculate_kinematics(pose_document(), options(camera_alignment_confirmed=False))
    assert report.quality.camera.assessment == "needs_confirmation"
    assert not report.posture_eligible and report.spine_delta_deg is None
    assert any("Confirm" in reason for reason in report.quality.posture.reasons)


def test_projection_conflict_vetoes_a_misdeclared_down_the_line_view():
    source = pose_document(spine_at=lambda t: 20 if t >= 1.25 else 45)
    for frame in source["frames"]:
        for name, shift in (
            ("left_shoulder", -130),
            ("right_shoulder", 130),
            ("left_hip", -90),
            ("right_hip", 90),
        ):
            frame["landmarks"][name]["xy_px"][0] += shift
    report = calculate_kinematics(source, options())
    assert report.quality.camera.projection_hint == "broad"
    assert report.quality.camera.assessment == "projection_conflict"
    assert not report.posture_eligible and report.max_posture_loss_deg is None
    assert any(issue.code == "VIEW_CONFLICT" for issue in report.quality.issues)


def test_missing_wrists_do_not_invalidate_manual_tempo_or_fabricate_hand_motion():
    source = pose_document()
    for frame in source["frames"]:
        frame["landmarks"].pop("left_wrist")
        frame["landmarks"].pop("right_wrist")
    report = calculate_kinematics(source, options())
    assert report.tempo_ratio == 3 and report.quality.tempo.eligible
    assert report.quality.tracking.wrist_pair_valid_fraction == 0
    assert all(point.wrist_speed_torso_per_second is None for point in report.series)


def test_torso_jump_is_reported_and_blocks_posture_even_if_filtered_values_exist():
    source = pose_document()
    for joint in source["frames"][48]["landmarks"].values():
        joint["xy_px"][0] += 400
    report = calculate_kinematics(source, options())
    assert report.quality.tracking.torso_jump_count >= 1
    assert any(issue.code == "TRACKING_JUMP" for issue in report.quality.issues)
    assert report.max_posture_loss_deg is None and not report.posture_eligible
    assert report.quality.tempo.eligible  # Explicit manual timing is a separate measurement.


def test_long_torso_gaps_are_not_hidden_by_smoothed_coordinates():
    source = pose_document()
    for frame in source["frames"][45:70]:
        frame["landmarks"]["left_shoulder"]["interpolated"] = True
    report = calculate_kinematics(source, options())
    assert report.quality.tracking.largest_torso_gap_seconds > 0.3
    assert report.quality.tracking.interpolated_fraction > 0
    assert not report.posture_eligible


def test_quality_is_scoped_to_the_swing_not_the_walk_back_to_camera():
    source = pose_document()
    for frame in source["frames"][95:]:
        frame["landmarks"] = {}
    report = calculate_kinematics(source, options())
    assert report.quality.window_source == "swing"
    assert report.quality.window_end_seconds == 1.5
    assert report.quality.tracking.torso_valid_fraction == 1
    assert report.posture_eligible


def test_out_of_image_coordinates_never_become_usable_pose_measurements():
    source = pose_document()
    for frame in source["frames"]:
        frame["landmarks"]["left_shoulder"]["xy_px"] = [-100, 300]
    report = calculate_kinematics(source, options())
    assert report.quality.tracking.torso_valid_fraction == 0
    assert all(point.spine_tilt_deg is None for point in report.series)
    assert not report.posture_eligible


def test_low_frame_rate_is_an_information_limit_not_an_invented_club_speed():
    source = pose_document()
    source["video"]["nominal_fps"] = 30
    report = calculate_kinematics(source, options())
    assert any(issue.code == "LIMITED_FRAME_RATE" for issue in report.quality.issues)
    assert report.tempo_ratio == 3


def test_border_contact_is_a_specific_framing_warning():
    source = pose_document()
    for frame in source["frames"]:
        frame["person_bbox_xyxy_px"] = [0, 100, 800, 1000]
    report = calculate_kinematics(source, options())
    assert report.quality.tracking.border_contact_fraction == 1
    assert any(issue.code == "FRAMING" for issue in report.quality.issues)


def test_quality_model_rejects_nonboolean_alignment_claims():
    with pytest.raises(ValueError):
        options(camera_alignment_confirmed="yes")


def test_missing_subject_requests_selection_instead_of_showing_good_technique():
    source = pose_document()
    for frame in source["frames"]:
        frame["landmarks"] = {}
    report = calculate_kinematics(source)
    assert report.quality.status == "insufficient"
    assert any(issue.code == "SUBJECT_NOT_FOUND" for issue in report.quality.issues)
    assert not report.posture_eligible and report.tempo_ratio is None


def test_estimated_markers_are_provisional_and_do_not_generate_actionable_faults():
    report = calculate_kinematics(
        pose_document(hand_at=swing_distance),
        AnalysisOptions(camera_view="down_the_line", camera_alignment_confirmed=True),
    )
    assert report.event_source == "estimated" and report.tempo_ratio is not None
    rules = evaluate_rules(report, RuleConfig(tempo_min=10, tempo_max=11))
    assert not rules.faults
    assert any("manual markers" in notice for notice in rules.notices)
