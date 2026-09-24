# AlphaGenome Atlas — regulatory & splicing effect evidence

Google DeepMind's **AlphaGenome** (Avsec et al., *Nature* 2026, doi:10.1038/s41586-025-10014-0) predicts the molecular consequences of a DNA change across modalities (RNA-seq expression, splice sites / splice-site usage / splice junctions, polyadenylation, ATAC/DNase accessibility, ChIP-TF and ChIP-histone, CAGE/PRO-cap TSS activity, 3D contact maps). **AlphaGenome Atlas** (Cheng et al. 2026, https://alphagenome.google/atlas) is the pre-computed, genome-wide (GRCh38) version of those scores for every possible SNV plus observed indels, together with the **AVI (AlphaGenome Variant Impact)** score and its SHAP feature attributions.

The WES routine (`_sistem/rutin.py` → `alphagenome_sorgu.py`) queries the Atlas API for the proband's candidate variants (phenotype, rare-LoF, ClinVar-pathogenic, tier and rare-homozygous axes plus `DENOVO_*` and `ORTAK_*` lists, after population-frequency ≤ 2 % and internal-cohort filters) and writes into `kanit/`:

| File | Content |
|---|---|
| `alphagenome.csv` | one row per candidate: `avi` (PHRED, derived from the Atlas calibrated quantile), `avi_ham` (raw model logit = sum of SHAP contributions; **not** PHRED), `avi_yorum`, `avi_katki`, `splicing_birlesik`, `duzenleyici_sinyal` (modalities significant after active-tissue gating + Bonferroni, e.g. `RNA_SEQ- (liver); DNASE+ (heart)`), per-modality `<mod>_ham` / `<mod>_kantil` / `<mod>_p` / `<mod>_doku` / `<mod>_gen` / `<mod>_aktif`, `kategori` (yuksek/orta/dusuk), `durum` (atlas / model / bulunamadi / hata / sorulamadi), Turkish `yorum` |
| `alphagenome_detay.csv` | variant × scorer × tissue long table (top 5 tissues/genes per scorer) |
| `alphagenome_ozet.json` | run status (`durum`, `neden`), counts, server scorer names (`sunucu_skorlari`), errors |
| `alphagenome_rapor.txt` | ready-made Turkish blocks: the comprehensive-report section, the one-sentence method line for the result/official reports, and the two references |

If the files are missing for a routine case: `cd _sistem && python rutin.py --alphagenome <OlguKodu>` (no Genomize login needed; needs `pip install alphagenome` and `ALPHAGENOME_API_KEY`). If `alphagenome_ozet.json` says `durum: atlandi` (no key, hg19, no package) or `hata`, do not invent scores — say in the report that AlphaGenome was not run and why.

## Reading the scores

- **AVI (PHRED)** — rank of the variant among all human SNVs: 10 = top 10 %, 20 = top 1 %, 30 = top 0.1 %. Range 0–55+. Above ~45 the score is driven by protein-truncation/AlphaMissense/splicing/conservation features; 22.5–45 is dominated by splicing and coding features (core splice sites peak at 32.5–35); 5–22.5 is the *cis*-regulatory regime (accessibility, TF/histone signals, UTR/synonymous/splice-region variants); complex-trait causal variants often sit at 0–5. The routine derives PHRED from the Atlas calibrated quantile (PHRED = −10·log10(1−q)); `avi_ham` is the raw model logit (the SHAP contributions sum to it) and must never be read as PHRED. The Atlas paper deliberately recommends **ranking over hard cut-offs** and region-/application-aware thresholds. In the GREGoR rare-disease analysis, de novo variants were ranked by AVI and the top 1 % (AVI ≥ 20) were reviewed case by case.
- **`avi_katki`** — the three largest SHAP contributions (e.g. `MERGED_SPLICING:+1.08; CACTUS_241_WAY:+0.45`): tells *why* AVI is high (splicing vs chromatin vs conservation vs protein: `PROTEIN_TERMINATION`, `ALPHAMISSENSE`, `MAX_ABS_<modality>`).
- **`splicing_birlesik`** — max(splice-site) + max(splice-site usage) + max(splice-junction)/5 across genes and tissues, exactly the AlphaGenome/Atlas "merged splicing score". In real exome data canonical splice-acceptor/donor SNVs score 2.5–3.5, splice-region/polypyrimidine variants 1.5–2.5, everything else < 0.5. ≥ 1.0 = strong, 0.5–1.0 = possible effect.
- **Calibrated quantile (`*_kantil`, −1…1)** — the raw modality score ranked against a background of common variants (gnomAD MAF > 1 %) per track. Two traps, both handled by the routine: (1) with hundreds of tissue/gene cells the *maximum* |quantile| is ~0.99 for essentially every variant (multiple comparisons), so a modality only counts as a signal when the Bonferroni-corrected tail `<mod>_p` = (number of active cells) × (1−|quantile|) is ≤ 0.01; (2) in a tissue where the gene/element is inactive a tiny effect saturates to ±1.0, so cells are first gated by the Atlas *active-allele* score (`<mod>_aktif` = activity relative to the most active tissue, kept if ≥ 0.10). Only modalities passing both appear in **`duzenleyici_sinyal`** (sign = direction, tissue in brackets). Use the quantile/tissue to say *where* the effect is and the raw value (`*_ham`, e.g. log-fold change) for its magnitude; do not quote a lone 0.99 quantile as evidence.
- **`kategori`** — a sorting aid only: *yuksek* if AVI ≥ 20 or merged splicing ≥ 1.0; *orta* if AVI ≥ 10, splicing ≥ 0.5 or a corrected regulatory signal is present; else *dusuk*. It is **not** a clinical threshold.
- **`durum`** — `atlas` (pre-computed lookup), `model` (the Atlas client currently accepts SNVs only, so indels/MNVs — and variants absent from the Atlas — are scored with the live model over a 1 Mb window; no AVI, no quantiles: judge them by merged splicing and raw effects), `bulunamadi` (live-model fallback off/exhausted), `hata` (API error), `sorulamadi` (mitochondrial, N bases, > 50 bp, unparsable key).

## How to weigh it against ACMG evidence

1. AlphaGenome is **secondary, research-level computational evidence**. The calibrated tools already in the pipeline (REVEL, SpliceAI, AlphaMissense) carry PP3/BP4; AlphaGenome is reported alongside them, never as a criterion code and never as the sole reason to move a class or to change NORMAL/ANORMAL.
2. **Splicing** — a merged score ≥ 1.0 or a splice-site quantile ≥ 0.99 in a phenotype-relevant gene raises priority (and Hot-VUS status is easier to justify) and calls for an RNA-level recommendation (RT-PCR / RNA-seq, minigene). Concordant SpliceAI ≥ 0.2 makes the case stronger; discordance is reported as such.
3. **Expression / chromatin** — for synonymous, UTR, promoter, deep-intronic or intergenic variants (target-gene and WGS cases), a high AVI with an expression or accessibility attribution and a strong quantile in a disease-relevant tissue is the reason to discuss the variant at all; still frame it as a hypothesis needing functional or RNA data.
4. **Missense** — AlphaGenome does not model protein function; coding effect comes from REVEL/AlphaMissense. A low AVI on a missense variant is therefore uninformative for protein mechanism, and a high AVI on a missense variant near an exon boundary usually reflects splicing — check `avi_katki` and the splice columns.
5. **Low scores never exclude** a variant. Absence from the Atlas is not evidence of anything.
6. **Terms of use** — Atlas outputs are for non-commercial research and "must not be used for clinical decision-making"; every report states this (the routine's text blocks already do).

## What goes into the reports

**Kapsamlı analiz raporu** — a section headed **"AlphaGenome Atlas değerlendirmesi (araştırma amaçlı)"** after the CNV section: the method paragraph, the table (Gen | Varyant | Kaynak | AVI (PHRED) | Birleşik splicing | Düzenleyici sinyal (modalite, doku) | Ekspresyon log-FC (doku) | Kategori | Yorum) covering all *yuksek*/*orta* variants and every candidate discussed in the priority/secondary sections, a short interpretation connecting the signals to the phenotype-relevant candidates (or stating explicitly that none of the candidates carries a meaningful regulatory/splicing signal), and the limits sentence. Add the two references to *Kaynaklar*. `kanit/alphagenome_rapor.txt` provides all of this; edit it into the report's voice rather than pasting blindly, and make sure numbers match `alphagenome.csv`.

**Sonuç raporu / resmi EÜTF raporu** — one sentence in the method paragraph (from `alphagenome_rapor.txt`, second block). In *Yorum*, one sentence only when AlphaGenome adds something about a reported variant (strong phenotype-consistent splicing/regulatory signal, or a clear contradiction of a suspected splicing mechanism). Never a table, never AVI numbers without the "araştırma amaçlı" qualifier.

Suggested Turkish phrasing:

- "*GENE* c.X (p.Y) için AlphaGenome Atlas birleşik splicing skoru 2,87 (kanonik splice site düzeyi) ve AVI PHRED 31,4 (tüm SNV'lerin en yüksek ~%0,07'si) ile güçlü bir aberran splicing öngörüsü vermektedir; SpliceAI ile uyumludur ve RNA düzeyinde doğrulama önerilir. Bu skorlar araştırma amaçlı hesaplamalı kanıttır."
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
# server scorer names (Sep 2026): RNA_SEQ, SPLICE_SITES, SPLICE_SITE_USAGE, SPLICE_JUNCTIONS, POLYADENYLATION,
# ATAC, DNASE, CHIP_TF, CHIP_HISTONE, CAGE, PROCAP, CONTACT_MAPS, their *_ACTIVE active-allele twins,
# AVI_SCORE, AVI_SCORE_FEATURE_IMPORTANCE (SHAP), AVI_SCORE_MODEL_FEATURES (raw 18 features).
# `python alphagenome_sorgu.py --incele chr6:10961512:A:T` dumps one raw response to incele_<key>.txt.
```

Variants must be GRCh38 with VCF-style ref/alt (1-based position, anchor base for indels). The live model (`alphagenome.models.dna_client`) scores any SNV/indel over a 1 Mb window when the Atlas has no record. Rate limits are generous for the Atlas and modest for the live model; the routine caches every answer under `_sistem/alphagenome_onbellek/`.
