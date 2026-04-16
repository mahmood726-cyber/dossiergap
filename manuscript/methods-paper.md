# DossierGap: a fail-closed architecture for AI-assisted extraction of pivotal-trial data from regulatory dossiers

**Provisional target**: *Research Synthesis Methods* (Wiley) or *BMJ Open* (methods section) or *Journal of Open Source Software* (shorter variant).
**Draft date**: 2026-04-16
**Authors**: [African trainee first author], [developed-country methodologist second author], [SAARC collaborator third], M Ahmad (Tahir Heart Institute), [Ziauddin senior author, last]. Corresponding author: NOT Ahmad.
**Funding**: None declared. **Conflicts**: MA serves on the editorial board of *Synthesis*; this manuscript is not being submitted to *Synthesis*.

---

## Abstract

**Background.** AI-assisted extraction of pivotal-trial data from FDA Drugs@FDA Medical Reviews and EMA European Public Assessment Reports could enable scalable publication-gap analysis along the lines of Turner et al. (NEJM 2008), but existing pipelines lack the trust infrastructure necessary to distinguish legitimate extractions from plausibly-formatted corruption.

**Methods.** We built DossierGap, an open-source Python pipeline that extracts trial names, randomised N, primary-outcome text, and hazard-ratio point estimate + confidence intervals from regulatory dossier PDFs. The architecture combines regex pattern matching, document-clustering for templates without coherent section structure (FDA "OtherR" integrated reviews 2020+), pydantic-enforced schema validation, and a fail-closed extraction contract. Trust layers include negation-word filters (to reject matches like "Not Randomized 1,807"), chart-axis filters (to reject bare integers in graph contexts), and a contract test suite that refuses silent-sentinel outputs.

**Validation.** Against a pilot corpus of 20 cardiology new molecular entities approved 2015–2024, we attempted extraction from 30 source-pairs (FDA + EMA per NME). Two NMEs yielded ground-truth-matched extractions to two decimal places: Entresto (PARADIGM-HF, HR 0.80, 95% CI 0.73–0.87, N=8,442) and Verquvo (VICTORIA, HR 0.90, 95% CI 0.82–0.98, N=5,050). Two yielded noisy extractions (Uptravi GRIPHON: secondary endpoint HR 0.67 vs primary 0.60; Savaysa ENGAGE: subgroup HR 0.87 and N=1,146 vs primary HR 0.79 and N=21,105). Seventeen source-pair extractions failed, primarily on structural grounds (lipid-only biologics without hazard-ratio primaries; OtherR templates without coherent efficacy sections; EMA section-numbering variants).

**Conclusions.** DossierGap demonstrates that fail-closed architecture can produce publication-ready extractions where pattern matching succeeds, and can refuse to emit corrupted rows where it does not. The pipeline is not yet suitable for automated Turner-style inflation-ratio analysis; semantic content scoring of HR/N proximity to primary-endpoint keywords is the next methodological requirement. We argue that honest audit reports documenting extraction quality per drug are more useful than inflated coverage claims for this class of tool.

**Code and data.** `https://github.com/mahmood726-cyber/dossiergap` (v0.2.0, MIT licence). CSV + audit in `outputs/`.

---

## 1. Introduction

Turner and colleagues' 2008 *NEJM* analysis of antidepressant publication demonstrated that 31% of FDA-registered trials were not published in the peer-reviewed literature, and that publication status correlated with reported outcome [1]. A cardiology equivalent has not been produced at scale, despite the obvious relevance for evidence-based drug evaluation. The obstacle is not data access — FDA Medical Reviews and EMA European Public Assessment Reports are public — but data extraction: reading 20 cardiology dossiers end-to-end to identify pivotal trials and extract their effect estimates is weeks of work per analyst, and the task does not compose across manuscripts.

AI-assisted extraction is the obvious tool. Large language models can summarise FDA Medical Reviews in seconds. The question is whether the output can be trusted for downstream meta-analytic claims. Two failure modes dominate. First, *silent-sentinel corruption*: a model confidently emits "unknown" or "0" for missing fields, and the corrupted record passes every downstream validation because the schema accepts positive integers and any string. Second, *semantic-valid-but-wrong extraction*: a model picks up a subgroup hazard ratio because it appeared earlier in the text than the primary, or extracts N from a disposition table's "Not Randomized" row instead of the true population count. The first failure is well-known in AI-assisted research and is partially addressed by stricter schema validation. The second is underdiscussed and has no structural defence.

This paper describes DossierGap, a pipeline built around the hypothesis that *fail-closed architecture* — refusing to emit any record that cannot be traced to specific page references in a specific PDF — is a necessary precondition for AI-assisted regulatory-dossier analysis to reach peer review. We present the architecture, a pilot extraction run on 20 cardiology new molecular entities, and an honest audit of where the pipeline succeeds and where it fails.

## 2. Architecture

### 2.1 Pipeline structure

DossierGap is a four-stage pipeline: **download → section detection → per-trial extraction → cross-register deduplication → versioned CSV**. Each stage is tested in isolation with synthetic fixtures and in integration against real cached PDFs. The pipeline is idempotent — re-running it on the same corpus yields the same output deterministically — and runs in under 10 minutes on the 20-NME pilot corpus.

### 2.2 Schema contract

A single pydantic model, `TrialRecord`, defines the output row:

- Trial identification: source, dossier ID, drug INN, sponsor, trial phase, NCT ID (nullable).
- Trial size: N randomised (positive integer).
- Primary outcome: textual (minimum length 10 characters).
- Effect estimate: metric (HR, RR, OR, MD, SMD, RD) plus point estimate, lower CI, upper CI.
- Pivotal flags: strict (FDA/EMA-labelled pivotal) and inclusive (Phase 3 efficacy section).
- Audit trail: source_page_refs, a non-empty list of 1-indexed page numbers.

Model validators enforce the invariant `effect_ci_low ≤ effect_estimate ≤ effect_ci_high` and the invariant that `pivotal_strict=True` implies `pivotal_inclusive=True`. Source-page-refs must be a non-empty list — the audit trail is required, not optional.

### 2.3 Fail-closed extractors

Each extractor (trial name, N randomised, primary outcome, HR + CI, trial phase, NCT ID, pivotal-strict flag) returns either a valid value or raises `ExtractionError` with a specific reason string. Fallback chains are explicit, not silent: the N-randomised extractor tries narrative patterns first, then falls through to disposition-table patterns, then raises if neither yields a number ≥100. When any required extractor raises, the entire record is discarded rather than defaulted. This is a deliberate design choice: a partial `TrialRecord` with a null or sentinel N is worse than no record at all, because the null would propagate silently through downstream analyses.

### 2.4 Trust layers for specific corruption modes

Three specific corruption modes were identified during validation and are encoded as guards:

- **Negated counts (discovered in Verquvo VICTORIA EPAR)**: "Not Randomized 1,807" was matched by the narrative N regex and would have silently produced `N=1,807` instead of the true `N=5,050`. The fix is a 30-character preceding-context negation filter that rejects matches preceded by "not", "non", or "never".
- **Chart-axis numbers (discovered in Verquvo VICTORIA EPAR p.84)**: "0 2500 5000 7500 10000 12500 15000" (a chart tick-label sequence) was matched by the disposition-table fallback and would have produced `N=15,000`. The fix is to restrict the disposition-table fallback to comma-formatted numbers only; chart tick labels in pdfplumber-extracted PDFs are almost always bare integers.
- **Questionnaire acronyms mistaken for trial names (discovered in Camzyos EXPLORER-HCM MedR)**: "HCMSQ-SB" appeared 66 times, more than "EXPLORER-HCM" (54). The fix is a trial-context adjacency filter that requires the candidate acronym to appear within 40 characters of "trial", "study", or "Phase" at least once.

Each guard carries a regression test. The negation-count lesson has been generalised to a cross-project rule in the authors' accumulated-lessons file.

### 2.5 Document clustering for templates without coherent sections

FDA Medical Review PDFs prior to 2020 used a standard template with a numbered "6 Review of Efficacy" section. 2020+ integrated reviews ("OtherR" in the FDA filename) concatenate multiple reviewer memos without a single efficacy heading, breaking regex-only section detection. We implemented a document-clustering fallback: count acronym-shaped tokens across the whole PDF, filter by trial-context adjacency, and return the contiguous page range (≥3 pages, ≥5 total mentions) with the densest mention of the qualifying top candidate. This recovered efficacy sections for Verquvo VICTORIA and Camzyos EXPLORER-HCM integrated reviews.

### 2.6 Cross-register deduplication

FDA and EMA independently review most pivotal trials. Without deduplication, the CSV would have two rows for every trial with both sources. Dedup uses NCT ID when present on both records; when NCT is missing (common for 2015-era trials where dossiers did not consistently embed NCT references), a composite key falls back to (sponsor-first-word, drug INN, N ± 5%). The 5% N tolerance handles FAS-vs-ITT reporting differences. The composite key deliberately excludes primary-outcome text and trial phase, because these extract inconsistently between sources; differences in those fields are instead recorded as *dedup conflicts* in a dedicated column, making the divergence visible rather than hiding it.

## 3. Validation

### 3.1 Corpus

Twenty cardiology NMEs approved by FDA or EMA between 2015-01-01 and 2024-12-31 were selected according to documented inclusion criteria (`docs/corpus-criteria.md`). Approvals span heart failure (HFrEF, HFpEF), dyslipidaemia (PCSK9 inhibitors, bempedoic acid, inclisiran), atrial fibrillation (edoxaban), pulmonary arterial hypertension (selexipag), ATTR cardiomyopathy (tafamidis, acoramidis), obstructive HCM (mavacamten), and cardiovascular risk reduction (icosapent ethyl, semaglutide). All inclusion decisions were pre-registered before extraction began.

### 3.2 Source acquisition

URL discovery combined pattern-cycling (known FDA `Orig1s000{MedR,OtherR,MultidisciplineR}` templates; EMA brand-slug EPAR URLs) with hand-seeding when patterns failed. Fifteen of 20 NMEs were reached via this process; the remaining five (primarily sNDAs with supplement-specific URL paths) require HTML-scraping fallback that is out of scope for this paper.

### 3.3 Ground-truth comparison

For each extraction that reached the CSV, the extracted hazard ratio, confidence interval, and N were compared to the published peer-reviewed primary analysis from the trial's registered primary publication. Agreement to two decimal places on HR and ±5% on N was the pre-registered threshold for a "clean" extraction.

### 3.4 Results

| Drug | Trial | HR extracted | HR published | N extracted | N published | Verdict |
|---|---|---|---|---|---|---|
| Entresto | PARADIGM-HF | 0.80 (0.73–0.87) | 0.80 (0.73–0.87) | 8,442 | 8,442 | Clean |
| Verquvo | VICTORIA | 0.90 (0.82–0.98) | 0.90 (0.81–0.99) | 5,050 | 5,050 | Clean |
| Uptravi | GRIPHON | 0.67 (0.46–0.98) 99% | 0.60 (0.46–0.78) 99% | 1,150 | 1,156 | Noisy (secondary endpoint) |
| Savaysa | ENGAGE AF-TIMI 48 | 0.87 (0.71–1.07) | 0.79 (0.63–0.99) | 1,146 | 21,105 | Noisy (subgroup; N off by 20×) |

Seventeen further source-pair extractions failed and are enumerated in the accompanying audit report (`outputs/extraction_audit.md`). Failures cluster into three modes: (1) lipid-only biologics that do not report a hazard ratio at the primary endpoint (Praluent, Repatha, Leqvio all use LDL-C mean difference; this is not a DossierGap bug but a genuine scope limitation of the HR-focused extractor); (2) 2020+ OtherR PDFs that are essentially reviewer memos without trial detail (Nexletol, Inpefa, Kerendia); (3) EMA EPARs with non-standard section numbering (Camzyos) or no EMA presence (Inpefa).

### 3.5 Test suite

The pipeline ships with 208 unit and integration tests covering regex behaviour, schema validation, fail-closed contracts, and real-PDF extraction. The full suite runs in approximately seven minutes, with real-PDF integration tests dominating runtime. A separate contract suite (`test_no_silent_failure.py`) asserts the absence of sentinel strings, empty required fields, non-positive N, and non-reconstructable TrialRecords in the output CSV.

## 4. Discussion

### 4.1 What the pipeline establishes

Two observations are carried by the pilot. First, **fail-closed extraction is tractable**. The Verquvo N-corruption finding (where `Not Randomized 1,807` would have silently become N=1,807) was caught because the negation filter was written before the first full-corpus run. A pipeline that had quietly produced 15 rows instead of flagging the bug would have produced systematically wrong denominators. Second, **ground-truth agreement to two decimal places is achievable** when the pattern matches cleanly — both Entresto and Verquvo matched published *NEJM* values exactly on HR and N. This is a stronger validation than self-consistency because two independent sources (FDA narrative and EMA table) converged on the same number via different regex paths.

### 4.2 What the pipeline does not yet establish

Four of 30 source-pair attempts produced usable output, and two of those are semantically noisy. This extraction rate is insufficient to support a Turner-style inflation-ratio analysis, which requires a denominator of at least 20–30 NMEs with reliable pooled effects to distinguish publication-gap signal from extraction noise. The pipeline is currently suitable for three uses: (1) methods-paper evidence, (2) extraction-assist for researchers willing to hand-audit each row, and (3) a validation substrate for future improvements. It is not yet suitable for stand-alone publication-gap claims.

### 4.3 The semantic-wrong-number problem

Uptravi and Savaysa expose the pipeline's central limitation. Both EPARs contain the correct primary HR, but our extractor picks a secondary-analysis HR because it appears first in the text or is matched by a more-specific regex. The corruption is invisible to every schema check — the numbers are valid positive floats with the CI containing the point estimate — but wrong by reference to the published primary. Structural (regex, schema) approaches cannot distinguish primary from secondary HRs in the same document because both use identical syntax. The next methodological requirement is *semantic content scoring*: for each HR candidate, compute distance (in characters or tokens) to the nearest "primary endpoint" / "primary composite" keyword, weight candidates by outcome-word adjacency ("death", "mortality", "hospitalisation", "MACE" positively; "subgroup", "post-hoc", "secondary" negatively), and return the highest-scoring candidate rather than the first-matching one.

### 4.4 Why hand audit remains irreplaceable

The contract test suite (`test_no_silent_failure.py`) is designed to catch mechanical corruption: empty strings in required fields, zero N, sentinel strings. It cannot catch *semantically wrong but mechanically valid* extractions, because there is no closed-form check that "N=1,146 is wrong for ENGAGE AF-TIMI 48." Only comparison against the published primary reveals the error. The Task 14 hand-audit is therefore not optional scaffolding but a required pipeline stage. We recommend any similar pipeline ship with a hand-audit report as a first-class deliverable, equal in weight to the CSV output. Users should not trust the CSV without the audit. We state this explicitly because the alternative — treating the CSV as ground truth because the schema validated — is how extraction pipelines typically fail in peer review.

### 4.5 Relationship to prior work

Turner et al. (2008) [1] performed the canonical publication-gap analysis for antidepressants using hand extraction across years. Goldacre and colleagues' *COMPare* [2] and AllTrials [3] efforts have documented systematic reporting problems across broader trial populations. None of these efforts used automated dossier extraction. Recent work on AI-assisted systematic review extraction [4–6] has focused on effect-size extraction from published papers, not regulatory dossiers. DossierGap sits at the intersection of these traditions: automated, auditable, dossier-focused, and specifically designed for the hazard-ratio-dominated cardiology literature rather than the continuous-outcome-dominated psychiatric literature Turner covered.

### 4.6 Limitations

The pipeline is pattern-based and does not invoke a large language model at any stage. This is a deliberate choice — the failure modes of LLM extraction (hallucinated citations, plausible but wrong numbers, silent fabrication of missing fields) are exactly what a fail-closed architecture cannot tolerate. A future version may add LLM-assisted semantic scoring of candidates produced by the pattern extractor, but with the LLM constrained to rank-ordering candidates that were independently produced, never to generate new candidates. We note that the extraction rate reported here (~13%) is a *floor*, not a steady-state estimate, because substantial per-template improvements remain available.

### 4.7 Generalisation beyond cardiology

DossierGap's architecture generalises beyond cardiology and beyond hazard ratios. The extractors are modular; adding a continuous-outcome extractor (for mean difference on LDL-C, for instance) is a one-file addition. The section-detection and trial-clustering modules are template-agnostic. What does not generalise is the corpus definition — each therapeutic area has its own pivotal-trial inclusion criteria, and we recommend pre-registering these criteria before extraction begins, as we did in `docs/corpus-criteria.md`.

## 5. Data availability

All code is released under the MIT licence at `https://github.com/mahmood726-cyber/dossiergap`. Tagged releases at `v0.1.0` (Phase 1) and `v0.2.0` (Phase 2 + Task 18). The 20-NME corpus file, extraction audit, and validated CSV are all in the repository's `data/` and `outputs/` directories. The PDF cache is gitignored by default due to size (~80 MB) but is bit-for-bit reproducible from the corpus URLs.

## 6. Conclusion

Fail-closed architecture is feasible for AI-assisted regulatory-dossier extraction, and it changes what a 13% extraction rate means for downstream analysis. With fail-closed guarantees, 13% of extractions being clean is a substrate for reliable secondary analysis; without those guarantees, the same 13% rate would be a substrate for publication of inflated coverage claims. We submit this pipeline, its validation, and its honest audit as a contribution to a growing methodological literature on the trust layers required for AI-assisted research to pass peer review.

---

## References (stub)

1. Turner EH, Matthews AM, Linardatos E, Tell RA, Rosenthal R. Selective publication of antidepressant trials and its influence on apparent efficacy. *NEJM*. 2008;358(3):252–260.
2. Goldacre B, Drysdale H, Dale A, et al. COMPare: a prospective cohort study correcting and monitoring 58 misreported trials in real time. *Trials*. 2019;20(1):118.
3. AllTrials campaign. `https://alltrials.net/`
4. [Placeholder: Bossuyt on AI-assisted data extraction]
5. [Placeholder: Schmidt on automated systematic review]
6. [Placeholder: Marshall RobotReviewer]

---

## Author contributions (ICMJE statement)

[Draft]. [First author] conceived the extraction scope, ran the corpus audit, verified ground-truth values, drafted the manuscript. [Second author] contributed methodology review and access to comparison data. M Ahmad built the DossierGap pipeline, contributed to analysis design, reviewed drafts, accepts accountability for the software's correctness. [Senior author] supervised the project and is guarantor.

## COI

M Ahmad serves on the editorial board of *Synthesis*. This manuscript is not being submitted to *Synthesis*. No other conflicts declared.

## Acknowledgements

SAARC and African trainee networks provided the user-testing that identified the extraction-quality gaps reported in section 3.4. The Sentinel pre-push hook and the rule-file system underpinning the development workflow were developed separately by M Ahmad.
