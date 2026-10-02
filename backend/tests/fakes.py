"""In-memory stand-ins for MySQL and the upstream, for unit tests."""

import asyncio
from collections import defaultdict
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from app.locking import LockTimeout, LockUnavailable, SaveLogEntry
from app.schemas import Project
from app.upstream import UpstreamWriteUnknown


class FakeLock:
    def __init__(self, timeout: float = 1.0, unavailable: bool = False):
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.timeout = timeout
        self.unavailable = unavailable

    @asynccontextmanager
    async def hold(self, project_id: str) -> AsyncGenerator[None, None]:
        if self.unavailable:
            raise LockUnavailable("fake MySQL is down")
        lock = self._locks[project_id]
        try:
            await asyncio.wait_for(lock.acquire(), self.timeout)
        except TimeoutError:
            raise LockTimeout(project_id) from None
        try:
            yield
        finally:
            lock.release()


class FakeSaveLog:
    def __init__(self):
        self.entries: list[SaveLogEntry] = []

    async def record(self, entry: SaveLogEntry) -> None:
        self.entries.append(entry)


class FakeUpstream:
    """Holds one project. `put_outcomes` scripts each PUT: "ok", "504-applied" or "504-lost".
    `before_get` runs before each GET, to simulate someone else writing in between."""

    def __init__(self, project: Project, put_outcomes: list[str] | None = None,
                 before_get: Callable[["FakeUpstream", int], None] | None = None):
        self.project = project
        self.put_outcomes = list(put_outcomes or [])
        self.before_get = before_get
        self.gets = 0
        self.puts: list[dict] = []

    async def get_project(self, project_id: str) -> Project:
        if self.before_get:
            self.before_get(self, self.gets)
        self.gets += 1
        return self.project.model_copy(deep=True)

    async def put_project(self, project_id: str, body: dict) -> Project:
        self.puts.append(body)
        outcome = self.put_outcomes.pop(0) if self.put_outcomes else "ok"
        if outcome in ("ok", "504-applied"):
            self.project = Project.model_validate({**body, "id": self.project.id})
        if outcome.startswith("504"):
            raise UpstreamWriteUnknown("504")
        return self.project.model_copy(deep=True)
