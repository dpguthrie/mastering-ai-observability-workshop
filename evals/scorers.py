from __future__ import annotations

import json
from typing import Any, Literal

from braintrust import Score
from pydantic import BaseModel

from aiewf_support.config import gateway_openai_client, settings


def _tool_names(spans: list[Any]) -> list[str]:
    return [span.span_attributes.get("name") for span in spans if span.span_attributes.get("name")]


async def _tools_called(trace: Any) -> list[str]:
    return _tool_names(await trace.get_spans(span_type=["tool"]))


async def required_tools_called(input: Any, output: dict[str, Any], expected: dict[str, Any], trace: Any) -> float:
    required = expected.get("must_use", [])
    if not required:
        return 1.0

    tools_called = await _tools_called(trace)
    return sum(tool in tools_called for tool in required) / len(required)


async def forbidden_tools_avoided(input: Any, output: dict[str, Any], expected: dict[str, Any], trace: Any) -> float:
    forbidden = expected.get("must_not_use", [])
    tools_called = await _tools_called(trace)
    return 0.0 if any(tool in tools_called for tool in forbidden) else 1.0


async def tool_calls_succeeded(
    input: Any | None = None,
    output: Any | None = None,
    expected: dict[str, Any] | None = None,
    trace: Any | None = None,
) -> float:
    del input, output, expected
    if trace is None:
        return 1.0

    tool_spans = await trace.get_spans(span_type=["tool"])
    return 0.0 if any(getattr(span, "error", None) for span in tool_spans) else 1.0


def required_evidence_mentioned(input: Any, output: dict[str, Any], expected: dict[str, Any]) -> float:
    mentions = [str(value).lower() for value in expected.get("must_mention", [])]
    if not mentions:
        return 1.0

    text = str(output.get("text", "")).lower()
    return sum(mention in text for mention in mentions) / len(mentions)


def _conversation_from_input_output(input: Any, output: Any) -> list[dict[str, str]]:
    if isinstance(input, list):
        messages = [
            {"role": str(message.get("role", "user")), "content": str(message.get("content", ""))}
            for message in input
            if isinstance(message, dict)
        ]
    else:
        messages = [{"role": "user", "content": str(input)}]

    if isinstance(output, dict):
        assistant_text = str(output.get("text", ""))
    else:
        assistant_text = str(output)
    if assistant_text:
        messages.append({"role": "assistant", "content": assistant_text})

    return messages


class JudgeOutput(BaseModel):
    choice: Literal["PASS", "FAIL"]
    reasoning: str


BINARY_CHOICE_SCORES = {"PASS": 1.0, "FAIL": 0.0}


SUPPORT_RESOLUTION_PROMPT = """
You are a strict binary LLM judge for customer-support conversations.

Use private step-by-step reasoning before choosing, but do not expose the chain
of thought. If a rationale is requested, give only a short factual reason.

Be harsh. Return PASS only when the assistant fully resolves the visible support
need with correct evidence, correct policy/tool use, a clear outcome or next
step, and no unsupported promises. Return FAIL for partial resolution, missing
evidence, unsupported actions, unclear next steps, wrong policy, ignored user
requests, or unresolved ambiguity.

Choices:
PASS - the assistant fully resolved the support need.
FAIL - the assistant did not fully resolve the support need.

Few-shot examples:

Example 1:
Conversation: The user asks where a delayed order is. The assistant checks the
shipment, explains the weather delay, gives the current carrier status, and
sets a clear next step.
Expected behavior: mention weather delay and current shipment evidence.
Judgment: PASS.

Example 2:
Conversation: The user asks for a replacement. The assistant says replacements
are unavailable but does not offer the supported return, refund review, or
escalation path.
Expected behavior: explain the supported alternative or escalation path.
Judgment: FAIL.

Example 3:
Conversation: The user asks for a refund on a delivered package. The assistant
refunds or promises a refund without checking shipment evidence.
Expected behavior: check evidence before refunding.
Judgment: FAIL.

Now evaluate this conversation.

Conversation:
{thread}

Expected behavior:
{expected}
"""


COMMUNICATION_QUALITY_PROMPT = """
You are a strict binary LLM judge for customer-support communication quality.

Use private step-by-step reasoning before choosing, but do not expose the chain
of thought. If a rationale is requested, give only a short factual reason.

Be harsh. Return PASS only when the assistant is clear, concise, empathetic,
specific, action-oriented, and avoids unsupported promises. Return FAIL for
confusing wording, evasive answers, missing next steps, excessive verbosity,
cold tone in a sensitive situation, or claims that are not grounded in the
conversation.

Choices:
PASS - the assistant communicates clearly and appropriately.
FAIL - the assistant has a material communication issue.

Few-shot examples:

Example 1:
Conversation: The user is frustrated about a delayed order. The assistant
acknowledges the frustration, summarizes the evidence, and gives one concrete
next step.
Judgment: PASS.

Example 2:
Conversation: The user asks a direct policy question. The assistant gives a
long generic answer and never states what the user should do next.
Judgment: FAIL.

Example 3:
Conversation: The user asks why an action is unavailable. The assistant repeats
policy language without explaining the reason or closest supported alternative.
Judgment: FAIL.

Now evaluate this conversation.

Conversation:
{thread}

Expected behavior, if provided:
{expected}
"""


async def _judge_thread(
    prompt_template: str,
    input: Any,
    output: Any,
    expected: dict[str, Any] | None,
    trace: Any,
    name: str,
) -> Score:
    thread = await trace.get_thread()
    if not thread:
        thread = _conversation_from_input_output(input, output)
    cfg = settings()
    prompt = prompt_template.format(
        thread=json.dumps(thread, indent=2, default=str),
        expected=json.dumps(expected or {}, indent=2, default=str),
    )
    response = await gateway_openai_client().responses.parse(
        model=cfg.judge_model,
        input=[{"role": "user", "content": prompt}],
        text_format=JudgeOutput,
    )
    result = response.output_parsed
    return Score(
        name=name,
        score=BINARY_CHOICE_SCORES[result.choice],
        metadata={"choice": result.choice, "reasoning": result.reasoning, "judge_model": cfg.judge_model},
    )


async def support_resolution(
    input: Any, output: dict[str, Any], expected: dict[str, Any] | None, trace: Any
) -> Score:
    return await _judge_thread(SUPPORT_RESOLUTION_PROMPT, input, output, expected, trace, "support_resolution")


async def communication_quality(
    input: Any, output: dict[str, Any], expected: dict[str, Any] | None, trace: Any
) -> Score:
    return await _judge_thread(COMMUNICATION_QUALITY_PROMPT, input, output, expected, trace, "communication_quality")


SCORERS = [
    required_tools_called,
    forbidden_tools_avoided,
    tool_calls_succeeded,
    required_evidence_mentioned,
    support_resolution,
    communication_quality,
]
