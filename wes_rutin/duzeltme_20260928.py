# -*- coding: utf-8 -*-
r"""duzeltme_20260928.py - olgular.xlsx'e elle girilen verinin silinmesini onler.

Sorun (28.09.2026, olgu 215876-BUR-TUR):
  * Rutin, olgular.xlsx'i her calismada birkac kez bastan yaziyor. Mac'te
    openpyxl, dosya Excel'de ACIKKEN de uzerine yazabildigi icin kullanicinin
    o sirada elle girdigi HPO kodlari sessizce kayboluyordu.
  * HPO'su bos kalan satir HPO_BEKLIYOR'da takiliyor ve sonraki calismalarda
    HICBIR uyari vermeden atlaniyordu; kullanici kendi olgusu yerine baska bir
    olgunun analiz edildigini goruyordu.
  * HPO beklenirken dosya okunamazsa (Excel'de acikken) zaman asimi denetimi
    hic calismiyor, rutin 15 dk yerine saatlerce bekliyordu.

Bu betik _sistem klasorundeki rutin.py ve klinik_dizin.py dosyalarini yerinde
duzeltir. Ayni dosyaya iki kez uygulanabilir (ikinci kez hicbir sey yapmaz).
Degistirmeden once .yedek_20260928 uzantili bir kopya birakir.

    python duzeltme_20260928.py            # _sistem klasorunu kendisi bulur
    python duzeltme_20260928.py --deneme   # yalnizca ne yapacagini yazar
"""
from __future__ import print_function
import argparse
import io
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
YEDEK_EKI = ".yedek_20260928"

# (dosya, kimlik_dizesi, eski_metin, yeni_metin, aciklama)
YAMALAR = [
    ("rutin.py", 'kilit = os.path.join(os.path.dirname(XLSX), "~$"',
     '''    if not PENDING:
        return True
    try:
        taze = load_workbook(XLSX)''',
     '''    if not PENDING:
        return True
    # Excel dosyayi acikken tutuyorsa YAZMA. Mac'te openpyxl acik dosyanin
    # uzerine yazabiliyor; kullanicinin o sirada elle girdigi veri (or. HPO)
    # boylece sessizce kayboluyordu. PENDING temizlenmez: bir sonraki
    # excel_kaydet cagrisinda yeniden denenir.
    kilit = os.path.join(os.path.dirname(XLSX), "~$" + os.path.basename(XLSX))
    if os.path.exists(kilit):
        log("!! olgular.xlsx Excel'de ACIK - yazilmadi (elle girdiginiz veri korunsun diye).")
        log("   Dosyayi kapatin; kayit sonraki adimda yeniden denenir.")
        return False
    try:
        taze = load_workbook(XLSX)''',
     "Excel acikken olgular.xlsx'e yazilmaz"),

    ("rutin.py", "BU OLGULAR ANALIZ EDILMIYOR",
     '''    sutun_garanti(ws, RUN_SUTUNU)
    işler = bekleyenler(ws)

    # HPO EL SIKISMASI''',
     '''    sutun_garanti(ws, RUN_SUTUNU)
    işler = bekleyenler(ws)

    # HPO_BEKLIYOR'da kalmis ve HPO'su HALA bos satirlar hicbir listeye girmez.
    # Eskiden sessizce atlanirlardi: kullanici olgusunun neden islenmedigini
    # goremez, bunun yerine baska bir olgunun analiz edildigini gorurdu.
    unutulan = [str(hucre(ws, r, "Olgu Kodu")).strip()
                for r in range(BASLIK_SATIRI + 1, ws.max_row + 1)
                if str(hucre(ws, r, "Olgu Kodu") or "").strip()
                and str(hucre(ws, r, "Durum") or "").strip().upper() == HPO_BEKLENIYOR
                and not hpo_dolu(ws, r)]
    if unutulan:
        print("")
        print("  !! HPO sutunu hala bos - BU OLGULAR ANALIZ EDILMIYOR: %s" % ", ".join(unutulan))
        print("     HPO'yu Excel'e elle yazmak yerine (rutin dosyayi yeniden")
        print("     yazarken elle yapilan degisiklik kaybolabilir) sunu kullanin:")
        print("       python hpo_yaz.py \\"<Olgu Kodu>\\" \\"HP:0000717, HP:0000750\\"")
        log("!! HPO_BEKLIYOR + HPO bos, atlandi: %s" % ", ".join(unutulan))

    # HPO EL SIKISMASI''',
     "HPO'su bos olgu sessizce atlanmaz"),

    ("rutin.py", "asildi = time.time() - t0 > HPO_BEKLEME_SN",
     '''        while True:
            time.sleep(20)
            try:
                wb, ws = excel_ac()
            except SystemExit:
                continue                    # dosya o an yaziliyor olabilir''',
     '''        while True:
            time.sleep(20)
            asildi = time.time() - t0 > HPO_BEKLEME_SN
            try:
                wb, ws = excel_ac()
            except SystemExit:
                # Dosya o an yaziliyor olabilir - kisa sureli hata normaldir.
                # Ama Excel'de ACIK kaldiysa bu durum surer ve zaman asimi
                # denetimi bu dala hic ugramadigi icin rutin saatlerce beklerdi
                # (28.09.2026 kaydi: 15 dk yerine 62 dk).
                if not asildi:
                    continue
                print("")
                print("  !! olgular.xlsx %d dk boyunca okunamadi - Excel'de acik olabilir."
                      % (HPO_BEKLEME_SN // 60))
                print("     Dosyayi kapatip rutini yeniden baslatin.")
                log("HPO beklemesi: olgular.xlsx okunamadi (dosya acik?), beklemeden cikildi.")
                break''',
     "dosya okunamazken de zaman asimi isler"),

    ("rutin.py", "            if asildi:\n                print(\"\")",
     '''            if time.time() - t0 > HPO_BEKLEME_SN:
                print("")
                print("  !! %d dk icinde HPO yazilmadi:''',
     '''            if asildi:
                print("")
                print("  !! %d dk icinde HPO yazilmadi:''',
     "zaman asimi tek yerden hesaplanir"),

    ("klinik_dizin.py", "if dolduruldu:\n        try:\n            wb.save(XLSX)",
     '''    try:
        wb.save(XLSX)
    except PermissionError:
        sys.exit("olgular.xlsx acik - kapatip tekrar deneyin.")''',
     '''    # Doldurulacak bir sey yoksa dosyaya HIC dokunma. Her calismada yapilan
    # gereksiz tam yeniden yazma, ayni anda elle girilen veriyi (or. HPO)
    # silebiliyordu.
    if dolduruldu:
        try:
            wb.save(XLSX)
        except PermissionError:
            sys.exit("olgular.xlsx acik - kapatip tekrar deneyin.")''',
     "degisiklik yokken olgular.xlsx yeniden yazilmaz"),
]


def oku(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def yaz(p, s):
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(s)


def main():
    ap = argparse.ArgumentParser(description="28.09.2026 olgular.xlsx koruma duzeltmeleri")
    ap.add_argument("--dizin", default=HERE, help="_sistem klasoru (varsayilan: bu dosyanin yeri)")
    ap.add_argument("--deneme", action="store_true", help="yalnizca ne yapilacagini yaz")
    a = ap.parse_args()

    metinler, uygulanan, atlanan, eksik = {}, [], [], []
    for dosya, kimlik, eski, yeni, aciklama in YAMALAR:
        p = os.path.join(a.dizin, dosya)
        if not os.path.exists(p):
            sys.exit("bulunamadi: %s\n(--dizin ile _sistem klasorunu verin)" % p)
        s = metinler.get(dosya) or oku(p)
        if kimlik in s:
            atlanan.append(aciklama)
        elif s.count(eski) == 1:
            s = s.replace(eski, yeni)
            uygulanan.append((dosya, aciklama))
        else:
            eksik.append("%s: %s (%d eslesme)" % (dosya, aciklama, s.count(eski)))
        metinler[dosya] = s

    if eksik:
        print("!! Su yamalar uygulanamadi (dosya beklenenden farkli):")
        for e in eksik:
            print("   -", e)
        print("   Hicbir dosya degistirilmedi.")
        return 1

    for dosya, aciklama in uygulanan:
        print("  + %-16s %s" % (dosya, aciklama))
    for aciklama in atlanan:
        print("  = zaten var:     %s" % aciklama)

    if not uygulanan:
        print("\nDuzeltmeler zaten uygulanmis, yapacak bir sey yok.")
        return 0

    # Diske dokunmadan once yeni metnin sozdizimini dogrula.
    for dosya in sorted(set(d for d, _ in uygulanan)):
        try:
            compile(metinler[dosya], dosya, "exec")
        except SyntaxError as e:
            print("!! %s yamalandiktan sonra gecersiz olurdu (%s). Hicbir dosya degistirilmedi." % (dosya, e))
            return 1

    if a.deneme:
        print("\n(--deneme) hicbir dosya yazilmadi.")
        return 0

    for dosya in sorted(set(d for d, _ in uygulanan)):
        p = os.path.join(a.dizin, dosya)
        shutil.copyfile(p, p + YEDEK_EKI)
        yaz(p, metinler[dosya])
        print("\n%s guncellendi (eski hali: %s)" % (dosya, os.path.basename(p) + YEDEK_EKI))

    print("\nTamam. Artik BASLAT'i normal sekilde kullanabilirsiniz.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
