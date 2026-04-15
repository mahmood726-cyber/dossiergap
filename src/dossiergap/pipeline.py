"""End-to-end extraction pipeline: corpus → downloads → extraction → dedup → CSV.

Chains the Task 3–11 components into a single function the CLI and Task 13
contract test can call. Per-NME failures are collected rather than raising
so ``--continue-on-error`` mode can emit a partial CSV and a failure log.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from dossiergap.corpus import CorpusEntry
from dossiergap.dedup import DedupGroup, dedup_trials
from dossiergap.download.ema import EMADownloadError, fetch_epar
from dossiergap.download.fda import FDADownloadError, fetch_medical_review
from dossiergap.io.csv_writer import write_csv
from dossiergap.parse._common_extract import NCT_RE, ExtractionError
from dossiergap.parse.ema_sections import (
    SectionNotFoundError as EMASectionError,
    find_efficacy_section as find_ema_efficacy,
)
from dossiergap.parse.ema_trials import (
    extract_primary_trial_from_pdf as extract_ema_trial,
)
from dossiergap.parse.fda_sections import (
    SectionNotFoundError as FDASectionError,
    find_efficacy_section as find_fda_efficacy,
)
from dossiergap.parse.fda_trials import (
    extract_primary_trial_from_pdf as extract_fda_trial,
)
from dossiergap.schema import TrialRecord


@dataclass
class ExtractionFailure:
    drug_inn: str
    source: str  # "FDA" or "EMA"
    dossier_id: str
    reason: str


def _scan_full_pdf_for_nct(pdf_path: Path) -> str | None:
    """Return the first ``NCT########`` id found anywhere in the PDF.

    NCTs are often listed in a study-registry appendix outside the
    efficacy section, so a successful primary-key dedup depends on this
    wider scan. Returns None if the PDF has no NCT at all.
    """
    with pdfplumber.open(pdf_path) as doc:
        for page in doc.pages:
            text = page.extract_text() or ""
            m = NCT_RE.search(text)
            if m:
                return m.group(0)
    return None


def _enrich_nct(record: TrialRecord, pdf_path: Path) -> TrialRecord:
    """If the extractor returned no NCT id, scan the full PDF as a fallback."""
    if record.nct_id is not None:
        return record
    nct = _scan_full_pdf_for_nct(pdf_path)
    if nct is None:
        return record
    return record.model_copy(update={"nct_id": nct})


def _fda_for(entry: CorpusEntry, cache_dir: Path) -> TrialRecord:
    if not entry.fda_application_number or not entry.fda_medical_review_url:
        raise ExtractionError(
            f"{entry.drug_inn}: missing FDA application number or MedR URL"
        )
    pdf = fetch_medical_review(
        entry.fda_medical_review_url,
        entry.fda_application_number,
        cache_dir=cache_dir,
    )
    eff_range = find_fda_efficacy(pdf)
    record = extract_fda_trial(
        pdf, eff_range,
        source="FDA",
        dossier_id=entry.fda_application_number,
        drug_inn=entry.drug_inn,
        sponsor=entry.brand_us or entry.drug_inn,
    )
    return _enrich_nct(record, pdf)


def _ema_for(entry: CorpusEntry, cache_dir: Path) -> TrialRecord:
    if not entry.ema_procedure_number or not entry.ema_epar_url:
        raise ExtractionError(
            f"{entry.drug_inn}: missing EMA procedure number or EPAR URL"
        )
    pdf = fetch_epar(
        entry.ema_epar_url,
        entry.ema_procedure_number,
        cache_dir=cache_dir,
    )
    eff_range = find_ema_efficacy(pdf)
    record = extract_ema_trial(
        pdf, eff_range,
        source="EMA",
        dossier_id=entry.ema_procedure_number,
        drug_inn=entry.drug_inn,
        sponsor=entry.brand_us or entry.drug_inn,
    )
    return _enrich_nct(record, pdf)


def run_pipeline(
    entries: list[CorpusEntry],
    cache_dir: Path,
    out_path: Path,
    *,
    limit: int | None = None,
    continue_on_error: bool = False,
    progress_stream=None,
) -> tuple[list[DedupGroup], list[ExtractionFailure]]:
    """Run the full pipeline. Returns (groups_written, failures).

    ``progress_stream`` defaults to ``sys.stderr``. Pass ``None`` explicitly
    to silence progress output (tests).
    """
    stream = progress_stream if progress_stream is not None else sys.stderr

    targets = entries[:limit] if limit is not None else entries
    records: list[TrialRecord] = []
    failures: list[ExtractionFailure] = []

    def log(msg: str) -> None:
        if stream is not None:
            print(msg, file=stream)

    def run_source(entry: CorpusEntry, source: str, fn) -> None:
        try:
            record = fn(entry, cache_dir)
            records.append(record)
            log(f"  [OK ] {source} {record.dossier_id}")
        except (
            FDADownloadError, EMADownloadError,
            FDASectionError, EMASectionError,
            ExtractionError,
        ) as e:
            dossier_id = (
                entry.fda_application_number if source == "FDA"
                else entry.ema_procedure_number
            ) or "?"
            failures.append(ExtractionFailure(
                drug_inn=entry.drug_inn,
                source=source,
                dossier_id=dossier_id,
                reason=f"{type(e).__name__}: {e}",
            ))
            log(f"  [FAIL] {source} {dossier_id}: {type(e).__name__}: {e}")
            if not continue_on_error:
                raise

    for i, entry in enumerate(targets, start=1):
        log(f"[{i}/{len(targets)}] {entry.drug_inn} ({entry.cv_indication})")
        if entry.fda_application_number and entry.fda_medical_review_url:
            run_source(entry, "FDA", _fda_for)
        if entry.ema_procedure_number and entry.ema_epar_url:
            run_source(entry, "EMA", _ema_for)

    groups = dedup_trials(records)
    write_csv(groups, out_path)
    log(f"Wrote {len(groups)} row(s) to {out_path}")
    if failures:
        log(f"Failures: {len(failures)}")

    return groups, failures
