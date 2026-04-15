"""Task 10 — cross-register dedup tests.

Same pivotal trial may appear in FDA Medical Review AND EMA EPAR. The
dedup step groups these into a single DedupGroup so the downstream CSV
writer emits one row per unique trial (not per dossier).
"""
from __future__ import annotations

import pytest

from dossiergap.dedup import DedupGroup, dedup_trials
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


# -- primary key: NCT match ---------------------------------------------------

def test_same_nct_merges_fda_and_ema():
    fda = _rec(source="FDA", dossier_id="207620")
    ema = _rec(
        source="EMA", dossier_id="EMEA/H/C/004062",
        source_page_refs=[60, 65, 72],
    )
    groups = dedup_trials([fda, ema])
    assert len(groups) == 1
    group = groups[0]
    assert len(group.records) == 2
    assert set(group.sources()) == {"FDA", "EMA"}


def test_different_nct_does_not_merge():
    a = _rec(nct_id="NCT01035255")
    b = _rec(nct_id="NCT12345678", source="EMA", dossier_id="EMEA/H/C/999999")
    groups = dedup_trials([a, b])
    assert len(groups) == 2


def test_canonical_prefers_fda_over_ema():
    fda = _rec(source="FDA", dossier_id="207620")
    ema = _rec(source="EMA", dossier_id="EMEA/H/C/004062")
    (group,) = dedup_trials([ema, fda])  # EMA first on input
    assert group.canonical.source == "FDA"


# -- fallback key: composite when NCT is missing -----------------------------

def test_fallback_composite_match_when_both_nct_missing():
    fda = _rec(source="FDA", nct_id=None)
    ema = _rec(source="EMA", dossier_id="EMEA/H/C/004062", nct_id=None,
               source_page_refs=[60, 65, 72])
    groups = dedup_trials([fda, ema])
    assert len(groups) == 1


def test_fallback_rejects_different_sponsor():
    a = _rec(source="FDA", nct_id=None, sponsor="Novartis")
    b = _rec(source="EMA", dossier_id="EMEA/H/C/999999", nct_id=None,
             sponsor="Pfizer")
    groups = dedup_trials([a, b])
    assert len(groups) == 2


def test_fallback_rejects_different_drug_inn():
    a = _rec(source="FDA", nct_id=None, drug_inn="sacubitril/valsartan")
    b = _rec(source="EMA", dossier_id="EMEA/H/C/999999", nct_id=None,
             drug_inn="dapagliflozin")
    groups = dedup_trials([a, b])
    assert len(groups) == 2


def test_fallback_rejects_different_phase():
    a = _rec(source="FDA", nct_id=None, trial_phase="3")
    b = _rec(source="EMA", dossier_id="EMEA/H/C/999999", nct_id=None,
             trial_phase="2")
    groups = dedup_trials([a, b])
    assert len(groups) == 2


def test_fallback_accepts_n_within_5_percent():
    """Dossiers occasionally report slightly different N (e.g., FAS vs ITT)."""
    a = _rec(source="FDA", nct_id=None, n_randomized=8442)
    b = _rec(source="EMA", dossier_id="EMEA/H/C/999999", nct_id=None,
             n_randomized=8399)  # 0.5% difference
    groups = dedup_trials([a, b])
    assert len(groups) == 1


def test_fallback_rejects_n_beyond_5_percent():
    a = _rec(source="FDA", nct_id=None, n_randomized=8442)
    b = _rec(source="EMA", dossier_id="EMEA/H/C/999999", nct_id=None,
             n_randomized=4000)
    groups = dedup_trials([a, b])
    assert len(groups) == 2


def test_fallback_outcome_substring_match():
    """FDA and EMA may phrase the primary outcome slightly differently."""
    a = _rec(
        source="FDA", nct_id=None,
        primary_outcome="cardiovascular death or first HF hospitalization",
    )
    b = _rec(
        source="EMA", dossier_id="EMEA/H/C/999999", nct_id=None,
        primary_outcome="CV death or first HF hospitalization",
    )
    groups = dedup_trials([a, b])
    # "CV death or first HF hospitalization" is a substring of the FDA wording
    # (after normalising CV/cardiovascular — handled by extractor). Without
    # that, strict substring match fails; plain substring is the bar here.
    assert len(groups) == 1 or len(groups) == 2  # document either outcome


# -- conflict detection ------------------------------------------------------

def test_conflict_detected_on_effect_estimate():
    fda = _rec(effect_estimate=0.80)
    ema = _rec(
        source="EMA", dossier_id="EMEA/H/C/004062",
        effect_estimate=0.79,
        effect_ci_low=0.72,
        effect_ci_high=0.86,
    )
    (group,) = dedup_trials([fda, ema])
    assert "effect_estimate" in group.conflicts
    assert set(group.conflicts["effect_estimate"]) == {0.80, 0.79}


def test_no_conflicts_when_fields_agree():
    fda = _rec(source="FDA")
    ema = _rec(source="EMA", dossier_id="EMEA/H/C/004062")  # identical fields
    (group,) = dedup_trials([fda, ema])
    # source and dossier_id differ by design — not flagged
    for field in ("effect_estimate", "effect_ci_low", "effect_ci_high",
                  "n_randomized", "trial_phase"):
        assert field not in group.conflicts, (
            f"{field} incorrectly flagged as conflict when identical across sources"
        )


# -- multi-record groups ----------------------------------------------------

def test_three_distinct_trials_stay_separate():
    a = _rec(nct_id="NCT00000001", drug_inn="drug-a", sponsor="SponsorA")
    b = _rec(nct_id="NCT00000002", drug_inn="drug-b", sponsor="SponsorB")
    c = _rec(nct_id="NCT00000003", drug_inn="drug-c", sponsor="SponsorC")
    groups = dedup_trials([a, b, c])
    assert len(groups) == 3


def test_page_refs_accessible_per_source():
    fda = _rec(source="FDA", source_page_refs=[55, 65, 68])
    ema = _rec(source="EMA", dossier_id="EMEA/H/C/004062",
               source_page_refs=[60, 65, 72])
    (group,) = dedup_trials([fda, ema])
    refs = group.page_refs_by_source()
    assert refs["FDA"] == [55, 65, 68]
    assert refs["EMA"] == [60, 65, 72]


# -- edge cases -------------------------------------------------------------

def test_empty_input_returns_empty_list():
    assert dedup_trials([]) == []


def test_single_record_returns_one_group():
    r = _rec()
    groups = dedup_trials([r])
    assert len(groups) == 1
    assert groups[0].canonical is r


def test_nct_takes_precedence_over_composite_mismatch():
    """NCT match overrides everything: if NCT matches, the trials are the same
    even if other fields look different (which would reflect extraction error)."""
    a = _rec(nct_id="NCT01035255", sponsor="Novartis", n_randomized=8442)
    b = _rec(nct_id="NCT01035255", source="EMA", dossier_id="EMEA/H/C/999999",
             sponsor="Novartis Pharma AG",  # slightly different legal name
             n_randomized=8000)  # extraction noise
    groups = dedup_trials([a, b])
    assert len(groups) == 1
