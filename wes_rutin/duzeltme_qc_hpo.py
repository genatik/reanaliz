# -*- coding: utf-8 -*-
r"""duzeltme_qc_hpo.py - QC adiminin bosuna 15 dk HPO beklemesini onler.

Sorun (03.10.2026, olgu 215357-MER-MER): BASLAT, rutin.py'yi iki kez cagirir:

    python rutin.py --qc-doldur     # kalite/kapsama verisini tamamlar
    python rutin.py                 # asil tarama

rutin.py main() icinde sira soyleydi:

    sutun_garanti / bekleyenler
    HPO EL SIKISMASI  ...................  15 dk bekleme
    if a.qc_doldur: return qc_doldur(seq)   <-- denetim EN SONDA

Bu yuzden --qc-doldur cagrisi da HPO el sikismasina giriyor, 15 dk bekliyor,
kullaniciya "HPO'suz devam edilsin mi?" diye soruyor; ardindan asil tarama
ayni beklemeyi BASTAN yapiyor. Kullanici ayni soruyu iki kez goruyor ve
HPO'su olmayan tek bir olgu BASLAT'i 30 dakika mesgul ediyor.

Ikinci etki: eski sirada, bekleyen olgu YOKSA akis daha da erken,
"BEKLIYOR durumunda olgu yok" satirinda donuyordu; yani --qc-doldur o
durumda kendi isini hic yapmiyordu.

qc_doldur() yalnizca rapor klasorlerindeki ozet.json dosyalarini gezer;
Excel satirlariyla da HPO ile de isi yoktur. Bu nedenle denetimi el
sikismasindan ONCE'ye almak davranisi degistirmez, yalnizca gereksiz
beklemeyi kaldirir ve QC adimini her zaman calistirir.

    python3 duzeltme_qc_hpo.py            # _sistem klasorunden calistirin
    python3 duzeltme_qc_hpo.py --deneme   # yalnizca ne yapacagini yazar

Ayni dosyaya iki kez uygulanabilir. Degistirmeden once .yedek_qc birakir.
"""
from __future__ import print_function
import argparse
import io
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
YEDEK_EKI = ".yedek_qc"
DOSYA = "rutin.py"
KIMLIK = "return qc_doldur(G.Seq())"

ANKOR = "    sutun_garanti(ws, RUN_SUTUNU)\n    işler = bekleyenler(ws)"

ONCE = (
    "    # --qc-doldur yalnizca tamamlanmis olgularin ozet.json'una kalite\n"
    "    # verisi ekler; Excel satirlariyla ya da HPO ile isi yoktur. Bu\n"
    "    # denetim eskiden HPO el sikismasindan SONRA geldigi icin BASLAT'in\n"
    "    # QC adimi da 15 dk HPO bekliyor, kullanici ayni soruyu iki kez\n"
    "    # goruyordu (once QC adiminda, sonra asil taramada).\n"
    "    if a.qc_doldur:\n"
    "        return qc_doldur(G.Seq())\n"
    "\n"
)

ESKI_SON = "    seq = G.Seq()\n    if a.qc_doldur:\n        return qc_doldur(seq)\n"
YENI_SON = "    seq = G.Seq()\n"


def oku(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def yaz(p, s):
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(s)


def varsayilan_dizin():
    for d in (HERE, os.getcwd()):
        if os.path.exists(os.path.join(d, DOSYA)):
            return d
    return HERE


def main():
    ap = argparse.ArgumentParser(description="QC adiminda gereksiz HPO beklemesi duzeltmesi")
    ap.add_argument("--dizin", default=varsayilan_dizin(),
                    help="_sistem klasoru (varsayilan: bu dosyanin ya da calisma klasorunuz)")
    ap.add_argument("--deneme", action="store_true", help="yalnizca ne yapilacagini yaz")
    a = ap.parse_args()

    p = os.path.join(a.dizin, DOSYA)
    if not os.path.exists(p):
        print("!! bulunamadi: %s" % p)
        print("   Betigi _sistem klasorunden calistirin (ya da --dizin verin).")
        return 1

    s = oku(p)
    if KIMLIK in s:
        print("  = zaten var: %s" % DOSYA)
        print("\nDuzeltme zaten uygulanmis, yapacak bir sey yok.")
        return 0

    for ad, metin, bek in (("el sikisma capasi", ANKOR, 1), ("qc-doldur denetimi", ESKI_SON, 1)):
        if s.count(metin) != bek:
            print("!! %s: %s %d kez bulundu (beklenen %d). Hicbir sey degistirilmedi."
                  % (DOSYA, ad, s.count(metin), bek))
            return 1

    yeni = s.replace(ANKOR, ONCE + ANKOR, 1).replace(ESKI_SON, YENI_SON, 1)
    print("  + --qc-doldur denetimi HPO el sikismasindan ONCE'ye alindi")
    print("    (QC adimi artik HPO beklemiyor; bekleme yalnizca asil taramada)")

    try:
        compile(yeni, DOSYA, "exec")
    except SyntaxError as e:
        print("!! %s yamalandiktan sonra gecersiz olurdu (%s). Hicbir sey degistirilmedi." % (DOSYA, e))
        return 1

    if a.deneme:
        print("\n(--deneme) hicbir dosya yazilmadi.")
        return 0

    shutil.copyfile(p, p + YEDEK_EKI)
    yaz(p, yeni)
    print("\n%s guncellendi (eski hali: %s)" % (DOSYA, DOSYA + YEDEK_EKI))
    print("\nTamam. BASLAT artik HPO'yu yalnizca bir kez, asil taramada bekler.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
