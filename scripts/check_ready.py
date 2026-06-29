from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aiewf_support.agent import build_agent
from aiewf_support.config import settings
from aiewf_support.db import database_is_seeded, seed_database
from aiewf_support.tracing import configure_braintrust

MODEL_CATALOG_URL = (
    "https://raw.githubusercontent.com/braintrustdata/braintrust-proxy/main/packages/proxy/schema/model_list.json"
)
TOOL_CAPABLE_FORMATS = {"openai", "anthropic", "google", "converse"}


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    warning: bool = False


def print_result(result: CheckResult) -> None:
    status = "WARN" if result.warning else "OK" if result.ok else "FAIL"
    print(f"[{status}] {result.name}: {result.message}")


def is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    return not stripped or stripped in {"...", "TODO", "CHANGE_ME"} or stripped.startswith("<")


def check_env_file() -> CheckResult:
    env_path = ROOT / ".env"
    if env_path.exists():
        return CheckResult(".env", True, f"found {env_path.relative_to(ROOT)}")
    return CheckResult(".env", False, "missing .env; run `cp .env.example .env` and fill it in")


def check_bt_cli() -> CheckResult:
    bt_path = shutil.which("bt")
    if bt_path is None:
        return CheckResult("bt CLI", False, "missing; install the Braintrust CLI before running evals or traces")
    try:
        completed = subprocess.run(
            [bt_path, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult("bt CLI", False, f"found at {bt_path}, but could not run `bt --version`: {exc}")
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip() or f"exit code {completed.returncode}"
        return CheckResult("bt CLI", False, f"found at {bt_path}, but `bt --version` failed: {message}")
    version = (completed.stdout or completed.stderr).strip().splitlines()[0]
    return CheckResult("bt CLI", True, f"{version} at {bt_path}")


def check_api_key() -> CheckResult:
    api_key = settings().braintrust_api_key
    if is_placeholder(api_key):
        return CheckResult(
            "BRAINTRUST_API_KEY",
            False,
            "missing or placeholder value; create a Braintrust API key and add it to .env",
        )
    return CheckResult("BRAINTRUST_API_KEY", True, "present")


def check_default_model() -> CheckResult:
    model = settings().model
    if is_placeholder(model):
        return CheckResult("AGENT_DEFAULT_MODEL", False, "missing model id in .env")
    return CheckResult("AGENT_DEFAULT_MODEL", True, model)


def check_database(seed: bool) -> CheckResult:
    cfg = settings()
    if seed:
        path = seed_database(cfg.db_path)
        return CheckResult("database", True, f"seeded {path}")
    if database_is_seeded(cfg.db_path):
        return CheckResult("database", True, f"seeded at {cfg.db_path}")
    return CheckResult(
        "database",
        False,
        "not seeded; run `uv run python scripts/seed_db.py` or rerun this script with `--seed`",
    )


def fetch_model_catalog(timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        MODEL_CATALOG_URL,
        headers={"User-Agent": "aiewf-readiness-check"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_model_catalog(model: str, timeout: float) -> CheckResult:
    try:
        catalog = fetch_model_catalog(timeout)
    except (TimeoutError, urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        return CheckResult(
            "model catalog",
            True,
            f"could not fetch catalog ({exc}); continuing to live model smoke",
            warning=True,
        )

    spec = catalog.get(model)
    if spec is None:
        needle = model.lower()
        matches = [name for name in catalog if needle in name.lower() or name.lower() in needle][:5]
        suffix = f"; similar catalog ids: {', '.join(matches)}" if matches else ""
        return CheckResult(
            "model catalog",
            True,
            f"{model!r} is not in the public catalog{suffix}. This can be okay for custom providers.",
            warning=True,
        )

    model_format = spec.get("format", "unknown")
    flavor = spec.get("flavor", "unknown")
    providers = ", ".join(spec.get("available_providers", [])) or "not listed"
    if flavor != "chat":
        return CheckResult(
            "model catalog",
            False,
            f"{model!r} has flavor={flavor!r}; this workshop needs a chat model",
        )
    if model_format not in TOOL_CAPABLE_FORMATS:
        return CheckResult(
            "model catalog",
            False,
            f"{model!r} has format={model_format!r}; this workshop needs a tool-capable chat format",
        )
    return CheckResult(
        "model catalog",
        True,
        f"{model!r} is cataloged as format={model_format}, flavor={flavor}, providers={providers}",
    )


async def run_agent_tool_smoke(model: str) -> CheckResult:
    logger = configure_braintrust()
    try:
        from agents import Runner
    except ImportError as exc:
        return CheckResult("agent tool smoke", False, f"OpenAI Agents SDK import failed: {exc}")

    agent = build_agent(model=model, customer_id=settings().chat_customer_id)
    prompt = (
        "Readiness check: call the lookup_order tool with order_id `ord_3002` before answering. "
        "Then reply in one short sentence that starts with `READY:` and includes the order status."
    )

    try:
        result = await Runner.run(agent, prompt, max_turns=6)
    except Exception as exc:
        return CheckResult(
            "agent tool smoke",
            False,
            f"live Gateway/tool-call run failed for {model!r}: {exc}",
        )
    finally:
        if logger is not None:
            logger.flush()

    tool_outputs = [
        str(getattr(item, "output", ""))
        for item in getattr(result, "new_items", [])
        if getattr(item, "type", "") == "tool_call_output_item"
    ]
    used_order_tool = any("ord_3002" in output for output in tool_outputs)
    final_output = str(getattr(result, "final_output", "") or "").strip()
    if not used_order_tool:
        return CheckResult(
            "agent tool smoke",
            False,
            "model responded but did not complete the required support-agent tool call",
        )
    if not final_output:
        return CheckResult("agent tool smoke", False, "model completed a tool call but returned empty final output")
    return CheckResult("agent tool smoke", True, f"{model!r} completed a real support-agent tool call")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether the workshop repo is ready to run.")
    parser.add_argument("--seed", action="store_true", help="Seed the local database before checking it.")
    parser.add_argument("--skip-model", action="store_true", help="Skip the live Gateway/model compatibility smoke.")
    parser.add_argument("--catalog-timeout", type=float, default=5.0, help="Seconds to wait for the model catalog.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")

    results = [
        check_env_file(),
        check_bt_cli(),
        check_api_key(),
        check_default_model(),
        check_database(seed=args.seed),
    ]

    model = settings().model
    if not is_placeholder(model):
        results.append(check_model_catalog(model, timeout=args.catalog_timeout))

    blocking_failure = any(not result.ok and not result.warning for result in results)
    if not args.skip_model and not blocking_failure:
        results.append(asyncio.run(run_agent_tool_smoke(model)))
    elif args.skip_model:
        results.append(CheckResult("agent tool smoke", True, "skipped by --skip-model", warning=True))

    print("\nWorkshop readiness checks\n")
    for result in results:
        print_result(result)

    failures = [result for result in results if not result.ok and not result.warning]
    if failures:
        print("\nNot ready yet. Fix the FAIL items above and rerun `make ready`.")
        return 1

    print("\nReady to proceed with the workshop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
