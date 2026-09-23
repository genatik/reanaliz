# Building the Word Documents

Both reports are delivered as `.docx`. **First read `/mnt/skills/public/docx/SKILL.md`** for the current docx-js API and gotchas, then build with a `docx` (npm) script. Save to `/mnt/user-data/outputs/`, validate, and `present_files`.

## Shared conventions

- **Font**: Arial throughout (clinical house style). Body ~10–11pt (size 20–22 in half-points).
- **Accent colour**: teal/navy (e.g., teal `2E8B8B` / navy `1F4E79`) for headings, table header shading, and the result box. Use consistently.
- **Tables**: native Word tables; set `columnWidths` on the table and `width` on every cell (`WidthType.DXA`); header rows shaded with `ShadingType.CLEAR` (never `SOLID`); borderless nested tables for the patient-info block.
- **Gene symbols italic** (`italics: true`) everywhere they appear (tables, prose, legends); protein changes three-letter; keep HGVS strings intact.
- **Page**: A4, ~1-inch margins; footer with page number (`PageNumber.CURRENT`) and an optional lab/PediatriPLUS line.
- No literal `\n` (separate `Paragraph`s) and no literal bullets (use a `numbering` config).

## Result report specifics

- **HASTA BİLGİLERİ** as a two-column layout of borderless nested info tables (label bold, value regular), matching the fields in `result-report.md`.
- **Result box**: a single shaded table row / framed paragraph, colour keyed to outcome — e.g., a warmer accent for ANORMAL, a neutral/green for NORMAL — containing the bold conclusion sentence.
- **Variant table**: compact, one row per reportable variant.
- Sign-off line and date at the foot.

## Comprehensive report specifics

- Per-candidate blocks: a variant detail table (gene/transcript/HGVS/zygosity/gnomAD/ClinVar/predictors/ACMG class+criteria/Hot-Cold) followed by short prose interpretation and a "Sonraki adım" line.
- Clear section headings (Klinik özet, QC, Öncelikli bulgular, İkincil adaylar, CNV, İnsidental, Sonuç, Kısıtlılıklar, Kaynaklar).

## Naming, validation, delivery

- File names: `WES_analiz_<dosyaNo>_<YYYY-MM-DD>.docx` and `WES_sonuc_<dosyaNo>_<YYYY-MM-DD>.docx`.
- After building, verify by converting to PDF and reading pages (`scripts/office/soffice.py --headless --convert-to pdf`, then `pdftoppm`), and validate with `python /mnt/skills/public/docx/scripts/office/validate.py <path>`.
- `present_files` both documents (comprehensive first).

## What stays a placeholder

Never invent: Dosya No, platform/kit if not given, patient identifiers, OMIM/ClinVar accessions not verified, or the reporting geneticist's name/signature. Use clear `[____]` placeholders for anything the user must supply.
