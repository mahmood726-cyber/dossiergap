---
title: 'DossierGap: a fail-closed pipeline for extracting pivotal-trial data from FDA and EMA regulatory dossiers'
tags:
  - Python
  - meta-research
  - regulatory
  - cardiology
  - publication bias
  - reproducibility
authors:
  - name: African or SAARC trainee first author
    affiliation: 1
  - name: Developed-country methodologist
    affiliation: 2
  - name: Mahmood Ahmad
    orcid: 0000-0000-0000-0000
    affiliation: 3
  - name: Senior author from Ziauddin
    affiliation: 4
affiliations:
 - name: Affiliation 1
   index: 1
 - name: Affiliation 2
   index: 2
 - name: Tahir Heart Institute, Pakistan
   index: 3
 - name: Ziauddin University, Pakistan
   index: 4
date: 16 April 2026
bibliography: paper.bib
---

# Summary

`DossierGap` is an open-source Python pipeline that extracts pivotal-trial hazard ratios, confidence intervals, and randomised population sizes from FDA Drugs@FDA Medical Reviews and EMA European Public Assessment Report PDFs. It is designed as a substrate for cardiology publication-gap analyses in the tradition of Turner et al. [@turner2008] and as a methodological example of the trust infrastructure required for AI-assisted regulatory-dossier analysis to reach peer review. The pipeline combines regex pattern matching, document-clustering for non-standard PDF templates, and pydantic-enforced schema validation, with three explicit corruption-mode guards (negated counts, chart-axis numbers, questionnaire-acronym false positives) and a mandatory hand-audit report comparing extracted values to published primaries. The architecture is deliberately fail-closed: every extractor either returns a validated value or raises `ExtractionError`, and partial records are discarded rather than defaulted.

# Statement of need

Turner et al.'s 2008 NEJM publication-gap analysis showed 31% of FDA-registered antidepressant trials reached no peer-reviewed publication and that publication status correlated with reported outcome [@turner2008]. A cardiology equivalent has not been produced at scale, despite the obvious relevance for evidence-based drug evaluation. The obstacle is not data access — FDA Medical Reviews and EMA European Public Assessment Reports are public — but reliable extraction at scale: hand-reading 20+ cardiology dossiers to identify pivotal trials and their effect estimates is weeks of work per analyst, and the task does not compose across analyses.

Existing AI-assisted research-extraction tools [@marshall2019; @tsafnat2014] focus on screening and effect-size extraction from published papers, not regulatory dossiers. None provides the trust infrastructure required to distinguish legitimate extractions from plausibly-formatted corruption — the failure mode where a positive integer in the right schema field is the wrong positive integer, undetectable by validation alone. `DossierGap` addresses this gap with explicit fail-closed contracts, a corpus-of-corruption-modes test suite, and a required hand-audit deliverable that serves as a first-class output of the pipeline rather than optional scaffolding.

# Functionality

The pipeline is a four-stage chain (`download` → `section detection` → `per-trial extraction` → `cross-register deduplication`) with versioned CSV output. Each stage is independently testable. The architecture is driven by the central observation that AI-assisted extraction fails in two distinct ways: silent-sentinel corruption (well-understood, partially solved by schema validation) and semantic-valid-but-wrong extraction (under-discussed, with no structural defence). `DossierGap` addresses the first via pydantic invariants — `effect_ci_low ≤ effect_estimate ≤ effect_ci_high`, `pivotal_strict ⊆ pivotal_inclusive`, mandatory non-empty `source_page_refs` audit trail — and addresses the second by acknowledging it as a residual limitation requiring hand audit.

Three specific corruption modes were discovered during validation against a 20-NME cardiology pilot corpus and are encoded as regression tests:

1. **Negated counts.** A "Not Randomized 1,807" disposition-table row was matched by the narrative N regex and would have produced `N=1,807` instead of the true `N=5,050` for the Verquvo VICTORIA trial. Fix: 30-character preceding-context negation filter (`not`/`non`/`never`).

2. **Chart-axis numbers.** "0 2500 5000 7500 10000 12500 15000" (chart tick labels) was matched by the disposition-table fallback and would have produced `N=15,000`. Fix: restrict disposition-table fallback to comma-formatted numbers; chart axis labels in `pdfplumber`-extracted PDFs are almost always bare integers.

3. **Questionnaire-acronym false positives.** "HCMSQ-SB" appeared more often than "EXPLORER-HCM" in the Camzyos Medical Review and would have been picked as the trial-name cluster centre. Fix: trial-context adjacency filter requiring candidate acronyms to appear within 40 characters of "trial", "study", or "Phase".

# Validation

Against 20 cardiology new molecular entities approved 2015–2024, two NMEs yielded ground-truth-matched extractions: Entresto/PARADIGM-HF [@mcmurray2014] (HR 0.80, 95% CI 0.73–0.87, N=8,442) and Verquvo/VICTORIA [@armstrong2020] (HR 0.90, 95% CI 0.82–0.98, N=5,050) — both matching the published primary *exactly* on hazard ratio, both CI bounds, and randomised N, via independent regex paths through FDA narrative and EMA table extraction. Two yielded noisy extractions (Uptravi/GRIPHON [@sitbon2015] secondary endpoint instead of primary; Savaysa/ENGAGE AF-TIMI 48 [@giugliano2013] subgroup analysis instead of full population). Seventeen failed on structural grounds documented in the audit. The 13% extraction success rate is a floor, not a steady-state estimate; the architecture is shipped as a validated substrate for further development, not as a turnkey corpus tool.

# Acknowledgements

Trainee networks at Ziauddin University, Pakistan, and partner institutions in sub-Saharan Africa contributed corpus auditing and identified the failure modes documented above. The development workflow leveraged a separately-developed pre-push integrity gate (Sentinel) and accumulated-lessons rule files [@ahmad_methodology]. Mahmood Ahmad serves on the editorial board of *Synthesis*; this manuscript is not being submitted to *Synthesis*.

# References
