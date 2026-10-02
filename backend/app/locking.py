"""MySQL coordination shared by every backend instance: a per-project lock and a save log.

MySQL never holds project data. The upstream is the only source of truth.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, MetaData, String, Table, func, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


class LockTimeout(Exception):
    """Another save of the same project held the lock for too long."""


class LockUnavailable(Exception):
    """MySQL could not be reached, so the lock could not be taken."""


class ProjectLock(Protocol):
    def hold(self, project_id: str) -> AbstractAsyncContextManager[None]: ...


@dataclass
class SaveLogEntry:
    project_id: str
    outcome: str  # saved, noop, conflict, unconfirmed, rejected, not_found, lock_timeout, lock_unavailable, upstream_error
    attempts: int
    duration_ms: int
    changed_slots: list[str] = field(default_factory=list)


class SaveLog(Protocol):
    async def record(self, entry: SaveLogEntry) -> None: ...


metadata = MetaData()

save_log_table = Table(
    "save_log",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("project_id", String(64), nullable=False, index=True),
    Column("outcome", String(32), nullable=False),
    Column("changed_slots", JSON, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("instance_id", String(128), nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)


async def create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)  # only creates what is missing


class MySQLProjectLock:
    """A MySQL named lock (GET_LOCK). It belongs to the connection that took it, so the connection is
    held for the whole save; if this instance dies, the connection drops and MySQL frees the lock."""

    def __init__(self, engine: AsyncEngine, timeout_seconds: int):
        self._engine = engine
        self._timeout = timeout_seconds

    @asynccontextmanager
    async def hold(self, project_id: str) -> AsyncGenerator[None, None]:
        name = f"editor:project:{project_id}"[:64]  # MySQL's limit for lock names
        # Any failure while taking the lock (network, auth, driver) means no lock: fail closed with a 503,
        # never a 500. Errors raised by the save itself, inside `yield`, are not caught here.
        try:
            conn = await self._engine.connect()
        except Exception as exc:
            raise LockUnavailable(str(exc)) from exc
        try:
            try:
                got = (await conn.execute(text("SELECT GET_LOCK(:name, :timeout)"),
                                          {"name": name, "timeout": self._timeout})).scalar()
            except Exception as exc:
                raise LockUnavailable(str(exc)) from exc
            if got != 1:
                raise LockTimeout(f"Project {project_id} is being saved by someone else")
            try:
                yield
            finally:
                try:
                    await conn.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
                except Exception:
                    logger.exception("Could not release lock %s; closing the connection frees it", name)
                    await conn.invalidate()
        finally:
            await conn.close()


class MySQLSaveLog:
    def __init__(self, engine: AsyncEngine, instance_id: str):
        self._engine = engine
        self._instance_id = instance_id
        # Startup tries to create the table, but MySQL may have been down then; retry until it works.
        self._table_ready = False

    async def record(self, entry: SaveLogEntry) -> None:
        """Best effort: a failing log write never fails the save."""
        try:
            if not self._table_ready:
                await create_tables(self._engine)
                self._table_ready = True
            async with self._engine.begin() as conn:
                await conn.execute(save_log_table.insert().values(
                    project_id=entry.project_id,
                    outcome=entry.outcome,
                    changed_slots=entry.changed_slots,
                    attempts=entry.attempts,
                    duration_ms=entry.duration_ms,
                    instance_id=self._instance_id,
                ))
        except Exception:
            logger.exception("Could not write the save log for %s", entry.project_id)
