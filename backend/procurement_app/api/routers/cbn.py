"""Net requirement run ("Calcul CBN"): proposals are written into the simulated-order cells."""

from __future__ import annotations

import datetime as dt
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...data.store import AppCell, AppOrder, CbnProposal, audit
from ...services import mrp_service
from ...services.context import AppContext
from .. import presenters as P
from .. import schemas as S
from ..deps import ctx_dep, current_user, session_dep

router = APIRouter(prefix="/api/cbn", tags=["cbn"])


@router.post("/run", response_model=S.CbnReport)
def run(
    body: S.CbnRequest,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
    user: str = Depends(current_user),
):
    """Recompute the net requirements of the perimeter and store them as simulated orders.

    Simulated orders typed by the planner are kept and taken into account; the cells written by
    the previous run are replaced (``reset``).  Every written cell stays editable in the grid.
    """
    try:
        result, written, removed = mrp_service.run_cbn(
            ctx,
            session,
            user,
            planner=body.planner,
            article_ids=body.article_ids,
            scenario_id=body.scenario_id,
            reset=body.reset,
            **body.params,
        )
    except KeyError as exc:
        raise HTTPException(404, f"Scénario inconnu : {exc}")
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, f"Paramètres invalides : {exc}")
    df = ctx.source.table("ref_suppliers")
    names = dict(zip(df["supplier_id"], df["name"]))
    items = [P.proposal_out(p, result.articles[p.article_id], names) for p in written]
    items.sort(key=lambda p: (not p.urgent, p.order_date, p.article_id))
    for item in items:
        existing = session.get(CbnProposal, (body.scenario_id or "", item.proposal_id))
        if existing:
            existing.payload_json = item.model_dump_json()
        else:
            session.add(
                CbnProposal(
                    scenario_id=body.scenario_id or "",
                    proposal_id=item.proposal_id,
                    article_id=item.article_id,
                    payload_json=item.model_dump_json(),
                )
            )
    session.commit()
    ctx.bump()
    return S.CbnReport(
        as_of=result.as_of,
        articles=len(result.articles),
        proposals=len(written),
        urgent=sum(1 for p in written if p.urgent),
        qty=float(sum(p.qty for p in written)),
        removed=removed,
        items=items,
        diagnostics=result.diagnostics,
    )


@router.get("/results")
def results(scenario_id: str | None = None, session: Session = Depends(session_dep)):
    return [
        json.loads(p.payload_json) | {"decision": p.status}
        for p in session.scalars(select(CbnProposal).where(CbnProposal.scenario_id == (scenario_id or "")))
    ]


class Decision(S.InputModel):
    scenario_id: str | None = None
    action: Literal["accept", "ignore"]
    qty: float | None = Field(None, gt=0, le=1e12)


@router.post("/decisions/{proposal_id}")
def decide(
    proposal_id: str,
    body: Decision,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
    user: str = Depends(current_user),
):
    mrp_service.scenario_events(session, body.scenario_id)
    p = session.get(CbnProposal, (body.scenario_id or "", proposal_id))
    if p is None:
        raise HTTPException(404, "Proposition inconnue")
    if p.status != "proposed":
        raise HTTPException(409, "Proposition déjà traitée")
    data = json.loads(p.payload_json)
    date = dt.date.fromisoformat(data["delivery_date"])
    cells = list(
        session.scalars(
            select(AppCell).where(
                AppCell.scenario_id == (body.scenario_id or ""),
                AppCell.article_id == data["article_id"],
                AppCell.date == date,
                AppCell.source == "CBN",
            )
        )
    )
    if not cells:
        raise HTTPException(409, "La cellule a été modifiée depuis le calcul ; relancer le CBN")
    cell = cells[0]
    if cell.qty + 1e-8 < data["qty"]:
        raise HTTPException(409, "Solde de proposition insuffisant")
    cell.qty -= data["qty"]
    cell.expression = str(cell.qty)
    if body.action == "accept":
        qty = body.qty if body.qty is not None else data["qty"]
        if body.scenario_id:
            # Keep a simulated decision in this scenario; never publish to operational entries.
            mrp_service.upsert_cell(
                ctx,
                session,
                user,
                data["article_id"],
                date,
                "sim_order",
                str(qty),
                source="ACCEPTED",
                note=f"Acceptée {proposal_id} / {data['supplier_id']}",
                scenario_id=body.scenario_id,
            )
        else:
            session.add(
                AppOrder(
                    article_id=data["article_id"],
                    supplier_id=data["supplier_id"],
                    expected_date=date,
                    qty=qty,
                    unit=data["unit"],
                    order_type="PLANNED",
                    source="PROPOSAL",
                    proposal_id=proposal_id,
                    created_by=user,
                    note=data["reason"],
                )
            )
    p.status = "accepted" if body.action == "accept" else "ignored"
    audit(
        session,
        user,
        p.status,
        "proposal",
        proposal_id,
        data["article_id"],
        {"original": data, "qty": body.qty, "scenario_id": body.scenario_id},
    )
    session.commit()
    ctx.bump()
    return {"status": p.status}
