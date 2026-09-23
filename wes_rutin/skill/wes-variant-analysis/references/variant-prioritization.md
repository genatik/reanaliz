# Variant Prioritisation & Inheritance Modelling

The goal is to move from hundreds of pre-filtered variants to a short, defensible list of candidates ranked by how well each explains the patient's phenotype. Phenotype fit, inheritance consistency, classification, and call quality together set priority.

## Phenotype anchoring (do this first)

Translate the clinical picture into HPO terms and a shortlist of candidate disorders/genes (OMIM/Orphanet), including the inheritance each would imply. This shortlist is the lens for every subsequent step: a variant in a gene on or near this list, with matching inheritance and zygosity, outranks a "more damaging" variant in an irrelevant gene.

## Inheritance models

- **AR homozygous** — from the homozygous list; strong candidates when consanguinity is present. Confirm true homozygosity vs a deletion-in-trans masquerading as homozygous (check the CNV list over the locus).
- **AR compound heterozygous** — two heterozygous hits in the same gene. In trio, **phase** them: each variant should come from a different parent. A second allele may sit in the high-quality OR low-quality het list, or be a CNV — scan all, but flag low-quality second hits for confirmation.
- **De novo** (trio) — present in proband, absent in both parents. Powerful for dominant disorders; state the parentage assumption and recommend confirmation (the apparent de novo could be a call artifact or parental mosaicism). Prioritise de novo in constrained, phenotype-relevant genes.
- **Autosomal dominant** (inherited) — segregating with an affected parent; weigh penetrance/expressivity.
- **X-linked** — hemizygous in an affected male; carrier mother. Mind the X-CNV artifact and correct handling of X zygosity.

## Quality tiers

- **Homozygous / comp-het list**: primary AR track.
- **High-quality het**: reliable; the main pool for de novo/AD/X-linked/second comp-het allele.
- **Low-quality het**: artifact-prone. Use only to (a) rescue a plausible second comp-het allele, or (b) surface a strong phenotype match — and in both cases flag explicitly for Sanger confirmation before it carries clinical weight. Do not report a low-quality het as causal without orthogonal confirmation.

## Trio logic

For each proband candidate, record the parental genotypes and derive: de novo (0/0 in both parents), biparental comp-het (each allele from one parent), AR homozygous (both parents carriers), or inherited dominant/X-linked. Inconsistencies (e.g., a "de novo" also seen in a parent's low-quality list) should be surfaced, not hidden. Segregation with phenotype in the family strengthens or weakens a candidate.

## CNV interpretation

Prioritise P/LP/VUS+ CNVs and large VUS overlapping phenotype-relevant genes. For each, consider gene content, dosage sensitivity, size, inheritance (de novo vs inherited, from trio), and whether it acts as a second hit in trans with a small variant. Exclude the systematic X-chromosome CNV artifact before calling an X CNV. Reconcile with the small-variant findings.

## Prioritisation output

Group findings as:
1. **Primary candidate(s)** — best explain the phenotype (P/LP or Hot VUS with strong fit and consistent inheritance).
2. **Secondary candidates** — plausible but weaker (partial fit, VUS, needs data).
3. **VUS to watch** — Hot VUS worth functional/segregation follow-up.
4. **CNV findings.**
5. **Secondary / incidental findings** — variants on the ACMG SF list unrelated to the indication; flag these for consent/return-of-results considerations rather than folding them into the primary interpretation.

State plainly whether the phenotype is **explained, partially explained, or unexplained**, and what would resolve remaining uncertainty (Sanger, parental testing, SpliceAI, RNA/functional studies, deep phenotyping, or later reanalysis).
