"""Extract pivotal trial records from an EMA EPAR efficacy section.

EMA EPARs present primary results in a distinctive table layout that
pdfplumber linearises as, for example:

    CV death or 1st HF Hazard ratio 0.80
    hospitalization
    95%-CI 0.73, 0.87
    P-value 0.00000021 (one-sided)

Narrative 'HR X, 95% CI Y to Z' sentences also appear but typically for
subgroup or post-hoc analyses. The extractor therefore prefers the
table format and only falls back to narrative if no table match is
found.
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

# Table format: "Hazard ratio <est>" followed (possibly across line
# breaks and neighbouring table cells) by "<ci-level>%-CI <low>, <high>".
# CI level parameterised so alpha-adjusted trials (e.g. GRIPHON's 99%) match.
_HR_CI_TABLE_RE = re.compile(
    r"Hazard\s+ratio\s+(\d+\.\d+)"
    r"[^\d]{0,200}?"
    r"(?:90|95|97\.?5|99)\s*%\s*-?\s*CI[:,\s]*"
    r"(\d+\.\d+)"
    r"\s*(?:,\s*|\s+to\s+|\s*[-–]\s*)"
    r"(\d+\.\d+)",
    re.IGNORECASE | re.DOTALL,
)

# Narrative format — either "HR 0.80; 95% CI 0.73, 0.87" or the full
# "Hazard ratio 0.80 (95% CI 0.73, 0.87)" phrasing EMA often uses in
# prose (not just in tables). Accepts 90/95/97.5/99 % CI.
_HR_CI_NARRATIVE_RE = re.compile(
    r"(?:\bHR\b|Hazard\s+ratio)[^\d]{0,10}(\d+\.\d+)"
    r"[^0-9.]{1,30}?"
    r"(?:90|95|97\.?5|99)\s*%?\s*CI[:\s]*"
    r"(\d+\.\d+)"
    r"\s*[,\-–]\s*"
    r"(\d+\.\d+)",
    re.IGNORECASE,
)


def _extract_hr_ci(pages: dict[int, str]) -> tuple[float, float, float, int]:
    """Phase-2 behaviour preserved on EMA: table-tier first-match, narrative
    fallback first-match. Semantic scoring (§4.3) is NOT applied here
    because EMA EPARs have a failure mode the scoring cannot distinguish:
    later discussion pages often cite historical comparator trials using
    'primary endpoint' language, and the preceding context for a compact
    primary-result narrative sentence does not. In Verquvo specifically,
    p.97 cites PARADIGM-HF's HR=0.80 as a comparator and scores higher
    than Verquvo's own VICTORIA primary HR=0.90 at p.78. Scoring is
    deferred to FDA narrative extraction (``fda_trials._extract_hr_ci``)
    where the subject of the HR is reliably established in the preceding
    200 chars.
    """
    table_hits = find_all(_HR_CI_TABLE_RE, pages)
    if table_hits:
        pnum, m = table_hits[0]
        return float(m.group(1)), float(m.group(2)), float(m.group(3)), pnum

    narrative_hits = find_all(_HR_CI_NARRATIVE_RE, pages)
    if narrative_hits:
        pnum, m = narrative_hits[0]
        return float(m.group(1)), float(m.group(2)), float(m.group(3)), pnum

    raise ExtractionError(
        "could not extract effect estimate: no match for table "
        "'Hazard ratio <p> ... 95%-CI <lo>, <hi>' or narrative "
        "'HR <p>; 95% CI <lo>, <hi>' pattern in efficacy section"
    )


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
