"""Portfolio-level orchestration of the MRP engine."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

import numpy as np

from .alerts import classify_alerts, worst_severity
from .calendar import WorkCalendar
from .demand import DayIndex, actual_share, build_program_daily, explode_demand
from .models import (
    Alert,
    AlertType,
    ArticleResult,
    Dataset,
    EngineParams,
    MrpResult,
    OrderLine,
    OrderType,
    Severity,
    SupplyEvent,
)
from .projection import Projection, coverage_days, first_shortage, project_stock, target_stock
from .proposals import generate_proposals


def resolve_as_of(dataset: Dataset, params: EngineParams) -> dt.date:
    if params.as_of:
        return params.as_of
    if dataset.stock:
        return max(s.snapshot_date for s in dataset.stock) + dt.timedelta(days=1)
    return dt.date.today()


def _order_is_selected(o: OrderLine, params: EngineParams) -> bool:
    if o.qty_open <= 0:
        return False
    if params.orders_source == "erp" and o.source == "APP":
        return False
    if params.orders_source == "app" and o.source == "ERP":
        return False
    return True


def run_mrp(dataset: Dataset, params: EngineParams | None = None, article_ids: list[str] | None = None) -> MrpResult:
    """Run the full computation for the articles of the dataset (or a subset)."""
    params = params or EngineParams()
    from .validation import validate_params

    validate_params(params)
    calendar = WorkCalendar.from_spec(params.working_weekdays, dataset.holidays)
    as_of = resolve_as_of(dataset, params)
    snapshots = {s.article_id: s for s in dataset.stock}
    earliest_snapshot = min((s.snapshot_date for s in dataset.stock), default=as_of - dt.timedelta(days=1))
    if (as_of - earliest_snapshot).days > 365 or any(s.snapshot_date >= as_of for s in dataset.stock):
        raise ValueError("Snapshot futur ou antérieur de plus de 365 jours à la référence")
    start = min(as_of - dt.timedelta(days=max(params.history_days, 0)), earliest_snapshot)
    end = as_of + dt.timedelta(days=int(params.horizon_days))
    span = max((a.coverage_target_days + a.order_cycle_days for a in dataset.articles), default=0)
    padding = min(800, (span * 7 // len(params.working_weekdays)) + abs(params.consumption_offset_days) + 14)
    calculation_end = end + dt.timedelta(days=padding)
    index = DayIndex(start, calculation_end)
    visible_n = (end - start).days + 1
    tail_demand = {}
    diagnostics: list[str] = []

    # ---------------------------------------------------------------- demand
    program_eff, program_plan, actual_mask, diag = build_program_daily(
        dataset.plan, dataset.actuals, calendar, index, params, as_of
    )
    diagnostics.extend(diag)
    demand_eff = explode_demand(program_eff, dataset.bom, index, params.consumption_offset_days)
    demand_plan = explode_demand(program_plan, dataset.bom, index, params.consumption_offset_days)

    from .validation import known_through

    known = known_through(dataset, params, as_of, calculation_end, calendar)
    # ---------------------------------------------------------------- lookups
    links_by_article: dict[str, list] = defaultdict(list)
    for l in dataset.links:
        if l.active:
            links_by_article[l.article_id].append(l)
    suppliers = {s.supplier_id: s for s in dataset.suppliers}
    bom_articles = {b.article_id for b in dataset.bom}
    orders_by_article: dict[str, list[OrderLine]] = defaultdict(list)
    for o in dataset.orders:
        orders_by_article[o.article_id].append(o)
    receipts_by_article = defaultdict(list)
    for r in dataset.receipts:
        receipts_by_article[r.article_id].append(r)
    movements_by_article = defaultdict(list)
    for m in dataset.movements:
        movements_by_article[m.article_id].append(m)
    cells_by_article = defaultdict(list)
    for c in dataset.cells:
        cells_by_article[c.article_id].append(c)
    # App receipts posted against an order reduce its open quantity (unless the ERP already did).
    app_received: dict[str, float] = defaultdict(float)
    order_lookup = {o.order_id: o for o in dataset.orders}
    for r in dataset.receipts:
        order = order_lookup.get(r.order_id)
        snap = snapshots.get(r.article_id)
        if (
            r.source == "APP"
            and r.order_id
            and (order and order.source == "APP" or not snap or r.receipt_date > snap.snapshot_date)
        ):
            app_received[r.order_id] += r.qty

    selected = [a for a in dataset.articles if a.active and (article_ids is None or a.article_id in article_ids)]
    results: dict[str, ArticleResult] = {}
    n = index.n
    i_as_of = index.offset(as_of)
    assert i_as_of is not None

    for article in selected:
        aid = article.article_id
        notes: list[str] = []
        demand = demand_eff.get(aid, np.zeros(n))
        dplan = demand_plan.get(aid, np.zeros(n))
        share = actual_share(program_eff, actual_mask, dataset.bom, aid, index)

        snap = snapshots.get(aid)
        if snap is not None:
            i_snap = index.offset(snap.snapshot_date)
            stock_start = snap.qty_on_hand - (snap.qty_blocked or 0.0)
            if i_snap is None:
                notes.append(f"snapshot du {snap.snapshot_date} hors fenêtre : projection depuis le début de fenêtre")
                i_snap = 0
        else:
            i_snap, stock_start = 0, 0.0
        snap_date = index.dates[i_snap]

        supply_firm = np.zeros(n)
        supply_forecast = np.zeros(n)
        supply_planned = np.zeros(n)
        receipts = np.zeros(n)
        adjustments = np.zeros(n)
        events: list[SupplyEvent] = []
        late_orders: list[OrderLine] = []
        open_orders: list[OrderLine] = []

        for o in orders_by_article.get(aid, []):
            if not _order_is_selected(o, params):
                continue
            qty = o.qty_open - app_received.get(o.order_id, 0.0)
            if qty <= 1e-9:
                continue
            day = o.expected_date
            late = False
            if day < as_of:
                late = True
                if params.late_order_policy == "ignore":
                    late_orders.append(o)
                    continue
                if params.late_order_policy == "reschedule":
                    day = calendar.next_working_day(as_of, inclusive=True)
                elif day <= snap_date:
                    day = calendar.next_working_day(snap_date, inclusive=False)
                late_orders.append(o)
            i = index.offset(day)
            if i is None:
                continue
            typ = o.order_type.value
            layer_type = typ
            if o.source != "ERP" and params.app_firm_orders == "simulated":
                layer_type = "PLANNED"  # planner entries never feed the firm / forecast layers
            if layer_type in params.firm_sources:
                supply_firm[i] += qty
            elif layer_type in params.forecast_sources:
                supply_forecast[i] += qty
            elif layer_type in params.simulated_sources:
                supply_planned[i] += qty
            else:
                continue
            open_orders.append(o)
            events.append(SupplyEvent(day, "order", o.order_id, qty, o.supplier_id, typ, o.source, late))

        for r in receipts_by_article.get(aid, []):
            if r.receipt_date <= snap_date:
                continue  # already in the on-hand stock
            i = index.offset(r.receipt_date)
            if i is None:
                continue
            receipts[i] += r.qty
            events.append(
                SupplyEvent(r.receipt_date, "receipt", r.receipt_id, r.qty, r.supplier_id, "RECEIPT", r.source)
            )
        for m in movements_by_article.get(aid, []):
            if m.date <= snap_date:
                continue
            i = index.offset(m.date)
            if i is None:
                continue
            adjustments[i] += m.qty
            events.append(SupplyEvent(m.date, "movement", m.movement_id, m.qty, None, m.movement_type, m.source))
        for c in cells_by_article.get(aid, []):
            if c.date <= snap_date:
                continue
            i = index.offset(c.date)
            if i is None:
                continue
            if c.kind == "sim_order":
                supply_planned[i] += c.qty
                events.append(
                    SupplyEvent(c.date, "sim_order", f"SIM-{c.date.isoformat()}", c.qty, None, "SIMULATED", c.source)
                )
            elif c.kind == "adjustment":
                adjustments[i] += c.qty
                events.append(
                    SupplyEvent(c.date, "movement", f"ADJ-{c.date.isoformat()}", c.qty, None, "ADJUSTMENT", c.source)
                )

        # Imported Excel rows replace aggregated flows; they never create ERP transactions.
        overlay = {
            "demand": demand,
            "firm_flow": supply_firm,
            "forecast_flow": supply_forecast,
            "planned_flow": supply_planned,
            "receipt_flow": receipts,
            "adjustment_flow": adjustments,
        }
        totals = defaultdict(float)
        for c in cells_by_article.get(aid, []):
            i = index.offset(c.date)
            if c.kind in overlay and i is not None and c.date > snap_date:
                totals[(c.kind, i)] += c.qty
        for (kind, i), qty in totals.items():
            overlay[kind][i] = qty

        # zero everything before the snapshot day (unknown history)
        if i_snap > 0:
            for arr in (supply_firm, supply_forecast, supply_planned, receipts, adjustments):
                arr[:i_snap] = 0.0
        demand_proj = demand.copy()
        demand_proj[: i_snap + 1] = 0.0  # snapshot day already consumed

        # three cumulative layers: firm ⊂ forecast ⊂ simulated
        def project(supply: np.ndarray) -> Projection:
            return project_stock(stock_start, supply, adjustments, demand_proj, params.shortage_policy, i_snap)

        supply_firm_all = supply_firm + receipts
        supply_forecast_all = supply_firm_all + supply_forecast
        supply_sim_all = supply_forecast_all + supply_planned
        firm = project(supply_firm_all)
        forecast = project(supply_forecast_all)
        sim = project(supply_sim_all)
        target = target_stock(demand, article, index, calendar, params)

        proposals, supply_proposed = [], np.zeros(n)
        known_end = known.get(aid, calculation_end)
        safe_end = (
            calendar.add_working_days(known_end, -(article.coverage_target_days + article.order_cycle_days))
            if params.coverage_unit == "working"
            else known_end - dt.timedelta(days=article.coverage_target_days + article.order_cycle_days)
        )
        proposal_params = params.copy_with(
            proposal_lookahead_days=max(
                0, min(params.proposal_lookahead_days or params.horizon_days, (safe_end - as_of).days)
            )
        )
        if params.generate_proposals:
            proposals, supply_proposed, _ = generate_proposals(
                article,
                links_by_article.get(aid, []),
                suppliers,
                sim.net,
                demand,
                target,
                index,
                calendar,
                as_of,
                proposal_params,
                supply_planned=supply_forecast + supply_planned,
                reproject=lambda extra: project(supply_sim_all + extra),
            )
            if params.include_proposals_in_simulation:
                sim = project(supply_sim_all + supply_proposed)
                for p in proposals:
                    events.append(
                        SupplyEvent(
                            p.delivery_date,
                            "proposal",
                            p.proposal_id,
                            p.qty,
                            p.supplier_id,
                            "PROPOSAL",
                            "ENGINE",
                            p.urgent,
                        )
                    )
        cov = {
            name: coverage_days(layer.net, demand, index, calendar, params.coverage_unit, params.coverage_tie_rule)
            for name, layer in (("firm", firm), ("forecast", forecast), ("sim", sim))
        }

        alerts = classify_alerts(
            article,
            index,
            as_of,
            firm,
            forecast,
            sim,
            cov["sim"],
            stock_start,
            demand,
            open_orders,
            late_orders,
            proposals,
            links_by_article.get(aid, []),
            aid in bom_articles,
            snap is not None,
            params,
        )
        alerts = [a for a in alerts if a.date is None or a.date <= end]
        if known_end < calculation_end:
            alerts.append(
                Alert(
                    aid,
                    AlertType.MISSING_DATA,
                    Severity.WARNING,
                    f"PDP continu connu jusqu’au {known_end} ; couverture au-delà indéterminée",
                    scope="data",
                )
            )
        if params.receipt_timing == "after_demand":
            prev = np.concatenate([[stock_start], firm.net[:-1]])
            intraday = prev + adjustments - demand_proj
            bad = np.where((intraday < -1e-9) & (np.arange(n) >= i_as_of))[0]
            if len(bad):
                alerts.append(
                    Alert(
                        aid,
                        AlertType.STOCKOUT,
                        Severity.CRITICAL,
                        "Rupture avant les arrivages du jour",
                        date=index.dates[int(bad[0])],
                        scope="firm",
                    )
                )
        last = (
            visible_n - 1
            if params.stockout_lookahead_days is None
            else min(visible_n - 1, i_as_of + params.stockout_lookahead_days)
        )
        k = {
            name: first_shortage(layer.shortage, i_as_of, last)
            for name, layer in (("firm", firm), ("forecast", forecast), ("sim", sim))
        }
        horizon_slice = slice(i_as_of, visible_n)
        kpis = {
            "demand_known_until": known_end.isoformat(),
            "coverage_censored": known_end < calculation_end or int(cov["sim"][i_as_of]) >= (n - i_as_of - 1),
            "stock_on_hand": float(stock_start),
            "snapshot_date": snap_date.isoformat(),
            "shortage_policy": params.shortage_policy,
            "stock_as_of_firm": float(firm.stock[i_as_of]),
            "stock_as_of_forecast": float(forecast.stock[i_as_of]),
            "stock_as_of_sim": float(sim.stock[i_as_of]),
            "coverage_firm_days": int(cov["firm"][i_as_of]),
            "coverage_forecast_days": int(cov["forecast"][i_as_of]),
            "coverage_sim_days": int(cov["sim"][i_as_of]),
            "coverage_target_days": int(article.coverage_target_days),
            "target_stock": float(target[i_as_of]),
            "first_stockout_firm": index.dates[k["firm"]].isoformat() if k["firm"] is not None else None,
            "first_stockout_forecast": index.dates[k["forecast"]].isoformat() if k["forecast"] is not None else None,
            "first_stockout_sim": index.dates[k["sim"]].isoformat() if k["sim"] is not None else None,
            "min_stock_firm": float(np.min(firm.stock[horizon_slice])),
            "min_stock_forecast": float(np.min(forecast.stock[horizon_slice])),
            "min_stock_sim": float(np.min(sim.stock[horizon_slice])),
            "max_shortage_firm": float(np.max(firm.shortage[horizon_slice])),
            "max_shortage_forecast": float(np.max(forecast.shortage[horizon_slice])),
            "max_shortage_sim": float(np.max(sim.shortage[horizon_slice])),
            "demand_next_7d": float(demand[i_as_of + 1 : i_as_of + 8].sum()),
            "demand_next_30d": float(demand[i_as_of + 1 : i_as_of + 31].sum()),
            "demand_horizon": float(demand[horizon_slice].sum()),
            "avg_daily_demand_30d": float(demand[i_as_of + 1 : i_as_of + 31].sum() / max(1, min(30, n - i_as_of - 1))),
            "open_firm_qty": float(supply_firm[horizon_slice].sum()),
            "open_forecast_qty": float(supply_forecast[horizon_slice].sum()),
            "open_planned_qty": float(supply_planned[horizon_slice].sum()),
            "proposed_qty": float(supply_proposed.sum()),
            "proposal_count": len(proposals),
            "urgent_proposal_count": sum(1 for p in proposals if p.urgent),
            "late_order_count": len(late_orders),
            "late_order_qty": float(sum(o.qty_open for o in late_orders)),
            "alert_count": len(alerts),
            "severity": (worst_severity(alerts).value if alerts else None),
            "actual_share_30d": float(share[i_as_of - 30 if i_as_of >= 30 else 0 : i_as_of + 1].mean())
            if i_as_of > 0
            else 0.0,
        }
        tail_demand[aid] = demand[visible_n:].tolist()
        results[aid] = ArticleResult(
            article=article,
            start_date=start,
            as_of=as_of,
            dates=index.dates[:visible_n],
            demand=demand.tolist()[:visible_n],
            demand_plan=dplan.tolist()[:visible_n],
            demand_actual_share=share.tolist()[:visible_n],
            supply_firm=supply_firm.tolist()[:visible_n],
            supply_forecast=supply_forecast.tolist()[:visible_n],
            supply_planned=supply_planned.tolist()[:visible_n],
            supply_proposed=supply_proposed.tolist()[:visible_n],
            receipts=receipts.tolist()[:visible_n],
            adjustments=adjustments.tolist()[:visible_n],
            stock_firm=firm.stock.tolist()[:visible_n],
            stock_forecast=forecast.stock.tolist()[:visible_n],
            stock_sim=sim.stock.tolist()[:visible_n],
            shortage_firm=firm.shortage.tolist()[:visible_n],
            shortage_forecast=forecast.shortage.tolist()[:visible_n],
            shortage_sim=sim.shortage.tolist()[:visible_n],
            stock_firm_net=firm.net.tolist()[:visible_n],
            stock_forecast_net=forecast.net.tolist()[:visible_n],
            stock_sim_net=sim.net.tolist()[:visible_n],
            coverage_firm=cov["firm"].tolist()[:visible_n],
            coverage_forecast=cov["forecast"].tolist()[:visible_n],
            coverage_sim=cov["sim"].tolist()[:visible_n],
            target_stock=target.tolist()[:visible_n],
            events=sorted(events, key=lambda e: (e.date, e.kind, e.ref)),
            alerts=alerts,
            proposals=proposals,
            kpis=kpis,
            suppliers=links_by_article.get(aid, []),
            diagnostics=notes,
        )

    program_daily = {
        pid: {index.dates[i]: float(v) for i, v in enumerate(arr[:visible_n]) if v} for pid, arr in program_eff.items()
    }
    return MrpResult(
        as_of=as_of,
        start_date=start,
        end_date=end,
        params=params,
        articles=results,
        program_daily=program_daily,
        tail_dates=index.dates[visible_n:],
        tail_demand=tail_demand,
        diagnostics=diagnostics,
    )


__all__ = ["run_mrp", "resolve_as_of", "Alert", "OrderType"]
