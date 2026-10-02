import httpx
import pytest

from app.upstream import (UpstreamClient, UpstreamNotFound, UpstreamRejected, UpstreamUnavailable,
                          UpstreamWriteUnknown)

PROJECT = {
    "id": "P-1", "name": "Project", "sector": "energy", "country": "Chile", "stage": "idea",
    "key_dates": [{"label": "Tender launch", "date": "2026-01-10"}],
    "linked_companies": [{"name": "Varelo Energia SA", "role": "owner"}],
    "internal_code": "IC-1", "region": "north", "latitude": -30.1,  # read-only extras
}


def client(handler) -> UpstreamClient:
    return UpstreamClient(httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://upstream",
                                            headers={"X-Api-Key": "k"}))


async def test_sends_the_api_key_and_drops_read_only_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers["X-Api-Key"]
        return httpx.Response(200, json=PROJECT)

    project = await client(handler).get_project("P-1")
    assert seen["key"] == "k"
    assert "internal_code" not in project.model_dump()
    assert project.linked_companies[0].role == "owner"


async def test_list_returns_summaries():
    summaries = await client(lambda r: httpx.Response(200, json=[PROJECT])).list_projects()
    assert summaries[0].model_dump() == {"id": "P-1", "name": "Project", "sector": "energy",
                                         "country": "Chile", "stage": "idea"}


@pytest.mark.parametrize(("status", "error"), [(404, UpstreamNotFound), (500, UpstreamUnavailable),
                                               (401, UpstreamUnavailable)])
async def test_get_errors(status, error):
    with pytest.raises(error):
        await client(lambda r: httpx.Response(status, json={"detail": "x"})).get_project("P-1")


async def test_get_network_failure_is_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(UpstreamUnavailable):
        await client(handler).get_project("P-1")


async def test_put_504_is_unknown_not_failed():
    with pytest.raises(UpstreamWriteUnknown):
        await client(lambda r: httpx.Response(504, json={"detail": "Gateway timeout"})).put_project("P-1", {})


async def test_put_read_timeout_is_unknown():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(UpstreamWriteUnknown):
        await client(handler).put_project("P-1", {})


async def test_put_connect_error_is_unavailable_because_nothing_was_sent():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(UpstreamUnavailable):
        await client(handler).put_project("P-1", {})


async def test_put_422_carries_a_readable_message():
    body = {"detail": [{"loc": ["body", "sector"], "msg": "Input should be 'energy' or 'mining'"}]}
    with pytest.raises(UpstreamRejected, match="sector: Input should be"):
        await client(lambda r: httpx.Response(422, json=body)).put_project("P-1", {})


async def test_put_returns_the_stored_project():
    project = await client(lambda r: httpx.Response(200, json=PROJECT)).put_project("P-1", {})
    assert project.id == "P-1"
