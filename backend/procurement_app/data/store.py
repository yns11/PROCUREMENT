"""Transactional app store: entries typed by the planners, scenarios, PDP versions, audit log.

SQLAlchemy 2.0 ORM.  Locally the store is a SQLite file; on Databricks Apps it is a Lakebase
(PostgreSQL) database attached as an app resource.  Schema creation is idempotent
(``Base.metadata.create_all``) so the app can boot on an empty database.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
    inspect,
)
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class AppOrder(Base):
    """Order typed in the app (planned) or accepted from a proposal."""

    __tablename__ = "app_orders"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("AO"))
    article_id: Mapped[str] = mapped_column(String(40), index=True)
    supplier_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    expected_date: Mapped[dt.date] = mapped_column(Date, index=True)
    qty: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(10), default="PCE")
    order_type: Mapped[str] = mapped_column(String(12), default="PLANNED")  # PLANNED | FIRM
    status: Mapped[str] = mapped_column(String(12), default="OPEN")  # OPEN | SENT | RECEIVED | CANCELLED
    source: Mapped[str] = mapped_column(String(12), default="MANUAL")  # MANUAL | PROPOSAL | IMPORT
    erp_order_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AppReceipt(Base):
    __tablename__ = "app_receipts"
    erp_receipt_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("AR"))
    article_id: Mapped[str] = mapped_column(String(40), index=True)
    supplier_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(40), nullable=True)  # app or ERP order id
    receipt_date: Mapped[dt.date] = mapped_column(Date, index=True)
    qty: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class AppAdjustment(Base):
    __tablename__ = "app_adjustments"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("AA"))
    article_id: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    qty: Mapped[float] = mapped_column(Float)
    movement_type: Mapped[str] = mapped_column(String(30), default="INVENTORY_ADJUSTMENT")
    comment: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class AppProductionActual(Base):
    """Actual produced quantity typed by the planner (overrides the ERP value for that day)."""

    __tablename__ = "app_production_actual"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("AP"))
    program_id: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    qty: Mapped[float] = mapped_column(Float)
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (Index("ix_app_prod_program_date", "program_id", "date", unique=True),)


class PdpVersion(Base):
    """A production plan imported from Excel (one active version at most)."""

    __tablename__ = "app_pdp_versions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("PDP"))
    name: Mapped[str] = mapped_column(String(120))
    source_file: Mapped[str] = mapped_column(String(255), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    imported_by: Mapped[str] = mapped_column(String(120), default="")
    imported_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    lines: Mapped[list["PdpLine"]] = relationship(back_populates="version", cascade="all, delete-orphan")


class PdpLine(Base):
    __tablename__ = "app_pdp_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("app_pdp_versions.id"), index=True)
    program_id: Mapped[str] = mapped_column(String(40), index=True)
    week_start: Mapped[dt.date] = mapped_column(Date)
    qty: Mapped[float] = mapped_column(Float)
    version: Mapped["PdpVersion"] = relationship(back_populates="lines")


class Scenario(Base):
    __tablename__ = "app_scenarios"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("SC"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft | archived
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    baseline_json: Mapped[str] = mapped_column(Text, default="{}")
    baseline_params_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    events: Mapped[list["ScenarioEventRow"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", order_by="ScenarioEventRow.seq"
    )

    @property
    def params(self) -> dict[str, Any]:
        return json.loads(self.params_json or "{}")


class ScenarioEventRow(Base):
    __tablename__ = "app_scenario_events"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("EV"))
    scenario_id: Mapped[str] = mapped_column(ForeignKey("app_scenarios.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(30))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    label: Mapped[str] = mapped_column(String(255), default="")
    scenario: Mapped["Scenario"] = relationship(back_populates="events")

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json or "{}")


class ParamOverride(Base):
    """Overrides of reference parameters (article thresholds, link lead times, global rules)."""

    __tablename__ = "app_param_overrides"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("PO"))
    scope: Mapped[str] = mapped_column(String(12))  # global | article | link | planner
    key1: Mapped[str] = mapped_column(String(60), default="")  # article_id / planner
    key2: Mapped[str] = mapped_column(String(60), default="")  # supplier_id for links
    field: Mapped[str] = mapped_column(String(60))
    value: Mapped[str] = mapped_column(String(255))
    updated_by: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("ix_param_scope_keys", "scope", "key1", "key2", "field", unique=True),)


class AppCell(Base):
    """One editable cell of the simulation grid: a simulated order or an adjustment for one day.

    The planner types a quantity or an arithmetic expression; the evaluated quantity is stored
    with the expression.  ``source`` is ``MANUAL`` (typed), ``CBN`` (written by the net
    requirement run) or ``IMPORT`` (re-imported workbook).  One row per (article, date, kind,
    source): a typed cell and a CBN result may coexist on the same day (the grid shows their sum);
    typing on that day replaces both.
    """

    __tablename__ = "app_cells"
    __table_args__ = (Index("ix_app_cells_key", "scenario_id", "article_id", "date", "kind", "source", unique=True),)
    scenario_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    supplier_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("AC"))
    article_id: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(12))  # sim_order | adjustment
    expression: Mapped[str] = mapped_column(String(200), default="")
    qty: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(12), default="MANUAL")  # MANUAL | CBN | IMPORT
    note: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CbnProposal(Base):
    __tablename__ = "procurement_cbn_proposals"
    scenario_id: Mapped[str] = mapped_column(String(40), primary_key=True, default="")
    proposal_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    article_id: Mapped[str] = mapped_column(String(40), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="proposed")


class AuditLog(Base):
    __tablename__ = "app_audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user: Mapped[str] = mapped_column(String(120), default="", index=True)
    action: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    article_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json or "{}")


class AppVersion(Base):
    __tablename__ = "procurement_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)


class ScenarioRevision(Base):
    __tablename__ = "procurement_scenario_revisions"
    scenario_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(254))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class WorkbookExport(Base):
    __tablename__ = "procurement_workbook_exports"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("XLS"))
    owner: Mapped[str] = mapped_column(String(254))
    scenario_id: Mapped[str] = mapped_column(String(40), default="")
    revision: Mapped[int] = mapped_column(Integer)
    manifest_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class ImportedWorkbook(Base):
    __tablename__ = "procurement_workbook_imports"
    checksum: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


@event.listens_for(Base, "init", propagate=True)
def _assign_id(target, args, kwargs):
    """Assign identifiers before audit, not on the later INSERT flush."""
    column = target.__table__.columns.get("id")
    if column is not None and isinstance(column.type, String) and not kwargs.get("id"):
        target.id = new_id(type(target).__name__[:4].upper())


def _record_values(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


@event.listens_for(Session, "before_flush")
def _capture_changes(session, flush_context, instances):
    """Complete before/after evidence, committed atomically with the business transaction."""
    if not session.info.get("actor"):
        return
    excluded = (AuditLog, AppVersion, ScenarioRevision, WorkbookExport, ImportedWorkbook)
    for row in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(row, excluded) or not isinstance(row, Base):
            continue
        after = _record_values(row)
        before = dict(after)
        for field in inspect(row).attrs:
            if field.key in before and field.history.deleted:
                before[field.key] = field.history.deleted[0]
        action = "create" if row in session.new else "delete" if row in session.deleted else "update"
        session.add(
            AuditLog(
                user=session.info["actor"],
                action=f"snapshot_{action}",
                entity_type=row.__tablename__,
                entity_id=str(getattr(row, "id", "")),
                article_id=getattr(row, "article_id", None),
                payload_json=json.dumps(
                    {"before": None if action == "create" else before, "after": None if action == "delete" else after},
                    default=str,
                ),
            )
        )


@event.listens_for(Session, "before_commit")
def _validate_transaction(session):
    ctx = session.info.get("context")
    if not ctx or not session.info.get("revision"):
        return
    from ..engine.validation import validate_dataset
    from ..services.mrp_service import build_params, load_dataset

    ds, _ = load_dataset(ctx, session)
    validate_dataset(ds, build_params(ctx, session))


# =============================================================================
# Engine / session factory
# =============================================================================
def make_engine(url: str):
    if url == "lakebase":
        from databricks.sdk import WorkspaceClient

        client = WorkspaceClient()
        target = URL.create(
            "postgresql+psycopg",
            username=os.environ["PGUSER"],
            host=os.environ["PGHOST"],
            port=int(os.getenv("PGPORT", "5432")),
            database=os.environ["PGDATABASE"],
            query={"sslmode": "require"},
        )
        engine = create_engine(target, pool_pre_ping=True, pool_recycle=2700, pool_size=5, max_overflow=5)

        @event.listens_for(engine, "do_connect")
        def _fresh_token(dialect, connection_record, args, params):
            params["password"] = client.postgres.generate_database_credential(
                endpoint=os.environ["LAKEBASE_ENDPOINT"]
            ).token

        return engine
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    else:
        engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, future=True)
    return engine


def init_store(url: str, initialize: bool = False) -> sessionmaker[Session]:
    engine = make_engine(url)
    if initialize or url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    elif not inspect(engine).has_table("procurement_state"):
        raise RuntimeError("Initialiser le schéma avec scripts/init_db.py avant déploiement")
    with Session(engine) as session:
        if session.get(AppVersion, 1) is None:
            session.add(AppVersion(id=1, version=0))
            session.commit()
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def audit(
    session: Session,
    user: str,
    action: str,
    entity_type: str,
    entity_id: str = "",
    article_id: str | None = None,
    payload: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            user=user,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            article_id=article_id,
            payload_json=json.dumps(payload or {}, default=str),
        )
    )
