"""DossierGap Task 0 — prereq gate.

Fails closed with exit code 1 and a specific user-action list if any
required condition is missing. Called directly or via `python -m`.

All checks are pure (`-> tuple[bool, str]`) so they can be unit-tested
without hitting the network or filesystem.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPO_ROOT / "data" / "cardiology-nme-corpus.json"
CACHE_DIR = REPO_ROOT / "cache"

FDA_URL = "https://www.accessdata.fda.gov/scripts/cder/daf/"
EMA_URL = "https://www.ema.europa.eu/en/medicines/"

CORPUS_TEMPLATE = """[
  {
    "drug_inn": "sacubitril/valsartan",
    "brand_us": "Entresto",
    "fda_application_number": "207620",
    "fda_approval_date": "2015-07-07",
    "ema_procedure_number": "EMEA/H/C/004062",
    "ema_approval_date": "2015-11-19",
    "cv_indication": "HFrEF",
    "notes": ""
  }
]
"""


def check_python_version(min_major: int = 3, min_minor: int = 13) -> tuple[bool, str]:
    cur = sys.version_info
    if (cur.major, cur.minor) >= (min_major, min_minor):
        return True, f"Python {cur.major}.{cur.minor}.{cur.micro}"
    return False, (
        f"Need Python >= {min_major}.{min_minor}, "
        f"have {cur.major}.{cur.minor}.{cur.micro}"
    )


def check_import(module_name: str) -> tuple[bool, str]:
    try:
        mod = importlib.import_module(module_name)
    except ImportError as e:
        return False, f"{module_name}: {e}. Install with `pip install {module_name}`"
    version = getattr(mod, "__version__", "unknown")
    return True, f"{module_name} {version}"


def check_url(url: str, timeout: int = 10) -> tuple[bool, str]:
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
    except Exception as e:
        return False, f"{url}: {e}"
    if resp.status_code != 200:
        return False, f"{url} returned HTTP {resp.status_code}"
    return True, f"{url} -> 200"


def check_file_exists(path: Path) -> tuple[bool, str]:
    if path.is_file():
        return True, f"{path.name} present"
    return False, f"{path} missing"


def check_writable(path: Path) -> tuple[bool, str]:
    if not path.is_dir():
        return False, f"{path} is not a directory (create it first)"
    try:
        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            pass
    except OSError as e:
        return False, f"{path} not writable: {e}"
    return True, f"{path} writable"


def check_corpus(corpus_path: Path) -> tuple[bool, str]:
    if not corpus_path.exists():
        return False, (
            f"CREATE THIS FILE at {corpus_path}\n"
            f"  Template:\n{CORPUS_TEMPLATE}"
            f"  See docs/corpus-criteria.md for inclusion rules."
        )
    try:
        data = json.loads(corpus_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"{corpus_path}: invalid JSON — {e}"
    if not isinstance(data, list) or len(data) == 0:
        return False, f"{corpus_path}: expected non-empty JSON array"
    return True, f"{corpus_path.name}: {len(data)} NMEs"


def main() -> int:
    checks = [
        ("Python >= 3.13",           check_python_version),
        ("pdfplumber importable",    lambda: check_import("pdfplumber")),
        ("requests importable",      lambda: check_import("requests")),
        ("pydantic importable",      lambda: check_import("pydantic")),
        ("FDA Drugs@FDA reachable",  lambda: check_url(FDA_URL)),
        ("EMA reachable",            lambda: check_url(EMA_URL)),
        ("Cache dir writable",       lambda: check_writable(CACHE_DIR)),
        ("Cardiology NME corpus",    lambda: check_corpus(CORPUS_PATH)),
    ]

    print("DossierGap preflight — Task 0 prereq gate")
    print("-" * 60)

    failures: list[tuple[str, str]] = []
    for name, fn in checks:
        ok, msg = fn()
        marker = "OK  " if ok else "FAIL"
        print(f"[{marker}] {name}: {msg}")
        if not ok:
            failures.append((name, msg))

    print("-" * 60)
    if failures:
        print("USER ACTION REQUIRED — fix the following before running Task 1+:")
        for name, msg in failures:
            print(f"  * {name}")
            for line in msg.splitlines():
                print(f"      {line}")
        return 1

    print("All prereqs satisfied. Task 1 (scaffold) cleared to run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
