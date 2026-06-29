from __future__ import annotations

import asyncio

from pipelines.trace_to_eval_drafts import transform


def test_trace_to_eval_draft_row_uses_thread_and_metadata() -> None:
    class Span:
        span_parents = []
        metadata = {"conversation_id": "conv-1", "customer_id": "cus_1002", "surface": "chat_ui", "turn_count": 2}

    class Trace:
        async def get_thread(self) -> list[dict[str, str]]:
            return [
                {"role": "user", "content": "Where is my order?"},
                {"role": "assistant", "content": "It has a weather delay but is still moving."},
            ]

        async def get_spans(self) -> list[Span]:
            return [Span()]

    row = asyncio.run(transform(trace=Trace()))

    assert row is not None
    assert set(row) == {"input", "expected", "metadata"}
    assert row["input"][0]["content"] == "Where is my order?"
    assert row["expected"] == {"review_status": "draft", "must_use": [], "must_not_use": [], "must_mention": []}
    assert row["metadata"]["conversation_id"] == "conv-1"
    assert row["metadata"]["customer_id"] == "cus_1002"


def test_trace_to_eval_draft_row_falls_back_to_input_and_metadata() -> None:
    row = asyncio.run(
        transform(
            input=[{"role": "user", "content": "Can I return this?"}],
            metadata={"conversation_id": "conv-2", "customer_id": "cus_1001"},
        )
    )

    assert row is not None
    assert row["input"] == [{"role": "user", "content": "Can I return this?"}]
    assert row["metadata"]["conversation_id"] == "conv-2"
    assert row["metadata"]["customer_id"] == "cus_1001"
