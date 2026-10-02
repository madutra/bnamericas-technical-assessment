"""The only code that talks HTTP to the upstream records API. Turns its habits into exceptions."""

import httpx

from app.config import Settings
from app.schemas import Project, ProjectSummary


class UpstreamError(Exception):
    pass


class UpstreamNotFound(UpstreamError):
    pass


class UpstreamRejected(UpstreamError):
    """422: the upstream refused the values."""


class UpstreamWriteUnknown(UpstreamError):
    """A PUT answered 504 or timed out: it may or may not have been applied. Re-read to find out."""


class UpstreamUnavailable(UpstreamError):
    pass


def _validation_message(response: httpx.Response) -> str:
    try:
        errors = response.json()["detail"]
        return "; ".join(f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in errors)
    except (ValueError, KeyError, TypeError):
        return response.text


class UpstreamClient:
    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    @classmethod
    def from_settings(cls, settings: Settings) -> "UpstreamClient":
        return cls(
            httpx.AsyncClient(
                base_url=settings.upstream_url,
                headers={"X-Api-Key": settings.upstream_api_key},
                timeout=settings.upstream_timeout_seconds,
            )
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def list_projects(self) -> list[ProjectSummary]:
        response = await self._request("GET", "/projects")
        return [ProjectSummary.model_validate(p) for p in response.json()]

    async def get_project(self, project_id: str) -> Project:
        response = await self._request("GET", f"/projects/{project_id}")
        return Project.model_validate(response.json())

    async def put_project(self, project_id: str, body: dict) -> Project:
        try:
            response = await self._http.put(f"/projects/{project_id}", json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Never reached the upstream: nothing was written.
            raise UpstreamUnavailable(str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise UpstreamWriteUnknown("Timed out waiting for the upstream") from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(str(exc)) from exc
        if response.status_code == 504:
            raise UpstreamWriteUnknown("Upstream answered 504")
        self._raise_for_status(response, project_id)
        return Project.model_validate(response.json())

    async def _request(self, method: str, path: str) -> httpx.Response:
        try:
            response = await self._http.request(method, path)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(str(exc) or type(exc).__name__) from exc
        self._raise_for_status(response, path.rsplit("/", 1)[-1])
        return response

    @staticmethod
    def _raise_for_status(response: httpx.Response, project_id: str) -> None:
        if response.status_code == 404:
            raise UpstreamNotFound(f"Project {project_id} not found")
        if response.status_code == 422:
            raise UpstreamRejected(_validation_message(response))
        if response.is_error:
            raise UpstreamUnavailable(f"Upstream answered {response.status_code}")
