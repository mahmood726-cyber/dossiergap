# DossierGap Phase 1 — Task 14 Extraction Audit

**Run date**: 2026-04-15
**Corpus**: `data/cardiology-nme-corpus.json` (20 NMEs, 2015–2024 approvals)
**CLI invocation**: `python -m dossiergap extract --corpus data/cardiology-nme-corpus.json --out outputs/dossier_trials.v0.1.0.csv --limit 20 --continue-on-error`
**Output CSV**: `outputs/dossier_trials.v0.1.0.csv` (2 rows)

---

## Honest outcome

| Category | Count |
|---|---|
| NMEs in corpus | 20 |
| NMEs with hand-seeded URLs (both sources where applicable) | 5 |
| Source-pairs attempted (FDA + EMA) | 10 |
| Source-pairs successfully extracted | 3 |
| Unique trials in output CSV after dedup | 2 |

The **Phase 1 ship criterion of ≤5 % hand-audit drift** was set against a denominator of "extracted trials". With only 2 trials successfully extracted from a 5-NME smoke subset, the criterion is not meaningfully testable yet — the audit below focuses on *what succeeded* and *why the failures failed*, not on drift rate.

---

## Succeeded

### 1. Entresto (sacubitril/valsartan, HFrEF) — PARADIGM-HF

- **FDA NDA 207620** → extracted HR 0.80, 95% CI 0.73–0.87, N=8442, primary outcome "cardiovascular death or first heart failure hospitalization". Pages 55, 65.
- **EMA EMEA/H/C/004062** → extracted HR 0.80, 95% CI 0.73–0.87, N=8442. Pages 60, 65, 72, 81.
- **Dedup** merged both via composite key (same sponsor + drug + N). Conflicts logged: `pivotal_strict` ([false, true]), `primary_outcome` (FDA clean vs EMA table-noise), `trial_phase` (3 vs 2 — EMA cited supporting Phase 2 studies).
- **Ground truth** (PARADIGM-HF NEJM 2014): HR 0.80, 95% CI 0.73–0.87. **Match to 2 dp on all values.**

### 2. Verquvo (vericiguat, HFrEF worsening) — VICTORIA

- **EMA EMEA/H/C/005325** → extracted HR 0.90, 95% CI 0.82–0.98, N=1807, primary outcome "found with HRs larger than the overall effect" (subgroup text — noisy).
- **FDA NDA 214377** → section detection failed (see Failures below).
- **Ground truth** (VICTORIA NEJM 2020): HR 0.90, 95% CI 0.81–0.99 for CV death or first HF hospitalization, N=5050. **HR and CI match within 0.01. N differs significantly (1807 vs 5050) — extractor pulled a subgroup or a different trial's N. Flagged.**

---

## Failed (7 source-pairs)

| NME | Source | Failure | Root cause |
|---|---|---|---|
| Uptravi | FDA NDA 207947 | SectionNotFoundError | 2015 review, but section heading uses a non-standard variant that Task-6 regexes don't match |
| Uptravi | EMA EMEA/H/C/003774 | ExtractionError (HR) | Section found, HR regex didn't match — EPAR uses narrative-only (no "Hazard ratio" table format) |
| Nexletol | FDA NDA 211616 | SectionNotFoundError | 2020 "OtherR" template — newer FDA reviews use different section-head phrasing |
| Nexletol | EMA EMEA/H/C/004829 | ExtractionError (HR) | Section found, HR regex miss — table format absent |
| Verquvo | FDA NDA 214377 | SectionNotFoundError | 2021 "OtherR" template — same as Nexletol |
| Camzyos | FDA NDA 214998 | SectionNotFoundError | 2022 "OtherR" template |
| Camzyos | EMA EMEA/H/C/005459 | SectionNotFoundError | EPAR section numbering differs from the 2015 template |

---

## Root-cause summary

Two template-drift problems dominate:

**1. FDA "OtherR" template (2020+).** The integrated-review format replaced the separate "Medical Review" with a combined document called `OtherR.pdf`. Section structure is different — no explicit "N Review of Efficacy" / "N+1 Review of Safety" pattern. Task-6 detector needs an OtherR-specific anchor set. Discovered at Task 14 because Phase 1 ground-truth work focused on the 2015 Entresto template.

**2. EMA EPAR extractor is fragile to non-table HR formats.** Drugs whose EPAR reports the primary HR in a narrative paragraph (rather than a structured results table) fail the `Hazard ratio <p> ... 95%-CI <lo>, <hi>` regex. Task 9 preferred table-first to avoid mis-matching post-hoc HRs in Entresto; the side effect is missing legitimate narrative HRs in other EPARs.

## Secondary issues (succeeded-but-noisy)

- **Verquvo N=1807** extracted but true VICTORIA N=5050. The N regex matched a subgroup count.
- **Verquvo primary_outcome** = "found with HRs larger than the overall effect" — subgroup text, not primary endpoint definition.
- **Entresto composite-dedup conflicts** (logged, not resolved): FDA reported `trial_phase=3`, EMA reported `trial_phase=2` because EMA's efficacy section cites supporting Phase-2 studies (CLCZ696B2124, B2214) alongside PARADIGM-HF.

---

## Recommended Phase 2 work (prerequisites for a shippable full-corpus run)

1. **FDA OtherR template support** — add a second regex set for 2020+ integrated reviews; ship-blocking.
2. **EMA narrative-HR fallback** — restore narrative `HR <p>; 95% CI <lo>, <hi>` matching when no table format is found in the efficacy section (currently returns first narrative match as fallback, but the regex itself may miss valid patterns).
3. **Primary-outcome regex hardening** — prefer occurrences near "Primary endpoint" section headings over free-text "primary endpoint was" phrases scattered elsewhere.
4. **N-randomized context scoring** — prefer N counts that appear in the first 5 pages of the efficacy section (summary) over later subgroup counts.
5. **URL-discovery helpers (Task 3.5 / 4.5)** — scrape the Drugs@FDA overview page for Medical Review links; scrape EMA procedure page for the EPAR PDF. Only 5/20 NMEs in the Phase 1 corpus have hand-seeded URLs.

---

## What this audit proves

- The Phase 1 architecture (download → section detect → extract → dedup → CSV) works end-to-end. **One complete trial (PARADIGM-HF) successfully extracted from both sources and merged into a single row with HR and CI matching the published values to 2 dp.**
- The pipeline fails closed correctly on template drift — no silent-sentinel rows in the output.
- Phase 1 output `dossier_trials.v0.1.0.csv` is a valid (though narrow) demonstration of the DossierGap concept. Not a ship-ready deliverable for the BMJ Analysis manuscript.

## What this audit does NOT prove

- The hand-audit drift rate across the full corpus (denominator too small).
- Whether the composite-dedup relaxation (sponsor + drug + N) generalises without false-merge risk (the only cross-source merge so far is Entresto, and it's clean).
- That the URL patterns `*Orig1s000MedR.pdf` / `*Orig1s000OtherR.pdf` cover the majority of the corpus — 4 of 10 URL probes returned 404 (Praluent BLA, Repatha BLA, Savaysa, Leqvio, Vyndaqel).
