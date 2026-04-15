"""TrialRecord schema — the contract for Phase 1 extraction output.

Invariants enforced by validators:
- CI bounds must contain the point estimate on natural scale.
- `source_page_refs` must be non-empty (audit trail required for Task 14).
- `pivotal_strict=True` implies `pivotal_inclusive=True` (strict is a
  subset of inclusive by construction; see docs/pivotal-criterion.md).

Effect estimates are stored on NATURAL scale for HR/RR/OR (reference
1.0) and on natural scale for MD/SMD/RD (reference 0.0). Log-transform
happens at pool time in Phase 3, not at storage.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Source = Literal["FDA", "EMA"]
TrialPhase = Literal["2", "2/3", "3", "3b", "4"]
EffectMetric = Literal["HR", "RR", "OR", "MD", "SMD", "RD"]

_NCT_RE = re.compile(r"^NCT\d{8}$")


class TrialRecord(BaseModel):
    source: Source
    dossier_id: str = Field(min_length=1)
    drug_inn: str = Field(min_length=1)
    sponsor: str = Field(min_length=1)
    trial_phase: TrialPhase
    nct_id: str | None = None
    n_randomized: int = Field(gt=0)
    primary_outcome: str = Field(min_length=1)
    effect_metric: EffectMetric
    effect_estimate: float
    effect_ci_low: float
    effect_ci_high: float
    reported_in_label: bool
    pivotal_strict: bool
    pivotal_inclusive: bool
    source_page_refs: list[int] = Field(min_length=1)

    @field_validator("nct_id")
    @classmethod
    def _validate_nct(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _NCT_RE.match(v):
            raise ValueError(f"NCT id must match ^NCT\\d{{8}}$, got {v!r}")
        return v

    @field_validator("source_page_refs")
    @classmethod
    def _validate_page_refs(cls, v: list[int]) -> list[int]:
        for p in v:
            if p < 1:
                raise ValueError(
                    f"source_page_refs must be 1-indexed positive ints, got {p}"
                )
        return v

    @model_validator(mode="after")
    def _validate_ci_contains_estimate(self) -> "TrialRecord":
        if self.effect_ci_low > self.effect_ci_high:
            raise ValueError(
                f"ci_low ({self.effect_ci_low}) > ci_high ({self.effect_ci_high})"
            )
        if not (self.effect_ci_low <= self.effect_estimate <= self.effect_ci_high):
            raise ValueError(
                f"ci must contain estimate: "
                f"{self.effect_ci_low} <= {self.effect_estimate} <= {self.effect_ci_high} "
                f"is false"
            )
        return self

    @model_validator(mode="after")
    def _validate_pivotal_subset(self) -> "TrialRecord":
        if self.pivotal_strict and not self.pivotal_inclusive:
            raise ValueError(
                "pivotal_strict=True requires pivotal_inclusive=True "
                "(strict is a subset of inclusive; see docs/pivotal-criterion.md)"
            )
        return self
