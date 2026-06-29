from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_eval_cases_use_customer_state_instead_of_name_introductions() -> None:
    forbidden = re.compile(
        r"\b(my name is|i'm|i am|here\.|maya|devon|priya|samir|@example\.com)\b",
        re.IGNORECASE,
    )
    cases = [json.loads(line) for line in (ROOT / "evals" / "cases.jsonl").read_text().splitlines() if line.strip()]

    for case in cases:
        assert set(case) == {"input", "expected", "metadata"}
        assert case["metadata"]["customer_id"].startswith("cus_")
        assert case["metadata"]["case_id"]
        assert not forbidden.search(case["input"])
