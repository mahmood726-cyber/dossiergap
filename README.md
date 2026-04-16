# DossierGap

Cardiology NME dossier pivotal-trial publication-gap audit. FDA Drugs@FDA + EMA EPAR, approvals 2015–2025.

## Status

- Phase 1 (in progress): dossier trial extraction → versioned `dossier_trials.csv`.
- Phase 2 (planned): publication matching (NCT → protocol-feature fallback → ICTRP/EUCTR cross-check).
- Phase 3 (planned): Turner-style inflation analysis, dashboard, BMJ Analysis manuscript, E156.

## Locked decisions

- `PHASE1-PLAN.md` — execution plan, 15 tasks, TDD.
- `PHASE2-PLAN.md` — Phase 2 P0 blockers.
- `docs/corpus-criteria.md` — included/excluded CV sub-indications and product types.
- `docs/pivotal-criterion.md` — strict (primary) + inclusive (sensitivity) operational definition.

## Manuscripts

- `manuscript/e156.md` — 156-word *Synthesis* submission draft (7 sentences, exact spec).
- `manuscript/methods-paper.md` — full methods-paper draft (~3200 words, 12 DOI-anchored refs) targeting *Research Synthesis Methods* / *BMJ Open*.
- `manuscript/joss-paper.md` — compressed *Journal of Open Source Software* variant (~676-word body, JOSS-format YAML front matter).
- `manuscript/paper.bib` — BibTeX references for the JOSS submission.
- `manuscript/figure1.mmd` — Mermaid source for the four-stage pipeline architecture diagram (renders natively on GitHub; export to SVG with `mmdc -i figure1.mmd -o figure1.svg` for publication).
- `outputs/extraction_audit.md` — honest audit of extraction results per drug, with ground-truth comparisons.

## Preflight

```
python scripts/preflight.py
```

Must return exit 0 before any Task 1+ work runs.

## Tests

```
python -m pytest tests/ -v
```
