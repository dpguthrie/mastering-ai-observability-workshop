from __future__ import annotations

import argparse
import json
import tarfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TOPIC_SPAN_NAME = "Topics"
STRIPPED_ANALYSIS_FIELDS = ("facets", "classifications", "scores", "comments", "_async_scoring_state")
DEFAULT_MAX_PART_BYTES = 64 * 1024 * 1024


def _jsonl_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]

    data_dir = input_path / "data"
    if data_dir.is_dir():
        input_path = data_dir

    files = sorted(input_path.glob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"No .jsonl files found under {input_path}")
    return files


def _span_name(row: dict[str, Any]) -> str | None:
    attrs = row.get("span_attributes") or {}
    return attrs.get("name") or row.get("name")


def _load_span_graph(files: list[Path]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    spans: dict[str, dict[str, Any]] = {}
    children: dict[str, list[str]] = defaultdict(list)
    for file in files:
        with file.open() as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                span_id = row.get("span_id")
                if not span_id:
                    continue
                spans[span_id] = row
                for parent_id in row.get("span_parents") or []:
                    children[parent_id].append(span_id)
    return spans, children


def _topic_span_ids(spans: dict[str, dict[str, Any]], children: dict[str, list[str]]) -> set[str]:
    remove = {span_id for span_id, row in spans.items() if _span_name(row) == TOPIC_SPAN_NAME}
    stack = list(remove)
    while stack:
        span_id = stack.pop()
        for child_id in children.get(span_id, []):
            if child_id not in remove:
                remove.add(child_id)
                stack.append(child_id)
    return remove


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(row)
    for field in STRIPPED_ANALYSIS_FIELDS:
        if field in cleaned:
            cleaned[field] = None
    return cleaned


def _write_row(
    row: dict[str, Any],
    output_dir: Path,
    state: dict[str, Any],
    max_part_bytes: int,
) -> None:
    encoded = (json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    if state["handle"] is None or state["bytes"] + len(encoded) > max_part_bytes:
        if state["handle"] is not None:
            state["handle"].close()
        state["part"] += 1
        part_path = output_dir / f"part-{state['part']:06d}.jsonl"
        state["handle"] = part_path.open("wb")
        state["bytes"] = 0
        state["parts"].append(part_path)
    state["handle"].write(encoded)
    state["bytes"] += len(encoded)


def prepare_bundle(input_path: Path, output_path: Path, max_part_bytes: int = DEFAULT_MAX_PART_BYTES) -> dict[str, Any]:
    files = _jsonl_files(input_path)
    spans, children = _load_span_graph(files)
    removed_span_ids = _topic_span_ids(spans, children)
    removed_names = Counter(
        _span_name(spans[span_id]) or "<unnamed>" for span_id in removed_span_ids if span_id in spans
    )

    data_dir = output_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    for existing in data_dir.glob("*.jsonl"):
        existing.unlink()

    state: dict[str, Any] = {"handle": None, "part": 0, "bytes": 0, "parts": []}
    rows_read = 0
    rows_written = 0
    rows_removed = 0
    root_span_ids: set[str] = set()

    try:
        for file in files:
            with file.open() as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    rows_read += 1
                    row = json.loads(line)
                    if row.get("span_id") in removed_span_ids:
                        rows_removed += 1
                        continue
                    root_span_id = row.get("root_span_id")
                    if root_span_id:
                        root_span_ids.add(root_span_id)
                    _write_row(_clean_row(row), data_dir, state, max_part_bytes)
                    rows_written += 1
    finally:
        if state["handle"] is not None:
            state["handle"].close()

    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "input": str(input_path),
        "rows_read": rows_read,
        "rows_written": rows_written,
        "rows_removed": rows_removed,
        "traces_written": len(root_span_ids),
        "removed_topic_spans": len(removed_span_ids),
        "removed_span_names": dict(sorted(removed_names.items())),
        "stripped_analysis_fields": list(STRIPPED_ANALYSIS_FIELDS),
        "part_files": [part.name for part in state["parts"]],
    }
    (output_path / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def write_archive(output_path: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(output_path, arcname=output_path.name)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a sanitized Braintrust sync trace bundle for workshop import."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="bt sync pull output directory, data directory, or JSONL file.",
    )
    parser.add_argument("--output", default=Path(".workshop_private/aiewf-sample-traces"), type=Path)
    parser.add_argument("--archive", default=Path(".workshop_private/aiewf-sample-traces.tar.gz"), type=Path)
    parser.add_argument("--max-part-bytes", default=DEFAULT_MAX_PART_BYTES, type=int)
    parser.add_argument("--no-archive", action="store_true")
    args = parser.parse_args()

    manifest = prepare_bundle(args.input, args.output, args.max_part_bytes)
    if not args.no_archive:
        write_archive(args.output, args.archive)

    print(f"Wrote {manifest['rows_written']} rows across {len(manifest['part_files'])} part file(s)")
    print(f"Removed {manifest['rows_removed']} Topics automation rows")
    print(f"Traces: {manifest['traces_written']}")
    if not args.no_archive:
        print(f"Archive: {args.archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
