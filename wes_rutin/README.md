# WES rutini — AlphaGenome Atlas entegrasyonu

Bu klasör, Google Drive'daki `WES_CES_Rutin_Raporlar/_sistem/` altında çalışan WES/CES analiz rutinine
eklenen **AlphaGenome Atlas** (Google DeepMind) adımının kaynak kodunu, testlerini ve rapor-yazım
kılavuzunu (skill güncellemesi) içerir. Rutinin kendisi Drive'da çalışır; buradaki kopya sürüm takibi
içindir.

## Ne yapar

`rutin.py`, her olgunun kanıt CSV'lerini yazdıktan sonra probandın aday varyantlarını
(`fenotip_iliskili`, `nadir_lof`, `clinvar_patojenik`, `tier`, `homozigot_nadir` eksenleri ile
`DENOVO_*` ve `ORTAK_*` listeleri; popülasyon frekansı ≤ %2 ve dahili kohort filtresi sonrası)
AlphaGenome Atlas API'sine sorar ve `kanit/` içine yazar:

| Dosya | İçerik |
|---|---|
| `alphagenome.csv` | varyant başına özet: AVI PHRED skoru ve yorumu, SHAP katkıları, en yüksek kalibre kantil (modalite/doku), birleşik splicing skoru, modalite bazlı ham/kantil/doku/gen sütunları, kategori (yuksek/orta/dusuk), Türkçe yorum |
| `alphagenome_detay.csv` | varyant × skor × doku uzun tablo |
| `alphagenome_ozet.json` | çalışma durumu, sayımlar, sunucudaki skor adları, hatalar |
| `alphagenome_rapor.txt` | rapora girecek hazır Türkçe bloklar (kapsamlı rapor bölümü, yöntem cümlesi, kaynakça) |

Özet `ozet.json > alphagenome` altına ve `olgular.xlsx` *Sonuç Özeti* sütununa ("AlphaGenome yuksek N / orta M") da yazılır.
API anahtarı, paket ya da ağ yoksa adım **sessizce atlanır**; olgu HATA'ya düşmez.

Var olan olgulara sonradan eklemek için (Genomize gerekmez):

```
python rutin.py --alphagenome 222080-DOR-HAY
python rutin.py --alphagenome TUMU
python alphagenome_sorgu.py --varyant chr12:13865958:C:T
python alphagenome_sorgu.py --skorlar-listele
```

## Kurulum (her bilgisayarda bir kez)

1. `python -m pip install alphagenome` (Python ≥ 3.10)
2. API anahtarı (ücretsiz, ticari olmayan kullanım): https://alphagenome.google/api
3. Windows: `setx ALPHAGENOME_API_KEY "anahtar"` — Mac: anahtarı `~/.alphagenome_api_key` dosyasına yazın

## Dosyalar

- `alphagenome_sorgu.py` — yeni modül (Atlas sorgusu, canlı model yedeği, önbellek, özetleme, rapor metni)
- `rutin.alphagenome.patch` — `rutin.py` üzerindeki değişiklik (import, `alphagenome_calistir`, `--alphagenome` komutu)
- `BASLAT.bat`, `BASLAT_mac.command` — paket/anahtar kontrolü eklenmiş başlatıcılar
- `README_OKU_alphagenome.txt` — `README_OKU.txt`'ye eklenen bölüm
- `tests/test_alphagenome_sorgu.py` — çevrimdışı testler (sahte Atlas istemcisi gerçek protobuf → AnnData dönüşümünü kullanır)
- `skill/wes-variant-analysis/` — rapor yazan Claude için güncellenmiş skill (yeni `references/alphagenome.md`; SKILL.md, comprehensive-report.md ve result-report.md'de AlphaGenome bölümü)

## Skorların anlamı (kısa)

- **AVI (PHRED)**: tüm SNV'ler içinde sıralama; 10 = en yüksek %10, 20 = en yüksek %1, 30 = en yüksek %0,1.
- **Kalibre kantil (−1…1)**: yaygın varyant arka planına göre uçluk; |0,99| = en uç %1. İşaret yönü gösterir.
- **Birleşik splicing**: max(SS) + max(SSU) + max(SJ)/5; > 1,0 genellikle büyük etki.
- **Kategori**: sıralama yardımcısıdır, klinik eşik değildir.

AlphaGenome çıktıları araştırma amaçlıdır; ACMG PP3/BP4 kanıtı yerine geçmez ve tek başına klinik karar
verdirmez (kullanım koşulları). Kaynaklar: Avsec ve ark., *Nature* 2026 (doi:10.1038/s41586-025-10014-0);
Cheng ve ark., AlphaGenome Atlas, 2026 (https://alphagenome.google/atlas).
