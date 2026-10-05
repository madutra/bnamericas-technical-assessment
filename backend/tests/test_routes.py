"""Our app against the real upstream app, in-process, with its randomness scripted."""

import asyncio

import httpx

from app.main import app, get_upstream
from app.upstream import UpstreamClient

EDITABLE = ("name", "sector", "country", "stage", "key_dates", "linked_companies")


async def load(harness, project_id="P-1001") -> dict:
    response = await harness.api.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    return response.json()


def save_body(base: dict, **changes) -> dict:
    editable = {k: base[k] for k in EDITABLE}
    return {"base": editable, "proposed": {**editable, **changes}}


async def write_directly(harness, project_id: str, **changes):
    """What the nightly import does: PUT straight to the upstream, around our backend."""
    current = (await harness.upstream.get(f"/projects/{project_id}")).json()
    response = await harness.upstream.put(f"/projects/{project_id}", json={**current, **changes})
    assert response.status_code == 200


async def test_health(harness):
    assert (await harness.api.get("/health")).json() == {"status": "ok"}


async def test_list_returns_slim_rows(harness):
    rows = (await harness.api.get("/api/projects")).json()
    assert len(rows) == 30
    assert set(rows[0]) == {"id", "name", "sector", "country", "stage"}


async def test_get_one_drops_read_only_fields(harness):
    project = await load(harness)
    assert set(project) == {"id", *EDITABLE}


async def test_get_unknown_is_404(harness):
    response = await harness.api.get("/api/projects/P-9999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Project P-9999 not found"}


async def test_save_keeps_untouched_fields_and_read_only_fields(harness):
    base = await load(harness)
    before = (await harness.upstream.get("/projects/P-1001")).json()
    response = await harness.api.put("/api/projects/P-1001", json=save_body(base, name="Renamed"))
    assert response.status_code == 200
    after = (await harness.upstream.get("/projects/P-1001")).json()
    assert after == {**before, "name": "Renamed"}


async def test_different_fields_from_two_editors_both_survive(harness):
    base = await load(harness)
    first = await harness.api.put("/api/projects/P-1001", json=save_body(base, name="Ana's name"))
    second = await harness.api.put("/api/projects/P-1001", json=save_body(base, country="Peru"))
    assert first.status_code == second.status_code == 200
    assert (second.json()["name"], second.json()["country"]) == ("Ana's name", "Peru")


async def test_same_field_conflicts_and_the_second_saver_decides(harness):
    base = await load(harness)
    await harness.api.put("/api/projects/P-1001", json=save_body(base, name="First"))
    response = await harness.api.put("/api/projects/P-1001", json=save_body(base, name="Second", stage="cancelled"))
    assert response.status_code == 409
    body = response.json()
    assert [(c["slot"], c["mine"], c["theirs"]) for c in body["conflicts"]] == [("name", "Second", "First")]
    assert body["merged"]["stage"] == "cancelled"
    assert (await load(harness))["name"] == "First"  # nothing written

    # The second saver picks "mine" and resends against the new current.
    current = body["current"]
    resend = {"base": {k: current[k] for k in EDITABLE}, "proposed": {**body["merged"], "name": "Second"}}
    response = await harness.api.put("/api/projects/P-1001", json=resend)
    assert response.status_code == 200
    assert (response.json()["name"], response.json()["stage"]) == ("Second", "cancelled")


async def test_different_key_dates_from_two_editors_both_survive(harness):
    base = await load(harness)
    first_label, second_label = base["key_dates"][0]["label"], base["key_dates"][1]["label"]

    def redated(label, new_date):
        return [{**kd, "date": new_date} if kd["label"] == label else kd for kd in base["key_dates"]]

    await harness.api.put("/api/projects/P-1001", json=save_body(base, key_dates=redated(first_label, "2030-01-01")))
    response = await harness.api.put("/api/projects/P-1001",
                                     json=save_body(base, key_dates=redated(second_label, "2031-01-01")))
    assert response.status_code == 200
    stored = {kd["label"]: kd["date"] for kd in response.json()["key_dates"]}
    assert (stored[first_label], stored[second_label]) == ("2030-01-01", "2031-01-01")


async def test_two_editors_renaming_the_same_key_date_conflict_instead_of_duplicating_it(harness):
    base = await load(harness)
    first = base["key_dates"][0]
    rest = base["key_dates"][1:]

    def rename(to):
        return save_body(base, key_dates=[{**first, "label": to}, *rest])

    assert (await harness.api.put("/api/projects/P-1001", json=rename("Renamed by A"))).status_code == 200
    response = await harness.api.put("/api/projects/P-1001", json=rename("Renamed by B"))
    assert response.status_code == 409
    [conflict] = response.json()["conflicts"]
    assert (conflict["key"], conflict["mine"]["label"], conflict["theirs"]["label"]) == (
        first["label"], "Renamed by B", "Renamed by A")
    assert len((await load(harness))["key_dates"]) == len(base["key_dates"])


async def test_nightly_job_write_is_not_overwritten(harness):
    base = await load(harness)
    await write_directly(harness, "P-1001", stage="cancelled")
    response = await harness.api.put("/api/projects/P-1001", json=save_body(base, name="Mine"))
    assert response.status_code == 200
    assert (response.json()["name"], response.json()["stage"]) == ("Mine", "cancelled")


async def test_duplicate_labels_written_by_the_nightly_job_survive_an_unrelated_edit(harness):
    current = (await harness.upstream.get("/projects/P-1001")).json()
    duplicated = [*current["key_dates"], {**current["key_dates"][0], "date": "2031-05-05"}]
    await write_directly(harness, "P-1001", key_dates=duplicated)
    base = await load(harness)
    response = await harness.api.put("/api/projects/P-1001", json=save_body(base, name="Mine"))
    assert response.status_code == 200
    assert len(response.json()["key_dates"]) == len(duplicated)


async def test_linked_companies_are_editable_and_merge_with_other_changes(harness):
    base = await load(harness)
    companies = [*base["linked_companies"], {"name": "Nueva Ingenieria SAS", "role": "consultant"}]
    first = await harness.api.put("/api/projects/P-1001", json=save_body(base, linked_companies=companies))
    second = await harness.api.put("/api/projects/P-1001", json=save_body(base, stage="cancelled"))
    assert first.status_code == second.status_code == 200
    stored = (await harness.upstream.get("/projects/P-1001")).json()
    assert {"name": "Nueva Ingenieria SAS", "role": "consultant"} in stored["linked_companies"]
    assert stored["stage"] == "cancelled"


async def test_same_company_role_changed_by_two_editors_conflicts(harness):
    base = await load(harness)
    target = base["linked_companies"][0]

    def with_role(role):
        changed = [{**c, "role": role} if c == target else c for c in base["linked_companies"]]
        return save_body(base, linked_companies=changed)

    roles = [r for r in ("owner", "developer", "consultant") if r != target["role"]]
    assert (await harness.api.put("/api/projects/P-1001", json=with_role(roles[0]))).status_code == 200
    response = await harness.api.put("/api/projects/P-1001", json=with_role(roles[1]))
    assert response.status_code == 409
    [conflict] = response.json()["conflicts"]
    assert (conflict["field"], conflict["key"]) == ("linked_companies", target["name"])


async def test_creating_duplicate_company_names_is_rejected(harness):
    base = await load(harness)
    duplicated = [*base["linked_companies"], {**base["linked_companies"][0], "role": "consultant"}]
    response = await harness.api.put("/api/projects/P-1001", json=save_body(base, linked_companies=duplicated))
    assert response.status_code == 422
    assert "Linked company names must be unique" in response.json()["detail"]


async def test_creating_duplicate_labels_is_rejected(harness):
    base = await load(harness)
    duplicated = [*base["key_dates"], base["key_dates"][0]]
    response = await harness.api.put("/api/projects/P-1001", json=save_body(base, key_dates=duplicated))
    assert response.status_code == 422
    assert "unique" in response.json()["detail"]


async def test_invalid_values_are_422_with_a_readable_message(harness):
    base = await load(harness)
    response = await harness.api.put("/api/projects/P-1001", json=save_body(base, sector="space", name="  "))
    assert response.status_code == 422
    assert "proposed.sector" in response.json()["detail"]
    assert "proposed.name" in response.json()["detail"]


async def test_save_unknown_project_is_404(harness):
    base = await load(harness)
    response = await harness.api.put("/api/projects/P-9999", json=save_body(base, name="x"))
    assert response.status_code == 404


async def test_504_that_landed_is_confirmed(harness):
    base = await load(harness)
    # GET (not slow), PUT (504), applied, then the re-read GET (not slow).
    harness.rng.script = [0.99, 0.0, 0.0]
    response = await harness.api.put("/api/projects/P-1001", json=save_body(base, name="Mine"))
    assert response.status_code == 200
    assert response.json()["name"] == "Mine"
    assert (harness.log.entries[0].outcome, harness.log.entries[0].attempts) == ("saved", 2)


async def test_504_that_was_lost_is_retried(harness):
    base = await load(harness)
    harness.rng.script = [0.99, 0.0, 0.99]  # GET, PUT 504, not applied; then GET + PUT succeed
    response = await harness.api.put("/api/projects/P-1001", json=save_body(base, name="Mine"))
    assert response.status_code == 200
    assert (await load(harness))["name"] == "Mine"


async def test_504_every_time_is_reported_as_unconfirmed(harness):
    base = await load(harness)
    harness.rng.script = [0.99, 0.0, 0.99] * 3
    response = await harness.api.put("/api/projects/P-1001", json=save_body(base, name="Mine"))
    assert response.status_code == 504
    assert "could not be confirmed" in response.json()["detail"]


async def test_lock_busy_is_503_with_retry_after(harness):
    base = await load(harness)
    harness.lock.timeout = 0.01
    async with harness.lock.hold("P-1001"):
        response = await harness.api.put("/api/projects/P-1001", json=save_body(base, name="Mine"))
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "2"


async def test_lock_store_down_blocks_saves_but_not_reads(harness):
    base = await load(harness)
    harness.lock.unavailable = True
    assert (await harness.api.put("/api/projects/P-1001", json=save_body(base, name="x"))).status_code == 503
    assert (await harness.api.get("/api/projects/P-1001")).status_code == 200


async def test_concurrent_saves_of_different_fields_through_the_lock_both_survive(harness):
    base = await load(harness)
    responses = await asyncio.gather(
        harness.api.put("/api/projects/P-1001", json=save_body(base, name="Mine")),
        harness.api.put("/api/projects/P-1001", json=save_body(base, country="Peru")),
    )
    assert [r.status_code for r in responses] == [200, 200]
    stored = await load(harness)
    assert (stored["name"], stored["country"]) == ("Mine", "Peru")


async def test_upstream_down_is_502(harness):
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    down = UpstreamClient(httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url="http://upstream"))
    app.dependency_overrides[get_upstream] = lambda: down
    response = await harness.api.get("/api/projects")
    assert response.status_code == 502
    assert response.json() == {"detail": "The records service is unavailable. Try again shortly."}
