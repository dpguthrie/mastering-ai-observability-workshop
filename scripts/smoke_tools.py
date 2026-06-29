from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aiewf_support.db import seed_database
from aiewf_support.tools import (
    check_shipment_status,
    initiate_return,
    lookup_customer,
    lookup_order,
    request_refund,
)


def main() -> int:
    seed_database()
    checks = {
        "customer": lookup_customer("maya.chen@example.com"),
        "order": lookup_order("ord_3002"),
        "shipment": check_shipment_status("ord_3002"),
        "return": initiate_return("ord_3001", "prod_2001", "too narrow"),
        "refund_block": request_refund("ord_3002", 33483, "late", "late package"),
    }
    print(json.dumps(checks, indent=2))
    assert checks["customer"]["ok"]
    assert checks["order"]["ok"]
    assert checks["shipment"]["ok"]
    assert checks["return"]["ok"]
    assert not checks["refund_block"]["ok"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
