"""Three-way merge of a project. Pure functions, no I/O.

base   = what the editor loaded
mine   = what the editor proposes
theirs = what the upstream holds now

A project is a set of slots: each scalar field, plus one slot per list item. The two lists follow the
same rule, with their own identity:

| list               | identity | value that pairs a rename |
|--------------------|----------|---------------------------|
| `key_dates`        | label    | date                      |
| `linked_companies` | name     | role                      |

An item's slot is keyed by its identity in `base` (or its own if it is new), and its value is the whole
item, or absent. So re-dating a key date, or changing a company's role, conflicts only with a concurrent
change of that same item.

A **rename** keeps the slot: an identity that disappeared, paired with exactly one new identity carrying
the same pairing value (same date / same role), is the same item renamed. Two people renaming the same
item differently therefore conflict instead of silently producing two items. Renaming *and* changing the
pairing value at once is a new item (the old one removed). Ambiguous pairings are not made.

If any side has duplicated identities in a list, identity breaks down and that whole list is a single
slot, so duplicates are never collapsed. The same fallback applies if a merge would produce duplicates.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.schemas import Conflict, EditableProject, has_duplicates, sort_companies, sort_key_dates

SCALAR_FIELDS = ("name", "sector", "country", "stage")


@dataclass(frozen=True)
class ListField:
    name: str  # the project field
    key: str  # what identifies an item
    pair_by: str  # what must stay equal for a changed identity to count as a rename
    sort: Callable[[list], list]

    def slot(self, key: str) -> str:
        return f"{self.name}[{key}]"


KEY_DATES = ListField("key_dates", key="label", pair_by="date", sort=sort_key_dates)
LINKED_COMPANIES = ListField("linked_companies", key="name", pair_by="role", sort=sort_companies)
LIST_FIELDS = (KEY_DATES, LINKED_COMPANIES)


def find_renames(base: list[BaseModel], side: list[BaseModel], lf: ListField) -> dict[str, str]:
    """{old identity: new identity} for every unambiguous rename on one side (identities unique on both)."""
    base_values = {getattr(item, lf.key): getattr(item, lf.pair_by) for item in base}
    side_values = {getattr(item, lf.key): getattr(item, lf.pair_by) for item in side}
    removed = [k for k in base_values if k not in side_values]
    added = [k for k in side_values if k not in base_values]
    renames = {}
    for old in removed:
        candidates = [new for new in added if side_values[new] == base_values[old]]
        # The new identity must also point back to exactly one removed identity with that value.
        if len(candidates) == 1 and sum(base_values[o] == side_values[candidates[0]] for o in removed) == 1:
            renames[old] = candidates[0]
    return renames


def to_slots(project: EditableProject, base: EditableProject, whole_lists: set[str]) -> dict[str, Any]:
    slots: dict[str, Any] = {name: getattr(project, name) for name in SCALAR_FIELDS}
    for lf in LIST_FIELDS:
        items = getattr(project, lf.name)
        if lf.name in whole_lists:
            # A tuple so it compares by value, sorted so order alone is never a change.
            slots[lf.name] = tuple(lf.sort(items))
            continue
        renamed_from = {new: old for old, new in find_renames(getattr(base, lf.name), items, lf).items()}
        for item in items:
            identity = getattr(item, lf.key)
            slots[lf.slot(renamed_from.get(identity, identity))] = item
    return slots


def from_slots(slots: dict[str, Any], whole_lists: set[str]) -> EditableProject:
    lists = {}
    for lf in LIST_FIELDS:
        if lf.name in whole_lists:
            items = list(slots[lf.name])
        else:
            items = [value for slot, value in slots.items() if slot.startswith(f"{lf.name}[")]
        lists[lf.name] = lf.sort(items)
    return EditableProject(**{name: slots[name] for name in SCALAR_FIELDS}, **lists)


@dataclass
class MergeResult:
    merged: EditableProject
    conflicts: list[Conflict] = field(default_factory=list)
    # Slots where `merged` differs from `theirs`, i.e. what a PUT would change. Empty = nothing to write.
    changed_slots: list[str] = field(default_factory=list)


def _conflict(slot: str, base: Any, mine: Any, theirs: Any) -> Conflict:
    if slot in SCALAR_FIELDS:
        return Conflict(slot=slot, field=slot, base=base, mine=mine, theirs=theirs)
    if slot in (lf.name for lf in LIST_FIELDS):
        return Conflict(slot=slot, field=slot, base=list(base), mine=list(mine), theirs=list(theirs))
    list_name, _, rest = slot.partition("[")
    return Conflict(slot=slot, field=list_name, key=rest.removesuffix("]"), base=base, mine=mine, theirs=theirs)


def three_way_merge(base: EditableProject, mine: EditableProject, theirs: EditableProject,
                    whole_lists: frozenset[str] = frozenset()) -> MergeResult:
    whole = set(whole_lists) | {
        lf.name for lf in LIST_FIELDS
        if any(has_duplicates(getattr(p, lf.name), lf.key) for p in (base, mine, theirs))
    }
    base_slots, my_slots, their_slots = (to_slots(p, base, whole) for p in (base, mine, theirs))

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

    result = from_slots(merged, whole)
    newly_duplicated = {
        lf.name for lf in LIST_FIELDS
        if lf.name not in whole and has_duplicates(getattr(result, lf.name), lf.key)
    }
    if newly_duplicated:
        # e.g. I renamed an item to an identity they just added: compare that whole list instead.
        return three_way_merge(base, mine, theirs, frozenset(whole | newly_duplicated))
    return MergeResult(merged=result, conflicts=conflicts, changed_slots=changed)
