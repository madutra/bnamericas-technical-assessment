import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.locking import (LockTimeout, LockUnavailable, MySQLProjectLock, MySQLSaveLog, ProjectLock, SaveLog,
                         create_tables)
from app.schemas import Project, ProjectSummary, SaveRequest
from app.service import SaveConflict, SaveUnconfirmed, save_project
from app.upstream import UpstreamClient, UpstreamNotFound, UpstreamRejected, UpstreamUnavailable

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        await create_tables(engine)
    except Exception:
        # Reads keep working without MySQL; saves will answer 503 until it is back.
        logger.exception("MySQL is not reachable at startup")
    app.state.settings = settings
    app.state.upstream = UpstreamClient.from_settings(settings)
    app.state.lock = MySQLProjectLock(engine, settings.lock_timeout_seconds)
    app.state.save_log = MySQLSaveLog(engine, settings.instance_id)
    yield
    await app.state.upstream.aclose()
    await engine.dispose()


app = FastAPI(title="Project editor", lifespan=lifespan)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_upstream(request: Request) -> UpstreamClient:
    return request.app.state.upstream


def get_lock(request: Request) -> ProjectLock:
    return request.app.state.lock


def get_save_log(request: Request) -> SaveLog:
    return request.app.state.save_log


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/projects")
async def list_projects(upstream: UpstreamClient = Depends(get_upstream)) -> list[ProjectSummary]:
    return await upstream.list_projects()


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str, upstream: UpstreamClient = Depends(get_upstream)) -> Project:
    return await upstream.get_project(project_id)


@app.put("/api/projects/{project_id}")
async def put_project(
    project_id: str,
    body: SaveRequest,
    upstream: UpstreamClient = Depends(get_upstream),
    lock: ProjectLock = Depends(get_lock),
    log: SaveLog = Depends(get_save_log),
    settings: Settings = Depends(get_settings),
) -> Project:
    return await save_project(project_id, body, upstream=upstream, lock=lock, log=log,
                              attempts=settings.save_attempts)


def _error(status: int, detail: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail}, headers=headers)


@app.exception_handler(SaveConflict)
async def on_conflict(_: Request, exc: SaveConflict) -> JSONResponse:
    return JSONResponse(status_code=409, content=exc.response.model_dump(mode="json"))


@app.exception_handler(UpstreamNotFound)
async def on_not_found(_: Request, exc: UpstreamNotFound) -> JSONResponse:
    return _error(404, str(exc))


@app.exception_handler(UpstreamRejected)
async def on_rejected(_: Request, exc: UpstreamRejected) -> JSONResponse:
    return _error(422, f"The records service rejected the values: {exc}")


@app.exception_handler(RequestValidationError)
async def on_invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    messages = []
    for error in exc.errors():
        where = ".".join(str(p) for p in error["loc"] if p != "body")
        messages.append(f"{where}: {error['msg']}" if where else error["msg"])
    return _error(422, "; ".join(messages))


@app.exception_handler(UpstreamUnavailable)
async def on_unavailable(_: Request, exc: UpstreamUnavailable) -> JSONResponse:
    logger.warning("Upstream unavailable: %s", exc)
    return _error(502, "The records service is unavailable. Try again shortly.")


@app.exception_handler(LockTimeout)
async def on_lock_timeout(_: Request, exc: LockTimeout) -> JSONResponse:
    return _error(503, "Someone else is saving this project right now. Try again.", {"Retry-After": "2"})


@app.exception_handler(LockUnavailable)
async def on_lock_unavailable(_: Request, exc: LockUnavailable) -> JSONResponse:
    logger.error("Lock store unavailable: %s", exc)
    return _error(503, "Saving is temporarily unavailable. Try again shortly.", {"Retry-After": "5"})


@app.exception_handler(SaveUnconfirmed)
async def on_unconfirmed(_: Request, exc: SaveUnconfirmed) -> JSONResponse:
    return _error(504, "The save could not be confirmed. Reload the project to see what was stored.")
