"""Task 8 — EMA EPAR section-detector tests. Mirror of test_parse_fda_sections.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from dossiergap.parse.ema_sections import (
    SectionNotFoundError,
    find_efficacy_section,
    find_efficacy_section_in_pages,
)

ENTRESTO_EPAR = (
    Path(__file__).resolve().parents[1] / "cache" / "ema" / "EMEA_H_C_004062" / "epar.pdf"
)

# Hand-audited ground truth for Entresto EPAR (EMEA/H/C/004062):
# Section 2.4 Clinical efficacy starts at page 59; Section 2.5 Clinical safety
# starts at page 84. Efficacy section is pages 59-83 inclusive.
ENTRESTO_EFFICACY = (59, 83)


# -- pure function happy path ------------------------------------------------

def test_numbered_section_2_4_efficacy_with_2_5_safety():
    pages = [
        "Cover page",
        "Table of Contents\n2.4. Clinical efficacy ................ 59\n"
        "2.5. Clinical safety .................. 84",
        "",
        "2.4. Clinical efficacy\nThe applicant presented data",
        "more efficacy",
        "still efficacy",
        "2.5. Clinical safety\nPatient exposure",
        "safety content",
    ]
    # 1-indexed: efficacy start p4, safety start p7, efficacy = (4, 6)
    assert find_efficacy_section_in_pages(pages) == (4, 6)


def test_alternate_numbering_2_5_efficacy():
    """Some EPARs number efficacy as 2.5 (not 2.4)."""
    pages = [
        "Intro",
        "2.5. Clinical efficacy\nBody",
        "content",
        "2.6. Clinical safety\nStop",
    ]
    assert find_efficacy_section_in_pages(pages) == (2, 3)


# -- fallback heuristics -----------------------------------------------------

def test_fallback_unnumbered_clinical_efficacy():
    pages = [
        "Intro",
        "Clinical efficacy",
        "body content",
        "Clinical safety",
        "safety content",
    ]
    assert find_efficacy_section_in_pages(pages) == (2, 3)


# -- TOC lines ignored (critical regression guard) ---------------------------

def test_toc_line_does_not_match_section_head():
    pages = [
        "Cover",
        "2.4. Clinical efficacy ..................................... 59",  # TOC
        "2.5. Clinical safety ....................................... 84",  # TOC
        "body intro",
        "2.4. Clinical efficacy",  # real section head
        "efficacy body",
        "2.5. Clinical safety",  # real section head
    ]
    assert find_efficacy_section_in_pages(pages) == (5, 6)


# -- error paths -------------------------------------------------------------

def test_raises_on_empty_page_list():
    with pytest.raises(SectionNotFoundError, match="empty"):
        find_efficacy_section_in_pages([])


def test_raises_when_no_efficacy_anchor_found():
    pages = [
        "Cover",
        "Background",
        "Quality aspects",
        "Non-clinical",
    ]
    with pytest.raises(SectionNotFoundError, match="efficacy"):
        find_efficacy_section_in_pages(pages)


# -- safety-missing fallback -------------------------------------------------

def test_efficacy_runs_to_eof_when_no_safety_section():
    pages = [
        "intro",
        "2.4. Clinical efficacy",
        "body1",
        "body2",
    ]
    start, end = find_efficacy_section_in_pages(pages)
    assert start == 2
    assert end == 4


# -- output invariants -------------------------------------------------------

def test_returned_pages_are_1_indexed():
    pages = ["2.4. Clinical efficacy", "2.5. Clinical safety"]
    start, end = find_efficacy_section_in_pages(pages)
    assert start >= 1 and end >= 1


def test_start_not_greater_than_end():
    pages = ["2.4. Clinical efficacy", "body", "2.5. Clinical safety"]
    start, end = find_efficacy_section_in_pages(pages)
    assert start <= end


# -- integration against real Entresto EPAR ---------------------------------

@pytest.mark.skipif(
    not ENTRESTO_EPAR.is_file(),
    reason="cached Entresto EPAR not present; run smoke fetch to populate",
)
def test_real_entresto_epar_efficacy_boundaries():
    start, end = find_efficacy_section(ENTRESTO_EPAR)
    expected_start, expected_end = ENTRESTO_EFFICACY
    assert abs(start - expected_start) <= 1, (
        f"EPAR efficacy start page {start} differs from hand-audit "
        f"{expected_start} by > 1"
    )
    assert abs(end - expected_end) <= 1, (
        f"EPAR efficacy end page {end} differs from hand-audit "
        f"{expected_end} by > 1"
    )
