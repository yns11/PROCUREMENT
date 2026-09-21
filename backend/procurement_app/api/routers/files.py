"""Excel round-trip uses a trusted server manifest, idempotency and isolated scenarios."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ...data.store import AppVersion, ImportedWorkbook, Scenario, ScenarioRevision, WorkbookExport, audit
from ...engine.models import SimCell
from ...engine.scenario import apply_scenario
from ...services import excel_service, mrp_service
from ...services.context import AppContext
from ...services.grid_excel import checked_workbook, export_grid, parse_grid
from .. import schemas as S
from ..deps import ctx_dep, current_user, session_dep

router = APIRouter(prefix="/api", tags=["files"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(content, filename):
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/exports/simulation.xlsx")
def export_simulation(
    planner: str | None = None,
    article_ids: list[str] | None = Query(None),
    scenario_id: str | None = None,
    granularity: Literal["day", "week"] = "day",
    horizon_days: int | None = Query(None, ge=7, le=730),
    from_date: dt.date | None = None,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
    user: str = Depends(current_user),
):
    result = mrp_service.compute(
        ctx, session, planner=planner, article_ids=article_ids, scenario_id=scenario_id, horizon_days=horizon_days
    )
    ds, _ = mrp_service.load_dataset(ctx, session, scenario_id)
    events, _ = mrp_service.scenario_events(session, scenario_id)
    ds, _ = apply_scenario(ds, events)
    # Freeze the actual displayed flows, including scenario cells and CBN, in the export baseline.
    from ...services.grid_excel import INPUTS

    for aid, ar in result.articles.items():
        for i, d in enumerate(ar.dates):
            if d < result.as_of:
                continue
            for kind, (_, series) in INPUTS.items():
                ds.cells = [c for c in ds.cells if (c.article_id, c.date, c.kind) != (aid, d, kind)]
                qty = getattr(ar, series)[i] + (
                    ar.supply_proposed[i]
                    if kind == "planned_flow" and result.params.include_proposals_in_simulation
                    else 0
                )
                ds.cells.append(SimCell(aid, d, kind, qty, "IMPORT"))
    state = session.get(AppVersion, 1)
    record = WorkbookExport(owner=user, scenario_id=scenario_id or "", revision=state.version, manifest_json="{}")
    content, manifest = export_grid(result, article_ids, granularity, from_date, {"holidays": ds.holidays}, record.id)
    params = dataclasses.asdict(result.params)
    params.update(as_of=result.as_of, generate_proposals=False)
    manifest.update(dataset=json.loads(mrp_service.DATASET.dump_json(ds)), params=params)
    record.manifest_json = json.dumps(manifest, default=str)
    session.add(record)
    session.commit()
    return _xlsx(content, f"simulation_{result.as_of}_{granularity}.xlsx")


@router.get("/exports/alerts.xlsx")
def export_alerts(
    planner: str | None = None,
    scenario_id: str | None = None,
    horizon_days: int | None = None,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
):
    result = mrp_service.compute(ctx, session, planner=planner, scenario_id=scenario_id, horizon_days=horizon_days)
    return _xlsx(excel_service.alerts_workbook(result), f"alertes_{result.as_of}.xlsx")


@router.get("/exports/orders.xlsx")
def export_orders(
    planner: str | None = None,
    scenario_id: str | None = None,
    horizon_days: int | None = None,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
):
    result = mrp_service.compute(ctx, session, planner=planner, scenario_id=scenario_id, horizon_days=horizon_days)
    return _xlsx(excel_service.orders_workbook(result), f"commandes_{result.as_of}.xlsx")


def read_export(content, session, user):
    wb = checked_workbook(content)
    if "_FORMAT" not in wb:
        raise ValueError("Réexportez la simulation avec PROCUREMENT V2")
    record = session.get(WorkbookExport, wb["_FORMAT"]["C1"].value)
    if record is None or record.owner != user:
        raise HTTPException(403, "Export absent ou appartenant à un autre utilisateur")
    manifest = json.loads(record.manifest_json)
    return manifest, parse_grid(content, manifest)


@router.post("/imports/preview")
async def preview(
    file: UploadFile = File(...), session: Session = Depends(session_dep), user: str = Depends(current_user)
):
    _, changes = read_export(await file.read(), session, user)
    return {"changes": changes, "count": len(changes), "destination": "nouveau scénario isolé"}


@router.post("/imports/entries", response_model=S.ImportReport, status_code=201)
async def import_entries(
    file: UploadFile = File(...),
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
    user: str = Depends(current_user),
):
    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()
    manifest, changes = read_export(content, session, user)
    if session.get(ImportedWorkbook, checksum):
        return S.ImportReport(created=0, ignored=0, notes=["Classeur déjà importé ; aucune duplication."])
    if not changes:
        return S.ImportReport(created=0, ignored=0, notes=["Grille inchangée ; aucune saisie créée."])
    ds = mrp_service.DATASET.validate_python(manifest["dataset"])
    for c in changes:
        d = dt.date.fromisoformat(c["date"])
        ds.cells = [x for x in ds.cells if (x.article_id, x.date, x.kind) != (c["article_id"], d, c["kind"])]
        ds.cells.append(SimCell(c["article_id"], d, c["kind"], c["qty"], "IMPORT", "Saisie Excel"))
    params = mrp_service.build_params(ctx, session, **manifest["params"])
    from ...engine.validation import validate_dataset

    validate_dataset(ds, params)
    sc = Scenario(
        name=f"Excel • {file.filename or 'simulation'}"[:120],
        created_by=user,
        baseline_json=mrp_service.DATASET.dump_json(ds).decode(),
        params_json=json.dumps(manifest["params"]),
        baseline_params_json=json.dumps(manifest["params"]),
    )
    session.add(sc)
    session.add(ImportedWorkbook(checksum=checksum, actor=user))
    session.add(
        ScenarioRevision(scenario_id=sc.id, version=1, actor=user, payload_json=json.dumps({"changes": changes}))
    )
    audit(
        session,
        user,
        "import_grid",
        "scenario",
        sc.id,
        None,
        {"changes": len(changes), "export": manifest["export_id"]},
    )
    session.commit()
    ctx.bump()
    return S.ImportReport(
        created=len(changes),
        ignored=0,
        notes=[f"Scénario créé : {sc.name} ({sc.id}). Choisissez-le dans le sélecteur de scénario."],
    )


@router.post("/imports/v1", response_model=S.ImportReport, status_code=201)
async def import_v1(
    file: UploadFile = File(...),
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
    user: str = Depends(current_user),
):
    """Recover a V1 JSON dataset or workbook into a private frozen V2 scenario."""
    content = await file.read()
    from procurement.models import Dataset as V1Dataset

    from ...services.migration import from_v1

    if (file.filename or "").lower().endswith(".xlsx"):
        checked_workbook(content)
        from procurement.exchange import read_workbook

        data = read_workbook(content)
    else:
        data = V1Dataset.model_validate_json(content)
    ds, params = from_v1(data)
    payload = json.dumps(dataclasses.asdict(params), default=str)
    sc = Scenario(
        name=f"Migration V1 • {file.filename}"[:120],
        created_by=user,
        baseline_json=mrp_service.DATASET.dump_json(ds).decode(),
        params_json=payload,
        baseline_params_json=payload,
    )
    session.add(sc)
    audit(session, user, "migration_v1", "scenario", sc.id, None, {"articles": len(ds.articles)})
    session.commit()
    ctx.bump()
    return S.ImportReport(
        created=len(ds.articles),
        ignored=0,
        notes=[f"Scénario V1 migré : {sc.id}. Les projections V2 suivent les règles documentées du moteur unifié."],
    )
