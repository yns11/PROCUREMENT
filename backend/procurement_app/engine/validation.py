"""Fail explicitly on invalid data; zero is a value, never a missing-data policy."""

from __future__ import annotations

import dataclasses
import datetime as dt
import math
from typing import Literal, get_args, get_origin, get_type_hints


def validate_params(params) -> None:
    types = get_type_hints(type(params))
    for key, hint in types.items():
        value = getattr(params, key)
        if get_origin(hint) is Literal and value not in get_args(hint):
            raise ValueError(f"Paramètre {key} invalide : {value}")
    bounds = {
        "horizon_days": (1, 730),
        "history_days": (0, 365),
        "frozen_days": (0, 730),
        "consumption_offset_days": (-365, 365),
        "firm_horizon_days": (0, 730),
        "proposal_lookahead_days": (0, 730),
        "stockout_lookahead_days": (0, 730),
    }
    for key, (lo, hi) in bounds.items():
        value = getattr(params, key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi):
            raise ValueError(f"{key} doit être un entier entre {lo} et {hi}")
    if (
        not params.working_weekdays
        or len(set(params.working_weekdays)) != len(params.working_weekdays)
        or any(not isinstance(x, int) or x not in range(1, 8) for x in params.working_weekdays)
    ):
        raise ValueError("Jours ouvrés uniques attendus entre 1 et 7")
    groups = [set(params.firm_sources), set(params.forecast_sources), set(params.simulated_sources)]
    # Cumulative configuration is accepted; routing uses firm, then forecast, then simulated.
    if any(g - {"FIRM", "FORECAST", "PLANNED", "PROPOSAL"} for g in groups):
        raise ValueError("Type de flux inconnu")


def validate_dataset(ds, params=None) -> None:
    specs = {
        "articles": lambda x: x.article_id,
        "suppliers": lambda x: x.supplier_id,
        "programs": lambda x: x.program_id,
        "links": lambda x: (x.article_id, x.supplier_id),
        "bom": lambda x: (x.program_id, x.article_id, x.valid_from, x.valid_to),
        "plan": lambda x: (x.program_id, x.week_start, x.version),
        "actuals": lambda x: (x.program_id, x.date),
        "orders": lambda x: x.order_id,
        "receipts": lambda x: x.receipt_id,
        "movements": lambda x: x.movement_id,
        "stock": lambda x: x.article_id,
    }
    for name, key in specs.items():
        rows = getattr(ds, name)
        if len(rows) > 100000:
            raise ValueError(f"Trop de lignes : {name}")
        keys = [key(r) for r in rows]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Clés dupliquées : {name}")
        for row in rows:
            for f in dataclasses.fields(row):
                value = getattr(row, f.name)
                if isinstance(value, float) and (not math.isfinite(value) or abs(value) > 1e12):
                    raise ValueError(f"Quantité non finie ou excessive : {name}.{f.name}")
    arts = {a.article_id: a for a in ds.articles}
    sups = {s.supplier_id: s for s in ds.suppliers}
    programs = {p.program_id for p in ds.programs}
    for a in ds.articles:
        if (
            not a.article_id
            or not a.unit
            or not 0 <= a.alert_red_days <= a.alert_yellow_days <= a.overstock_days <= 730
        ):
            raise ValueError(f"Référence, unité ou seuils invalides : {a.article_id}")
        if not 0 <= a.coverage_target_days <= 365 or not 0 <= a.order_cycle_days <= 365 or a.safety_stock_qty < 0:
            raise ValueError(f"Politique de stock invalide : {a.article_id}")
        if a.lot_policy not in ("coverage", "poq", "fixed_lot") or a.fixed_lot_qty < 0:
            raise ValueError("Politique de lot invalide")
    for s in ds.suppliers:
        if not s.delivery_weekdays or any(x not in range(1, 8) for x in s.delivery_weekdays):
            raise ValueError(f"Calendrier fournisseur invalide : {s.supplier_id}")
    for l in ds.links:
        if l.article_id not in arts or l.supplier_id not in sups:
            raise ValueError("Lien article/fournisseur orphelin")
        if min(l.moq, l.pack_qty, l.lead_time_days, l.quota_pct) < 0 or l.lead_time_days > 365 or l.quota_pct > 100:
            raise ValueError("MOQ, multiple, délai ou quota invalide")
    for b in ds.bom:
        if b.article_id not in arts or b.program_id not in programs or b.qty_per <= 0 or not 0 <= b.scrap_pct <= 100:
            raise ValueError("Nomenclature invalide")
        if b.unit.upper() != arts[b.article_id].unit.upper():
            raise ValueError(f"Conversion d'unité requise : {b.article_id}")
        if b.valid_from and b.valid_to and b.valid_from > b.valid_to:
            raise ValueError("Validité de nomenclature inversée")
    for row in [*ds.plan, *ds.actuals]:
        if row.program_id not in programs or row.qty < 0:
            raise ValueError("PDP/réalisé invalide")
    for row in ds.plan:
        if not isinstance(row.week_start, dt.date) or row.week_start.weekday() != 0:
            raise ValueError("Le PDP exige un lundi ISO")
    orders = {o.order_id: o for o in ds.orders}
    for o in ds.orders:
        if (
            o.article_id not in arts
            or o.supplier_id not in sups
            or o.qty_ordered < 0
            or not 0 <= o.qty_received <= o.qty_ordered
        ):
            raise ValueError(f"Commande invalide : {o.order_id}")
        if not isinstance(o.expected_date, dt.date):
            raise ValueError("Date de commande manquante")
    for r in [*ds.receipts, *ds.movements, *ds.cells, *ds.stock]:
        if r.article_id not in arts:
            raise ValueError("Flux sur article inconnu")
    for r in ds.receipts:
        if r.qty < 0 or (r.order_id and r.order_id in orders and orders[r.order_id].article_id != r.article_id):
            raise ValueError("Réception incohérente")
    for s in ds.stock:
        if not isinstance(s.snapshot_date, dt.date) or s.qty_blocked < 0 or s.qty_blocked > max(0, s.qty_on_hand):
            raise ValueError("Stock bloqué/snapshot invalide")
    if params and len(ds.articles) * (params.horizon_days + params.history_days + 2 * 365) > 2000000:
        raise ValueError("Calcul trop volumineux : réduire le portefeuille ou l'horizon")


def known_through(ds, params, start, end, calendar):
    """Last continuous known demand day by article; missing future coverage is censored."""
    plans = {(p.program_id, p.week_start) for p in ds.plan}
    actuals = {(a.program_id, a.date) for a in ds.actuals}
    through = {}
    for pid in {b.program_id for b in ds.bom}:
        d = start
        while d <= end:
            if calendar.is_working_day(d):
                actual = (pid, d) in actuals
                plan = (pid, d - dt.timedelta(days=d.weekday())) in plans
                known = (
                    actual
                    if params.production_mode == "actual_only"
                    else plan
                    if params.production_mode == "plan_only"
                    else actual or plan
                )
                if not known:
                    break
            d += dt.timedelta(days=1)
        through[pid] = d - dt.timedelta(days=1)
    return {
        a.article_id: min((through[b.program_id] for b in ds.bom if b.article_id == a.article_id), default=end)
        for a in ds.articles
    }
