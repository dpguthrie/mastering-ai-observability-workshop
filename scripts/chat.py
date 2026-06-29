from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aiewf_support.agent import run_agent_sync
from aiewf_support.db import seed_database


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("message", nargs="+")
    parser.add_argument("--customer-id")
    parser.add_argument("--model")
    parser.add_argument("--reset-db", action="store_true")
    args = parser.parse_args()
    if args.reset_db:
        seed_database()
    print(run_agent_sync(" ".join(args.message), model=args.model, customer_id=args.customer_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
