from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_BASE_URL = "https://gateway.braintrust.dev"
_GATEWAY_CLIENT_KEY: str | None = None
_GATEWAY_CLIENT: Any | None = None


@dataclass(frozen=True)
class Settings:
    db_path: Path
    project_name: str
    model: str
    judge_model: str
    additional_models: tuple[str, ...]
    chat_customer_id: str
    braintrust_api_key: str | None


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def settings() -> Settings:
    load_dotenv(ROOT / ".env")
    model = os.getenv("AGENT_DEFAULT_MODEL", "gpt-5-mini")
    additional_models = _csv_env("ADDITIONAL_MODELS")
    judge_model = os.getenv("JUDGE_MODEL") or model
    return Settings(
        db_path=Path(os.getenv("AIEWF_DB_PATH", str(ROOT / "data" / "workshop.db"))),
        project_name=os.getenv("BRAINTRUST_PROJECT", "AIE-Workshop"),
        model=model,
        judge_model=judge_model,
        additional_models=additional_models,
        chat_customer_id=os.getenv("AIEWF_CHAT_CUSTOMER_ID", "cus_1002"),
        braintrust_api_key=os.getenv("BRAINTRUST_API_KEY") or None,
    )


def model_ids() -> tuple[str, ...]:
    cfg = settings()
    return tuple(dict.fromkeys((cfg.model, *cfg.additional_models)))


def configure_gateway_client() -> None:
    global _GATEWAY_CLIENT, _GATEWAY_CLIENT_KEY

    cfg = settings()
    if not cfg.braintrust_api_key:
        return
    if _GATEWAY_CLIENT is not None and _GATEWAY_CLIENT_KEY == cfg.braintrust_api_key:
        return

    from agents import set_default_openai_client
    from openai import AsyncOpenAI

    _GATEWAY_CLIENT = AsyncOpenAI(api_key=cfg.braintrust_api_key, base_url=GATEWAY_BASE_URL)
    _GATEWAY_CLIENT_KEY = cfg.braintrust_api_key
    set_default_openai_client(_GATEWAY_CLIENT, use_for_tracing=False)


def gateway_openai_client() -> Any:
    configure_gateway_client()
    if _GATEWAY_CLIENT is not None:
        return _GATEWAY_CLIENT

    from openai import AsyncOpenAI

    return AsyncOpenAI()
