"""Identity, roles and optimistic transaction boundary shared by every route."""

from __future__ import annotations

from typing import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..data.store import AppVersion
from ..services.context import AppContext, get_context


def ctx_dep() -> AppContext:
    return get_context()


def current_user(request: Request, ctx: AppContext = Depends(ctx_dep)) -> str:
    user = request.headers.get("x-forwarded-email", "").strip().lower()
    if ctx.settings.mode == "demo":
        return user or "demo@local"
    if not user or len(user) > 254:
        raise HTTPException(401, "Identité Databricks absente")
    return user


def is_admin(ctx: AppContext, user: str) -> bool:
    return ctx.settings.mode == "demo" or user in {x.strip().lower() for x in ctx.settings.admins.split(",")}


def require_admin(ctx: AppContext, user: str):
    if not is_admin(ctx, user):
        raise HTTPException(403, "Action réservée à l'administrateur métier")


def session_dep(
    request: Request, ctx: AppContext = Depends(ctx_dep), user: str = Depends(current_user)
) -> Iterator[Session]:
    session = ctx.session()
    try:
        session.info.update(actor=user, context=ctx)
        mutation = (
            not request.url.path.startswith("/api/poc/parse/")
            and request.method not in ("GET", "HEAD", "OPTIONS")
            and request.url.path
            not in (
                "/api/simulate",
                "/api/imports/preview",
            )
        )
        if mutation:
            editors = {x.strip().lower() for x in (ctx.settings.editors + "," + ctx.settings.admins).split(",")}
            if ctx.settings.mode != "demo" and user not in editors:
                raise HTTPException(403, "Accès en lecture seule")
            expected = request.headers.get("if-match", "").strip('"')
            if not expected.isdigit():
                raise HTTPException(428, "Version requise. Rechargez le portefeuille avant de modifier.")
            result = session.execute(
                update(AppVersion)
                .where(AppVersion.id == 1, AppVersion.version == int(expected))
                .values(version=int(expected) + 1)
            )
            if result.rowcount != 1:
                raise HTTPException(409, "Le portefeuille a changé. Rechargez avant de réessayer.")
            session.info["revision"] = int(expected) + 1
        scenario_id = request.path_params.get("scenario_id") or request.query_params.get("scenario_id")
        if scenario_id:
            from ..data.store import Scenario

            scenario = session.get(Scenario, scenario_id)
            if scenario is None:
                raise HTTPException(404, "Scénario inconnu")
            if scenario.created_by != user and not is_admin(ctx, user):
                raise HTTPException(403, "Scénario privé")
        state = session.get(AppVersion, 1)
        request.state.revision = session.info.get("revision", state.version if state else 0)
        yield session
        if mutation and session.in_transaction():
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
