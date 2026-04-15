"""EMA EPAR (European Public Assessment Report) downloader.

Mirror of ``fda.py``. EMA procedure numbers (``EMEA/H/C/NNNNNN``) contain
forward slashes, which would collapse into nested cache subdirectories;
we sanitise slashes to underscores so every procedure has a single,
sibling-of-``fda/`` cache dir.

URL discovery (from the EMA procedure overview page to the actual PDF
URL) is deferred — Phase 1 smoke uses hand-seeded URLs.
"""
from __future__ import annotations

from pathlib import Path

import requests

from ._common import DownloadError, fetch_pdf, make_session


class EMADownloadError(DownloadError):
    pass


_make_session = make_session


def _sanitise_procedure(procedure_number: str) -> str:
    return procedure_number.replace("/", "_")


def fetch_epar(
    url: str,
    procedure_number: str,
    cache_dir: Path,
    *,
    timeout: int = 30,
    session: requests.Session | None = None,
) -> Path:
    """Fetch an EMA EPAR PDF, cache it, return the cached path.

    Cache layout: ``{cache_dir}/ema/{sanitised_procedure}/epar.pdf``
    where ``sanitised_procedure`` replaces every ``/`` with ``_``.
    Raises ``EMADownloadError`` on any failure.
    """
    safe = _sanitise_procedure(procedure_number)
    cache_path = cache_dir / "ema" / safe / "epar.pdf"
    resolved_session = session if session is not None else _make_session()
    return fetch_pdf(
        url,
        cache_path,
        error_cls=EMADownloadError,
        timeout=timeout,
        session=resolved_session,
    )
