import time

from app.locking import LockTimeout, LockUnavailable, ProjectLock, SaveLog, SaveLogEntry
from app.merge import three_way_merge
from app.schemas import ConflictResponse, Project, SaveRequest
from app.upstream import UpstreamClient, UpstreamNotFound, UpstreamRejected, UpstreamWriteUnknown


class SaveConflict(Exception):
    def __init__(self, response: ConflictResponse):
        super().__init__("Conflicting changes")
        self.response = response


class SaveUnconfirmed(Exception):
    """Every PUT answered 504 and the re-reads never showed the write: we do not know if it landed."""


async def save_project(
    project_id: str,
    request: SaveRequest,
    *,
    upstream: UpstreamClient,
    lock: ProjectLock,
    log: SaveLog,
    attempts: int,
) -> Project:
    """GET current → merge → 409 on conflicts → no-op if nothing to write → PUT.

    A 504 on the PUT means "unknown", so the loop re-reads and re-merges: if our write landed the merge
    finds nothing left to do; if it was lost we write again; if someone else wrote, the merge sees it.
    """
    started = time.monotonic()
    outcome = "upstream_error"
    changed: list[str] = []
    rounds = 0
    try:
        async with lock.hold(project_id):
            while rounds < attempts:
                rounds += 1
                current = await upstream.get_project(project_id)
                result = three_way_merge(request.base, request.proposed, current.editable())
                if result.conflicts:
                    outcome = "conflict"
                    raise SaveConflict(ConflictResponse(current=current, merged=result.merged,
                                                        conflicts=result.conflicts))
                if not result.changed_slots:
                    # On a later round this confirms that a PUT answered with 504 did land.
                    outcome = "noop" if rounds == 1 else "saved"
                    return current
                changed = result.changed_slots
                body = result.merged.model_dump(mode="json")
                body["linked_companies"] = [c.model_dump(mode="json") for c in current.linked_companies]
                try:
                    stored = await upstream.put_project(project_id, body)
                except UpstreamWriteUnknown:
                    continue
                outcome = "saved"
                return stored
            outcome = "unconfirmed"
            raise SaveUnconfirmed(f"The save of {project_id} could not be confirmed")
    except LockTimeout:
        outcome = "lock_timeout"
        raise
    except LockUnavailable:
        outcome = "lock_unavailable"
        raise
    except UpstreamRejected:
        outcome = "rejected"
        raise
    except UpstreamNotFound:
        outcome = "not_found"
        raise
    finally:
        # After the lock is released, so logging never holds up the next saver.
        await log.record(SaveLogEntry(
            project_id=project_id,
            outcome=outcome,
            attempts=rounds,
            duration_ms=round((time.monotonic() - started) * 1000),
            changed_slots=changed,
        ))
