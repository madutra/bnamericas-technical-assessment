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
    """The edit form: every field a save may change."""

    name: Text
    sector: Sector
    country: Text
    stage: Stage
    key_dates: list[KeyDate]


class Project(EditableProject):
    id: str
    # Read-only for us: shown in the UI, sent back unchanged on every PUT.
    linked_companies: list[LinkedCompany]

    def editable(self) -> EditableProject:
        return EditableProject.model_validate(self.model_dump(include=set(EditableProject.model_fields)))


class ProjectSummary(BaseModel):
    id: str
    name: str
    sector: Sector
    country: str
    stage: Stage


def has_duplicate_labels(key_dates: list[KeyDate]) -> bool:
    labels = [kd.label for kd in key_dates]
    return len(labels) != len(set(labels))


def sort_key_dates(key_dates: list[KeyDate]) -> list[KeyDate]:
    return sorted(key_dates, key=lambda kd: (kd.date, kd.label))


class SaveRequest(BaseModel):
    """`base` is the version the editor loaded, `proposed` is the edited form."""

    base: EditableProject
    proposed: EditableProject

    @model_validator(mode="after")
    def no_new_duplicate_labels(self) -> "SaveRequest":
        # Duplicates already stored upstream (e.g. by the nightly import) are tolerated while untouched.
        proposed = self.proposed.key_dates
        if has_duplicate_labels(proposed) and sort_key_dates(proposed) != sort_key_dates(self.base.key_dates):
            raise ValueError("Key date labels must be unique")
        return self


SlotValue = str | dt.date | list[KeyDate] | None


class Conflict(BaseModel):
    """One slot both sides changed to different values. `None` means the key date is absent."""

    slot: str
    field: Literal["name", "sector", "country", "stage", "key_dates"]
    # Set for a single key date; None for scalar fields and for the whole-list fallback.
    label: str | None = None
    base: SlotValue
    mine: SlotValue
    theirs: SlotValue


class ConflictResponse(BaseModel):
    current: Project
    merged: EditableProject
    conflicts: list[Conflict]
