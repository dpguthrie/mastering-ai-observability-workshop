from __future__ import annotations

import os
from typing import Any

import braintrust
from pydantic import BaseModel

try:
    from scorers import (
        BINARY_CHOICE_SCORES,
        COMMUNICATION_QUALITY_PROMPT,
        SUPPORT_RESOLUTION_PROMPT,
        TOOL_USE_QUALITY_PROMPT,
        forbidden_tools_avoided,
        required_evidence_mentioned,
        required_tools_called,
    )
except ImportError:
    from evals.scorers import (
        BINARY_CHOICE_SCORES,
        COMMUNICATION_QUALITY_PROMPT,
        SUPPORT_RESOLUTION_PROMPT,
        TOOL_USE_QUALITY_PROMPT,
        forbidden_tools_avoided,
        required_evidence_mentioned,
        required_tools_called,
    )

PROJECT_NAME = os.getenv("BRAINTRUST_PROJECT", "AIE-Workshop")
JUDGE_MODEL = os.getenv("JUDGE_MODEL") or os.getenv("AGENT_DEFAULT_MODEL", "gpt-5-mini")

project = braintrust.projects.create(name=PROJECT_NAME)


class TraceScorerParams(BaseModel):
    input: Any | None = None
    output: dict[str, Any] | None = None
    expected: dict[str, Any]
    trace: Any


class EvidenceScorerParams(BaseModel):
    input: Any | None = None
    output: dict[str, Any]
    expected: dict[str, Any]


class JudgeScorerParams(BaseModel):
    input: Any | None = None
    output: Any | None = None
    expected: dict[str, Any] | None = None
    trace: Any


required_tools_called_scorer = project.scorers.create(
    name="Required tools called",
    slug="required-tools-called",
    description="Checks whether the trace called every tool listed in expected.must_use.",
    parameters=TraceScorerParams,
    handler=required_tools_called,
    if_exists="replace",
    metadata={"__pass_threshold": 1.0},
)

forbidden_tools_avoided_scorer = project.scorers.create(
    name="Forbidden tools avoided",
    slug="forbidden-tools-avoided",
    description="Checks whether the trace avoided every tool listed in expected.must_not_use.",
    parameters=TraceScorerParams,
    handler=forbidden_tools_avoided,
    if_exists="replace",
    metadata={"__pass_threshold": 1.0},
)

required_evidence_mentioned_scorer = project.scorers.create(
    name="Required evidence mentioned",
    slug="required-evidence-mentioned",
    description="Checks whether expected customer-facing evidence appears in the final answer.",
    parameters=EvidenceScorerParams,
    handler=required_evidence_mentioned,
    if_exists="replace",
    metadata={"__pass_threshold": 1.0},
)

support_resolution_scorer = project.scorers.create(
    name="Support resolution",
    slug="support-resolution",
    description="LLM judge for whether the full conversation resolved the customer's support need.",
    messages=[
        {
            "role": "user",
            "content": SUPPORT_RESOLUTION_PROMPT.replace("{thread}", "{{thread}}").replace(
                "{expected}", "{{expected}}"
            ),
        }
    ],
    model=JUDGE_MODEL,
    use_cot=True,
    choice_scores=BINARY_CHOICE_SCORES,
    if_exists="replace",
    metadata={"__pass_threshold": 1.0, "judge_model": JUDGE_MODEL},
    parameters=JudgeScorerParams,
)

tool_use_quality_scorer = project.scorers.create(
    name="Tool use quality",
    slug="tool-use-quality",
    description="LLM judge for whether tool calls were necessary, correctly ordered, and grounded the answer.",
    messages=[
        {
            "role": "user",
            "content": TOOL_USE_QUALITY_PROMPT.replace("{thread}", "{{thread}}").replace(
                "{expected}", "{{expected}}"
            ),
        }
    ],
    model=JUDGE_MODEL,
    use_cot=True,
    choice_scores=BINARY_CHOICE_SCORES,
    if_exists="replace",
    metadata={"__pass_threshold": 1.0, "judge_model": JUDGE_MODEL},
    parameters=JudgeScorerParams,
)

communication_quality_scorer = project.scorers.create(
    name="Communication quality",
    slug="communication-quality",
    description="LLM judge for clarity, empathy, concision, and appropriate promises.",
    messages=[
        {
            "role": "user",
            "content": COMMUNICATION_QUALITY_PROMPT.replace("{thread}", "{{thread}}").replace(
                "{expected}", "{{expected}}"
            ),
        }
    ],
    model=JUDGE_MODEL,
    use_cot=True,
    choice_scores=BINARY_CHOICE_SCORES,
    if_exists="replace",
    metadata={"__pass_threshold": 1.0, "judge_model": JUDGE_MODEL},
    parameters=JudgeScorerParams,
)
