"""Task 12 — end-to-end pipeline tests.

The integration path (fetch → detect section → extract → dedup → CSV)
is expensive (pdfplumber over 299-page PDF). Pure-pipeline tests use
mocked per-source helpers; one real smoke test runs the full pipeline
against the cached Entresto PDFs.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest import mock

import pytest

from dossiergap.corpus import CorpusEntry, load_corpus
from dossiergap.io.csv_writer import read_csv, row_to_trial_record
from dossiergap.pipeline import ExtractionFailure, run_pipeline
from dossiergap.schema import TrialRecord

ENTRESTO_MEDR = (
    Path(__file__).resolve().parents[1]
    / "cache" / "fda" / "207620" / "medical_review.pdf"
)
ENTRESTO_EPAR = (
    Path(__file__).resolve().parents[1]
    / "cache" / "ema" / "EMEA_H_C_004062" / "epar.pdf"
)
SEED_CORPUS = Path(__file__).resolve().parents[1] / "data" / "cardiology-nme-corpus.json"


def _corpus_entry(**overrides) -> CorpusEntry:
    base = dict(
        drug_inn="sacubitril/valsartan",
        brand_us="Entresto",
        fda_application_number="207620",
        fda_approval_type="NDA",
        cv_indication="HFrEF",
        fda_medical_review_url="https://example.invalid/medr.pdf",
        ema_procedure_number="EMEA/H/C/004062",
        ema_epar_url="https://example.invalid/epar.pdf",
    )
    base.update(overrides)
    return CorpusEntry.model_validate(base)


def _record(**overrides) -> TrialRecord:
    base = dict(
        source="FDA",
        dossier_id="207620",
        drug_inn="sacubitril/valsartan",
        sponsor="Entresto",
        trial_phase="3",
        nct_id="NCT01035255",
        n_randomized=8442,
        primary_outcome="CV death or first HF hospitalization",
        effect_metric="HR",
        effect_estimate=0.80,
        effect_ci_low=0.73,
        effect_ci_high=0.87,
        reported_in_label=True,
        pivotal_strict=True,
        pivotal_inclusive=True,
        source_page_refs=[55, 65, 68],
    )
    base.update(overrides)
    return TrialRecord(**base)


# -- pipeline orchestration (mocked fetch + extract) -------------------------

def test_pipeline_single_entry_fda_only(tmp_path):
    entry = _corpus_entry(ema_procedure_number=None, ema_epar_url=None)
    out = tmp_path / "out.csv"

    with mock.patch("dossiergap.pipeline._fda_for") as m_fda, \
         mock.patch("dossiergap.pipeline._ema_for") as m_ema:
        m_fda.return_value = _record()

        groups, failures = run_pipeline(
            [entry], cache_dir=tmp_path, out_path=out,
            progress_stream=io.StringIO(),
        )

    assert len(groups) == 1
    assert failures == []
    assert m_fda.called
    assert not m_ema.called
    rows = read_csv(out)
    assert len(rows) == 1


def test_pipeline_merges_fda_and_ema_for_same_trial(tmp_path):
    entry = _corpus_entry()
    out = tmp_path / "out.csv"

    with mock.patch("dossiergap.pipeline._fda_for") as m_fda, \
         mock.patch("dossiergap.pipeline._ema_for") as m_ema:
        m_fda.return_value = _record(source="FDA", dossier_id="207620")
        m_ema.return_value = _record(
            source="EMA", dossier_id="EMEA/H/C/004062",
            source_page_refs=[60, 65, 72],
        )

        groups, failures = run_pipeline(
            [entry], cache_dir=tmp_path, out_path=out,
            progress_stream=io.StringIO(),
        )

    assert len(groups) == 1  # same NCT -> merged
    assert set(groups[0].sources()) == {"FDA", "EMA"}
    row = read_csv(out)[0]
    assert set(row["all_sources"].split("|")) == {"FDA", "EMA"}


def test_pipeline_limit_respected(tmp_path):
    entries = [
        _corpus_entry(drug_inn="drug-a", fda_application_number="111111",
                      ema_procedure_number=None, ema_epar_url=None),
        _corpus_entry(drug_inn="drug-b", fda_application_number="222222",
                      ema_procedure_number=None, ema_epar_url=None),
        _corpus_entry(drug_inn="drug-c", fda_application_number="333333",
                      ema_procedure_number=None, ema_epar_url=None),
    ]
    out = tmp_path / "out.csv"

    with mock.patch("dossiergap.pipeline._fda_for") as m_fda:
        m_fda.side_effect = [
            _record(drug_inn="drug-a", dossier_id="111111", nct_id="NCT00000001"),
            _record(drug_inn="drug-b", dossier_id="222222", nct_id="NCT00000002"),
        ]
        groups, _ = run_pipeline(
            entries, cache_dir=tmp_path, out_path=out, limit=2,
            progress_stream=io.StringIO(),
        )

    assert m_fda.call_count == 2
    assert len(groups) == 2


# -- failure handling -------------------------------------------------------

def test_pipeline_fails_fast_by_default(tmp_path):
    from dossiergap.download.fda import FDADownloadError

    entry = _corpus_entry(ema_procedure_number=None, ema_epar_url=None)
    out = tmp_path / "out.csv"

    with mock.patch("dossiergap.pipeline._fda_for",
                    side_effect=FDADownloadError("simulated")):
        with pytest.raises(FDADownloadError):
            run_pipeline([entry], cache_dir=tmp_path, out_path=out,
                         progress_stream=io.StringIO())


def test_pipeline_continue_on_error_collects_failures(tmp_path):
    from dossiergap.download.fda import FDADownloadError

    good = _corpus_entry(drug_inn="good", fda_application_number="111111",
                         ema_procedure_number=None, ema_epar_url=None)
    bad = _corpus_entry(drug_inn="bad", fda_application_number="222222",
                        ema_procedure_number=None, ema_epar_url=None)
    out = tmp_path / "out.csv"

    def fake_fda(entry, cache_dir):
        if entry.drug_inn == "bad":
            raise FDADownloadError("simulated 404")
        return _record(drug_inn="good", dossier_id="111111",
                       nct_id="NCT00000001")

    with mock.patch("dossiergap.pipeline._fda_for", side_effect=fake_fda):
        groups, failures = run_pipeline(
            [good, bad], cache_dir=tmp_path, out_path=out,
            continue_on_error=True,
            progress_stream=io.StringIO(),
        )

    assert len(groups) == 1
    assert len(failures) == 1
    assert failures[0].drug_inn == "bad"
    assert "simulated 404" in failures[0].reason


# -- CSV round-trip integration ---------------------------------------------

def test_pipeline_output_is_valid_trialrecord(tmp_path):
    entry = _corpus_entry(ema_procedure_number=None, ema_epar_url=None)
    out = tmp_path / "out.csv"

    with mock.patch("dossiergap.pipeline._fda_for") as m_fda:
        m_fda.return_value = _record()
        run_pipeline([entry], cache_dir=tmp_path, out_path=out,
                     progress_stream=io.StringIO())

    rows = read_csv(out)
    parsed = row_to_trial_record(rows[0])
    assert parsed.effect_estimate == pytest.approx(0.80)
    assert parsed.nct_id == "NCT01035255"


# -- seed corpus has URLs for at least Entresto -----------------------------

def test_seed_corpus_entresto_has_urls():
    entries = load_corpus(SEED_CORPUS)
    entresto = next((e for e in entries if e.brand_us == "Entresto"), None)
    assert entresto is not None, "seed corpus missing Entresto entry"
    assert entresto.fda_medical_review_url, "Entresto entry missing FDA URL"
    assert entresto.ema_epar_url, "Entresto entry missing EMA URL"


# -- full-pipeline integration against real cached PDFs --------------------

@pytest.mark.skipif(
    not (ENTRESTO_MEDR.is_file() and ENTRESTO_EPAR.is_file()),
    reason="cached Entresto PDFs not present",
)
def test_real_end_to_end_entresto_smoke(tmp_path):
    """End-to-end: real PDFs -> extraction -> dedup -> CSV -> reparse."""
    cache_dir = Path(__file__).resolve().parents[1] / "cache"
    entries = load_corpus(SEED_CORPUS)
    entresto = [e for e in entries if e.brand_us == "Entresto"]
    assert len(entresto) >= 1

    out = tmp_path / "dossier_trials.v0.1.0.csv"
    groups, failures = run_pipeline(
        entresto, cache_dir=cache_dir, out_path=out, limit=1,
        progress_stream=io.StringIO(),
    )

    assert failures == []
    assert len(groups) == 1
    group = groups[0]
    # PARADIGM-HF should come from both FDA and EMA, dedup merges to one row
    assert set(group.sources()) == {"FDA", "EMA"}
    # Canonical (FDA) should have HR 0.80, CI 0.73-0.87
    assert group.canonical.effect_estimate == pytest.approx(0.80, abs=0.01)

    # CSV is valid and round-trippable
    rows = read_csv(out)
    assert len(rows) == 1
    parsed = row_to_trial_record(rows[0])
    assert parsed.effect_estimate == pytest.approx(0.80, abs=0.01)
    assert "FDA" in rows[0]["all_sources"] and "EMA" in rows[0]["all_sources"]
