"""Run with the schema owner once. The production app requires DML only."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from procurement_app.config import get_settings
from procurement_app.data.store import init_store

if __name__ == "__main__":
    init_store(get_settings().resolved_db_url, initialize=True)
    print("Schéma PROCUREMENT V2 initialisé")
