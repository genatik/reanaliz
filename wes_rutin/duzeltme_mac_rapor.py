# -*- coding: utf-8 -*-
r"""duzeltme_mac_rapor.py - rapor uretimini Mac'te de calisir hale getirir.

Sorun: build7.py ve aday_ozet.py icindeki _sistem_bul(), Drive kokunu
YALNIZCA Windows surucu harflerini tarayarak buluyor:

    for h in string.ascii_uppercase[3:]:
        p = os.path.join(h + ":" + os.sep, "My Drive", "WES_CES_Rutin_Raporlar", "_sistem")

macOS'ta boyle bir yol hicbir zaman olusmaz; betik
"Drive _sistem klasoru bulunamadi" / "_sistem yok" ile cikar. Sonuc: analiz
(BASLAT) iki bilgisayarda da calisirken RAPOR URETIMI yalnizca Windows'ta
calisiyor.

Cozum: bu iki dosya zaten _sistem/rapor/ icinde durdugundan, Drive koku
dosyanin kendi konumundan bilinir. Surucu harfi taramasindan ONCE bu
denetim eklenir; tarama yedek olarak kalir. Isletim sistemi bagimsiz.

    python3 duzeltme_mac_rapor.py            # rapor klasorunden calistirin
    python3 duzeltme_mac_rapor.py --deneme   # yalnizca ne yapacagini yazar

Ayni dosyaya iki kez uygulanabilir (ikinci kez hicbir sey yapmaz).
Degistirmeden once .yedek_mac uzantili bir kopya birakir.
"""
from __future__ import print_function
import argparse
import io
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
YEDEK_EKI = ".yedek_mac"

KIMLIK = "_ust = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))"

ANKOR = ('    for h in string.ascii_uppercase[3:]:\n'
         '        p = os.path.join(h + ":" + os.sep, "My Drive", "WES_CES_Rutin_Raporlar", "_sistem")')

YENI = ('    # Bu dosya _sistem/rapor/ icinde durur; Drive koku kendi konumundan bilinir.\n'
        '    # Windows surucu harfi taramasi yedek olarak asagida kalir (macOS\'ta islemez).\n'
        '    _ust = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n'
        '    if os.path.basename(_ust) == "_sistem" and os.path.isdir(_ust):\n'
        '        return _ust\n'
        + ANKOR)

DOSYALAR = ["build7.py", "aday_ozet.py"]


def oku(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def yaz(p, s):
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(s)


def main():
    ap = argparse.ArgumentParser(description="Mac'te rapor uretimi duzeltmesi")
    ap.add_argument("--dizin", default=HERE, help="_sistem/rapor klasoru (varsayilan: bu dosyanin yeri)")
    ap.add_argument("--deneme", action="store_true", help="yalnizca ne yapilacagini yaz")
    a = ap.parse_args()

    metinler, uygulanan, atlanan, eksik = {}, [], [], []
    for dosya in DOSYALAR:
        p = os.path.join(a.dizin, dosya)
        if not os.path.exists(p):
            eksik.append("%s bulunamadi" % p)
            continue
        s = oku(p)
        if KIMLIK in s:
            atlanan.append(dosya)
        elif s.count(ANKOR) == 1:
            metinler[dosya] = s.replace(ANKOR, YENI)
            uygulanan.append(dosya)
        else:
            eksik.append("%s: capa %d kez bulundu (beklenen 1)" % (dosya, s.count(ANKOR)))

    if eksik:
        print("!! Uygulanamadi:")
        for e in eksik:
            print("   -", e)
        print("   Hicbir dosya degistirilmedi.")
        return 1

    for d in uygulanan:
        print("  + %-14s Drive koku dosya konumundan bulunacak" % d)
    for d in atlanan:
        print("  = zaten var:   %s" % d)
    if not uygulanan:
        print("\nDuzeltme zaten uygulanmis, yapacak bir sey yok.")
        return 0

    for d in uygulanan:                       # diske dokunmadan once sozdizimi
        try:
            compile(metinler[d], d, "exec")
        except SyntaxError as e:
            print("!! %s yamalandiktan sonra gecersiz olurdu (%s). Hicbir sey degistirilmedi." % (d, e))
            return 1

    if a.deneme:
        print("\n(--deneme) hicbir dosya yazilmadi.")
        return 0

    for d in uygulanan:
        p = os.path.join(a.dizin, d)
        shutil.copyfile(p, p + YEDEK_EKI)
        yaz(p, metinler[d])
        print("\n%s guncellendi (eski hali: %s)" % (d, d + YEDEK_EKI))

    print("\nTamam. Rapor betikleri (vaka_*.py) artik Mac'te de calisir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
