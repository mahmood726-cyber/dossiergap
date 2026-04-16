"""Task 15 — FDA OtherR structural section detector via trial-name clustering.

OtherR integrated reviews (2020+) concatenate multiple reviewer memos
without a single 'Review of Efficacy' section. Regex-only fallbacks
miss them. The clustering detector finds the contiguous page range
where the pivotal trial name (e.g., VICTORIA, EXPLORER-HCM) is
mentioned densely.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dossiergap.parse.fda_sections import (
    SectionNotFoundError,
    _find_trial_name_cluster,
    find_efficacy_section,
    find_efficacy_section_in_pages,
)

VERQUVO_PDF = (
    Path(__file__).resolve().parents[1] / "cache" / "fda" / "214377" / "medical_review.pdf"
)
CAMZYOS_PDF = (
    Path(__file__).resolve().parents[1] / "cache" / "fda" / "214998" / "medical_review.pdf"
)


# -- pure-function cluster detector ------------------------------------------

def test_cluster_returns_dense_range():
    pages = [
        "Regulatory memo",
        "Purpose of memorandum",
        "The VICTORIA trial was a Phase 3 pivotal study.",  # p3
        "VICTORIA enrolled patients with worsening HF.",    # p4
        "Results of VICTORIA primary endpoint.",             # p5
        "VICTORIA secondary endpoints.",                     # p6
        "VICTORIA long-term follow-up data.",                # p7
        "Safety review.",
    ]
    r = _find_trial_name_cluster(pages)
    assert r is not None
    start, end = r
    assert start == 3
    assert end == 7


def test_cluster_rejects_scale_or_questionnaire_names():
    """Acronyms that are questionnaires/scales lack trial-context adjacency
    and must not be picked over the real trial name."""
    pages = [
        "This review discusses the HCMSQ-SB score repeatedly.",
        "HCMSQ-SB was administered at baseline and week 30.",
        "HCMSQ-SB results showed improvement.",
        "HCMSQ-SB analysis continued.",
        "HCMSQ-SB subscale details.",
        "HCMSQ-SB validation data.",
        "The EXPLORER-HCM trial was a Phase 3 pivotal study.",  # trial-context
        "EXPLORER-HCM enrolled 251 patients.",
        "EXPLORER-HCM met its primary endpoint.",
        "EXPLORER-HCM secondary endpoints.",
        "EXPLORER-HCM extension data.",
    ]
    r = _find_trial_name_cluster(pages)
    assert r is not None
    start, end = r
    # Should pick the EXPLORER-HCM range (7-11), not HCMSQ-SB (1-6)
    assert start == 7
    assert end == 11


def test_cluster_returns_none_when_signal_too_weak():
    """If the top acronym has < 5 total mentions, give up."""
    pages = [
        "TRIAL-X was mentioned once.",
        "No other trial names here.",
        "Random content.",
    ]
    r = _find_trial_name_cluster(pages)
    assert r is None


def test_cluster_returns_none_on_empty_pages():
    assert _find_trial_name_cluster([]) is None


def test_cluster_picks_largest_contiguous_range():
    """Two clusters of the same trial name — pick the larger one."""
    pages = [
        "VICTORIA mentioned once.",            # p1
        "No mention",                           # p2
        "No mention",                           # p3
        "VICTORIA trial details.",              # p4
        "VICTORIA efficacy results.",           # p5
        "VICTORIA safety.",                     # p6
        "VICTORIA long-term follow-up.",        # p7
        "Unrelated.",                           # p8
    ]
    r = _find_trial_name_cluster(pages)
    assert r is not None
    start, end = r
    # Larger cluster is pp.4-7; isolated p.1 mention is ignored
    assert start == 4
    assert end == 7


# -- integration into find_efficacy_section_in_pages -------------------------

def test_find_efficacy_falls_through_to_cluster_when_no_anchors():
    pages = [
        "Regulatory memo 1 Introduction",
        "Regulatory memo 2 Study Report",
        "Purpose of memorandum",
        "The VICTORIA trial was a Phase 3 pivotal study of vericiguat.",
        "VICTORIA enrolled 5050 patients.",
        "VICTORIA primary endpoint CV death or HF hospitalization.",
        "VICTORIA HR 0.90.",
        "VICTORIA additional safety results.",
        "Further unrelated memo.",
    ]
    # No 'Review of Efficacy' anchor; no 'Clinical Efficacy' etc. fallback.
    # Must fall through to cluster-based detection.
    start, end = find_efficacy_section_in_pages(pages)
    assert start == 4
    assert end == 8


def test_primary_anchor_still_wins_over_cluster():
    """Regression guard: if the primary 'Review of Efficacy' anchor exists,
    it must win even when a trial-name cluster also exists."""
    pages = [
        "6 Review of Efficacy",
        "Efficacy content",
        "TRIAL-X Phase 3 pivotal",
        "TRIAL-X results",
        "TRIAL-X more",
        "TRIAL-X data",
        "TRIAL-X analysis",
        "7 Review of Safety",
    ]
    start, end = find_efficacy_section_in_pages(pages)
    assert start == 1  # primary anchor, not the trial cluster


# -- integration against real OtherR PDFs -----------------------------------

@pytest.mark.skipif(
    not VERQUVO_PDF.is_file(),
    reason="cached Verquvo MedR not present; run smoke fetch",
)
def test_verquvo_otherr_finds_victoria_cluster():
    start, end = find_efficacy_section(VERQUVO_PDF)
    # VICTORIA mentions observed on p.47, 60-64, 88-101 in the real PDF.
    # The clustering detector should pick the densest contiguous range —
    # either p.60-64 or p.88-101 is acceptable.
    assert start >= 40 and end <= 110, (
        f"VICTORIA cluster span {start}-{end} outside expected 40-110 window"
    )
    assert end - start >= 2, "cluster range too narrow"


@pytest.mark.skipif(
    not CAMZYOS_PDF.is_file(),
    reason="cached Camzyos MedR not present; run smoke fetch",
)
def test_camzyos_otherr_finds_explorer_hcm_cluster():
    start, end = find_efficacy_section(CAMZYOS_PDF)
    # EXPLORER-HCM is the pivotal trial for Camzyos (approved 2022).
    # The cluster should land somewhere in the 30-90 page range.
    assert start >= 20 and end <= 130, (
        f"EXPLORER-HCM cluster span {start}-{end} outside expected 20-130 window"
    )
    assert end - start >= 2
