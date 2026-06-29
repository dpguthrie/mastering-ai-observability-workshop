from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import ROOT, settings

DEFAULT_SEED_PATH = ROOT / "data" / "seed.json"


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
DROP TABLE IF EXISTS escalations;
DROP TABLE IF EXISTS refunds;
DROP TABLE IF EXISTS returns;
DROP TABLE IF EXISTS credits;
DROP TABLE IF EXISTS shipments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS policies;

CREATE TABLE customers (
  customer_id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  loyalty_tier TEXT NOT NULL,
  account_state TEXT NOT NULL,
  region TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE products (
  product_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  return_window_days INTEGER NOT NULL,
  hazmat INTEGER NOT NULL DEFAULT 0,
  final_sale INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE orders (
  order_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  placed_at TEXT NOT NULL,
  status TEXT NOT NULL,
  subtotal_cents INTEGER NOT NULL,
  shipping_cents INTEGER NOT NULL,
  tax_cents INTEGER NOT NULL,
  payment_state TEXT NOT NULL,
  risk_flag TEXT,
  delivery_promise TEXT
);

CREATE TABLE order_items (
  order_item_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES orders(order_id),
  product_id TEXT NOT NULL REFERENCES products(product_id),
  quantity INTEGER NOT NULL,
  unit_price_cents INTEGER NOT NULL
);

CREATE TABLE shipments (
  shipment_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES orders(order_id),
  carrier TEXT NOT NULL,
  tracking_number TEXT NOT NULL,
  status TEXT NOT NULL,
  shipped_at TEXT,
  estimated_delivery TEXT,
  delivered_at TEXT,
  last_scan TEXT NOT NULL,
  exception_reason TEXT
);

CREATE TABLE returns (
  return_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES orders(order_id),
  product_id TEXT NOT NULL REFERENCES products(product_id),
  status TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  disposition TEXT NOT NULL
);

CREATE TABLE refunds (
  refund_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES orders(order_id),
  amount_cents INTEGER NOT NULL,
  status TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE credits (
  credit_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  amount_cents INTEGER NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE escalations (
  escalation_id TEXT PRIMARY KEY,
  customer_id TEXT REFERENCES customers(customer_id),
  order_id TEXT REFERENCES orders(order_id),
  reason TEXT NOT NULL,
  evidence TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE policies (
  policy_key TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  body TEXT NOT NULL
);
"""


TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "customers": ("customer_id", "email", "name", "loyalty_tier", "account_state", "region", "notes"),
    "products": (
        "product_id",
        "name",
        "category",
        "price_cents",
        "return_window_days",
        "hazmat",
        "final_sale",
    ),
    "orders": (
        "order_id",
        "customer_id",
        "placed_at",
        "status",
        "subtotal_cents",
        "shipping_cents",
        "tax_cents",
        "payment_state",
        "risk_flag",
        "delivery_promise",
    ),
    "order_items": ("order_item_id", "order_id", "product_id", "quantity", "unit_price_cents"),
    "shipments": (
        "shipment_id",
        "order_id",
        "carrier",
        "tracking_number",
        "status",
        "shipped_at",
        "estimated_delivery",
        "delivered_at",
        "last_scan",
        "exception_reason",
    ),
    "returns": ("return_id", "order_id", "product_id", "status", "reason", "created_at", "disposition"),
    "refunds": ("refund_id", "order_id", "amount_cents", "status", "reason", "created_at"),
    "credits": ("credit_id", "customer_id", "amount_cents", "reason", "created_at", "expires_at"),
    "escalations": ("escalation_id", "customer_id", "order_id", "reason", "evidence", "created_at", "status"),
    "policies": ("policy_key", "title", "body"),
}

INSERT_ORDER = (
    "customers",
    "products",
    "orders",
    "order_items",
    "shipments",
    "returns",
    "refunds",
    "credits",
    "escalations",
    "policies",
)


def load_seed_data(seed_path: Path | str | None = None) -> dict[str, list[dict[str, Any]]]:
    path = Path(seed_path) if seed_path else DEFAULT_SEED_PATH
    raw = json.loads(path.read_text())
    tables = raw.get("tables", {})
    if not isinstance(tables, dict):
        raise ValueError(f"Seed file {path} must contain a 'tables' object.")
    seed_data: dict[str, list[dict[str, Any]]] = {}
    for table in INSERT_ORDER:
        rows = tables.get(table, [])
        if not isinstance(rows, list):
            raise ValueError(f"Seed table {table!r} must be a list.")
        columns = set(TABLE_COLUMNS[table])
        normalized_rows: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"Seed row {table}[{index}] must be an object.")
            unknown = set(row) - columns
            missing = columns - set(row)
            if unknown:
                raise ValueError(f"Seed row {table}[{index}] has unknown columns: {sorted(unknown)}")
            if missing:
                raise ValueError(f"Seed row {table}[{index}] is missing columns: {sorted(missing)}")
            normalized_rows.append(row)
        seed_data[table] = normalized_rows
    return seed_data


def insert_seed_data(conn: sqlite3.Connection, seed_data: dict[str, list[dict[str, Any]]]) -> None:
    for table in INSERT_ORDER:
        columns = TABLE_COLUMNS[table]
        rows = seed_data.get(table, [])
        if not rows:
            continue
        column_sql = ", ".join(columns)
        placeholder_sql = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholder_sql})",
            ([row[column] for column in columns] for row in rows),
        )


def database_is_seeded(db_path: Path | str | None = None) -> bool:
    path = Path(db_path) if db_path else settings().db_path
    if not path.exists():
        return False
    try:
        with connect(path) as conn:
            for table in ("customers", "products", "orders", "order_items", "shipments", "policies"):
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table,),
                ).fetchone()
                if row is None:
                    return False
                count = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
                if count == 0:
                    return False
    except sqlite3.Error:
        return False
    return True


def ensure_database(
    db_path: Path | str | None = None,
    seed_path: Path | str | None = None,
    *,
    reset: bool = False,
) -> Path:
    path = Path(db_path) if db_path else settings().db_path
    if reset or not database_is_seeded(path):
        return seed_database(path, seed_path)
    return path


def seed_database(
    db_path: Path | str | None = None,
    seed_path: Path | str | None = None,
) -> Path:
    path = Path(db_path) if db_path else settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        insert_seed_data(conn, load_seed_data(seed_path))
        conn.commit()
    finally:
        conn.close()
    return path


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def query_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(sql, params).fetchone())


def query_all(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]
