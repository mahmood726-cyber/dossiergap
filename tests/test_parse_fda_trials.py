"""Task 7 — FDA per-trial extractor tests.

Pure-function tests exercise the extractor with synthetic text.
Integration test runs against the real Entresto MedR.

Scope (Phase 1):
- One TrialRecord per MedR (primary pivotal trial only).
- HR as the primary effect metric (cardiology-typical).
- reported_in_label is a Phase-1 placeholder set to True for pivotal trials;
  accurate extraction deferred to Task 7.1.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dossiergap.parse.fda_trials import (
    ExtractionError,
    extract_primary_trial,
    extract_primary_trial_from_pdf,
)
from dossiergap.parse.fda_sections import find_efficacy_section

ENTRESTO_PDF = (
    Path(__file__).resolve().parents[1] / "cache" / "fda" / "207620" / "medical_review.pdf"
)

# Common meta-kwargs for constructing a TrialRecord from extractor output.
META = dict(
    source="FDA",
    dossier_id="207620",
    drug_inn="sacubitril/valsartan",
    sponsor="Novartis",
)

CLEAN_EFFICACY_TEXT = (
    "6 Review of Efficacy\n"
    "Efficacy Summary\n"
    "In support of the proposed indication, Novartis conducted PARADIGM-HF, a "
    "randomized, double-blind, active-controlled, outcomes trial in which 8,442 "
    "subjects were randomized to treatment with LCZ696 or enalapril. "
    "The primary endpoint was cardiovascular death or first heart failure "
    "hospitalization. "
    "LCZ696 reduced the risk of the primary composite endpoint "
    "(HR 0.80; 95% CI 0.73, 0.87; 1-sided p<0.0001). "
    "PARADIGM-HF was a Phase 3 pivotal study. "
    "ClinicalTrials.gov identifier: NCT01035255."
)


# -- happy path -------------------------------------------------------------

def test_extracts_valid_record_from_clean_text():
    pages = {55: CLEAN_EFFICACY_TEXT}
    r = extract_primary_trial(pages, **META)
    assert r.effect_metric == "HR"
    assert r.effect_estimate == pytest.approx(0.80)
    assert r.effect_ci_low == pytest.approx(0.73)
    assert r.effect_ci_high == pytest.approx(0.87)
    assert r.n_randomized == 8442
    assert r.nct_id == "NCT01035255"
    assert "cardiovascular death" in r.primary_outcome.lower()
    assert r.trial_phase == "3"
    assert r.pivotal_strict is True
    assert r.pivotal_inclusive is True
    assert 55 in r.source_page_refs


def test_nct_optional_when_absent():
    text = CLEAN_EFFICACY_TEXT.replace(
        "ClinicalTrials.gov identifier: NCT01035255.", ""
    )
    pages = {55: text}
    r = extract_primary_trial(pages, **META)
    assert r.nct_id is None


def test_strict_false_when_pivotal_not_mentioned():
    """Strict pivotal requires explicit label; inclusive applies by being in efficacy section."""
    text = CLEAN_EFFICACY_TEXT.replace("pivotal study", "study")
    pages = {55: text}
    r = extract_primary_trial(pages, **META)
    assert r.pivotal_strict is False
    assert r.pivotal_inclusive is True


# -- multi-page extraction ---------------------------------------------------

def test_combines_evidence_across_multiple_pages():
    """Fields can be spread across pages — extractor must search all pages."""
    pages = {
        55: "6 Review of Efficacy\nNovartis conducted PARADIGM-HF, a Phase 3 pivotal study.",
        56: "The primary endpoint was cardiovascular death or first heart failure hospitalization.",
        65: "In PARADIGM-HF, 8,442 subjects were randomized to treatment.",
        70: "The primary composite endpoint favoured LCZ696 (HR 0.80; 95% CI 0.73, 0.87).",
    }
    r = extract_primary_trial(pages, **META)
    assert r.n_randomized == 8442
    assert r.effect_estimate == pytest.approx(0.80)
    # source_page_refs should include the pages where extractions landed
    assert set(r.source_page_refs) >= {55, 56, 65, 70}


# -- fail-closed contracts ---------------------------------------------------

def test_raises_when_no_hr_found():
    text = CLEAN_EFFICACY_TEXT.replace("HR 0.80; 95% CI 0.73, 0.87", "")
    pages = {55: text}
    with pytest.raises(ExtractionError, match="effect estimate|HR"):
        extract_primary_trial(pages, **META)


def test_raises_when_no_n_randomized_found():
    text = CLEAN_EFFICACY_TEXT.replace("8,442 subjects were randomized", "patients enrolled")
    pages = {55: text}
    with pytest.raises(ExtractionError, match="N randomi"):
        extract_primary_trial(pages, **META)


def test_raises_when_no_trial_name_found():
    text = CLEAN_EFFICACY_TEXT.replace("PARADIGM-HF", "the study")
    pages = {55: text}
    with pytest.raises(ExtractionError, match="trial name"):
        extract_primary_trial(pages, **META)


def test_raises_when_no_primary_outcome_found():
    text = CLEAN_EFFICACY_TEXT.replace(
        "The primary endpoint was cardiovascular death or first heart failure hospitalization. ",
        "",
    )
    assert "The primary endpoint was" not in text, "fixture setup failed"
    pages = {55: text}
    with pytest.raises(ExtractionError, match="primary outcome|endpoint"):
        extract_primary_trial(pages, **META)


def test_rejects_tiny_n_as_noise():
    """'4 subjects randomized' is almost certainly not the trial N — reject and search more."""
    text = "The run-in phase had 4 subjects randomized to placebo. " + CLEAN_EFFICACY_TEXT
    pages = {55: text}
    r = extract_primary_trial(pages, **META)
    assert r.n_randomized == 8442  # not 4


def test_rejects_not_randomized_count():
    """Regression guard for Verquvo VICTORIA EPAR: a 'Not Randomized 1,807'
    table row must not be picked up as the trial N. Fix discovered 2026-04-15
    when re-auditing Task 14 output."""
    text = (
        "Review of Efficacy: Trial TEST-NAME Phase 3 pivotal study. "
        "Disposition of subjects. Not Randomized 1,807 "
        "Then 9,999 patients were randomized to treatment. "
        "The primary endpoint was all-cause mortality. "
        "HR 0.80; 95% CI 0.73, 0.87."
    )
    pages = {1: text}
    r = extract_primary_trial(pages, **META)
    assert r.n_randomized == 9999, (
        "negation-preceded N count was incorrectly extracted"
    )


# -- effect-value parsing edge cases -----------------------------------------

def test_parses_hr_with_comma_separated_ci():
    """FDA format: HR 0.80; 95% CI 0.73, 0.87"""
    pages = {1: "Phase 3 pivotal study TRIAL-X randomized 1,000 subjects. "
                "The primary endpoint was major adverse cardiovascular events. "
                "HR 0.85; 95% CI 0.70, 0.95."}
    r = extract_primary_trial(pages, **META)
    assert r.effect_estimate == pytest.approx(0.85)
    assert r.effect_ci_low == pytest.approx(0.70)
    assert r.effect_ci_high == pytest.approx(0.95)


def test_parses_hr_with_dash_separated_ci():
    """Some reports use dash: HR 0.80 (95% CI 0.73-0.87)"""
    pages = {1: "TRIAL-Y Phase 3 pivotal study randomized 2,500 patients. "
                "The primary endpoint was cardiovascular mortality. "
                "HR 0.75 (95% CI 0.60-0.90)."}
    r = extract_primary_trial(pages, **META)
    assert r.effect_estimate == pytest.approx(0.75)
    assert r.effect_ci_low == pytest.approx(0.60)
    assert r.effect_ci_high == pytest.approx(0.90)


def test_ci_invariant_enforced_by_schema():
    """If extraction returns implausible values, schema validation must reject them."""
    pages = {1: "TRIAL-Z Phase 3 pivotal study randomized 1,000 subjects. "
                "The primary endpoint was all-cause mortality. "
                "HR 0.50; 95% CI 0.70, 0.90."}
    # CI does not contain estimate — TrialRecord validator should reject
    with pytest.raises(Exception):  # ValidationError or ExtractionError
        extract_primary_trial(pages, **META)


# -- integration against real Entresto MedR ---------------------------------

@pytest.mark.skipif(
    not ENTRESTO_PDF.is_file(),
    reason="cached Entresto MedR not present; run smoke fetch to populate",
)
def test_real_entresto_extraction():
    eff_range = find_efficacy_section(ENTRESTO_PDF)
    r = extract_primary_trial_from_pdf(ENTRESTO_PDF, eff_range, **META)

    # Hand-audited PARADIGM-HF values from the Entresto NDA 207620 MedR:
    assert r.effect_metric == "HR"
    assert r.effect_estimate == pytest.approx(0.80, abs=0.01)
    assert r.effect_ci_low == pytest.approx(0.73, abs=0.01)
    assert r.effect_ci_high == pytest.approx(0.87, abs=0.01)
    assert r.n_randomized == 8442
    assert "cardiovascular death" in r.primary_outcome.lower()
    assert r.pivotal_inclusive is True
    assert len(r.source_page_refs) >= 1
