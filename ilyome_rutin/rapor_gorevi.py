# -*- coding: utf-8 -*-
"""Rapor gorevi - VERI_HAZIR olgularin raporlarini yaz.

Bu dosya, raporu yazan Claude adiminin TEK gorev tanimidir. Hem Mac'teki
Claude Code (ILYOME_BASLAT'in 3/3 adimi) hem de bulut gorevi bunu okur. Degisiklik
gerekirse burayi degistirin; iki yol da ayni anda guncellenir.

    python rapor_gorevi.py      # gorev metnini ekrana yazar


GOREV
=====
olgular.xlsx icinde Durum = VERI_HAZIR olan ve _sistem/rapor/ icinde
vaka_<Proband No>.py surucusu BULUNMAYAN olgular icin o surucuyu yaz.

Belgeleri sen uretmezsin, Durum'u sen degistirmezsin: surucuyu yazdiktan sonra
raporla.py onu calistirip .docx'leri uretir ve olguyu TAMAMLANDI yapar.

Bir kosuda EN COK 3 olgu isle. Cok olgu varken acele etmek yerine siradakini
bir sonraki kosuya birak.


OKUNACAKLAR  (olgu klasoru = Drive koku/<Olgu Kodu>/)
====================================================
KLINIK.txt                               klinik bilgi, aile yapisi
ozet.json                                birey basina QC, derinlik, kapsama, eksen sayilari
kanit/<proband>_fenotip_iliskili.csv     HPO fenotip ekseni
kanit/<proband>_clinvar_patojenik.csv    ClinVar P/LP
kanit/<proband>_nadir_lof.csv            nadir islev kaybi
kanit/<proband>_homozigot_nadir.csv      homozigot
kanit/<proband>_tier.csv                 prioritizasyon
kanit/<proband>_cnv.csv                  kopya sayisi
kanit/alphagenome.csv                    varyant basina AVI, splicing, modalite
kanit/alphagenome_rapor.txt              hazir Turkce AlphaGenome bolumu
*_ARTEFAKT.csv                           kohort artefakti olarak elenenler - RAPORLAMAYIN

Bu kurulum ILYOME (ilyome.com) kurulumudur; kanit CSV'leri ilyome_seq.py ile
uretilir, sutun duzeni Genomize ile AYNIDIR (ek sutunlar sonda). Farklar:
* pathogenicity = Ilyome ACMG sinifi; autopat_score = Ilyome skoru (score_raw);
  ilyome_color (success/warning/danger) ve is_reported platform isaretleridir.
* tier ekseni = Ilyome'un "top-reportable" listesi (IA/IIA tier'i YOKTUR).
* gme sutunu = genoks_af (Turk kohort frekansi); raporda "Genoks" diye anin.
* internal_freq yalniz cohort_an >= 200 ise doludur; bos ise artefakt ayrimi
  YAPILMAMISTIR, dusuk kaliteli/tekrar bolgesi cagrilari sizin suzmeniz gerekir.
* omim sutunu Ilyome'un OMIM eslesmeleri, inheritance = HPO/Monarch kalitimi.
* Kunye: ozet.json["platform"] = "Ilyome", bireyler[..]["kit"] = Ilyome run adi
  (+capture), "pipeline" = Dragen, "genom" = hg38/hg19. Raporda "Genomize SEQ"
  YAZMAYIN; "Ilyome" ve run/kit bilgisini ozet.json'dan alin.


DEGERLENDIRME KURALLARI
=======================
* ACMG 2015 + Tavtigian 2020 bayes cercevesi.
* Kalibre in-siliko esikler: REVEL PP3 >= 0,644 ; BP4 <= 0,290. Arada kalan
  degerde HICBIRI uygulanmaz.
* Trio'da de novo ekseni en bilgilendirici eksendir; ebeveyn export'unda cagri
  yapilmamasi teknik yanlis pozitif uretir - derinlik ve kalite bakilmadan
  "de novo" denmez.
* Resesif modelde faz sart: iki alelin TRANS oldugu ebeveyn verisiyle ya da
  okuma duzeyi fazlama ile gosterilmedikce "bilesik heterozigot" denmez.
* Dusuk kaliteli (LQ) cagri tek basina rapora girmez; girerse Sanger
  dogrulamasi onerilir.
* Psodogeni olan genler (GBA1, CYP21A2, SMN1, PKD1, STRC, NEB...) ekzomla
  guvenilir degerlendirilemez - DISLANMADIGI acikca yazilir.
* Ekzomun goremedikleri (tekrar genislemesi, derin intronik, dengeli yapisal,
  damgalanma, mozaisizm, tam gen delesyonu) negatif raporda kisitlilik olarak
  yazilir.
* AlphaGenome DESTEKLEYICIDIR; PP3/BP4 yerine gecmez. Yuksek AVI kodlayici
  etkiden geliyorsa (ALPHAMISSENSE, PROTEIN_TERMINATION katkisi) REVEL'in
  verdigi bilgiyi tekrarlar, ek kanit sayilmaz.
* OMIM'de hastalik iliskisi olmayan gen -> aday gen bolumu, ARASTIRMA
  duzeyinde; resmi raporun sonucunu degistirmez.


URETILECEK DOSYA
================
_sistem/rapor/vaka_<Proband No>.py - ev duzenini kullanir:

    # -*- coding: utf-8 -*-
    \"\"\"<tarih> - <Olgu Kodu> (<tip>, <klinik>). <SONUC>.\"\"\"
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.dont_write_bytecode = True
    from build7 import ROOT, TARIH, sonuc_raporu, ebeveyn_raporu
    from negatif import kapsamli, resmi_normal, metrik

    KOD  = "<Olgu Kodu>"
    OZET = "<Sonuc Ozeti sutununa yazilacak TEK satir>"
    ...
    if __name__ == "__main__":
        ...
        print("toplam", len(CIK))

* KOD ve OZET ZORUNLUDUR; raporla.py ikisini de okur.
* Negatif olguda kapsamli() + sonuc_raporu() + resmi_normal(); trio/duo ise
  ayrica her ebeveyn icin ebeveyn_raporu().
* Pozitif olguda resmi rapor build7.resmi_raporu() (wes_patojenik.docx sablonu).
* Sablonlar _sistem/sablonlar/; yolu build_reports.TPLDIR verir, ELLE YAZMAYIN.
* Ornek: vaka_215876.py (trio, negatif, aday genli, AlphaGenome AG-1/AG-2 tablolu).


YAZMAYACAKLARIN
===============
* Kanitin soylemedigini yazma. Veri yetersizse surucuyu yine yaz ama sonucu
  "SONUCLANDIRILAMADI" olarak kur ve nedenini (kalite, eksik ebeveyn, eksik
  klinik) OZET'e koy - tahmin yurutme.
* Hicbir olgunun Durum'unu degistirme, olgular.xlsx'e dokunma.
* Zaten vaka_*.py surucusu olan olguyu yeniden yazma.
* Her rapor "KARAR-DESTEGI TASLAGI" uyarisiyla uretilir; degerlendirme ve imza
  genetik uzmanina aittir. Bu uyariyi kaldirma.
"""
from __future__ import print_function
import sys

GOREV = __doc__

if __name__ == "__main__":
    print(GOREV)
    sys.exit(0)
