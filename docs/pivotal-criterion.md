# Pivotal-Trial Operational Definition

**Decided**: 2026-04-15. Locked before extraction begins. This is the denominator for the headline claim and is pre-registered here to pre-empt post-hoc criterion-shopping.

## Primary criterion: STRICT (FDA/EMA-labelled pivotal)

A trial is **pivotal** if and only if the FDA Medical Review or EMA EPAR explicitly labels it as pivotal, primary, or the basis-of-approval trial. Labels accepted:

- FDA Medical Review: "pivotal trial", "primary efficacy trial", "trial supporting approval" when listed as the sole/main study
- EMA EPAR §2.5.x: "main study", "pivotal study", "Study X supported the approval"

Trials appearing in "supportive evidence", "additional studies", "Phase 2 dose-ranging", or "pharmacology studies" sections are NOT pivotal under the strict criterion, regardless of Phase.

## Secondary criterion: INCLUSIVE (sensitivity analysis)

A trial is **inclusive-pivotal** if it appears in any "Studies to Support Efficacy" or "Clinical Efficacy" section AND is Phase 3 (or Phase 2/3, Phase 3b). Phase 2-only dose-finding trials remain excluded even under the inclusive criterion.

## Reporting plan

Phase 1 extraction tags both `pivotal_strict` and `pivotal_inclusive` flags on every `TrialRecord`. Phase 3 manuscript reports the strict criterion as the primary headline result and the inclusive criterion as a pre-specified sensitivity. This is the Phase 1 CSV deliverable — both columns present.

## Why strict as primary

- **Turner 2008 comparability**: Turner et al. (2008) NEJM used FDA-labelled pivotal for antidepressants. A direct cardiology replication maximises methodological defensibility. A reviewer cannot argue "your denominator is different from Turner's" if we match his operationalisation.
- **Cleanest attack surface**: Every trial in the strict denominator has a clear regulatory paper trail labelling it pivotal. A reviewer claiming "but this trial was not really pivotal" is arguing against the FDA/EMA reviewer's own words, not against ours.
- **Smaller N, tighter claim**: Strict yields fewer trials per NME (typically 1-2) and a tighter, more defensible publication-gap percentage.

## Why inclusive as sensitivity

- **Pre-empts the "you cherry-picked a small denominator" criticism**: A reviewer who thinks strict is too narrow gets their answer in the sensitivity analysis without us having to re-run.
- **Turner-analog sensitivity**: Turner himself reported sensitivity with broader trial sets. Doing so here is not an innovation, it's expected.
- **Free-ish engineering**: Both flags fall out of the same extraction pass. Cost = one extra column, not a second extraction run.

## Locked

No post-hoc switching of primary criterion after data is in. If the strict result underwhelms, the inclusive result is reported as pre-specified sensitivity — not promoted to primary.

## Amendment log

*None yet. First extraction run pending.*
