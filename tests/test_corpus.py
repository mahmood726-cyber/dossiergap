"""Task 2 — cardiology NME corpus tests."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from dossiergap.corpus import CorpusEntry, CorpusError, load_corpus

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_CORPUS = REPO_ROOT / "data" / "cardiology-nme-corpus.json"

SEED_MIN_ENTRIES = 15  # current seed floor; will tighten to >=40 before Task 14


# -- schema-level -------------------------------------------------------------

def test_entry_requires_drug_inn():
    with pytest.raises(Exception):
        CorpusEntry.model_validate({"cv_indication": "HFrEF"})


def test_entry_requires_cv_indication():
    with pytest.raises(Exception):
        CorpusEntry.model_validate({"drug_inn": "x"})


def test_entry_rejects_malformed_fda_number():
    with pytest.raises(Exception):
        CorpusEntry.model_validate(
            {"drug_inn": "x", "cv_indication": "y", "fda_application_number": "abc123"}
        )


def test_entry_rejects_malformed_ema_procedure():
    with pytest.raises(Exception):
        CorpusEntry.model_validate(
            {"drug_inn": "x", "cv_indication": "y", "ema_procedure_number": "EU/H/C/123"}
        )


def test_entry_accepts_valid_fda_and_ema():
    e = CorpusEntry.model_validate(
        {
            "drug_inn": "sacubitril/valsartan",
            "cv_indication": "HFrEF",
            "fda_application_number": "207620",
            "ema_procedure_number": "EMEA/H/C/004062",
            "fda_approval_date": "2015-07-07",
        }
    )
    assert e.fda_approval_date == date(2015, 7, 7)
    assert e.has_dossier_source() is True


def test_entry_without_any_dossier_id_is_flagged_by_loader(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(
        json.dumps([{"drug_inn": "phantom", "cv_indication": "HFrEF"}]),
        encoding="utf-8",
    )
    with pytest.raises(CorpusError, match="fda_application_number OR ema_procedure_number"):
        load_corpus(f)


# -- loader-level -------------------------------------------------------------

def test_load_corpus_missing_file(tmp_path):
    with pytest.raises(CorpusError, match="not found"):
        load_corpus(tmp_path / "nope.json")


def test_load_corpus_invalid_json(tmp_path):
    f = tmp_path / "c.json"
    f.write_text("{not json", encoding="utf-8")
    with pytest.raises(CorpusError, match="invalid JSON"):
        load_corpus(f)


def test_load_corpus_empty_array(tmp_path):
    f = tmp_path / "c.json"
    f.write_text("[]", encoding="utf-8")
    with pytest.raises(CorpusError, match="empty"):
        load_corpus(f)


def test_load_corpus_non_array(tmp_path):
    f = tmp_path / "c.json"
    f.write_text('{"drug_inn": "x"}', encoding="utf-8")
    with pytest.raises(CorpusError, match="top-level JSON array"):
        load_corpus(f)


# -- seed-file-level ----------------------------------------------------------

def test_seed_corpus_file_exists():
    assert SEED_CORPUS.is_file(), f"seed corpus missing at {SEED_CORPUS}"


def test_seed_corpus_loads():
    entries = load_corpus(SEED_CORPUS)
    assert len(entries) >= SEED_MIN_ENTRIES, (
        f"seed corpus has {len(entries)} entries, expected >= {SEED_MIN_ENTRIES}"
    )


def test_seed_corpus_all_entries_have_dossier_source():
    entries = load_corpus(SEED_CORPUS)
    for e in entries:
        assert e.has_dossier_source(), f"{e.drug_inn} / {e.cv_indication} has no FDA or EMA id"


def test_seed_corpus_approval_dates_in_phase1_window():
    entries = load_corpus(SEED_CORPUS)
    window_start = date(2015, 1, 1)
    window_end = date(2025, 12, 31)
    for e in entries:
        if e.fda_approval_date is not None:
            assert window_start <= e.fda_approval_date <= window_end, (
                f"{e.drug_inn} FDA date {e.fda_approval_date} outside 2015-2025 window"
            )
        if e.ema_approval_date is not None:
            assert window_start <= e.ema_approval_date <= window_end, (
                f"{e.drug_inn} EMA date {e.ema_approval_date} outside 2015-2025 window"
            )


def test_seed_corpus_covers_multiple_cv_indications():
    entries = load_corpus(SEED_CORPUS)
    indications = {e.cv_indication for e in entries}
    assert len(indications) >= 5, (
        f"seed corpus covers {len(indications)} indications, expected >= 5 for Phase 1 spread"
    )


def test_snda_entries_have_snda_type():
    """sNDA/sBLA entries (new indication on existing molecule) must be typed correctly."""
    entries = load_corpus(SEED_CORPUS)
    for e in entries:
        if e.brand_us and "indication" in e.brand_us.lower():
            assert e.fda_approval_type in ("sNDA", "sBLA"), (
                f"{e.drug_inn} ({e.brand_us}) looks like a supplemental but type={e.fda_approval_type}"
            )
