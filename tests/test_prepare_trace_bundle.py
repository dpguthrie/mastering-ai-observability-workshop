from __future__ import annotations

import json
from pathlib import Path

from scripts.prepare_trace_bundle import prepare_bundle


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_prepare_bundle_removes_topics_descendants_and_analysis_fields(tmp_path: Path) -> None:
    source = tmp_path / "sync-output"
    rows = [
        {
            "span_id": "root",
            "root_span_id": "root",
            "is_root": True,
            "span_attributes": {"name": "Agent workflow", "type": "task"},
            "facets": {"Task": "Refund status"},
            "classifications": {"Task": [{"label": "Refunds"}]},
            "scores": {"quality": 1},
            "comments": [{"text": "reviewed"}],
            "_async_scoring_state": {"done": True},
        },
        {
            "span_id": "response",
            "root_span_id": "root",
            "span_parents": ["root"],
            "span_attributes": {"name": "Response", "type": "llm"},
        },
        {
            "span_id": "topics",
            "root_span_id": "root",
            "span_parents": ["root"],
            "span_attributes": {"name": "Topics", "type": "automation"},
        },
        {
            "span_id": "pipeline",
            "root_span_id": "root",
            "span_parents": ["topics"],
            "span_attributes": {"name": "Pipeline", "type": "facet"},
        },
    ]
    _write_jsonl(source / "data" / "part-000001.jsonl", rows)

    output = tmp_path / "bundle"
    manifest = prepare_bundle(source, output)

    assert manifest["rows_read"] == 4
    assert manifest["rows_written"] == 2
    assert manifest["rows_removed"] == 2
    assert manifest["traces_written"] == 1

    output_rows = [
        json.loads(line)
        for part in sorted((output / "data").glob("*.jsonl"))
        for line in part.read_text().splitlines()
    ]
    output_names = {row["span_attributes"]["name"] for row in output_rows}
    assert output_names == {"Agent workflow", "Response"}
    assert output_rows[0]["facets"] is None
    assert output_rows[0]["classifications"] is None
    assert output_rows[0]["scores"] is None
    assert output_rows[0]["comments"] is None
    assert output_rows[0]["_async_scoring_state"] is None
