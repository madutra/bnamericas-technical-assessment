# AI trail

Tool: Claude Code (desktop app), one session. The full transcript can be exported from the app and attached.

## How the tooling was set up

1. **Environment.** The upstream needed Python ≥ 3.11 and `uv`, and the machine only had Python 3.9.
   Claude installed `uv` (via Homebrew) and found out why package downloads failed: the network was
   resetting connections to `files.pythonhosted.org`.
2. **A throwaway first backend**, used to learn the FastAPI basics (dependency injection, Pydantic, async httpx) with an explanation of every file.
3. **`CLAUDE.md`.** Claude generated it with `/init` from the brief and the upstream's code. It covers the hard rules, the upstream's habits and the commands. **I then edited it myself**: I added the frontend (React + MUI, port 4000, Jest) and testing expectations.
4. **Rebuild from `CLAUDE.md`.** I asked Claude to delete all code so far and build again from the file I had edited, so that the spec, not the conversation, drives the code.

## What the tool produced (second pass)

- Backend:
  - three-way merge as pure functions (`merge.py`);
  - a save loop that handles the ambiguous 504 (`service.py`);
  - an upstream client that turns HTTP quirks into exceptions;
  - 50 tests (61 after the review round), including integration tests against the real upstream app with its randomness scripted.
- Frontend: list, edit form, key-dates editor, conflict dialog, 26 Jest tests (30 after the review round).
- `README.md`, `DECISIONS.md`, `.claude/launch.json`.

## Where the tool deviated from my spec, and why

- **CORS.** I had pictured the frontend calling the backend directly. Claude used a Vite proxy instead, so the browser only ever sees its own origin and no CORS is needed.
- **"Scale horizontally for 50 editors".** My `CLAUDE.md` said this. Claude pointed out that the first thing to break at 50 editors is a correctness problem (the read-then-write window), which more instances do not fix. See `DECISIONS.md`.
- **Jest with Vite.** This needs Babel and a `TextEncoder` polyfill. Claude kept Jest, as I asked, rather than switching to Vitest.

## Mistakes caught along the way

These were found by the tests, the type-checker or a manual run, not by reading:

- the merge duplicated every key date (the label order was not de-duplicated): 6 failing tests;
- a broken sort expression in the merge, caught on re-reading the code;
- MUI v9 no longer accepts style props on `Stack` directly: caught by `tsc`;
- one test expectation was wrong, not the component: checked with a debug test before changing it;
- `ict` showed as "Ict": noticed in the browser.

## Review round

I asked for a critical review of the finished code. Claude listed six findings, ranked by severity, and confirmed the worst one by running the merge on a crafted input before reporting it. I decided which to fix:

- **Fixed: duplicate key-date labels lost data.** If the upstream held two dates with the same label, saving an unrelated field silently dropped one. Now the whole list becomes a single field in that case.
- Writing the integration test for this exposed a second problem: our validation then refused every save of such a project. Duplicates that are already stored and untouched are now tolerated.
- **Fixed: slow saves were silent.** After 3 s the form says the save is still being confirmed.
- **Fixed: an upstream 422 showed as "service unavailable".** It now returns a 422 with a clear message.
- **Fixed: labels differing only by spaces** counted as different dates. Schemas now strip whitespace.
- **Kept, documented:** the read-then-write window (it needs upstream support), and the fact that `base` comes from the client, so the protection is cooperative rather than a security boundary.

Verified end to end in the browser: I wrote a duplicate label straight to the upstream, as the nightly job
could, renamed the project through the UI, and all 5 dates and both companies survived.

## Third pass: brainstorm, new spec, rebuild with MySQL

1. **Brainstorm, no code.** Claude read the brief, the upstream's README and source, and the old markdown,
   then wrote an analysis of the upstream's habits and the concurrency options, with a list of open
   questions. I answered them: exact labels, dates sorted after a merge, the Vite proxy, linked companies
   read-only, and MySQL for a shared lock and a save log.
2. **`CLAUDE.md` rewritten as a spec.** I removed a part about my own experience level that Claude had
   added; it did not belong in the repo.
3. **Rebuild from the spec:**
   - Backend: 68 pytest tests, including 6 against the real MySQL and integration tests against the real
     upstream app with scripted 504s.
   - Frontend: 23 Jest tests.
   - `dev.sh`, `.claude/launch.json`, `backend/.env.example`.

Mistakes caught in this pass, all by running things:

- A test of "upstream down" closed the HTTP client, which raises a different error than a network failure.
  The test was wrong, not the code; it now simulates a refused connection.
- `@mui/icons-material/DeleteOutline` does not exist (it is `DeleteOutlined`): caught by `tsc`.
- oxlint flagged state updates inside the load effect and helpers exported from a component file; both
  were restructured.
- I noticed my editor marking `@asynccontextmanager` as deprecated. Claude first checked only at runtime
  and found nothing; a type checker (basedpyright) confirmed it: annotating the return as `AsyncIterator`
  is deprecated in the type stubs, so it is now `AsyncGenerator`, in the fakes and in `locking.py`.
- **Docker found two real bugs** on the first `docker compose up --scale backend=3`. Six concurrent saves
  all returned 500:
  - the containerized MySQL user has a password, and MySQL 8's default auth then needs the
    `cryptography` package (DBngin's passwordless root had hidden this);
  - the resulting `RuntimeError` slipped past the lock's error handling, which only caught database and
    network errors, so "lock unavailable" became a 500 instead of a 503. Any failure while taking the
    lock now fails closed with 503, and `save_log` also creates its table lazily in case MySQL was down
    at startup.

  After the fix, the 6 concurrent saves of different fields on one project, spread over the 3 instances
  with the upstream's flakiness on, all returned 200 and all 6 changes survived. One save hit a 504 and
  recovered on its second round. With MySQL stopped, reads still worked and saves answered 503; after
  restarting it, saves worked again.

- **I found a design flaw by testing two tabs:** both renamed the same key date to different labels, and
  the project ended up with two dates instead of a conflict. The cause was the rule "rename = remove + add":
  both sides removed the same label, which is not a conflict, and each added a different one, which is not
  a conflict either. I decided the rule: same date with a new label = same milestone renamed; a new
  label and a new date = a new milestone. Claude recommended inferring renames from the data on both sides,
  rather than having the form send them, so the nightly job's renames are also caught. Claude reproduced
  my case in the merge function first, then fixed it, then added 10 merge tests, 1 integration test and
  1 frontend test.

- **Linked companies.** Reading the upstream's README, I noticed `linked_companies` is editable there and
  asked for it. Claude had cut it on purpose (the brief only asks for core fields and key dates). We
  applied the same rules as key dates: identity by name, renames paired by role, whole-list fallback for
  duplicates. Claude generalised the merge so both lists share one implementation, then added 11 backend
  tests and 4 frontend tests.

## Checked by hand

- Claude, in the in-app browser (third pass): the same project open in two tabs. Tab A renamed and saved.
  Tab B renamed and changed the country, then saved: only the name conflicted, with nothing preselected.
  After choosing "mine", the upstream held tab B's name and country, all 4 key dates and all 3 companies.
  `save_log` showed `saved`, `conflict`, `saved` (the last took 2 s: it drew one of the slow GETs).
- Claude, in the in-app browser (second pass): the same project open in two tabs. Tab 1 changed the name and saved. Tab 2 changed the name and the country, and saved. Only the name conflicted. After choosing "mine", the upstream held tab 2's name, tab 2's country, and the untouched companies and dates.
- Me:
  - Two tabs on the same project, editing the same key date: its date, its label, and both at once.
    Nothing should be saved silently; the second saver must get a conflict and choose. Renaming the
    same date in both tabs created a second date instead of a conflict — the bug that led to the
    rename rule (see "Where I overrode the tool").
  - The form refuses two key dates with the same label.
  - The time of each request to the backend and the upstream (the slow GETs show up as ~2 s saves).
  - The `save_log` in MySQL after every update: one row per save, with its outcome and the fields it
    changed. This is how I found I was looking at the wrong database (port 3306 instead of 3307).

## My own note

**Before any code.** I started with a brainstorm, not a prompt to build. I asked Claude to read the brief,
the upstream's README and its source, and to tell me what the real task was. The answer: the CRUD is
easy. The hard part is a safe per-field save on top of an upstream that has:

- only a replace-everything `PUT`, with no version;
- 504s that may or may not have written;
- three stateless instances in front of it, and a nightly job writing behind our back.

From that I made the decisions:

- a three-way merge per field, with the browser sending the version it loaded (`base`) along with the edit;
- key dates identified by their exact label (only trimmed), and sorted by date after a merge;
- the Vite proxy for `/api`, so the browser only talks to its own origin;
- linked companies read-only at first, since the brief did not ask for them;
- **MySQL**, my addition to make the challenge more complete. Claude pointed out that it cannot hold
  project data (the nightly job would make it stale). So we agreed on two uses: a per-project lock
  shared by the three instances, and a `save_log` of every save.

**Turning that into a spec.** I had Claude rewrite `CLAUDE.md` from the brainstorm as a spec of what to
build. The old one described deleted files, which would have misled the agent. The spec fixes the merge
rules, the save algorithm, the API contract, the layout and the tests, so the build follows the file,
not the conversation.

**Where I overrode the tool.**

- **MySQL.** Claude's recommendation was to only document a shared lock. I chose to build it, with a
  save log, and accepted the extra service.
- **What goes in the spec.** Claude put a note about my experience level into `CLAUDE.md`. I removed it:
  the repo is a deliverable, not a place for notes about me.
- **Deprecations.** My editor flagged `@asynccontextmanager` as deprecated. Claude first said it was not,
  having checked only at runtime. I insisted on the exact line. A type checker then confirmed the
  problem (an `AsyncIterator` return annotation), and it was fixed in two files.
- **Docker.** I asked for a Docker setup so anyone can run the project without installing anything. Its
  first run exposed two real bugs that my local setup hid: a missing `cryptography` package, and a lock
  failure that surfaced as 500 instead of 503.
- **The rename rule for key dates.** Testing two tabs, I renamed the same key date in both and got two
  dates instead of a conflict. I decided the rule: a new label with the same date is the same milestone;
  a new label and a new date is a new one. Claude implemented it, inferring renames from the data.
- **Linked companies.** Reading the upstream's README, I saw they are editable there and asked for it,
  reversing my earlier decision. They now follow the same rules as key dates (identity by name, renames
  paired by role).

**Where I was corrected.**

- **Scaling.** My first `CLAUDE.md` said horizontal scaling would handle 50 editors. The brainstorm showed
  that the first thing to break is correctness, not capacity: the window between the backend's read and
  its write. The MySQL lock closes it between our own editors. For the nightly job, only an upstream
  version or `If-Match` could.
- **The database I was looking at.** When a save seemed missing, Claude used the logs to show that every
  save had reached the backend and been logged. The tool I was using (HeidiSQL) was connected to the
  local MySQL on 3306, not to the Docker one on 3307.

**What I checked by hand.** See "Checked by hand" above.
