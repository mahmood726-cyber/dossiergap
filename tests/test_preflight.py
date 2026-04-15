"""Task 0 — prereq gate tests.

Each check is tested in isolation with mocked dependencies. The
end-to-end `main()` is tested for exit-code behaviour only.
"""
from __future__ import annotations

from unittest import mock

import pytest

import preflight  # path added via pyproject [tool.pytest.ini_options] pythonpath


# -- check_python_version -----------------------------------------------------

def test_python_version_ok_on_current_interpreter():
    ok, msg = preflight.check_python_version(min_major=3, min_minor=13)
    assert ok, msg


def test_python_version_fail_when_floor_above_current():
    ok, msg = preflight.check_python_version(min_major=99, min_minor=0)
    assert not ok
    assert "99.0" in msg


# -- check_import -------------------------------------------------------------

def test_import_check_success_on_stdlib():
    ok, msg = preflight.check_import("json")
    assert ok, msg


def test_import_check_fail_on_missing_module():
    ok, msg = preflight.check_import("definitely_not_a_real_module_xyz")
    assert not ok
    assert "definitely_not_a_real_module_xyz" in msg


# -- check_url ----------------------------------------------------------------

def test_url_check_ok_on_200():
    with mock.patch("preflight.requests.get") as m:
        m.return_value.status_code = 200
        ok, msg = preflight.check_url("https://example.invalid/")
    assert ok, msg


def test_url_check_fail_on_403():
    with mock.patch("preflight.requests.get") as m:
        m.return_value.status_code = 403
        ok, msg = preflight.check_url("https://example.invalid/")
    assert not ok
    assert "403" in msg


def test_url_check_fail_on_connection_error():
    with mock.patch("preflight.requests.get", side_effect=Exception("boom")):
        ok, msg = preflight.check_url("https://example.invalid/")
    assert not ok
    assert "boom" in msg


# -- check_file_exists --------------------------------------------------------

def test_file_check_ok_when_present(tmp_path):
    f = tmp_path / "x.json"
    f.write_text("{}", encoding="utf-8")
    ok, msg = preflight.check_file_exists(f)
    assert ok, msg


def test_file_check_fail_when_missing(tmp_path):
    ok, msg = preflight.check_file_exists(tmp_path / "missing.json")
    assert not ok
    assert "missing.json" in msg


# -- check_writable -----------------------------------------------------------

def test_writable_check_ok(tmp_path):
    ok, msg = preflight.check_writable(tmp_path)
    assert ok, msg


def test_writable_check_fail_on_missing_dir(tmp_path):
    ok, msg = preflight.check_writable(tmp_path / "does_not_exist")
    assert not ok


# -- corpus bootstrap on first run -------------------------------------------

def test_corpus_template_printed_when_missing(tmp_path, capsys):
    corpus = tmp_path / "cardiology-nme-corpus.json"
    ok, msg = preflight.check_corpus(corpus)
    assert not ok
    assert "CREATE THIS FILE" in msg
    assert "drug_inn" in msg  # template is included in the user-action msg


def test_corpus_ok_when_present_and_valid(tmp_path):
    corpus = tmp_path / "cardiology-nme-corpus.json"
    corpus.write_text('[{"drug_inn": "sacubitril/valsartan"}]', encoding="utf-8")
    ok, msg = preflight.check_corpus(corpus)
    assert ok, msg


def test_corpus_fail_on_invalid_json(tmp_path):
    corpus = tmp_path / "cardiology-nme-corpus.json"
    corpus.write_text("{not json", encoding="utf-8")
    ok, msg = preflight.check_corpus(corpus)
    assert not ok
    assert "JSON" in msg


# -- main() ------------------------------------------------------------------

def test_main_exits_1_when_any_check_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "CORPUS_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(preflight, "CACHE_DIR", tmp_path / "cache")
    # cache missing too; corpus missing — guaranteed failure
    with mock.patch("preflight.requests.get") as m:
        m.return_value.status_code = 200
        code = preflight.main()
    assert code == 1
    out = capsys.readouterr().out
    assert "USER ACTION REQUIRED" in out


def test_main_exits_0_when_all_checks_pass(tmp_path, monkeypatch):
    corpus = tmp_path / "cardiology-nme-corpus.json"
    corpus.write_text('[{"drug_inn": "x"}]', encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(preflight, "CORPUS_PATH", corpus)
    monkeypatch.setattr(preflight, "CACHE_DIR", cache)
    with mock.patch("preflight.requests.get") as m:
        m.return_value.status_code = 200
        code = preflight.main()
    assert code == 0
