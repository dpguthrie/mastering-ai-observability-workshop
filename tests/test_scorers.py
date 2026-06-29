from __future__ import annotations

import asyncio
from typing import Any

from evals.scorers import tool_calls_succeeded


class Span:
    def __init__(self, error: Any | None = None) -> None:
        self.error = error


class Trace:
    def __init__(self, spans: list[Span]) -> None:
        self.spans = spans

    async def get_spans(self, span_type: list[str] | None = None) -> list[Span]:
        assert span_type == ["tool"]
        return self.spans


def test_tool_calls_succeeded_passes_without_tool_errors() -> None:
    score = asyncio.run(tool_calls_succeeded(trace=Trace([Span(), Span()])))

    assert score == 1.0


def test_tool_calls_succeeded_fails_with_tool_error() -> None:
    score = asyncio.run(tool_calls_succeeded(trace=Trace([Span(), Span(error={"message": "failed"})])))

    assert score == 0.0
