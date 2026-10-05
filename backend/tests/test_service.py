import asyncio

import pytest

from app.locking import LockTimeout, LockUnavailable
from app.schemas import Project, SaveRequest
from app.service import SaveConflict, SaveUnconfirmed, save_project
from tests.fakes import FakeLock, FakeSaveLog, FakeUpstream

STORED = {
    "id": "P-1", "name": "Original", "sector": "energy", "country": "Chile", "stage": "idea",
    "key_dates": [{"label": "Tender launch", "date": "2026-01-10"}],
    "linked_companies": [{"name": "Varelo Energia SA", "role": "owner"}],
}


def stored(**overrides) -> Project:
    return Project.model_validate({**STORED, **overrides})


def request(**proposed) -> SaveRequest:
    base = stored().editable().model_dump(mode="json")
    return SaveRequest.model_validate({"base": base, "proposed": {**base, **proposed}})


async def save(upstream, req, lock=None, log=None, attempts=3):
    return await save_project("P-1", req, upstream=upstream, lock=lock or FakeLock(), log=log or FakeSaveLog(),
                              attempts=attempts)


async def test_saves_my_change_and_keeps_linked_companies():
    upstream, log = FakeUpstream(stored()), FakeSaveLog()
    result = await save(upstream, request(name="Mine"), log=log)
    assert result.name == "Mine"
    assert upstream.puts[0]["linked_companies"] == [{"name": "Varelo Energia SA", "role": "owner"}]
    [entry] = log.entries
    assert (entry.outcome, entry.attempts, entry.changed_slots) == ("saved", 1, ["name"])


async def test_merges_onto_a_concurrent_change_of_another_field():
    upstream = FakeUpstream(stored(country="Peru"))
    result = await save(upstream, request(name="Mine"))
    assert (result.name, result.country) == ("Mine", "Peru")


async def test_nothing_to_write_does_not_put():
    upstream, log = FakeUpstream(stored()), FakeSaveLog()
    await save(upstream, request(), log=log)
    assert upstream.puts == []
    assert log.entries[0].outcome == "noop"


async def test_conflict_raises_409_and_writes_nothing():
    upstream, log = FakeUpstream(stored(name="Theirs")), FakeSaveLog()
    with pytest.raises(SaveConflict) as exc:
        await save(upstream, request(name="Mine"), log=log)
    assert exc.value.response.current.name == "Theirs"
    assert [c.slot for c in exc.value.response.conflicts] == ["name"]
    assert upstream.puts == []
    assert log.entries[0].outcome == "conflict"


async def test_504_that_landed_is_confirmed_by_the_reread_without_a_second_put():
    upstream, log = FakeUpstream(stored(), put_outcomes=["504-applied"]), FakeSaveLog()
    result = await save(upstream, request(name="Mine"), log=log)
    assert result.name == "Mine"
    assert len(upstream.puts) == 1 and upstream.gets == 2
    assert (log.entries[0].outcome, log.entries[0].attempts, log.entries[0].changed_slots) == ("saved", 2, ["name"])


async def test_504_that_was_lost_is_written_again():
    upstream = FakeUpstream(stored(), put_outcomes=["504-lost", "ok"])
    result = await save(upstream, request(name="Mine"))
    assert result.name == "Mine"
    assert len(upstream.puts) == 2


async def test_504_then_someone_else_wrote_is_merged_not_overwritten():
    def nightly_job(fake: FakeUpstream, get_number: int):
        if get_number == 1:  # between our lost PUT and the re-read
            fake.project = fake.project.model_copy(update={"stage": "financing"})

    upstream = FakeUpstream(stored(), put_outcomes=["504-lost", "ok"], before_get=nightly_job)
    result = await save(upstream, request(name="Mine"))
    assert (result.name, result.stage) == ("Mine", "financing")


async def test_gives_up_after_the_configured_attempts():
    upstream, log = FakeUpstream(stored(), put_outcomes=["504-lost"] * 3), FakeSaveLog()
    with pytest.raises(SaveUnconfirmed):
        await save(upstream, request(name="Mine"), log=log, attempts=3)
    assert len(upstream.puts) == 3
    assert (log.entries[0].outcome, log.entries[0].attempts) == ("unconfirmed", 3)


async def test_lock_timeout_is_logged_and_raised():
    lock, log = FakeLock(timeout=0.01), FakeSaveLog()
    async with lock.hold("P-1"):  # someone else is saving
        with pytest.raises(LockTimeout):
            await save(FakeUpstream(stored()), request(name="Mine"), lock=lock, log=log)
    assert log.entries[0].outcome == "lock_timeout"


async def test_lock_unavailable_blocks_the_save():
    upstream, log = FakeUpstream(stored()), FakeSaveLog()
    with pytest.raises(LockUnavailable):
        await save(upstream, request(name="Mine"), lock=FakeLock(unavailable=True), log=log)
    assert upstream.gets == 0
    assert log.entries[0].outcome == "lock_unavailable"


async def test_two_concurrent_saves_are_serialized_and_both_survive():
    upstream, lock = FakeUpstream(stored()), FakeLock()
    await asyncio.gather(save(upstream, request(name="Mine"), lock=lock),
                         save(upstream, request(country="Peru"), lock=lock))
    assert (upstream.project.name, upstream.project.country) == ("Mine", "Peru")


async def test_two_users_editing_same_key_date_label_concurrently_one_conflicts():
    lock = FakeLock()
    upstream = FakeUpstream(stored())
    req_a = request(key_dates=[{"label": "Tender launch", "date": "2026-02-01"}])
    req_b = request(key_dates=[{"label": "Tender launch", "date": "2026-03-01"}])
    results = await asyncio.gather(
        save(upstream, req_a, lock=lock),
        save(upstream, req_b, lock=lock),
        return_exceptions=True,
    )
    successes = [r for r in results if isinstance(r, Project)]
    conflicts = [r for r in results if isinstance(r, SaveConflict)]
    assert len(successes) == 1 and len(conflicts) == 1
    [conflict] = conflicts[0].response.conflicts
    assert conflict.slot == "key_dates[Tender launch]"


async def test_log_failure_does_not_fail_the_save():
    class FailingSaveLog:
        async def record(self, entry) -> None:
            raise RuntimeError("DB is down")

    upstream = FakeUpstream(stored())
    result = await save(upstream, request(name="Mine"), log=FailingSaveLog())
    assert result.name == "Mine"
