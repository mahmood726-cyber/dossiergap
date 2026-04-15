"""Locate the Clinical Efficacy section inside an EMA EPAR PDF.

EMA EPARs follow a standard Assessment Report template. The typical
top-level layout for cardiology products 2015-2025 is:

    1.   Background information on the procedure
    2.   Scientific discussion
    2.1  Introduction
    2.2  Non-clinical aspects
    2.3  Clinical aspects
    2.4  Clinical efficacy     <-- target section (sometimes 2.5)
    2.5  Clinical safety       (or 2.6 if efficacy is 2.5)
    2.6  Risk Management Plan
    3.   Benefit-risk balance

The detector returns the 1-indexed page range ``(start, end)`` covering
the Clinical efficacy section. End is one before the next top-level
section (Clinical safety), or the last page if no Safety head is found.

Mirror of ``fda_sections.py`` — see that module for the TOC-filter logic.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber


class SectionNotFoundError(RuntimeError):
    pass


# Section heads — numbered prefix is optional so we handle both the standard
# EMA template ("2.4. Clinical efficacy") and older or non-standard EPARs.
_EFFICACY_HEAD_RE = re.compile(
    r"^\s*(?:\d+\.\d+\.?\s+)?Clinical efficacy\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_SAFETY_HEAD_RE = re.compile(
    r"^\s*(?:\d+\.\d+\.?\s+)?Clinical safety\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Further fallbacks for efficacy when the section is labelled differently.
_EFFICACY_FALLBACK_RE = re.compile(
    r"^\s*(?:Discussion on clinical efficacy|Main studies)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _find_last_page(pages: list[str], pattern: re.Pattern[str]) -> int | None:
    last: int | None = None
    for i, text in enumerate(pages, start=1):
        if pattern.search(text):
            last = i
    return last


def find_efficacy_section_in_pages(pages: list[str]) -> tuple[int, int]:
    """Pure function: return 1-indexed inclusive ``(start, end)`` for clinical efficacy."""
    if not pages:
        raise SectionNotFoundError("cannot locate efficacy section: empty page list")

    start = _find_last_page(pages, _EFFICACY_HEAD_RE)
    if start is None:
        start = _find_last_page(pages, _EFFICACY_FALLBACK_RE)
    if start is None:
        raise SectionNotFoundError(
            "cannot locate efficacy section: no '2.X Clinical efficacy' or "
            "fallback anchor ('Clinical efficacy' / 'Discussion on clinical "
            "efficacy' / 'Main studies') matched"
        )

    safety_start = _find_last_page(pages, _SAFETY_HEAD_RE)
    if safety_start is None or safety_start <= start:
        end = len(pages)
    else:
        end = safety_start - 1

    return (start, end)


def find_efficacy_section(pdf_path: Path) -> tuple[int, int]:
    """Open ``pdf_path`` with pdfplumber and locate the efficacy section."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    return find_efficacy_section_in_pages(pages)
