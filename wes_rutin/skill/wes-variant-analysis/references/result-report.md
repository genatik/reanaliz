# Clinical Result Report (Sonuç Raporu)

The formal, concise clinical report — the document that goes to the file/clinician. Turkish, clean, professional. It states the outcome and the reportable variant(s); it does not reproduce the full analytical reasoning (that lives in the comprehensive report).

## Structure

1. **HASTA BİLGİLERİ** — a two-column header table:
   - Dosya No; Analiz Tipi (Tüm Ekzom Sekanslama [WES], Solo/Trio); Platform (e.g., NovaSeq 6000 / MGI DNBSEQ); Kit (e.g., Twist Exome 2.0) — use what the user provides, placeholder otherwise.
   - Rapor Tarihi; Analiz Kapsamı (Tüm Ekzom + CNV; Trio ise belirt); Referans Genom (GRCh38/hg38); Klinik Ön Tanı.

2. **SONUÇ kutusu** — a prominent result box:
   - **NORMAL** — "Hastanın klinik bulgularını açıklayabilecek, klinik önemi olan bir varyant saptanmamıştır." (no reportable variant)
   - **ANORMAL** — "Hastanın klinik bulgularını açıklayabilecek varyant(lar) saptanmıştır."
   - Or an intermediate wording when only a VUS/partial explanation is found — state it honestly (e.g., klinik önemi belirsiz varyant saptanmıştır).

3. **Saptanan varyant(lar)** — for each reportable variant, a compact table row: Gene (*italic*), transcript + HGVS c./p., zygosity, inheritance, ACMG class (+ key criteria), ClinVar, associated OMIM disorder. Keep it to what is being reported, not the full candidate list.

4. **Yorum** — a short clinical interpretation: how the variant relates to the phenotype, inheritance and recurrence implications, and classification confidence. If AlphaGenome gives a strong, phenotype-consistent splicing/regulatory signal for a reported variant (or clearly contradicts a suspected splicing mechanism), add one sentence stating it as supportive computational evidence (never as an ACMG criterion).

5. **Öneriler** — Sanger confirmation of reportable variant(s); parental/segregation testing; any indicated functional/RNA or additional testing; genetic counselling; reanalysis if negative/inconclusive.

   **Negative cases with a candidate gene:** the result box stays **NORMAL** — a candidate gene is not a clinical diagnosis and must never be reported as causal. Add a brief, clearly-labelled pointer here: that a research-level candidate gene/variant is discussed in the comprehensive analysis report, that it does not currently permit clinical or reproductive decisions, and that further steps (segregation, functional studies, GeneMatcher/Matchmaker Exchange submission, research participation with appropriate consent, reanalysis in 12–18 months) may be offered. Do not reproduce the full candidate argument here.

6. **Kısıtlılıklar & imza** — brief method/limitation statement (WES scope, what it may miss, that negative does not exclude), report author/geneticist sign-off line, and date. Placeholders for name/title/signature. When AlphaGenome was run, the method statement (and the *Analiz Yöntemi* paragraph of the official EÜTF report) gets the one-sentence AlphaGenome method line from `kanit/alphagenome_rapor.txt`.

## Design

Professional clinical layout: teal/navy accent, Arial, patient-info table at top, a clearly shaded result box (colour keyed to NORMAL vs ANORMAL), compact variant table, page numbers, and a footer. See `references/docx-format.md`. Keep it to 1–2 pages where possible.

## Consistency

Numbers, variants, classes, and the NORMAL/ANORMAL conclusion must match the comprehensive analysis report exactly. Only variants intended for clinical reporting appear here; secondary/incidental findings appear only if the return-of-results decision includes them.
