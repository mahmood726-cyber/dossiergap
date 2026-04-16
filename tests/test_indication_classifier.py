"""Phase 5 — FDA appletter indication-classifier tests."""
from __future__ import annotations

from dossiergap.download.url_discovery import classify_letter_indication


def test_hfref_nyha_phrase():
    # Farxiga s020 DAPA-HF approval letter
    text = (
        "for the use of FARXIGA to reduce the risk of cardiovascular death "
        "and hospitalization for heart failure in adults with heart failure "
        "(NYHA class II-IV) with reduced ejection fraction."
    )
    assert classify_letter_indication(text) == "HFrEF"


def test_hfpef_preserved_phrase():
    text = "indication for preserved ejection fraction heart failure"
    assert classify_letter_indication(text) == "HFpEF"


def test_attr_cm_phrase():
    text = "for the treatment of transthyretin amyloid cardiomyopathy"
    assert classify_letter_indication(text) == "ATTR-CM"


def test_hcm_phrase():
    text = "for symptomatic obstructive hypertrophic cardiomyopathy"
    assert classify_letter_indication(text) == "Obstructive HCM"


def test_no_match_returns_none():
    text = "approval of a label update for medication guide revisions"
    assert classify_letter_indication(text) is None


def test_case_insensitive():
    text = "REDUCED EJECTION FRACTION indication approved"
    assert classify_letter_indication(text) == "HFrEF"
