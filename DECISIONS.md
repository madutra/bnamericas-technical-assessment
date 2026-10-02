# Decisions

## Concurrent editing: a three-way merge on every save

The upstream keeps the last PUT without a word, replaces whole lists and has no version field. So the
browser sends the version it loaded (`base`) along with the edit (`proposed`). On each save the backend
reads the upstream **now** (`theirs`) and merges field by field:

- a field only I changed → mine; a field only they changed → theirs;
- both changed it to the same value → fine; to different values → **409**, nothing written.

The 409 carries both values and a `merged` version (theirs plus all my other changes). The second saver
picks per field, with nothing preselected, and resends against the new `current`. Neither side wins
silently.

**Why:** the state needed to detect a conflict travels with the request, and `theirs` always comes from
the upstream. Any of the 3 instances can serve any save, and the nightly job needs no special case: its
writes are just "theirs". A lock taken when the form opens or a hash of the whole record was rejected:
the first blocks people editing different fields, and the second would turn every concurrent edit into a
conflict.

## "The same field" for key dates: the same label

Each key date is its own field, identified by its label (trimmed, case-sensitive). Re-dating "Financial
close" and re-dating "Tender launch" never conflict; re-dating and deleting the same milestone does.

- **Not the whole list:** any two date edits on a project would conflict, but milestones are researched
  independently.
- **Not the position:** inserting or removing a date shifts every index, so unrelated rows would collide.
- **Consequences:** renaming a label = removing one date and adding another. Our API and form refuse to
  *create* duplicate labels. After a merge the list is sorted by date, so order alone is never a change.
- **Duplicates already stored** (the upstream allows them, e.g. via the import): label identity breaks
  down, so the whole list becomes one field. Other fields stay editable, and the duplicates are kept
  exactly as stored.

## The ambiguous 504

A 504 on PUT means "unknown". The backend re-reads and re-merges: if our write landed, there is nothing
left to do; if it was lost, it writes again; if someone else wrote meanwhile, the merge sees it. The merge
makes the retry safe. After 3 rounds the answer is 504 "could not be confirmed, reload". A timeout on our
side counts as a 504; a refused connection does not, because nothing was sent. After 3 s the form says
it is still confirming.

## MySQL: a shared lock and a save log, never project data

The merge alone leaves a window between our GET and our PUT, in which another of our instances could
write and be overwritten. Each save therefore holds a MySQL named lock per project
(`GET_LOCK('editor:project:<id>')`). The lock is shared by all instances and freed by MySQL if an
instance dies. When the lock is busy for 5 s, the answer is 503 "try again". When MySQL is down, saves
answer 503 (fail closed) but reading still works. Every save attempt writes a row to `save_log`; that
write is best effort and never fails a save.

MySQL never holds project fields. The nightly job writes straight to the upstream, so a copy would go
stale and hide conflicts. **The lock does not cover the nightly job**: only a version or `If-Match` on
the upstream could. MySQL is an extra service to run, which I accepted for this guarantee. The fakes keep
the unit and integration tests independent of it.

## What I cut, and why

- **Editing linked companies.** Not asked for. Every PUT sends back the companies stored at that moment.
- **Identity, "edited by" in conflicts.** The upstream has one shared key and no users.
- **Caching.** It would serve stale data after the nightly import, for little gain at this scale.
- **Presence and push updates** ("Ana is editing"). A 409 at save time covers correctness.
- **Migration tooling.** One table, created at startup if missing.
- **End-to-end browser tests.** Backend integration tests run against the real upstream app with scripted
  504s; the two-tab flow was checked by hand in the browser.

## What breaks first with 50 editors

1. **Nightly-job writes inside the read-then-write window.** Our own editors are serialized by the lock;
   the job is not. Rare at night, but it is a silent loss. Fix: ask the upstream team for `If-Match`.
2. **Lock contention on hot projects.** A save holds the lock for its whole GET → PUT, up to ~6 s with a
   slow GET and retries. Editors queued behind it get 503 after 5 s. Each held lock also holds a pooled DB
   connection. Fix: hedged GETs (fire a second GET after ~300 ms) to cut the 2 s tail, and a bigger pool.
3. **The list endpoint** fetches every project in full from the upstream on every view. Fix: a
   short-TTL cache or an upstream summary endpoint.
4. **Retries amplify load.** Each 504 adds a GET and maybe a PUT. Fix: backoff, and a cap per instance.

Adding more instances fixes none of these: the first two are correctness and contention problems, not
capacity.
