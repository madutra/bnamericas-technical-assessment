"""The upstream records API. Candidates treat this as owned by another team and do not change it."""

import asyncio
import copy
import os
import random
from datetime import date
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from records_api.seed import COMPANY_ROLES, SECTORS, STAGES, build_projects

API_KEY = "local-dev-key"
SLOW_SECONDS = 2.0
DEFAULT_SLOW_RATE = 0.1
DEFAULT_TIMEOUT_RATE = 0.1

Sector = Literal[tuple(SECTORS)]  # type: ignore[valid-type]
Stage = Literal[tuple(STAGES)]  # type: ignore[valid-type]
CompanyRole = Literal[tuple(COMPANY_ROLES)]  # type: ignore[valid-type]


class KeyDate(BaseModel):
    label: str = Field(min_length=1)
    date: date


class LinkedCompany(BaseModel):
    name: str = Field(min_length=1)
    role: CompanyRole


class ProjectUpdate(BaseModel):
    """Only these fields can be written. Anything else in the body is ignored."""

    name: str = Field(min_length=1)
    sector: Sector
    country: str = Field(min_length=1)
    stage: Stage
    key_dates: list[KeyDate]
    linked_companies: list[LinkedCompany]


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Api-Key")


def create_app(rng: random.Random | None = None) -> FastAPI:
    rng = rng or random.Random()
    store = build_projects()
    slow_rate = float(os.environ.get("UPSTREAM_SLOW_RATE", DEFAULT_SLOW_RATE))
    timeout_rate = float(os.environ.get("UPSTREAM_TIMEOUT_RATE", DEFAULT_TIMEOUT_RATE))
    app = FastAPI(title="Records API (upstream)", version="1.0.0", dependencies=[Depends(require_api_key)])

    def find(project_id: str) -> dict:
        if project_id not in store:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return store[project_id]

    @app.get("/projects")
    def list_projects() -> list[dict]:
        return [copy.deepcopy(p) for p in store.values()]

    @app.get("/projects/{project_id}")
    async def get_project(project_id: str) -> dict:
        if slow_rate > 0 and rng.random() < slow_rate:
            await asyncio.sleep(SLOW_SECONDS)
        return copy.deepcopy(find(project_id))

    @app.put("/projects/{project_id}")
    def replace_project(project_id: str, update: ProjectUpdate) -> dict:
        project = find(project_id)
        if timeout_rate > 0 and rng.random() < timeout_rate:
            # Like a gateway timing out: the caller cannot tell whether the write landed.
            if rng.random() < 0.5:
                project.update(update.model_dump(mode="json"))
            raise HTTPException(status_code=504, detail="Gateway timeout")
        project.update(update.model_dump(mode="json"))
        return copy.deepcopy(project)

    return app


def run() -> None:
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.environ.get("UPSTREAM_PORT", "8081")))
