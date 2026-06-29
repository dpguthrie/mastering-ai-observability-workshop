from __future__ import annotations

import asyncio
import os
import uuid
from collections import Counter
from typing import Any

from braintrust.integrations.openai_agents import BraintrustTracingProcessor

from aiewf_support import config as config_module
from aiewf_support.config import GATEWAY_BASE_URL, configure_gateway_client, settings
from aiewf_support.tracing import configure_openai_agents_tracing, trace_request_id
from scripts import run_production_sim


def test_configure_gateway_client_sets_agents_sdk_default_without_mutating_openai_env(monkeypatch) -> None:
    from agents.models import _openai_shared

    original_client = _openai_shared.get_default_openai_client()

    monkeypatch.setenv("BRAINTRUST_API_KEY", "braintrust-test-key")
    monkeypatch.setenv("BRAINTRUST_PROJECT", "AIE-Workshop")
    monkeypatch.setenv("OPENAI_API_KEY", "stale-openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(config_module, "_GATEWAY_CLIENT", None)
    monkeypatch.setattr(config_module, "_GATEWAY_CLIENT_KEY", None)

    try:
        configure_gateway_client()

        client = _openai_shared.get_default_openai_client()
        assert client is not None
        assert str(client.base_url).rstrip("/") == GATEWAY_BASE_URL
        assert client.api_key == "braintrust-test-key"
        assert os.environ["OPENAI_API_KEY"] == "stale-openai-key"
        assert os.environ["OPENAI_BASE_URL"] == "https://api.openai.com/v1"
    finally:
        _openai_shared.set_default_openai_client(original_client)


def test_trace_request_id_uses_agents_trace_id() -> None:
    class FakeTrace:
        trace_id = "trace_test"

    assert trace_request_id(FakeTrace()) == "trace_test"
    assert trace_request_id(None).startswith("local_")


def test_configure_openai_agents_tracing_replaces_default_exporter() -> None:
    import agents

    class FakeLogger:
        def flush(self) -> None:
            return None

    provider = agents.tracing.get_trace_provider()
    original_processors = tuple(getattr(getattr(provider, "_multi_processor", None), "_processors", ()))
    original_manual_disabled = getattr(provider, "_manual_disabled", None)

    try:
        configure_openai_agents_tracing(FakeLogger())
        processors = tuple(getattr(getattr(provider, "_multi_processor", None), "_processors", ()))

        assert len(processors) == 1
        assert isinstance(processors[0], BraintrustTracingProcessor)
        assert getattr(provider, "_disabled", True) is False
    finally:
        provider.set_processors(list(original_processors))
        provider._manual_disabled = original_manual_disabled
        if hasattr(provider, "_refresh_disabled_flag"):
            provider._refresh_disabled_flag()


def test_judge_model_defaults_to_agent_model(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_DEFAULT_MODEL", "agent-model")
    monkeypatch.setenv("ADDITIONAL_MODELS", "other-model")
    monkeypatch.delenv("JUDGE_MODEL", raising=False)

    assert settings().judge_model == "agent-model"


def test_judge_model_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_DEFAULT_MODEL", "agent-model")
    monkeypatch.setenv("JUDGE_MODEL", "judge-model")

    assert settings().judge_model == "judge-model"


def test_production_sim_passes_trace_metadata_through_run_config(monkeypatch) -> None:
    captured_kwargs: list[dict[str, Any]] = []

    async def fake_next_user_turn(*args: Any, **kwargs: Any) -> run_production_sim.SimulatedUserTurn:
        return run_production_sim.SimulatedUserTurn(
            done=False,
            message="Where is my order?",
            sentiment="neutral",
            reason="test turn",
        )

    class FakeResult:
        final_output = "Your order is on the way."

        def to_input_list(self) -> list[dict[str, str]]:
            return []

    async def fake_run(cls: object, starting_agent: object, run_input: Any, **kwargs: Any) -> FakeResult:
        captured_kwargs.append(kwargs)
        return FakeResult()

    monkeypatch.setattr(run_production_sim, "build_agent", lambda *args, **kwargs: object())
    monkeypatch.setattr(run_production_sim, "next_user_turn", fake_next_user_turn)

    from agents import Runner

    monkeypatch.setattr(Runner, "run", classmethod(fake_run))

    scenario = run_production_sim.GeneratedScenario(
        customer_id="cus_1002",
        solvability="supported",
        topic_target="tasks",
        user_goal="Track an order",
        situation="Customer wants shipment status.",
        tone="neutral",
        user_agent_instructions="Ask about order status.",
        max_turns=1,
    )

    asyncio.run(
        run_production_sim.run_dynamic_conversation(
            scenario,
            conversation_id="test_conversation",
            agent_model="gpt-test",
            user_model="gpt-test",
            max_turns=1,
        )
    )

    assert captured_kwargs
    run_config = captured_kwargs[0]["run_config"]
    assert run_config.trace_metadata["conversation_id"] == "test_conversation"
    assert run_config.trace_metadata["surface"] == "chat_ui"
    assert run_config.trace_metadata["customer_id"] == "cus_1002"
    assert set(run_config.trace_metadata) == {"conversation_id", "customer_id", "surface", "turn_count"}


def test_template_scenarios_are_deterministic_and_valid() -> None:
    scenarios = run_production_sim.generate_template_scenarios(20, seed=7, max_turns=5)
    repeated = run_production_sim.generate_template_scenarios(20, seed=7, max_turns=5)

    assert scenarios == repeated
    assert len(scenarios) == 20
    assert {scenario.solvability for scenario in scenarios} <= {"supported", "unsupported", "likely_issue"}
    assert {scenario.topic_target for scenario in scenarios} <= {"tasks", "issues", "sentiment"}
    assert all(scenario.customer_id in run_production_sim.CUSTOMER_IDS for scenario in scenarios)
    assert all(1 <= scenario.max_turns <= 5 for scenario in scenarios)


def test_production_sim_conversation_id_does_not_leak_scenario_labels() -> None:
    scenario = run_production_sim.GeneratedScenario(
        customer_id="cus_1002",
        solvability="likely_issue",
        topic_target="issues",
        user_goal="Get a replacement sent for a damaged item.",
        situation="The customer wants a replacement, not a return.",
        tone="frustrated and impatient",
        user_agent_instructions="Ask for replacement help.",
        max_turns=1,
    )

    conversation_id = run_production_sim.conversation_id_for_run(12, scenario)

    assert str(uuid.UUID(conversation_id)) == conversation_id
    assert "likely_issue" not in conversation_id
    assert "replacement" not in conversation_id
    assert "damaged" not in conversation_id


def test_template_scenarios_skew_toward_shorter_neutral_conversations() -> None:
    scenarios = run_production_sim.generate_template_scenarios(200, seed=7, max_turns=5)
    turn_counts = Counter(scenario.max_turns for scenario in scenarios)
    tone_counts = Counter(scenario.tone for scenario in scenarios)
    solvability_counts = Counter(scenario.solvability for scenario in scenarios)

    assert turn_counts[1] + turn_counts[2] > turn_counts[3] + turn_counts[4] + turn_counts[5]
    assert tone_counts["frustrated and impatient"] < len(scenarios) * 0.15
    assert solvability_counts["supported"] > solvability_counts["likely_issue"] + solvability_counts["unsupported"]
    assert solvability_counts["unsupported"] < len(scenarios) * 0.15
