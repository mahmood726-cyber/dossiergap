"""Task 6 — FDA Medical Review section-detector tests.

Pure-function tests exercise ``find_efficacy_section_in_pages`` with
synthetic page lists (no PDF needed). Integration test runs against the
real Entresto MedR if the cached file is present.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dossiergap.parse.fda_sections import (
    SectionNotFoundError,
    find_efficacy_section,
    find_efficacy_section_in_pages,
)

ENTRESTO_PDF = (
    Path(__file__).resolve().parents[1] / "cache" / "fda" / "207620" / "medical_review.pdf"
)

# Ground-truth hand-audited on the real Entresto MedR:
# Section 6 "Review of Efficacy" starts at page 55; Section 7 "Review of
# Safety" starts at page 88. Efficacy section is pages 55-87 inclusive.
ENTRESTO_EFFICACY = (55, 87)


# -- pure function happy path ------------------------------------------------

def test_numbered_section_6_efficacy_with_7_safety():
    pages = [
        "Cover page content",
        "Table of Contents\n6 REVIEW OF EFFICACY ...................... 3",  # TOC
        "",  # filler
        "6 Review of Efficacy\nEfficacy Summary\nDetails of pivotal trial",
        "More efficacy content",
        "Still efficacy",
        "7 Review of Safety\nSafety summary begins here",
        "Safety content",
    ]
    # 1-indexed: efficacy starts p4, safety starts p7, so efficacy = (4, 6)
    assert find_efficacy_section_in_pages(pages) == (4, 6)


def test_alternate_numbering_section_5_efficacy():
    pages = [
        "5 Review of Efficacy\nContent",
        "more",
        "6 Review of Safety\nStop",
    ]
    assert find_efficacy_section_in_pages(pages) == (1, 2)


# -- fallback heuristics -----------------------------------------------------

def test_fallback_clinical_efficacy_header():
    pages = [
        "Introduction",
        "Clinical Efficacy",
        "pivotal trial content",
        "Adverse events",
    ]
    # No "Review of Safety" anchor — runs to EOF (page 4)
    start, end = find_efficacy_section_in_pages(pages)
    assert start == 2
    assert end == 4


def test_fallback_efficacy_summary_header():
    pages = [
        "Cover",
        "Efficacy Summary",
        "content",
    ]
    start, end = find_efficacy_section_in_pages(pages)
    assert start == 2


# -- TOC-shaped lines are NOT matched (the critical regression guard) --------

def test_toc_line_does_not_match_section_head():
    """The TOC entry '6 REVIEW OF EFFICACY ................................ 55'
    must NOT be mistaken for a section header (would return the wrong page)."""
    pages = [
        "Cover",
        "6 REVIEW OF EFFICACY ............................... 55",  # TOC entry
        "7 REVIEW OF SAFETY ................................. 88",  # TOC entry
        "Intermediate content",
        "6 Review of Efficacy",  # real section head
        "efficacy body",
        "7 Review of Safety",  # real section head
    ]
    assert find_efficacy_section_in_pages(pages) == (5, 6)


def test_last_occurrence_wins_when_toc_matches_leniently():
    """Defense-in-depth: even if both TOC and body could match, the body
    comes later and wins because we pick the LAST match."""
    pages = [
        "6 Review of Efficacy (TOC reference, unlikely but possible)",
        "filler",
        "filler",
        "filler",
        "filler",
        "6 Review of Efficacy",  # real body header
        "body content",
        "7 Review of Safety",
    ]
    assert find_efficacy_section_in_pages(pages) == (6, 7)


# -- error paths -------------------------------------------------------------

def test_raises_on_empty_page_list():
    with pytest.raises(SectionNotFoundError, match="empty"):
        find_efficacy_section_in_pages([])


def test_raises_when_no_efficacy_anchor_found():
    pages = [
        "Cover page",
        "2 Introduction",
        "3 Ethics",
        "Random content without efficacy markers",
    ]
    with pytest.raises(SectionNotFoundError, match="efficacy"):
        find_efficacy_section_in_pages(pages)


# -- safety-section-missing fallback -----------------------------------------

def test_efficacy_runs_to_eof_when_no_safety_section():
    pages = [
        "Cover",
        "6 Review of Efficacy",
        "content1",
        "content2",
    ]
    start, end = find_efficacy_section_in_pages(pages)
    assert start == 2
    assert end == 4


def test_efficacy_end_is_one_before_safety_start():
    pages = ["a", "6 Review of Efficacy", "b", "c", "d", "7 Review of Safety", "e"]
    start, end = find_efficacy_section_in_pages(pages)
    assert start == 2
    assert end == 5
    # invariant: end + 1 is the safety page
    assert end + 1 == 6


# -- output-contract invariants ----------------------------------------------

def test_returned_pages_are_1_indexed():
    pages = ["6 Review of Efficacy", "7 Review of Safety"]
    start, end = find_efficacy_section_in_pages(pages)
    assert start >= 1
    assert end >= 1


def test_start_is_not_greater_than_end():
    pages = ["6 Review of Efficacy", "body", "7 Review of Safety"]
    start, end = find_efficacy_section_in_pages(pages)
    assert start <= end


# -- integration against real Entresto MedR ---------------------------------

@pytest.mark.skipif(
    not ENTRESTO_PDF.is_file(),
    reason="cached Entresto MedR not present; run smoke fetch to populate",
)
def test_real_entresto_medr_efficacy_boundaries():
    start, end = find_efficacy_section(ENTRESTO_PDF)
    expected_start, expected_end = ENTRESTO_EFFICACY
    # Plan spec allows +/-1 page tolerance for ground-truth comparison
    assert abs(start - expected_start) <= 1, (
        f"efficacy start page {start} differs from hand-audit {expected_start} by > 1"
    )
    assert abs(end - expected_end) <= 1, (
        f"efficacy end page {end} differs from hand-audit {expected_end} by > 1"
    )
