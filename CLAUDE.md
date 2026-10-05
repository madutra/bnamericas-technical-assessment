# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
It is the **spec** the code was built from and must keep matching. Where this file says "must", keep it that
way; if something here looks wrong once you are in the code, stop and say so instead of deviating silently.

## What this repo is

A hiring challenge (BNamericas): a project-record editor that sits in front of an **upstream records API
owned by another team**. The original brief is in `BRIEF.md`; the upstream's contract and habits are in
`upstream/README.md` and `upstream/records_api/main.py`. `README.md`, `DECISIONS.md` and `AI-TRAIL.md`
are ours.

## Working style

- The code will be extended live in an interview: prefer small modules, plain functions and obvious names
  over clever abstractions.
- Build in small steps and run the tests after each one. Do not commit unless asked.

## Pieces

| Folder | What | Port |
|---|---|---|
| `upstream/` | Third-party API (FastAPI, in-memory, ~30 seeded projects, resets on restart). **Read-only.** | 8081 |
| `backend/` | Our FastAPI service between the browser and the upstream | 8000 |
| `frontend/` | React + TypeScript + MUI, built with Vite | 4000 |
| MySQL 8 | Shared lock + save log for our backend instances (see below). Never holds project data | 3306 |

## Hard rules

- **The browser never calls the upstream directly.** All traffic: frontend → `backend/` → upstream. The
  upstream API key lives only in the backend.
- **Never modify anything in `upstream/`.** Work around its behaviour in `backend/`.
- The backend must be correct as **3 instances behind a load balancer**, while a **nightly import job
  writes to the upstream directly**. So: no in-process locks, caches or per-instance state as a source of
  truth. **The upstream is the only source of truth for project data.** MySQL holds only coordination
  (locks) and history (save log), never project fields.

## Upstream behaviour the backend must handle

- **Last write wins silently.** No version, ETag or timestamp. Concurrency protection is ours to build.
- **`PUT` replaces everything.** All editable fields are required (`name`, `sector`, `country`, `stage`,
  `key_dates`, `linked_companies`) and both lists are replaced wholesale. Every save must merge onto the
  current record before sending.
- **~10% of `GET /projects/{id}` take ~2 s.** `GET /projects` (list) is never slow.
- **~10% of `PUT`s answer `504`, and the write may or may not have landed (50/50).** A 504 means
  "unknown", not "failed". Re-read to find out.
- `PUT` validates enums and non-empty strings (`422`); read-only fields in the body are ignored.
- Responses carry ~15 read-only fields the editor does not need.

## Concurrency design (decided)

### Three-way merge per field

The browser sends `{base, proposed}`: `base` is the version it loaded, `proposed` is the edited form.
On save the backend reads the upstream **now** (`theirs`) and merges slot by slot:

| base → mine | base → theirs | Result |
|---|---|---|
| unchanged | any | theirs |
| changed | unchanged | mine |
| changed | changed to the same value | that value |
| changed | changed to a different value | **conflict** |

`merged` = theirs + every non-conflicting change of mine. Any conflict → **409**, nothing written. The
nightly job needs no special case: its writes are simply "theirs".

### Slots, and what "the same field" means for key dates

- Each scalar field (`name`, `sector`, `country`, `stage`) is one slot.
- **Each key date is one slot, identified by its label in `base`** (or its own label if it is new).
  Labels are compared exactly after trimming surrounding whitespace (case-sensitive: "Tender launch" ≠
  "tender launch").
- A slot's value is the whole key date (label + date), or "absent". So re-dating two different labels
  never conflicts; re-dating vs deleting the same label does.
- **Renames keep the slot.** On each side (`mine` and `theirs`, separately), a base label that disappeared
  is paired with a new label carrying **the same date**, if that pairing is unique both ways
  (`find_renames`). Two people renaming the same date differently therefore conflict instead of producing
  two dates; rename vs re-date or delete of the same date conflicts too. Renaming *and* re-dating at once is
  not paired: it is a new date plus a removal. Ambiguous cases (several candidates with the same date) are
  not paired either. The pairing is inferred from the data, so it also catches the nightly job's renames.
- If a merge would still produce duplicate labels (e.g. I renamed to a label they just added), the merge
  is redone with the whole list as one slot (below).
- **Duplicate labels** (the upstream allows them, e.g. via the nightly import): if `base`, `proposed` or
  `theirs` has a duplicated label, the whole `key_dates` list becomes **one slot**, compared as a whole,
  so duplicates are never collapsed or dropped. Our API must not *create* duplicates: reject `proposed`
  with duplicate labels unless `proposed.key_dates` equals `base.key_dates` (untouched stored duplicates).
- **Order:** `merged.key_dates` is always sorted by `(date, label)`. Compare lists in sorted form, so an
  order-only difference is never a change.
- **Linked companies follow the same rules, keyed by company name** (trimmed, case-sensitive). The slot
  value is the company (name + role), so changing the role of the same company concurrently conflicts,
  while changes to different companies merge. A rename (e.g. fixing a typo in the name) is paired by
  **role**, as key-date renames are paired by date. The same company twice (two roles) makes the whole
  companies list one slot; our API rejects *new* duplicate names (`Linked company names must be unique`).
  Companies are sorted by `(name, role)`. Both lists share one implementation (`ListField` in `merge.py`).

### Save algorithm (`PUT /api/projects/{id}`)

1. Validate the request (Pydantic). Trim text fields and labels.
2. Acquire the **MySQL named lock** for this project (below). Timeout → **503** with `Retry-After`.
3. `GET` the upstream → `theirs`.
4. Merge. Conflicts → **409** with the conflict body. Nothing left to change → return `theirs` (200, no PUT).
5. `PUT` the merged record (every editable field, including both lists).
6. On `504` or our own HTTP timeout on the PUT: go back to step 3 (re-read, re-merge). If our write
   landed, the merge finds nothing to do and the save succeeds; if it was lost, we write again; if
   someone else wrote meanwhile, the merge sees it. At most `EDITOR_SAVE_ATTEMPTS` (default 3) rounds,
   then **504** "could not be confirmed, reload".
7. Release the lock (always, in `finally`). Write one `save_log` row (best effort: a failing log write
   is logged, never fails the save).

### MySQL: lock and save log

- **Lock:** `SELECT GET_LOCK('editor:project:<id>', <timeout>)` / `RELEASE_LOCK(...)` on one dedicated
  connection held for the whole save (a named lock belongs to its connection; if the instance dies the
  connection drops and MySQL frees the lock). Default timeout 5 s. This serializes saves across our 3
  instances, closing the read-then-write window **between our own editors**. It does **not** protect
  against the nightly job — only an upstream version/`If-Match` could. Say so in `DECISIONS.md`.
- **Fail closed on the lock:** any failure while taking the lock (network, auth, driver) is
  `LockUnavailable` → 503, never a 500. Reads (list/get) do not touch
  MySQL and keep working.
- **`save_log` table:** `id`, `project_id`, `outcome` (`saved`, `noop`, `conflict`, `unconfirmed`,
  `rejected`, `not_found`, `lock_timeout`, `lock_unavailable`, `upstream_error`), `changed_slots` (JSON), `attempts`, `duration_ms`,
  `instance_id`, `created_at`. Created at startup if missing (`CREATE TABLE IF NOT EXISTS`); no migration
  tool (cut).
- Access through SQLAlchemy 2 async Core + `aiomysql`. Keep it behind small interfaces (`ProjectLock`,
  `SaveLog`) so unit tests use in-memory fakes.

## Backend (`backend/`) — target layout

Python ≥ 3.11, managed with `uv` (`pyproject.toml`, `uv.lock`, `.venv`). FastAPI, httpx (async),
pydantic-settings, SQLAlchemy async + aiomysql (+ `cryptography`, required by MySQL 8's default
`caching_sha2_password` auth whenever the user has a password). Tests: pytest + pytest-asyncio.

- `app/config.py` — settings from env vars prefixed `EDITOR_` or `backend/.env`: `EDITOR_UPSTREAM_URL`
  (default `http://127.0.0.1:8081`), `EDITOR_UPSTREAM_API_KEY`, `EDITOR_UPSTREAM_TIMEOUT_SECONDS`
  (default 5, must exceed the 2 s slow GET), `EDITOR_SAVE_ATTEMPTS` (3), `EDITOR_DATABASE_URL`
  (`mysql+aiomysql://...`), `EDITOR_LOCK_TIMEOUT_SECONDS` (5), `EDITOR_INSTANCE_ID`.
- `app/upstream.py` — `UpstreamClient`, the **only** code that talks HTTP to the upstream. Injects
  `X-Api-Key`. Maps responses to exceptions: `UpstreamNotFound` (404), `UpstreamRejected` (422),
  `UpstreamWriteUnknown` (PUT 504 or our timeout on a PUT), `UpstreamUnavailable` (anything else).
- `app/schemas.py` — Pydantic models for what the browser sees. Validating upstream payloads through them
  drops the read-only fields. `KeyDate`, `LinkedCompany`, `EditableProject` (name, sector, country,
  stage, key_dates, linked_companies), `Project` (+ `id`), `ProjectSummary` (list row: id, name, sector, country,
  stage), `SaveRequest` (`{base, proposed}`), `Conflict` (`slot`, `field`, `key`, `base`, `mine`, `theirs`),
  `ConflictResponse` (`current`, `merged`, `conflicts`).
- `app/merge.py` — **pure functions**, no I/O: split a project into slots, three-way merge, rebuild a
  project from slots. Conflict slot names: `name`, `sector`, `country`, `stage`, `key_dates[<label>]`,
  `linked_companies[<name>]`, or `key_dates` / `linked_companies` for a whole-list fallback. Each
  `Conflict` also carries `field` and `key` (the item's identity in `base`), so the frontend never parses
  slot names.
- `app/locking.py` — `ProjectLock`/`SaveLog` protocols, their MySQL versions (`MySQLProjectLock`,
  `MySQLSaveLog`) and the table definition. Fakes for tests live in `tests/fakes.py`.
- `app/service.py` — `save_project(...)`: the algorithm above. Depends on the client, lock and log
  passed in, so it is testable with fakes.
- `app/main.py` — routes and exception handlers. One `UpstreamClient` and one DB engine per process,
  created in `lifespan`, stored on `app.state`, injected with `Depends(...)` (tests swap them via
  `app.dependency_overrides`).

### HTTP API (all under `/api`, plus `GET /health`)

| Route | Success | Errors |
|---|---|---|
| `GET /api/projects` | `ProjectSummary[]` | 502 |
| `GET /api/projects/{id}` | `Project` | 404, 502 |
| `PUT /api/projects/{id}` body `SaveRequest` | `Project` (stored) | 404, 409 `ConflictResponse`, 422, 502, 503 (lock busy / DB down), 504 (unconfirmed) |

Every non-409 error body is `{"detail": "<human-readable message>"}`. After a 409 the client resends with
`base = current` and `proposed = merged` plus the values the user chose.

No caching of the list or of projects (the nightly job would make it stale).

## Frontend (`frontend/`) — target layout

Node 20+, Vite, React + TypeScript, MUI (style props go in `sx`), `@mui/icons-material` for icons, React
Router. Dev server on port 4000; `vite.config.ts` proxies `/api` to `BACKEND_URL` (default
`http://127.0.0.1:8000`), so there is no CORS and the browser only sees its own origin.

- `src/api.ts` — the **only** module that calls `fetch`, always `/api/...`. A 409 becomes
  `SaveConflictError` carrying the `ConflictResponse`; other failures become `ApiError` with `detail`.
- `src/conflicts.ts` — `applyChoices(merged, conflicts, choices)`: what to resend after a 409; also the
  dialog's display helpers. Cancelling the dialog keeps `base` and `draft` unchanged (the next save
  conflicts again), so a cancelled dialog can never revert someone else's change.
- `src/types.ts` — the shared shapes (mirror `schemas.py`), `editableOf`, `humanize`.
- `src/components/KeyDatesEditor.tsx` — rows of label + date, add/remove.
- `src/components/LinkedCompaniesEditor.tsx` — rows of company name + role, add/remove.
- `src/validation.ts` — mirrors the backend: required fields, valid enums, unique key-date labels and
  company names.
- `src/pages/ProjectListPage.tsx` — table of projects, click to edit.
- `src/pages/ProjectEditPage.tsx` — form for name, sector, country, stage and a key-dates editor (add,
  remove, re-date, rename) and a linked-companies editor (add, remove, rename, change role). Keeps `base` (last loaded/saved version)
  and `draft`; after a conflict `base` becomes the 409's `current`. Saving shows progress, and after 3 s
  says it is still confirming (slow GETs and 504 retries).
- `src/components/ConflictDialog.tsx` — one row per conflict: base, mine, theirs. **Nothing preselected**;
  Save is disabled until every conflict has a choice.

## Testing

Test the logic hard; do not chase a coverage number (the brief does not score it).

- **Backend unit:** `test_merge.py` (every row of the merge table, key-date cases: different labels,
  same label, re-date vs delete, renames (same date, conflicting renames, rename vs re-date/delete,
  rename + re-date, ambiguous pairing, rename onto their new label), duplicates fallback, sorting, no-op), `test_upstream.py` (httpx
  `MockTransport`, status → exception mapping), `test_service.py` (fake client/lock/log: 504 landed,
  504 lost, 504 then someone else wrote, attempts exhausted, conflict, no-op, lock timeout, log failure
  does not fail the save).
- **Backend integration:** `test_routes.py` runs our app against the **real upstream app in-process**
  (add `upstream` as a path dev dependency; its `create_app(rng=...)` accepts a scripted `random.Random`
  to force slow GETs and 504s deterministically), with the in-memory lock fake. One test per route and
  status code. MySQL-specific tests (`test_locking.py`) are marked `mysql` and skip when
  `EDITOR_DATABASE_URL` is unreachable.
- **Frontend:** Jest + Testing Library, tests next to the code (`*.test.ts(x)`): `conflicts.ts`,
  `validation.ts`, `ConflictDialog`, the edit page's save/conflict flow with `../api` mocked.

## Commands

```sh
# Everything in Docker (MySQL, upstream, backend, frontend behind nginx on :4000). Files in docker/.
docker compose up --build
docker compose up --build --scale backend=3     # the production shape: 3 instances behind nginx

# MySQL 8 runs locally from DBngin (root, no password, port 3306). Once:
/Users/Shared/DBngin/mysql/8.0.33/bin/mysql -h127.0.0.1 -uroot -e "CREATE DATABASE IF NOT EXISTS project_editor"
# The save_log table is created by the backend at startup.

# Upstream (port 8081, docs at /docs). Every request needs header X-Api-Key: local-dev-key
cd upstream && uv run upstream
cd upstream && UPSTREAM_SLOW_RATE=0 UPSTREAM_TIMEOUT_RATE=0 uv run upstream   # flakiness off

# Backend (port 8000, docs at /docs)
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd backend && uv run pytest                     # unit + integration
cd backend && uv run pytest -m "not mysql"      # without a MySQL server

# Frontend (port 4000)
cd frontend && npm install && npm run dev
cd frontend && npm test                         # jest
cd frontend && npm run build                    # tsc + vite build

# Everything at once (Ctrl+C stops all); --stable turns the upstream flakiness off
./dev.sh [--stable]
```

In Docker the upstream runs as `uvicorn records_api.main:create_app --factory --host 0.0.0.0`, because its
own `run()` binds to 127.0.0.1; `upstream/` itself stays untouched. nginx (`docker/nginx.conf`) plays the
Vite proxy's role and spreads `/api` across scaled backend instances.

`.claude/launch.json` defines `upstream`, `backend` and `frontend` for the preview tool, and
`backend/.env.example` lists every `EDITOR_` setting. Frontend tests run through Babel
(`babel.config.cjs`, `jest.config.cjs`), not Vite; `tsconfig.test.json` type-checks the tests.

## Out of scope (say so in DECISIONS.md)

User identity and auth, presence ("X is editing"), push updates, caching,
message queues, DB migrations tooling, end-to-end browser tests, UI polish.

## Deliverables (from the brief)

Our own `README.md` (what runs, what does not, how to start), a one-page `DECISIONS.md` (choices, cuts,
what breaks first with 50 editors: nightly-job writes inside the read-then-write window, lock contention
on hot projects, the list endpoint fetching every project in full, retry amplification), and the AI
trail (`AI-TRAIL.md`).
