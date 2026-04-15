"""Extract pivotal trial records from an FDA Medical Review efficacy section.

Scope (Phase 1):
- One ``TrialRecord`` per MedR (the primary pivotal trial).
- HR as the primary effect metric (cardiology-typical). Non-HR metrics
  for Phase 1 smoke subset (Entresto, Farxiga HF, Verquvo) are all HR.
- Fails closed on missing HR, N, trial name, or primary outcome rather
  than emitting silent-sentinel records (per 2026-04-14 lesson).

Source-agnostic extractors (trial name, N, NCT, outcome, phase, strict
pivotal) live in ``_common_extract``. Only the HR regex is FDA-specific.

Known limitations (deferred):
- Multi-trial MedRs (rare in cardiology) yield only the first matched trial.
- ``reported_in_label`` is a Phase-1 placeholder set True for pivotal trials.
- Effect metric assumed HR; RR/OR/MD/SMD/RD extraction is Task 7.1.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from dossiergap.schema import Source, TrialRecord

from ._common_extract import (
    ExtractionError,
    extract_n_randomized,
    extract_nct,
    extract_phase,
    extract_primary_outcome,
    extract_trial_name,
    find_all,
    is_strict_pivotal,
)

# FDA narrative format. Accepts 90/95/97.5/99 % CI — some FDA reviews
# quote 97.5% (two-sided from one-sided alpha = 0.025) or 99% (GRIPHON-
# style alpha-spending designs). 95% is overwhelmingly the default.
_HR_CI_RE = re.compile(
    r"\bHR\b[^\d]{0,10}(\d+\.\d+)"
    r"[^0-9.]{1,30}?"
    r"(?:90|95|97\.?5|99)\s*%?\s*CI[:\s]*"
    r"(\d+\.\d+)"
    r"\s*[,\-–]\s*"
    r"(\d+\.\d+)",
    re.IGNORECASE,
)


def _extract_hr_ci(pages: dict[int, str]) -> tuple[float, float, float, int]:
    hits = find_all(_HR_CI_RE, pages)
    if not hits:
        raise ExtractionError(
            "could not extract effect estimate: no match for "
            "'HR <point>; 95% CI <low>, <high>' pattern in efficacy section"
        )
    pnum, m = hits[0]  # first HR in FDA narrative = primary result
    return float(m.group(1)), float(m.group(2)), float(m.group(3)), pnum


def extract_primary_trial(
    efficacy_pages: dict[int, str],
    *,
    source: Source,
    dossier_id: str,
    drug_inn: str,
    sponsor: str,
) -> TrialRecord:
    if not efficacy_pages:
        raise ExtractionError("efficacy_pages is empty")

    trial_name, name_pg = extract_trial_name(efficacy_pages)
    n_random, n_pg = extract_n_randomized(efficacy_pages)
    est, lo, hi, hr_pg = _extract_hr_ci(efficacy_pages)
    outcome, outcome_pg = extract_primary_outcome(efficacy_pages)
    phase = extract_phase(efficacy_pages)
    nct = extract_nct(efficacy_pages)
    strict = is_strict_pivotal(efficacy_pages, trial_name)

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
        reported_in_label=True,
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
