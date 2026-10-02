"""Against a real MySQL (EDITOR_DATABASE_URL). Skipped when it is not reachable."""

import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.locking import (LockTimeout, LockUnavailable, MySQLProjectLock, MySQLSaveLog, SaveLogEntry,
                         create_tables, save_log_table)

pytestmark = pytest.mark.mysql


@pytest.fixture
async def engine():
    engine = create_async_engine(Settings().database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("MySQL is not reachable")
    await create_tables(engine)
    yield engine
    await engine.dispose()


async def test_lock_is_exclusive_per_project(engine):
    first, second = MySQLProjectLock(engine, timeout_seconds=1), MySQLProjectLock(engine, timeout_seconds=0)
    async with first.hold("TEST-1"):
        with pytest.raises(LockTimeout):
            async with second.hold("TEST-1"):
                pass
        async with second.hold("TEST-2"):  # another project is not blocked
            pass
    async with second.hold("TEST-1"):  # released
        pass


async def test_lock_is_released_when_the_body_raises(engine):
    lock = MySQLProjectLock(engine, timeout_seconds=0)
    with pytest.raises(ValueError):
        async with lock.hold("TEST-3"):
            raise ValueError("boom")
    async with lock.hold("TEST-3"):
        pass


async def test_waiting_saver_gets_the_lock_when_released(engine):
    lock = MySQLProjectLock(engine, timeout_seconds=2)
    order = []

    async def saver(name, pause):
        async with lock.hold("TEST-4"):
            order.append(f"{name} in")
            await asyncio.sleep(pause)
            order.append(f"{name} out")

    await asyncio.gather(saver("a", 0.2), saver("b", 0))
    assert order in (["a in", "a out", "b in", "b out"], ["b in", "b out", "a in", "a out"])


async def test_unreachable_mysql_is_lock_unavailable():
    engine = create_async_engine("mysql+aiomysql://root@127.0.0.1:1/nothing")
    with pytest.raises(LockUnavailable):
        async with MySQLProjectLock(engine, timeout_seconds=1).hold("TEST-5"):
            pass
    await engine.dispose()


async def test_save_log_writes_a_row(engine):
    await MySQLSaveLog(engine, "test-instance").record(
        SaveLogEntry(project_id="TEST-6", outcome="saved", attempts=2, duration_ms=12, changed_slots=["name"]))
    async with engine.connect() as conn:
        row = (await conn.execute(select(save_log_table).where(save_log_table.c.project_id == "TEST-6")
                                  .order_by(save_log_table.c.id.desc()))).first()
        await conn.execute(save_log_table.delete().where(save_log_table.c.project_id == "TEST-6"))
        await conn.commit()
    assert (row.outcome, row.attempts, row.changed_slots, row.instance_id) == ("saved", 2, ["name"], "test-instance")


async def test_save_log_failure_does_not_raise():
    engine = create_async_engine("mysql+aiomysql://root@127.0.0.1:1/nothing")
    await MySQLSaveLog(engine, "x").record(SaveLogEntry(project_id="P", outcome="saved", attempts=1, duration_ms=1))
    await engine.dispose()


class EngineFailingOnConnect:
    """Like an engine whose driver raises something that is not a database error, e.g. the RuntimeError
    aiomysql raises when `cryptography` is missing for MySQL 8's default authentication."""

    async def connect(self):
        raise RuntimeError("'cryptography' package is required")

    def begin(self):
        raise RuntimeError("'cryptography' package is required")


async def test_any_failure_while_taking_the_lock_is_lock_unavailable():
    with pytest.raises(LockUnavailable):
        async with MySQLProjectLock(EngineFailingOnConnect(), timeout_seconds=1).hold("TEST-7"):
            pass


async def test_save_log_swallows_any_failure():
    await MySQLSaveLog(EngineFailingOnConnect(), "x").record(
        SaveLogEntry(project_id="P", outcome="saved", attempts=1, duration_ms=1))
