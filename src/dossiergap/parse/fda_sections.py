"""Locate the Clinical Efficacy section inside an FDA Medical Review PDF.

FDA Medical Reviews follow a standard template with numbered top-level
sections. For cardiology NMEs 2015-2025 the typical layout is:

    1  Recommendations
    2  Introduction / Background
    3  Ethics & Good Clinical Practices
    4  Significant Efficacy/Safety Issues Related to Other Review Disciplines
    5  Sources of Clinical Data
    6  Review of Efficacy     <-- target section
    7  Review of Safety
    8  Postmarket Experience
    9  Appendices

The detector returns the 1-indexed page range ``(start, end)`` covering
Section 6 (or its nearest equivalent). The end page is one before the
next top-level section (Safety), or the last page of the PDF if no
Safety section is found.

Table-of-contents lines like
    ``6 REVIEW OF EFFICACY ....................................... 55``
are deliberately not matched: the trailing dot-leaders and page number
fail the ``\\s*$`` anchor. Only a clean section-head line (the header
alone on its line) matches.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber


class SectionNotFoundError(RuntimeError):
    pass


# Primary anchors: numbered top-level section heads in the legacy
# "Medical Review" template (2015-era Entresto, Uptravi, etc.).
_EFFICACY_HEAD_RE = re.compile(
    r"^\s*\d{1,2}\s+Review of Efficacy\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_SAFETY_HEAD_RE = re.compile(
    r"^\s*\d{1,2}\s+Review of Safety\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Fallback anchors for MedRs with a non-standard layout. Includes the
# 2020+ "OtherR" integrated-review template where efficacy lives under
# "Clinical Studies" / "Pivotal Study" / "Pivotal Phase III" / etc.
# The trailing `(?![.\s]*\d)` negative lookahead rejects TOC entries,
# which have dot-leaders and page numbers after the heading text.
_EFFICACY_FALLBACK_RE = re.compile(
    r"^\s*(?:Clinical Efficacy|Efficacy Review|Efficacy Summary"
    r"|Clinical Studies|Pivotal Study|Pivotal Phase|Primary Efficacy"
    r"|Efficacy Results|Efficacy Evaluation)"
    r"(?![.\s]*\d)"
    r"[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)

# Additional end-anchor candidates for the OtherR template — "Safety"
# isn't always the immediately-following top section.
_SAFETY_FALLBACK_RE = re.compile(
    r"^\s*(?:Clinical Safety|Safety Review|Safety Summary"
    r"|Benefit[\s-]Risk|Adverse Reactions|Postmarketing)"
    r"(?![.\s]*\d)"
    r"[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)


def _find_last_page(pages: list[str], pattern: re.Pattern[str]) -> int | None:
    """Return the 1-indexed page number of the last page whose text matches."""
    last: int | None = None
    for i, text in enumerate(pages, start=1):
        if pattern.search(text):
            last = i
    return last


def find_efficacy_section_in_pages(pages: list[str]) -> tuple[int, int]:
    """Pure-function core: given a list of page texts, return the efficacy page range.

    1-indexed inclusive range ``(start, end)``. Raises
    :class:`SectionNotFoundError` if no efficacy anchor can be found.
    """
    if not pages:
        raise SectionNotFoundError("cannot locate efficacy section: empty page list")

    start = _find_last_page(pages, _EFFICACY_HEAD_RE)
    if start is None:
        start = _find_last_page(pages, _EFFICACY_FALLBACK_RE)
    if start is None:
        raise SectionNotFoundError(
            "cannot locate efficacy section: no 'Review of Efficacy' or "
            "OtherR-template fallback anchor (Clinical Efficacy | Efficacy "
            "Review | Efficacy Summary | Clinical Studies | Pivotal Study "
            "| Pivotal Phase | Primary Efficacy | Efficacy Results | "
            "Efficacy Evaluation) matched"
        )

    # End boundary: prefer the numbered "Review of Safety" head, then
    # fall back to the OtherR-template safety / benefit-risk candidates.
    safety_start = _find_last_page(pages, _SAFETY_HEAD_RE)
    if safety_start is None or safety_start <= start:
        # Look for a fallback safety/benefit-risk head that appears
        # AFTER the efficacy start (earlier occurrences are unrelated).
        for pnum in range(start + 1, len(pages) + 1):
            text = pages[pnum - 1] if pnum - 1 < len(pages) else ""
            if _SAFETY_FALLBACK_RE.search(text):
                safety_start = pnum
                break
    if safety_start is None or safety_start <= start:
        end = len(pages)
    else:
        end = safety_start - 1

    return (start, end)


def find_efficacy_section(pdf_path: Path) -> tuple[int, int]:
    """Open ``pdf_path`` with pdfplumber, extract per-page text, locate the efficacy section."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    return find_efficacy_section_in_pages(pages)
