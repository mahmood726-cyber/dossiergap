"""Task 3 — FDA Drugs@FDA downloader tests.

All tests mock `requests.Session.get` — no network hits. Real-network
integration is a manual verification step (see PROGRESS.md).
"""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
import requests

from dossiergap.download.fda import (
    FDADownloadError,
    fetch_medical_review,
)

# A minimal valid PDF byte sequence — header magic + EOF marker.
# Not a parseable PDF for pdfplumber but enough to satisfy the magic check.
MIN_PDF = b"%PDF-1.4\n%%EOF\n"

FDA_URL = "https://www.accessdata.fda.gov/drugsatfda_docs/nda/2015/207620Orig1s000MedR.pdf"
APP_NUM = "207620"


def _mock_response(status_code: int, content: bytes, headers: dict | None = None):
    resp = mock.Mock(spec=requests.Response)
    resp.status_code = status_code
    resp.content = content
    resp.headers = headers or {"content-type": "application/pdf"}
    return resp


# -- happy path ---------------------------------------------------------------

def test_fetch_saves_pdf_on_200(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(200, MIN_PDF)

    out = fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)

    assert out == tmp_path / "fda" / APP_NUM / "medical_review.pdf"
    assert out.is_file()
    assert out.read_bytes() == MIN_PDF


def test_fetch_uses_cache_when_present(tmp_path):
    cached = tmp_path / "fda" / APP_NUM / "medical_review.pdf"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(MIN_PDF)

    session = mock.Mock(spec=requests.Session)
    out = fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)

    assert out == cached
    session.get.assert_not_called()


def test_fetch_bypasses_cache_when_empty(tmp_path):
    """A zero-byte cached file is not a valid cache hit."""
    cached = tmp_path / "fda" / APP_NUM / "medical_review.pdf"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"")

    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(200, MIN_PDF)

    out = fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)

    assert out.read_bytes() == MIN_PDF
    session.get.assert_called_once()


# -- fail-closed error paths --------------------------------------------------

def test_fetch_raises_on_403(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(403, b"")

    with pytest.raises(FDADownloadError, match="403"):
        fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)


def test_fetch_raises_on_404(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(404, b"")

    with pytest.raises(FDADownloadError, match="404"):
        fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)


def test_fetch_raises_on_cloudflare_html_masquerade(tmp_path):
    """HTTP 200 with HTML body (e.g. Cloudflare challenge) must fail closed."""
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(
        200,
        b"<!DOCTYPE html><html><body>Checking your browser...</body></html>",
        headers={"content-type": "text/html"},
    )

    with pytest.raises(FDADownloadError, match="expected PDF"):
        fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)


def test_fetch_raises_on_empty_body(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(200, b"")

    with pytest.raises(FDADownloadError, match="empty"):
        fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)


def test_fetch_raises_on_connection_error(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.side_effect = requests.ConnectionError("dns failure")

    with pytest.raises(FDADownloadError, match="dns failure|ConnectionError"):
        fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)


# -- partial-write safety ----------------------------------------------------

def test_no_partial_file_written_on_cloudflare_masquerade(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(
        200,
        b"<html>blocked</html>",
        headers={"content-type": "text/html"},
    )
    with pytest.raises(FDADownloadError):
        fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)

    cached = tmp_path / "fda" / APP_NUM / "medical_review.pdf"
    assert not cached.exists(), "partial/invalid file must not be cached"


def test_no_partial_file_written_on_403(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(403, b"")
    with pytest.raises(FDADownloadError):
        fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)

    cached = tmp_path / "fda" / APP_NUM / "medical_review.pdf"
    assert not cached.exists()


# -- cache layout -----------------------------------------------------------

def test_cache_layout_matches_spec(tmp_path):
    """Cache path must be cache_dir/fda/{application_number}/medical_review.pdf
    so Task 4 (EMA) can mirror the layout under .../ema/{procedure_number}/..."""
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(200, MIN_PDF)

    out = fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path, session=session)

    assert out.parent.parent.name == "fda"
    assert out.parent.name == APP_NUM
    assert out.name == "medical_review.pdf"


def test_cache_layout_uses_distinct_subdirs_for_different_apps(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(200, MIN_PDF)

    out1 = fetch_medical_review(FDA_URL, "207620", cache_dir=tmp_path, session=session)
    out2 = fetch_medical_review(FDA_URL, "214998", cache_dir=tmp_path, session=session)

    assert out1 != out2
    assert out1.parent != out2.parent


# -- session default --------------------------------------------------------

def test_fetch_creates_default_session_when_none_passed(tmp_path):
    """When session=None (production path), the downloader must still work."""
    with mock.patch("dossiergap.download.fda._make_session") as factory:
        inner_session = mock.Mock(spec=requests.Session)
        inner_session.get.return_value = _mock_response(200, MIN_PDF)
        factory.return_value = inner_session

        out = fetch_medical_review(FDA_URL, APP_NUM, cache_dir=tmp_path)

    factory.assert_called_once()
    assert out.is_file()
