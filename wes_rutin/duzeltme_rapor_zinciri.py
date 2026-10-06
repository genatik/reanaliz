# -*- coding: utf-8 -*-
r"""duzeltme_rapor_zinciri.py - BASLAT'i rapor yazimina kadar goturur.

Sorun: rutin.py analizi bitirip olguyu VERI_HAZIR yapiyor ve ekrana "Claude
raporlari KENDILIGINDEN yazar (izleme gorevi...)" yaziyordu - ama bunu yapan
hicbir kod yoktu. Ne BASLAT.bat'ta ne rutin.py'de rapor adimi var; zincir
analizden sonra kopuyordu.

Bu betik eksik halkayi kurar:

  1) RAPORLA.bat (Windows) / RAPORLA_mac.command (Mac) olusturur:
       - Claude Code kuruluysa rapor_gorevi.py'deki gorevi calistirir
         (VERI_HAZIR olgulara vaka_*.py surucusu yazar),
       - sonra raporla.py ile belgeleri uretip olgulari TAMAMLANDI yapar.
       Claude Code yoksa yorum adimi atlanir, bulut gorevi onu yazar;
       raporla.py yine de calisir ve hazir surucüleri isler.
  2) BASLAT'a bu adimi ekler (kilit hala tutulurken calisir, boylece
     rapor yazimi sirasinda ikinci bir kosu baslayamaz).

    python duzeltme_rapor_zinciri.py            # _sistem klasorunden
    python duzeltme_rapor_zinciri.py --deneme   # yalnizca ne yapacagini yaz

Ayni dosyaya iki kez uygulanabilir. BASLAT dosyalarinin .yedek_zincir kopyasi
birakilir. Yalnizca bu isletim sisteminin baslaticisi guncellenir; digerini
o makinede calistirin (iki dosya da Drive'da ayni klasordedir).
"""
from __future__ import print_function
import argparse
import io
import os
import shutil
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
YEDEK_EKI = ".yedek_zincir"
KIMLIK = "RAPORLA"

ISTEM = ("_sistem klasorundeki rapor_gorevi.py dosyasini oku ve icindeki gorevi "
         "yerine getir. Baska bir sey yapma.")

BAT = """@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title WES / CES Rapor Yazimi

echo.
echo ----------------------------------------------------------------------
echo   3/3  Raporlar yaziliyor...
echo ----------------------------------------------------------------------
echo.

REM --- 1) Yorum adimi: kanit tablolarini okuyup vaka_*.py surucusunu yazar.
REM     Claude Code kurulu degilse atlanir; bulut gorevi ayni isi yapar.
where claude >nul 2>nul
if errorlevel 1 (
  echo   Claude Code kurulu degil - yorum adimi atlandi.
  echo   Surucüleri bulut gorevi yazacak; sonra bu dosyaya cift tiklayin.
) else (
  echo   Claude Code bulundu; VERI_HAZIR olgulara bakiliyor...
  claude -p "{ISTEM}" --permission-mode acceptEdits
  if errorlevel 1 echo   UYARI: yorum adimi hata verdi - hazir surucüler yine islenecek.
)

REM --- 2) Hazir surucüleri calistir, belgeleri uret, olgulari kapat
echo.
python raporla.py
set RC=%errorlevel%

echo.
if not "%RC%"=="0" echo   Bazi olgular raporlanamadi - yukaridaki satirlara bakin.
if "%1"=="--zincir" goto :son
echo Bu pencereyi kapatabilirsiniz.
pause
:son
endlocal
"""

SH = """#!/bin/bash
# WES / CES rapor yazimi (Mac). Finder'da cift tiklanabilir.
cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1

echo
echo "----------------------------------------------------------------------"
echo "  3/3  Raporlar yaziliyor..."
echo "----------------------------------------------------------------------"
echo

# --- 1) Yorum adimi: kanit tablolarini okuyup vaka_*.py surucusunu yazar.
if command -v claude >/dev/null 2>&1; then
  echo "  Claude Code bulundu; VERI_HAZIR olgulara bakiliyor..."
  claude -p "{ISTEM}" --permission-mode acceptEdits \\
    || echo "  UYARI: yorum adimi hata verdi - hazir surucüler yine islenecek."
else
  echo "  Claude Code kurulu degil - yorum adimi atlandi."
  echo "  Surucüleri bulut gorevi yazacak; sonra bu dosyaya cift tiklayin."
fi

# --- 2) Hazir surucüleri calistir, belgeleri uret, olgulari kapat
echo
python3 raporla.py
RC=$?

echo
[ "$RC" != "0" ] && echo "  Bazi olgular raporlanamadi - yukaridaki satirlara bakin."
if [ "$1" != "--zincir" ]; then
  read -r -p "Kapatmak icin Enter'a basin... " _
fi
exit "$RC"
"""

# (dosya, capa, eklenecek satirlar)  - capa KORUNUR, blok capadan ONCE girer
YAMALAR = [
    ("BASLAT.bat",
     'python -c "import yollar as Y; Y.kilit_birak()"',
     'REM --- 3/3 Raporlar (kilit hala tutuluyor; ikinci kosu baslayamaz)\r\n'
     'call "%~dp0RAPORLA.bat" --zincir\r\n'
     '\r\n'),
    ("BASLAT_mac.command",
     'temizle; trap - EXIT',
     '# --- 3/3 Raporlar (kilit hala tutuluyor; ikinci kosu baslayamaz)\n'
     'bash "$(dirname "$0")/RAPORLA_mac.command" --zincir\n'
     '\n'),
]


def oku(p):
    with io.open(p, encoding="utf-8", newline="") as f:      # satir sonlarini koru
        return f.read()


def yaz(p, s):
    """Satir sonunu dosya turune gore yazar.

    .bat dosyasi CRLF olmali: cmd.exe yalnizca LF iceren toplu is dosyalarinda
    - ozellikle if (...) else (...) bloklari ve etiketlerde - hatali davranir.
    """
    if p.lower().endswith(".bat"):
        s = s.replace("\r\n", "\n").replace("\n", "\r\n")
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def varsayilan_dizin():
    for d in (HERE, os.getcwd()):
        if os.path.exists(os.path.join(d, "rutin.py")):
            return d
    return HERE


def main():
    ap = argparse.ArgumentParser(description="BASLAT -> rapor zinciri")
    ap.add_argument("--dizin", default=varsayilan_dizin(),
                    help="_sistem klasoru (varsayilan: bu dosyanin ya da calisma klasorunuz)")
    ap.add_argument("--deneme", action="store_true", help="yalnizca ne yapilacagini yaz")
    ap.add_argument("--hepsi", action="store_true",
                    help="her iki baslaticiyi da yamala (varsayilan: yalnizca bu isletim sistemi)")
    a = ap.parse_args()

    d = a.dizin
    for gerek in ("rutin.py", "raporla.py", "rapor_gorevi.py"):
        if not os.path.exists(os.path.join(d, gerek)):
            print("!! %s bulunamadi: %s" % (gerek, os.path.join(d, gerek)))
            print("   Once o dosyayi _sistem klasorune koyun.")
            return 1

    win = os.name == "nt"
    yapilacak = []

    # 1) baslatici dosyalar
    for ad, govde, exe in (("RAPORLA.bat", BAT, False), ("RAPORLA_mac.command", SH, True)):
        if not a.hepsi and ((ad.endswith(".bat")) != win):
            continue
        p = os.path.join(d, ad)
        metin = govde.replace("{ISTEM}", ISTEM)
        bek = (metin.replace("\r\n", "\n").replace("\n", "\r\n")
               if ad.lower().endswith(".bat") else metin)
        if os.path.exists(p) and oku(p) == bek:
            print("  = zaten var: %s" % ad)
            continue
        yapilacak.append(("yaz", p, metin, exe))
        print("  + %s olusturulacak" % ad)

    # 2) BASLAT yamalari
    for ad, ankor, blok in YAMALAR:
        if not a.hepsi and ((ad == "BASLAT.bat") != win):
            continue
        p = os.path.join(d, ad)
        if not os.path.exists(p):
            print("  - %s yok, atlandi" % ad)
            continue
        s = oku(p)
        if KIMLIK in s:
            print("  = zaten bagli: %s" % ad)
            continue
        if s.count(ankor) != 1:
            print("!! %s: capa %d kez bulundu (beklenen 1). Bu dosya degistirilmeyecek."
                  % (ad, s.count(ankor)))
            continue
        yapilacak.append(("yamala", p, s.replace(ankor, blok + ankor, 1), False))
        print("  + %s icine 3/3 rapor adimi eklenecek" % ad)

    if not yapilacak:
        print("\nYapacak bir sey yok.")
        return 0
    if a.deneme:
        print("\n(--deneme) hicbir dosya yazilmadi.")
        return 0

    for is_tipi, p, metin, exe in yapilacak:
        if is_tipi == "yamala":
            shutil.copyfile(p, p + YEDEK_EKI)
        yaz(p, metin)
        if exe:
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print("\n%s %s" % (os.path.basename(p),
                           "guncellendi (eski hali: %s)" % (os.path.basename(p) + YEDEK_EKI)
                           if is_tipi == "yamala" else "olusturuldu"))

    print("\nTamam. BASLAT artik analizden sonra raporlari da yazar.")
    print("Claude Code kurulu degilse yorum adimi atlanir; bulut gorevi surucüleri")
    print("yazdiktan sonra RAPORLA dosyasina cift tiklamak yeterlidir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
