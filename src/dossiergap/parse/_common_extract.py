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

# Disposition-table anchors. When narrative "N subjects randomized" is absent,
# the real trial N may live in a disposition table row such as
# "Subjects in population 2,526 2,524 5,050" (arm1 arm2 total). The anchor
# matches the leading label; the number extraction takes the MAXIMUM of all
# numbers in the next 100 chars (total > individual arm counts).
N_DISPOSITION_RE = re.compile(
    r"(?:Subjects\s+in\s+(?:population|study|(?:the\s+)?analysis)"
    r"|Analysis\s+set"
    r"|FAS\b"
    r"|ITT(?:\s+population)?"
    r"|Intention[\s-]to[\s-]treat"
    r"|Total\s+(?:enrolled|randomi[sz]ed|analy[sz]ed)"
    r"|Full\s+analysis\s+set"
    r"|Per\s+protocol\s+population)",
    re.IGNORECASE,
)

# Disposition-fallback uses COMMA-FORMATTED numbers only. Chart axis labels
# in pdfplumber-extracted PDFs are almost always bare integers ("5000",
# "15000"); table counts for trial arms are almost always comma-formatted
# ("5,050", "2,526"). This filter rejects an observed false-positive where
# chart tick labels "0 2500 5000 7500 10000 12500 15000" were being picked
# up as N=15000 in the Verquvo VICTORIA EPAR p.84.
_COMMA_NUMBER_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})+)\b")


def _extract_n_from_disposition_table(pages: dict[int, str]) -> tuple[int, int] | None:
    """Fallback N extractor: look for disposition-table anchors and return
    the MAX comma-formatted number within 100 chars (total > arm counts).
    Bare integers are rejected as probable chart axis labels."""
    best: tuple[int, int] | None = None
    for pnum in sorted(pages):
        text = pages[pnum]
        for m in N_DISPOSITION_RE.finditer(text):
            window_start = m.start()
            window_end = min(len(text), m.end() + 100)
            window = text[window_start:window_end]
            for nm in _COMMA_NUMBER_RE.finditer(window):
                n = int(nm.group(1).replace(",", ""))
                # Trial sizes typically 100-100000; reject out-of-range noise.
                if not (100 <= n <= 100000):
                    continue
                if best is None or n > best[0]:
                    best = (n, pnum)
    return best


def extract_n_randomized(pages: dict[int, str]) -> tuple[int, int]:
    """Find the first plausible N randomized (>= 100), skipping negated matches.

    Primary: narrative 'N subjects randomized' (Phase 1 regex).
    Fallback (Phase 2): disposition-table anchors like 'Subjects in population
    2,526 2,524 5,050' — takes the MAX of numbers near the anchor so the
    total is preferred over individual arm counts.

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

    # Phase 2 disposition-table fallback.
    disposition = _extract_n_from_disposition_table(pages)
    if disposition is not None:
        return disposition

    raise ExtractionError(
        "could not extract N randomized: no match for narrative pattern "
        "'(\\d+) (subjects|patients|participants) (were )?randomized' or "
        "'randomized (\\d+) (subjects|patients|participants)' with N >= 100, "
        "and no disposition-table anchor (Subjects in population / Analysis "
        "set / FAS / ITT / Total randomized / Full analysis set) yielded a "
        "valid N. Negated matches like 'Not Randomized N' are deliberately "
        "skipped."
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
