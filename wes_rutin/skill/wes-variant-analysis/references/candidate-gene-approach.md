# Candidate-Gene Approach (Aday Gen Yaklaşımı)

Invoked when the standard analysis is **negative**: no variant in an established disease gene explains the phenotype. Roughly 50–75% of clinical exomes end here, and a substantial share of them are unsolved not because the data are empty but because **the causal gene is not yet linked to human disease**. This phase looks for exactly that.

## What this is — and what it is not

- **It is** structured, evidence-based hypothesis generation: identifying a gene with no established OMIM disease association (or an association with a clearly different phenotype) in which this patient carries a plausibly deleterious, inheritance-consistent variant, and building the pathophysiological argument for it.
- **It is not** a clinical diagnosis. A candidate gene has, by definition, insufficient evidence for clinical reporting. It cannot be used for clinical decisions, prognosis, or reproductive counselling on its own, and it must never appear as a causal finding in the result report.

Label it plainly in the report: **"Aday gen yaklaşımı — araştırma amaçlıdır, klinik tanı değildir."**

The discipline here matters more than anywhere else in the skill. A candidate-gene section is easy to write persuasively and hard to write honestly: any gene can be made to sound plausible with a selectively-told pathway story. Resist that. The output must show the evidence, name the gaps, and remain falsifiable.

## Step 1 — Re-mine the data with the OMIM filter inverted

Standard analysis discards variants in genes with no disease association. This phase deliberately looks at them.

From the already-parsed variant tables, select variants that are:
- **Rare** — very low/absent in gnomAD (population frequency consistent with the disorder's expected prevalence and inheritance; homozygotes absent for a presumed AR condition; pLI/LOEUF-relevant for AD).
- **Plausibly deleterious** — LoF (nonsense, frameshift, canonical splice ±1/2) carries the most weight; missense needs calibrated predictor support (REVEL/AlphaMissense) and ideally a functional-domain hit; SpliceAI for splice effects.
- **Inheritance-consistent** with the pedigree: homozygous (especially with consanguinity), compound heterozygous (phased where trio data exist), **de novo** (trio — the single most powerful signal for a novel dominant gene), or hemizygous X-linked in an affected male.
- **In a gene with no established OMIM phenotype** (no # phenotype entry), or with an OMIM entry for a distinctly different disorder (in which case the case may be a phenotype expansion rather than a novel gene — say which you are proposing).

Also revisit the **low-quality heterozygous list** here: a candidate second allele may be hiding there. Flag any such variant for mandatory Sanger confirmation before it carries any weight.

## Step 2 — Build the evidence dossier for each candidate

Do not assert a candidate without working through these four axes. Verify everything by look-up (PubMed, and web sources for OMIM/gnomAD/ClinGen/GTEx/protein databases); **never recall gene function from memory.**

### 2.0 — Mandatory literature search (do this before writing anything)

Every biological claim about a candidate gene must come from a paper you actually retrieved in this session. Never write a reference, PMID, DOI, author, year or journal from memory — fabricated citations are the characteristic failure mode here, and a candidate-gene argument built on invented sources is worse than no argument at all.

Use the PubMed tools (load with `tool_search` first: `search_articles`, `get_article_metadata`, `find_related_articles`, `get_full_text_article`). Search in layers for each candidate:
- `<GENE>` function / molecular role
- `<GENE>` + the key phenotype terms (e.g., "epilepsy", "microcephaly", "hipotoni")
- `<GENE>` + knockout / mouse / zebrafish / model
- `<GENE>` + the pathway or complex it belongs to
- `<GENE>` + the established disease genes it interacts with
- `<GENE>` + "de novo" / "candidate" / "novel gene" — has anyone already proposed it?

Capture real metadata (authors, title, journal, year, PMID, DOI) with `get_article_metadata`. Use `web_search`/`web_fetch` for gnomAD constraint, GTEx/Human Protein Atlas expression, MGI/ZFIN model phenotypes, STRING/Reactome pathway membership, OMIM and ClinGen status. If a search returns nothing to support a claim, **say so explicitly** ("bu gen için model organizma verisi bulunamadı") rather than softening it into vague plausibility.

### 2.1 — How every piece of evidence must be presented

This is a hard formatting requirement, not a preference. A bare assertion ("bu gen sinaptik veziküllerde rol oynar") is unusable — the geneticist cannot check it, weigh it, or cite it. Each piece of evidence is presented as a three-part unit:

1. **The claim** — one specific sentence.
2. **The source** — full citation: authors, journal, year, **PMID and/or DOI** (real, retrieved). For databases: name + version/access date (e.g., "gnomAD v4.1", "GTEx v8", "MGI, erişim: [tarih]").
3. **A short summary of what that study actually showed** — 1–3 sentences: the model or system used, the key result, and its limitation if relevant. Not just the title; what was *found*.
4. **Relevance line** — "Bu hasta için anlamı:" one sentence tying it to *this* patient's variant/phenotype.

Example of the required density (illustrative structure only — never reuse these as real facts):

> **Kanıt:** *GENE X* knockout farelerde kortikal nöronal migrasyon defekti ve nöbet fenotipi gözlenmiştir.
> **Kaynak:** Author A, et al. *J Neurosci.* 2019;39(4):123–135. PMID: 12345678. doi:10.xxxx/yyy
> **Özet:** Homozigot knockout farelerde E14.5'te radyal migrasyon belirgin şekilde bozulmuş, hayvanların %70'inde postnatal 3. haftadan itibaren spontan nöbet gelişmiştir; heterozigot hayvanlar etkilenmemiştir (resesif model).
> **Bu hasta için anlamı:** Hastadaki biallelik LoF varyantı ve kortikal malformasyon + dirençli epilepsi tablosu, bu resesif model ile mekanistik olarak uyumludur.

Apply this to the strongest 3–6 pieces of evidence per candidate — enough to carry the argument, not an exhaustive literature dump. Weak or absent evidence gets stated as such, in the same explicit way.

**A. Variant-level evidence**
Gene (italic), versioned transcript, HGVS c./p., zygosity, exon/domain, gnomAD frequency (exome+genome; homozygote count), predictor scores against calibrated thresholds, quality tier, and — for trio — de novo status or phasing. Note whether Sanger confirmation is pending.

**B. Gene-level constraint and tolerance**
- **gnomAD constraint**: pLI / LOEUF (intolerance to LoF — relevant for a dominant/de novo hypothesis), missense z-score, o/e ratios. Give the gnomAD version.
- Absence of homozygous LoF individuals in gnomAD supports a recessive lethal/severe hypothesis.
- Presence of many LoF carriers argues against a LoF-based dominant mechanism — state it if so.

**C. Pathophysiological link to the phenotype (the core argument)**
Establish each of the following with the citation + summary + relevance structure above:
- **Molecular function** of the gene product and the pathway it acts in.
- **Expression pattern** — is it expressed in the affected tissue(s) at the relevant developmental stage? (GTEx, Human Protein Atlas, developmental expression atlases; give version/access date.)
- **Pathway/interactome proximity to known disease genes**: does it interact with, regulate, or sit in the same complex/pathway as genes already causing a phenotype resembling the patient's? A gene in the same complex as an established disease gene with an overlapping phenotype is a strong argument — and the *known* gene's disease and its OMIM number must be given so the parallel is checkable. (STRING/BioGRID/Reactome + literature.)
- **Mechanistic coherence**: does the predicted variant effect (LoF vs missense/dominant-negative) fit the proposed mechanism and inheritance?

**D. Model-organism and functional evidence**
- Animal/cellular models: mouse (MGI), zebrafish (ZFIN), fly, C. elegans — does disruption produce a phenotype recapitulating the patient's? Summarise the actual model phenotype, not just its existence.
- Any existing functional data on the gene or on this variant.
- **Matchmaking**: has a similar patient been reported? Search the literature and preprints for other patients with variants in the same gene and an overlapping phenotype, and recommend submission to **GeneMatcher / Matchmaker Exchange**. A second unrelated patient is often the decisive evidence.

## Step 3 — Write the narrative rationale (why *this* gene, in *this* patient)

Tables and citation blocks give the evidence; they do not give the **argument**. Each candidate therefore also gets a short piece of connected prose (roughly 150–300 words) — the part a colleague reads to understand *why this gene came onto the radar at all*. Written as explanation, not as a list. It must cover, in a natural flow:

1. **How the candidate surfaced** — what the standard analysis found (or failed to find), and what made this variant stand out once the OMIM filter was inverted: e.g., "known disease genes yielded nothing consistent with the phenotype; on re-mining, the only biallelic LoF variant in a constrained gene with no OMIM disease entry was …".
2. **Why the variant is plausibly deleterious** — variant type, constraint, frequency, predictors, in one or two sentences.
3. **Why the gene is biologically plausible for *this* phenotype** — the pathophysiological chain, stated as a causal argument: gene function → the process it serves → the tissue/developmental window → how disruption would produce the patient's specific findings. Where a known disease gene sits in the same pathway/complex and causes an overlapping phenotype, make that parallel explicit (and name the disease + OMIM number) — this is usually the strongest single argument available.
4. **How the inheritance fits** — de novo in a constrained gene, biallelic in a consanguineous family, etc., and why that fits the proposed mechanism.
5. **What argues against it** — the honest counter-case: what is missing, what doesn't fit, what an unconvinced reviewer would say. Every candidate section must contain this; a rationale with no counter-argument is advocacy, not analysis.

The tone is explanatory and specific. Avoid generic pathway prose ("bu gen hücresel homeostazda rol oynar") — that fits any gene and is therefore worthless. If the mechanistic chain has a weak link, name the weak link.

## Step 4 — Grade the candidate honestly

Rank candidates (Aday 1, Aday 2, …) and, for each, state a strength judgement with its basis:

- **Strong candidate** — de novo or biallelic LoF in a constrained, phenotype-relevant, appropriately-expressed gene, with a coherent mechanism and supporting model-organism data; ideally a matching second patient.
- **Moderate candidate** — inheritance-consistent and biologically plausible, but with a gap (e.g., missense with predictor support only, or no functional/model data, or expression not confirmed in the relevant tissue).
- **Weak candidate** — plausible on one axis only; report for completeness but do not over-argue.

Align this with the **ClinGen gene–disease validity framework** (Definitive → Strong → Moderate → Limited → No known association): a novel candidate is by definition at "Limited" or "No known association", and the report should say what evidence would move it up.

## Step 5 — State what is missing and what would resolve it

Every candidate section ends with the falsification/confirmation plan:
- Sanger confirmation of the variant (and of de novo status, with parentage).
- Segregation in the family (additional affected/unaffected relatives).
- **GeneMatcher/Matchmaker Exchange submission** to find a second patient.
- Functional work: expression/localisation, cellular assay, model organism, RNA studies (for splice candidates).
- Deep phenotyping to sharpen the match.
- Reanalysis in 12–18 months — new gene–disease associations are published continuously, and today's candidate is often tomorrow's established gene.
- Alternative explanations that WES cannot exclude: deep-intronic/regulatory variants, repeat expansions, structural variants, mosaicism, imprinting/UPD, non-genetic causes.

## Reporting

The candidate-gene section goes **at the end of the comprehensive analysis report**, clearly headed and clearly labelled as research-level (**"araştırma amaçlıdır, klinik tanı değildir"**).

Per candidate, in this order:
1. **Varyant kaydı** — table (gene, transcript, HGVS c./p., zygosity, exon/domain, gnomAD, predictors, quality tier, de novo/phase).
2. **Gen kısıtı** — pLI/LOEUF, missense z, gnomAD homozygote count (with version).
3. **Neden aday gen? (gerekçe)** — the narrative rationale from Step 3, including the counter-case.
4. **Bilimsel kanıtlar** — the evidence units from Step 2.1, each with **claim → citation (PMID/DOI) → what the study showed → relevance to this patient**. Group by axis (function/expression, pathway & known-gene parallels, model organism, prior candidate reports).
5. **Aday gücü** — strong/moderate/weak + ClinGen validity level, with basis.
6. **Sonraki adımlar** — the Step 5 plan.
7. **Kaynakça** — numbered list of the retrieved references for this candidate (real PMIDs/DOIs only), so the geneticist can go straight to the papers.

Additional rules:
- **All literature and database claims must be verified by look-up and cited.** No remembered gene functions, no invented OMIM/PubMed IDs. If evidence for a link is thin, say it is thin.
- The **clinical result report stays NORMAL/negative.** Add only a brief pointer: that a research-level candidate is discussed in the comprehensive report, that it is not a clinical diagnosis, and that further investigation/consent (research context, possible functional studies, matchmaking) may be offered.
- Consider whether the family should be counselled about research participation and about the possibility of future reclassification.
