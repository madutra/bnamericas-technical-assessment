# Decisions

## Concurrent editing: a three-way merge on every save

The upstream keeps the last PUT silently, replaces whole lists and has no version. So the browser sends
the version it loaded (`base`) with its edit (`proposed`). The backend reads the upstream **now**
(`theirs`) and merges field by field:
- a field only one side changed takes that side's value;
- both sides changing it to the same value is fine;
- both sides changing it to different values is a **409**, and nothing is written.

The person saving second sees both values, with nothing preselected, and picks one. Neither side wins
silently.

**Why:** the state needed to detect a conflict travels with the request, and `theirs` always comes from
the upstream. Any of the 3 instances can serve any save, and the nightly job's writes are just "theirs".
- Rejected: a lock taken when the form opens. It blocks people editing different fields.
- Rejected: a hash of the whole record. Every concurrent edit would conflict.

## "The same field" for list items: the same label, or the same company name

Each key date is its own field, identified by its label (trimmed, case-sensitive). Each linked company is
one too, identified by its name. So re-dating two different milestones never conflicts, while re-dating
and deleting the same one does. The same goes for companies and their roles.
- **Not the whole list:** milestones are researched independently, so unrelated edits would collide.
- **Not the position:** inserting or removing a row shifts every index.
- **Renames:** a label that disappeared plus a new one with the **same date** is the same milestone,
  renamed. Two people renaming it differently get a conflict, not two milestones. For companies, a rename
  is paired by **role**. Renaming *and* changing the date (or the role) at once is a new item. Ambiguous
  pairings are not guessed. Renames are inferred from the data, so the nightly job's renames count too.
- **Duplicates:** the upstream allows a label or a company twice, e.g. via the import. Then identity
  breaks down, and that whole list becomes one field, kept exactly as stored. Our form and API refuse to
  *create* duplicates.
- Lists are sorted after a merge (dates by date, companies by name), so order alone is never a change.

## The ambiguous 504

A 504 on PUT means "unknown". The backend re-reads and merges again:
- if our write landed, there is nothing left to do;
- if it was lost, it writes again;
- if someone else wrote in between, the merge sees it.

After 3 rounds it answers 504 "could not be confirmed, reload". After 3 s the form says it is still
confirming.

## MySQL: a shared lock and a save log, never project data

Each save holds a per-project MySQL named lock for its whole GET → merge → PUT. That closes the gap
between read and write for our own 3 instances. MySQL frees the lock if an instance dies.
- **Lock busy for 5 s:** 503 "try again".
- **MySQL down:** saves fail closed with 503, and reads keep working.
- **`save_log`:** every save attempt is recorded (outcome, changed fields, rounds, instance). The log is
  best effort and never fails a save.

MySQL never holds project fields: the nightly job would make a copy stale. **The lock does not cover the
nightly job.** Only a version or `If-Match` on the upstream could.

## What I cut, and why

- **User identity, "edited by" in conflicts:** the upstream has one shared key and no users.
- **Caching:** it would serve stale data after the nightly import.
- **Presence and push updates:** a 409 at save time covers correctness.
- **Migration tooling:** one table, created when missing.
- **End-to-end browser tests:** integration tests run against the real upstream app with scripted 504s.
  The two-tab flows were checked by hand.

## What breaks first with 50 editors

1. **Nightly-job writes between our read and our write.** Rare, but silent. Fix: `If-Match` upstream.
2. **Lock contention on hot projects.** A save can hold the lock ~6 s (slow GET plus retries). Editors
   queued behind it get 503. Fix: hedged GETs to cut the 2 s tail, and a bigger connection pool.
3. **The list endpoint** fetches every project in full. Fix: a short-TTL cache or a summary endpoint.
4. **Retries amplify load.** Fix: backoff and a per-instance cap.

More instances fix none of these: they are correctness and contention problems, not capacity.
