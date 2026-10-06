# -*- coding: utf-8 -*-
r"""duzeltme_hpo_otomatik.py - rutin.py'yi hpo_otomatik.py'ye baglar.

Sorun: HPO el sikismasi acik bir Claude oturumu gerektiriyordu. Oturum yoksa
rutin 15 dk bekleyip "HPO'suz devam edilsin mi?" diye soruyor, kabul edilirse
FENOTIP EKSENI CALISMIYORDU. 03.10.2026 kosusunda 15 olgunun 15'i bu durumda
kaldi; oysa 14'unun klinik bilgisi MiSeq listesinden ZATEN gelmisti.

Cozum: bekleyenler() cagrilmadan hemen once, HPO'su bos her olgunun Klinik
Bilgi metni hpo_otomatik.terimler() ile eslestirilir ve bulunan terimler HPO
sutununa yazilir. bekleyenler() zaten "HPO_BEKLIYOR + HPO dolu -> BEKLIYOR"
kuralini isletir, yani eslesen olgu el sikismaya HIC girmez.

Eslesmeyen olgu (klinik bilgi bos ya da taninmayan ifade) eskisi gibi
el sikismaya girer ve size sorulur - betik terim UYDURMAZ.

Yazilan her terim ekrana ve _sistem/log'a dokulur; HPO sutunundan da
gorulur, boylece hangi fenotiple calisildigi her zaman denetlenebilir.

    python3 duzeltme_hpo_otomatik.py            # _sistem klasorunden
    python3 duzeltme_hpo_otomatik.py --deneme   # yalnizca ne yapacagini yaz

Ayni dosyaya iki kez uygulanabilir. Degistirmeden once .yedek_hpo birakir.
Not: hpo_otomatik.py'nin de _sistem klasorunde olmasi gerekir.
"""
from __future__ import print_function
import argparse
import io
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
YEDEK_EKI = ".yedek_hpo"
DOSYA = "rutin.py"
KIMLIK = "HPO otomatik uretildi:"

ANKOR = "    sutun_garanti(ws, RUN_SUTUNU)\n    işler = bekleyenler(ws)"

BLOK = '''    # --- HPO'yu ONCE klinik bilgiden otomatik uret (hpo_otomatik.py).
    # Eslesen olgu el sikismaya hic girmez; eslesmeyen olgu eskisi gibi
    # sorulur. Asagidaki bekleyenler() "HPO dolu -> BEKLIYOR" kuralini isletir.
    # --qc-doldur adiminda calismaz (o adim Excel'e dokunmaz).
    if not a.qc_doldur:
        try:
            import hpo_otomatik as _HO
            _yazilan = []
            for _r in range(BASLIK_SATIRI + 1, ws.max_row + 1):
                _kod = str(hucre(ws, _r, "Olgu Kodu") or "").strip()
                if not _kod or hpo_dolu(ws, _r):
                    continue
                if str(hucre(ws, _r, "Durum") or "").strip().upper() not in (
                        ISLENECEK, HPO_BEKLENIYOR):
                    continue
                _t = _HO.terimler(str(hucre(ws, _r, "Klinik Bilgi") or ""))
                if _t:
                    yaz(ws, _r, "HPO (istege bagli)", ", ".join(_t))
                    _yazilan.append((_kod, _t))
            if _yazilan:
                print("")
                print("  Klinik bilgiden HPO uretildi (hpo_otomatik.py):")
                for _kod, _t in _yazilan:
                    log("HPO otomatik uretildi: %s -> %s" % (_kod, ", ".join(_t)))
                excel_kaydet(wb)
        except Exception as _e:
            log("!! HPO otomatik uretimi atlandi: %s" % _e)

''' + ANKOR


def oku(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def yaz_dosya(p, s):
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(s)


def varsayilan_dizin():
    for d in (HERE, os.getcwd()):
        if os.path.exists(os.path.join(d, DOSYA)):
            return d
    return HERE


def main():
    ap = argparse.ArgumentParser(description="rutin.py -> hpo_otomatik baglantisi")
    ap.add_argument("--dizin", default=varsayilan_dizin(),
                    help="_sistem klasoru (varsayilan: bu dosyanin ya da calisma klasorunuz)")
    ap.add_argument("--deneme", action="store_true", help="yalnizca ne yapilacagini yaz")
    a = ap.parse_args()

    p = os.path.join(a.dizin, DOSYA)
    if not os.path.exists(p):
        print("!! bulunamadi: %s" % p)
        print("   Betigi _sistem klasorunden calistirin (ya da --dizin verin).")
        return 1
    yardimci = os.path.join(a.dizin, "hpo_otomatik.py")
    if not os.path.exists(yardimci):
        print("!! hpo_otomatik.py ayni klasorde yok: %s" % yardimci)
        print("   Once onu _sistem klasorune koyun.")
        return 1

    s = oku(p)
    if KIMLIK in s:
        print("  = zaten var: %s" % DOSYA)
        print("\nDuzeltme zaten uygulanmis, yapacak bir sey yok.")
        return 0
    if s.count(ANKOR) != 1:
        print("!! %s: capa %d kez bulundu (beklenen 1). Hicbir sey degistirilmedi."
              % (DOSYA, s.count(ANKOR)))
        return 1

    yeni = s.replace(ANKOR, BLOK, 1)   # BLOK capayi kendi icinde korur
    print("  + rutin.py, HPO'yu klinik bilgiden kendisi uretecek")
    print("    (eslesmeyen olgular eskisi gibi size sorulur)")

    try:
        compile(yeni, DOSYA, "exec")
    except SyntaxError as e:
        print("!! %s yamalandiktan sonra gecersiz olurdu (%s). Hicbir sey degistirilmedi."
              % (DOSYA, e))
        return 1

    if a.deneme:
        print("\n(--deneme) hicbir dosya yazilmadi.")
        return 0

    shutil.copyfile(p, p + YEDEK_EKI)
    yaz_dosya(p, yeni)
    print("\n%s guncellendi (eski hali: %s)" % (DOSYA, DOSYA + YEDEK_EKI))
    print("\nTamam. BASLAT artik cogu olguda HPO icin beklemeyecek.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
