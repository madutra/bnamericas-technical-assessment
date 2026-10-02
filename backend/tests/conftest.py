import random
from dataclasses import dataclass

import httpx
import pytest
from records_api.main import create_app as create_upstream_app

from app.config import Settings
from app.main import app, get_lock, get_save_log, get_settings, get_upstream
from app.upstream import UpstreamClient
from tests.fakes import FakeLock, FakeSaveLog

NO_EVENT = 0.99  # above every rate: not slow, no 504


class ScriptedRandom(random.Random):
    """Replaces the upstream's randomness. Each random() call pops the next scripted value.

    The upstream draws once per GET /projects/{id} (slow?), once per PUT (504?) and, after a 504, once
    more (applied?). Values below 0.1 trigger the event; below 0.5 on the last draw means "applied".
    """

    def __init__(self):
        super().__init__()
        self.script: list[float] = []

    def random(self) -> float:
        return self.script.pop(0) if self.script else NO_EVENT


@dataclass
class Harness:
    api: httpx.AsyncClient
    upstream: httpx.AsyncClient  # direct access, like the nightly job
    rng: ScriptedRandom
    log: FakeSaveLog
    lock: FakeLock


@pytest.fixture
async def harness():
    rng = ScriptedRandom()
    upstream_http = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_upstream_app(rng=rng)),
                                      base_url="http://upstream", headers={"X-Api-Key": "local-dev-key"})
    lock, log = FakeLock(), FakeSaveLog()
    app.dependency_overrides = {
        get_upstream: lambda: UpstreamClient(upstream_http),
        get_lock: lambda: lock,
        get_save_log: lambda: log,
        get_settings: lambda: Settings(save_attempts=3),
    }
    api = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://editor")
    yield Harness(api=api, upstream=upstream_http, rng=rng, log=log, lock=lock)
    app.dependency_overrides = {}
    await api.aclose()
    await upstream_http.aclose()
