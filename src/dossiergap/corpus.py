"""Cardiology NME corpus loader + schema validator.

The corpus is the authoritative list of FDA/EMA dossier-review events
whose pivotal trials are in Phase 1 scope. Each entry is one
approval event (NDA, BLA, sNDA for a new indication, or EMA
procedure). An sNDA for a new CV indication on an existing molecule
is a distinct corpus entry from the original approval.

Inclusion rules: see `docs/corpus-criteria.md`.
Pivotal criterion: see `docs/pivotal-criterion.md`.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ApprovalType = Literal["NDA", "BLA", "sNDA", "sBLA", "EPAR"]

_FDA_APP_RE = re.compile(r"^\d{6}$")
_EMA_PROC_RE = re.compile(r"^EMEA/H/C/\d{6}$")


class CorpusEntry(BaseModel):
    drug_inn: str = Field(min_length=2)
    brand_us: str | None = None
    fda_application_number: str | None = None
    fda_approval_type: ApprovalType | None = None
    fda_approval_date: date | None = None
    ema_procedure_number: str | None = None
    ema_approval_date: date | None = None
    cv_indication: str = Field(min_length=2)
    fda_medical_review_url: str | None = None  # hand-seeded until Task 3.5 URL discovery
    ema_epar_url: str | None = None            # hand-seeded until Task 4.5 URL discovery
    notes: str = ""

    @field_validator("fda_application_number")
    @classmethod
    def _validate_fda_app(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _FDA_APP_RE.match(v):
            raise ValueError(f"FDA application number must be 6 digits, got {v!r}")
        return v

    @field_validator("ema_procedure_number")
    @classmethod
    def _validate_ema_proc(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _EMA_PROC_RE.match(v):
            raise ValueError(f"EMA procedure number must match EMEA/H/C/NNNNNN, got {v!r}")
        return v

    def has_dossier_source(self) -> bool:
        """At least one of FDA or EMA must be identified for extraction."""
        return self.fda_application_number is not None or self.ema_procedure_number is not None


class CorpusError(ValueError):
    pass


def load_corpus(path: Path) -> list[CorpusEntry]:
    if not path.is_file():
        raise CorpusError(f"corpus file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CorpusError(f"{path}: invalid JSON — {e}") from e
    if not isinstance(raw, list):
        raise CorpusError(f"{path}: expected top-level JSON array")
    entries: list[CorpusEntry] = []
    for i, row in enumerate(raw):
        try:
            entries.append(CorpusEntry.model_validate(row))
        except Exception as e:
            raise CorpusError(f"{path} entry {i}: {e}") from e
    if not entries:
        raise CorpusError(f"{path}: corpus is empty")
    for i, entry in enumerate(entries):
        if not entry.has_dossier_source():
            raise CorpusError(
                f"{path} entry {i} ({entry.drug_inn}): "
                "must have fda_application_number OR ema_procedure_number"
            )
    return entries
