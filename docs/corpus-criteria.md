# Cardiology NME Corpus — Inclusion Criteria

**Decided**: 2026-04-15. Locked before extraction begins. Changes after corpus freeze require an explicit amendment entry below with a dated rationale.

## Scope

FDA- or EMA-approved new molecular entities (NMEs) with a primary cardiovascular indication, approved 2015-01-01 through 2025-12-31.

## Included CV sub-indications

- Heart failure (HFrEF, HFmrEF, HFpEF, acute decompensated HF)
- Acute coronary syndrome / myocardial infarction (secondary prevention)
- Stable coronary artery disease
- Hypertension (essential, resistant, secondary)
- Dyslipidemia (LDL-lowering, triglyceride-lowering, Lp(a), HoFH)
- Atrial fibrillation (rate, rhythm, stroke prevention)
- Peripheral arterial disease
- Pulmonary arterial hypertension
- Cardiac amyloidosis (ATTR-CM, AL)
- Hypertrophic cardiomyopathy

## Included product types

- Single-entity NMEs
- Fixed-dose combinations containing at least one new molecular entity
- Repurposed drugs approved for a new primary CV indication (e.g., dapagliflozin for HFrEF under a separate sNDA/EMA procedure — the CV approval is the unit of analysis, not the molecule)

## Excluded

- Diagnostic and imaging agents (cardiac MRI contrast, nuclear perfusion tracers)
- Antithrombotics approved exclusively for peri-procedural or surgical use
- Devices, biologics used only as adjuncts, cell therapies (out of scope for "NME" as operationalised here)
- Line extensions and reformulations of previously approved entities with no new CV indication
- Generic and biosimilar approvals

## Boundary cases — decided

- **SGLT2 inhibitors for HF**: INCLUDED. The HF indication is a separate regulatory approval with its own pivotal trials (DAPA-HF, EMPEROR-Reduced, EMPEROR-Preserved) even though the molecule was first approved for diabetes.
- **GLP-1 agonists with CV outcomes labelling**: INCLUDED only if the CV-specific approval generated new pivotal trials (e.g., semaglutide SELECT cardiovascular indication). Pure CVOT-driven label updates without a new approval procedure excluded.
- **Icosapent ethyl**: INCLUDED (REDUCE-IT was pivotal for the CV indication).
- **Vericiguat, omecamtiv mecarbil, mavacamten**: INCLUDED as NMEs.

## Why these choices

- **Breadth over purity**: Turner et al. (2008) operationalised antidepressants by FDA registration dossier, not by molecule. DossierGap follows the same unit (approval procedure = trial-set), which makes repurposed drugs with new CV approvals analysable.
- **Cardiologist-practice alignment**: The included sub-indications are what a general cardiologist prescribes from. Excluding them because of molecule-history (e.g., SGLT2i "is really a diabetes drug") would miss the clinically relevant publication-gap question.
- **HiddennessAtlas independence**: No exclusions based on prior HiddennessAtlas coverage. DossierGap operates on the dossier layer (FDA Medical Review, EMA EPAR); HiddennessAtlas operates on the CT.gov registry layer. Exclusions would destroy the three-way join (HiddennessAtlas + DossierGap + MetaAudit) that is the portfolio claim.

## Amendment log

*None yet. First extraction run pending.*
