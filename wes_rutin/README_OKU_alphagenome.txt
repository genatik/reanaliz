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
                 PHRED, Atlas'in kalibre kantilinden turetilir; avi_ham
                 sutunu modelin ham logit'idir (SHAP katkilarinin toplami),
                 PHRED degildir.
  splicing     : max(SS)+max(SSU)+max(SJ)/5 (makale tanimi). Kanonik
                 splice site varyantlari 2,5-3,5; >=1,0 guclu, 0,5-1,0 olasi.
  kantil       : -1..1; |0,99| = yaygin varyant arka planinin en uc %1'i.
                 Yuzlerce doku/gen hucresi icinde en uc kantil HER varyantta
                 ~0,99 cikar (coklu karsilastirma). Bu yuzden yalniz AKTIF
                 dokularda (aktif alel skoru >= en aktif dokunun %10'u) ve
                 Bonferroni duzeltmesiyle (p = aktif hucre sayisi x (1-|kantil|)
                 <= 0,01) anlamli sayilir -> duzenleyici_sinyal sutunu
                 (ornek: "RNA_SEQ- (liver)"). *_p ve *_aktif sutunlari bunu verir.
  kategori     : yuksek = AVI>=20 ya da splicing>=1,0
                 orta   = AVI>=10 ya da splicing>=0,5 ya da duzenleyici sinyal
                 Siralama yardimcisidir, klinik esik DEGILDIR.
Atlas yalniz hg38 ve SNV icerir (v0.9 istemcisi indel/MNV kabul etmiyor);
indel ve MNV'ler canli AlphaGenome modeliyle (1 Mb pencere, olgu basina en
fazla 100, AVI skoru yok) skorlanir; varyant basina birkac saniye surer.
Referans genomu hg19 olan olgularda adim atlanir.
Tani / kalibrasyon: python alphagenome_sorgu.py --incele chr6:10961512:A:T
  (sunucunun ham yanitini incele_<key>.txt dosyasina yazar)

RAPORA NASIL GIRER:
  Kapsamli analiz raporu: "AlphaGenome Atlas degerlendirmesi" bolumu
  (alphagenome_rapor.txt'deki tablo + yorum + sinirlar).
  Sonuc/resmi rapor: Analiz Yontemi paragrafina tek cumle; raporlanan
  varyantta guclu/celisen sinyal varsa Yorum'da bir cumle.
  AlphaGenome skoru ACMG PP3/BP4 yerine GECMEZ; arastirma amaclidir,
  tek basina klinik karar verdirmez (kullanim kosullari da boyle der).
