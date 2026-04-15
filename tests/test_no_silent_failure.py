"""Task 13 — contract test against silent-failure sentinels.

Per the 2026-04-14 MetaReproducer lesson, silent-failure sentinels
('unknown', None in a numeric field, empty strings where text is
required) are worse than a raised exception — they let the pipeline
complete with corrupted output that reaches analysis. This suite runs
the CLI on the Entresto smoke subset and asserts the output CSV has
no such sentinels.

The expensive CLI subprocess is scoped 'module' so all contract
assertions share one CLI run.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from dossiergap.io.csv_writer import CSV_COLUMNS, read_csv, row_to_trial_record

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_CORPUS = REPO_ROOT / "data" / "cardiology-nme-corpus.json"
ENTRESTO_MEDR = REPO_ROOT / "cache" / "fda" / "207620" / "medical_review.pdf"
ENTRESTO_EPAR = REPO_ROOT / "cache" / "ema" / "EMEA_H_C_004062" / "epar.pdf"

SENTINEL_STRINGS = {"unknown", "none", "null", "n/a", "na", "?", "tbd", "todo"}


# -- fixture: run CLI once, reuse CSV for all contract tests -----------------

@pytest.fixture(scope="module")
def cli_smoke_csv(tmp_path_factory):
    if not (ENTRESTO_MEDR.is_file() and ENTRESTO_EPAR.is_file()):
        pytest.skip("cached Entresto PDFs not present; run smoke fetch to populate")

    out_dir = tmp_path_factory.mktemp("cli_smoke")
    out = out_dir / "dossier_trials.v0.1.0.csv"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["DOSSIERGAP_CACHE_DIR"] = str(REPO_ROOT / "cache")

    result = subprocess.run(
        [
            sys.executable, "-m", "dossiergap", "extract",
            "--corpus", str(SEED_CORPUS),
            "--out", str(out),
            "--limit", "1",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"CLI exit {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert out.is_file(), f"CLI produced no CSV at {out}"
    return out


# -- CSV structure -----------------------------------------------------------

def test_csv_has_header_comment(cli_smoke_csv):
    first_line = cli_smoke_csv.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("#")
    assert "DossierGap" in first_line
    # Version tag like v0.1.0
    assert re.search(r"v\d+\.\d+\.\d+", first_line)


def test_csv_columns_match_frozen_schema(cli_smoke_csv):
    rows = read_csv(cli_smoke_csv)
    assert len(rows) >= 1
    assert set(rows[0].keys()) == set(CSV_COLUMNS)


def test_csv_has_at_least_one_row(cli_smoke_csv):
    rows = read_csv(cli_smoke_csv)
    assert len(rows) >= 1, "CLI smoke run produced no data rows"


# -- silent-failure contracts ------------------------------------------------

def test_no_zero_or_negative_n_randomized(cli_smoke_csv):
    for row in read_csv(cli_smoke_csv):
        n = int(row["n_randomized"])
        assert n > 0, f"row has n_randomized={n} which is a silent-failure sentinel"


def test_no_empty_required_text_fields(cli_smoke_csv):
    required = [
        "source", "dossier_id", "drug_inn", "sponsor",
        "trial_phase", "primary_outcome", "effect_metric",
    ]
    for row in read_csv(cli_smoke_csv):
        for field in required:
            assert row[field].strip() != "", (
                f"row has empty {field!r} — silent-failure sentinel"
            )


def test_no_sentinel_strings_anywhere(cli_smoke_csv):
    """Scan every non-numeric field for 'unknown'/'n/a'/'tbd' and friends."""
    numeric_fields = {
        "n_randomized", "effect_estimate", "effect_ci_low", "effect_ci_high",
    }
    list_fields = {"source_page_refs", "page_refs_fda", "page_refs_ema"}
    json_fields = {"dedup_conflicts"}
    skip = numeric_fields | list_fields | json_fields

    for row in read_csv(cli_smoke_csv):
        for field, value in row.items():
            if field in skip:
                continue
            if value.strip().lower() in SENTINEL_STRINGS:
                raise AssertionError(
                    f"row has sentinel {value!r} in field {field!r} — "
                    "silent-failure sentinel per 2026-04-14 lesson"
                )


def test_effect_estimate_is_finite_number(cli_smoke_csv):
    for row in read_csv(cli_smoke_csv):
        est = float(row["effect_estimate"])
        assert est == est, "effect_estimate is NaN"  # NaN != NaN
        assert abs(est) < 1e6, f"effect_estimate {est} is implausibly large"


def test_ci_bounds_are_finite_numbers(cli_smoke_csv):
    for row in read_csv(cli_smoke_csv):
        lo = float(row["effect_ci_low"])
        hi = float(row["effect_ci_high"])
        assert lo == lo and hi == hi, "CI bound is NaN"
        assert lo <= hi, f"ci_low {lo} > ci_high {hi}"


def test_ci_contains_estimate(cli_smoke_csv):
    for row in read_csv(cli_smoke_csv):
        est = float(row["effect_estimate"])
        lo = float(row["effect_ci_low"])
        hi = float(row["effect_ci_high"])
        assert lo <= est <= hi, (
            f"CI [{lo}, {hi}] does not contain estimate {est} — "
            "schema invariant would have caught this on construction; "
            "survival here means silent corruption in the writer path"
        )


def test_source_page_refs_nonempty(cli_smoke_csv):
    """Audit-trail requirement from the schema."""
    for row in read_csv(cli_smoke_csv):
        refs = row["source_page_refs"].split("|") if row["source_page_refs"] else []
        assert len(refs) >= 1, (
            "row has no source_page_refs — audit trail missing, "
            "Task 14 hand-audit is impossible for this trial"
        )
        for r in refs:
            assert int(r) >= 1, f"page ref {r!r} is not a positive 1-indexed integer"


# -- round-trip + CLI exit integrity ---------------------------------------

def test_every_row_reconstructs_to_valid_trialrecord(cli_smoke_csv):
    """If the CSV cannot rebuild a valid TrialRecord the writer or extractor
    introduced silent corruption that the schema validator would have caught
    on original construction."""
    for row in read_csv(cli_smoke_csv):
        rec = row_to_trial_record(row)  # raises if any field fails validation
        assert rec is not None


def test_entresto_smoke_produces_hr_in_expected_range(cli_smoke_csv):
    """Protects against regression to nonsense values from extractor changes."""
    rows = read_csv(cli_smoke_csv)
    entresto = [r for r in rows if r["drug_inn"] == "sacubitril/valsartan"]
    assert entresto, "Entresto row missing from smoke output"
    est = float(entresto[0]["effect_estimate"])
    assert 0.5 < est < 1.0, (
        f"Entresto/PARADIGM-HF effect estimate {est} outside plausible range — "
        "extraction regressed from HR 0.80"
    )


# -- CLI fail-closed behaviours (short, not subprocess-slow) ---------------

def test_cli_fails_on_missing_corpus_file(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    result = subprocess.run(
        [
            sys.executable, "-m", "dossiergap", "extract",
            "--corpus", str(tmp_path / "does_not_exist.json"),
            "--out", str(tmp_path / "out.csv"),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0, "CLI did not fail on missing corpus"
    combined = (result.stdout + result.stderr).lower()
    assert "not found" in combined or "no such file" in combined or "corpus" in combined


def test_cli_rejects_unknown_subcommand(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "dossiergap", "nonsense-command"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
