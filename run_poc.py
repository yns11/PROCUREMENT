"""Standalone, reproducible POC; separate database and fixed demonstration date."""

import os
import runpy
from pathlib import Path

root = Path(__file__).resolve().parent
for key, value in {
    "PROCUREMENT_POC": "true",
    "PROCUREMENT_MODE": "demo",
    "PROCUREMENT_DATA_SOURCE": "local",
    "PROCUREMENT_AS_OF": "2026-09-21",
    "PROCUREMENT_HORIZON_DAYS": "60",
    "PROCUREMENT_HISTORY_DAYS": "0",
}.items():
    os.environ.setdefault(key, value)
if os.environ["PROCUREMENT_MODE"] != "demo":
    raise RuntimeError("Le lanceur POC exige PROCUREMENT_MODE=demo")
if not os.environ.get("PGHOST"):
    folder = root / "data/local"
    folder.mkdir(exist_ok=True, parents=True)
    os.environ.setdefault("PROCUREMENT_DB_URL", "sqlite:///" + str(folder / "poc-management.db"))
runpy.run_path(str(root / "run.py"), run_name="__main__")
