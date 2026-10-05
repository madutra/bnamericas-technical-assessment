"""What the browser sees. Validating upstream payloads through these drops the read-only fields."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints, model_validator

Sector = Literal["energy", "mining", "water", "transport", "oil_and_gas", "ict"]
Stage = Literal["idea", "feasibility", "tender", "financing", "construction", "operation", "cancelled"]
CompanyRole = Literal["owner", "developer", "epc_contractor", "financier", "consultant"]

# Trimmed, non-empty text: "Tender launch " and "Tender launch" are the same label.
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class KeyDate(BaseModel):
    label: Text
    date: dt.date


class LinkedCompany(BaseModel):
    name: Text
    role: CompanyRole


class EditableProject(BaseModel):
    """The edit form: every field a save may change (all of the upstream's editable fields)."""

    name: Text
    sector: Sector
    country: Text
    stage: Stage
    key_dates: list[KeyDate]
    linked_companies: list[LinkedCompany]


class Project(EditableProject):
    id: str

    def editable(self) -> EditableProject:
        return EditableProject.model_validate(self.model_dump(include=set(EditableProject.model_fields)))


class ProjectSummary(BaseModel):
    id: str
    name: str
    sector: Sector
    country: str
    stage: Stage


def has_duplicates(items: list[BaseModel], key: str) -> bool:
    keys = [getattr(item, key) for item in items]
    return len(keys) != len(set(keys))


def sort_key_dates(key_dates: list[KeyDate]) -> list[KeyDate]:
    return sorted(key_dates, key=lambda kd: (kd.date, kd.label))


def sort_companies(companies: list[LinkedCompany]) -> list[LinkedCompany]:
    return sorted(companies, key=lambda c: (c.name, c.role))


class SaveRequest(BaseModel):
    """`base` is the version the editor loaded, `proposed` is the edited form."""

    base: EditableProject
    proposed: EditableProject

    @model_validator(mode="after")
    def no_new_duplicates(self) -> "SaveRequest":
        # Duplicates already stored upstream (e.g. by the nightly import) are tolerated while untouched.
        base, proposed = self.base, self.proposed
        if has_duplicates(proposed.key_dates, "label") and \
                sort_key_dates(proposed.key_dates) != sort_key_dates(base.key_dates):
            raise ValueError("Key date labels must be unique")
        if has_duplicates(proposed.linked_companies, "name") and \
                sort_companies(proposed.linked_companies) != sort_companies(base.linked_companies):
            raise ValueError("Linked company names must be unique")
        return self


# A scalar's value, one list item, a whole list (fallback), or None = absent.
SlotValue = str | KeyDate | LinkedCompany | list[KeyDate] | list[LinkedCompany] | None


class Conflict(BaseModel):
    """One slot both sides changed to different values. `None` means the item is absent."""

    slot: str
    field: Literal["name", "sector", "country", "stage", "key_dates", "linked_companies"]
    # For a single list item: its identity in `base` (key-date label or company name), or its own if new.
    # Each side's value may carry a different label/name when that side renamed it. None for scalar fields
    # and for the whole-list fallback.
    key: str | None = None
    base: SlotValue
    mine: SlotValue
    theirs: SlotValue


class ConflictResponse(BaseModel):
    current: Project
    merged: EditableProject
    conflicts: list[Conflict]
