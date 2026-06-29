from __future__ import annotations

import uuid

import braintrust
from braintrust.integrations.openai_agents import BraintrustTracingProcessor

from .config import configure_gateway_client, settings

_LOGGER: braintrust.Logger | None = None
_CONFIGURED = False


def configure_openai_agents_tracing(logger: braintrust.Logger) -> None:
    from agents import set_trace_processors, set_tracing_disabled

    set_trace_processors([BraintrustTracingProcessor(logger)])
    set_tracing_disabled(False)


def braintrust_logger() -> braintrust.Logger | None:
    global _CONFIGURED, _LOGGER
    configure_gateway_client()
    cfg = settings()
    if not cfg.braintrust_api_key:
        return None
    if _CONFIGURED:
        return _LOGGER
    _LOGGER = braintrust.init_logger(project=cfg.project_name)
    configure_openai_agents_tracing(_LOGGER)
    _CONFIGURED = True
    return _LOGGER


def configure_braintrust() -> braintrust.Logger | None:
    return braintrust_logger()


def local_request_id() -> str:
    return f"local_{uuid.uuid4().hex}"


def trace_request_id(trace: object | None) -> str:
    trace_id = getattr(trace, "trace_id", None)
    if not trace_id:
        return local_request_id()
    return str(trace_id)
