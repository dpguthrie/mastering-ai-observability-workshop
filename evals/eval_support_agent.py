from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from braintrust import Eval

from aiewf_support.agent import build_agent
from aiewf_support.config import settings
from aiewf_support.db import ensure_database
from evals.scorers import SCORERS

EVAL_MODEL = os.getenv("AGENT_DEFAULT_MODEL") or settings().model
PROJECT_NAME = os.getenv("BRAINTRUST_PROJECT", "AIE-Workshop")

ensure_database()


def data() -> list[dict[str, Any]]:
    cases_path = ROOT / "evals" / "cases.jsonl"
    return [json.loads(line) for line in cases_path.read_text().splitlines() if line.strip()]


def input_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


async def run_case_input(case_input: Any, model: str, customer_id: str | None) -> str:
    from agents import Runner

    result = await Runner.run(build_agent(model, customer_id), case_input)
    return str(result.final_output)


async def task(input: Any, hooks) -> dict[str, Any]:
    by_input = {input_key(case["input"]): case for case in data()}
    case = by_input[input_key(input)]
    metadata = case.get("metadata") or {}
    customer_id = metadata.get("customer_id")
    return {
        "text": await run_case_input(input, EVAL_MODEL, customer_id),
        "tool_calls": [],
        "metadata": {"model": EVAL_MODEL, **metadata},
    }


def eval_data() -> list[dict[str, Any]]:
    rows = []
    for case in data():
        rows.append(
            {
                "input": case["input"],
                "expected": case.get("expected") or {},
                "metadata": case.get("metadata") or {},
            }
        )
    return rows


Eval(
    PROJECT_NAME,
    data=eval_data,
    task=task,
    scores=SCORERS,
    metadata={"agent": "attendee", "model": EVAL_MODEL},
)
