import random

import pytest
from fastapi.testclient import TestClient

from records_api.main import API_KEY, create_app

HEADERS = {"X-Api-Key": API_KEY}
EDITABLE = {"name", "sector", "country", "stage", "key_dates", "linked_companies"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("UPSTREAM_SLOW_RATE", "0")
    monkeypatch.setenv("UPSTREAM_TIMEOUT_RATE", "0")
    return TestClient(create_app())


def editable_body(project: dict) -> dict:
    return {k: project[k] for k in EDITABLE}


def test_rejects_missing_or_wrong_api_key(client):
    assert client.get("/projects").status_code == 401
    assert client.get("/projects", headers={"X-Api-Key": "nope"}).status_code == 401


def test_lists_about_thirty_seeded_projects(client):
    response = client.get("/projects", headers=HEADERS)
    assert response.status_code == 200
    projects = response.json()
    assert isinstance(projects, list)
    assert len(projects) == 30


def test_seed_is_deterministic_across_restarts(monkeypatch):
    monkeypatch.setenv("UPSTREAM_SLOW_RATE", "0")
    first = TestClient(create_app()).get("/projects", headers=HEADERS).json()
    second = TestClient(create_app()).get("/projects", headers=HEADERS).json()
    assert first == second


def test_responses_carry_many_more_fields_than_the_editable_ones(client):
    project = client.get("/projects", headers=HEADERS).json()[0]
    assert EDITABLE <= project.keys()
    assert len(project.keys() - EDITABLE - {"id"}) >= 15


def test_has_no_version_or_modification_timestamp(client):
    project = client.get("/projects", headers=HEADERS).json()[0]
    forbidden = {"version", "etag", "updated_at", "modified_at", "last_modified", "revision"}
    assert not forbidden & project.keys()


def test_get_one_and_unknown_id(client):
    project_id = client.get("/projects", headers=HEADERS).json()[0]["id"]
    assert client.get(f"/projects/{project_id}", headers=HEADERS).json()["id"] == project_id
    assert client.get("/projects/P-0000", headers=HEADERS).status_code == 404


def test_put_replaces_nested_lists_entirely(client):
    project = client.get("/projects", headers=HEADERS).json()[0]
    assert len(project["key_dates"]) >= 2
    body = editable_body(project)
    body["key_dates"] = [{"label": "Only date", "date": "2030-01-01"}]
    saved = client.put(f"/projects/{project['id']}", json=body, headers=HEADERS).json()
    assert saved["key_dates"] == [{"label": "Only date", "date": "2030-01-01"}]


def test_last_write_wins_silently(client):
    project = client.get("/projects", headers=HEADERS).json()[0]
    first, second = editable_body(project), editable_body(project)
    first["name"] = "Edited by Ana"
    second["country"] = "Peru"
    assert client.put(f"/projects/{project['id']}", json=first, headers=HEADERS).status_code == 200
    assert client.put(f"/projects/{project['id']}", json=second, headers=HEADERS).status_code == 200
    stored = client.get(f"/projects/{project['id']}", headers=HEADERS).json()
    assert stored["name"] == project["name"]  # Ana's edit is gone
    assert stored["country"] == "Peru"


def test_put_ignores_read_only_fields(client):
    project = client.get("/projects", headers=HEADERS).json()[0]
    body = editable_body(project) | {"internal_code": "HACKED"}
    saved = client.put(f"/projects/{project['id']}", json=body, headers=HEADERS).json()
    assert saved["internal_code"] == project["internal_code"]


def test_put_validates_editable_fields(client):
    project = client.get("/projects", headers=HEADERS).json()[0]
    body = editable_body(project)
    del body["name"]
    assert client.put(f"/projects/{project['id']}", json=body, headers=HEADERS).status_code == 422
    body = editable_body(project) | {"stage": "not-a-stage"}
    assert client.put(f"/projects/{project['id']}", json=body, headers=HEADERS).status_code == 422


def test_put_unknown_id_is_404(client):
    project = client.get("/projects", headers=HEADERS).json()[0]
    response = client.put("/projects/P-0000", json=editable_body(project), headers=HEADERS)
    assert response.status_code == 404


class FixedRandom(random.Random):
    """random() returns the given values in turn, so each flaky path can be forced."""

    def __init__(self, *values: float):
        super().__init__()
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0)


def flaky_client(monkeypatch, *values: float) -> TestClient:
    monkeypatch.setenv("UPSTREAM_SLOW_RATE", "0")
    monkeypatch.setenv("UPSTREAM_TIMEOUT_RATE", "0.1")
    return TestClient(create_app(rng=FixedRandom(*values)))


def test_timed_out_put_can_still_apply(monkeypatch):
    client = flaky_client(monkeypatch, 0.0, 0.0)  # time out, and apply
    project = client.get("/projects/P-1001", headers=HEADERS).json()
    body = editable_body(project) | {"name": "Applied anyway"}
    assert client.put(f"/projects/{project['id']}", json=body, headers=HEADERS).status_code == 504
    assert client.get(f"/projects/{project['id']}", headers=HEADERS).json()["name"] == "Applied anyway"


def test_timed_out_put_can_be_lost(monkeypatch):
    client = flaky_client(monkeypatch, 0.0, 0.9)  # time out, and do not apply
    project = client.get("/projects/P-1001", headers=HEADERS).json()
    body = editable_body(project) | {"name": "Never stored"}
    assert client.put(f"/projects/{project['id']}", json=body, headers=HEADERS).status_code == 504
    assert client.get(f"/projects/{project['id']}", headers=HEADERS).json()["name"] == project["name"]


def test_put_succeeds_when_no_timeout_is_drawn(monkeypatch):
    client = flaky_client(monkeypatch, 0.5)
    project = client.get("/projects/P-1001", headers=HEADERS).json()
    body = editable_body(project) | {"name": "Fine"}
    assert client.put(f"/projects/{project['id']}", json=body, headers=HEADERS).status_code == 200
