# DossierGap

Cardiology NME dossier pivotal-trial publication-gap audit. FDA Drugs@FDA + EMA EPAR, approvals 2015–2025.

## Status

- Phase 1 (in progress): dossier trial extraction → versioned `dossier_trials.csv`.
- Phase 2 (planned): publication matching (NCT → protocol-feature fallback → ICTRP/EUCTR cross-check).
- Phase 3 (planned): Turner-style inflation analysis, dashboard, BMJ Analysis manuscript, E156.

## Locked decisions

- `PHASE1-PLAN.md` — execution plan, 15 tasks, TDD.
- `docs/corpus-criteria.md` — included/excluded CV sub-indications and product types.
- `docs/pivotal-criterion.md` — strict (primary) + inclusive (sensitivity) operational definition.

## Preflight

```
python scripts/preflight.py
```

Must return exit 0 before any Task 1+ work runs.

## Tests

```
python -m pytest tests/ -v
```
