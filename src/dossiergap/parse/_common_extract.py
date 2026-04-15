"""Shared pure-text extractors used by both FDA (``fda_trials``) and EMA
(``ema_trials``) per-trial parsers.

Only the HR + 95% CI extractor differs between sources (FDA writes
narrative 'HR X; 95% CI Y, Z'; EMA mixes that with a table format
'Hazard ratio X | 95%-CI Y, Z'), so those live in the per-source modules.
Trial name, N randomized, NCT id, primary outcome, phase, and strict-
pivotal detection are source-agnostic and live here.
"""
from __future__ import annotations

import re
from collections import Counter


class ExtractionError(RuntimeError):
    pass


NCT_RE = re.compile(r"NCT\d{8}")

N_RANDOMIZED_RE = re.compile(
    r"(?:"
    r"(?P<n_before>\d{1,3}(?:,\d{3})+|\d{3,6})\s+(?:subjects|patients|participants)"
    r"\s+(?:were\s+)?(?:randomi[sz]ed|enrolled)"
    r"|"
    r"(?:randomi[sz]ed|enrolled)\s+"
    r"(?P<n_after>\d{1,3}(?:,\d{3})+|\d{3,6})\s+(?:subjects|patients|participants)"
    r")",
    re.IGNORECASE,
)

PRIMARY_OUTCOME_RE = re.compile(
    r"(?:The\s+)?primary\s+(?:composite\s+)?endpoint\s+was\s+"
    r"(?:a\s+composite\s+of\s+)?"
    r"([^.]{10,200}?)\s*(?:\.|,\s+an\s+endpoint)",
    re.IGNORECASE,
)

ACRONYM_RE = re.compile(r"\b([A-Z]{4,20}(?:-[A-Za-z0-9]{1,10})?)\b")

ACRONYM_STOPWORDS = {
    "NCT", "FDA", "EMA", "MEDR", "NDA", "BLA", "EPAR", "CHMP",
    "LCZ", "ACEI", "ARB", "ARNI", "SGLT", "GLP",
    "HFREF", "HFPEF", "HFMREF", "NYHA", "LVEF", "KCCQ",
    "ICD", "CRT", "MI", "MACE", "CV", "CABG", "PCI",
    "SOLVD", "CONSENSUS",
    "PHASE",
}

PHASE_RE = re.compile(r"\bPhase\s+(2/3|3b|[234])\b", re.IGNORECASE)

PIVOTAL_WINDOW = 200


def find_all(pattern: re.Pattern[str], pages: dict[int, str]) -> list[tuple[int, re.Match[str]]]:
    hits: list[tuple[int, re.Match[str]]] = []
    for pnum in sorted(pages):
        for m in pattern.finditer(pages[pnum]):
            hits.append((pnum, m))
    return hits


def extract_trial_name(pages: dict[int, str]) -> tuple[str, int]:
    counts: Counter[str] = Counter()
    first_page: dict[str, int] = {}
    for pnum in sorted(pages):
        for m in ACRONYM_RE.finditer(pages[pnum]):
            token = m.group(1)
            base = token.split("-")[0].upper()
            if base in ACRONYM_STOPWORDS:
                continue
            if len(base) < 4:
                continue
            counts[token] += 1
            first_page.setdefault(token, pnum)
    if not counts:
        raise ExtractionError(
            "could not extract trial name: no acronym candidates found "
            "(try adding the trial's acronym to the stopword exemption list)"
        )
    name, _n = counts.most_common(1)[0]
    return name, first_page[name]


_NEGATION_PREFIX_RE = re.compile(r"\b(?:not|non|never)[\s-]+$", re.IGNORECASE)


def extract_n_randomized(pages: dict[int, str]) -> tuple[int, int]:
    """Find the first plausible N randomized (>= 100), skipping negated matches.

    FDA/EMA tables sometimes include a 'Not Randomized' row listing the count
    of subjects excluded from randomisation — e.g. Verquvo VICTORIA EPAR
    reports 'Not Randomized 1,807' immediately before 'Subjects in population
    ... 5,050'. Matches preceded by 'not'/'non'/'never' within 30 chars are
    skipped to avoid extracting the wrong count.
    """
    hits = find_all(N_RANDOMIZED_RE, pages)
    for pnum, m in hits:
        prefix = pages[pnum][max(0, m.start() - 30):m.start()]
        if _NEGATION_PREFIX_RE.search(prefix):
            continue
        n_str = m.group("n_before") or m.group("n_after")
        n = int(n_str.replace(",", ""))
        if n >= 100:
            return n, pnum
    raise ExtractionError(
        "could not extract N randomized: no match for pattern "
        "'(\\d+) (subjects|patients|participants) (were )?randomized' or "
        "'randomized (\\d+) (subjects|patients|participants)' with N >= 100 "
        "(negated matches like 'Not Randomized N' are deliberately skipped)"
    )


def extract_primary_outcome(pages: dict[int, str]) -> tuple[str, int]:
    hits = find_all(PRIMARY_OUTCOME_RE, pages)
    if not hits:
        raise ExtractionError(
            "could not extract primary outcome/endpoint: no match for "
            "'(The )?primary (composite )?endpoint was <text>' pattern"
        )
    pnum, m = min(hits, key=lambda h: len(h[1].group(1)))
    text = " ".join(m.group(1).split())
    return text, pnum


def extract_phase(pages: dict[int, str]) -> str:
    for pnum in sorted(pages):
        m = PHASE_RE.search(pages[pnum])
        if m:
            phase = m.group(1)
            if phase in ("2", "2/3", "3", "3b", "4"):
                return phase
    return "3"


def extract_nct(pages: dict[int, str]) -> str | None:
    hits = find_all(NCT_RE, pages)
    return hits[0][1].group(0) if hits else None


def is_strict_pivotal(pages: dict[int, str], trial_name: str) -> bool:
    for pnum in sorted(pages):
        text = pages[pnum]
        for m in re.finditer(re.escape(trial_name), text):
            start = max(0, m.start() - PIVOTAL_WINDOW)
            end = min(len(text), m.end() + PIVOTAL_WINDOW)
            if re.search(r"\bpivotal\b", text[start:end], re.IGNORECASE):
                return True
    return False
