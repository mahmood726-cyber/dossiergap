"""Shared PDF-fetch transport for FDA (Task 3) and EMA (Task 4) downloaders.

Both sources publish their dossier documents as PDFs behind varying URL
schemes. Only the URL discovery differs; the transport is identical:
cache-hit bypass, urllib3 retry on 429/5xx, fail-closed on non-200,
non-PDF body, empty body, and connection errors. Partial files are
never written to the cache.
"""
from __future__ import annotations

from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PDF_MAGIC = b"%PDF-"
RETRIABLE_STATUS = (429, 500, 502, 503, 504)


class DownloadError(RuntimeError):
    """Base class for dossier-fetch failures. Subclassed per source."""


def make_session() -> requests.Session:
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


def fetch_pdf(
    url: str,
    cache_path: Path,
    *,
    error_cls: type[DownloadError] = DownloadError,
    timeout: int = 30,
    session: requests.Session | None = None,
) -> Path:
    """Fetch a PDF to ``cache_path``, returning the path on success.

    On cache hit (file exists and non-empty), the network is not touched.
    Failure modes raise ``error_cls`` without writing any file.
    """
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        return cache_path

    sess = session if session is not None else make_session()

    try:
        resp = sess.get(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        raise error_cls(f"{url}: {type(e).__name__}: {e}") from e

    if resp.status_code != 200:
        note = " (possible Cloudflare block)" if resp.status_code == 403 else ""
        raise error_cls(f"{url}: HTTP {resp.status_code}{note}")

    body = resp.content or b""
    if len(body) == 0:
        raise error_cls(f"{url}: empty response body")

    if not body.startswith(PDF_MAGIC):
        ctype = resp.headers.get("content-type", "")
        raise error_cls(
            f"{url}: expected PDF magic {PDF_MAGIC!r}; "
            f"got content-type={ctype!r}, body[:32]={body[:32]!r}"
        )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(body)
    return cache_path
