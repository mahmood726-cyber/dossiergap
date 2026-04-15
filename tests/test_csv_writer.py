"""Task 11 — CSV writer tests.

Contract: write_csv(groups, path, version_tag) produces a UTF-8 CSV with
a leading '# ' comment row (version tag + date) and a frozen column order
matching CSV_COLUMNS. read_csv + row_to_trial_record round-trips the
canonical TrialRecord fields losslessly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dossiergap.dedup import DedupGroup, dedup_trials
from dossiergap.io.csv_writer import (
    CSV_COLUMNS,
    read_csv,
    row_to_trial_record,
    write_csv,
)
from dossiergap.schema import TrialRecord


def _rec(**overrides) -> TrialRecord:
    base = dict(
        source="FDA",
        dossier_id="207620",
        drug_inn="sacubitril/valsartan",
        sponsor="Novartis",
        trial_phase="3",
        nct_id="NCT01035255",
        n_randomized=8442,
        primary_outcome="CV death or first HF hospitalization",
        effect_metric="HR",
        effect_estimate=0.80,
        effect_ci_low=0.73,
        effect_ci_high=0.87,
        reported_in_label=True,
        pivotal_strict=True,
        pivotal_inclusive=True,
        source_page_refs=[55, 65, 68],
    )
    base.update(overrides)
    return TrialRecord(**base)


# -- header + column order ---------------------------------------------------

def test_leading_comment_row_includes_version_tag(tmp_path):
    out = tmp_path / "dossier_trials.v0.1.0.csv"
    write_csv([], out, version_tag="v0.1.0")
    first = out.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("#")
    assert "v0.1.0" in first


def test_column_order_is_frozen(tmp_path):
    out = tmp_path / "trials.csv"
    write_csv([DedupGroup(canonical=_rec(), records=[_rec()])], out)
    lines = out.read_text(encoding="utf-8").splitlines()
    # lines[0] is the comment; lines[1] is the CSV header
    header = lines[1].split(",")
    assert header == CSV_COLUMNS


def test_empty_groups_produces_header_only(tmp_path):
    out = tmp_path / "empty.csv"
    write_csv([], out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # comment + column header
    assert lines[1].split(",") == CSV_COLUMNS


# -- round-trip --------------------------------------------------------------

def test_round_trip_preserves_canonical_fields(tmp_path):
    original = _rec()
    out = tmp_path / "rt.csv"
    write_csv([DedupGroup(canonical=original, records=[original])], out)
    rows = read_csv(out)
    assert len(rows) == 1
    parsed = row_to_trial_record(rows[0])
    assert parsed == original


def test_round_trip_preserves_nct_none(tmp_path):
    original = _rec(nct_id=None)
    out = tmp_path / "rt.csv"
    write_csv([DedupGroup(canonical=original, records=[original])], out)
    parsed = row_to_trial_record(read_csv(out)[0])
    assert parsed.nct_id is None


def test_round_trip_preserves_page_refs(tmp_path):
    original = _rec(source_page_refs=[55, 65, 68, 79])
    out = tmp_path / "rt.csv"
    write_csv([DedupGroup(canonical=original, records=[original])], out)
    parsed = row_to_trial_record(read_csv(out)[0])
    assert parsed.source_page_refs == [55, 65, 68, 79]


# -- dedup metadata columns --------------------------------------------------

def test_fda_ema_group_emits_both_sources(tmp_path):
    fda = _rec(source="FDA", dossier_id="207620", source_page_refs=[55, 65])
    ema = _rec(
        source="EMA", dossier_id="EMEA/H/C/004062",
        source_page_refs=[60, 72],
    )
    (group,) = dedup_trials([fda, ema])
    out = tmp_path / "merged.csv"
    write_csv([group], out)
    row = read_csv(out)[0]
    assert set(row["all_sources"].split("|")) == {"FDA", "EMA"}
    assert "207620" in row["all_dossier_ids"]
    assert "EMEA/H/C/004062" in row["all_dossier_ids"]
    assert row["page_refs_fda"] == "55|65"
    assert row["page_refs_ema"] == "60|72"


def test_single_source_group_has_empty_page_refs_for_other_source(tmp_path):
    fda = _rec(source="FDA")
    (group,) = dedup_trials([fda])
    out = tmp_path / "single.csv"
    write_csv([group], out)
    row = read_csv(out)[0]
    assert row["all_sources"] == "FDA"
    assert row["page_refs_fda"] != ""
    assert row["page_refs_ema"] == ""


def test_conflicts_serialized_as_json(tmp_path):
    fda = _rec(effect_estimate=0.80)
    ema = _rec(
        source="EMA", dossier_id="EMEA/H/C/004062",
        effect_estimate=0.79,
        effect_ci_low=0.72,
        effect_ci_high=0.86,
    )
    (group,) = dedup_trials([fda, ema])
    out = tmp_path / "conflict.csv"
    write_csv([group], out)
    row = read_csv(out)[0]
    conflicts = json.loads(row["dedup_conflicts"])
    assert "effect_estimate" in conflicts
    assert set(conflicts["effect_estimate"]) == {0.80, 0.79}


def test_empty_conflicts_serialized_as_empty_string(tmp_path):
    r = _rec()
    (group,) = dedup_trials([r])
    out = tmp_path / "no_conflict.csv"
    write_csv([group], out)
    row = read_csv(out)[0]
    assert row["dedup_conflicts"] == ""


# -- canonical source selection ---------------------------------------------

def test_canonical_source_is_fda_when_both_present(tmp_path):
    fda = _rec(source="FDA")
    ema = _rec(source="EMA", dossier_id="EMEA/H/C/004062")
    (group,) = dedup_trials([ema, fda])  # EMA first
    out = tmp_path / "canon.csv"
    write_csv([group], out)
    row = read_csv(out)[0]
    assert row["source"] == "FDA"


# -- multiple groups --------------------------------------------------------

def test_multiple_groups_emit_multiple_rows(tmp_path):
    a = _rec(nct_id="NCT00000001", drug_inn="drug-a", sponsor="SponsorA")
    b = _rec(nct_id="NCT00000002", drug_inn="drug-b", sponsor="SponsorB")
    c = _rec(nct_id="NCT00000003", drug_inn="drug-c", sponsor="SponsorC")
    groups = dedup_trials([a, b, c])
    out = tmp_path / "multi.csv"
    write_csv(groups, out)
    assert len(read_csv(out)) == 3


# -- utf-8 / unicode handling -----------------------------------------------

def test_unicode_in_outcome_preserved(tmp_path):
    r = _rec(primary_outcome="Death from any cause (≥7 days post-randomization)")
    (group,) = dedup_trials([r])
    out = tmp_path / "unicode.csv"
    write_csv([group], out)
    row = read_csv(out)[0]
    assert "≥" in row["primary_outcome"]


# -- fail-closed on bad input -----------------------------------------------

def test_writer_preserves_column_count_per_row(tmp_path):
    """A row must have exactly len(CSV_COLUMNS) fields — no accidental extras."""
    (group,) = dedup_trials([_rec()])
    out = tmp_path / "count.csv"
    write_csv([group], out)
    lines = out.read_text(encoding="utf-8").splitlines()
    data_row = lines[2]  # skip comment + header
    # csv.DictWriter handles quoting so field-count check via re-read:
    rows = read_csv(out)
    assert set(rows[0].keys()) == set(CSV_COLUMNS)
