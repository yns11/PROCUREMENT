"""Generate entirely synthetic canonical data; never publish the operational workbook."""

import csv
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from procurement_app.data.schemas import TABLES  # noqa: E402

rows = {name: [] for name in TABLES}
start = dt.date(2026, 9, 21)
for i, name in enumerate(
    [
        "Vis de fixation",
        "Support moteur",
        "Joint étanche",
        "Câble de connexion",
        "Résine technique",
        "Rondelle acier",
        "Boîtier injecté",
        "Clip de maintien",
    ],
    1,
):
    aid = f"DEMO-{i:03}"
    rows["ref_articles"].append(
        dict(
            article_id=aid,
            designation=name,
            unit="KG" if i == 5 else "PCE",
            family="Matière" if i == 5 else "Composant",
            planner="Équipe Démo",
            coverage_target_days=7,
            alert_red_days=3,
            alert_yellow_days=7,
            overstock_days=30,
            safety_stock_qty=20,
            service_rate_tracked=True,
            active=True,
        )
    )
    rows["ref_article_suppliers"].append(
        dict(
            article_id=aid,
            supplier_id=f"SUP-{1 + (i % 2)}",
            moq=50,
            pack_qty=10,
            lead_time_days=3 + i % 3,
            quota_pct=100,
            priority=1,
            active=True,
        )
    )
    rows["ref_bom"].append(
        dict(
            program_id="VEH-A",
            article_id=aid,
            qty_per=0.25 if i == 5 else 1 + i % 3,
            unit="KG" if i == 5 else "PCE",
            scrap_pct=0,
        )
    )
    rows["fct_stock"].append(
        dict(
            article_id=aid,
            snapshot_date=start - dt.timedelta(days=1),
            qty_on_hand=[25, 500, 3500, 50, 600, 200, 450, 1200][i - 1],
            qty_blocked=0,
            unit="KG" if i == 5 else "PCE",
            location="DEMO",
        )
    )
    rows["fct_purchase_orders"].append(
        dict(
            order_id=f"ERP-DEMO-{i}",
            line_no=1,
            article_id=aid,
            supplier_id=f"SUP-{1 + (i % 2)}",
            order_type="FIRM" if i % 2 else "FORECAST",
            message_type="DELJIT" if i % 2 else "DELFOR",
            order_date=start - dt.timedelta(days=12),
            expected_date=start + dt.timedelta(days=(i - 2) * 3),
            qty_ordered=500,
            qty_received=0,
            status="OPEN",
            unit="KG" if i == 5 else "PCE",
        )
    )
for i in (1, 2):
    rows["ref_suppliers"].append(
        dict(
            supplier_id=f"SUP-{i}",
            name=f"Fournisseur Démo {i}",
            country="FR",
            contact="",
            delivery_weekdays="1,2,3,4,5",
            calendar_id="DEFAULT",
            active=True,
        )
    )
rows["ref_programs"].append(
    dict(program_id="VEH-A", name="Véhicule Démo A", family="Automobile", has_bom=True, active=True)
)
for week in range(-4, 110):
    date = start + dt.timedelta(weeks=week)
    rows["fct_production_plan"].append(
        dict(
            program_id="VEH-A",
            week_start=date,
            iso_week=f"{date.isocalendar().year}-W{date.isocalendar().week:02}",
            qty=250 + (week % 4) * 25,
            version="DEMO-1",
            published_at=start,
        )
    )
folder = ROOT / "data/seed"
folder.mkdir(parents=True, exist_ok=True)
for name, schema in TABLES.items():
    with (folder / f"{name}.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=schema.columns, lineterminator="\n")
        writer.writeheader()
        for row in rows[name]:
            writer.writerow({k: row.get(k, "") for k in schema.columns})
