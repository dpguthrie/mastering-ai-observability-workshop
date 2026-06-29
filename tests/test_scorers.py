from __future__ import annotations

import asyncio

from evals.scorers import (
    SCORERS,
    forbidden_tools_avoided,
    required_tools_called,
)


class Span:
    def __init__(self, name: str) -> None:
        self.span_attributes = {"name": name}


class Trace:
    def __init__(self, spans: list[Span]) -> None:
        self.spans = spans

    async def get_spans(self, span_type: list[str] | None = None) -> list[Span]:
        assert span_type == ["tool"]
        return self.spans


def test_required_tools_called_scores_fraction_of_expected_tools() -> None:
    score = asyncio.run(
        required_tools_called(
            input=None,
            output={},
            expected={"must_use": ["lookup_order", "check_shipment_status"]},
            trace=Trace([Span("lookup_order")]),
        )
    )

    assert score == 0.5


def test_forbidden_tools_avoided_fails_when_forbidden_tool_was_called() -> None:
    score = asyncio.run(
        forbidden_tools_avoided(
            input=None,
            output={},
            expected={"must_not_use": ["request_refund"]},
            trace=Trace([Span("lookup_order"), Span("request_refund")]),
        )
    )

    assert score == 0.0


def test_tool_use_quality_replaces_tool_calls_succeeded() -> None:
    scorer_names = {getattr(scorer, "__name__", "") for scorer in SCORERS}

    assert "tool_use_quality" in scorer_names
    assert "tool_calls_succeeded" not in scorer_names
