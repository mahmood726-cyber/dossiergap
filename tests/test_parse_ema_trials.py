"""Task 9 — EMA EPAR per-trial extractor tests.

EMA EPARs present primary HR/CI in a table rather than a prose sentence.
The table format is distinctive:
    'Hazard ratio 0.80 | 95%-CI 0.73, 0.87 | P-value ...'

Narrative 'HR X, 95% CI Y to Z' also appears but typically for subgroup
or post-hoc analyses. The extractor must prefer the table format.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dossiergap.parse.ema_trials import (
    ExtractionError,
    extract_primary_trial,
    extract_primary_trial_from_pdf,
)
from dossiergap.parse.ema_sections import find_efficacy_section

ENTRESTO_EPAR = (
    Path(__file__).resolve().parents[1] / "cache" / "ema" / "EMEA_H_C_004062" / "epar.pdf"
)

META = dict(
    source="EMA",
    dossier_id="EMEA/H/C/004062",
    drug_inn="sacubitril/valsartan",
    sponsor="Novartis",
)

# Simulated EPAR efficacy text capturing the table-format primary result.
CLEAN_EPAR_TEXT = (
    "2.4. Clinical efficacy\n"
    "The applicant conducted PARADIGM-HF, a Phase 3 pivotal study. "
    "A total of 8,442 patients were randomized. "
    "The primary endpoint was cardiovascular death or first heart failure "
    "hospitalization. "
    "Effect estimate per comparison group LCZ696 vs. enalapril: "
    "CV death or 1st HF Hazard ratio 0.80\nhospitalization\n95%-CI 0.73, 0.87\n"
    "P-value 0.00000021 (one-sided)."
)


# -- happy path ---------------------------------------------------------------

def test_extracts_valid_record_from_clean_table_text():
    r = extract_primary_trial({59: CLEAN_EPAR_TEXT}, **META)
    assert r.source == "EMA"
    assert r.effect_metric == "HR"
    assert r.effect_estimate == pytest.approx(0.80)
    assert r.effect_ci_low == pytest.approx(0.73)
    assert r.effect_ci_high == pytest.approx(0.87)
    assert r.n_randomized == 8442
    assert r.pivotal_strict is True
    assert r.pivotal_inclusive is True


def test_table_format_wins_over_narrative():
    """When both table and narrative HRs appear, the table (primary) wins."""
    text = (
        "2.4. Clinical efficacy\n"
        "PARADIGM-HF Phase 3 pivotal study randomized 8,442 patients. "
        "The primary endpoint was CV death or HF hospitalization. "
        "A subgroup HR 0.84; 95% CI 0.76 to 0.93 was observed for all-cause mortality.\n"
        "CV death or 1st HF Hazard ratio 0.80\n95%-CI 0.73, 0.87\nP-value 0.0001."
    )
    r = extract_primary_trial({59: text}, **META)
    # Primary (table) value is 0.80, not the subgroup 0.84
    assert r.effect_estimate == pytest.approx(0.80)
    assert r.effect_ci_low == pytest.approx(0.73)


def test_narrative_fallback_when_no_table():
    """If no table format found, fall back to first narrative HR (Task 7 behaviour)."""
    text = (
        "2.4. Clinical efficacy\n"
        "TRIAL-X Phase 3 pivotal study randomized 2,000 patients. "
        "The primary endpoint was MACE composite. "
        "HR 0.82; 95% CI 0.70, 0.95."
    )
    r = extract_primary_trial({59: text}, **META)
    assert r.effect_estimate == pytest.approx(0.82)


# -- EPAR-specific format variants -------------------------------------------

def test_table_with_percentage_hyphen_ci():
    """EMA often writes '95%-CI' (with hyphen) instead of '95% CI'."""
    text = (
        "2.4. Clinical efficacy\n"
        "TRIAL-Y Phase 3 pivotal study randomized 1,500 patients. "
        "The primary endpoint was all-cause mortality. "
        "Hazard ratio 0.75\n95%-CI 0.60, 0.90."
    )
    r = extract_primary_trial({59: text}, **META)
    assert r.effect_estimate == pytest.approx(0.75)
    assert r.effect_ci_low == pytest.approx(0.60)
    assert r.effect_ci_high == pytest.approx(0.90)


# -- fail-closed contracts ---------------------------------------------------

def test_raises_when_no_hr_found():
    text = (
        "2.4. Clinical efficacy\nTRIAL-X Phase 3 pivotal study randomized "
        "1,000 patients. The primary endpoint was MACE."
    )
    with pytest.raises(ExtractionError, match="effect estimate|HR"):
        extract_primary_trial({59: text}, **META)


def test_raises_when_no_n_found():
    text = (
        "2.4. Clinical efficacy\nTRIAL-X Phase 3 pivotal study. "
        "The primary endpoint was MACE. "
        "Hazard ratio 0.80\n95%-CI 0.73, 0.87."
    )
    with pytest.raises(ExtractionError, match="N randomi"):
        extract_primary_trial({59: text}, **META)


# -- integration against real Entresto EPAR --------------------------------

@pytest.mark.skipif(
    not ENTRESTO_EPAR.is_file(),
    reason="cached Entresto EPAR not present",
)
def test_real_entresto_epar_extraction():
    eff_range = find_efficacy_section(ENTRESTO_EPAR)
    r = extract_primary_trial_from_pdf(ENTRESTO_EPAR, eff_range, **META)

    # Hand-audited PARADIGM-HF values from Entresto EPAR (primary table on p.72):
    assert r.source == "EMA"
    assert r.effect_metric == "HR"
    assert r.effect_estimate == pytest.approx(0.80, abs=0.01)
    assert r.effect_ci_low == pytest.approx(0.73, abs=0.01)
    assert r.effect_ci_high == pytest.approx(0.87, abs=0.01)
    assert r.n_randomized == 8442
    assert r.pivotal_inclusive is True
