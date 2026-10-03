# -*- coding: utf-8 -*-
r"""duzeltme_mac_sablon.py - sablon klasorunu Mac'te de bulunur hale getirir.

Sorun 1: build_reports.py icinde sablon klasoru Windows'a sabitlenmis:

    TPLDIR = r"K:\My Drive\WES_CES_Rutin_Raporlar\_sistem\sablonlar"

macOS'ta K: diye bir surucu yoktur; resmi rapor uretilirken
"FileNotFoundError: ... K:\My Drive\...\sablonlar/wes_normal.docx" alinir.
Sablon kullanan uc fonksiyonun ucu de bu tek degiskeni kullanir:
negatif.resmi_normal (wes_normal.docx), build7.resmi_raporu
(wes_patojenik.docx) ve build7.ebeveyn_raporu (wes_trio_ebeveyn.docx).

Sorun 2: dosyanin basindaki

    os.makedirs(OUT, exist_ok=True)

satiri 209711 olgusunun tek seferlik Windows cikti klasorunu her ice
aktarmada yaratmaya calisir. macOS'ta ters bolu gecerli bir dosya adi
karakteri oldugu icin calisma klasorunde
"C:\Users\Huseyin Onay\Downloads\WES_209711-OYK-ZEY-OZC" adinda tek parca,
cop bir klasor olusur.

Cozum: TPLDIR dosyanin kendi konumundan bulunur (_sistem/rapor/ ->
_sistem/sablonlar); bulunamazsa eski Windows yolu yedek olarak devrede
kalir, yani Windows'ta davranis aynen korunur. makedirs yalnizca
Windows'ta calisir.

    python3 duzeltme_mac_sablon.py            # rapor klasorunden calistirin
    python3 duzeltme_mac_sablon.py --deneme   # yalnizca ne yapacagini yazar

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
DOSYA = "build_reports.py"
KIMLIK = "_SIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))"
MAKEDIRS = "os.makedirs(OUT, exist_ok=True)"


def varsayilan_dizin():
    """Betik rapor klasorunde durabilir ya da indirilip baska yerden
    calistirilabilir; her iki durumda da build_reports.py'yi bul."""
    for d in (HERE, os.getcwd()):
        if os.path.exists(os.path.join(d, DOSYA)):
            return d
    return HERE


def oku(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def yaz(p, s):
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(s)


def yama(metin):
    """(yeni_metin, [yapilan_isler]) dondurur; capa bulunamazsa SystemExit."""
    satirlar = metin.splitlines(True)
    yapilan = []

    tpl = [i for i, s in enumerate(satirlar) if s.startswith("TPLDIR")]
    if len(tpl) != 1:
        raise SystemExit("%s: TPLDIR satiri %d kez bulundu (beklenen 1)" % (DOSYA, len(tpl)))
    i = tpl[0]
    eski_satir = satirlar[i].rstrip("\n")
    satirlar[i] = (
        "# Sablon klasoru bu dosyanin konumundan bulunur (_sistem/rapor/ -> _sistem/sablonlar).\n"
        "# Bulunamazsa asagidaki eski Windows yolu yedek olarak kullanilir.\n"
        "%s\n"
        "TPLDIR = os.path.join(_SIS, \"sablonlar\")\n"
        "if not os.path.isdir(TPLDIR):\n"
        "    %s\n" % (KIMLIK, eski_satir)
    )
    yapilan.append("TPLDIR dosya konumundan bulunacak")

    mk = [i for i, s in enumerate(satirlar) if s.strip() == MAKEDIRS]
    if len(mk) != 1:
        raise SystemExit("%s: makedirs satiri %d kez bulundu (beklenen 1)" % (DOSYA, len(mk)))
    i = mk[0]
    satirlar[i] = (
        "if os.name == \"nt\":                 # 209711'in eski tek seferlik cikti klasoru;\n"
        "    %s      # macOS'ta cop klasor yaratmasin\n" % MAKEDIRS
    )
    yapilan.append("OUT klasoru yalnizca Windows'ta yaratilacak")

    return "".join(satirlar), yapilan


def main():
    ap = argparse.ArgumentParser(description="Mac'te sablon klasoru duzeltmesi")
    ap.add_argument("--dizin", default=varsayilan_dizin(),
                    help="_sistem/rapor klasoru (varsayilan: bu dosyanin ya da calisma klasorunuz)")
    ap.add_argument("--deneme", action="store_true", help="yalnizca ne yapilacagini yaz")
    a = ap.parse_args()

    p = os.path.join(a.dizin, DOSYA)
    if not os.path.exists(p):
        print("!! bulunamadi: %s" % p)
        print("   Betigi _sistem/rapor klasorunden calistirin (ya da --dizin verin).")
        return 1

    s = oku(p)
    if KIMLIK in s:
        print("  = zaten var: %s" % DOSYA)
        print("\nDuzeltme zaten uygulanmis, yapacak bir sey yok.")
        return 0

    yeni, yapilan = yama(s)
    for i in yapilan:
        print("  + %s" % i)

    try:                                   # diske dokunmadan once sozdizimi
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

    sab = os.path.join(os.path.dirname(os.path.abspath(a.dizin)), "sablonlar")
    if os.path.isdir(sab):
        var = sorted(f for f in os.listdir(sab) if f.endswith(".docx"))
        print("Sablon klasoru: %s" % sab)
        print("  bulunan sablonlar: %s" % (", ".join(var) if var else "(bos!)"))
    else:
        print("!! UYARI: %s yok - sablonlari kontrol edin." % sab)

    print("\nTamam. Artik resmi raporlar da uretilebilir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
