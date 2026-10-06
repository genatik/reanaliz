# -*- coding: utf-8 -*-
r"""hpo_toplu.py - bir koşudaki TUM HPO_BEKLIYOR olgularina HPO yazar.

hpo_yaz.py tek olgu icindir; 15 olgu beklerken 15 kez calistirmak gerekiyordu.
Bu betik asagidaki PLAN tablosunu tek geciste isler:

  * her olgunun terimleri ontology.jax.org'da dogrulanir (hpo_yaz.dogrula),
  * SADECE tum terimleri gecerli olan olgular yazilir - bir olgudaki hatali
    terim digerlerini engellemez,
  * Durum HPO_BEKLIYOR ise BEKLIYOR yapilir (bekleyen rutin devam eder),
  * olgular.xlsx Excel'de ACIKSA hicbir sey yazilmaz.

    python hpo_toplu.py            # yaz
    python hpo_toplu.py --deneme   # yalnizca dogrula, yazma

Tablo bu kosuya ozeldir; kalici cozum icin hpo_otomatik.py'ye bakin.
"""
from __future__ import print_function
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

from openpyxl import load_workbook          # noqa: E402
import yollar as Y                          # noqa: E402
from hpo_yaz import dogrula                 # noqa: E402  (ayni dogrulama)

BASLIK = 3

# (Olgu Kodu, [HP kimlikleri], gerekce = Klinik Bilgi sutunundaki metin)
PLAN = [
    ("217464-NEH-OK",      ["HP:0004444", "HP:0001878", "HP:0001744", "HP:0000952"],
     "Herediter sferositoz"),
    ("217465-PIN-ELG",     ["HP:0001892", "HP:0003125"], "Koagulopati?"),
    ("217478-DUY-GUN",     ["HP:0001892", "HP:0003125"], "Koagulopati?"),
    ("217482-ELI-CAN",     ["HP:0001892", "HP:0003125"], "Koagulopati?"),
    ("217486-ZEY-BEY-YIL", ["HP:0001892", "HP:0003125"], "Koagulopati?"),
    ("217528-ABD-AFS",     ["HP:0001878", "HP:0001903"], "Kalitsal hemolitik anemi?"),
    ("217572-UMM-AKK",     ["HP:0001878", "HP:0001903"], "Kalitsal hemolitik anemi?"),
    ("217665-ZUM-GUL-SAT", ["HP:0000951"],               "Genodermatoz?"),
    ("217669-AYH-BAS",     ["HP:0000951"],               "Genodermatoz?"),
    ("217718-SAD-DOG",     ["HP:0001892", "HP:0003125"], "Koagulopati?"),
    ("217741-ENE-YAM",     ["HP:0000365"],               "Isitme kaybi"),
    ("217760-LEY-DUR-OGU", ["HP:0000957", "HP:0009733"],
     "Sol serebellar dusuk dereceli glial kitle + 2 adet cafe-au-lait"),
    ("217777-SEM-ARS",     ["HP:0001892", "HP:0003125"], "Koagulopati?"),
    ("217809-MUF-KIL",     ["HP:0001892", "HP:0003125"], "Koagulopati?"),
]


def main():
    ap = argparse.ArgumentParser(description="Toplu HPO yazimi")
    ap.add_argument("--deneme", action="store_true", help="yalnizca dogrula, yazma")
    a = ap.parse_args()

    p = Y.olgular_xlsx()
    kilit = os.path.join(os.path.dirname(p), "~$" + os.path.basename(p))
    if os.path.exists(kilit):
        print("!! olgular.xlsx Excel'de ACIK. Kapatip tekrar calistirin.")
        return 1

    # --- 1) dogrulama (tek tek, olgu bazinda)
    bellek, gecen, kalan = {}, [], []
    for olgu, hpo, gerekce in PLAN:
        kotu = []
        for h in hpo:
            if h not in bellek:
                bellek[h] = dogrula([h])[0]          # (id, ad, obsolete)
            _, ad, eski = bellek[h]
            if not ad or eski or ad.startswith("?"):
                kotu.append((h, ad, eski))
        if kotu:
            kalan.append((olgu, kotu))
        else:
            gecen.append((olgu, hpo, gerekce))

    print("")
    for olgu, hpo, gerekce in gecen:
        print("  %-22s %s" % (olgu, gerekce))
        for h in hpo:
            print("      %s  %s" % (h, bellek[h][1]))
    if kalan:
        print("\n  !! YAZILMAYACAK (gecersiz/eskimis terim):")
        for olgu, kotu in kalan:
            for h, ad, eski in kotu:
                print("     %-22s %s  %s%s" % (olgu, h, ad or "BULUNAMADI",
                                               " (OBSOLETE)" if eski else ""))

    if a.deneme:
        print("\n(--deneme) hicbir sey yazilmadi. Gecerli olgu: %d" % len(gecen))
        return 0
    if not gecen:
        print("\nYazilacak olgu yok.")
        return 1

    # --- 2) tek acilis, tek kayit
    wb = load_workbook(p)
    ws = wb["OLGULAR"]
    H = {str(ws.cell(BASLIK, c).value).strip(): c
         for c in range(1, ws.max_column + 1) if ws.cell(BASLIK, c).value}

    yazildi, bulunamadi = [], []
    for olgu, hpo, _ in gecen:
        satir = [r for r in range(BASLIK + 1, ws.max_row + 1)
                 if str(ws.cell(r, H["Olgu Kodu"]).value or "").strip() == olgu]
        if len(satir) != 1:
            bulunamadi.append((olgu, len(satir)))
            continue
        r = satir[0]
        ws.cell(r, H["HPO (istege bagli)"]).value = ", ".join(hpo)
        if str(ws.cell(r, H["Durum"]).value or "").strip().upper() == "HPO_BEKLIYOR":
            ws.cell(r, H["Durum"]).value = "BEKLIYOR"
        yazildi.append(olgu)

    if bulunamadi:
        print("\n  !! Olgu kodu eslesmedi (yazilmadi):")
        for olgu, n in bulunamadi:
            print("     %-22s %d satir" % (olgu, n))
    if not yazildi:
        print("\nHicbir satir eslesmedi; dosya degistirilmedi.")
        return 1

    wb.save(p)
    print("\n%d olguya HPO yazildi, Durum=BEKLIYOR yapildi." % len(yazildi))
    print("Bekleyen rutin bunu 20 sn icinde gorup devam eder.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
