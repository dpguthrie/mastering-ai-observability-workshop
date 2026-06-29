from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from braintrust import Eval, init_dataset

from aiewf_support.agent import build_agent
from aiewf_support.config import settings
from aiewf_support.db import ensure_database
from evals.scorers import SCORERS

CFG = settings()
EVAL_MODEL = os.getenv("AGENT_DEFAULT_MODEL") or CFG.model
PROJECT_NAME = CFG.project_name
EVAL_DATASET = os.getenv("AIEWF_EVAL_DATASET") or os.getenv("EVAL_DATASET", "support-agent-eval-cases")
REVIEW_STATUS = os.getenv("AIEWF_EVAL_REVIEW_STATUS", "").strip()

ensure_database()


def eval_data() -> list[dict[str, Any]]:
    dataset = init_dataset(project=PROJECT_NAME, name=EVAL_DATASET)
    rows = []
    for row in dataset.fetch():
        expected = row.get("expected") or {}
        if REVIEW_STATUS and expected.get("review_status") != REVIEW_STATUS:
            continue
        rows.append(row)
    if rows:
        return rows
    suffix = f" with expected.review_status={REVIEW_STATUS!r}" if REVIEW_STATUS else ""
    raise ValueError(
        f"No eval cases found in Braintrust dataset {EVAL_DATASET!r}{suffix}. "
        "Run `make create-eval-dataset` to seed starter cases."
    )


async def run_case_input(case_input: Any, model: str, customer_id: str | None) -> str:
    from agents import Runner

    result = await Runner.run(build_agent(model, customer_id), case_input)
    return str(result.final_output)


async def task(input: Any, hooks) -> dict[str, Any]:
    metadata = hooks.metadata or {}
    customer_id = metadata.get("customer_id")
    return {
        "text": await run_case_input(input, EVAL_MODEL, customer_id),
        "tool_calls": [],
    }


Eval(
    PROJECT_NAME,
    data=eval_data,
    task=task,
    scores=SCORERS,
    metadata={"model": EVAL_MODEL, "dataset": EVAL_DATASET},
)
