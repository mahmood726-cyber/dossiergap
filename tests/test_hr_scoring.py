"""Methods-paper §4.3 semantic-content scoring of HR candidates.

Unit tests of the pure scoring function, plus integration tests
asserting that scoring preserves Entresto and Verquvo clean
extractions (regression guard) and picks primary over subgroup in
synthetic scenarios (new capability).
"""
from __future__ import annotations

import re

import pytest

from dossiergap.parse._common_extract import (
    rank_hr_candidates,
    score_hr_candidate,
)
from dossiergap.parse.fda_trials import _HR_CI_RE as FDA_HR_CI_RE


# -- pure-function tests ----------------------------------------------------

def test_scoring_rewards_primary_keyword_proximity():
    text = "The primary composite endpoint was CV death. HR 0.80; 95% CI 0.73, 0.87."
    # Position of HR match
    m = FDA_HR_CI_RE.search(text)
    assert m is not None
    score = score_hr_candidate(text, m.start(), m.end())
    # Primary keyword very close, composite/death adjacent → high score
    assert score > 500


def test_scoring_penalises_subgroup_adjacency():
    text = "Subgroup analysis: HR 0.75; 95% CI 0.60, 0.94 (sensitivity, per-protocol)."
    m = FDA_HR_CI_RE.search(text)
    assert m is not None
    score = score_hr_candidate(text, m.start(), m.end())
    # No "primary" nearby, plus 3 negative-word hits → low score
    assert score < 100


def test_scoring_ranks_primary_over_subgroup_in_same_page():
    text = (
        "Subgroup analysis by sex: HR 0.75; 95% CI 0.60, 0.94 (exploratory). "
        "The primary composite endpoint was CV death or HF hospitalisation. "
        "HR 0.80; 95% CI 0.73, 0.87."
    )
    hits = [(1, m) for m in FDA_HR_CI_RE.finditer(text)]
    assert len(hits) == 2
    ranked = rank_hr_candidates(hits, {1: text})
    top = ranked[0]
    # Top candidate should be the primary HR (0.80), not subgroup (0.75).
    assert top[1].group(1) == "0.80"


def test_scoring_ties_resolved_by_first_in_text():
    """When two candidates score identically, stable sort preserves input order."""
    text = (
        "Trial result: HR 0.80; 95% CI 0.73, 0.87. "
        "Identical restatement: HR 0.90; 95% CI 0.82, 0.98."
    )
    hits = [(1, m) for m in FDA_HR_CI_RE.finditer(text)]
    ranked = rank_hr_candidates(hits, {1: text})
    # Neither has primary/outcome context; scores equal; first-in-text wins
    assert ranked[0][1].group(1) == "0.80"


def test_scoring_works_across_pages():
    """Primary keyword on page A, HR candidate on page B — still works."""
    pages = {
        1: "The primary composite endpoint was CV death.",
        2: "Results: HR 0.80; 95% CI 0.73, 0.87.",
        3: "Subgroup analysis: HR 0.75; 95% CI 0.60, 0.94 (exploratory).",
    }
    hits = []
    for pnum, text in pages.items():
        for m in FDA_HR_CI_RE.finditer(text):
            hits.append((pnum, m))
    ranked = rank_hr_candidates(hits, pages)
    # Primary keyword is on page 1; p.2 HR 0.80 is on a different page so
    # its proximity signal is 0. But its adjacency signal (no negative
    # words; has 'composite'/'death' via page 1? No — only same-page
    # window is checked). So scoring only sees within-page context.
    # p.3 subgroup gets penalised for 'subgroup'/'exploratory' → score < 0.
    # p.2 no penalty, no bonus → 0 score.
    # Top should be p.2 HR 0.80 (higher score than p.3 negative).
    assert ranked[0][0] == 2
    assert ranked[0][1].group(1) == "0.80"


# -- integration regression guards -----------------------------------------

from pathlib import Path

ENTRESTO_MEDR = (
    Path(__file__).resolve().parents[1] / "cache" / "fda" / "207620" / "medical_review.pdf"
)
ENTRESTO_EPAR = (
    Path(__file__).resolve().parents[1] / "cache" / "ema" / "EMEA_H_C_004062" / "epar.pdf"
)
VERQUVO_EPAR = (
    Path(__file__).resolve().parents[1] / "cache" / "ema" / "EMEA_H_C_005325" / "epar.pdf"
)


@pytest.mark.skipif(
    not ENTRESTO_MEDR.is_file(),
    reason="cached Entresto MedR not present",
)
def test_regression_entresto_fda_still_extracts_primary():
    from dossiergap.parse.fda_sections import find_efficacy_section
    from dossiergap.parse.fda_trials import extract_primary_trial_from_pdf

    eff_range = find_efficacy_section(ENTRESTO_MEDR)
    r = extract_primary_trial_from_pdf(
        ENTRESTO_MEDR, eff_range,
        source="FDA", dossier_id="207620",
        drug_inn="sacubitril/valsartan", sponsor="Entresto",
    )
    assert r.effect_estimate == pytest.approx(0.80, abs=0.01)
    assert r.effect_ci_low == pytest.approx(0.73, abs=0.01)
    assert r.effect_ci_high == pytest.approx(0.87, abs=0.01)


@pytest.mark.skipif(
    not ENTRESTO_EPAR.is_file(),
    reason="cached Entresto EPAR not present",
)
def test_regression_entresto_ema_still_extracts_primary():
    from dossiergap.parse.ema_sections import find_efficacy_section
    from dossiergap.parse.ema_trials import extract_primary_trial_from_pdf

    eff_range = find_efficacy_section(ENTRESTO_EPAR)
    r = extract_primary_trial_from_pdf(
        ENTRESTO_EPAR, eff_range,
        source="EMA", dossier_id="EMEA/H/C/004062",
        drug_inn="sacubitril/valsartan", sponsor="Entresto",
    )
    assert r.effect_estimate == pytest.approx(0.80, abs=0.01)
    assert r.effect_ci_low == pytest.approx(0.73, abs=0.01)
    assert r.effect_ci_high == pytest.approx(0.87, abs=0.01)


@pytest.mark.skipif(
    not VERQUVO_EPAR.is_file(),
    reason="cached Verquvo EPAR not present",
)
def test_regression_verquvo_ema_still_extracts_primary():
    from dossiergap.parse.ema_sections import find_efficacy_section
    from dossiergap.parse.ema_trials import extract_primary_trial_from_pdf

    eff_range = find_efficacy_section(VERQUVO_EPAR)
    r = extract_primary_trial_from_pdf(
        VERQUVO_EPAR, eff_range,
        source="EMA", dossier_id="EMEA/H/C/005325",
        drug_inn="vericiguat", sponsor="Verquvo",
    )
    assert r.effect_estimate == pytest.approx(0.90, abs=0.01)
    assert r.effect_ci_low == pytest.approx(0.82, abs=0.01)
    assert r.effect_ci_high == pytest.approx(0.98, abs=0.01)
