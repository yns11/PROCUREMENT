"""POC input contracts, canonical adapter and reversible firm/simulation reconciliation.

Inputs live in the isolated app database. No ERP table is written. Forecast delivery
 dates are normalized before persistence; firm dates remain exact.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, model_validator
from sqlalchemy import select

from .schemas import TABLES, coerce
from .sources import FrozenSource
from .store import AppCell, PocWorkspace

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Quantity = Annotated[float, Field(ge=0, le=1e9, allow_inf_nan=False)]
DAY = dt.date(2026, 9, 21)
FIXTURE = Path(__file__).resolve().parents[3] / "data/poc/presentation.json"


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArticleInput(Input):
    article_id: Code
    designation: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    unit: Annotated[str, StringConstraints(min_length=1, max_length=10)] = "PCE"
    stock_initial: Quantity = 0
    coverage_target_days: int = Field(5, ge=0, le=365)
    safety_stock_qty: Quantity = 0
    supplier_id: Code = "FOURN-01"
    moq: Quantity = 0
    pack_qty: Quantity = 1
    lead_time_days: int = Field(0, ge=0, le=365)


class BomInput(Input):
    program_id: Code
    article_id: Code
    qty_per: float = Field(gt=0, le=1e6, allow_inf_nan=False)


class PlanInput(Input):
    program_id: Code
    week_start: dt.date
    qty: Quantity

    @model_validator(mode="after")
    def normalize(self):
        self.week_start = monday(self.week_start)
        return self


class OrderInput(Input):
    order_id: Code
    article_id: Code
    supplier_id: Code
    expected_date: dt.date
    qty: Quantity
    order_type: Literal["FIRM", "FORECAST"]
    note: Annotated[str, StringConstraints(max_length=500)] = ""

    @model_validator(mode="after")
    def normalize(self):
        if self.order_type == "FORECAST":
            self.expected_date = monday(self.expected_date)
        return self


MODELS = {"articles": ArticleInput, "bom": BomInput, "pdp": PlanInput, "orders": OrderInput}
KEYS = {
    "articles": ("article_id",),
    "bom": ("program_id", "article_id"),
    "pdp": ("program_id", "week_start"),
    "orders": ("order_id",),
}
LABELS = {
    "note": "Commentaire",
    "article_id": "Article",
    "designation": "Désignation",
    "unit": "Unité",
    "stock_initial": "Stock initial",
    "coverage_target_days": "Couverture cible (j)",
    "safety_stock_qty": "Stock de sécurité",
    "supplier_id": "Fournisseur",
    "moq": "MOQ",
    "pack_qty": "Conditionnement",
    "lead_time_days": "Délai (j ouvrés)",
    "program_id": "Programme",
    "qty_per": "Quantité par produit",
    "week_start": "Lundi",
    "qty": "Quantité",
    "order_id": "Commande",
    "expected_date": "Livraison",
    "order_type": "Nature",
}


def monday(day):
    return day - dt.timedelta(days=day.weekday())


def validate_rows(table, rows):
    if table not in MODELS:
        raise ValueError("Table inconnue")
    if len(rows) > 2000:
        raise ValueError("Maximum 2 000 lignes par table")
    values = TypeAdapter(list[MODELS[table]]).validate_python(rows)
    out = [v.model_dump(mode="json") for v in values]
    keys = [tuple(r[k] for k in KEYS[table]) for r in out]
    if len(keys) != len(set(keys)):
        raise ValueError("Clés dupliquées après normalisation des dates")
    return out


def demo_tables():
    raw = json.loads(FIXTURE.read_text())
    return {name: validate_rows(name, rows) for name, rows in raw.items()}


def read_tables(session):
    row = session.get(PocWorkspace, 1)
    return json.loads(row.tables_json) if row else demo_tables()


def canonical(tables, as_of=DAY):
    """Map the four small management-facing input tables to the shared ERP contract."""
    records = {name: [] for name in TABLES}
    articles = {r["article_id"]: r for r in tables["articles"]}
    suppliers = {r["supplier_id"] for r in tables["articles"]} | {r["supplier_id"] for r in tables["orders"]}
    programs = {r["program_id"] for r in tables["bom"]} | {r["program_id"] for r in tables["pdp"]}
    for a in tables["articles"]:
        records["ref_articles"].append(
            dict(
                article_id=a["article_id"],
                designation=a["designation"],
                unit=a["unit"],
                family="POC",
                planner="",
                coverage_target_days=a["coverage_target_days"],
                alert_red_days=2,
                alert_yellow_days=5,
                overstock_days=30,
                safety_stock_qty=a["safety_stock_qty"],
                service_rate_tracked=False,
                dhrq="",
                active=True,
            )
        )
        records["ref_article_suppliers"].append(
            dict(
                article_id=a["article_id"],
                supplier_id=a["supplier_id"],
                moq=a["moq"],
                pack_qty=a["pack_qty"],
                lead_time_days=a["lead_time_days"],
                quota_pct=100,
                priority=1,
                active=True,
            )
        )
        records["fct_stock"].append(
            dict(
                article_id=a["article_id"],
                snapshot_date=as_of - dt.timedelta(days=1),
                qty_on_hand=a["stock_initial"],
                qty_blocked=0,
                unit=a["unit"],
                location="POC",
            )
        )
    records["ref_suppliers"] = [
        dict(supplier_id=s, name=s, country="", contact="", delivery_weekdays="1", calendar_id="POC-LUNDI", active=True)
        for s in sorted(suppliers)
    ]
    records["ref_programs"] = [
        dict(program_id=p, name=p, family="POC", has_bom=True, active=True) for p in sorted(programs)
    ]
    for r in tables["bom"]:
        if r["article_id"] not in articles:
            raise ValueError(f"Nomenclature : article inconnu {r['article_id']}")
        records["ref_bom"].append(
            r | dict(unit=articles[r["article_id"]]["unit"], scrap_pct=0, valid_from=None, valid_to=None)
        )
    for r in tables["pdp"]:
        records["fct_production_plan"].append(r | dict(iso_week="", version="POC", published_at=as_of))
    for r in tables["orders"]:
        if r["article_id"] not in articles:
            raise ValueError(f"Commande : article inconnu {r['article_id']}")
        records["fct_purchase_orders"].append(
            dict(
                order_id=r["order_id"],
                line_no=1,
                article_id=r["article_id"],
                supplier_id=r["supplier_id"],
                order_type=r["order_type"],
                message_type="POC",
                order_date=None,
                expected_date=r["expected_date"],
                qty_ordered=r["qty"],
                qty_received=0,
                status="OPEN",
                unit=articles[r["article_id"]]["unit"],
            )
        )
    frames = {
        name: coerce(pd.DataFrame(rows, columns=list(TABLES[name].columns)), TABLES[name])
        for name, rows in records.items()
    }
    return FrozenSource("poc", frames)


class PocSource:
    name = "poc"

    def __init__(self, factory, as_of=None):
        self.factory, self.as_of = factory, as_of or DAY

    def with_session(self, session):
        return canonical(read_tables(session), self.as_of)

    def snapshot(self):
        with self.factory() as session:
            return self.with_session(session)

    def table(self, name):
        return self.snapshot().table(name)

    def refresh(self):
        pass

    def describe(self):
        return {"name": "Données POC"}


def firm_totals(ds):
    totals = defaultdict(float)
    for order in ds.orders:
        if order.order_type.value == "FIRM":
            totals[order.article_id, order.expected_date] += order.qty_open
    return totals


def effective_cells(ds, rows):
    """Allocate new firm supply once to eligible cells; retain originals for reversal.

    Each cell remembers firm quantity existing at its creation. Firm additions above
    that baseline absorb only positive simulated quantity at that same article/day.
    Descending baselines allocate the most restrictive intervals first.
    """
    firms, grouped = firm_totals(ds), defaultdict(list)
    effective = {r.id: r.qty for r in rows}
    for r in rows:
        if r.kind == "sim_order" and r.qty > 0 and r.firm_baseline is not None and not r.scenario_id:
            grouped[r.article_id, r.date].append(r)
    for key, cells in grouped.items():
        upper = firms.get(key, 0)
        for r in sorted(cells, key=lambda r: (-r.firm_baseline, r.source != "CBN", r.id)):
            consumed = min(r.qty, max(0, upper - r.firm_baseline))
            effective[r.id] = r.qty - consumed
            upper -= consumed
    return effective


def reconcile_cells(ds, session):
    rows = list(session.scalars(select(AppCell).where(AppCell.scenario_id == "")))
    effective = effective_cells(ds, rows)
    qty = {(r.article_id, r.date, r.kind, r.source): effective[r.id] for r in rows}
    for cell in ds.cells:
        key = (cell.article_id, cell.date, cell.kind, cell.source)
        if key in qty:
            cell.qty = qty[key]
