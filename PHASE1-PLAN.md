# DossierGap — Phase 1 Implementation Plan

**Status**: LOCKED 2026-04-15. Decisions committed to `docs/corpus-criteria.md` and `docs/pivotal-criterion.md`. Ready to execute Task 0.
**Created**: 2026-04-15
**Phase 1 deliverable**: Versioned `dossier_trials.v0.1.0.csv` containing FDA Drugs@FDA + EMA EPAR pivotal efficacy trials for cardiology NMEs approved 2015–2025, with passing extraction tests and ≤5% hand-audit drift.

---

## Scope

**In Phase 1**:
- Data acquisition: FDA Drugs@FDA Medical Review PDFs + EMA EPAR PDFs
- Trial extraction: structured `TrialRecord` per pivotal efficacy trial
- Cross-register deduplication (same trial in FDA + EMA)
- Versioned CSV output

**Deferred to Phase 2**: publication matching (NCT → protocol-feature fallback → ICTRP/EUCTR cross-check), `publication_status` column.

**Deferred to Phase 3**: Turner-style inflation analysis, dashboard, BMJ Analysis manuscript, E156.

---

## Static vs. Dynamic Hardcode Disclosure

| Component | Static (hardcoded) | Dynamic (runtime) |
|---|---|---|
| Cardiology NME list | Frozen JSON, 60–80 NMEs (user-curated, Task 2) | — |
| FDA / EMA URL bases | Hardcoded base URLs | Per-NME paths via app number / procedure number |
| PDF section anchors | Regex for "Studies to Support Efficacy", "§2.5.x", "Clinical Efficacy" | Actual section boundaries per PDF |
| Pivotal-trial criterion | Operational definition (user-contributed, Task 6) | Per-PDF application |
| Effect preference order | primary > label-claimed > first-listed | Per-trial extraction |
| Dedup NCT priority | NCT ID when present; else sponsor+INN+phase+N±5%+outcome | Per-pair comparison |

---

## Task 0 — Prereq Gate (blocks all downstream tasks)

**Why**: Per the 2026-04-14 Evidence-Forecast lesson, a plan that depends on external data must preflight that data before scaffolding. EF discovered missing prereqs at Task 17 of 19; we will not repeat that.

**Script**: `scripts/preflight.py`

**Checks** (all must pass; fails closed with exit 1 + user-action list):
1. `python --version` ≥ 3.13
2. `import pdfplumber` and `import requests` succeed
3. `GET https://www.accessdata.fda.gov/scripts/cder/daf/` returns 200 (FDA Drugs@FDA reachable)
4. `GET https://www.ema.europa.eu/en/medicines/` returns 200 (EMA reachable)
5. `data/cardiology-nme-corpus.json` exists and parses (on first run: prints template + "CREATE THIS FILE" with exit 1)
6. `cache/` is writable

**Tests**: `tests/test_preflight.py` — parametrised missing-prereq cases, each asserts exit-code-1 + specific stderr keyword.

---

## Task 1 — Project Scaffold

- `pyproject.toml` — deps: `pdfplumber`, `requests`, `pydantic`, `pytest`
- `src/dossiergap/__init__.py`, `tests/conftest.py`
- `.gitignore`: `PROGRESS.md`, `cache/`, `*.pdf`, `.venv`, `__pycache__`, `dossier_trials*.csv` (outputs version-controlled separately once stable)
- `README.md` stub — scope, Phase 1/2/3 status, link to this plan
- Move Task 0's `scripts/preflight.py` into repo

**Tests**: `tests/test_scaffold.py` — package imports; `.gitignore` excludes `PROGRESS.md`; `python -m dossiergap --help` returns 0.

---

## Task 2 — Cardiology NME Corpus **[USER CONTRIBUTION — 5–10 lines]**

**Why this matters**: The corpus defines the denominator for every downstream claim. A cardiologist's domain knowledge on inclusion (e.g., "do bridging-study-only approvals count?") is more valuable than my guesswork.

**What I will build**:
- Schema validator
- Seed file with 10 confident examples (Entresto, Farxiga CV, Verquvo, Inpefa, Camzyos, Leqvio, Nexletol, Vyndaqel, Corlanor, Tavneos)
- Template row + inclusion-criteria placeholder in `docs/corpus-criteria.md`

**What I will request from you**:
- Decide on inclusion scope: which CV sub-indications count? (HFrEF, HFpEF, ACS, hypertension, dyslipidemia, AF, PAD, pulm HTN, amyloidosis — yes/no each)
- Decide: include fixed-dose combinations with one new entity? Include repurposed drugs with new CV indications (e.g., SGLT2i for HF)? Exclude diagnostic/imaging agents?
- Extend the seed list to the full 2015–2025 cardiology NME set (~60–80 entries expected)

**File**: `data/cardiology-nme-corpus.json`. Schema:
```json
{"drug_inn": "...", "brand_us": "...", "fda_application_number": "...",
 "fda_approval_date": "YYYY-MM-DD", "ema_procedure_number": "...",
 "ema_approval_date": "YYYY-MM-DD", "cv_indication": "...", "notes": ""}
```

**Tests**: `tests/test_corpus.py` — JSON schema validates; ≥20 NMEs present; all dates parse; FDA/EMA IDs pattern-match.

---

## Task 3 — FDA Drugs@FDA Downloader

TDD with VCR-style fixture for NDA 207620 (sacubitril/valsartan).

- `src/dossiergap/download/fda.py::fetch_medical_review(application_number) -> Path`
- Cache: `cache/fda/{application_number}/medical_review.pdf`
- Retry with bounded exponential backoff on 429/502/503; fail closed on persistent 403 or Cloudflare HTML
- Preserve `.etag` / `.last-modified` for re-runs

**Tests**: fixture-backed fetch succeeds; Cloudflare HTML body raises; 429 triggers retry then succeeds; persistent 403 raises.

---

## Task 4 — EMA EPAR Downloader

Mirror of Task 3 for EMEA/H/C/004062 (Entresto EPAR).

- `src/dossiergap/download/ema.py::fetch_epar(procedure_number) -> Path`
- EMA hosts EPARs behind redirect chains — follow redirects, cache final PDF
- Cache: `cache/ema/{procedure_number}/epar.pdf`

**Tests**: fixture-backed fetch succeeds; redirect chain resolves; missing EPAR raises.

---

## Task 5 — TrialRecord Schema

Pydantic model with fields:
```
source: Literal["FDA", "EMA"]
dossier_id: str            # NDA/BLA number or EMA procedure number
drug_inn: str
sponsor: str
trial_phase: Literal["2", "2/3", "3", "3b", "4"]
nct_id: str | None
n_randomized: int
primary_outcome: str
effect_metric: Literal["HR", "RR", "OR", "MD", "SMD", "RD"]
effect_estimate: float
effect_ci_low: float
effect_ci_high: float
reported_in_label: bool
pivotal: bool
source_page_refs: list[int]
```

**Tests**: round-trip (model → CSV row → model) preserves all fields; missing required field raises `ValidationError`; invalid `effect_metric` raises.

---

## Task 6 — FDA Medical Review: Section Detection **[USER CONTRIBUTION — operational definition]**

**Why this matters**: The operational definition of "pivotal" drives the headline claim ("X% of pivotal trials unpublished"). Two defensible operationalisations:

| Option | Definition | Effect on denominator |
|---|---|---|
| **Strict** | Only trials the FDA reviewer explicitly labels "pivotal" | Smaller denominator, cleaner claim |
| **Inclusive** | All Phase 3 efficacy trials in "Studies to Support Efficacy" | Larger denominator, Turner et al. (2008) precedent |

**What I will build**: both filters, toggled by a `PIVOTAL_CRITERION` config value.

**What I will request from you**: pick one (or "both — report as sensitivity"), write a 1-paragraph rationale in `docs/pivotal-criterion.md`. The rationale commits us in peer review — write it now, not after the data is in.

**Implementation** (either way):
- `src/dossiergap/parse/fda_sections.py::find_efficacy_section(pdf_path) -> tuple[int, int]`
- Regex anchors: `"Efficacy Review"`, `"Studies to Support Efficacy"`, `"Clinical Efficacy"`, `"Pivotal Trial"`

**Tests**: 3-NME fixture (Entresto, Farxiga CV, Verquvo) — section boundaries match hand-audited ground truth ±1 page.

---

## Task 7 — FDA Medical Review: Per-Trial Extractor

- `src/dossiergap/parse/fda_trials.py::extract_trials(pdf_path, section_range, criterion) -> list[TrialRecord]`
- Extracts trial name, NCT (if present), design, N, primary outcome, effect + CI, label-claim flag
- Applies Task-6 `criterion` to flag `pivotal`
- Emits `source_page_refs` for audit

**Tests**: ≥1 trial per NME in 3-fixture set; effect estimates match hand-audit within ±0.01 on point estimate, exact CI bounds.

---

## Task 8 — EMA EPAR: Section Detection

Mirror of Task 6 for EPAR §2.5 (Clinical Efficacy). Regex anchors include `"2.5."`, `"Clinical Efficacy"`, `"Main Studies"`.

**Tests**: 3-EPAR fixture; section boundaries match ground truth ±1 page.

---

## Task 9 — EMA EPAR: Per-Trial Extractor

Mirror of Task 7.

**Tests**: ≥1 trial per EPAR in 3-fixture set; effect estimates match hand-audit.

---

## Task 10 — Cross-Register Deduplication

Same trial (e.g., PARADIGM-HF) appears in FDA Medical Review AND EMA EPAR. Dedup:
1. **Primary key**: NCT ID if both records have one and they match
2. **Fallback key**: `(sponsor, drug_inn, trial_phase, n_randomized ±5%, primary_outcome_normalised)`
3. **Merge policy**: union `source_page_refs`, keep both `source` tags, flag field conflicts in new `dedup_conflicts` column

**Tests**: PARADIGM-HF, DAPA-HF, VICTORIA dedupe to one record each; three deliberately-distinct trials do not merge.

---

## Task 11 — CSV Writer + Schema Validation

- `src/dossiergap/io/csv_writer.py::write_csv(records, out_path, version_tag)`
- Frozen column order (matches `TrialRecord` field order)
- Version tag in filename (`dossier_trials.v0.1.0.csv`) AND in header comment row
- Fail-closed on schema violation — no silent drops, no "unknown" sentinels

**Tests**: round-trip write → re-read with Task 5 schema yields identical records; invalid record raises `ValidationError`.

---

## Task 12 — CLI End-to-End

`python -m dossiergap extract --corpus data/cardiology-nme-corpus.json --out dossier_trials.csv --limit 3`

- `--limit N` for smoke-test; no limit for full run
- Progress per-NME to stderr
- Exit 1 on any per-NME extraction failure unless `--continue-on-error`

**Tests**: 3-NME smoke test produces valid CSV, ≥1 row per NME, exit 0.

---

## Task 13 — Contract Test: No Silent Failure

Per 2026-04-14 MetaReproducer lesson — silent failure sentinels are the enemy.

**Test** (`tests/test_no_silent_failure.py`):
- Run Task 12 CLI on 3-NME smoke corpus
- Assert output CSV has **no** rows with `n_randomized == 0`, `primary_outcome == ""`, or `effect_estimate == None`
- Assert output CSV has **no** `"unknown"` string sentinels in any field
- Assert per-NME row count ≥ 1

---

## Task 14 — Full-Corpus Extraction + 10% Hand Audit

- Run Task 12 on full corpus (no `--limit`)
- Sample 10% of extracted trials uniformly at random (seeded)
- Hand-audit sample against PDF ground truth
- Record drift rate per field (N, effect, CI, outcome, NCT)
- Output `extraction_audit.md`

**Phase 1 ship criterion**: ≤5% drift rate on hand-audit sample across all fields. Drift >5% → log blockers to `STUCK_FAILURES.md`, do not promote Phase 1.

---

## Execution Discipline

- **TDD**: Each task writes tests first, then implementation.
- **Retry cap**: 3 fix attempts per failing test → log to `STUCK_FAILURES.md` and stop.
- **Full-suite rerun cap**: 5 per phase.
- **Commit per task**, not at phase end. Self-trigger: "moving from Task N to Task N+1" → commit Task N first.
- **PROGRESS.md** updated on every usage-limit interruption; gitignored.
- **No completion claim** without full test suite pass/fail counts reported.
- **Task 0 is a hard gate**: no Task 1+ work until preflight returns 0.

---

## Learning-mode contribution points (summary)

| Task | Your contribution | Size |
|---|---|---|
| Task 2 | Inclusion criteria + corpus curation | ~60–80 corpus entries + criteria paragraph |
| Task 6 | Pivotal-trial operational definition | 1 paragraph in `docs/pivotal-criterion.md` |

Everything else is mine to build.

---

## Open questions before kickoff

1. Task 2 inclusion scope — which CV sub-indications count?
2. Task 6 pivotal criterion — strict / inclusive / both-as-sensitivity?
3. Any NMEs you want explicitly excluded for domain reasons (e.g., approved-but-withdrawn, or ones you've already audited in HiddennessAtlas)?

Reply with answers to these three and I will start Task 0.
