import time

from fastapi.testclient import TestClient
import pytest

from app.coaching.kinematics import calculate_kinematics
from app.coaching.rule_engine import evaluate_rules
from app.coaching.schemas import AnalysisOptions, SwingEvents
from app.config import Settings
from app.errors import ServiceError
from app.main import create_app
from app.services.sessions import (
    SessionClipReference,
    SessionRequest,
    sign_analysis,
    summarize_session,
    verify_analysis,
)
from coaching_fixtures import MARKERS, pose_document, swing_distance

SECRET = "session-test-backend-token-long-enough"


def token(identifier, *, events=MARKERS, loss=20, estimated=False):
    metrics = calculate_kinematics(
        pose_document(
            spine_at=lambda t: 45 - loss if t > 1.25 else 45,
            hand_at=swing_distance if estimated else None,
        ),
        AnalysisOptions(
            camera_view="down_the_line",
            camera_alignment_confirmed=True,
            events=None if estimated else SwingEvents(**events),
        ),
    )
    return sign_analysis(identifier, metrics, evaluate_rules(metrics), SECRET)


def reference(identifier, swing, **kwargs):
    return SessionClipReference(
        clip_id=identifier, swing_id=swing, summary_token=token(identifier, **kwargs)
    )


def test_linked_views_contribute_once_and_separate_swings_remain_distinct():
    request = SessionRequest(
        clips=[
            reference("view1", "Swing A"),
            reference("view2", "Swing A"),
            reference("view3", "Swing B"),
        ],
        attempted_clips=3,
    )
    report = summarize_session(request, SECRET)
    assert report.analyzed_clips == 3 and report.unique_swings == 2
    assert report.tempo.swings == report.posture_loss.swings == 2
    assert report.tempo.median == 3
    assert report.patterns[0].swing_count == 2
    assert "SESSION_JSON" in report.prompt_payload
    assert "xy_px" not in report.prompt_payload and SECRET not in report.prompt_payload


def test_conflicting_reviewed_views_are_withheld_instead_of_averaged():
    different = {"start_seconds": 0.3, "top_seconds": 1.3, "impact_seconds": 1.5}
    report = summarize_session(
        SessionRequest(
            clips=[reference("one", "A", loss=20), reference("two", "A", events=different, loss=0)],
            attempted_clips=2,
        ),
        SECRET,
    )
    assert report.swings[0].tempo_ratio is None and report.swings[0].max_posture_loss_deg is None
    assert len(report.swings[0].conflicts) == 2
    assert not report.patterns


def test_provisional_and_partial_evidence_remains_explicit():
    report = summarize_session(
        SessionRequest(clips=[reference("provisional", "A", estimated=True)], attempted_clips=3),
        SECRET,
    )
    assert report.status == "partial" and report.tempo.median is None
    assert report.posture_loss.median is None and not report.patterns
    assert any("partial" in notice.lower() for notice in report.notices)


def test_modified_expired_or_foreign_reports_are_rejected(monkeypatch):
    good = token("one")
    for bad in (good + "x", "invalid", good.replace(".", ".bad", 1)):
        with pytest.raises(ServiceError):
            verify_analysis(bad, SECRET)
    with pytest.raises(ServiceError):
        verify_analysis(good, "different-server-secret")
    with monkeypatch.context() as context:
        context.setattr(time, "time", lambda: 1)
        expired = token("old")
    with pytest.raises(ServiceError):
        verify_analysis(expired, SECRET)


def test_duplicate_reports_cannot_inflate_session_counts():
    value = token("same-analysis")
    request = SessionRequest(
        clips=[
            SessionClipReference(clip_id=clip, swing_id=clip, summary_token=value)
            for clip in ("one", "two")
        ],
        attempted_clips=2,
    )
    with pytest.raises(ServiceError, match="counted twice"):
        summarize_session(request, SECRET)


def test_session_endpoint_auth_validation_and_compact_response():
    with TestClient(create_app(Settings(api_token=SECRET))) as client:
        payload = SessionRequest(clips=[reference("one", "A")], attempted_clips=1).model_dump(
            mode="json"
        )
        assert client.post("/api/v1/sessions", json=payload).status_code == 401
        response = client.post(
            "/api/v1/sessions", headers={"Authorization": f"Bearer {SECRET}"}, json=payload
        )
        assert response.status_code == 200 and response.json()["unique_swings"] == 1
        assert response.headers["Cache-Control"] == "no-store"
        assert (
            client.post(
                "/api/v1/sessions",
                headers={"Authorization": f"Bearer {SECRET}"},
                content=b"x" * 1048577,
            ).status_code
            == 413
        )
