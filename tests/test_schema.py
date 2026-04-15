"""Task 5 — TrialRecord schema tests.

The schema is the contract between Tasks 7/9 (extractors), Task 10
(dedup), and Task 11 (CSV writer). Tests here lock invariants the rest
of Phase 1 will depend on.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from dossiergap.schema import TrialRecord


def _valid_kwargs(**overrides):
    base = dict(
        source="FDA",
        dossier_id="207620",
        drug_inn="sacubitril/valsartan",
        sponsor="Novartis",
        trial_phase="3",
        nct_id="NCT01035255",
        n_randomized=8442,
        primary_outcome="CV death or HF hospitalization",
        effect_metric="HR",
        effect_estimate=0.80,
        effect_ci_low=0.73,
        effect_ci_high=0.87,
        reported_in_label=True,
        pivotal_strict=True,
        pivotal_inclusive=True,
        source_page_refs=[42, 88, 103],
    )
    base.update(overrides)
    return base


# -- happy path + round-trip --------------------------------------------------

def test_valid_record_constructs():
    r = TrialRecord(**_valid_kwargs())
    assert r.drug_inn == "sacubitril/valsartan"
    assert r.effect_estimate == pytest.approx(0.80)


def test_model_dict_round_trip():
    original = TrialRecord(**_valid_kwargs())
    d = original.model_dump()
    rebuilt = TrialRecord(**d)
    assert rebuilt == original


def test_nct_none_is_valid():
    r = TrialRecord(**_valid_kwargs(nct_id=None))
    assert r.nct_id is None


# -- source / phase / metric enums -------------------------------------------

def test_invalid_source_raises():
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(source="HC"))  # Health Canada — out of Phase 1 scope


def test_invalid_phase_raises():
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(trial_phase="1"))


def test_invalid_effect_metric_raises():
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(effect_metric="foo"))


def test_accepted_phases():
    for phase in ("2", "2/3", "3", "3b", "4"):
        TrialRecord(**_valid_kwargs(trial_phase=phase))


def test_accepted_metrics():
    for metric in ("HR", "RR", "OR", "MD", "SMD", "RD"):
        TrialRecord(**_valid_kwargs(effect_metric=metric))


# -- NCT pattern --------------------------------------------------------------

def test_invalid_nct_raises():
    with pytest.raises(ValidationError, match="NCT"):
        TrialRecord(**_valid_kwargs(nct_id="12345678"))


def test_nct_lowercase_is_rejected():
    with pytest.raises(ValidationError, match="NCT"):
        TrialRecord(**_valid_kwargs(nct_id="nct01035255"))


def test_nct_too_few_digits_rejected():
    with pytest.raises(ValidationError, match="NCT"):
        TrialRecord(**_valid_kwargs(nct_id="NCT1234567"))


# -- CI contains estimate invariant -------------------------------------------

def test_ci_must_contain_estimate_lower_bound():
    with pytest.raises(ValidationError, match="ci"):
        TrialRecord(**_valid_kwargs(effect_ci_low=0.85, effect_estimate=0.80))


def test_ci_must_contain_estimate_upper_bound():
    with pytest.raises(ValidationError, match="ci"):
        TrialRecord(**_valid_kwargs(effect_ci_high=0.75, effect_estimate=0.80))


def test_ci_equal_to_estimate_is_ok():
    """Tight CI (estimate == bound) is valid though rare."""
    TrialRecord(**_valid_kwargs(effect_ci_low=0.80, effect_estimate=0.80))


def test_ci_low_above_high_raises():
    with pytest.raises(ValidationError, match="ci"):
        TrialRecord(**_valid_kwargs(effect_ci_low=0.9, effect_ci_high=0.7, effect_estimate=0.8))


# -- source_page_refs audit-trail requirement --------------------------------

def test_empty_page_refs_raises():
    """Every trial must have at least one page reference — audit trail required."""
    with pytest.raises(ValidationError, match="source_page_refs"):
        TrialRecord(**_valid_kwargs(source_page_refs=[]))


def test_negative_page_ref_raises():
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(source_page_refs=[-1, 5]))


def test_zero_page_ref_raises():
    """PDF pages are 1-indexed in audit references."""
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(source_page_refs=[0, 5]))


# -- pivotal_strict ⊆ pivotal_inclusive invariant -----------------------------

def test_strict_true_requires_inclusive_true():
    """Strict is a subset of inclusive by construction — no trial can be
    strict-pivotal without also being inclusive-pivotal."""
    with pytest.raises(ValidationError, match="pivotal"):
        TrialRecord(**_valid_kwargs(pivotal_strict=True, pivotal_inclusive=False))


def test_strict_false_with_inclusive_true_is_ok():
    """Inclusive-only (e.g., a Phase 3 supportive trial) is valid."""
    TrialRecord(**_valid_kwargs(pivotal_strict=False, pivotal_inclusive=True))


def test_both_false_is_ok():
    """Non-pivotal trial — valid record, will be filtered downstream."""
    TrialRecord(**_valid_kwargs(pivotal_strict=False, pivotal_inclusive=False))


# -- N_randomized positivity --------------------------------------------------

def test_zero_randomized_raises():
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(n_randomized=0))


def test_negative_randomized_raises():
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(n_randomized=-10))


# -- silent-failure sentinel defence (per 2026-04-14 MetaReproducer lesson) ---

def test_empty_primary_outcome_raises():
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(primary_outcome=""))


def test_empty_sponsor_raises():
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(sponsor=""))


def test_empty_drug_inn_raises():
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(drug_inn=""))


def test_empty_dossier_id_raises():
    with pytest.raises(ValidationError):
        TrialRecord(**_valid_kwargs(dossier_id=""))
