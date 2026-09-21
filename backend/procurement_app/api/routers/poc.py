"""Small editable staging tables for the management demonstration."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import zipfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ...data.poc import FIXTURE, KEYS, LABELS, MODELS, read_tables, validate_rows
from ...data.store import AppVersion, AuditLog, Base, PocWorkspace, audit
from ...services.context import AppContext
from ...services.grid_excel import checked_workbook
from ..deps import ctx_dep, current_user, session_dep


def poc_only(ctx: AppContext = Depends(ctx_dep)):
    if not ctx.settings.poc:
        raise HTTPException(404, "POC indisponible")


router = APIRouter(prefix="/api/poc", tags=["poc"], dependencies=[Depends(poc_only)])


class TableInput(BaseModel):
    rows: list[dict] = Field(max_length=2000)


def check_table(table):
    if table not in MODELS:
        raise HTTPException(404, "Table inconnue")


@router.get("/tables/{table}")
def get_table(table: str, session: Session = Depends(session_dep)):
    check_table(table)
    schema = MODELS[table].model_json_schema()["properties"]
    return {
        "rows": read_tables(session)[table],
        "keys": KEYS[table],
        "columns": [
            {
                "key": name,
                "label": LABELS[name],
                "type": "date" if spec.get("format") == "date" else spec.get("type", "string"),
                "choices": spec.get("enum"),
                "default": spec.get("default", ""),
            }
            for name, spec in schema.items()
        ],
    }


@router.put("/tables/{table}")
def put_table(
    table: str,
    body: TableInput,
    ctx: AppContext = Depends(ctx_dep),
    session: Session = Depends(session_dep),
    user: str = Depends(current_user),
):
    check_table(table)
    tables = read_tables(session)
    tables[table] = validate_rows(table, body.rows)
    row = session.get(PocWorkspace, 1)
    if row is None:
        row = PocWorkspace(id=1, tables_json="{}")
        session.add(row)
    row.tables_json = json.dumps(tables, ensure_ascii=False)
    audit(session, user, "poc_save", table, table, None, {"rows": len(tables[table])})
    session.commit()  # shared boundary validates all references and rolls back atomically
    ctx.bump()
    return {"rows": tables[table]}


@router.post("/parse/{table}")
async def parse(table: str, file: UploadFile = File(...), session: Session = Depends(session_dep)):
    check_table(table)
    content = await file.read(12 * 1024**2 + 1)
    if len(content) > 12 * 1024**2:
        raise HTTPException(413, "Fichier limité à 12 Mo")
    if (file.filename or "").lower().endswith(".xlsx"):
        try:
            wb = checked_workbook(content)
        except (zipfile.BadZipFile, KeyError) as exc:
            raise ValueError("Classeur XLSX invalide") from exc
        ws = wb[table] if table in wb.sheetnames else wb.active
        if ws.max_row > 2001 or ws.max_column > 30:
            raise ValueError("Fichier limité à 2 000 lignes et 30 colonnes")
        if any(c.data_type == "f" for row in ws for c in row):
            raise ValueError("Importer des valeurs, sans formules")
        matrix = [[v.date().isoformat() if isinstance(v, dt.datetime) else v for v in r] for r in ws.values]
    elif (file.filename or "").lower().endswith(".csv"):
        text = content.decode("utf-8-sig")
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t").delimiter
        except csv.Error:
            delimiter = ";"
        matrix = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    else:
        raise ValueError("Formats acceptés : CSV UTF-8 et XLSX")
    if not matrix:
        raise ValueError("Fichier vide")
    aliases = {LABELS[k].lower(): k for k in MODELS[table].model_fields}
    headers = [aliases.get(str(x).strip().lower(), str(x).strip()) for x in matrix[0]]
    if len(set(headers)) != len(headers):
        raise ValueError("Colonnes dupliquées")
    rows = []
    for line in matrix[1:]:
        if not any(v not in (None, "") for v in line):
            continue
        if len(line) > len(headers):
            raise ValueError("Ligne avec trop de colonnes")
        rows.append({k: v for k, v in zip(headers, line) if v not in (None, "")})
    return {"rows": validate_rows(table, rows)}


@router.get("/templates/{table}.csv")
def template(table: str, session: Session = Depends(session_dep)):
    check_table(table)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(MODELS[table].model_fields), delimiter=";")
    writer.writeheader()
    writer.writerows(json.loads(FIXTURE.read_text())[table])
    return Response(
        content=("\ufeff" + stream.getvalue()).encode(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="poc-{table}.csv"'},
    )


@router.post("/reset")
def reset(
    ctx: AppContext = Depends(ctx_dep), session: Session = Depends(session_dep), user: str = Depends(current_user)
):
    # This route is inaccessible outside the isolated POC. Keep the journal and concurrency revision.
    keep = {AppVersion.__tablename__, AuditLog.__tablename__}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name not in keep:
            session.execute(delete(table))
    audit(session, user, "poc_reset", "poc", "1", None, {})
    session.commit()
    ctx.bump()
    return {"status": "ok"}
