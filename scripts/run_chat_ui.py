from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv

from aiewf_support.config import ROOT


def main() -> int:
    load_dotenv(ROOT / ".env")
    port = int(os.getenv("PORT", "8765"))
    uvicorn.run(
        "aiewf_support.web.app:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
