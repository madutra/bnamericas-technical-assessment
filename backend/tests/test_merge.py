from datetime import date

from app.merge import three_way_merge
from app.schemas import EditableProject, KeyDate


def project(**overrides) -> EditableProject:
    data = {
        "name": "Cerro Talvi Solar Park",
        "sector": "energy",
        "country": "Chile",
        "stage": "tender",
        "key_dates": [
            {"label": "Tender launch", "date": "2026-01-10"},
            {"label": "Financial close", "date": "2026-07-01"},
        ],
        "linked_companies": [
            {"name": "Talcora Capital SpA", "role": "financier"},
            {"name": "Varelo Energia SA", "role": "owner"},
        ],
    }
    data.update(overrides)
    return EditableProject.model_validate(data)


def dates(result_project: EditableProject) -> dict[str, date]:
    return {kd.label: kd.date for kd in result_project.key_dates}


# --- scalar fields -------------------------------------------------------------------------------

def test_nobody_changed_anything_is_a_noop():
    base = project()
    result = three_way_merge(base, base, base)
    assert result.conflicts == [] and result.changed_slots == []
    assert result.merged == base


def test_only_i_changed_a_field():
    base = project()
    result = three_way_merge(base, project(name="New name"), base)
    assert result.merged.name == "New name"
    assert result.changed_slots == ["name"]


def test_only_they_changed_a_field_keeps_theirs_and_writes_nothing():
    base = project()
    result = three_way_merge(base, base, project(stage="financing"))
    assert result.merged.stage == "financing"
    assert result.changed_slots == []


def test_different_fields_both_survive():
    base = project()
    result = three_way_merge(base, project(name="Mine"), project(country="Peru"))
    assert result.conflicts == []
    assert (result.merged.name, result.merged.country) == ("Mine", "Peru")
    assert result.changed_slots == ["name"]


def test_same_field_same_value_is_not_a_conflict():
    base = project()
    result = three_way_merge(base, project(name="Same"), project(name="Same"))
    assert result.conflicts == [] and result.changed_slots == []


def test_same_field_different_values_conflicts():
    base = project()
    result = three_way_merge(base, project(name="Mine"), project(name="Theirs"))
    [conflict] = result.conflicts
    assert (conflict.slot, conflict.field, conflict.key) == ("name", "name", None)
    assert (conflict.base, conflict.mine, conflict.theirs) == ("Cerro Talvi Solar Park", "Mine", "Theirs")
    assert result.merged.name == "Theirs"  # conflicts keep theirs until the user chooses


def test_conflict_keeps_my_other_changes_in_merged():
    base = project()
    result = three_way_merge(base, project(name="Mine", stage="financing"), project(name="Theirs"))
    assert [c.slot for c in result.conflicts] == ["name"]
    assert result.merged.stage == "financing"


# --- key dates: one slot per label ---------------------------------------------------------------

def test_redating_different_labels_both_survive():
    base = project()
    mine = project(key_dates=[{"label": "Tender launch", "date": "2026-02-01"},
                              {"label": "Financial close", "date": "2026-07-01"}])
    theirs = project(key_dates=[{"label": "Tender launch", "date": "2026-01-10"},
                                {"label": "Financial close", "date": "2026-09-09"}])
    result = three_way_merge(base, mine, theirs)
    assert result.conflicts == []
    assert dates(result.merged) == {"Tender launch": date(2026, 2, 1), "Financial close": date(2026, 9, 9)}


def test_redating_the_same_label_differently_conflicts():
    base = project()
    mine = project(key_dates=[{"label": "Tender launch", "date": "2026-02-01"},
                              {"label": "Financial close", "date": "2026-07-01"}])
    theirs = project(key_dates=[{"label": "Tender launch", "date": "2026-03-01"},
                                {"label": "Financial close", "date": "2026-07-01"}])
    [conflict] = three_way_merge(base, mine, theirs).conflicts
    assert (conflict.slot, conflict.field, conflict.key) == ("key_dates[Tender launch]", "key_dates", "Tender launch")
    assert (conflict.base, conflict.mine, conflict.theirs) == (
        KeyDate(label="Tender launch", date=date(2026, 1, 10)),
        KeyDate(label="Tender launch", date=date(2026, 2, 1)),
        KeyDate(label="Tender launch", date=date(2026, 3, 1)),
    )


def test_redate_vs_delete_of_the_same_label_conflicts():
    base = project()
    mine = project(key_dates=[{"label": "Financial close", "date": "2026-07-01"}])  # deleted Tender launch
    theirs = project(key_dates=[{"label": "Tender launch", "date": "2026-03-01"},
                                {"label": "Financial close", "date": "2026-07-01"}])
    [conflict] = three_way_merge(base, mine, theirs).conflicts
    assert conflict.mine is None and conflict.theirs == KeyDate(label="Tender launch", date=date(2026, 3, 1))


def test_deleting_a_date_nobody_else_touched():
    base = project()
    mine = project(key_dates=[{"label": "Financial close", "date": "2026-07-01"}])
    result = three_way_merge(base, mine, base)
    assert dates(result.merged) == {"Financial close": date(2026, 7, 1)}
    assert result.changed_slots == ["key_dates[Tender launch]"]


def test_both_adding_different_dates_keeps_both():
    base = project()
    mine = project(key_dates=[*base.model_dump()["key_dates"], {"label": "Construction start", "date": "2027-01-01"}])
    theirs = project(key_dates=[*base.model_dump()["key_dates"], {"label": "Commercial operation", "date": "2028-01-01"}])
    result = three_way_merge(base, mine, theirs)
    assert set(dates(result.merged)) == {"Tender launch", "Financial close", "Construction start", "Commercial operation"}


def test_labels_are_case_sensitive_and_trimmed():
    base = project()
    mine = project(key_dates=[{"label": "  Tender launch ", "date": "2026-01-10"},
                              {"label": "financial close", "date": "2026-07-01"}])
    result = three_way_merge(base, mine, base)
    # The trimmed label is unchanged; the lower-case one is a change (a rename, same date).
    assert result.changed_slots == ["key_dates[Financial close]"]
    assert set(dates(result.merged)) == {"Tender launch", "financial close"}


# --- key dates: renames ---------------------------------------------------------------------------

TENDER = {"label": "Tender launch", "date": "2026-01-10"}
CLOSE = {"label": "Financial close", "date": "2026-07-01"}


def renamed(to: str, date_: str = "2026-01-10") -> list[dict]:
    return [{"label": to, "date": date_}, CLOSE]


def test_a_rename_keeps_the_same_date_slot():
    base = project()
    result = three_way_merge(base, project(key_dates=renamed("Tender start")), base)
    assert dates(result.merged) == {"Tender start": date(2026, 1, 10), "Financial close": date(2026, 7, 1)}
    assert result.changed_slots == ["key_dates[Tender launch]"]


def test_renaming_the_same_date_differently_conflicts_instead_of_duplicating():
    base = project()
    result = three_way_merge(base, project(key_dates=renamed("Bid launch")), project(key_dates=renamed("Tender start")))
    [conflict] = result.conflicts
    assert (conflict.slot, conflict.key) == ("key_dates[Tender launch]", "Tender launch")
    assert conflict.mine == KeyDate(label="Bid launch", date=date(2026, 1, 10))
    assert conflict.theirs == KeyDate(label="Tender start", date=date(2026, 1, 10))
    assert set(dates(result.merged)) == {"Tender start", "Financial close"}  # theirs until the user chooses


def test_both_renaming_to_the_same_label_is_not_a_conflict():
    base = project()
    result = three_way_merge(base, project(key_dates=renamed("Tender start")), project(key_dates=renamed("Tender start")))
    assert result.conflicts == [] and result.changed_slots == []


def test_rename_vs_redate_of_the_same_date_conflicts():
    base = project()
    theirs = project(key_dates=[{**TENDER, "date": "2026-03-03"}, CLOSE])
    [conflict] = three_way_merge(base, project(key_dates=renamed("Tender start")), theirs).conflicts
    assert conflict.mine.label == "Tender start" and conflict.theirs.date == date(2026, 3, 3)


def test_rename_vs_delete_of_the_same_date_conflicts():
    base = project()
    [conflict] = three_way_merge(base, project(key_dates=renamed("Tender start")), project(key_dates=[CLOSE])).conflicts
    assert conflict.mine.label == "Tender start" and conflict.theirs is None


def test_renaming_one_date_while_they_rename_another_both_survive():
    base = project()
    theirs = project(key_dates=[TENDER, {"label": "Financing closed", "date": "2026-07-01"}])
    result = three_way_merge(base, project(key_dates=renamed("Tender start")), theirs)
    assert result.conflicts == []
    assert set(dates(result.merged)) == {"Tender start", "Financing closed"}


def test_renaming_and_redating_at_once_is_a_new_date():
    base = project()
    result = three_way_merge(base, project(key_dates=renamed("Tender start", "2026-02-02")), base)
    assert sorted(result.changed_slots) == ["key_dates[Tender launch]", "key_dates[Tender start]"]


def test_ambiguous_renames_are_not_paired():
    # Two dates on the same day, both relabelled: which became which is a guess, so nothing is paired.
    base = project(key_dates=[{"label": "A", "date": "2026-01-01"}, {"label": "B", "date": "2026-01-01"}])
    mine = project(key_dates=[{"label": "C", "date": "2026-01-01"}, {"label": "D", "date": "2026-01-01"}])
    result = three_way_merge(base, mine, base)
    assert sorted(result.changed_slots) == ["key_dates[A]", "key_dates[B]", "key_dates[C]", "key_dates[D]"]


def test_renaming_to_a_label_they_just_added_falls_back_to_the_whole_list():
    base = project()
    theirs = project(key_dates=[TENDER, CLOSE, {"label": "Tender start", "date": "2026-05-05"}])
    result = three_way_merge(base, project(key_dates=renamed("Tender start")), theirs)
    [conflict] = result.conflicts
    assert conflict.slot == "key_dates"
    assert not any(c.slot.startswith("key_dates[") for c in result.conflicts)


def test_retry_after_a_rename_that_landed_is_a_noop():
    base = project()
    mine = project(key_dates=renamed("Tender start"))
    assert three_way_merge(base, mine, mine).changed_slots == []


def test_merged_key_dates_are_sorted_by_date_then_label():
    base = project(key_dates=[{"label": "B", "date": "2026-05-01"}, {"label": "A", "date": "2026-05-01"},
                              {"label": "C", "date": "2026-01-01"}])
    result = three_way_merge(base, base, base)
    assert [kd.label for kd in result.merged.key_dates] == ["C", "A", "B"]


def test_order_only_difference_is_not_a_change():
    base = project()
    reordered = project(key_dates=list(reversed(base.model_dump()["key_dates"])))
    assert three_way_merge(base, reordered, base).changed_slots == []


# --- key dates: duplicate labels fall back to the whole list ------------------------------------

DUPLICATED = [{"label": "Tender launch", "date": "2026-01-10"},
              {"label": "Tender launch", "date": "2026-02-10"},
              {"label": "Financial close", "date": "2026-07-01"}]


def test_duplicates_upstream_survive_an_unrelated_edit():
    theirs = project(key_dates=DUPLICATED)
    result = three_way_merge(theirs, project(key_dates=DUPLICATED, name="Mine"), theirs)
    assert result.conflicts == []
    assert len(result.merged.key_dates) == 3
    assert result.changed_slots == ["name"]


def test_duplicates_appearing_concurrently_survive_my_unrelated_edit():
    base = project()
    result = three_way_merge(base, project(name="Mine"), project(key_dates=DUPLICATED))
    assert len(result.merged.key_dates) == 3 and result.merged.name == "Mine"


def test_with_duplicates_any_concurrent_list_change_conflicts_as_a_whole():
    base = project()
    mine = project(key_dates=[{"label": "Tender launch", "date": "2026-01-10"}])
    [conflict] = three_way_merge(base, mine, project(key_dates=DUPLICATED)).conflicts
    assert (conflict.slot, conflict.field, conflict.key) == ("key_dates", "key_dates", None)
    assert conflict.theirs == [KeyDate.model_validate(kd) for kd in
                               sorted(DUPLICATED, key=lambda kd: (kd["date"], kd["label"]))]


def test_retry_after_a_write_that_landed_is_a_noop():
    base = project()
    mine = project(name="Mine", key_dates=[{"label": "Financial close", "date": "2026-08-01"}])
    assert three_way_merge(base, mine, mine).changed_slots == []


# --- linked companies: one slot per company name, renames paired by role ---------------------------

TALCORA = {"name": "Talcora Capital SpA", "role": "financier"}
VARELO = {"name": "Varelo Energia SA", "role": "owner"}


def companies(result_project: EditableProject) -> dict[str, str]:
    return {c.name: c.role for c in result_project.linked_companies}


def test_adding_and_removing_companies_on_both_sides_merge():
    base = project()
    mine = project(linked_companies=[TALCORA, VARELO, {"name": "Maduri Obras SAC", "role": "epc_contractor"}])
    theirs = project(linked_companies=[VARELO])  # they removed Talcora
    result = three_way_merge(base, mine, theirs)
    assert result.conflicts == []
    assert companies(result.merged) == {"Varelo Energia SA": "owner", "Maduri Obras SAC": "epc_contractor"}
    assert result.changed_slots == ["linked_companies[Maduri Obras SAC]"]


def test_changing_the_role_of_different_companies_both_survive():
    base = project()
    mine = project(linked_companies=[TALCORA, {**VARELO, "role": "developer"}])
    theirs = project(linked_companies=[{**TALCORA, "role": "consultant"}, VARELO])
    result = three_way_merge(base, mine, theirs)
    assert result.conflicts == []
    assert companies(result.merged) == {"Talcora Capital SpA": "consultant", "Varelo Energia SA": "developer"}


def test_changing_the_role_of_the_same_company_differently_conflicts():
    base = project()
    mine = project(linked_companies=[TALCORA, {**VARELO, "role": "developer"}])
    theirs = project(linked_companies=[TALCORA, {**VARELO, "role": "consultant"}])
    [conflict] = three_way_merge(base, mine, theirs).conflicts
    assert (conflict.slot, conflict.field, conflict.key) == (
        "linked_companies[Varelo Energia SA]", "linked_companies", "Varelo Energia SA")
    assert (conflict.mine.role, conflict.theirs.role) == ("developer", "consultant")


def test_role_change_vs_removal_of_the_same_company_conflicts():
    base = project()
    mine = project(linked_companies=[TALCORA, {**VARELO, "role": "developer"}])
    [conflict] = three_way_merge(base, mine, project(linked_companies=[TALCORA])).conflicts
    assert conflict.theirs is None


def test_renaming_the_same_company_differently_conflicts_instead_of_duplicating():
    base = project()
    mine = project(linked_companies=[TALCORA, {**VARELO, "name": "Varelo Energía S.A."}])
    theirs = project(linked_companies=[TALCORA, {**VARELO, "name": "Varelo Energia S.A."}])
    result = three_way_merge(base, mine, theirs)
    [conflict] = result.conflicts
    assert conflict.key == "Varelo Energia SA"
    assert (conflict.mine.name, conflict.theirs.name) == ("Varelo Energía S.A.", "Varelo Energia S.A.")
    assert len(result.merged.linked_companies) == 2


def test_a_company_name_fix_is_a_rename_not_a_new_company():
    base = project()
    mine = project(linked_companies=[TALCORA, {**VARELO, "name": "Varelo Energia S.A."}])
    result = three_way_merge(base, mine, base)
    assert result.changed_slots == ["linked_companies[Varelo Energia SA]"]


def test_same_company_twice_with_two_roles_falls_back_to_the_whole_list():
    stored = project(linked_companies=[TALCORA, VARELO, {**VARELO, "role": "developer"}])
    result = three_way_merge(stored, project(linked_companies=stored.model_dump()["linked_companies"], name="Mine"), stored)
    assert result.conflicts == [] and len(result.merged.linked_companies) == 3


def test_company_and_key_date_conflicts_are_independent():
    base = project()
    mine = project(linked_companies=[TALCORA], name="Mine")  # removed Varelo
    theirs = project(key_dates=[{"label": "Tender launch", "date": "2026-09-09"},
                                {"label": "Financial close", "date": "2026-07-01"}])
    result = three_way_merge(base, mine, theirs)
    assert result.conflicts == []
    assert companies(result.merged) == {"Talcora Capital SpA": "financier"}
    assert dates(result.merged)["Tender launch"] == date(2026, 9, 9)
