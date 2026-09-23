---
name: wes-variant-analysis
description: Analyse whole-exome sequencing (WES) results and produce two Turkish Word reports — a comprehensive analysis and a formal clinical result report. Use whenever WES variant files (Franklin/genoox CSV exports, or a VCF) plus clinical information are provided and variant analysis, pathogenicity assessment, or a report is requested. Covers solo WES (homozygous/comp-het, high- and low-quality het, CNV lists) and trio WES (same files for proband, mother, father). Trigger on asks like "bu WES'i analiz et", "solo/trio WES", "ekzom analizi", "varyant değerlendirmesi", "ACMG sınıflandırması", "de novo / compound-het", "CNV analizi", "sonuç raporu", "reanaliz", "aday gen". Applies ACMG 2015 + Tavtigian 2020, calibrated in-silico thresholds and VUS Hot/Cold. When no known disease gene explains the phenotype, it moves to a mandatory research-level candidate-gene approach (genes lacking OMIM disease association, argued with constraint, expression, pathway and model evidence). Decision support; the geneticist signs off.
---

# WES Variant Analysis — Clinical Exome Analysis & Reporting

This skill supports an experienced clinical geneticist in analysing whole-exome sequencing (WES) data and producing two deliverables in Turkish for every case:

1. **Kapsamlı analiz raporu** — the full working analysis: every candidate variant with complete ACMG/Tavtigian reasoning, phenotype correlation, VUS Hot/Cold calls, prioritisation, and next steps.
2. **Sonuç raporu** — the formal clinical result report: patient-information header, a NORMAL/ANORMAL result box, the causal/reportable variant(s), and recommendations.

The user pre-filters variants in Franklin (genoox) and exports them as CSVs. The skill's job is to turn those exports plus the clinical picture into a rigorous, phenotype-anchored analysis and two polished Word documents — not merely a variant list.

**This is decision support, not autonomous diagnosis.** The skill does the analysis and drafting; the clinical geneticist reviews every call and signs off. Language of output is **Turkish**, with variant nomenclature in standard HGVS.

---

## Core principles

1. **Phenotype first.** The patient's clinical picture drives everything. Map findings to HPO terms and candidate OMIM disorders early, and judge every variant by how well it fits the phenotype, inheritance, and family history. A perfectly "damaging" variant in a phenotype-irrelevant gene is a low-priority finding; say so.

2. **Classify by the current framework, with the criteria shown.** Use ACMG/AMP 2015 **and** the Tavtigian 2020 point-based Bayesian refinement (ClinGen SVI). State the specific evidence codes applied (PVS1, PS3, PM2, PP3, BS1…) and, where useful, the point total and resulting class. Apply **calibrated in-silico thresholds** (REVEL, SpliceAI, AlphaMissense per Pejaver 2022 / Walker 2023 / Cheng 2023), never a single predictor as proof. See `references/acmg-tavtigian.md`.

3. **Never fabricate.** Variant-level data (gene, transcript, HGVS, zygosity, gnomAD, predictor scores, Franklin class) comes **only** from the provided files. Gene–disease validity, OMIM numbers, ClinVar status, and prior reports are verified by targeted search/PubMed when asserted — not recalled from memory. If a claim can't be supported, flag it. The container has no network to annotation databases, so the analysis relies on the annotated exports the user provides plus deliberate look-ups.

4. **Be quality-aware.** The three small-variant lists carry different confidence: homozygous/compound-het (primary AR candidates), high-quality heterozygous (reliable; de novo/AD/X-linked/comp-het), and low-quality heterozygous (artifact-prone — use cautiously, weight down, and recommend orthogonal confirmation before any clinical weight). Treat CNVs on their own track. See `references/variant-prioritization.md`.

5. **Two reports, every time, as Word files.** Produce both the comprehensive analysis report and the clinical result report, in Turkish, as `.docx`. See `references/comprehensive-report.md`, `references/result-report.md`, `references/docx-format.md`.

6. **State confirmation and limits.** Recommend Sanger confirmation, parental segregation, SpliceAI/functional work where relevant; note coverage/pipeline limitations; and make explicit that a negative/inconclusive result does not exclude a genetic cause (reanalysis may help later).

---

## Inputs

Read `references/input-formats.md` for the details. In brief:

**Solo WES — 4 CSV files (proband):**
1. Homozygous / compound-heterozygous variants
2. High-quality heterozygous variants
3. Low-quality heterozygous variants
4. CNVs (`*_copy_number_variants.csv`)

**Trio WES — 12 files:** the same four files for **proband + mother + father**.

**Alternative single-file input:** a single **annotated** VCF (VEP/SnpEff/Franklin, with ANN/CSQ + gnomAD) can be parsed directly. A **raw/unannotated** VCF can only be quality/coordinate-filtered here (no offline gene annotation); recommend the Franklin CSV export or an annotated VCF instead. The CSV workflow is primary.

**AlphaGenome Atlas outputs (routine pipeline cases):** the WES routine (`_sistem/rutin.py`) queries Google DeepMind's AlphaGenome Atlas for the proband's candidate variants and writes `kanit/alphagenome.csv`, `kanit/alphagenome_detay.csv`, `kanit/alphagenome_ozet.json` and `kanit/alphagenome_rapor.txt` (ready-made Turkish report blocks). Read `references/alphagenome.md` and use these files in every report. If they are missing for a routine case, run `python rutin.py --alphagenome <OlguKodu>` from `_sistem/` (no Genomize login needed) before writing; if `alphagenome_ozet.json` says the step was skipped (no API key / hg19 / no package), state in the report that AlphaGenome was not run.

**Clinical information** arrives in the prompt or an uploaded document: age, sex, phenotype, consanguinity, family history, suspected disorder/gene, inheritance hypothesis. Ask for it if missing — it is required for a meaningful analysis.

---

## Workflow

### Phase 1 — Intake
Determine solo vs trio and identify each file (by filename and columns; CNV file by `copy_number_variants` / CNV columns). Read the clinical information; if absent, request age, sex, phenotype, consanguinity, family history, and any inheritance hypothesis. Establish HPO terms and a shortlist of candidate OMIM disorders/genes from the phenotype. Note genome build (GRCh38 default), platform and capture kit if given.

### Phase 2 — Parse & QC
Read every CSV with code (`view` the relevant SKILL.md first if creating files; use `pandas`/`csv`). Auto-detect columns (Franklin naming varies) and normalise into one variant table per individual, tagging each small variant with its **quality tier** (homo/comp-het, HQ-het, LQ-het) and keeping CNVs separate. For trio, map proband/mother/father and align genotypes per variant. Report counts and any parsing issues. Watch for known artifacts (e.g., systematic X-chromosome CNV artifact).

### Phase 3 — Filter & inheritance modelling
Against the phenotype, apply inheritance models: AR homozygous, AR compound-heterozygous (require two hits; phase via parents in trio), de novo (trio: absent in both parents — confirm parentage assumption), autosomal dominant, and X-linked. Use the quality tiers: a low-quality het rescuing a second comp-het allele or a strong candidate is worth noting but flagged for confirmation. See `references/variant-prioritization.md`.

### Phase 4 — Classify
For each candidate, apply ACMG 2015 + Tavtigian 2020 with calibrated predictors, assign a class (P/LP/VUS/LB/B) and, for VUS, a **Hot/Cold** call with justification. Verify gene–disease validity, OMIM, and ClinVar/prior-report status by targeted search/PubMed when you assert them. Classify CNVs with the ACMG/ClinGen CNV framework using the file's evidence codes plus dosage sensitivity. See `references/acmg-tavtigian.md`.

### Phase 4b — AlphaGenome Atlas (regulatory / splicing effect evidence)
For every candidate discussed in the report (and for any de novo / homozygous / target-gene variant that is otherwise hard to classify), read its AlphaGenome row: AVI PHRED score, the merged splicing score, the strongest calibrated quantile and its modality/tissue, and the AVI feature attributions. Use it as **secondary, research-level computational evidence**: it never replaces REVEL/SpliceAI-based PP3/BP4, never upgrades a class on its own, and low scores never exclude a variant. A strong splicing signal (merged ≥ 1.0 or splice-site quantile ≥ 0.99) in a phenotype-relevant gene raises the candidate's priority and triggers an RNA-level confirmation recommendation; a strong tissue-specific expression/chromatin signal on a non-coding or synonymous variant is what makes such a variant worth discussing at all. See `references/alphagenome.md` for thresholds, wording and limits.

### Phase 5 — Prioritise
Rank findings by phenotype fit × classification × quality: primary candidate(s) that explain the phenotype, secondary candidates, VUS to watch, CNV findings, and any secondary/incidental findings (ACMG SF list) — flag the last for consent considerations. State clearly whether the phenotype is explained, partially explained, or unexplained.

### Phase 6 — Candidate-gene approach (MANDATORY when the analysis is negative)
**Trigger:** no variant adequately explains the phenotype in a known disease gene — i.e., the result would be reported as NORMAL/negative (or only phenotype-irrelevant findings, or a partial explanation the geneticist considers insufficient).

When this happens, **do not stop at "negatif".** Move to the candidate-gene approach: look for a plausible variant in a gene **not yet associated with any human disease in OMIM** (no OMIM phenotype/# entry), or associated only with a clearly different phenotype, and argue the case with explicit evidence.

This is **research-grade hypothesis generation, not a clinical diagnosis** — label it as such everywhere. The bar for evidence is deliberately high, because candidate-gene reasoning is where speculation creeps in. Follow `references/candidate-gene-approach.md`, which requires: a **mandatory PubMed/database literature search** (no gene function from memory, no fabricated citations); every piece of evidence presented as **claim → real citation with PMID/DOI → a short summary of what that study actually showed → what it means for this patient**; a **narrative rationale** explaining why this gene surfaced as a candidate at all (including the counter-case against it); a strength grade; and a confirmation/falsification plan.

The candidate discussion appears **at the end of the comprehensive analysis report** as its own section, with the pathophysiological rationale, the cited evidence with summaries, and a per-candidate reference list. It does **not** move the clinical result report from NORMAL to ANORMAL — the result report stays negative and refers to the candidate section as research-level.

### Phase 7 — Comprehensive analysis report (Word)
Build the full analysis report per `references/comprehensive-report.md` and `references/docx-format.md`. Turkish, HGVS, per-variant reasoning tables, prioritisation, next steps — and, for negative cases, the candidate-gene section at the end.

### Phase 8 — Clinical result report (Word)
Build the formal result report per `references/result-report.md`: patient-info header, NORMAL/ANORMAL box, causal/reportable variant(s), interpretation and recommendations, teal-themed and submission-clean.

Save both to `/mnt/user-data/outputs/`, validate, and `present_files`.

---

## Reference files

- `references/input-formats.md` — the 4-CSV / 12-CSV structure, column auto-detection, filename/column identification, trio mapping, and the VCF fallback modes.
- `references/acmg-tavtigian.md` — ACMG 2015 criteria, Tavtigian 2020 point framework, calibrated in-silico thresholds (Pejaver/Walker/Cheng), VUS Hot/Cold logic, gene–disease validity, CNV classification.
- `references/variant-prioritization.md` — phenotype-driven filtering, inheritance models, quality-tier handling, trio logic (de novo, comp-het phasing, segregation), CNV interpretation, secondary findings.
- `references/alphagenome.md` — AlphaGenome Atlas (AVI score, modality quantiles, merged splicing): what the routine's `kanit/alphagenome*` files contain, how to weigh them next to ACMG evidence, the report section and sentences to add, and the non-clinical-use limits.
- `references/candidate-gene-approach.md` — **the negative-case workflow**: re-mining variants in genes with no OMIM disease association, the four-axis evidence dossier (variant, constraint, pathophysiology, model/matchmaking), candidate grading, and how to report it as research-level without changing the clinical result.
- `references/comprehensive-report.md` — structure and section-by-section content of the comprehensive analysis report.
- `references/result-report.md` — structure of the formal clinical result report.
- `references/docx-format.md` — how to build both Word documents (theme, fonts, tables, patient header, result box, page numbers).

---

## Style notes

- Output in **Turkish**; variant nomenclature in **HGVS** with versioned transcripts (NM_…), gene symbols italicised, protein changes in three-letter code, genome build stated.
- Show ACMG criteria codes and Tavtigian points; don't assert a class without its evidence.
- Distinguish confidence: high-quality vs low-quality het, and always recommend orthogonal confirmation (Sanger) for reportable variants.
- Decision support only: the geneticist reviews and signs off; never phrase output as a final diagnosis on Claude's authority.
- Never fabricate variant data, OMIM numbers, ClinVar entries, or literature; verify by look-up or flag.
- AlphaGenome Atlas scores are research-level computational predictions: report them in their own section and in the method sentence, label them as such, never present them as ACMG criteria and never let them alone change a class or the NORMAL/ANORMAL outcome.
