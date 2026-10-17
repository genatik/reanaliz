# -*- coding: utf-8 -*-
r"""
yollar.py - ILYOME rutininin tum yollari TEK yerden; Windows ve Mac'te ayni kod.

Bu kurulum Genomize rutininden (WES_CES_Rutin_Raporlar/) TAMAMEN AYRIDIR:
ayri Drive koku, ayri olgular.xlsx, ayri olgu klasorleri, ayri kilit.

  Ilyome_Rutin_Raporlar/
      olgular.xlsx               <- Ilyome olgu listesi (tek kaynak)
      <Olgu Kodu>/               <- olgu klasoru: kanit/, KLINIK.txt, ozet.json, raporlar
      _sistem/                   <- kod, ILYOME_BASLAT_mac.command, log/

  Masaustu  Ilyome_Rutin/
      raporlar/<Olgu>/*.docx     <- raporlarin masaustu kopyasi (drive_esitle.py)

Drive bulunamazsa hicbir yere SESSIZCE donulmez; hata verilir.
"""
from __future__ import print_function
import datetime
import glob
import json
import os
import socket
import string
import sys

sys.dont_write_bytecode = True          # Drive'da __pycache__ birikmesin

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM = "ILYOME"                     # rutin.py bunu okur: bu kokte YALNIZ Ilyome olgulari
DRIVE_KLASOR_ADI = "Ilyome_Rutin_Raporlar"
SISTEM_ADI = "_sistem"
KOK_ADLARI = ("My Drive", "Drive'ım", "Drive'im", "Mi unidad", "Meine Ablage")
EV = os.path.expanduser("~")
MASAUSTU_KOPYA = os.path.join(EV, "Desktop", "Ilyome_Rutin", "raporlar")
KILIT_AD = "CALISIYOR.kilit"
KILIT_SURE_SAAT = 4                     # daha eski kilit bayat sayilir


def _adaylar():
    ev = os.environ.get("ILYOME_DRIVE_KOKU") or os.environ.get("WES_DRIVE_KOKU")
    if ev:
        yield ev
    # kod Drive'daki _sistem klasorunden calisiyorsa kok, bir ust klasordur
    if os.path.basename(HERE) == SISTEM_ADI:
        yield os.path.dirname(HERE)
    ayar = os.path.join(HERE, "drive_yolu.txt")
    if os.path.exists(ayar):
        with open(ayar, encoding="utf-8") as f:
            y = f.read().strip().strip('"')
        if y:
            yield y
    if os.name == "nt":
        for h in string.ascii_uppercase[3:]:            # D: .. Z:
            for ad in KOK_ADLARI:
                yield os.path.join(h + ":" + os.sep, ad, DRIVE_KLASOR_ADI)
    else:                                               # macOS
        for bulut in sorted(glob.glob(os.path.join(EV, "Library", "CloudStorage", "GoogleDrive-*"))):
            for ad in KOK_ADLARI:
                yield os.path.join(bulut, ad, DRIVE_KLASOR_ADI)
        for ad in KOK_ADLARI:
            yield os.path.join("/Volumes/GoogleDrive", ad, DRIVE_KLASOR_ADI)
    for ad in KOK_ADLARI:                               # yansitma (mirror) modu
        yield os.path.join(EV, ad, DRIVE_KLASOR_ADI)


def drive_koku():
    """Drive'daki Ilyome_Rutin_Raporlar klasorunun yerel yolu; yoksa None."""
    for a in _adaylar():
        try:
            if os.path.isdir(a):
                return a
        except OSError:
            pass
    return None


def veri_koku():
    """olgular.xlsx ve olgu klasorlerinin koku (= Drive klasoru)."""
    d = drive_koku()
    if not d:
        raise SystemExit(
            "Google Drive klasoru bulunamadi (%s).\n"
            "Google Drive uygulamasinin acik ve oturumun acik oldugundan emin olun,\n"
            "sonra tekrar deneyin." % DRIVE_KLASOR_ADI)
    return d


def rapor_koku():
    """Olgu klasorlerinin koku: Drive klasorunun kendisi."""
    return veri_koku()


def sistem_klasoru():
    return os.path.join(veri_koku(), SISTEM_ADI)


def olgular_xlsx():
    return os.path.join(veri_koku(), "olgular.xlsx")


def miseq_xlsx():
    """Ilyome kurulumunda MiSeq run listesi YOK; eski araclar cagirirsa yol doner, dosya bulunmaz."""
    return os.path.join(veri_koku(), "MiSeq_Run_Pediatri.xlsx")


def olgu_klasorleri():
    """Drive kokundeki olgu klasorleri (_sistem ve gizli klasorler haric)."""
    k = veri_koku()
    return sorted(os.path.join(k, a) for a in os.listdir(k)
                  if os.path.isdir(os.path.join(k, a)) and not a.startswith(("_", ".")))


# ---------------------------------------------------------------- kilit
def _kilit_yolu():
    return os.path.join(sistem_klasoru(), KILIT_AD)


def kilit_al():
    """Iki bilgisayarin ayni anda calismasini engelle. Basari: 0, dolu: 1."""
    p = _kilit_yolu()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                k = json.load(f)
            bas = datetime.datetime.fromisoformat(k.get("baslangic"))
            yas = (datetime.datetime.now() - bas).total_seconds() / 3600.0
        except Exception:
            k, yas = {}, 0.0
        if yas < KILIT_SURE_SAAT:
            print("  !! Rutin su anda baska bir yerde calisiyor: %s (%s, %.0f dk once basladi)."
                  % (k.get("bilgisayar", "?"), k.get("sistem", "?"), yas * 60))
            print("     Bitmesini bekleyin. Pencere kapanip kilit takili kaldiysa:")
            print("     python yollar.py --kilit-birak")
            return 1
        print("  (bayat kilit bulundu, %.1f saatlik - yok sayiliyor)" % yas)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"bilgisayar": socket.gethostname(), "sistem": sys.platform,
                   "baslangic": datetime.datetime.now().isoformat(timespec="seconds")}, f)
    return 0


def kilit_birak(zorla=False):
    """Kilidi kaldir. zorla=False iken YALNIZ bu bilgisayarin kilidi silinir:
    Mac'te gec kapatilan bir pencere, Windows'ta o sirada baslamis bir
    calismanin kilidini silmesin."""
    p = _kilit_yolu()
    if not zorla:
        try:
            with open(p, encoding="utf-8") as f:
                if json.load(f).get("bilgisayar") != socket.gethostname():
                    return 0
        except Exception:
            pass
    try:
        os.remove(p)
    except OSError:
        pass
    return 0


# ---------------------------------------------------------------- BASLAT on-kontrolu
def _benzerler(klasor, kok_ad):
    """'olgular (1).xlsx', 'olgular.gsheet' gibi ikinci kopyalar."""
    taban = kok_ad.lower()
    out = []
    for ad in os.listdir(klasor):
        a = ad.lower()
        if a == taban + ".xlsx" or a.startswith("~$"):
            continue
        if a.startswith(taban) and (a.endswith(".xlsx") or a.endswith(".gsheet")):
            out.append(ad)
    return out


def durum_yaz():
    """Veri klasoru, dosya tarihleri, ikinci kopya uyarisi. Uyari varsa 1 (BASLAT durur)."""
    kok = veri_koku()
    print("  Veri klasoru : " + kok)
    sorun = False
    for ad, kok_ad in (("olgular.xlsx", "olgular"),):
        yol = os.path.join(kok, ad)
        if os.path.exists(yol):
            t = datetime.datetime.fromtimestamp(os.path.getmtime(yol))
            print("  %-24s son degisiklik: %s" % (ad, t.strftime("%d.%m.%Y %H:%M")))
        else:
            print("  !! %s bulunamadi" % ad)
            sorun = True
        for b in _benzerler(kok, kok_ad):
            sorun = True
            print("  !! Ikinci kopya var: %s" % b)
            if b.lower().endswith(".gsheet"):
                print("     (Google E-Tablolar'a donusturulmus kopya - rutin bunu OKUMAZ.")
                print("      Degisiklikleri %s'e girin, bu kopyayi silin.)" % ad)
            else:
                print("     (Drive'a ayni adla ikinci kez yuklenmis - rutin yalniz %s'i okur." % ad)
                print("      Guncel olani %s adiyla birakin, digerini silin.)" % ad)
    return 1 if sorun else 0


if __name__ == "__main__":
    if "--kilit-birak" in sys.argv:
        kilit_birak(zorla=True); print("kilit kaldirildi"); sys.exit(0)
    print("Platform      :", PLATFORM)
    print("Drive klasoru :", drive_koku() or "BULUNAMADI")
    try:
        print("olgular.xlsx  :", olgular_xlsx())
        print("Sistem        :", sistem_klasoru())
        print("Olgu klasoru  :", len(olgu_klasorleri()))
        print("Masaustu kopya:", MASAUSTU_KOPYA if os.path.isdir(MASAUSTU_KOPYA) else "(yok)")
    except SystemExit as e:
        print("HATA:", e)
