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
from collections import Counter
from pathlib import Path

import pdfplumber


class SectionNotFoundError(RuntimeError):
    pass


# Acronym-clustering constants for Task 15 OtherR support.
_ACRONYM_CLUSTER_RE = re.compile(r"\b([A-Z]{5,20}(?:-[A-Za-z0-9]{1,10})?)\b")
_CLUSTER_STOPWORDS = frozenset({
    "NCT", "FDA", "EMA", "MEDR", "NDA", "BLA", "EPAR", "CHMP", "NYHA",
    "LVEF", "KCCQ", "MACE", "PHASE", "HFREF", "HFPEF", "HFMREF", "CABG",
    "OTHERR", "MEDICAL", "REVIEW", "CLINICAL", "EFFICACY", "SAFETY",
    "SPONSOR", "SUMMARY", "ASSESSMENT", "INTRODUCTION", "CONCLUSIONS",
    "RECOMMENDATIONS", "STUDY", "STUDIES", "RESULTS", "METHODS",
    "ANALYSIS", "SUBJECTS", "PATIENTS", "SECTION", "TABLE", "FIGURE",
    "PROTOCOL", "MEMORANDUM", "REGULATORY", "MATERIALS", "REVIEWED",
    "FINDINGS", "REASON", "PURPOSE", "OVERALL", "BACKGROUND", "APPENDIX",
    "APPENDICES", "POSTMARKETING", "POSTMARKET", "EXPERIENCE",
    "INVESTIGATOR", "LABELING", "DMEPA", "DARRTS", "GCPAB",
    "WITH", "FROM", "WERE", "THIS", "THAT", "HAVE", "BEEN", "WHEN",
    "WHICH",
})
_TRIAL_CONTEXT_RE_TMPL = r"\b{name}\b.{{0,40}}\b(?:trial|study|Phase)\b|\b(?:trial|study|Phase)\b.{{0,40}}\b{name}\b"
_MIN_CLUSTER_MENTIONS = 5
_MIN_CLUSTER_PAGES = 3


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


def _find_trial_name_cluster(pages: list[str]) -> tuple[int, int] | None:
    """Locate the contiguous page range with densest trial-name mentions.

    Used for FDA OtherR (2020+) integrated reviews where efficacy content
    is scattered across concatenated reviewer memos without a single
    'Review of Efficacy' section heading.

    Algorithm:
      1. Find candidate acronym-shaped tokens, filter by length + stopwords.
      2. Among candidates, require at least one occurrence adjacent to
         'trial' / 'study' / 'Phase' — this rejects questionnaire/scale
         names (e.g., HCMSQ-SB in the Camzyos MedR) that share the shape
         of trial names but aren't trials.
      3. Pick the most-frequent qualifying candidate.
      4. Return the longest contiguous run of pages containing it (min
         3 pages), or None if the signal is too weak (< 5 total mentions).
    """
    if not pages:
        return None

    # Step 1: count acronym candidates and track their page sets.
    counts: Counter[str] = Counter()
    per_page: dict[str, dict[int, int]] = {}
    full_text_per_page = pages  # already list[str]
    for pnum, text in enumerate(full_text_per_page, start=1):
        for m in _ACRONYM_CLUSTER_RE.finditer(text):
            token = m.group(1)
            base = token.split("-")[0].upper()
            if base in _CLUSTER_STOPWORDS:
                continue
            counts[token] += 1
            per_page.setdefault(token, {}).setdefault(pnum, 0)
            per_page[token][pnum] += 1

    if not counts:
        return None

    # Step 2: filter to tokens with trial-context adjacency.
    joined = "\n".join(full_text_per_page)
    qualifying: list[tuple[str, int]] = []
    for token, n in counts.most_common(10):
        ctx_re = re.compile(
            _TRIAL_CONTEXT_RE_TMPL.format(name=re.escape(token)),
            re.IGNORECASE,
        )
        if ctx_re.search(joined):
            qualifying.append((token, n))

    if not qualifying:
        return None

    # Step 3: pick the most-frequent qualifying token.
    top_token, top_count = qualifying[0]
    if top_count < _MIN_CLUSTER_MENTIONS:
        return None

    # Step 4: find longest contiguous run of pages containing the token.
    mention_pages = sorted(per_page[top_token].keys())
    best: tuple[int, int] | None = None
    run_start = mention_pages[0]
    run_end = run_start
    for p in mention_pages[1:]:
        if p == run_end + 1:
            run_end = p
        else:
            length = run_end - run_start + 1
            if best is None or length > (best[1] - best[0] + 1):
                best = (run_start, run_end)
            run_start = p
            run_end = p
    # Close final run.
    length = run_end - run_start + 1
    if best is None or length > (best[1] - best[0] + 1):
        best = (run_start, run_end)

    if best is None or (best[1] - best[0] + 1) < _MIN_CLUSTER_PAGES:
        return None
    return best


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
        # Third fallback: trial-name cluster detection for OtherR templates
        # that concatenate reviewer memos without a single efficacy heading.
        cluster = _find_trial_name_cluster(pages)
        if cluster is not None:
            return cluster
        raise SectionNotFoundError(
            "cannot locate efficacy section: no 'Review of Efficacy' or "
            "OtherR-template fallback anchor (Clinical Efficacy | Efficacy "
            "Review | Efficacy Summary | Clinical Studies | Pivotal Study "
            "| Pivotal Phase | Primary Efficacy | Efficacy Results | "
            "Efficacy Evaluation) matched, and no trial-name cluster with "
            "adequate mention density was found"
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
