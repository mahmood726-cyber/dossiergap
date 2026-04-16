"""URL discovery for FDA Drugs@FDA Medical Reviews and EMA EPAR documents.

Pattern-cycling approach: try a list of known URL templates for each
source, HEAD-request each, return the first 200. No HTML scraping yet
— that's a future refinement. This helper exists so the corpus doesn't
need every URL hand-seeded.

Known limits of the pattern approach:
  - FDA BLAs with non-standard reviewer pathways (integrated-review
    sponsor-submitted format) are not covered.
  - FDA sNDAs have variable supplement numbers (Orig1s001,
    Orig1s015, etc.) — the simple patterns here cover only s000.
  - EMA procedures whose brand slug differs from the US brand name
    need manual mapping (e.g. 'Nilemdo' EMA vs 'Nexletol' US).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import quote

import requests

FDA_DOCS_BASE = "https://www.accessdata.fda.gov/drugsatfda_docs"
EMA_DOCS_BASE = "https://www.ema.europa.eu/en/documents/assessment-report"

# Per-request pause to avoid rate limits (EMA returns 429 under sustained load).
_REQUEST_DELAY_S = 0.5


@dataclass
class DiscoveredURL:
    url: str
    status_code: int
    pattern_matched: str


def _head(url: str, timeout: int = 15) -> int:
    """HEAD request with small delay to be polite to servers."""
    time.sleep(_REQUEST_DELAY_S)
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        return resp.status_code
    except requests.RequestException:
        return 0


def discover_fda_medical_review_url(
    application_number: str,
    approval_year: int,
    application_type: str = "nda",
    *,
    head: callable = _head,
) -> DiscoveredURL | None:
    """Cycle through known FDA Medical Review URL patterns.

    Returns the first URL that HEAD-requests to 200. Returns None if none match.
    """
    app_type = application_type.lower()
    # Patterns in priority order. MedR is the classic 2010-2019 template;
    # OtherR and MultidisciplineR are 2020+ integrated-review names.
    patterns = [
        (f"{FDA_DOCS_BASE}/{app_type}/{approval_year}/{application_number}Orig1s000MedR.pdf", "Orig1s000MedR"),
        (f"{FDA_DOCS_BASE}/{app_type}/{approval_year}/{application_number}Orig1s000OtherR.pdf", "Orig1s000OtherR"),
        (f"{FDA_DOCS_BASE}/{app_type}/{approval_year}/{application_number}Orig1s000MultidisciplineR.pdf", "Orig1s000MultidisciplineR"),
        (f"{FDA_DOCS_BASE}/{app_type}/{approval_year}/{application_number}Orig1s000SumR.pdf", "Orig1s000SumR"),
    ]
    # If application_type was guessed wrong, try the other.
    other_type = "bla" if app_type == "nda" else "nda"
    patterns.extend([
        (f"{FDA_DOCS_BASE}/{other_type}/{approval_year}/{application_number}Orig1s000MedR.pdf", f"{other_type}-MedR"),
        (f"{FDA_DOCS_BASE}/{other_type}/{approval_year}/{application_number}Orig1s000OtherR.pdf", f"{other_type}-OtherR"),
    ])

    for url, label in patterns:
        code = head(url)
        if code == 200:
            return DiscoveredURL(url=url, status_code=200, pattern_matched=label)
    return None


def discover_fda_supplement_url(
    application_number: str,
    approval_year: int,
    application_type: str = "nda",
    supplement_range: range | None = None,
    *,
    head: callable = _head,
) -> DiscoveredURL | None:
    """For sNDAs, iterate through supplement numbers s001..s030 looking for
    a published MedR/OtherR.

    This is expensive (up to 30 HEAD requests per call) so it's a separate
    function only invoked when the main `discover_fda_medical_review_url`
    returns None and the caller knows the application is a supplement.
    """
    app_type = application_type.lower()
    supplement_range = supplement_range or range(1, 31)
    suffixes = ("MedR", "OtherR", "MultidisciplineR")
    for s_num in supplement_range:
        s_str = f"s{s_num:03d}"
        for suffix in suffixes:
            url = f"{FDA_DOCS_BASE}/{app_type}/{approval_year}/{application_number}Orig1{s_str}{suffix}.pdf"
            code = head(url)
            if code == 200:
                return DiscoveredURL(
                    url=url,
                    status_code=200,
                    pattern_matched=f"Orig1{s_str}{suffix}",
                )
    return None


def _slugify_brand(brand_name: str) -> str:
    """Convert 'Entresto' -> 'entresto'; strip parenthetical indication notes."""
    base = brand_name.split("(")[0].strip()
    return base.lower().replace(" ", "-").replace("/", "-")


FDA_OVERVIEW_TMPL = (
    "https://www.accessdata.fda.gov/scripts/cder/daf/"
    "index.cfm?event=overview.process&ApplNo={app_num}"
)

_REVIEW_SUFFIX_RE = re.compile(
    r"/(?:drugsatfda_docs)/(?:nda|bla)/(\d{4})/"
    r"(?P<app>\d+)Orig\d+s(?P<supp>\d{3})"
    r"(?P<suffix>SumR|MedR|OtherR|MultidisciplineR)?\.pdf",
    re.IGNORECASE,
)


def discover_fda_supplement_url_via_scrape(
    application_number: str,
    approval_year: int | None = None,
    *,
    fetch: callable = None,
    head: callable = _head,
) -> list[DiscoveredURL]:
    """Scrape the Drugs@FDA overview page for all supplement review PDFs.

    sNDA supplement numbers vary per approval and don't follow the
    predictable ``Orig1s000`` pattern used by original NDAs. This helper
    HTTP-GETs the overview page, extracts all PDF links that match a
    review-filename shape, and returns them ordered by supplement
    number. Caller filters by year/supplement to pick the right one.
    """
    import requests as _requests
    fetch = fetch or (lambda url: _requests.get(
        url, timeout=30,
        headers={"User-Agent": "DossierGap URL discovery"},
    ))
    url = FDA_OVERVIEW_TMPL.format(app_num=application_number)
    resp = fetch(url)
    if getattr(resp, "status_code", 0) != 200:
        return []
    html = resp.text
    results: list[DiscoveredURL] = []
    seen: set[str] = set()
    for m in _REVIEW_SUFFIX_RE.finditer(html):
        candidate = m.group(0)
        if candidate in seen:
            continue
        seen.add(candidate)
        supp_num = int(m.group("supp"))
        suffix = m.group("suffix") or "bare"
        # Prepend protocol if the href was relative
        if not candidate.startswith("http"):
            candidate = "https://www.accessdata.fda.gov" + candidate
        results.append(DiscoveredURL(
            url=candidate,
            status_code=200,
            pattern_matched=f"s{supp_num:03d}/{suffix}",
        ))
    return results


def discover_ema_epar_url(
    brand_name: str,
    *,
    alternative_slugs: list[str] | None = None,
    head: callable = _head,
) -> DiscoveredURL | None:
    """Try the EMA EPAR URL pattern using the brand name as slug.

    ``alternative_slugs`` lets the caller pass other known names when the US
    brand differs from the EMA brand (e.g. Nexletol US / Nilemdo EMA).
    """
    slugs = [_slugify_brand(brand_name)]
    if alternative_slugs:
        slugs.extend(s.lower() for s in alternative_slugs)

    for slug in slugs:
        url = f"{EMA_DOCS_BASE}/{quote(slug)}-epar-public-assessment-report_en.pdf"
        code = head(url)
        if code == 200:
            return DiscoveredURL(
                url=url,
                status_code=200,
                pattern_matched=f"epar-public-assessment/{slug}",
            )
    return None
