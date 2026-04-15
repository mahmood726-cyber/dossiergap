"""Task 4 — EMA EPAR downloader tests. Mirror of test_download_fda.py."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
import requests

from dossiergap.download.ema import EMADownloadError, fetch_epar

MIN_PDF = b"%PDF-1.7\n%%EOF\n"

EMA_URL = "https://www.ema.europa.eu/en/documents/assessment-report/entresto-epar-public-assessment-report_en.pdf"
PROC = "EMEA/H/C/004062"


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

    out = fetch_epar(EMA_URL, PROC, cache_dir=tmp_path, session=session)

    assert out.is_file()
    assert out.read_bytes() == MIN_PDF
    assert out.name == "epar.pdf"


def test_fetch_uses_cache_when_present(tmp_path):
    # Build the expected cache path manually using the same sanitisation rule
    safe_proc = PROC.replace("/", "_")
    cached = tmp_path / "ema" / safe_proc / "epar.pdf"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(MIN_PDF)

    session = mock.Mock(spec=requests.Session)
    out = fetch_epar(EMA_URL, PROC, cache_dir=tmp_path, session=session)

    assert out == cached
    session.get.assert_not_called()


# -- slash-sanitisation (EMA-specific) ---------------------------------------

def test_procedure_slashes_sanitised_in_cache_path(tmp_path):
    """EMA procedure numbers contain `/` — must be replaced in cache key so
    the cache dir is a single sibling of `fda/`, not a 4-level nested tree."""
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(200, MIN_PDF)

    out = fetch_epar(EMA_URL, "EMEA/H/C/004062", cache_dir=tmp_path, session=session)

    assert "/" not in out.parent.name, (
        f"procedure number slashes leaked into cache path component: {out.parent.name!r}"
    )
    assert out.parent.parent.name == "ema"
    assert out.parent.name == "EMEA_H_C_004062"


def test_distinct_procedures_cache_separately(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(200, MIN_PDF)

    out1 = fetch_epar(EMA_URL, "EMEA/H/C/004062", cache_dir=tmp_path, session=session)
    out2 = fetch_epar(EMA_URL, "EMEA/H/C/005459", cache_dir=tmp_path, session=session)

    assert out1 != out2
    assert out1.parent != out2.parent


# -- fail-closed error paths -------------------------------------------------

def test_fetch_raises_on_403(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(403, b"")
    with pytest.raises(EMADownloadError, match="403"):
        fetch_epar(EMA_URL, PROC, cache_dir=tmp_path, session=session)


def test_fetch_raises_on_404(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(404, b"")
    with pytest.raises(EMADownloadError, match="404"):
        fetch_epar(EMA_URL, PROC, cache_dir=tmp_path, session=session)


def test_fetch_raises_on_non_pdf_body(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(
        200,
        b"<html><body>not a PDF</body></html>",
        headers={"content-type": "text/html"},
    )
    with pytest.raises(EMADownloadError, match="expected PDF"):
        fetch_epar(EMA_URL, PROC, cache_dir=tmp_path, session=session)


def test_fetch_raises_on_empty_body(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(200, b"")
    with pytest.raises(EMADownloadError, match="empty"):
        fetch_epar(EMA_URL, PROC, cache_dir=tmp_path, session=session)


def test_fetch_raises_on_connection_error(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.side_effect = requests.ConnectionError("network down")
    with pytest.raises(EMADownloadError, match="network down|ConnectionError"):
        fetch_epar(EMA_URL, PROC, cache_dir=tmp_path, session=session)


# -- partial-write safety ----------------------------------------------------

def test_no_partial_file_written_on_failure(tmp_path):
    session = mock.Mock(spec=requests.Session)
    session.get.return_value = _mock_response(403, b"")
    with pytest.raises(EMADownloadError):
        fetch_epar(EMA_URL, PROC, cache_dir=tmp_path, session=session)

    safe_proc = PROC.replace("/", "_")
    cached = tmp_path / "ema" / safe_proc / "epar.pdf"
    assert not cached.exists()


# -- error-class hierarchy ---------------------------------------------------

def test_ema_error_inherits_common_download_error():
    from dossiergap.download._common import DownloadError
    assert issubclass(EMADownloadError, DownloadError)
