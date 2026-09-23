--------------------------------------------------------
ALPHAGENOME ATLAS (Google DeepMind) - DUZENLEYICI/SPLICING ETKI
--------------------------------------------------------
Rutin, probandin aday varyantlarini (eksenler + DENOVO_* + ORTAK_*)
AlphaGenome Atlas API'sine sorar ve kanit/ icine yazar:
  alphagenome.csv        varyant basina ozet (AVI PHRED skoru, modalite
                         bazli kalibre kantil skorlari, birlesik splicing,
                         kategori yuksek/orta/dusuk, Turkce yorum)
  alphagenome_detay.csv  varyant x skor x doku (en yuksek 5 doku)
  alphagenome_ozet.json  calisma bilgisi, sunucudaki skor adlari, hatalar
  alphagenome_rapor.txt  RAPORA GIRECEK HAZIR METIN (kapsamli rapor
                         bolumu + resmi raporun yontem cumlesi + kaynakca)
Ozet ayrica ozet.json > "alphagenome" altinda ve olgular.xlsx
Sonuc Ozeti sutununda ("AlphaGenome yuksek N / orta M") gorunur.

KURULUM (bir kez, her bilgisayarda):
  1) python -m pip install alphagenome        (Python 3.10+ gerekir)
  2) API anahtari (ucretsiz, ticari olmayan kullanim):
        https://alphagenome.google/api
  3) Windows: setx ALPHAGENOME_API_KEY "anahtar"
     Mac    : anahtari ~/.alphagenome_api_key dosyasina yazin
              (ya da ~/.zprofile icine export ALPHAGENOME_API_KEY="anahtar")
  Anahtar ya da paket yoksa adim SESSIZCE ATLANIR, olgu HATA'ya
  dusmez; ozet.json'da nedeni yazar.

VAR OLAN OLGULARA SONRADAN EKLEMEK (Genomize gerekmez):
  python rutin.py --alphagenome 222080-DOR-HAY
  python rutin.py --alphagenome TUMU
  (yalniz kanit/ dosyalarini ve ozet.json'u gunceller; olgular.xlsx'teki
   Sonuc Ozeti sutununa dokunmaz - o sutun rutin calisirken yazilir)
Tek varyant / skor listesi:
  python alphagenome_sorgu.py --varyant chr12:13865958:C:T
  python alphagenome_sorgu.py --skorlar-listele

SKORLARIN ANLAMI:
  AVI (PHRED)  : tum SNV'ler icinde siralama; 10 = en yuksek %10,
                 20 = en yuksek %1, 30 = en yuksek %0,1. >45 protein/
                 splicing duzeyi, 5-22,5 arasi duzenleyici bolge duzeyi.
  kantil       : -1..1; |0,99| = yaygin varyant arka planinin en uc %1'i.
                 Isaret yonu gosterir (ekspresyonda - azalma).
  splicing     : max(SS)+max(SSU)+max(SJ)/5; >1,0 genellikle buyuk etki.
  kategori     : yuksek = AVI>=20 ya da |kantil|>=0,99 ya da splicing>=1,0
                 orta   = AVI>=10 ya da |kantil|>=0,95 ya da splicing>=0,5
                 Siralama yardimcisidir, klinik esik DEGILDIR.
Atlas yalniz hg38 ve on-hesaplanmis SNV/indel icerir; bulunmayanlar
canli modelle (1 Mb pencere, en fazla 25 varyant) skorlanir.
Referans genomu hg19 olan olgularda adim atlanir.

RAPORA NASIL GIRER:
  Kapsamli analiz raporu: "AlphaGenome Atlas degerlendirmesi" bolumu
  (alphagenome_rapor.txt'deki tablo + yorum + sinirlar).
  Sonuc/resmi rapor: Analiz Yontemi paragrafina tek cumle; raporlanan
  varyantta guclu/celisen sinyal varsa Yorum'da bir cumle.
  AlphaGenome skoru ACMG PP3/BP4 yerine GECMEZ; arastirma amaclidir,
  tek basina klinik karar verdirmez (kullanim kosullari da boyle der).
