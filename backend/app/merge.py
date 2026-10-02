"""Three-way merge of a project. Pure functions, no I/O.

base   = what the editor loaded
mine   = what the editor proposes
theirs = what the upstream holds now

A project is a set of slots: each scalar field, plus one slot per key date keyed by its label
(value = the date, or absent). If any side has duplicated labels, label identity breaks down and the
whole key-date list is a single slot, so duplicates are never collapsed.
"""

from dataclasses import dataclass, field
from typing import Any

from app.schemas import Conflict, EditableProject, KeyDate, has_duplicate_labels, sort_key_dates

SCALAR_FIELDS = ("name", "sector", "country", "stage")
WHOLE_LIST = "key_dates"


def key_date_slot(label: str) -> str:
    return f"key_dates[{label}]"


def to_slots(project: EditableProject, whole_list: bool) -> dict[str, Any]:
    slots: dict[str, Any] = {name: getattr(project, name) for name in SCALAR_FIELDS}
    if whole_list:
        # A tuple so it compares by value, sorted so order alone is never a change.
        slots[WHOLE_LIST] = tuple(sort_key_dates(project.key_dates))
    else:
        for kd in project.key_dates:
            slots[key_date_slot(kd.label)] = kd.date
    return slots


def from_slots(slots: dict[str, Any], whole_list: bool) -> EditableProject:
    if whole_list:
        key_dates = list(slots[WHOLE_LIST])
    else:
        key_dates = [
            KeyDate(label=slot.removeprefix("key_dates[").removesuffix("]"), date=value)
            for slot, value in slots.items()
            if slot.startswith("key_dates[")
        ]
    return EditableProject(**{name: slots[name] for name in SCALAR_FIELDS}, key_dates=sort_key_dates(key_dates))


@dataclass
class MergeResult:
    merged: EditableProject
    conflicts: list[Conflict] = field(default_factory=list)
    # Slots where `merged` differs from `theirs`, i.e. what a PUT would change. Empty = nothing to write.
    changed_slots: list[str] = field(default_factory=list)


def _conflict(slot: str, base: Any, mine: Any, theirs: Any) -> Conflict:
    if slot in SCALAR_FIELDS:
        return Conflict(slot=slot, field=slot, base=base, mine=mine, theirs=theirs)
    if slot == WHOLE_LIST:
        return Conflict(slot=slot, field="key_dates", base=list(base), mine=list(mine), theirs=list(theirs))
    label = slot.removeprefix("key_dates[").removesuffix("]")
    return Conflict(slot=slot, field="key_dates", label=label, base=base, mine=mine, theirs=theirs)


def three_way_merge(base: EditableProject, mine: EditableProject, theirs: EditableProject) -> MergeResult:
    whole_list = any(has_duplicate_labels(p.key_dates) for p in (base, mine, theirs))
    base_slots, my_slots, their_slots = (to_slots(p, whole_list) for p in (base, mine, theirs))

    merged = dict(their_slots)
    conflicts: list[Conflict] = []
    changed: list[str] = []
    # dict.fromkeys keeps a stable order without repeats.
    for slot in dict.fromkeys([*base_slots, *my_slots, *their_slots]):
        b, m, t = base_slots.get(slot), my_slots.get(slot), their_slots.get(slot)
        if m == b:
            continue  # I did not touch it: theirs stands.
        if t == m:
            continue  # Both made the same change (or my earlier write already landed).
        if t == b:
            # Only I changed it.
            if m is None:
                merged.pop(slot)
            else:
                merged[slot] = m
            changed.append(slot)
            continue
        conflicts.append(_conflict(slot, b, m, t))

    return MergeResult(merged=from_slots(merged, whole_list), conflicts=conflicts, changed_slots=changed)
