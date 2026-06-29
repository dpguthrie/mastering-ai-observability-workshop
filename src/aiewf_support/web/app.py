from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from aiewf_support import tools as support_tools
from aiewf_support.agent import build_agent
from aiewf_support.config import model_ids, settings
from aiewf_support.db import seed_database
from aiewf_support.tracing import local_request_id, trace_request_id

STATIC_DIR = Path(__file__).resolve().parent / "static"
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


def model_label(model_id: str) -> str:
    words = model_id.replace("-", " ").replace("_", " ").split()
    return " ".join(word.upper() if word.lower() in {"gpt", "oss"} else word.capitalize() for word in words)


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


TOOL_ACTIVITY_LABELS = {
    "lookup_customer": ("Looking up customer", "Looked up customer"),
    "lookup_order": ("Looking up order", "Looked up order"),
    "check_shipment_status": ("Checking shipment status", "Checked shipment status"),
    "lookup_policy": ("Checking support policy", "Checked support policy"),
    "lookup_product": ("Looking up product details", "Looked up product details"),
    "list_products": ("Listing products", "Listed products"),
    "search_customer_orders": ("Searching customer orders", "Searched customer orders"),
    "initiate_return": ("Initiating return", "Initiated return"),
    "request_refund": ("Requesting refund", "Requested refund"),
    "apply_credit": ("Applying store credit", "Applied store credit"),
    "escalate_to_human": ("Escalating to human support", "Escalated to human support"),
}


def humanize_tool_name(tool_name: str) -> str:
    return " ".join(part for part in tool_name.replace("-", "_").split("_") if part).capitalize()


def tool_activity_labels(tool_name: str | None) -> tuple[str, str]:
    if not tool_name:
        return ("Using tool", "Used tool")
    human_name = humanize_tool_name(tool_name)
    return TOOL_ACTIVITY_LABELS.get(tool_name, (f"Using {human_name}", f"Used {human_name}"))


def raw_item_value(raw_item: Any, key: str) -> Any:
    if isinstance(raw_item, dict):
        return raw_item.get(key)
    return getattr(raw_item, key, None)


def tool_name_for_item(item: Any) -> str | None:
    raw_item = getattr(item, "raw_item", None)
    for key in ("name", "tool_name"):
        candidate = raw_item_value(raw_item, key)
        if isinstance(candidate, str) and candidate:
            return candidate
    for candidate in (
        getattr(item, "tool_name", None),
        getattr(item, "name", None),
        getattr(item, "title", None),
    ):
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def tool_call_id_for_item(item: Any) -> str | None:
    raw_item = getattr(item, "raw_item", None)
    for key in ("call_id", "id"):
        candidate = raw_item_value(raw_item, key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def title_from_message(message: str) -> str:
    words = re.sub(r"\s+", " ", message.strip()).split(" ")
    title = " ".join(words[:5]).strip(" .?!")
    return title or "New support chat"


def tool_widgets_for(text: str) -> list[dict[str, Any]]:
    lower = text.lower()
    widgets: list[dict[str, Any]] = []
    if "weather delay" in lower or "ord_3002" in lower:
        widgets.append(
            {
                "type": "shipment",
                "title": "Shipment status",
                "order_id": "ord_3002",
                "status": "Weather delay",
                "carrier": "FedEx",
                "detail": "Arrived at regional facility; still moving.",
            }
        )
    if "final sale" in lower or "return" in lower:
        widgets.append(
            {
                "type": "policy",
                "title": "Return policy",
                "status": "Policy check",
                "detail": "Most items are returnable unless final sale or hazmat manual review applies.",
            }
        )
    if "$15" in lower or "credit" in lower:
        widgets.append(
            {
                "type": "credit",
                "title": "Goodwill credit limit",
                "status": "$15 max",
                "detail": "Higher credits should be escalated for review.",
            }
        )
    return widgets


async def homepage(_: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers=NO_CACHE_HEADERS)


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]):
        response = await super().get_response(path, scope)
        response.headers.update(NO_CACHE_HEADERS)
        return response


async def config(_: Request) -> JSONResponse:
    cfg = settings()
    return JSONResponse(
        {
            "models": [
                {
                    "id": model_id,
                    "label": model_label(model_id),
                    "provider": "Default" if model_id == cfg.model else "Additional",
                }
                for model_id in model_ids()
            ],
            "default_model": cfg.model,
            "customer_id": cfg.chat_customer_id,
            "gateway_base_url": "https://gateway.braintrust.dev",
            "project": cfg.project_name,
        }
    )


async def reset_db(_: Request) -> JSONResponse:
    path = seed_database()
    return JSONResponse({"ok": True, "db_path": str(path)})


async def products(_: Request) -> JSONResponse:
    return JSONResponse(support_tools.list_products())


async def customers(_: Request) -> JSONResponse:
    return JSONResponse(support_tools.list_customers())


def event_text_delta(event: Any) -> str | None:
    event_type = getattr(event, "type", "")
    data = getattr(event, "data", None)
    data_type = getattr(data, "type", "")
    if event_type == "response.output_text.delta" or (
        event_type == "raw_response_event" and data_type == "response.output_text.delta"
    ):
        delta = getattr(data, "delta", None)
        if isinstance(delta, str):
            return delta
    delta = getattr(event, "delta", None)
    if isinstance(delta, str):
        return delta
    return None


async def fallback_chunks(text: str):
    for token in re.findall(r"\S+\s*", text):
        await asyncio.sleep(0.015)
        yield sse("delta", {"text": token})


def clean_agent_text(text: str) -> str:
    """Remove streamed tool-call argument fragments if a provider leaks them into final text."""
    cleaned = text.strip()
    while cleaned.startswith("{"):
        try:
            _, index = json.JSONDecoder().raw_decode(cleaned)
        except json.JSONDecodeError:
            break
        remainder = cleaned[index:].lstrip()
        if not remainder:
            break
        cleaned = remainder
    return cleaned


def fallback_conversation_id(messages: list[Any], customer_id: str) -> str:
    first_user = next(
        (
            str(message.get("content", ""))
            for message in messages
            if isinstance(message, dict) and message.get("role") == "user"
        ),
        "",
    )
    key = json.dumps({"customer_id": customer_id, "first_user": first_user}, sort_keys=True)
    return "conv_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


async def chat(request: Request) -> StreamingResponse:
    payload = await request.json()
    messages = payload.get("messages", [])
    model = payload.get("model") or settings().model
    customer_id = payload.get("customer_id") or settings().chat_customer_id
    conversation_id = str(payload.get("conversation_id") or payload.get("chat_id") or "").strip()
    if not conversation_id:
        conversation_id = fallback_conversation_id(messages, customer_id)
    reset = bool(payload.get("reset_db", False))
    if reset:
        seed_database()

    turns = [str(message.get("content", "")) for message in messages if message.get("role") == "user"]
    latest = turns[-1] if turns else ""
    agent = build_agent(model, customer_id)
    history: list[dict[str, str]] = []
    for message in messages[:-1]:
        role = message.get("role")
        if role in {"user", "assistant"}:
            history.append({"role": role, "content": str(message.get("content", ""))})
    run_input: str | list[dict[str, str]]
    if history:
        history.append({"role": "user", "content": latest})
        run_input = history
    else:
        run_input = latest

    async def generate():
        request_id = local_request_id()
        sent_meta = False
        final_text = ""
        streamed_any = False
        error_message = None
        active_tools: dict[str, tuple[str | None, str, str]] = {}
        try:
            from agents import RunConfig, Runner

            trace_metadata = {
                "conversation_id": conversation_id,
                "surface": "chat_ui",
                "customer_id": customer_id,
                "turn_count": len(turns),
            }
            result = Runner.run_streamed(agent, run_input, run_config=RunConfig(trace_metadata=trace_metadata))
            request_id = trace_request_id(result.trace)
            yield sse(
                "meta",
                {
                    "model": model,
                    "title": title_from_message(latest),
                    "thinking": True,
                    "customer_id": customer_id,
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                },
            )
            sent_meta = True
            async for event in result.stream_events():
                delta = event_text_delta(event)
                if delta:
                    streamed_any = True
                    final_text += delta
                    yield sse("delta", {"text": delta})
                    continue

                if getattr(event, "type", "") == "run_item_stream_event":
                    event_name = getattr(event, "name", "")
                    item = getattr(event, "item", None)
                    tool_name = tool_name_for_item(item)
                    call_id = tool_call_id_for_item(item) or tool_name or event_name or "tool"
                    if event_name in {"tool_called", "tool_search_called", "mcp_list_tools"}:
                        start_label, done_label = tool_activity_labels(tool_name)
                        active_tools[call_id] = (tool_name, start_label, done_label)
                        yield sse(
                            "activity",
                            {
                                "id": call_id,
                                "status": "active",
                                "tool": tool_name,
                                "label": start_label,
                            },
                        )
                    elif event_name in {"tool_output", "tool_search_output_created"}:
                        stored_tool_name, _, done_label = active_tools.pop(
                            call_id,
                            (tool_name, *tool_activity_labels(tool_name)),
                        )
                        yield sse(
                            "activity",
                            {
                                "id": call_id,
                                "status": "complete",
                                "tool": stored_tool_name,
                                "label": done_label,
                            },
                        )
            if not final_text:
                final_text = clean_agent_text(str(result.final_output or ""))
                async for chunk in fallback_chunks(final_text):
                    yield chunk
            elif not streamed_any:
                final_text = clean_agent_text(final_text)
                async for chunk in fallback_chunks(final_text):
                    yield chunk
        except Exception as exc:
            error_message = str(exc)
            final_text = (
                "I could not reach the live model path, so here is a local workshop fallback. "
                "Check your model, Braintrust Gateway, and API key configuration before the live demo."
            )
            if not sent_meta:
                yield sse(
                    "meta",
                    {
                        "model": model,
                        "title": title_from_message(latest),
                        "thinking": True,
                        "customer_id": customer_id,
                        "conversation_id": conversation_id,
                        "request_id": request_id,
                    },
                )
            yield sse("error", {"message": error_message})
            async for chunk in fallback_chunks(final_text):
                yield chunk
        widgets = tool_widgets_for(final_text)
        yield sse("widgets", {"widgets": widgets})
        yield sse(
            "done",
            {
                "text": final_text,
                "turn_count": len(turns),
                "conversation_id": conversation_id,
                "request_id": request_id,
            },
        )

    return StreamingResponse(generate(), media_type="text/event-stream")


app = Starlette(
    debug=True,
    routes=[
        Route("/", homepage),
        Route("/api/config", config),
        Route("/api/reset-db", reset_db, methods=["POST"]),
        Route("/api/products", products),
        Route("/api/customers", customers),
        Route("/api/chat", chat, methods=["POST"]),
        Mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static"),
    ],
)
