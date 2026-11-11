import asyncio
import json
from types import SimpleNamespace

import httpx2
from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from pydantic import SecretStr
import pytest

from app.coaching.kinematics import calculate_kinematics
from app.coaching.llm_synthesizer import synthesize_coaching
from app.coaching.rule_engine import evaluate_rules
from app.coaching.schemas import AnalysisOptions, CoachingNarrative, SwingEvents
from coaching_fixtures import MARKERS, pose_document


def evidence():
    metrics = calculate_kinematics(
        pose_document(spine_at=lambda t: 20 if t >= 1.25 else 45),
        AnalysisOptions(events=SwingEvents(**MARKERS), camera_view="down_the_line"),
    )
    return metrics, evaluate_rules(metrics)


def narrative(**updates):
    return CoachingNarrative(
        **{
            "summary": "Your torso appears more upright in the downswing.",
            "possible_root_cause": "Reduced hip depth is one possible explanation, but the camera cannot establish the cause.",
            "priorities": [
                {
                    "fault_code": "LOSS_OF_POSTURE",
                    "explanation": "Review a down-the-line rehearsal.",
                }
            ],
            "recommended_drill_ids": ["hip_depth_rehearsal"],
            "practice_plan": "Use five slow hip-depth rehearsals, then record half-speed swings.",
            **updates,
        }
    )


class FakeProvider:
    def __init__(self, records, *, value=None, error=None, status="completed", delay=0):
        self.records, self.value, self.error = records, value, error
        self.status, self.delay = status, delay

    def __call__(self, **kwargs):
        provider = self

        class Client:
            async def __aenter__(self):
                provider.records.append(kwargs)
                self.responses = self
                return self

            async def __aexit__(self, *args):
                await kwargs["http_client"].aclose()

            async def parse(self, **params):
                provider.records[-1]["request"] = params
                await asyncio.sleep(provider.delay)
                if provider.error:
                    raise provider.error
                return SimpleNamespace(
                    status=provider.status, output_parsed=provider.value or narrative()
                )

        return Client()


def test_disabled_missing_key_and_empty_rules_never_create_a_client():
    metrics, rules = evidence()
    records = []
    factory = FakeProvider(records)
    for key, enabled, expected in (
        (SecretStr("sk-test"), False, "disabled"),
        (None, True, "unavailable"),
    ):
        assert (
            asyncio.run(
                synthesize_coaching(
                    metrics, rules, api_key=key, enabled=enabled, client_factory=factory
                )
            ).status
            == expected
        )
    rules.faults = []
    assert (
        asyncio.run(
            synthesize_coaching(
                metrics, rules, api_key=SecretStr("sk-test"), enabled=True, client_factory=factory
            )
        ).status
        == "skipped"
    )
    assert not records


def test_simultaneous_keys_are_isolated_and_payload_contains_only_coaching_evidence(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-environment-must-not-be-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid")
    metrics, rules = evidence()
    records = []

    async def run():
        return await asyncio.gather(
            *[
                synthesize_coaching(
                    metrics,
                    rules,
                    api_key=SecretStr(key),
                    enabled=True,
                    client_factory=FakeProvider(records),
                )
                for key in ("sk-user-one", "sk-user-two")
            ]
        )

    results = asyncio.run(run())
    assert all(result.status == "complete" for result in results)
    assert {record["api_key"] for record in records} == {"sk-user-one", "sk-user-two"}
    for record in records:
        assert record["base_url"] == "https://api.openai.com/v1" and record["max_retries"] == 0
        request = record["request"]
        assert request["store"] is False
        assert "series" not in json.loads(request["input"])["metrics"]
        assert "xy_px" not in request["input"] and "sk-user" not in request["input"]


def test_provider_failure_does_not_expose_credentials_or_remove_rule_feedback(caplog):
    metrics, rules = evidence()
    result = asyncio.run(
        synthesize_coaching(
            metrics,
            rules,
            api_key=SecretStr("sk-private-key"),
            enabled=True,
            client_factory=FakeProvider([], error=RuntimeError("provider leaked sk-private-key")),
        )
    )
    assert result.status == "unavailable" and rules.faults
    assert "sk-private-key" not in result.model_dump_json() + caplog.text


def test_timeout_and_incomplete_output_fall_back_to_rules():
    metrics, rules = evidence()
    for provider in (FakeProvider([], delay=0.1), FakeProvider([], status="incomplete")):
        result = asyncio.run(
            synthesize_coaching(
                metrics,
                rules,
                api_key=SecretStr("sk-test"),
                enabled=True,
                timeout_seconds=0.03,
                client_factory=provider,
            )
        )
        assert result.status == "unavailable" and result.narrative is None


@pytest.mark.parametrize(
    "value",
    [
        {"recommended_drill_ids": ["invented_drill"]},
        {"priorities": [{"fault_code": "INVENTED_FAULT", "explanation": "Unsupported."}]},
        {"summary": "sk-private-key"},
    ],
)
def test_unsupported_or_sensitive_model_output_is_rejected(value):
    metrics, rules = evidence()
    result = asyncio.run(
        synthesize_coaching(
            metrics,
            rules,
            api_key=SecretStr("sk-private-key"),
            enabled=True,
            client_factory=FakeProvider([], value=narrative(**value)),
        )
    )
    assert result.status == "unavailable" and result.narrative is None


def test_real_sdk_serializes_request_scoped_key_and_structured_output_without_network():
    metrics, rules = evidence()
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "gpt-4.1-mini",
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": narrative().model_dump_json(),
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    def factory(**kwargs):
        # Close the unused default client before replacing it in this transport test.
        supplied = kwargs.pop("http_client")
        assert supplied.is_closed is False
        kwargs["http_client"] = DefaultAsyncHttpxClient(
            transport=httpx2.MockTransport(handler), trust_env=False
        )
        return AsyncOpenAI(**kwargs)

    result = asyncio.run(
        synthesize_coaching(
            metrics, rules, api_key=SecretStr("sk-wire-test"), enabled=True, client_factory=factory
        )
    )
    assert result.status == "complete"
    assert requests[0].headers["Authorization"] == "Bearer sk-wire-test"
    payload = json.loads(requests[0].content)
    assert payload["store"] is False and payload["text"]["format"]["type"] == "json_schema"
