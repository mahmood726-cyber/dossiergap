"""FDA Drugs@FDA Medical Review downloader.

Design choices:
- The caller supplies the Medical Review PDF URL. URL discovery from the
  Drugs@FDA approval-package index is deferred to Task 3.5 — for Phase 1
  smoke-testing we hand-seed URLs for the 3-NME subset.
- Transport (retry, fail-closed on non-PDF, no partial writes) lives in
  ``_common.py`` and is shared with the EMA downloader.
"""
from __future__ import annotations

from pathlib import Path

import requests

from ._common import DownloadError, fetch_pdf, make_session  # noqa: F401


class FDADownloadError(DownloadError):
    pass


# Backwards-compat: tests patch this symbol for the "no session passed" case.
_make_session = make_session


def fetch_medical_review(
    url: str,
    application_number: str,
    cache_dir: Path,
    *,
    timeout: int = 30,
    session: requests.Session | None = None,
) -> Path:
    """Fetch an FDA Medical Review PDF, cache it, return the cached path.

    Cache layout: ``{cache_dir}/fda/{application_number}/medical_review.pdf``.
    Raises ``FDADownloadError`` on any failure.
    """
    cache_path = cache_dir / "fda" / application_number / "medical_review.pdf"
    resolved_session = session if session is not None else _make_session()
    return fetch_pdf(
        url,
        cache_path,
        error_cls=FDADownloadError,
        timeout=timeout,
        session=resolved_session,
    )
