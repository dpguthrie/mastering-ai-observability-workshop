from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .db import connect, query_all, query_one


def _now() -> str:
    return datetime.now(UTC).date().isoformat()


def _money(cents: int) -> str:
    return f"${cents / 100:.2f}"


def _result(ok: bool, **payload: Any) -> dict[str, Any]:
    return {"ok": ok, **payload}


def lookup_customer(identifier: str, db_path: Path | str | None = None) -> dict[str, Any]:
    """Look up a customer by customer ID or email."""
    with connect(db_path) as conn:
        customer = query_one(
            conn,
            "SELECT * FROM customers WHERE customer_id = ? OR lower(email) = lower(?)",
            (identifier, identifier),
        )
        if not customer:
            return _result(False, error="customer_not_found", identifier=identifier)
        orders = query_all(
            conn,
            "SELECT order_id, placed_at, status, payment_state, risk_flag FROM orders "
            "WHERE customer_id = ? ORDER BY placed_at DESC",
            (customer["customer_id"],),
        )
        return _result(True, customer=customer, recent_orders=orders)


def list_customers(db_path: Path | str | None = None) -> dict[str, Any]:
    """List seeded demo customers for the local chat UI."""
    with connect(db_path) as conn:
        customers = query_all(
            conn,
            "SELECT customer_id, name, email, loyalty_tier, account_state, region FROM customers ORDER BY customer_id",
        )
        return _result(True, customers=customers)


def lookup_order(order_id: str, db_path: Path | str | None = None) -> dict[str, Any]:
    """Look up order, item, customer, and shipment details."""
    with connect(db_path) as conn:
        order = query_one(
            conn,
            "SELECT o.*, c.email, c.name, c.loyalty_tier, c.account_state "
            "FROM orders o JOIN customers c USING (customer_id) WHERE o.order_id = ?",
            (order_id,),
        )
        if not order:
            return _result(False, error="order_not_found", order_id=order_id)
        items = query_all(
            conn,
            "SELECT oi.order_item_id, oi.quantity, oi.unit_price_cents, p.* "
            "FROM order_items oi JOIN products p USING (product_id) WHERE oi.order_id = ?",
            (order_id,),
        )
        shipments = query_all(conn, "SELECT * FROM shipments WHERE order_id = ?", (order_id,))
        returns = query_all(conn, "SELECT * FROM returns WHERE order_id = ?", (order_id,))
        refunds = query_all(conn, "SELECT * FROM refunds WHERE order_id = ?", (order_id,))
        return _result(True, order=order, items=items, shipments=shipments, returns=returns, refunds=refunds)


def check_shipment_status(order_id: str, db_path: Path | str | None = None) -> dict[str, Any]:
    """Check shipment status and return operational guidance."""
    order_info = lookup_order(order_id, db_path)
    if not order_info["ok"]:
        return order_info
    shipments = order_info["shipments"]
    if not shipments:
        return _result(False, error="shipment_not_created", order_id=order_id)
    shipment = shipments[0]
    guidance = "provide_status"
    if shipment["status"] == "exception":
        guidance = "explain_delay_do_not_refund_without_more_evidence"
    if shipment["status"] == "delivered" and shipment["delivered_at"]:
        guidance = "confirm_delivery_details_before_reship_or_refund"
    return _result(True, shipment=shipment, guidance=guidance)


def lookup_policy(topic: str, db_path: Path | str | None = None) -> dict[str, Any]:
    """Look up policy text by topic or keyword."""
    normalized = topic.lower().strip()
    with connect(db_path) as conn:
        policy = query_one(
            conn,
            "SELECT * FROM policies WHERE lower(policy_key) = lower(?) OR lower(title) LIKE ?",
            (normalized, f"%{normalized}%"),
        )
        if not policy:
            policies = query_all(conn, "SELECT policy_key, title FROM policies ORDER BY policy_key")
            return _result(False, error="policy_not_found", available=policies)
        return _result(True, policy=policy)


def lookup_product(query: str, db_path: Path | str | None = None) -> dict[str, Any]:
    """Look up products by ID, name, category, or policy-relevant keyword."""
    normalized = query.lower().strip()
    hazmat_filter = "hazmat" in normalized or "battery" in normalized
    final_sale_filter = "final" in normalized or "outlet" in normalized
    with connect(db_path) as conn:
        products = query_all(
            conn,
            "SELECT * FROM products "
            "WHERE lower(product_id) = lower(?) "
            "OR lower(name) LIKE ? "
            "OR lower(category) LIKE ? "
            "OR (? = 1 AND hazmat = 1) "
            "OR (? = 1 AND final_sale = 1) "
            "ORDER BY name",
            (
                normalized,
                f"%{normalized}%",
                f"%{normalized}%",
                1 if hazmat_filter else 0,
                1 if final_sale_filter else 0,
            ),
        )
        if not products:
            return _result(False, error="product_not_found", query=query)
        return _result(True, products=products)


def search_customer_orders(
    identifier: str,
    query: str,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Search a customer's orders by product, category, shipment state, or order status."""
    customer_result = lookup_customer(identifier, db_path)
    if not customer_result["ok"]:
        return customer_result
    customer_id = customer_result["customer"]["customer_id"]
    normalized = query.lower().strip()
    with connect(db_path) as conn:
        rows = query_all(
            conn,
            "SELECT DISTINCT o.order_id, o.placed_at, o.status, o.payment_state, o.risk_flag, "
            "o.delivery_promise, p.product_id, p.name AS product_name, p.category, "
            "s.status AS shipment_status, s.last_scan "
            "FROM orders o "
            "JOIN order_items oi USING(order_id) "
            "JOIN products p USING(product_id) "
            "LEFT JOIN shipments s USING(order_id) "
            "WHERE o.customer_id = ? "
            "AND (lower(o.order_id) LIKE ? "
            "OR lower(o.status) LIKE ? "
            "OR lower(p.name) LIKE ? "
            "OR lower(p.category) LIKE ? "
            "OR lower(s.status) LIKE ? "
            "OR lower(s.last_scan) LIKE ?) "
            "ORDER BY o.placed_at DESC",
            (
                customer_id,
                f"%{normalized}%",
                f"%{normalized}%",
                f"%{normalized}%",
                f"%{normalized}%",
                f"%{normalized}%",
                f"%{normalized}%",
            ),
        )
        if not rows:
            return _result(False, error="orders_not_found", customer=customer_result["customer"], query=query)
        return _result(True, customer=customer_result["customer"], matches=rows)


def initiate_return(
    order_id: str,
    product_id: str,
    reason: str,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Initiate a return if the item is eligible."""
    with connect(db_path) as conn:
        order = query_one(conn, "SELECT * FROM orders WHERE order_id = ?", (order_id,))
        item = query_one(
            conn,
            "SELECT p.*, oi.quantity FROM order_items oi JOIN products p USING(product_id) "
            "WHERE oi.order_id = ? AND oi.product_id = ?",
            (order_id, product_id),
        )
        if not order or not item:
            return _result(False, error="order_or_item_not_found", order_id=order_id, product_id=product_id)
        if order["payment_state"] != "captured":
            return _result(False, error="payment_not_captured", policy="refunds")
        if order["risk_flag"]:
            return _result(False, error="manual_review_required", risk_flag=order["risk_flag"])
        if item["final_sale"]:
            return _result(False, error="final_sale_not_returnable", product_id=product_id)
        if item["hazmat"]:
            return _result(False, error="hazmat_manual_review_required", product_id=product_id)
        return_id = f"ret_{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO returns VALUES (?, ?, ?, ?, ?, ?, ?)",
            (return_id, order_id, product_id, "authorized", reason, _now(), "customer_ship_back"),
        )
        conn.commit()
        return _result(True, return_id=return_id, status="authorized", next_step="send_return_label")


def request_refund(
    order_id: str,
    amount_cents: int,
    reason: str,
    evidence: str,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Request a refund after checking payment, risk, and evidence constraints."""
    with connect(db_path) as conn:
        order = query_one(conn, "SELECT * FROM orders WHERE order_id = ?", (order_id,))
        if not order:
            return _result(False, error="order_not_found", order_id=order_id)
        if order["payment_state"] != "captured":
            return _result(False, error="payment_not_captured", order_id=order_id)
        if order["risk_flag"]:
            return _result(False, error="manual_review_required", risk_flag=order["risk_flag"])
        if not evidence or len(evidence.strip()) < 20:
            return _result(False, error="insufficient_evidence_before_refund")
        max_amount = order["subtotal_cents"] + order["shipping_cents"] + order["tax_cents"]
        if amount_cents > max_amount:
            return _result(False, error="refund_exceeds_order_total", max_refund=_money(max_amount))
        refund_id = f"ref_{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO refunds VALUES (?, ?, ?, ?, ?, ?)",
            (refund_id, order_id, amount_cents, "requested", reason, _now()),
        )
        conn.commit()
        return _result(True, refund_id=refund_id, status="requested", amount=_money(amount_cents))


def apply_credit(
    customer_id: str,
    amount_cents: int,
    reason: str,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Apply a goodwill store credit within policy limits."""
    with connect(db_path) as conn:
        customer = query_one(conn, "SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
        if not customer:
            return _result(False, error="customer_not_found", customer_id=customer_id)
        if customer["account_state"] != "active":
            return _result(False, error="account_not_active", account_state=customer["account_state"])
        if amount_cents > 1500:
            return _result(False, error="credit_exceeds_agent_limit", max_credit="$15.00")
        credit_id = f"cred_{uuid.uuid4().hex[:8]}"
        expires_at = (datetime.now(UTC).date() + timedelta(days=180)).isoformat()
        conn.execute(
            "INSERT INTO credits VALUES (?, ?, ?, ?, ?, ?)",
            (credit_id, customer_id, amount_cents, reason, _now(), expires_at),
        )
        conn.commit()
        return _result(True, credit_id=credit_id, amount=_money(amount_cents), expires_at=expires_at)


def escalate_to_human(
    reason: str,
    evidence: str,
    customer_id: str | None = None,
    order_id: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Escalate to a human support queue with explicit evidence."""
    if not evidence or len(evidence.strip()) < 25:
        return _result(False, error="evidence_required_before_escalation")
    escalation_id = f"esc_{uuid.uuid4().hex[:8]}"
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO escalations VALUES (?, ?, ?, ?, ?, ?, ?)",
            (escalation_id, customer_id, order_id, reason, evidence, _now(), "open"),
        )
        conn.commit()
    return _result(True, escalation_id=escalation_id, status="open")


def list_products(db_path: Path | str | None = None) -> dict[str, Any]:
    """List products and return eligibility flags."""
    with connect(db_path) as conn:
        products = query_all(
            conn,
            "SELECT product_id, name, category, return_window_days, hazmat, final_sale FROM products",
        )
        return _result(True, products=products)


def dump_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True)
