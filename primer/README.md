# Sanger primer tasarımı (NGS varyant doğrulama ve segregasyon)

Gen adı ve varyant girilir. Araç varyantı genomik koordinata çevirir, UCSC'den bölge verisini çeker, alternatifli primer çiftleri tasarlar, her çifti kontrol eder ve sonucu görsel olarak sunar. Sunucu gerektirmez: statik bir sayfadır ve tüm hesaplama tarayıcıda yapılır.

## Kullanım

- GitHub Pages açıksa: `https://<kullanıcı>.github.io/reanaliz/primer/`
- Yerelde:

```bash
cd reanaliz && python3 -m http.server 8000
```

Ardından tarayıcıda `http://localhost:8000/primer/` adresini açın.

Bağlantı ile doğrudan çalıştırma da mümkündür: `primer/?gene=CFTR&variant=c.1521_1523del&build=hg38`

### Kabul edilen varyant gösterimleri

| Girdi | Örnek | Çözümleyen |
|---|---|---|
| Gen + c. gösterimi | `CFTR` + `c.1521_1523del` | VariantValidator (MANE Select) |
| Transkriptli HGVS | `NM_000492.4:c.489+1G>T` | VariantValidator |
| rsID | `rs113993960` | Ensembl REST |
| Genomik koordinat | `chr7:117559590 ATCT>A` | Doğrudan |

GRCh38/hg38 ve GRCh37/hg19 desteklenir.

## İş akışı

1. **Varyant çözümleme.** HGVS gösterimi VariantValidator ile doğrulanır ve VCF koordinatına çevrilir. Protein değişikliği ve uyarılar da alınır.
2. **UCSC verisi** (UCSC REST API):
   - NCBI RefSeq Select gen modeli: ekzon/intron numarası, girilen gen adı ile tutarlılık
   - Referans dizi: varyantın REF alleli referansla karşılaştırılır
   - dbSNP155 Common: primer bağlanma yerlerinde yaygın SNP (allel düşmesi riski)
   - RepeatMasker ve Simple Repeats: tekrar bölgeleri
3. **Tasarım.** Varyantın iki yanındaki tüm olası primerler taranır, filtrelenir ve Primer3 tarzı ceza puanı ile sıralanır. Birbirinden en az 10 baz farklı konumda olan alternatif çiftler seçilir. Sıkı kriterlerle yeterli çift çıkmazsa kriterler kontrollü olarak gevşetilir ve bu çiftler arayüzde işaretlenir.
4. **Kontrol.** Her çift için kontrol listesi, dimer hizalamaları, Sanger okuma planı ve işaretli amplikon dizisi gösterilir.
5. **UCSC görselleştirme.** Bölge haritası, UCSC Genome Browser görüntüsü ve primerlerin özel iz olarak yüklendiği UCSC bağlantısı verilir.

## Kontroller

- Tm, GC oranı, 3' GC kenetlenmesi, homopolimer ve dinükleotit tekrarı
- Hairpin, self-dimer, 3' uç self-dimer, F×R heterodimer ΔG ve 3' uç stabilitesi
- Primerde yaygın SNP (sıkı modda hiç yok, gevşek modda 3' son 5 bazda yok)
- Primerin tekrar bölgesine denk gelmesi
- Şablon içinde primer 3' ucunun (12 baz) başka bir yere bağlanması
- Varyantın her iki primerden en az belirlenen mesafede olması (varsayılan 60 baz; Sanger izinin ilk ~40 bazı okunamaz)
- Primer ile varyant arasında homopolimer (≥9 baz) olması
- Amplikon GC oranı
- İsteğe bağlı: varyantın bulunduğu ekzonun tamamını kapsama

## Doğrulama

`tests/` klasöründeki testler ağ gerektirmez:

```bash
node primer/tests/compare.js
```

```bash
node primer/tests/design.test.js
```

`compare.js` motoru Primer3 (primer3-py 2.4.0) ile 608 oligo üzerinde karşılaştırır. Referans değerler `make_reference.py` ile üretilir.

| Ölçüm | Primer3 ile fark |
|---|---|
| Tm | 0.000 °C (birebir aynı) |
| Heterodimer ΔG | ortalama 0.5 kcal/mol, korelasyon r = 0.89 |
| Self-dimer ΔG | ortalama 0.8 kcal/mol, korelasyon r = 0.93 |
| Hairpin ΔG | ortalama 0.3 kcal/mol, korelasyon r = 0.92 |

`design.test.js` CFTR c.1521_1523del (F508del) bölgesinin kaydedilmiş UCSC verisi üzerinde tüm kısıtların sağlandığını doğrular.

## Sınırlamalar

- **Genom geneli özgüllük tarayıcıdan otomatik yapılamaz.** UCSC BLAT ve In-Silico PCR programatik erişimi engelliyor. Her çift için hazır doldurulmuş UCSC In-Silico PCR, BLAT ve NCBI Primer-BLAST bağlantıları verilir. Sipariş öncesi bu kontrol mutlaka yapılmalıdır. Psödogeni veya paralogu olan genlerde (ör. SMN1/SMN2, PMS2, CYP21A2, GBA1) bu adım özellikle kritiktir.
- İkincil yapı ΔG değerleri Primer3'ün termodinamik hizalamasının yaklaşık karşılığıdır. Eşik kontrolü ve sıralama için yeterlidir, ancak mutlak değerler birkaç kcal/mol farklı olabilir.
- SNP maskesi dbSNP155 Common'a (MAF ≥ %1) dayanır. Nadir popülasyona özgü varyantlar bu izde bulunmayabilir.
- Varyant ekzonun tamamını kapsama seçeneğinde ekzon, maksimum ürün boyuna sığmalıdır.

## Dosyalar

| Dosya | İçerik |
|---|---|
| `index.html` | Arayüz |
| `app.js` | Veri toplama (VariantValidator, Ensembl, UCSC) ve görselleştirme |
| `engine.js` | Termodinamik ve primer tasarım motoru (tarayıcı ve Node.js) |
| `tests/` | Primer3 karşılaştırması ve tasarım regresyon testi |
