# Records API (upstream)

This service stands in for an API owned by **another team**. Treat it as something you consume, not
something you change: do not edit anything in this folder.

## Run it

Requires [uv](https://docs.astral.sh/uv/).

```sh
cd upstream
uv run upstream
```

It listens on `http://127.0.0.1:8081`. Interactive docs are at `/docs`, and the OpenAPI spec is at
`/openapi.json`.

| Environment variable | Default | Effect |
|---|---|---|
| `UPSTREAM_PORT` | `8081` | Port to listen on |
| `UPSTREAM_SLOW_RATE` | `0.1` | Share of `GET /projects/{id}` calls that take about 2 seconds. Set it to `0` to switch this off |
| `UPSTREAM_TIMEOUT_RATE` | `0.1` | Share of `PUT` calls that answer `504 Gateway timeout`. Set it to `0` to switch this off |

Its own tests: `uv run pytest`.

## Authentication

Every request needs the header `X-Api-Key: local-dev-key`. There is one key for the whole service. The
API has no idea who the person behind a request is.

## Endpoints

| Method | Path | What it does |
|---|---|---|
| `GET` | `/projects` | Every project, in full |
| `GET` | `/projects/{id}` | One project, in full. `404` if unknown |
| `PUT` | `/projects/{id}` | Saves the editable fields of one project and returns the stored record. `404` if unknown, `422` if invalid, sometimes `504` (see below) |

## Data

About 30 fictional projects, seeded identically on every start. **Data lives in memory and resets when
the service restarts.**

**Editable fields** (the `PUT` body, all required):

| Field | Type |
|---|---|
| `name` | string |
| `sector` | one of `energy`, `mining`, `water`, `transport`, `oil_and_gas`, `ict` |
| `country` | string |
| `stage` | one of `idea`, `feasibility`, `tender`, `financing`, `construction`, `operation`, `cancelled` |
| `key_dates` | list of `{ "label": string, "date": "YYYY-MM-DD" }` |
| `linked_companies` | list of `{ "name": string, "role": one of owner, developer, epc_contractor, financier, consultant }` |

Every other field in a response is owned by other systems. It is read-only, and it is ignored if you
send it.

## Known behaviour

The owning team knows about these habits and has no plans to change them:

- **The last save wins.** There is no version number, no timestamp and no conflict check. Two `PUT`s
  on the same project both succeed, and the second one overwrites the first without a word.
- **`PUT` replaces the lists.** `key_dates` and `linked_companies` are replaced wholesale by whatever
  you send. Send a list with one entry and the others are gone.
- **Responses are wide.** Each project carries about 15 more fields than an edit screen needs.
- **It is sometimes slow.** About one `GET /projects/{id}` in ten takes around 2 seconds.
- **Saves sometimes time out.** About one `PUT` in ten answers `504 Gateway timeout`. A `504` does
  not tell you whether the save happened: sometimes it did, sometimes it did not.
