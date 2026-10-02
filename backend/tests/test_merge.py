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
    assert (conflict.slot, conflict.field, conflict.label) == ("name", "name", None)
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
    assert (conflict.slot, conflict.field, conflict.label) == ("key_dates[Tender launch]", "key_dates", "Tender launch")
    assert (conflict.base, conflict.mine, conflict.theirs) == (date(2026, 1, 10), date(2026, 2, 1), date(2026, 3, 1))


def test_redate_vs_delete_of_the_same_label_conflicts():
    base = project()
    mine = project(key_dates=[{"label": "Financial close", "date": "2026-07-01"}])  # deleted Tender launch
    theirs = project(key_dates=[{"label": "Tender launch", "date": "2026-03-01"},
                                {"label": "Financial close", "date": "2026-07-01"}])
    [conflict] = three_way_merge(base, mine, theirs).conflicts
    assert conflict.mine is None and conflict.theirs == date(2026, 3, 1)


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


def test_renaming_a_label_is_a_remove_plus_an_add():
    base = project()
    mine = project(key_dates=[{"label": "Tender start", "date": "2026-01-10"},
                              {"label": "Financial close", "date": "2026-07-01"}])
    result = three_way_merge(base, mine, base)
    assert dates(result.merged) == {"Tender start": date(2026, 1, 10), "Financial close": date(2026, 7, 1)}
    assert sorted(result.changed_slots) == ["key_dates[Tender launch]", "key_dates[Tender start]"]


def test_labels_are_case_sensitive_and_trimmed():
    base = project()
    mine = project(key_dates=[{"label": "  Tender launch ", "date": "2026-01-10"},
                              {"label": "financial close", "date": "2026-07-01"}])
    result = three_way_merge(base, mine, base)
    # The trimmed label is the same date; the lower-case one is a different date.
    assert sorted(result.changed_slots) == ["key_dates[Financial close]", "key_dates[financial close]"]


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
    assert (conflict.slot, conflict.field, conflict.label) == ("key_dates", "key_dates", None)
    assert conflict.theirs == [KeyDate.model_validate(kd) for kd in
                               sorted(DUPLICATED, key=lambda kd: (kd["date"], kd["label"]))]


def test_retry_after_a_write_that_landed_is_a_noop():
    base = project()
    mine = project(name="Mine", key_dates=[{"label": "Financial close", "date": "2026-08-01"}])
    assert three_way_merge(base, mine, mine).changed_slots == []
