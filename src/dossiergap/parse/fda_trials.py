"""Extract pivotal trial records from an FDA Medical Review efficacy section.

Scope (Phase 1):
- One ``TrialRecord`` per MedR (the primary pivotal trial).
- HR as the primary effect metric (cardiology-typical). Non-HR metrics
  for Phase 1 smoke subset (Entresto, Farxiga HF, Verquvo) are all HR.
- Fails closed on missing HR, N, trial name, or primary outcome rather
  than emitting silent-sentinel records (per 2026-04-14 lesson).

Known limitations (deferred):
- Multi-trial MedRs (rare in cardiology) yield only the first matched trial.
- ``reported_in_label`` is a Phase-1 placeholder set True for pivotal trials.
- Effect metric assumed HR; RR/OR/MD/SMD/RD extraction is Task 7.1.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pdfplumber

from dossiergap.schema import Source, TrialRecord


class ExtractionError(RuntimeError):
    pass


_NCT_RE = re.compile(r"NCT\d{8}")

# N randomized: accept both "N subjects randomized" and "randomized N subjects".
# Cap leading number to 3+ digits so "4 subjects" is skipped as noise.
_N_RANDOMIZED_RE = re.compile(
    r"(?:"
    r"(?P<n_before>\d{1,3}(?:,\d{3})+|\d{3,6})\s+(?:subjects|patients|participants)"
    r"\s+(?:were\s+)?(?:randomi[sz]ed|enrolled)"
    r"|"
    r"(?:randomi[sz]ed|enrolled)\s+"
    r"(?P<n_after>\d{1,3}(?:,\d{3})+|\d{3,6})\s+(?:subjects|patients|participants)"
    r")",
    re.IGNORECASE,
)

# HR with 95% CI; accepts comma or dash separator inside CI.
_HR_CI_RE = re.compile(
    r"\bHR\b[^\d]{0,10}(\d+\.\d+)"       # point estimate
    r"[^0-9.]{1,30}?"                     # gap (semicolon, parens, etc.)
    r"95\s*%?\s*CI[:\s]*"                # "95% CI"
    r"(\d+\.\d+)"                         # lower bound
    r"\s*[,\-–]\s*"                      # separator
    r"(\d+\.\d+)",                        # upper bound
    re.IGNORECASE,
)

# "The primary endpoint was ..." or "The primary composite endpoint was ...".
# Uses [^.] (not [^.\n]) so wrapped FDA narrative can span PDF line breaks;
# capture stops at a period or the ", an endpoint" continuation clause.
_PRIMARY_OUTCOME_RE = re.compile(
    r"(?:The\s+)?primary\s+(?:composite\s+)?endpoint\s+was\s+"
    r"(?:a\s+composite\s+of\s+)?"
    r"([^.]{10,200}?)\s*(?:\.|,\s+an\s+endpoint)",
    re.IGNORECASE,
)

# Trial-name acronyms: all-caps >=4 chars, optional -HF/-CM/-DKD suffix.
_ACRONYM_RE = re.compile(
    r"\b([A-Z]{4,20}(?:-[A-Za-z0-9]{1,10})?)\b"
)

# Words that look like acronyms but aren't trial names
_ACRONYM_STOPWORDS = {
    "NCT", "FDA", "EMA", "MEDR", "NDA", "BLA",
    "LCZ", "ACEI", "ARB", "ARNI", "SGLT", "GLP",
    "HFREF", "HFPEF", "HFMREF", "NYHA", "LVEF", "KCCQ",
    "ICD", "CRT", "MI", "MACE", "CV", "CABG", "PCI",
    "SOLVD", "CONSENSUS",  # historical comparator trials cited in PARADIGM
    "PHASE",
}

_PHASE_RE = re.compile(r"\bPhase\s+(2/3|3b|[234])\b", re.IGNORECASE)

# "pivotal" within 200 chars of the trial name → strict pivotal
_PIVOTAL_WINDOW = 200


def _find_all(pattern: re.Pattern[str], pages: dict[int, str]) -> list[tuple[int, re.Match[str]]]:
    hits: list[tuple[int, re.Match[str]]] = []
    for pnum in sorted(pages):
        for m in pattern.finditer(pages[pnum]):
            hits.append((pnum, m))
    return hits


def _extract_trial_name(pages: dict[int, str]) -> tuple[str, int]:
    """Pick the most frequent acronym-shaped token, excluding stopwords."""
    counts: Counter[str] = Counter()
    first_page: dict[str, int] = {}
    for pnum in sorted(pages):
        for m in _ACRONYM_RE.finditer(pages[pnum]):
            token = m.group(1)
            base = token.split("-")[0].upper()
            if base in _ACRONYM_STOPWORDS:
                continue
            if len(base) < 4:
                continue
            counts[token] += 1
            first_page.setdefault(token, pnum)
    if not counts:
        raise ExtractionError(
            "could not extract trial name: no acronym candidates found "
            "(try adding the trial's acronym to the stopword exemption list)"
        )
    name, _n = counts.most_common(1)[0]
    return name, first_page[name]


def _extract_n_randomized(pages: dict[int, str]) -> tuple[int, int]:
    hits = _find_all(_N_RANDOMIZED_RE, pages)
    for pnum, m in hits:
        n_str = m.group("n_before") or m.group("n_after")
        n = int(n_str.replace(",", ""))
        if n >= 100:
            return n, pnum
    raise ExtractionError(
        "could not extract N randomized: no match for pattern "
        "'(\\d+) (subjects|patients|participants) (were )?randomized' or "
        "'randomized (\\d+) (subjects|patients|participants)' with N >= 100"
    )


def _extract_hr_ci(pages: dict[int, str]) -> tuple[float, float, float, int]:
    hits = _find_all(_HR_CI_RE, pages)
    if not hits:
        raise ExtractionError(
            "could not extract effect estimate: no match for "
            "'HR <point>; 95% CI <low>, <high>' pattern in efficacy section"
        )
    pnum, m = hits[0]  # first HR in efficacy section = primary result
    return float(m.group(1)), float(m.group(2)), float(m.group(3)), pnum


def _extract_primary_outcome(pages: dict[int, str]) -> tuple[str, int]:
    hits = _find_all(_PRIMARY_OUTCOME_RE, pages)
    if not hits:
        raise ExtractionError(
            "could not extract primary outcome/endpoint: no match for "
            "'(The )?primary (composite )?endpoint was <text>' pattern"
        )
    # Prefer the cleanest occurrence — the shortest match tends to be the
    # canonical statement rather than a narrative mention.
    pnum, m = min(hits, key=lambda h: len(h[1].group(1)))
    text = " ".join(m.group(1).split())
    return text, pnum


def _extract_phase(pages: dict[int, str]) -> str:
    for pnum in sorted(pages):
        m = _PHASE_RE.search(pages[pnum])
        if m:
            phase = m.group(1)
            if phase in ("2", "2/3", "3", "3b", "4"):
                return phase
    return "3"  # cardiology-default for pivotal trials


def _extract_nct(pages: dict[int, str]) -> str | None:
    hits = _find_all(_NCT_RE, pages)
    return hits[0][1].group(0) if hits else None


def _is_strict_pivotal(pages: dict[int, str], trial_name: str) -> bool:
    """True if 'pivotal' appears within _PIVOTAL_WINDOW chars of the trial name."""
    for pnum in sorted(pages):
        text = pages[pnum]
        for m in re.finditer(re.escape(trial_name), text):
            start = max(0, m.start() - _PIVOTAL_WINDOW)
            end = min(len(text), m.end() + _PIVOTAL_WINDOW)
            if re.search(r"\bpivotal\b", text[start:end], re.IGNORECASE):
                return True
    return False


def extract_primary_trial(
    efficacy_pages: dict[int, str],
    *,
    source: Source,
    dossier_id: str,
    drug_inn: str,
    sponsor: str,
) -> TrialRecord:
    """Extract the primary pivotal trial from a dict of efficacy-section pages."""
    if not efficacy_pages:
        raise ExtractionError("efficacy_pages is empty")

    trial_name, name_pg = _extract_trial_name(efficacy_pages)
    n_random, n_pg = _extract_n_randomized(efficacy_pages)
    est, lo, hi, hr_pg = _extract_hr_ci(efficacy_pages)
    outcome, outcome_pg = _extract_primary_outcome(efficacy_pages)
    phase = _extract_phase(efficacy_pages)
    nct = _extract_nct(efficacy_pages)
    strict = _is_strict_pivotal(efficacy_pages, trial_name)

    page_refs = sorted({name_pg, n_pg, hr_pg, outcome_pg})

    return TrialRecord(
        source=source,
        dossier_id=dossier_id,
        drug_inn=drug_inn,
        sponsor=sponsor,
        trial_phase=phase,
        nct_id=nct,
        n_randomized=n_random,
        primary_outcome=outcome,
        effect_metric="HR",
        effect_estimate=est,
        effect_ci_low=lo,
        effect_ci_high=hi,
        reported_in_label=True,  # Phase-1 placeholder; see module docstring
        pivotal_strict=strict,
        pivotal_inclusive=True,
        source_page_refs=page_refs,
    )


def extract_primary_trial_from_pdf(
    pdf_path: Path,
    efficacy_range: tuple[int, int],
    *,
    source: Source,
    dossier_id: str,
    drug_inn: str,
    sponsor: str,
) -> TrialRecord:
    start, end = efficacy_range
    with pdfplumber.open(pdf_path) as doc:
        pages = {
            i: doc.pages[i - 1].extract_text() or ""
            for i in range(start, end + 1)
        }
    return extract_primary_trial(
        pages,
        source=source,
        dossier_id=dossier_id,
        drug_inn=drug_inn,
        sponsor=sponsor,
    )
