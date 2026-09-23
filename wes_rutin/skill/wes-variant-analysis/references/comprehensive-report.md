# Comprehensive Analysis Report (Kapsamlı Analiz Raporu)

The working analysis document: complete, transparent reasoning for every candidate, in Turkish. This is what the geneticist reviews to make the call. It is more detailed than the result report and shows the ACMG/Tavtigian logic, not just conclusions.

## Structure

1. **Başlık / künye** — case ID, analysis type (Solo/Trio WES), date, reference genome (GRCh38/hg38), platform and capture kit if known, analysis scope (WES ± CNV).

2. **Klinik özet** — age, sex, phenotype (with HPO terms), consanguinity, family history, suspected disorder/inheritance hypothesis. State the candidate-disorder shortlist derived from the phenotype.

3. **Analiz özeti / QC** — files received and identified (the four tiers; trio individuals), variant counts per tier, parsing notes, and any quality caveats (e.g., low-quality het pool, X-CNV artifact check).

4. **Öncelikli bulgular (primary candidates)** — for each, a full record:
   - Gene (*italic*), transcript (NM_… versioned), HGVS c. and p., exon, zygosity.
   - gnomAD (exome/genome) AF; ClinVar; Franklin classification.
   - Predictor scores against calibrated thresholds (REVEL/SpliceAI/AlphaMissense).
   - **ACMG criteria applied + Tavtigian points + class**; for VUS, **Hot/Cold** with justification.
   - Gene–disease/OMIM context (verified), inheritance and **phenotype-fit reasoning**.
   - Trio interpretation (de novo / phased comp-het / segregation) where applicable.
   - **Sonraki adım** — Sanger, parental testing, SpliceAI, functional/RNA, deep phenotyping.
   A per-variant table plus a short prose interpretation reads best.

5. **İkincil adaylar & izlenecek VUS'lar** — weaker or uncertain candidates, briefly, with why they rank lower and what would change that.

6. **CNV değerlendirmesi** — prioritised CNVs with classification and phenotype overlap; artifact exclusion noted; any second-hit-in-trans logic.

6b. **AlphaGenome Atlas değerlendirmesi** — heading: "AlphaGenome Atlas değerlendirmesi (araştırma amaçlı)". Source: `kanit/alphagenome_rapor.txt` (first block) and `kanit/alphagenome.csv`. Content: one method paragraph (what was queried, how many variants, Atlas vs live-model vs unscored counts); a table of the variants in the *yüksek* and *orta* categories plus every variant discussed in sections 4–5 (Gen | Varyant | AVI PHRED | En yüksek kantil (modalite, doku) | Birleşik splicing | Ekspresyon log-FC | Kategori | Yorum); a short interpretation tying strong signals to the phenotype-relevant candidates and stating explicitly when no candidate carries a meaningful regulatory/splicing signal; the standard limits sentence (research use, not a substitute for PP3/BP4, low score does not exclude). If the step was skipped, one sentence saying so and why. See `references/alphagenome.md`.

7. **İkincil/insidental bulgular** — ACMG SF-list findings unrelated to the indication, flagged for consent/return-of-results discussion (kept separate from the primary interpretation).

8. **Sonuç ve yorum** — is the phenotype explained / partially explained / unexplained? The leading hypothesis, and the concrete steps to confirm or resolve it.

8b. **ADAY GEN YAKLAŞIMI (negatif sonuçlarda zorunlu)** — when no known disease gene explains the phenotype, this section carries the research-level candidate(s): variants in genes with no established OMIM disease association (or a clearly different one). Per candidate, in ranked order: **(1)** varyant kaydı tablosu; **(2)** gen kısıtı (pLI/LOEUF, gnomAD homozigot sayısı, sürümüyle); **(3) "Neden aday gen?"** — a 150–300 word narrative rationale explaining how the candidate surfaced, why the variant is deleterious, the pathophysiological chain to *this* phenotype (naming any known disease gene in the same pathway/complex, with its OMIM number), how the inheritance fits, and **what argues against it**; **(4) bilimsel kanıtlar** — each as claim → real citation (PMID/DOI) → short summary of what the study actually showed → relevance to this patient, grouped by function/expression, pathway & known-gene parallels, model organism, prior reports; **(5)** aday gücü (strong/moderate/weak + ClinGen validity level); **(6)** sonraki adımlar (Sanger, segregation, GeneMatcher, functional studies, reanalysis); **(7)** kaynakça — numbered list of retrieved references with real PMIDs/DOIs. Every claim verified by look-up — see `references/candidate-gene-approach.md`. Head the section clearly: **araştırma amaçlıdır, klinik tanı değildir.**

9. **Kısıtlılıklar** — coverage/pipeline limits, that WES misses certain variant classes (deep-intronic, repeat expansions, some SVs, low-level mosaicism), low-quality-call caveats, and that a negative result does not exclude a genetic cause; reanalysis may reclassify later.

10. **Kaynaklar** — any gene–disease/variant references actually looked up (verified), with links where useful; when AlphaGenome was run, add the two AlphaGenome references from `alphagenome_rapor.txt`.

## Tone

Rigorous and transparent: show the evidence and the reasoning, quantify where possible, and separate what is established from what is inferred. Decision support — the geneticist signs off.
