"""The corrections change exactly the planned fields."""

import json

import pytest
from conftest import PLAN, planned, record
from correction import NEW_LABEL, OLD_LABEL, CorrectionError, correct, diff, dump, load

SPACING_10UM = [0.010125, 0.0135, 0.010125]


def changes(subject, file="ccf_alignment/processing.json"):
    entry = planned(subject, file)
    raw = record(subject, file)
    fixed, summary = correct(raw, entry["relabel"], entry["spacing"])
    return diff(load(raw)[0], load(fixed)[0]), summary, fixed


@pytest.mark.parametrize("subject", ["841260", "782644", "744782", "754611", "721828"])
def test_published_records_round_trip_byte_for_byte(subject):
    raw = record(subject)
    assert dump(*load(raw)) == raw


def test_a_new_format_record_changes_only_its_labels_and_spacing():
    found, summary, _ = changes("841260")
    assert summary == {"relabels": record("841260").decode().count(OLD_LABEL), "spacing_added": 2}
    fields = sorted({path.rsplit(".", 1)[-1].split("[")[0] for path, _, _ in found})
    assert fields == [
        "applied_spacing_mm",
        "ccf_to_template_fwd",
        "notes",
        "template_to_ccf_transforms",
    ]
    added = {path: new for path, old, new in found if old == "<absent>"}
    assert SPACING_10UM in added.values()


def test_the_root_record_gets_the_same_changes():
    _, summary, fixed = changes("841260", "processing.json")
    assert summary["spacing_added"] == 2 and summary["relabels"] > 0
    assert OLD_LABEL not in fixed.decode()


def test_an_old_format_record_changes_only_its_notes():
    found, summary, fixed = changes("782644")
    assert summary == {"relabels": record("782644").decode().count(OLD_LABEL), "spacing_added": 0}
    assert {path.rsplit(".", 1)[-1] for path, _, _ in found} == {"notes"}
    assert NEW_LABEL in fixed.decode() and OLD_LABEL not in fixed.decode()


def test_older_spacing_equals_sample_scale():
    found, _, _ = changes("744782")
    added = [new for path, old, new in found if old == "<absent>"]
    assert [0.010125, 0.010125, 0.0135] in added and [0.02025, 0.02025, 0.027] in added


@pytest.mark.parametrize("subject", ["754611", "721828"])
def test_records_outside_the_plan_are_untouched(subject):
    assert not [p for p in PLAN if p["subject"] == subject]
    raw = record(subject)
    fixed, summary = correct(raw, relabel_record=False, spacing={})
    assert fixed == raw and summary == {"relabels": 0, "spacing_added": 0}


def test_correcting_twice_changes_nothing_more():
    entry = planned("841260")
    once, _ = correct(record("841260"), entry["relabel"], entry["spacing"])
    twice, summary = correct(once, entry["relabel"], entry["spacing"])
    assert twice == once and summary == {"relabels": 0, "spacing_added": 0}


def test_a_spacing_that_is_not_a_reordering_is_refused():
    with pytest.raises(CorrectionError, match="not a reordering"):
        correct(record("841260"), False, {"Image atlas alignment - 10 um": [0.01, 0.01, 0.01]})


def test_a_different_existing_spacing_is_refused():
    entry = planned("841260")
    once, _ = correct(record("841260"), entry["relabel"], entry["spacing"])
    other = {"Image atlas alignment - 10 um": [0.0135, 0.010125, 0.010125]}
    with pytest.raises(CorrectionError, match="already has a different"):
        correct(once, False, other)


def test_a_label_outside_the_expected_fields_is_refused():
    doc = json.loads(record("841260"))
    doc["data_processes"][0]["code"]["url"] = f"https://x/{OLD_LABEL}"
    with pytest.raises(CorrectionError, match="outside the expected fields"):
        correct(dump(doc, False), True, {})


def test_a_record_that_does_not_round_trip_is_refused():
    raw = record("841260").replace(b"   ", b"  ", 1)
    with pytest.raises(CorrectionError, match="byte for byte"):
        correct(raw, True, {})
