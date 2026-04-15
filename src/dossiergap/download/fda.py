"""FDA Drugs@FDA Medical Review downloader.

Design choices:
- The caller supplies the Medical Review PDF URL. URL discovery from the
  Drugs@FDA approval-package index is deferred (see PROGRESS.md "open
  decision"). For Phase 1 smoke-testing we hand-seed URLs for the 3-NME
  subset; full-corpus URL discovery is a Task 3.5 problem.
- Retries and bounded backoff are handled by urllib3's Retry adapter so
  the code stays linear. Tests can pass a mocked session to bypass both
  the retries and the sleeps.
- Fail-closed on: non-200 (including 403), Cloudflare HTML masquerading
  as a 200, empty body, and connection errors. Partial files are never
  written to the cache.
"""
from __future__ import annotations

from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PDF_MAGIC = b"%PDF-"
RETRIABLE_STATUS = (429, 500, 502, 503, 504)


class FDADownloadError(RuntimeError):
    pass


def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=list(RETRIABLE_STATUS),
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {"User-Agent": "DossierGap/0.1 (publication-gap audit; +https://github.com/)"}
    )
    return session


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

    Returns the cached path on success. Raises ``FDADownloadError`` on any
    failure mode (non-200, non-PDF body, empty body, connection error).
    """
    cache_path = cache_dir / "fda" / application_number / "medical_review.pdf"
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        return cache_path

    sess = session if session is not None else _make_session()

    try:
        resp = sess.get(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        raise FDADownloadError(f"{url}: {type(e).__name__}: {e}") from e

    if resp.status_code != 200:
        raise FDADownloadError(
            f"{url}: HTTP {resp.status_code}"
            + (" (possible Cloudflare block)" if resp.status_code == 403 else "")
        )

    body = resp.content or b""
    if len(body) == 0:
        raise FDADownloadError(f"{url}: empty response body")

    if not body.startswith(PDF_MAGIC):
        ctype = resp.headers.get("content-type", "")
        raise FDADownloadError(
            f"{url}: expected PDF magic {PDF_MAGIC!r}; "
            f"got content-type={ctype!r}, body[:32]={body[:32]!r}"
        )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(body)
    return cache_path
