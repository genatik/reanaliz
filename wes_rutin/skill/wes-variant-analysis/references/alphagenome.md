# AlphaGenome Atlas — regulatory & splicing effect evidence

Google DeepMind's **AlphaGenome** (Avsec et al., *Nature* 2026, doi:10.1038/s41586-025-10014-0) predicts the molecular consequences of a DNA change across modalities (RNA-seq expression, splice sites / splice-site usage / splice junctions, polyadenylation, ATAC/DNase accessibility, ChIP-TF and ChIP-histone, CAGE/PRO-cap TSS activity, 3D contact maps). **AlphaGenome Atlas** (Cheng et al. 2026, https://alphagenome.google/atlas) is the pre-computed, genome-wide (GRCh38) version of those scores for every possible SNV plus observed indels, together with the **AVI (AlphaGenome Variant Impact)** score and its SHAP feature attributions.

The WES routine (`_sistem/rutin.py` → `alphagenome_sorgu.py`) queries the Atlas API for the proband's candidate variants (phenotype, rare-LoF, ClinVar-pathogenic, tier and rare-homozygous axes plus `DENOVO_*` and `ORTAK_*` lists, after population-frequency ≤ 2 % and internal-cohort filters) and writes into `kanit/`:

| File | Content |
|---|---|
| `alphagenome.csv` | one row per candidate: `avi`, `avi_yorum`, `avi_katki`, `en_yuksek_kantil` + `en_yuksek_modalite`, `splicing_birlesik`, per-modality `<mod>_ham` / `<mod>_kantil` / `<mod>_doku` / `<mod>_gen`, `kategori` (yuksek/orta/dusuk), `durum` (atlas / model / bulunamadi / hata / sorulamadi), Turkish `yorum` |
| `alphagenome_detay.csv` | variant × scorer × tissue long table (top 5 tissues/genes per scorer) |
| `alphagenome_ozet.json` | run status (`durum`, `neden`), counts, server scorer names (`sunucu_skorlari`), errors |
| `alphagenome_rapor.txt` | ready-made Turkish blocks: the comprehensive-report section, the one-sentence method line for the result/official reports, and the two references |

If the files are missing for a routine case: `cd _sistem && python rutin.py --alphagenome <OlguKodu>` (no Genomize login needed; needs `pip install alphagenome` and `ALPHAGENOME_API_KEY`). If `alphagenome_ozet.json` says `durum: atlandi` (no key, hg19, no package) or `hata`, do not invent scores — say in the report that AlphaGenome was not run and why.

## Reading the scores

- **AVI (PHRED)** — rank of the variant among all human SNVs: 10 = top 10 %, 20 = top 1 %, 30 = top 0.1 %. Range 0–55+. Above ~45 the score is driven by protein-truncation/AlphaMissense/splicing/conservation features; 22.5–45 is dominated by splicing and coding features (core splice sites peak at 32.5–35); 5–22.5 is the *cis*-regulatory regime (accessibility, TF/histone signals, UTR/synonymous/splice-region variants); complex-trait causal variants often sit at 0–5. The Atlas paper deliberately recommends **ranking over hard cut-offs** and region-/application-aware thresholds. In the GREGoR rare-disease analysis, de novo variants were ranked by AVI and the top 1 % (AVI ≥ 20) were reviewed case by case.
- **`avi_katki`** — the three largest SHAP contributions (e.g. `SPLICING:+2.30; PHASTCONS:+0.90`): tells *why* AVI is high (splicing vs chromatin vs conservation vs protein).
- **Calibrated quantile (`*_kantil`, −1…1)** — the raw modality score ranked against a background of common variants (gnomAD MAF > 1 %). |0.99| means "more extreme than 99 % of common variants" for that scorer and track; the sign gives direction (expression −: predicted decrease). Use the quantile to judge whether a signal is unusual and the raw value (`*_ham`, e.g. log-fold change) for its magnitude.
- **`splicing_birlesik`** — max(splice-site) + max(splice-site usage) + max(splice-junction)/5 across genes and tissues (the AlphaGenome paper's merged splicing score used for ClinVar mis-splicing). Empirically most variants lie in 0–6; > 1.0 generally indicates a large effect, 0.5–1.0 a possible effect.
- **`kategori`** — a sorting aid only: *yuksek* if AVI ≥ 20 or |kantil| ≥ 0.99 or splicing ≥ 1.0; *orta* if AVI ≥ 10 or |kantil| ≥ 0.95 or splicing ≥ 0.5; else *dusuk*. It is **not** a clinical threshold.
- **`durum`** — `atlas` (pre-computed lookup), `model` (variant absent from the Atlas — usually a rare indel — scored with the live model over a 1 Mb window; no AVI available), `bulunamadi` (absent and the live-model fallback was off/exhausted), `hata` (API error), `sorulamadi` (mitochondrial, N bases, > 50 bp, unparsable key).

## How to weigh it against ACMG evidence

1. AlphaGenome is **secondary, research-level computational evidence**. The calibrated tools already in the pipeline (REVEL, SpliceAI, AlphaMissense) carry PP3/BP4; AlphaGenome is reported alongside them, never as a criterion code and never as the sole reason to move a class or to change NORMAL/ANORMAL.
2. **Splicing** — a merged score ≥ 1.0 or a splice-site quantile ≥ 0.99 in a phenotype-relevant gene raises priority (and Hot-VUS status is easier to justify) and calls for an RNA-level recommendation (RT-PCR / RNA-seq, minigene). Concordant SpliceAI ≥ 0.2 makes the case stronger; discordance is reported as such.
3. **Expression / chromatin** — for synonymous, UTR, promoter, deep-intronic or intergenic variants (target-gene and WGS cases), a high AVI with an expression or accessibility attribution and a strong quantile in a disease-relevant tissue is the reason to discuss the variant at all; still frame it as a hypothesis needing functional or RNA data.
4. **Missense** — AlphaGenome does not model protein function; coding effect comes from REVEL/AlphaMissense. A low AVI on a missense variant is therefore uninformative for protein mechanism, and a high AVI on a missense variant near an exon boundary usually reflects splicing — check `avi_katki` and the splice columns.
5. **Low scores never exclude** a variant. Absence from the Atlas is not evidence of anything.
6. **Terms of use** — Atlas outputs are for non-commercial research and "must not be used for clinical decision-making"; every report states this (the routine's text blocks already do).

## What goes into the reports

**Kapsamlı analiz raporu** — a section headed **"AlphaGenome Atlas değerlendirmesi (araştırma amaçlı)"** after the CNV section: the method paragraph, the table (Gen | Varyant | AVI (PHRED) | En yüksek kantil (modalite, doku) | Birleşik splicing | Ekspresyon log-FC (doku) | Kategori | Yorum) covering all *yuksek*/*orta* variants and every candidate discussed in the priority/secondary sections, a short interpretation connecting the signals to the phenotype-relevant candidates (or stating explicitly that none of the candidates carries a meaningful regulatory/splicing signal), and the limits sentence. Add the two references to *Kaynaklar*. `kanit/alphagenome_rapor.txt` provides all of this; edit it into the report's voice rather than pasting blindly, and make sure numbers match `alphagenome.csv`.

**Sonuç raporu / resmi EÜTF raporu** — one sentence in the method paragraph (from `alphagenome_rapor.txt`, second block). In *Yorum*, one sentence only when AlphaGenome adds something about a reported variant (strong phenotype-consistent splicing/regulatory signal, or a clear contradiction of a suspected splicing mechanism). Never a table, never AVI numbers without the "araştırma amaçlı" qualifier.

Suggested Turkish phrasing:

- "*GENE* c.X (p.Y) için AlphaGenome Atlas birleşik splicing skoru 1,87 (splice site kantili 0,9995) ve AVI PHRED 31,4 (tüm SNV'lerin en yüksek ~%0,07'si) ile güçlü bir aberran splicing öngörüsü vermektedir; SpliceAI ile uyumludur ve RNA düzeyinde doğrulama önerilir. Bu skorlar araştırma amaçlı hesaplamalı kanıttır."
- "Sorgulanan aday varyantların hiçbiri AlphaGenome Atlas'ta belirgin düzenleyici ya da splicing etkisi göstermemiştir; bu bulgu bir genetik nedeni dışlamaz."
- "AlphaGenome Atlas sorgusu bu olguda çalıştırılamamıştır (API anahtarı tanımlı değil); değerlendirme standart tahmin araçlarıyla sınırlıdır."

## Direct queries (only when the routine output is insufficient)

```python
from alphagenome.atlas import atlas
from alphagenome.data import genome
client = atlas.create(API_KEY)                      # ALPHAGENOME_API_KEY
meta = client.scorer_metadata()                     # server-side scorer names
v = genome.Variant(chromosome="chr12", position=13865958, reference_bases="C", alternate_bases="T")
scores = client.query_variant(v, requested_scorers=["RNA_SEQ", "SPLICE_SITES", "SPLICE_SITE_USAGE", "SPLICE_JUNCTIONS"])
# scores: {scorer: AnnData}; .X raw, .layers["quantiles"] calibrated, .obs genes, .var tracks
```

Variants must be GRCh38 with VCF-style ref/alt (1-based position, anchor base for indels). The live model (`alphagenome.models.dna_client`) scores any SNV/indel over a 1 Mb window when the Atlas has no record. Rate limits are generous for the Atlas and modest for the live model; the routine caches every answer under `_sistem/alphagenome_onbellek/`.
