"""Explicit adapter for PROCUREMENT V1 datasets. V1 remains a regression oracle."""

import datetime as dt

from ..engine.models import (
    ActualLine,
    Article,
    BomLine,
    Dataset,
    EngineParams,
    Movement,
    OrderLine,
    OrderStatus,
    OrderType,
    PlanLine,
    Program,
    Receipt,
    StockSnapshot,
    Supplier,
    SupplierLink,
)
from ..engine.validation import validate_dataset


def from_v1(data):
    s = data.settings
    ds = Dataset(
        articles=[
            Article(
                x.id,
                x.name,
                x.unit,
                planner=x.planner,
                coverage_target_days=x.target_days,
                alert_red_days=x.min_days,
                alert_yellow_days=x.target_days,
                overstock_days=x.max_days,
                safety_stock_qty=float(x.safety_stock),
                order_cycle_days=0,
            )
            for x in data.items
        ],
        suppliers=[Supplier(x.id, x.name) for x in data.suppliers],
        links=[
            SupplierLink(
                x.item_id, x.supplier_id, float(x.moq), float(x.multiple), x.lead_days, float(x.quota * 100), x.priority
            )
            for x in data.sourcing
        ],
        programs=[Program(x, x) for x in sorted({b.program for b in data.bom})],
        bom=[BomLine(x.program, x.item_id, float(x.quantity), x.unit) for x in data.bom],
        plan=[PlanLine(x.program, x.week, float(x.quantity), "V1") for x in data.plans],
        actuals=[ActualLine(x.program, x.day, float(x.quantity)) for x in data.actuals],
        stock=[StockSnapshot(x.id, s.start - dt.timedelta(days=1), float(x.opening_stock)) for x in data.items],
        orders=[
            OrderLine(
                x.id,
                x.item_id,
                x.supplier_id,
                x.due,
                float(x.quantity),
                float(x.received_before_start),
                OrderType.FORECAST
                if x.message_type == "DELFOR"
                else OrderType.FIRM
                if x.status == "confirmed"
                else OrderType.PLANNED,
                OrderStatus.CANCELLED if x.status in ("ignored", "cancelled") else OrderStatus.OPEN,
                "APP",
            )
            for x in data.orders
        ],
        receipts=[
            Receipt(
                x.id,
                next(o.item_id for o in data.orders if o.id == x.order_id),
                x.day,
                float(x.quantity),
                order_id=x.order_id,
                source="APP",
            )
            for x in data.receipts
        ],
        movements=[
            Movement(x.id, x.item_id, x.day, float(x.quantity), comment=x.reason, source="APP")
            for x in data.adjustments
        ],
        holidays=s.holidays,
        meta={"migration": "PROCUREMENT V1"},
    )
    params = EngineParams(
        as_of=s.start,
        horizon_days=s.horizon,
        working_weekdays=tuple(d + 1 for d in s.workdays),
        lead_calendar=s.lead_calendar,
        coverage_unit=s.coverage_calendar,
        receipt_timing=s.receipt_timing,
        production_mode={"plan": "plan_only", "actual_preferred": "actual_then_plan", "actual_only": "actual_only"}[
            s.production_mode
        ],
        sourcing_policy=s.sourcing_mode,
        late_order_policy="ignore" if s.overdue_policy == "exclude" else "reschedule",
        target_policy="sum",
        spread_rounding="none",
        respect_lead_time=True,
    )
    validate_dataset(ds, params)
    return ds, params
