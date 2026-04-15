"""Cross-register deduplication of pivotal trial records.

The same pivotal trial (e.g., PARADIGM-HF) is typically reviewed by
both FDA and EMA and therefore appears once in the FDA Medical Review
extraction and once in the EMA EPAR extraction. Dedup groups these
into a single ``DedupGroup`` so downstream CSV output has one row per
unique trial — the denominator for the publication-gap analysis.

Matching policy:
    1. Primary key: NCT ID. When both records have one and they match,
       the records are the same trial — even if other fields look
       different (which would reflect extraction noise).
    2. Fallback: when NCT is missing on either side, use a composite
       key (sponsor, drug INN, phase, N ± 5%, primary-outcome substring).
       N tolerance covers FAS-vs-ITT differences in reported analysis
       populations.

Field conflicts (e.g., FDA reports HR 0.80 and EMA reports 0.79) are
recorded in ``DedupGroup.conflicts`` without resolving them — the
canonical record is chosen by source preference (FDA > EMA).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dossiergap.schema import TrialRecord

# Fields compared for conflict detection (source/dossier_id deliberately excluded).
_CONFLICT_FIELDS = (
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
    "pivotal_strict",
    "pivotal_inclusive",
)

_N_TOLERANCE = 0.05  # 5% — covers FAS vs ITT reporting differences
_SOURCE_PREF = {"FDA": 0, "EMA": 1}


@dataclass
class DedupGroup:
    """One unique trial, optionally reviewed by multiple dossier sources."""

    canonical: TrialRecord
    records: list[TrialRecord] = field(default_factory=list)
    conflicts: dict[str, list[Any]] = field(default_factory=dict)

    def sources(self) -> list[str]:
        return sorted({r.source for r in self.records})

    def page_refs_by_source(self) -> dict[str, list[int]]:
        return {r.source: list(r.source_page_refs) for r in self.records}

    def merged_page_refs(self) -> list[int]:
        refs: set[int] = set()
        for r in self.records:
            refs.update(r.source_page_refs)
        return sorted(refs)


def _n_within_tolerance(a: int, b: int) -> bool:
    larger = max(a, b)
    if larger == 0:
        return a == b
    return abs(a - b) / larger <= _N_TOLERANCE


def _outcome_substring_match(a: str, b: str) -> bool:
    al, bl = a.lower().strip(), b.lower().strip()
    return al in bl or bl in al


def _are_same_trial(a: TrialRecord, b: TrialRecord) -> bool:
    # Primary key: NCT match (overrides everything else).
    if a.nct_id and b.nct_id:
        return a.nct_id == b.nct_id

    # Fallback composite key.
    if a.sponsor.lower().split()[0] != b.sponsor.lower().split()[0]:
        # Compare only the first word of sponsor to tolerate "Novartis" vs
        # "Novartis Pharma AG". Good-enough heuristic for Phase 1.
        return False
    if a.drug_inn.lower() != b.drug_inn.lower():
        return False
    if a.trial_phase != b.trial_phase:
        return False
    if not _n_within_tolerance(a.n_randomized, b.n_randomized):
        return False
    if not _outcome_substring_match(a.primary_outcome, b.primary_outcome):
        return False
    return True


def _pick_canonical(records: list[TrialRecord]) -> TrialRecord:
    """Deterministic canonical choice: FDA first, then EMA, then input order."""
    return min(records, key=lambda r: (_SOURCE_PREF.get(r.source, 99),))


def _detect_conflicts(records: list[TrialRecord]) -> dict[str, list[Any]]:
    if len(records) < 2:
        return {}
    conflicts: dict[str, list[Any]] = {}
    for fld in _CONFLICT_FIELDS:
        values = [getattr(r, fld) for r in records]
        unique: list[Any] = []
        for v in values:
            if v not in unique:
                unique.append(v)
        if len(unique) > 1:
            conflicts[fld] = unique
    return conflicts


def dedup_trials(records: list[TrialRecord]) -> list[DedupGroup]:
    """Group records that refer to the same underlying trial.

    Preserves input order for groups: the group containing the first
    input record is returned first. Within a group, records retain their
    input order.
    """
    buckets: list[list[TrialRecord]] = []
    for r in records:
        for bucket in buckets:
            if _are_same_trial(bucket[0], r):
                bucket.append(r)
                break
        else:
            buckets.append([r])

    groups: list[DedupGroup] = []
    for bucket in buckets:
        canonical = _pick_canonical(bucket)
        groups.append(
            DedupGroup(
                canonical=canonical,
                records=list(bucket),
                conflicts=_detect_conflicts(bucket),
            )
        )
    return groups
