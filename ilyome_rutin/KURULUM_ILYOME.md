# Ilyome WES/CES Rutini — Mac Kurulum ve Geçiş Kılavuzu

Bu klasör, Genomize üzerinde çalışan WES/CES rutinini **ilyome.com** olgularına da
açar. Mantık aynı kalır: olguları Drive'daki `olgular.xlsx` listesine girersiniz,
rutin platforma sizin hesabınızla girer, tarama eksenlerini çalıştırır, kanıt
tablolarını (CSV) olgu klasörüne yazar; Claude kanıtları yorumlayıp indeks olgu için
3 rapor (kapsamlı analiz, sonuç, EÜTF resmi) ve her ebeveyn için 1 resmi rapor üretir.

Tek fark: `olgular.xlsx`'e **Platform** sütunu gelir. Boş veya `Genomize` → eski yol;
`Ilyome` → ilyome.com. İki platformun olguları aynı listede, aynı BAŞLAT ile işlenir.

> Parolanız hiçbir yere kaydedilmez. BAŞLAT çalışırken gizli sorulur, pencere
> kapanınca bellekten silinir. Yalnızca o anda bekleyen olgusu olan platformun
> parolası sorulur.

---

## Bu klasördeki dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `ilyome_seq.py` | Ilyome API istemcisi (giriş, örnek bulma, filtre şablonu, SNV/CNV listeleri). `genomize_seq.py` ile aynı arayüz, aynı CSV sütunları. |
| `rutin.py` | Mevcut `rutin.py`'nin **Platform sütunu destekli** sürümü. Genomize olguları için davranış değişmez. |
| `rutin_platform.diff` | Mevcut `rutin.py`'ye göre yapılan değişikliklerin tamamı (inceleme için). |
| `BASLAT_mac.command` | Yeni Mac başlatıcı: yalnızca gereken platformun parolasını sorar; sonunda Claude Code varsa raporları da yazdırır. |
| `test_ilyome_seq.py`, `test_rutin_ilyome_e2e.py`, `test_fixtures/` | Ilyome'un kendi demo yanıtlarıyla çevrimdışı testler. Giriş gerekmez; her şey yeşil. |

---

## Nasıl ilerleyeceğiz (3 aşama)

### Aşama 1 — Keşif (sizin Mac'inizde, ~10 dk)

Ilyome'un filtre semantiğini (iki kutucuk işaretlenince VEYA mu, VE mi? boş frekans
alanı nasıl davranır? sayfa boyutu sınırı?) gerçek hesapla doğrulamadan rutini
kapatmam doğru olmaz. Bunun için `kesfet` komutu var: giriş yapar, **bir** örnek
üzerinde her adımın ham yanıtını JSON'a yazar (token/parola gizlenir).

1. **Python 3** kurulu mu? Terminal'de `python3 --version` (3.10+ olmalı; yoksa python.org).
2. Paketler (bir kez): `python3 -m pip install --user requests openpyxl`
3. **Google Drive for Desktop** açık ve `WES_CES_Rutin_Raporlar` klasörü Finder'da görünüyor olmalı.
4. Bu klasördeki `ilyome_seq.py` dosyasını Drive'daki `_sistem/` klasörüne kopyalayın
   (henüz `rutin.py` ve `BASLAT_mac.command`'ı DEĞİŞTİRMEYİN; eski rutin aynen çalışır).
5. Terminal:
   ```bash
   cd ~/Library/CloudStorage/GoogleDrive-*/My\ Drive/WES_CES_Rutin_Raporlar/_sistem
   python3 ilyome_seq.py kesfet "<Ilyome'daki bir örnek adı>"
   ```
   E-posta ve parola sorulur. Hesabınız tek kullanımlık kod istiyorsa e-postanıza
   gelen kodu da sorar.
6. Çıktı `_sistem/ilyome_kesif/<tarih>/` altına yazılır (`kesif_ozet.json`, `ham_istekler.json`).
   Bu dosyalar hasta verisi içerir; Drive'da kalsın, başka yere göndermeyin.
7. Bana **"Ilyome keşfi hazır"** deyin. Keşif çıktısını okuyup eksenlerin filtre
   mantığını kalibre eder, gerekiyorsa `ilyome_seq.py`'yi düzeltirim.

Keşif sırasında Ilyome hesabınızda `WES_RUTIN` adında bir filtre şablonu (search theme)
açılır. Rutin yalnızca bu şablonu kullanır; kendi şablonlarınıza dokunmaz.

### Aşama 2 — Geçiş (ben kalibre ettikten sonra, ~5 dk)

1. Drive `_sistem/` içinde yedek alın: `rutin.py` → `rutin.py.yedek_ilyome_oncesi`,
   `BASLAT_mac.command` → `BASLAT_mac.command.yedek`.
2. Bu klasördeki `rutin.py`, `ilyome_seq.py` ve `BASLAT_mac.command` dosyalarını `_sistem/` içine kopyalayın.
3. `chmod +x _sistem/BASLAT_mac.command` (bir kez).
4. Masaüstündeki `WES_BASLAT.command` kısayolu Drive'daki `BASLAT_mac.command`'ı çalıştırır; değiştirmeniz gerekmez.
5. İlk çalıştırmada rutin `olgular.xlsx`'e **Platform** sütununu kendisi ekler (en sağa).
   Windows'taki `BASLAT.bat` da aynı `rutin.py`'yi kullanır; orada da çalışır
   (Ilyome olgusu varsa `ILYOME_USER` / `ILYOME_PASS` ortam değişkenleri gerekir; istenirse `.bat`'ı da güncellerim).

### Aşama 3 — Rutin kullanım

1. `olgular.xlsx` → OLGULAR sayfasına olguyu girin. Zorunlu alanlar aynı: Olgu Kodu, Test,
   Analiz Tipi, Proband No, Klinik Bilgi. **Proband/Anne/Baba No** için Ilyome'daki
   `sampleid` (örnek adı) yazılır; birden fazla eşleşirse rutin durur ve tam adı ister.
2. **Platform** sütununa `Ilyome` yazın. Durum = `BEKLIYOR`. Excel'i kapatın.
3. `WES_BASLAT.command`'a çift tıklayın. Bekleyen olgular Genomize'da ise Genomize,
   Ilyome'da ise Ilyome parolası sorulur (ikisi de varsa ikisi de).
4. Rutin her birey için `kanit/` CSV'lerini, `KLINIK.txt` ve `ozet.json`'u olgu klasörüne
   yazar; satır `VERI_HAZIR` olur. Trio'da `DENOVO_*.csv`, iki etkilenen kardeşte `ORTAK_*.csv`
   aynen üretilir; aile ilişkisi kontrolü (akrabalik.py) ve AlphaGenome adımı değişmez.
5. Raporlar: BAŞLAT'ın 3/3 adımı Mac'te `claude` komutu varsa rapor sürücüsünü yazdırıp
   `raporla.py` ile 3 + ebeveyn raporlarını üretir ve satırı `TAMAMLANDI` yapar.
   `claude` yoksa Claude oturumunda "WES rutini çalıştı, raporları yaz" demeniz yeter.

**Claude Code'u Mac'e kurmak (3/3 adımının otomatik çalışması için):**
```bash
curl -fsSL https://claude.ai/install.sh | bash      # ya da: brew install --cask claude-code
claude                                              # ilk açılışta hesabınızla giriş yapın
```

---

## Ilyome eksenleri — Genomize karşılıkları

| Eksen (CSV adı) | Genomize | Ilyome |
|---|---|---|
| `fenotip_iliskili` | HPO fenotip eşleşmesi, pop. frek. < %1 | Şablona HPO terimleri eklenir (`phenotype/bulk-add`), gnomAD ekzom **ve** genom AF ≤ 0,01 (boş = görülmemiş dahil) |
| `nadir_lof` | yıkıcı sonuç, pop. frek. < %0,1 | consequence ∈ {stop_gained, frameshift, splice donor/acceptor, start/stop lost, inframe ins/del}, gnomAD AF ≤ 0,001 |
| `clinvar_patojenik` | ClinVar P/LP | `clinvar_clnsig` ∈ {Pathogenic, Likely_pathogenic, Conflicting} |
| `tier` | Genomize IA/IIA/IB/IIB önceliklendirme | Ilyome'un **top-reportable** listesi (platformun kendi önceliklendirmesi) |
| `homozigot_nadir` | HOM, pop. frek. < %0,5, P..VUS | zyg ∈ {HOM, HEM}, acmg_class ∈ {P, LP, VUS}, gnomAD AF ≤ 0,005 |
| `cnv` | CNV listesi + kohort artefaktı | `cnv/<şablon>/` listesi; `ilyomedb_total / ilyomedb_total_filter` ≥ 0,3 → `cohort_artifact` |
| Hedef Genler modu | yalnız verilen genler | Şablona genler eklenir (`gene/<id>/`), başka filtre yok; CNV'ler hedef genlere (F8 için int1h/int22h penceresi dahil) sınırlanır |

Sütun eşlemesi (`kanit/*.csv`, Genomize ile aynı sıra; Ilyome'a özgü ekler sonda):

- `key` ← `variant_key` (`3:129528965:A:C`, `chr` öneki yok — akrabalik.py bunu bekler)
- `pathogenicity` ← `acmg_class`; `autopat_score` ← `score_raw` (Ilyome skoru)
- `genotype` ← `zyg` küçük harf (het/hom/hem); `quality` ← `filter` (PASS/…); `depth` ← `dp`; `allele_fraction` ← `allelefraction/100`
- `af_max` ← `max_af`; `gnomad_exome/genome` ← `af_exomes/af_genomes`; `gnomad_exome_hom` ← `nhomalt_exomes`
- `gme` ← `genoks_af` (Türk kohort frekansı; GME yerine kullanılır — raporda belirtin)
- `revel`, `sift`, `polyphen`, `spliceai` (splice_ai yoksa SpliceAI DS en büyüğü)
- `internal_freq` ← `cohort_af` **yalnız** `cohort_an ≥ 200` ise; küçük merkez kohortunda (ör. 16 alel) tek het %6 verir ve her şeyi artefakt yapardı, bu yüzden boş bırakılır
- Ek sütunlar: `cadd_phred`, `alphamissense`, `impact`, `inheritance` (OMIM/HPO kalıtım), `ilyome_score`, `ilyome_color`, `is_reported`, `omim`, `cohort_af`, `cohort_an`, `ilyome_id`

`ozet.json`'a `platform: "Ilyome"`, birey başına `kit` (run adı + capture), `genom` (HG38→hg38),
`dizileme_tipi` (WES/WGS) ve `pipeline` (Dragen) yazılır; künye bölümü buradan dolar.

---

## Keşiften sonra netleşecek noktalar (açık sorular)

1. **Çoklu kutucuk mantığı** — aynı filtrede birden çok terim (ör. 8 yıkıcı sonuç) VEYA olarak mı birleşiyor? Keşif `f_stop_gained` ile `f_stop_gained_VEYA_frameshift` sayılarını karşılaştırır.
2. **Frekans filtresinde boş değer** — `isnull=true` gnomAD'de hiç görülmemiş varyantları listede tutuyor mu? (`f_pop_frekans_0_1` vs `..._nullsuz`).
3. **Sayfa boyutu** — `page_size=200` kabul ediliyor mu, sunucu sınırı var mı?
4. **Merkez ön-eki** — isteklerin `/api/c/<merkez>/...` ile gitmesi gerekiyor; merkez adı `whoami`'den okunur. Yanlışsa `ILYOME_CENTER=...` ile elle verilebilir.
5. **Şablon sıfırlama ucu** `DELETE .../reset/` mi `POST` mu — kod ikisini de dener; keşif hangisinin 200 verdiğini gösterir.
6. **Trio modu** — Ilyome'un kendi "Family / Trio / De novo" filtresi var. Şimdilik Genomize'daki gibi birey başına tarama + küme farkı kullanılıyor (DENOVO/ORTAK CSV'leri aynen). Keşiften sonra Ilyome'un trio filtresini ek bir eksen (`ilyome_denovo`) olarak eklemek mümkün.

---

## Sorun giderme

- **"Ilyome girisi basarisiz (401)"** — e-posta/parola. Hesap OTP istiyorsa kod sorulur.
- **"merkez on-eki eksik" / 404** — `ILYOME_CENTER="<merkez adı>"` ortam değişkenini verin (whoami çıktısındaki `center`).
- **"'X' N ornekle eslesti"** — Proband No'ya Ilyome'daki tam `sampleid`'yi yazın.
- **"tum tarama eksenleri 0 satir dondu"** — bu negatif sonuç DEĞİL, veri toplama hatasıdır; olgu HATA'ya düşer, raporlanmaz. Keşif çıktısıyla birlikte bildirin.
- **Excel yazılamadı** — `olgular.xlsx` açık; kapatıp yeniden çalıştırın (eski kural).
- Testler (giriş gerekmez): `python3 test_ilyome_seq.py && python3 test_rutin_ilyome_e2e.py`
