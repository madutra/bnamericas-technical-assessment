# Project editor

An editor for infrastructure project records, sitting in front of an upstream records API we do not own.
The browser talks only to our backend; the backend talks to the upstream. The original challenge is in
[`BRIEF.md`](BRIEF.md), design choices are in [`DECISIONS.md`](DECISIONS.md), and how AI was used is in
[`AI-TRAIL.md`](AI-TRAIL.md). [`CLAUDE.md`](CLAUDE.md) is the spec the code was built from.

```
browser ──▶ frontend dev server :4000 ──/api──▶ backend :8000 ──X-Api-Key──▶ upstream :8081
            (React + MUI)                       (FastAPI)  │                  (do not modify)
                                                           └──▶ MySQL :3306 (per-project lock + save log)
```

## Run it with Docker (nothing else to install)

Requires Docker with Compose. Builds the four services (MySQL, upstream, backend, frontend served by nginx):

```sh
docker compose up --build                     # then open http://localhost:4000
docker compose up --build --scale backend=3   # 3 backend instances behind nginx, as in production
UPSTREAM_SLOW_RATE=0 UPSTREAM_TIMEOUT_RATE=0 docker compose up --build   # upstream flakiness off
docker compose down -v                        # stop and delete the MySQL data
```

MySQL is published on host port 3307 (user `editor`, password `editor`) to inspect `save_log`. The upstream
is not published: only the backend can reach it.

## Run it locally

Requires [uv](https://docs.astral.sh/uv/) (it fetches Python 3.11+ if needed), Node 20.19+ or 22.12+, and a
MySQL 8 on `127.0.0.1:3306` (e.g. DBngin; user `root`, no password). For other credentials, copy
`backend/.env.example` to `backend/.env` and edit `EDITOR_DATABASE_URL`. Create the database once:

```sh
mysql -h127.0.0.1 -uroot -e "CREATE DATABASE IF NOT EXISTS project_editor"
```

Then one command starts the other three (Ctrl+C stops them):

```sh
cd frontend && npm install && cd ..
./dev.sh            # upstream with its flakiness on (slow GETs, 504s)
./dev.sh --stable   # flakiness off
```

Open http://localhost:4000. To try the conflict flow: open the same project in two tabs, change the same
field in both, save both.

Or one terminal each, from the repo root:

```sh
cd upstream && uv run upstream                                   # :8081
cd backend && uv run uvicorn app.main:app --reload --port 8000   # :8000, docs at /docs
cd frontend && npm run dev                                       # :4000
```

## Tests

```sh
cd backend && uv run pytest                 # 93 tests: unit, integration against the real upstream app, MySQL
cd backend && uv run pytest -m "not mysql"  # without a MySQL server
cd frontend && npm test                     # 28 Jest + Testing Library tests
cd frontend && npm run build                # type-checks app and tests, then builds
```

## What works

- Project list, and an edit form for name, sector, country, stage and key dates (add, remove, re-date,
  rename) and linked companies (add, remove, rename, change role), with client-side validation.
- Concurrent editing: changes to different fields (and to different key dates or companies) from two
  editors both survive. Changes to the same field return a conflict; the person saving second sees both values and
  picks, with nothing preselected.
- Saves of the same project are serialized across backend instances by a MySQL named lock.
- Upstream 504s on save: the backend re-reads to find out whether the write landed, and writes again if
  it did not. A save that cannot be confirmed after 3 rounds says so.
- The nightly job's direct writes are treated like any other editor's and are not overwritten, apart
  from the case below.
- Every save attempt is recorded in the `save_log` table (outcome, changed fields, rounds, duration).

## What does not (yet)

- A nightly-job write landing between our read and our write (milliseconds, up to seconds on a slow
  GET) is lost. Closing that needs a version or `If-Match` from the upstream (see `DECISIONS.md`).
- No user identity or audit of who changed what: the upstream has no notion of users.
