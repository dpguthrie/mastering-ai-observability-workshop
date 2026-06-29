from __future__ import annotations

import os
from typing import Any

from braintrust import DatasetPipeline

PROJECT = os.getenv("BRAINTRUST_PROJECT", "AIE-Workshop")
TARGET_DATASET = os.getenv("AIEWF_DRAFT_DATASET", "support-flywheel-draft-cases")
SOURCE_FILTER = os.getenv("AIEWF_DRAFT_PIPELINE_FILTER", "").strip()


async def transform(
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
    trace: Any | None = None,
    **_: Any,
) -> dict[str, Any] | None:
    conversation = await trace.get_thread() if trace else input
    if not conversation:
        return None

    trace_metadata = metadata or {}
    if trace:
        spans = await trace.get_spans()
        root_span = next((span for span in spans if not span.span_parents), None)
        trace_metadata = root_span.metadata if root_span and root_span.metadata else trace_metadata

    return {
        "input": conversation,
        "expected": {
            "review_status": "draft",
            "must_use": [],
            "must_not_use": [],
            "must_mention": [],
        },
        "metadata": {
            "source": "trace_to_eval_drafts_pipeline",
            "conversation_id": trace_metadata.get("conversation_id"),
            "customer_id": trace_metadata.get("customer_id"),
            "surface": trace_metadata.get("surface"),
            "turn_count": trace_metadata.get("turn_count"),
        },
    }


source: dict[str, Any] = {
    "project_name": PROJECT,
    "scope": "trace",
}
if SOURCE_FILTER:
    source["filter"] = SOURCE_FILTER

DatasetPipeline(
    name="trace-to-eval-drafts",
    source=source,
    target={
        "project_name": PROJECT,
        "dataset_name": TARGET_DATASET,
        "description": "Human-review draft eval cases derived from real support traces.",
        "metadata": {"workshop": "aiewf", "review_required": True},
    },
    transform=transform,
)
