"""Serialize DedupGroups to a versioned dossier_trials.csv.

Output shape:
    # DossierGap dossier_trials <version> | <date>
    source,dossier_id,drug_inn,...,dedup_conflicts
    FDA,207620,sacubitril/valsartan,...,<json>
    ...

One row per DedupGroup (= one row per unique pivotal trial). The leading
``#`` comment line carries the schema version and generation date; the
CSV header on line 2 is frozen to ``CSV_COLUMNS``.

Canonical TrialRecord fields (first block of columns) round-trip back
to a TrialRecord via ``row_to_trial_record``. Dedup-metadata columns
(all_sources, page_refs_{fda,ema}, dedup_conflicts) carry information
that can't live on a single-source TrialRecord.
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from dossiergap.dedup import DedupGroup
from dossiergap.schema import TrialRecord

CSV_SCHEMA_VERSION = "v0.1.0"

CSV_COLUMNS: list[str] = [
    # Canonical TrialRecord fields (order matches schema.py field order).
    "source",
    "dossier_id",
    "drug_inn",
    "sponsor",
    "trial_phase",
    "nct_id",
    "n_randomized",
    "primary_outcome",
    "effect_metric",
    "effect_estimate",
    "effect_ci_low",
    "effect_ci_high",
    "reported_in_label",
    "pivotal_strict",
    "pivotal_inclusive",
    "source_page_refs",
    # Dedup-metadata columns.
    "all_sources",
    "all_dossier_ids",
    "page_refs_fda",
    "page_refs_ema",
    "dedup_conflicts",
]


def _encode_int_list(xs: list[int]) -> str:
    return "|".join(str(x) for x in xs)


def _encode_str_list(xs: list[str]) -> str:
    return "|".join(xs)


def _encode_conflicts(conflicts: dict[str, list[Any]]) -> str:
    if not conflicts:
        return ""
    return json.dumps(conflicts, sort_keys=True, default=str)


def _group_to_row(group: DedupGroup) -> dict[str, Any]:
    c = group.canonical
    page_refs_by_src = group.page_refs_by_source()
    return {
        "source": c.source,
        "dossier_id": c.dossier_id,
        "drug_inn": c.drug_inn,
        "sponsor": c.sponsor,
        "trial_phase": c.trial_phase,
        "nct_id": c.nct_id or "",
        "n_randomized": c.n_randomized,
        "primary_outcome": c.primary_outcome,
        "effect_metric": c.effect_metric,
        "effect_estimate": c.effect_estimate,
        "effect_ci_low": c.effect_ci_low,
        "effect_ci_high": c.effect_ci_high,
        "reported_in_label": c.reported_in_label,
        "pivotal_strict": c.pivotal_strict,
        "pivotal_inclusive": c.pivotal_inclusive,
        "source_page_refs": _encode_int_list(c.source_page_refs),
        "all_sources": _encode_str_list(group.sources()),
        "all_dossier_ids": _encode_str_list([r.dossier_id for r in group.records]),
        "page_refs_fda": _encode_int_list(page_refs_by_src.get("FDA", [])),
        "page_refs_ema": _encode_int_list(page_refs_by_src.get("EMA", [])),
        "dedup_conflicts": _encode_conflicts(group.conflicts),
    }


def write_csv(
    groups: list[DedupGroup],
    out_path: Path,
    version_tag: str = CSV_SCHEMA_VERSION,
) -> Path:
    """Write dedup groups to a versioned CSV.

    Returns the written path. Parent directories are created on demand.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        f.write(
            f"# DossierGap dossier_trials {version_tag} "
            f"| generated {date.today().isoformat()}\n"
        )
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for group in groups:
            writer.writerow(_group_to_row(group))
    return out_path


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read data rows from a DossierGap CSV, skipping the ``#`` comment line."""
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        first = f.readline()
        if not first.startswith("#"):
            f.seek(0)
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _parse_bool(s: str) -> bool:
    return s.strip().lower() in ("true", "1", "yes")


def _parse_int_list(s: str) -> list[int]:
    if not s:
        return []
    return [int(p) for p in s.split("|") if p]


def row_to_trial_record(row: dict[str, str]) -> TrialRecord:
    """Reconstruct a TrialRecord from a CSV row (canonical fields only)."""
    return TrialRecord(
        source=row["source"],
        dossier_id=row["dossier_id"],
        drug_inn=row["drug_inn"],
        sponsor=row["sponsor"],
        trial_phase=row["trial_phase"],
        nct_id=row["nct_id"] if row["nct_id"] else None,
        n_randomized=int(row["n_randomized"]),
        primary_outcome=row["primary_outcome"],
        effect_metric=row["effect_metric"],
        effect_estimate=float(row["effect_estimate"]),
        effect_ci_low=float(row["effect_ci_low"]),
        effect_ci_high=float(row["effect_ci_high"]),
        reported_in_label=_parse_bool(row["reported_in_label"]),
        pivotal_strict=_parse_bool(row["pivotal_strict"]),
        pivotal_inclusive=_parse_bool(row["pivotal_inclusive"]),
        source_page_refs=_parse_int_list(row["source_page_refs"]),
    )
