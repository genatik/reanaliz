# Ilyome WES/CES Rutini — Ayrı Sistem, Mac Kurulum Kılavuzu

Ilyome rutini Genomize rutininden **tamamen ayrı** çalışır:

| | Genomize sistemi (mevcut) | Ilyome sistemi (yeni) |
|---|---|---|
| Drive kökü | `WES_CES_Rutin_Raporlar/` | `Ilyome_Rutin_Raporlar/` |
| Olgu listesi | `WES_CES_Rutin_Raporlar/olgular.xlsx` | `Ilyome_Rutin_Raporlar/olgular.xlsx` |
| Kod | `WES_CES_Rutin_Raporlar/_sistem/` | `Ilyome_Rutin_Raporlar/_sistem/` |
| Olgu klasörleri | `WES_CES_Rutin_Raporlar/<Olgu Kodu>/` | `Ilyome_Rutin_Raporlar/<Olgu Kodu>/` |
| Başlatıcı (Mac) | Masaüstü `WES_BASLAT.command` | Masaüstü `ILYOME_BASLAT.command` |
| Masaüstü rapor kopyası | `~/Desktop/WES_CES_Rutin/raporlar/` | `~/Desktop/Ilyome_Rutin/raporlar/` |
| Kilit dosyası | `_sistem/CALISIYOR.kilit` (kendi kökünde) | `_sistem/CALISIYOR.kilit` (kendi kökünde) |

İki sistem birbirinin Excel'ini, klasörünü, kilidini görmez. Genomize tarafında **hiçbir dosya değişmez**.
Rapor adımı (indeks olgu için kapsamlı analiz + sonuç + EÜTF resmi rapor; her ebeveyn için
1 resmi rapor) aynı kod ve aynı şablonlarla, Ilyome kökünün kendi kopyasından çalışır.

> Ilyome parolası hiçbir yere kaydedilmez; BAŞLAT çalışırken gizli sorulur, pencere kapanınca silinir.

---

## Drive'da hazır olanlar (ben oluşturdum)

```
Ilyome_Rutin_Raporlar/
    olgular.xlsx                 <- boş liste (Genomize listesinin biçimi, 'Ilyome Run' sütunu, ÖRNEK satırı)
    _sistem/
        rutin.py                 <- rutin (yollar.PLATFORM = ILYOME -> yalnız Ilyome)
        ilyome_seq.py            <- Ilyome API istemcisi
        yollar.py                <- Ilyome köküne göre yollar + kendi kilidi
        ILYOME_BASLAT_mac.command
        README_OKU.txt, KURULUM_ILYOME.md
        akrabalik.py, alphagenome_sorgu.py, hpo_otomatik.py, hpo_yaz.py, hpo_toplu.py,
        raporla.py, rapor_gorevi.py, drive_esitle.py ...   <- Genomize _sistem'den kopya (aynı kod)
        sablonlar/               <- rapor şablonları (kopya)
        rapor/                   <- rapor kütüphaneleri (kopya; vaka_*.py sürücüleri yok)
        wes-variant-analysis/    <- Claude'un rapor yazma becerisi (kopya)
        log/
```

Genomize tarafına keşif için geçici koyduğum `_sistem/ilyome_kurulum/` klasörünü kaldırdım;
Ilyome'a ait her şey artık yalnızca `Ilyome_Rutin_Raporlar/` altında.

---

## Aşama 1 — Mac kurulumu ve API keşfi (~15 dk)

1. **Python 3.10+**: Terminal'de `python3 --version`. Yoksa python.org'dan kurun.
2. **Paketler** (bir kez): `python3 -m pip install --user requests openpyxl`
   (AlphaGenome için ayrıca `python3 -m pip install --user alphagenome`; anahtar `~/.alphagenome_api_key` — Genomize'da nasılsa aynı.)
3. **Google Drive for Desktop** açık; Finder'da `Ilyome_Rutin_Raporlar` klasörü görünüyor olmalı.
4. Başlatıcıyı çalıştırılabilir yapın ve masaüstüne kısayol koyun (bir kez):
   ```bash
   cd ~/Library/CloudStorage/GoogleDrive-*/My\ Drive/Ilyome_Rutin_Raporlar/_sistem
   chmod +x ILYOME_BASLAT_mac.command
   printf '#!/bin/bash\nopen -a Terminal "%s/ILYOME_BASLAT_mac.command"\n' "$PWD" > ~/Desktop/ILYOME_BASLAT.command
   chmod +x ~/Desktop/ILYOME_BASLAT.command
   ```
5. **Keşif** (gerçek hesapla, bir örnek üzerinde; filtre mantığını doğrulamak için):
   ```bash
   cd ~/Library/CloudStorage/GoogleDrive-*/My\ Drive/Ilyome_Rutin_Raporlar/_sistem
   python3 ilyome_seq.py kesfet "<Ilyome'daki bir örnek adı>"
   ```
   E-posta ve parola sorulur (hesap tek kullanımlık kod istiyorsa o da). Çıktı
   `_sistem/ilyome_kesif/<tarih>/` altına yazılır; hasta verisi içerir, Drive'da kalsın.
   Ilyome hesabınızda `WES_RUTIN` adlı bir filtre şablonu açılır; rutin yalnızca onu kullanır.
6. Bana **"Ilyome keşfi hazır"** deyin. Keşfi okuyup eksenlerin filtre mantığını kalibre ederim,
   gerekirse `ilyome_seq.py`'yi güncellerim (Drive'daki kopyayı ben yenilerim).

## Aşama 2 — Rutin kullanım

1. `Ilyome_Rutin_Raporlar/olgular.xlsx` → OLGULAR sayfasına olguyu girin. Zorunlu alanlar: Olgu Kodu,
   Test, Analiz Tipi, Proband No, Klinik Bilgi. **Proband/Anne/Baba No** = Ilyome'daki `sampleid`
   (örnek adı). HPO sütununu boş bırakabilirsiniz (klinik bilgiden otomatik üretilir / Claude planlar).
2. Durum = `BEKLIYOR`. Excel'i kapatın.
3. Masaüstündeki `ILYOME_BASLAT.command`'a çift tıklayın; Ilyome parolası sorulur.
4. Rutin her birey için `kanit/` CSV'lerini, `KLINIK.txt`, `ozet.json`'u olgu klasörüne yazar; satır
   `VERI_HAZIR` olur. Trio'da `DENOVO_*.csv`, iki etkilenen kardeşte `ORTAK_*.csv`; aile ilişkisi
   kontrolü ve AlphaGenome adımı Genomize'daki gibi.
5. Raporlar: Mac'te `claude` komutu varsa 3/3 adımı rapor sürücüsünü yazdırır, `raporla.py` ile
   Word raporlarını üretir ve satırı `TAMAMLANDI` yapar. Yoksa Claude oturumunda
   "Ilyome rutini çalıştı, raporları yaz" demeniz yeter.

**Claude Code kurulumu (Mac):**
```bash
curl -fsSL https://claude.ai/install.sh | bash      # ya da: brew install --cask claude-code
claude                                              # ilk açılışta hesabınızla giriş yapın
```

---

## Ilyome eksenleri — Genomize karşılıkları

| Eksen (CSV adı) | Genomize | Ilyome |
|---|---|---|
| `fenotip_iliskili` | HPO fenotip eşleşmesi, pop. frek. < %1 | Şablona HPO terimleri eklenir, gnomAD ekzom **ve** genom AF ≤ 0,01 (boş = görülmemiş dahil) |
| `nadir_lof` | yıkıcı sonuç, pop. frek. < %0,1 | consequence ∈ {stop_gained, frameshift, splice donor/acceptor, start/stop lost, inframe ins/del}, gnomAD AF ≤ 0,001 |
| `clinvar_patojenik` | ClinVar P/LP | `clinvar_clnsig` ∈ {Pathogenic, Likely_pathogenic, Conflicting} |
| `tier` | Genomize IA/IIA/IB/IIB | Ilyome **top-reportable** listesi (platformun kendi önceliklendirmesi) |
| `homozigot_nadir` | HOM, pop. frek. < %0,5, P..VUS | zyg ∈ {HOM, HEM}, acmg_class ∈ {P, LP, VUS}, gnomAD AF ≤ 0,005 |
| `cnv` | CNV listesi + kohort artefaktı | `cnv/<şablon>/` listesi; `ilyomedb_total / ilyomedb_total_filter` ≥ 0,3 → `cohort_artifact` |
| Hedef Genler modu | yalnız verilen genler | Şablona genler eklenir, başka filtre yok; CNV'ler hedef genlere (F8 için int1h/int22h penceresi dahil) sınırlanır |

`kanit/*.csv` sütunları Genomize ile aynı sırada; Ilyome'a özgü ekler sonda
(`cadd_phred`, `alphamissense`, `impact`, `inheritance`, `ilyome_score`, `ilyome_color`, `is_reported`,
`omim`, `cohort_af`, `cohort_an`, `ilyome_id`). Önemli eşlemeler: `key` ← `variant_key` (chr öneksiz),
`pathogenicity` ← `acmg_class`, `genotype` ← `zyg` (het/hom/hem), `gme` ← `genoks_af` (Türk kohortu),
`internal_freq` ← `cohort_af` yalnız `cohort_an ≥ 200` ise (küçük merkez kohortu artefakt kriteri sayılmaz).
`ozet.json`'a `platform: "Ilyome"`, birey başına `kit` (run adı + capture), `genom`, `dizileme_tipi`, `pipeline` yazılır.

---

## Keşiften sonra netleşecek noktalar

1. Aynı filtrede çoklu kutucuk VEYA mı, VE mi? (`f_stop_gained` vs `f_stop_gained_VEYA_frameshift`)
2. Frekans filtresinde `isnull=true` gnomAD'de görülmemiş varyantları tutuyor mu?
3. `page_size=200` kabul ediliyor mu?
4. Merkez ön-eki `/api/c/<merkez>/`; merkez adı `whoami`'den. Yanlışsa `ILYOME_CENTER=...`.
5. Şablon sıfırlama ucu `DELETE` mi `POST` mu (kod ikisini de dener).
6. Ilyome'un kendi Trio / De novo filtresi ek eksen olarak eklenebilir.

## Sorun giderme

- **"Ilyome girisi basarisiz (401)"** — e-posta/parola. OTP isteniyorsa kod sorulur.
- **"merkez on-eki eksik" / 404** — `ILYOME_CENTER="<merkez adı>"` verin.
- **"'X' N ornekle eslesti"** — Proband No'ya tam `sampleid` yazın.
- **"tum tarama eksenleri 0 satir dondu"** — negatif sonuç DEĞİL, veri toplama hatası; olgu HATA'ya düşer.
- **Excel yazılamadı** — `olgular.xlsx` açık; kapatıp yeniden çalıştırın.
- Testler (giriş gerekmez): `python3 test_ilyome_seq.py && python3 test_rutin_ilyome_e2e.py`
