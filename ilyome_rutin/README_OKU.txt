=================================================================
  ILYOME  WES / CES ANALIZ RUTINI - KULLANIM
=================================================================

Bu kurulum Genomize rutininden (WES_CES_Rutin_Raporlar/) TAMAMEN AYRIDIR:
ayri Drive koku, ayri olgu listesi, ayri olgu klasorleri, ayri kilit.
Genomize olgularini BU listeye girmeyin; Ilyome olgularini oraya girmeyin.

  Drive > Ilyome_Rutin_Raporlar/
      olgular.xlsx              Ilyome olgu listesi (tek kaynak)
      <Olgu Kodu>/              kanit/, KLINIK.txt, ozet.json, raporlar
      _sistem/                  kod, ILYOME_BASLAT_mac.command, log/

BASLATMAK (Mac): Masaustundeki ILYOME_BASLAT.command
  (kurulumda olusturulur; Drive'daki _sistem/ILYOME_BASLAT_mac.command'i calistirir)

Parola her seferinde gizli sorulur, HICBIR YERE KAYDEDILMEZ.
Iki bilgisayarda AYNI ANDA calistirmayin; kilit 4 saat sonra kendiliginden
duser; hemen kaldirmak icin _sistem icinde:  python3 yollar.py --kilit-birak

-----------------------------------------------------------------
NASIL KULLANILIR
-----------------------------------------------------------------
1) olgular.xlsx (Drive) > OLGULAR sayfasina olguyu girin.
   Zorunlu: Olgu Kodu, Test (WES/CES), Analiz Tipi (solo/duo/trio/kuartet),
            Proband No, Klinik Bilgi
   Proband / Anne / Baba No = Ilyome'daki ORNEK ADI (sampleid). Birden fazla
   ornek eslesirse rutin durur ve tam adi ister.
   Etkilenen Bireyler, Diger Bireyler, Hedef Genler: Genomize'daki gibi.
2) HPO: bos birakabilirsiniz; klinik bilgiden otomatik uretilir (hpo_otomatik),
   uretilemezse Claude planlar (HPO_BEKLIYOR el sikismasi).
3) Durum = BEKLIYOR.   4) EXCEL'I KAPATIN.
5) ILYOME_BASLAT.command'a cift tiklayin; Ilyome e-posta/parola sorulur.
6) Her olgu icin olgu klasoru dolar (KLINIK.txt, ozet.json, kanit/*.csv);
   satir VERI_HAZIR olur.
7) Raporlar: Mac'te 'claude' komutu varsa 3/3 adimi kendiliginden yazar;
   yoksa Claude'a "Ilyome rutini calisti, raporlari yaz" deyin.
   Indeks olgu: kapsamli analiz + sonuc + EUTF resmi rapor; ebeveyn basina
   1 resmi rapor. Satir TAMAMLANDI olur.

-----------------------------------------------------------------
TARAMA EKSENLERI (Ilyome)
-----------------------------------------------------------------
  fenotip_iliskili   HPO terimleri (filtre sablonu) + gnomAD AF <= %1
  nadir_lof          yikici sonuc, gnomAD AF <= %0,1
  clinvar_patojenik  ClinVar P / LP / celiskili-patojenik
  tier               Ilyome "top-reportable" listesi (platform onceliklendirmesi)
  homozigot_nadir    HOM/HEM, ACMG P/LP/VUS, gnomAD AF <= %0,5
  cnv                CNV listesi; Ilyome DB sikligi >= %30 -> cohort_artifact
  Hedef Genler dolu ise yalniz o genler (intronik/UTR dahil), eksenler calismaz.
Aile modelleri: ORTAK_*.csv (etkilenen kardesler), DENOVO_*.csv (trio).
Rutin Ilyome hesabinizda WES_RUTIN adli bir filtre sablonu kullanir; sizin
sablonlariniza dokunmaz.

Ilyome'da isinma (warmup) yoktur: ornek durumu "Finished" ise hemen sorgulanir.
MiSeq run listesi / klinik_dizin adimi bu kurulumda YOKTUR.

-----------------------------------------------------------------
DURUM DEGERLERI
-----------------------------------------------------------------
  BEKLIYOR    islenecek          VERI_HAZIR  veri toplandi, rapor bekliyor
  TAMAMLANDI  raporlar hazir     HATA        Sonuc Ozeti'nde neden yazar
  BEKLEMEDE   siz beklettiniz    ORNEK       ornek satir, atlanir
  HPO_BEKLIYOR  HPO'yu Claude yaziyor; rutin bekler

-----------------------------------------------------------------
KOMUT SATIRI (istege bagli, _sistem icinde)
-----------------------------------------------------------------
  python3 rutin.py --liste                 olgulari listele
  python3 rutin.py --tamamla "KOD" "ozet"  olguyu TAMAMLANDI isaretle
  python3 rutin.py --alphagenome KOD       yalniz AlphaGenome adimi
  python3 ilyome_seq.py kesfet ORNEK       API kesfi (ham yanitlar -> ilyome_kesif/)
  python3 ilyome_seq.py resolve ORNEK      ornegi bul
  python3 ilyome_seq.py qc ORNEK           kalite / kapsama
  python3 ilyome_seq.py hpo "seizure"      HPO terimi ara

-----------------------------------------------------------------
SORUN GIDERME
-----------------------------------------------------------------
"Ilyome girisi basarisiz (401)"   e-posta/parola; OTP istenirse kod sorulur
"merkez on-eki eksik" / 404       ILYOME_CENTER="<merkez adi>" ortam degiskeni
"'X' N ornekle eslesti"           Proband No'ya tam sampleid yazin
"tum tarama eksenleri 0 satir"    negatif sonuc DEGIL, veri toplama hatasi;
                                  olgu HATA'ya duser, RAPORLANMAZ
"olgular.xlsx YAZILAMADI"         Excel'de acik; kapatip tekrar calistirin

AlphaGenome Atlas: Genomize kurulumundaki gibi (pip install --user alphagenome,
anahtar ~/.alphagenome_api_key). Anahtar yoksa adim sessizce atlanir.

KAPSAM UYARISI: Ekzom derin intronik varyantlari, tekrar genislemelerini,
dengeli yapisal degisiklikleri, mtDNA'yi ve dusuk duzeyli mozaisizmi guvenilir
saptayamaz. Negatif sonuc genetik bir nedeni dislamaz. Tum raporlar
"karar-destegi taslagi" uyarisiyla uretilir; degerlendirme ve imza genetik
uzmanina aittir.
