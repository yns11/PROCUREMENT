"""FastAPI application factory. Serves the API under ``/api`` and the built frontend at ``/``."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..config import get_settings
from .deps import current_user
from .routers import cbn, entries, files, mrp, pdp, poc, reference, scenarios


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = FastAPI(title=settings.app_title, version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.get("/api/health", tags=["health"])
    def health():
        return {"status": "ok", "version": __version__}

    for r in (
        reference.router,
        mrp.router,
        entries.router,
        cbn.router,
        scenarios.router,
        pdp.router,
        files.router,
        poc.router,
    ):
        app.include_router(r, dependencies=[Depends(current_user)])

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("x-procurement-request") != "1":
                return JSONResponse(status_code=403, content={"detail": "En-tête de requête requis"})
            length = request.headers.get("content-length", "0")
            if not length.isdigit() or int(length) > 12 * 1024 * 1024:
                return JSONResponse(status_code=413, content={"detail": "Requête trop volumineuse"})
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 12 * 1024 * 1024:
                    return JSONResponse(status_code=413, content={"detail": "Requête trop volumineuse"})
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/") and request.url.path != "/api/health":
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Data-Revision"] = str(getattr(request.state, "revision", 0))
        return response

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)[:2000]})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover - defensive
        logging.getLogger("appro").exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500, content={"detail": "Erreur interne. Consulter le journal de l'application."}
        )

    static = Path(settings.static_dir)
    if static.exists() and (static / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            candidate = (static / full_path).resolve()
            if not candidate.is_relative_to(static.resolve()):
                return JSONResponse(status_code=404, content={"detail": "Fichier inconnu"})
            if full_path and candidate.is_file() and candidate.suffix in (".svg", ".ico", ".png", ".webmanifest"):
                return FileResponse(candidate)
            return FileResponse(static / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def root():
            return {"message": "APPRO API – frontend non construit (npm run build dans client/)", "docs": "/api/docs"}

    return app


app = create_app()

if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("procurement_app.api.main:app", host="0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)))
