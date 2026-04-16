"""Task 18 — URL-discovery tests. Mocks HEAD requests; no network."""
from __future__ import annotations

from unittest import mock

import pytest

from dossiergap.download.url_discovery import (
    DiscoveredURL,
    discover_ema_epar_url,
    discover_fda_medical_review_url,
    discover_fda_supplement_url,
)


def _fake_head(response_map: dict[str, int]):
    def head(url, timeout=15):
        return response_map.get(url, 404)
    return head


def test_fda_first_pattern_matches():
    response_map = {
        "https://www.accessdata.fda.gov/drugsatfda_docs/nda/2015/207620Orig1s000MedR.pdf": 200,
    }
    r = discover_fda_medical_review_url("207620", 2015, head=_fake_head(response_map))
    assert r is not None
    assert r.pattern_matched == "Orig1s000MedR"


def test_fda_falls_through_to_otherr():
    response_map = {
        "https://www.accessdata.fda.gov/drugsatfda_docs/nda/2021/214377Orig1s000OtherR.pdf": 200,
    }
    r = discover_fda_medical_review_url("214377", 2021, head=_fake_head(response_map))
    assert r is not None
    assert r.pattern_matched == "Orig1s000OtherR"


def test_fda_bla_fallback():
    response_map = {
        "https://www.accessdata.fda.gov/drugsatfda_docs/bla/2015/125559Orig1s000MedR.pdf": 200,
    }
    r = discover_fda_medical_review_url(
        "125559", 2015, application_type="bla", head=_fake_head(response_map),
    )
    assert r is not None
    assert "MedR" in r.pattern_matched


def test_fda_type_swap_when_guessed_wrong():
    """If caller passes NDA but the app is actually a BLA, patterns should still find it."""
    response_map = {
        "https://www.accessdata.fda.gov/drugsatfda_docs/bla/2015/125559Orig1s000MedR.pdf": 200,
    }
    r = discover_fda_medical_review_url(
        "125559", 2015, application_type="nda", head=_fake_head(response_map),
    )
    assert r is not None


def test_fda_returns_none_when_no_pattern_matches():
    r = discover_fda_medical_review_url("999999", 2099, head=_fake_head({}))
    assert r is None


def test_fda_supplement_discovery():
    response_map = {
        "https://www.accessdata.fda.gov/drugsatfda_docs/nda/2020/202293Orig1s015MedR.pdf": 200,
    }
    r = discover_fda_supplement_url(
        "202293", 2020, supplement_range=range(10, 20), head=_fake_head(response_map),
    )
    assert r is not None
    assert "s015" in r.pattern_matched


def test_ema_primary_slug_matches():
    response_map = {
        "https://www.ema.europa.eu/en/documents/assessment-report/entresto-epar-public-assessment-report_en.pdf": 200,
    }
    r = discover_ema_epar_url("Entresto", head=_fake_head(response_map))
    assert r is not None
    assert "entresto" in r.pattern_matched


def test_ema_alternative_slugs_tried():
    """Nexletol US is Nilemdo in EMA — alternative slug must be tried."""
    response_map = {
        "https://www.ema.europa.eu/en/documents/assessment-report/nilemdo-epar-public-assessment-report_en.pdf": 200,
    }
    r = discover_ema_epar_url(
        "Nexletol",
        alternative_slugs=["Nilemdo"],
        head=_fake_head(response_map),
    )
    assert r is not None
    assert "nilemdo" in r.pattern_matched


def test_ema_strips_parenthetical_indication():
    """Brand 'Farxiga (HFrEF indication)' should slug to 'farxiga', not the full phrase."""
    response_map = {
        "https://www.ema.europa.eu/en/documents/assessment-report/farxiga-epar-public-assessment-report_en.pdf": 200,
    }
    r = discover_ema_epar_url("Farxiga (HFrEF indication)", head=_fake_head(response_map))
    assert r is not None


def test_ema_returns_none_when_nothing_matches():
    r = discover_ema_epar_url("NonexistentDrug", head=_fake_head({}))
    assert r is None
