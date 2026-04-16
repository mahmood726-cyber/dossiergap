# DossierGap Phase 2 Plan

**Status**: Draft, 2026-04-16.
**Context**: Phase 1 shipped (`v0.1.0`, 2 clean CSV rows from 5-NME smoke). Audit in `outputs/extraction_audit.md` identified three P0 blockers for a ship-ready full-corpus run.

## Phase 2 goals

1. Get FDA OtherR (2020+ integrated reviews) to extract — unblocks Nexletol, Verquvo, Camzyos FDA paths.
2. Primary-outcome proximity scoring — fix the noisy-outcome text for Uptravi and Verquvo.
3. Recover Verquvo N via context scoring or a dedicated disposition-table pattern.

Non-goals (Phase 3): URL-discovery helpers (Task 3.5/4.5), cross-drug batching, large-corpus parallelism.

## Static vs dynamic hardcode disclosure

| Component | Static | Dynamic |
|---|---|---|
| OtherR trial-name detection | None — cluster by acronym density | Per-PDF acronym frequency |
| Primary-outcome proximity window | 500 chars default | Per-match distance scoring |
| N disposition-table rejection | "not/non/never" negation prefix (Phase 1 fix) | Per-page candidate scoring |

## Tasks

### Task 15 — FDA OtherR structural section detector

**Why**: 3 of 5 smoke NMEs fail on FDA OtherR. Regex-only fallbacks are insufficient — OtherR concatenates reviewer memos without a single "Review of Efficacy" heading. Need document-clustering.

**Design**:
- New pure function `_find_trial_name_cluster(pages: list[str]) -> tuple[int, int] | None`
- Step 1: find the most-frequent acronym-shaped token across the whole PDF (same detector as `extract_trial_name`)
- Step 2: compute per-page mention count for that token
- Step 3: find the contiguous page range (min 3 pages, ≥2 mentions per page, or equivalent density threshold) with the highest total count
- Integrate as third fallback in `find_efficacy_section_in_pages` after the existing primary + OtherR-anchor paths

**Tests**: synthetic cluster, Verquvo integration (expect VICTORIA cluster around p.40–80 range).

### Task 16 — Primary-outcome proximity scoring

**Why**: Uptravi extracted HR 0.67 (secondary endpoint, not primary 0.60). Verquvo extracted "found with HRs larger than the overall effect" (subgroup text). Both are noisy because the extractor picks the shortest/first match, not the most-primary-adjacent.

**Design**:
- Score each candidate HR match and primary-outcome match by distance (in chars) to nearest "primary endpoint" / "primary composite" keyword
- Break ties by earlier page (primary results usually introduced before subgroups)

**Tests**: synthetic pages with subgroup-before-primary ordering; Entresto regression guard (HR 0.80 should still win).

**Status (2026-04-16)**: DONE. Delivered in two commits:
- `1bb2e2f` (partial): fallback-pattern expansion (colon/table-style/outcome form). Deferred semantic scoring to Phase 3 after pure-proximity experiment regressed Uptravi.
- Task-16-completion commit: semantic content scoring per the partial commit's own proposal. `score_outcome_candidate` in `_common_extract.py` rewards clinical-endpoint vocabulary (death/mortality/hospitali/mace/composite) inside the capture, penalises method vocabulary (performed/analysed/FAS/per-protocol/log-rank) inside the capture, and adds a primary-keyword proximity bonus. `rank_outcome_candidates` sorts by score with shortest-captured tie-break (preserves Phase-1 behaviour on no-signal). `extract_primary_outcome` now delegates to the ranker. The HR-candidate half of the original design was covered by Task 19 (FDA narrative `score_hr_candidate`).
- Tests: `tests/test_outcome_scoring.py` (10 tests — 5 pure-fn, 2 ranker, 3 integration) + existing Entresto regression tests in `test_parse_fda_trials.py` continue to assert `"cardiovascular death" in primary_outcome.lower()` on the real PDF.
- Full suite: 228/228 pass, 0 regressions.

### Task 17 — N context scoring (disposition-table aware)

**Why**: Verquvo extraction currently fails because `Not Randomized 1,807` is rejected (Phase 1 fix) but no other N pattern exists in the efficacy section. The real N=5,050 appears in the disposition-table row: `Subjects in population 2,526 2,524 5,050`. Need a second N pattern.

**Design**:
- Add a disposition-table pattern: `(?:Subjects|Total|Analysis set|FAS|ITT)[\s\w]{0,20}(\d{1,3}(?:,\d{3})+|\d{3,6})`
- Context-score: prefer N values appearing in first half of efficacy section (near demographic/disposition tables)

**Tests**: synthetic disposition-table case; Verquvo integration (should recover N=5050).

## Execution discipline

- TDD per task.
- Commit per task.
- Retry cap 3 per failing test; log to `STUCK_FAILURES.md`.
- Real-PDF integration tests marked `@pytest.mark.slow` before full suite grows past 10 min (currently 7:48).
- Rerun Task 14 audit after each Phase 2 task; target improved row count with no silent-corruption regressions.
