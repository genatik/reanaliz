# Classification — ACMG 2015 + Tavtigian 2020

Classify every candidate with the ACMG/AMP 2015 criteria **and** the Tavtigian 2020 point-based Bayesian refinement adopted by ClinGen SVI. Always show the evidence codes; where useful, show the point total and the resulting class.

## ACMG/AMP 2015 classes

Pathogenic (P), Likely pathogenic (LP), Variant of uncertain significance (VUS), Likely benign (LB), Benign (B). Combine pathogenic (PVS1, PS1–4, PM1–6, PP1–5) and benign (BA1, BS1–4, BP1–7) criteria per the 2015 combining rules, refined by the point system below.

## Tavtigian 2020 point framework

Map criteria strengths to points (pathogenic positive, benign negative):
- Very strong = 8, Strong = 4, Moderate = 2, Supporting = 1 (pathogenic); benign criteria take the negative of the same magnitudes.
- Sum the points and classify: P ≥ 10; LP 6–9; VUS 0–5 (and −1 to −6 tends toward LB); LB −1 to −6; B ≤ −7 (with BA1 standalone benign). Use the ClinGen SVI Bayesian thresholds; state the total.

This point view makes VUS sub-stratification explicit and supports the Hot/Cold call below.

## Calibrated in-silico thresholds

Never treat a single predictor as proof; use calibrated thresholds and combine complementary tools per variant class.

- **REVEL** (missense): ≥0.773 → PP3 supporting; ≥0.932 → PP3 moderate; ≥0.99 → PP3 strong. Low REVEL supports BP4 at the corresponding calibrated cutoffs (Pejaver 2022).
- **SpliceAI** (splice impact): ≥0.2 supporting, ≥0.5 moderate, ≥0.8 strong (Walker 2023 direction). Use for canonical and non-canonical splice and for exonic variants that may affect splicing.
- **AlphaMissense** (missense): apply the Cheng 2023 likely-pathogenic / likely-benign class thresholds as supporting–moderate evidence.
- **CADD**: phred scores do **not** map cleanly to ACMG strength; do not use CADD as a standalone pathogenicity call. It may contextualise but should not carry PP3.
- State predictor versions when available; use the right tool for the variant class (missense vs splice vs UTR/deep-intronic).

## VUS Hot / Cold

Sub-stratify VUS by how close they sit to LP and by phenotype fit:
- **Hot VUS** — nearer the LP boundary (higher point total, e.g., PM2 + PP3 with additional support), in a phenotype-consistent gene/inheritance; worth functional/segregation follow-up. Flag as higher priority.
- **Cold VUS** — nearer LB (minimal support, phenotype-irrelevant gene, benign-leaning predictors); low priority. Note that its classification may be driven by an unrelated gene–disease context.

Always give the basis (criteria + phenotype reasoning) for the Hot/Cold call.

## Gene–disease validity and databases

Before treating a gene as causal, confirm gene–disease validity (ClinGen), the associated OMIM phenotype (# number), and inheritance. Check ClinVar and the literature (targeted search/PubMed) for the specific variant's prior classification and any functional data — verify, don't recall. Reconcile the Franklin classification with your own ACMG call and explain any difference (Franklin may classify in a gene/disease context that doesn't match this patient's phenotype).

## CNV classification

Use the ACMG/ClinGen 2019 CNV framework (copy-number loss vs gain scoring). Use the file's SEQ Pathogenicity and ACMG Evidence Codes as a starting point, then reason about gene content, dosage sensitivity (ClinGen/DECIPHER, HI/TS scores), size, inheritance, and phenotype overlap. Distinguish a real CNV from artifact (especially the X-chromosome CNV artifact). Consider a CNV as a possible second hit in trans with a small variant.

## Standard evidence to state per variant

Zygosity; gnomAD frequency (exome and genome, with rarity supporting PM2/BS1/BA1); inheritance model and fit; segregation (trio); de novo status with parentage assumption; ClinVar/prior reports; predictor scores against calibrated thresholds; the ACMG criteria applied and (optionally) Tavtigian points; the resulting class; and the phenotype-fit judgement.
