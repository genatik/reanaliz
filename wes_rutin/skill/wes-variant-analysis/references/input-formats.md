# Input Formats

## Solo WES — four CSV files (proband only)

All four are exports; the first three are the user's pre-filtered small-variant lists from Franklin (genoox), the fourth is the CNV list.

1. **Homozygous / compound-heterozygous list** — the primary autosomal-recessive candidates (both true homozygous and genes carrying ≥2 heterozygous hits).
2. **High-quality heterozygous list** — reliable heterozygous calls; the pool for de novo (in trio), autosomal-dominant, X-linked, and the second allele of compound-heterozygous pairs.
3. **Low-quality heterozygous list** — lower-confidence calls (low depth/allele balance, strand/quality flags). Artifact-prone: use cautiously, weight down, and recommend Sanger before any clinical weight. Still worth scanning to rescue a second comp-het allele or an otherwise strong phenotype match — but flag every one for confirmation.
4. **CNV list** — `*_copy_number_variants.csv`.

## Trio WES — twelve files

The same four files for **proband + mother + father** (4 × 3 = 12). Identify each individual by the sample ID in the filename (or ask the user for the mapping). Align genotypes per variant across the trio for de novo, phasing, and segregation.

## Identifying files

- CNV file: filename contains `copy_number_variants` (or columns `Chromosome, Start, End, Copy Number, Length, SEQ Pathogenicity, Gene(s), Exon Numbers, ACMG Evidence Codes`).
- Small-variant files: gene/transcript/HGVS/zygosity/gnomAD/predictor columns. The three tiers are usually distinguished by the user's filename convention or by a quality/zygosity column; if ambiguous, ask which file is which rather than guessing.
- Trio: group by sample ID; confirm proband vs parent if filenames are unclear.

## Column auto-detection (Franklin exports vary)

Read headers first and map flexibly. Typical small-variant fields to locate: Gene; Transcript (NM_… versioned); cDNA/HGVS c.; Protein/HGVS p.; Exon; Zygosity; gnomAD exome AF; gnomAD genome AF; ClinVar; Franklin classification; ACMG classification/criteria; REVEL; CADD; SpliceAI; (sometimes) inheritance, filter status, quality/depth. Don't assume exact header strings — match case-insensitively and by synonym, and report which columns were found.

Read every file with code (pandas/csv), using `encoding='utf-8-sig'` to handle BOM. Normalise into one table per individual, tagging each row with its source tier (homo/comp-het, HQ-het, LQ-het) and keeping CNVs separate.

## CNV file specifics

Columns commonly include Chromosome, Start, End, Copy Number, Length, SEQ Pathogenicity (P / LP / VUS+ / VUS / LB / B), Gene(s), Exon Numbers, ACMG Evidence Codes. Prioritise P/LP/VUS+ and large VUS overlapping phenotype-relevant loci. **Check for the systematic X-chromosome CNV artifact** seen in some runs before calling an X CNV real. Assess overlap of any candidate CNV with the genes implicated by the small-variant analysis (e.g., a second hit in trans).

## Alternative single-file input (the VCF question)

The CSV workflow is **primary** because annotation and predictor scores are already present. A single VCF is supported in two modes:

- **Annotated VCF** (VEP `CSQ`, SnpEff `ANN`, or a Franklin/annotated VCF with gene, consequence, HGVS, gnomAD, ClinVar, predictor fields): parse the INFO annotations directly and proceed as with CSVs. State which annotation source and fields were used.
- **Raw / unannotated VCF** (coordinates + genotypes only): the container has **no network access to annotation databases (Ensembl/VEP, gnomAD servers)**, so gene-level annotation and predictor scores cannot be generated offline here. Do only what is reliable — quality filtering (PASS, depth, GQ, allele balance), zygosity, region/coordinate lookups for specific candidate loci — and then recommend either the Franklin CSV export or an annotated VCF for full analysis. Do not invent gene names or scores for an unannotated VCF.

When a VCF is gzip-compressed, decompress and inspect the header (`##INFO`) first to determine which mode applies.
