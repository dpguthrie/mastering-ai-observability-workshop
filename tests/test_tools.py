from __future__ import annotations

from pathlib import Path

from aiewf_support.db import database_is_seeded, load_seed_data, seed_database
from aiewf_support.tools import (
    apply_credit,
    check_shipment_status,
    initiate_return,
    list_customers,
    lookup_customer,
    lookup_order,
    lookup_product,
    request_refund,
    search_customer_orders,
)


def test_seed_and_lookup(tmp_path: Path) -> None:
    db_path = tmp_path / "workshop.db"
    seed_database(db_path)
    assert database_is_seeded(db_path)
    customer = lookup_customer("maya.chen@example.com", db_path)
    assert customer["ok"]
    assert customer["customer"]["customer_id"] == "cus_1001"
    order = lookup_order("ord_3002", db_path)
    assert order["ok"]
    assert len(order["items"]) == 2


def test_list_customers_for_demo_picker(tmp_path: Path) -> None:
    db_path = tmp_path / "workshop.db"
    seed_database(db_path)

    result = list_customers(db_path)

    assert result["ok"]
    customer_ids = {customer["customer_id"] for customer in result["customers"]}
    assert customer_ids >= {
        "cus_1001",
        "cus_1002",
        "cus_1003",
        "cus_1004",
    }
    assert len(customer_ids) >= 10


def test_shipment_exception_blocks_unsupported_refund(tmp_path: Path) -> None:
    db_path = tmp_path / "workshop.db"
    seed_database(db_path)
    shipment = check_shipment_status("ord_3002", db_path)
    assert shipment["ok"]
    assert shipment["shipment"]["status"] == "exception"
    refund = request_refund("ord_3002", 33483, "late", "late package", db_path)
    assert not refund["ok"]
    assert refund["error"] == "insufficient_evidence_before_refund"


def test_return_boundaries(tmp_path: Path) -> None:
    db_path = tmp_path / "workshop.db"
    seed_database(db_path)
    allowed = initiate_return("ord_3001", "prod_2001", "too narrow", db_path)
    assert allowed["ok"]
    final_sale = initiate_return("ord_3003", "prod_2004", "changed mind", db_path)
    assert not final_sale["ok"]
    assert final_sale["error"] == "final_sale_not_returnable"
    hazmat = initiate_return("ord_3005", "prod_2005", "unopened", db_path)
    assert not hazmat["ok"]
    assert hazmat["error"] == "hazmat_manual_review_required"


def test_credit_limit(tmp_path: Path) -> None:
    db_path = tmp_path / "workshop.db"
    seed_database(db_path)
    too_high = apply_credit("cus_1002", 4000, "late shipment", db_path)
    assert not too_high["ok"]
    assert too_high["error"] == "credit_exceeds_agent_limit"
    allowed = apply_credit("cus_1002", 1500, "late shipment", db_path)
    assert allowed["ok"]


def test_product_lookup_and_order_search(tmp_path: Path) -> None:
    db_path = tmp_path / "workshop.db"
    seed_database(db_path)
    battery = lookup_product("battery", db_path)
    assert battery["ok"]
    assert battery["products"][0]["hazmat"] == 1
    outlet = lookup_product("final sale", db_path)
    assert outlet["ok"]
    assert outlet["products"][0]["final_sale"] == 1
    rain_shell = search_customer_orders("devon.ross@example.com", "rain shell", db_path)
    assert rain_shell["ok"]
    assert rain_shell["matches"][0]["order_id"] == "ord_3002"


def test_seed_fixture_contains_expanded_demo_data() -> None:
    seed = load_seed_data()

    assert len(seed["customers"]) >= 10
    assert len(seed["products"]) >= 12
    assert len(seed["orders"]) >= 15
    assert any(policy["policy_key"] == "identity" for policy in seed["policies"])
