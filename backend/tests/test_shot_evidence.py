import json

import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.evidence.launch_monitor import ShotImportRequest, import_shots
from app.errors import ServiceError
from app.main import create_app
from app.evidence.tokens import sign_evidence, verify_evidence


def request(row=None, **changes):
    row = row or dict(
        shot_id="one",
        swing_id="Swing A",
        ball_speed=150,
        ball_speed_unit="mph",
        ball_speed_method="measured",
        carry=160,
        carry_unit="yd",
        carry_method="device_calculated",
        offline=10,
        offline_unit="yd",
        offline_method="measured",
        launch_direction=1,
        launch_direction_unit="deg",
        launch_direction_method="measured",
        spin_axis=12,
        spin_axis_unit="deg",
        spin_axis_method="measured",
    )
    data = dict(
        format="json",
        content=json.dumps([row]),
        device="Synthetic monitor fixture",
        positive_direction="right",
        positive_spin_axis_curve="right",
        intent=dict(carry_min_m=140, carry_max_m=160, desired_shape="fade"),
    )
    data.update(changes)
    return ShotImportRequest.model_validate(data)


def test_units_provenance_intent_and_handedness_are_preserved():
    report = import_shots(request())
    shot = report.shots[0]
    assert shot.metrics["ball_speed"].value == pytest.approx(67.056)
    assert shot.metrics["carry"].value == pytest.approx(146.304)
    assert shot.metrics["carry"].method == "device_calculated"
    assert all(check.status == "within_intent" for check in shot.checks)
    left = import_shots(request(intent=dict(desired_shape="fade", handedness="left")))
    assert left.shots[0].checks[-1].status == "outside_intent"
    inverted = import_shots(request(positive_direction="left", positive_spin_axis_curve="left"))
    assert (
        inverted.shots[0].metrics["offline"].value < 0
        and inverted.shots[0].metrics["spin_axis"].value < 0
    )


def test_unset_target_missing_fields_and_unknown_provenance_are_unavailable():
    row = dict(shot_id="a", swing_id="A", carry=120, carry_unit="m", carry_method="unknown")
    shot = import_shots(request(row, intent={})).shots[0]
    assert all(check.status == "unavailable" for check in shot.checks)
    assert len(shot.metrics) == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"ball_speed_unit": "knots"},
        {"ball_speed": float("nan")},
        {"ball_speed": True},
        {"ball_speed_method": {}},
        {"recorded_at": "2026-11-12T12:00:00"},
        {"unknown_column": 2},
        {"ball_speed": 99999},
    ],
)
def test_malformed_or_ambiguous_imports_are_rejected(patch):
    row = dict(
        shot_id="a",
        swing_id="A",
        ball_speed=120,
        ball_speed_unit="mph",
        ball_speed_method="measured",
        **{},
    )
    row.update(patch)
    with pytest.raises(ServiceError):
        import_shots(request(row))


def test_csv_signs_receipt_without_provider_api_and_body_is_bounded():
    settings = Settings(api_token="shot-import-test-token-at-least-24")
    with TestClient(create_app(settings)) as client:
        payload = request(
            format="csv",
            content="shot_id,swing_id,carry,carry_unit,carry_method\na,A,150,m,manual\n",
        ).model_dump(mode="json")
        assert client.post("/api/v1/shot-imports", json=payload).status_code == 401
        headers = {"Authorization": "Bearer " + settings.api_token.get_secret_value()}
        response = client.post("/api/v1/shot-imports", headers=headers, json=payload)
        assert response.status_code == 200 and response.json()["evidence_token"]
        assert response.headers["Cache-Control"] == "no-store"
        assert (
            client.post("/api/v1/shot-imports", headers=headers, content=b"x" * 1048577).status_code
            == 413
        )
        payload["content"] = (
            "shot_id,swing_id,carry,carry_unit,carry_method\na,A,150,m,manual\nb,A,150,m,manual\n"
        )
        assert client.post("/api/v1/shot-imports", headers=headers, json=payload).status_code == 422


def test_evidence_receipts_reject_changes_and_expiry(monkeypatch):
    secret = "evidence-test-secret"
    token = sign_evidence("monitor", ["A"], [], {"value": 1}, secret)
    assert verify_evidence(token, secret)["evidence"] == {"value": 1}
    with pytest.raises(ServiceError):
        verify_evidence(token + "x", secret)
    with pytest.raises(ServiceError):
        verify_evidence(token, "another-secret")
    import time

    future = time.time() + 86401
    monkeypatch.setattr(time, "time", lambda: future)
    with pytest.raises(ServiceError):
        verify_evidence(token, secret)
