"""Databricks port binding; the trusted Databricks proxy supplies user identity."""

import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
if __name__ == "__main__":
    uvicorn.run(
        "procurement_app.api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("DATABRICKS_APP_PORT", "8000")),
        proxy_headers=False,
    )
