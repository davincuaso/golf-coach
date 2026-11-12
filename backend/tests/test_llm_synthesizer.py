"""Local prompt contracts and evidence fidelity; no AI provider SDK is imported."""

import json
import socket

import pytest

from app.coaching.kinematics import calculate_kinematics
from app.coaching.llm_synthesizer import generate_coaching_prompt
from app.coaching.rule_engine import evaluate_rules
from app.coaching.schemas import AnalysisOptions, SeriesPoint, SwingEvents
from coaching_fixtures import MARKERS, pose_document


def evidence():
    metrics = calculate_kinematics(
        pose_document(spine_at=lambda t: 20 if t >= 1.25 else 45),
        AnalysisOptions(
            events=SwingEvents(**MARKERS),
            camera_view="down_the_line",
            camera_alignment_confirmed=True,
        ),
    )
    return metrics, evaluate_rules(metrics)


def data(prompt):
    return json.loads(prompt.split("\nKINEMATIC_JSON\n", 1)[1].rsplit("\nEND_KINEMATIC_JSON", 1)[0])


def test_local_prompt_preserves_metrics_evidence_and_drills_without_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Local prompt generation must never open a network connection")

    monkeypatch.setattr(socket, "socket", forbidden)
    metrics, rules = evidence()
    prompt = generate_coaching_prompt(metrics, rules)
    payload = data(prompt)
    assert payload["kinematics"] == metrics.model_dump(mode="json", exclude={"series"})
    assert payload["coaching"] == rules.model_dump(mode="json")
    assert payload["coaching"]["faults"][0]["code"] == "LOSS_OF_POSTURE"
    assert "master golf professional" in prompt
    assert "tentative hypothesis" in prompt
    assert "NOT physical clubhead speed" in prompt
    assert "xy_px" not in prompt
    assert generate_coaching_prompt(metrics, rules) == prompt


def test_short_trace_retains_every_raw_value_and_null():
    metrics, rules = evidence()
    metrics.series[0].spine_tilt_deg = None
    metrics.series[1].spine_tilt_deg = 43.1234567890123
    trace = data(generate_coaching_prompt(metrics, rules))["kinematic_trace"]
    assert trace["sampling"] == "all rows"
    assert trace["source_rows"] == trace["included_rows"] == len(metrics.series)
    assert trace["rows"][0][1] is None
    assert trace["rows"][1][1] == 43.1234567890123
    assert [row[0] for row in trace["rows"]] == [
        point.timestamp_seconds for point in metrics.series
    ]


def test_long_trace_is_bounded_disclosed_and_retains_phase_neighbors():
    metrics, rules = evidence()
    metrics.series = [
        SeriesPoint(
            timestamp_seconds=i / 400,
            spine_tilt_deg=40.0,
            spine_delta_deg=None,
            wrist_speed_torso_per_second=None,
        )
        for i in range(12000)
    ]
    prompt = generate_coaching_prompt(metrics, rules)
    payload = data(prompt)
    trace = payload["kinematic_trace"]
    assert trace["source_rows"] == len(metrics.series) == 12000
    assert 121 <= trace["included_rows"] <= 127
    assert "sampling" in trace and trace["sampling"] != "all rows"
    assert trace["rows"][0][0] == 0 and trace["rows"][-1][0] == 11999 / 400
    assert {0.3, 1.2, 1.5} <= {row[0] for row in trace["rows"]}
    assert payload["kinematics"]["tempo_ratio"] == metrics.tempo_ratio
    assert len(prompt) < 25000


def test_no_faults_or_insufficient_data_still_produce_a_useful_prompt():
    metrics, _ = evidence()
    metrics = metrics.model_copy(
        update={
            "status": "insufficient_data",
            "events": None,
            "tempo_ratio": None,
            "posture_eligible": False,
            "max_posture_loss_deg": None,
            "warnings": ["Missing posture data"],
            "series": [],
        }
    )
    prompt = generate_coaching_prompt(metrics, evaluate_rules(metrics))
    payload = data(prompt)
    assert payload["coaching"]["faults"] == []
    assert payload["kinematics"]["tempo_ratio"] is None
    assert payload["kinematics"]["warnings"] == ["Missing posture data"]
    assert payload["kinematic_trace"]["rows"] == []
    assert "do not invent a fault" in prompt and "filming/measurement check" in prompt


def test_invalid_nonfinite_measurements_are_never_serialized_as_json():
    metrics, rules = evidence()
    with pytest.raises(ValueError):
        generate_coaching_prompt(metrics.model_copy(update={"tempo_ratio": float("nan")}), rules)
