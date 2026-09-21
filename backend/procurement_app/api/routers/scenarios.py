"""Saved what-if scenarios and comparison with the baseline."""

from __future__ import annotations

import dataclasses
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...data.store import Scenario, ScenarioEventRow, ScenarioRevision, audit
from ...engine.runner import resolve_as_of
from ...engine.scenario import ScenarioEvent, apply_scenario
from ...engine.validation import validate_dataset
from ...services import mrp_service
from ...services.context import AppContext
from .. import presenters as P
from .. import schemas as S
from ..deps import ctx_dep, current_user, session_dep

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


def _out(sc: Scenario) -> S.ScenarioOut:
    return S.ScenarioOut(
        id=sc.id,
        name=sc.name,
        description=sc.description,
        status=sc.status,
        params=sc.params,
        events=[
            S.ScenarioEventOut(id=e.id, seq=e.seq, kind=e.kind, payload=e.payload, label=e.label) for e in sc.events
        ],
        created_by=sc.created_by,
        created_at=sc.created_at,
        updated_at=sc.updated_at,
    )


def _check_events(events: list[S.ScenarioEventIn]) -> None:
    bad = [e.kind for e in events if e.kind not in S.EVENT_KINDS]
    if bad:
        raise HTTPException(422, f"Types d'événement inconnus : {bad}. Attendus : {list(S.EVENT_KINDS)}")


@router.get("", response_model=list[S.ScenarioOut])
def list_scenarios(session: Session = Depends(session_dep)):
    ctx = session.info["context"]
    actor = session.info["actor"]
    from ..deps import is_admin

    query = select(Scenario).order_by(Scenario.updated_at.desc())
    if not is_admin(ctx, actor):
        query = query.where(Scenario.created_by == actor)
    return [_out(s) for s in session.scalars(query).all()]


@router.post("", response_model=S.ScenarioOut, status_code=201)
def create_scenario(
    body: S.ScenarioIn,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
    user: str = Depends(current_user),
):
    _check_events(body.events)
    sc = Scenario(
        name=body.name, description=body.description, params_json=json.dumps(body.params, default=str), created_by=user
    )
    for i, e in enumerate(body.events):
        sc.events.append(
            ScenarioEventRow(seq=i, kind=e.kind, payload_json=json.dumps(e.payload, default=str), label=e.label)
        )
    ds, _ = mrp_service.load_dataset(ctx, session)
    params = mrp_service.build_params(ctx, session, **body.params)
    params.as_of = resolve_as_of(ds, params)
    validate_dataset(apply_scenario(ds, [ScenarioEvent(e.kind, e.payload) for e in body.events])[0], params)
    sc.baseline_json = mrp_service.DATASET.dump_json(ds).decode()
    sc.baseline_params_json = json.dumps(dataclasses.asdict(params), default=str)
    sc.params_json = sc.baseline_params_json
    session.add(sc)
    session.add(ScenarioRevision(scenario_id=sc.id, version=1, actor=user, payload_json=body.model_dump_json()))
    audit(session, user, "create", "scenario", sc.id, None, {"name": body.name, "events": len(body.events)})
    session.commit()
    ctx.bump()
    return _out(sc)


@router.get("/{scenario_id}", response_model=S.ScenarioOut)
def get_scenario(scenario_id: str, session: Session = Depends(session_dep)):
    sc = session.get(Scenario, scenario_id)
    if sc is None:
        raise HTTPException(404, "Scénario inconnu")
    return _out(sc)


@router.put("/{scenario_id}", response_model=S.ScenarioOut)
def update_scenario(
    scenario_id: str,
    body: S.ScenarioIn,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
    user: str = Depends(current_user),
):
    sc = session.get(Scenario, scenario_id)
    if sc is None:
        raise HTTPException(404, "Scénario inconnu")
    if sc.created_by != user and ctx.settings.mode != "demo" and user not in ctx.settings.admins.split(","):
        raise HTTPException(403, "Seul le propriétaire peut modifier ce scénario")
    _check_events(body.events)
    ds, _ = mrp_service.load_dataset(ctx, session, scenario_id)
    params = mrp_service.build_params(ctx, session, **(json.loads(sc.baseline_params_json) | body.params))
    validate_dataset(apply_scenario(ds, [ScenarioEvent(e.kind, e.payload) for e in body.events])[0], params)
    sc.version += 1
    session.add(
        ScenarioRevision(scenario_id=sc.id, version=sc.version, actor=user, payload_json=body.model_dump_json())
    )
    sc.name, sc.description = body.name, body.description
    sc.params_json = json.dumps(json.loads(sc.baseline_params_json) | body.params, default=str)
    sc.events.clear()
    for i, e in enumerate(body.events):
        sc.events.append(
            ScenarioEventRow(seq=i, kind=e.kind, payload_json=json.dumps(e.payload, default=str), label=e.label)
        )
    audit(session, user, "update", "scenario", sc.id, None, {"name": body.name, "events": len(body.events)})
    session.commit()
    ctx.bump()
    return _out(sc)


@router.delete("/{scenario_id}", status_code=204)
def delete_scenario(
    scenario_id: str,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
    user: str = Depends(current_user),
):
    sc = session.get(Scenario, scenario_id)
    if sc is None:
        raise HTTPException(404, "Scénario inconnu")
    if sc.created_by != user and ctx.settings.mode != "demo" and user not in ctx.settings.admins.split(","):
        raise HTTPException(403, "Seul le propriétaire peut supprimer ce scénario")
    audit(session, user, "delete", "scenario", sc.id, None, {"name": sc.name})
    session.delete(sc)
    session.commit()
    ctx.bump()


@router.get("/{scenario_id}/compare", response_model=S.CompareResponse)
def compare(
    scenario_id: str,
    planner: str | None = None,
    horizon_days: int | None = None,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
):
    if session.get(Scenario, scenario_id) is None:
        raise HTTPException(404, "Scénario inconnu")
    from ...engine import run_mrp

    ds, _ = mrp_service.load_dataset(ctx, session, scenario_id)
    sc = session.get(Scenario, scenario_id)
    params = mrp_service.build_params(
        ctx, session, **(json.loads(sc.baseline_params_json) | ({"horizon_days": horizon_days} if horizon_days else {}))
    )
    ids = [a.article_id for a in ds.articles if not planner or a.planner == planner]
    base = run_mrp(ds, params, article_ids=ids)
    scen = mrp_service.compute(ctx, session, planner=planner, scenario_id=scenario_id, horizon_days=params.horizon_days)
    return S.CompareResponse(
        as_of=base.as_of,
        base_kpis=P.cockpit_kpis(base),
        scenario_kpis=P.cockpit_kpis(scen),
        articles=P.compare_articles(base, scen),
        diagnostics=scen.diagnostics,
    )


@router.get("/{scenario_id}/history")
def history(scenario_id: str, session: Session = Depends(session_dep)):
    return [
        {"version": x.version, "actor": x.actor, "created_at": x.created_at, "content": json.loads(x.payload_json)}
        for x in session.scalars(
            select(ScenarioRevision)
            .where(ScenarioRevision.scenario_id == scenario_id)
            .order_by(ScenarioRevision.version.desc())
        )
    ]


@router.post("/{scenario_id}/clone", response_model=S.ScenarioOut)
def clone(
    scenario_id: str,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
    user: str = Depends(current_user),
):
    old = session.get(Scenario, scenario_id)
    ds, _ = mrp_service.load_dataset(ctx, session, scenario_id)
    ds, _ = apply_scenario(ds, [ScenarioEvent(e.kind, e.payload) for e in old.events])
    from ...data.store import AppCell
    from ...engine.models import SimCell

    cells = list(session.scalars(select(AppCell).where(AppCell.scenario_id == scenario_id)))
    replaced = {(c.article_id, c.date, c.kind) for c in cells if c.source in ("MANUAL", "IMPORT")}
    ds.cells = [x for x in ds.cells if (x.article_id, x.date, x.kind) not in replaced]
    ds.cells.extend(SimCell(c.article_id, c.date, c.kind, c.qty, c.source, c.note) for c in cells)
    new = Scenario(
        name=("Copie • " + old.name)[:120],
        description=old.description,
        created_by=user,
        baseline_json=mrp_service.DATASET.dump_json(ds).decode(),
        baseline_params_json=old.params_json,
        params_json=old.params_json,
    )
    session.add(new)
    session.add(
        ScenarioRevision(scenario_id=new.id, version=1, actor=user, payload_json=json.dumps({"cloned_from": old.id}))
    )
    session.commit()
    ctx.bump()
    return _out(new)
