"""Semantic scoring of primary-outcome text candidates (Task 16 completion).

Mirrors the HR-candidate scoring pattern (methods-paper §4.3) but applied
to the PRIMARY-OUTCOME text extraction. Unlike HR candidates — where the
subject precedes the number — outcome text IS the subject, so clinical-
endpoint words should appear INSIDE the captured text and method/procedure
words indicate the regex captured a method-description sentence instead.

Task 16's earliest-across-all-patterns experiment regressed Uptravi to
'...performed on the Full Analysis Set...'. Shortest-within-canonical was
committed as a partial fallback. This file drives the semantic-scoring
completion per the Task 16 commit message proposal:
  'prefer matches containing death/mortality/hospitalization over
   matches containing performed/analyzed/based on'
"""
from __future__ import annotations

import pytest

from dossiergap.parse._common_extract import (
    extract_primary_outcome,
    rank_outcome_candidates,
    score_outcome_candidate,
)


# -- pure-function tests ---------------------------------------------------

def test_outcome_scoring_rewards_primary_keyword_proximity():
    text = (
        "The primary endpoint was time to cardiovascular death or "
        "hospitalisation for heart failure. Secondary endpoints included..."
    )
    captured = "time to cardiovascular death or hospitalisation for heart failure"
    start = text.find(captured)
    end = start + len(captured)
    score = score_outcome_candidate(text, start, end, captured)
    # primary bonus (+500) + clinical words (death, hospitali) inside capture
    assert score > 500


def test_outcome_scoring_penalises_method_text():
    text = (
        "The primary efficacy analysis was performed on the Full Analysis "
        "Set using a stratified log-rank test."
    )
    captured = "performed on the Full Analysis Set using a stratified log-rank test"
    start = text.find(captured)
    end = start + len(captured)
    score = score_outcome_candidate(text, start, end, captured)
    # Method words inside capture (performed, full analysis set) — net negative.
    assert score < 0


def test_outcome_scoring_rewards_clinical_endpoint_words_inside_capture():
    captured = (
        "time to composite of cardiovascular death or hospitalisation "
        "for heart failure"
    )
    text = f"Primary endpoint was {captured}."
    start = text.find(captured)
    end = start + len(captured)
    score = score_outcome_candidate(text, start, end, captured)
    # primary +500, composite +100, death +100, hospitali +100 = 800 floor
    assert score >= 800


def test_outcome_scoring_no_primary_no_clinical_returns_zero():
    captured = "change from baseline in systolic blood pressure"
    text = f"One of the exploratory outcomes was {captured}."
    start = text.find(captured)
    end = start + len(captured)
    score = score_outcome_candidate(text, start, end, captured)
    # No primary keyword in preceding 100 chars, no clinical words inside,
    # no method words → 0.
    assert score == 0


def test_outcome_scoring_method_words_beat_single_clinical_word():
    """A method-description sentence that happens to mention 'death' once
    in passing should NOT win over a clean clinical-endpoint definition."""
    captured = (
        "analysis was performed on the Full Analysis Set based on "
        "death events"
    )
    text = f"The primary endpoint was {captured}."
    start = text.find(captured)
    end = start + len(captured)
    score = score_outcome_candidate(text, start, end, captured)
    # primary +500, death +100 = +600, minus method penalties (performed,
    # full analysis set, based on) = -600 → net = 0, NOT a clean winner.
    assert score < 500  # should not beat a real clinical endpoint


# -- ranker tests ----------------------------------------------------------

def test_rank_outcome_candidates_picks_clinical_over_method():
    pages = {
        1: (
            "The primary endpoint was performed on the Full Analysis Set "
            "using a stratified log-rank test."
        ),
        2: (
            "The primary endpoint was time to composite of cardiovascular "
            "death or hospitalisation for heart failure."
        ),
    }
    # Simulate all canonical hits from both pages
    import re
    from dossiergap.parse._common_extract import PRIMARY_OUTCOME_RE
    hits = []
    for pnum in sorted(pages):
        for m in PRIMARY_OUTCOME_RE.finditer(pages[pnum]):
            hits.append((pnum, m))
    assert len(hits) >= 2, "test setup: need hits on both pages"
    ranked = rank_outcome_candidates(hits, pages)
    top_pnum = ranked[0][0]
    top_text = ranked[0][1].group(1)
    assert top_pnum == 2
    assert "cardiovascular death" in top_text.lower() or "hospitalisation" in top_text.lower()


def test_rank_outcome_candidates_stable_on_ties():
    """Equal-score candidates preserve input order (Phase 1 first-in-text)."""
    pages = {
        1: "The primary endpoint was event A occurring first in the trial.",
        2: "The primary endpoint was event B occurring later during follow-up.",
    }
    import re
    from dossiergap.parse._common_extract import PRIMARY_OUTCOME_RE
    hits = []
    for pnum in sorted(pages):
        for m in PRIMARY_OUTCOME_RE.finditer(pages[pnum]):
            hits.append((pnum, m))
    ranked = rank_outcome_candidates(hits, pages)
    # Neither has clinical/method markers → scores equal → stable sort → p.1 first
    assert ranked[0][0] == 1


# -- integration via extract_primary_outcome -------------------------------

def test_extract_primary_outcome_picks_clinical_over_shortest_method():
    """Regression for the Uptravi-style failure mode: method-description
    text is SHORTER but semantically wrong; clinical-endpoint text is longer
    but correct. Shortest-within-canonical would pick the wrong one; semantic
    scoring picks the right one.
    """
    pages = {
        1: "The primary endpoint was performed on the analysis set.",
        2: (
            "The primary endpoint was time to composite of cardiovascular "
            "death or hospitalisation for heart failure."
        ),
    }
    text, pnum = extract_primary_outcome(pages)
    # Must NOT return the method-description (the shorter match).
    assert "performed" not in text.lower()
    assert "cardiovascular death" in text.lower() or "hospitalisation" in text.lower()
    assert pnum == 2


def test_extract_primary_outcome_prefers_primary_context_over_raw_clinical():
    """When a non-primary sentence mentions clinical words and the primary
    sentence doesn't carry them directly, the primary-anchored match still
    wins because of the primary-keyword proximity bonus."""
    pages = {
        1: (
            "The primary endpoint was change from baseline in the Kansas "
            "City Cardiomyopathy Questionnaire score."
        ),
        2: (
            "Subgroup analysis of cardiovascular death and hospitalisation "
            "was performed separately."
        ),
    }
    text, pnum = extract_primary_outcome(pages)
    # The canonical 'was X' pattern only hits p.1; p.2 has no canonical hit.
    # So extraction picks p.1 by pattern, scoring is moot but must not regress.
    assert pnum == 1
    assert "Kansas City" in text or "KCCQ" in text or "baseline" in text.lower()


def test_extract_primary_outcome_unchanged_when_single_candidate():
    """Single canonical match → return it regardless of score (backward
    compatibility with Phase 1 extraction on clean PDFs like Entresto)."""
    pages = {
        1: (
            "Results. The primary endpoint was time to first occurrence of "
            "death from cardiovascular causes or hospitalisation for heart "
            "failure. After a median follow-up of 27 months..."
        ),
    }
    text, pnum = extract_primary_outcome(pages)
    assert pnum == 1
    assert "death" in text.lower()
    assert "hospitali" in text.lower()
