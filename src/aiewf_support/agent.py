from __future__ import annotations

import asyncio

from . import tools as support_tools
from .config import settings
from .db import seed_database
from .tracing import configure_braintrust

INSTRUCTIONS = """You are Trailhead Outfitters' support agent.

Help customers with orders, shipments, returns, refunds, credits, policies, and escalation.
Use available tools when you need account or order state. Be concise and friendly.
Do not reveal internal IDs unless useful for support continuity.
"""


def instructions_for_customer(customer_id: str | None = None) -> str:
    if not customer_id:
        return INSTRUCTIONS
    return (
        INSTRUCTIONS
        + "\nThe authenticated chat state includes current_customer_id="
        + customer_id
        + ". When the customer says my account, my order, or my shipment, use this customer ID as the "
        "customer identifier. Do not ask the customer to restate their name."
    )


def _configure_runtime() -> None:
    configure_braintrust()


def build_agent(model: str | None = None, customer_id: str | None = None):
    """Build the OpenAI Agents SDK agent with deterministic business tools."""
    configure_braintrust()

    from agents import Agent, function_tool

    @function_tool
    def lookup_customer(identifier: str) -> str:
        """Look up a customer by customer ID or email. Use current_customer_id for the authenticated customer."""
        return support_tools.dump_json(support_tools.lookup_customer(identifier))

    @function_tool
    def lookup_order(order_id: str) -> str:
        """Look up an order with items, shipment, returns, and refunds."""
        return support_tools.dump_json(support_tools.lookup_order(order_id))

    @function_tool
    def check_shipment_status(order_id: str) -> str:
        """Check shipment state and return operational guidance."""
        return support_tools.dump_json(support_tools.check_shipment_status(order_id))

    @function_tool
    def lookup_policy(topic: str) -> str:
        """Look up a support policy by topic, such as returns, refunds, shipping, or credits."""
        return support_tools.dump_json(support_tools.lookup_policy(topic))

    @function_tool
    def lookup_product(query: str) -> str:
        """Look up products by ID, name, category, final-sale status, or hazmat status."""
        return support_tools.dump_json(support_tools.lookup_product(query))

    @function_tool
    def list_products() -> str:
        """List products and return eligibility flags."""
        return support_tools.dump_json(support_tools.list_products())

    @function_tool
    def search_customer_orders(identifier: str, query: str) -> str:
        """Search a customer's orders by product, category, shipment state, or order status."""
        return support_tools.dump_json(support_tools.search_customer_orders(identifier, query))

    @function_tool
    def initiate_return(order_id: str, product_id: str, reason: str) -> str:
        """Initiate a return when the item and account are eligible."""
        return support_tools.dump_json(support_tools.initiate_return(order_id, product_id, reason))

    @function_tool
    def request_refund(order_id: str, amount_cents: int, reason: str, evidence: str) -> str:
        """Request a refund after gathering evidence."""
        return support_tools.dump_json(support_tools.request_refund(order_id, amount_cents, reason, evidence))

    @function_tool
    def apply_credit(customer_id: str, amount_cents: int, reason: str) -> str:
        """Apply a goodwill store credit within policy limits."""
        return support_tools.dump_json(support_tools.apply_credit(customer_id, amount_cents, reason))

    @function_tool
    def escalate_to_human(
        reason: str,
        evidence: str,
        customer_id: str | None = None,
        order_id: str | None = None,
    ) -> str:
        """Escalate to a human support queue with gathered evidence."""
        return support_tools.dump_json(support_tools.escalate_to_human(reason, evidence, customer_id, order_id))

    return Agent(
        name="trailhead_support",
        instructions=instructions_for_customer(customer_id),
        model=model or settings().model,
        tools=[
            lookup_customer,
            lookup_order,
            check_shipment_status,
            lookup_policy,
            lookup_product,
            list_products,
            search_customer_orders,
            initiate_return,
            request_refund,
            apply_credit,
            escalate_to_human,
        ],
    )


async def run_agent(
    message: str,
    reset_db: bool = False,
    model: str | None = None,
    customer_id: str | None = None,
) -> str:
    """Run the live LLM-backed agent and return its final customer-facing output."""
    _configure_runtime()
    if reset_db:
        seed_database()
    from agents import Runner

    result = await Runner.run(build_agent(model, customer_id or settings().chat_customer_id), message)
    return str(result.final_output)


def run_agent_sync(
    message: str,
    reset_db: bool = False,
    model: str | None = None,
    customer_id: str | None = None,
) -> str:
    return asyncio.run(run_agent(message, reset_db, model, customer_id))


async def run_conversation(
    turns: list[str],
    reset_db: bool = False,
    model: str | None = None,
    customer_id: str | None = None,
) -> dict:
    """Run a multi-turn conversation and return per-turn outputs."""
    _configure_runtime()
    if reset_db:
        seed_database()
    from agents import Runner

    active_customer_id = customer_id or settings().chat_customer_id
    agent = build_agent(model, active_customer_id)
    current_input = []
    transcript = []
    result = None
    for index, customer_text in enumerate(turns, start=1):
        if result is None:
            run_input = customer_text
        else:
            current_input = result.to_input_list()
            current_input.append({"role": "user", "content": customer_text})
            run_input = current_input
        result = await Runner.run(agent, run_input)
        transcript.append(
            {
                "turn_index": index,
                "customer": customer_text,
                "agent": str(result.final_output),
                "tool_calls": [],
            }
        )
    return {
        "text": transcript[-1]["agent"] if transcript else "",
        "turns": transcript,
        "tool_calls": [],
        "metadata": {"turn_count": len(transcript), "mode": "live", "customer_id": active_customer_id},
    }


def run_conversation_sync(
    turns: list[str],
    reset_db: bool = False,
    model: str | None = None,
    customer_id: str | None = None,
) -> dict:
    return asyncio.run(run_conversation(turns, reset_db, model, customer_id))
