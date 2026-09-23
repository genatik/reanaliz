@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title WES / CES Analiz Rutini

echo.
echo ======================================================================
echo   WES / CES ANALIZ RUTINI
echo ======================================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo HATA: Python bulunamadi. Python kurulu ve PATH'te olmali.
  echo.
  pause
  exit /b 1
)

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONDONTWRITEBYTECODE=1

REM --- Veri klasoru: olgular.xlsx, MiSeq listesi ve olgu klasorleri Google
REM     Drive'dadir. Drive acik degilse parola sorulmadan durulur.
python -c "import sys, yollar as Y; sys.exit(Y.durum_yaz())"
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

REM --- AlphaGenome Atlas (istege bagli): paket/anahtar yoksa adim atlanir ---------
python -c "import alphagenome" >nul 2>nul
if errorlevel 1 (
  echo   UYARI: alphagenome paketi yok - AlphaGenome adimi atlanacak.
  echo          Kurmak icin: python -m pip install alphagenome
) else (
  if "%ALPHAGENOME_API_KEY%"=="" (
    for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command ^
      "[Environment]::GetEnvironmentVariable('ALPHAGENOME_API_KEY','User')"`) do set "ALPHAGENOME_API_KEY=%%K"
  )
  if "%ALPHAGENOME_API_KEY%"=="" (
    echo   UYARI: ALPHAGENOME_API_KEY tanimli degil - AlphaGenome adimi atlanacak.
    echo          setx ALPHAGENOME_API_KEY "anahtar"   ^(https://alphagenome.google/api^)
  ) else (
    echo   AlphaGenome: paket + API anahtari var
  )
)

REM --- Kullanici adi -------------------------------------------------------
if "%GENOMIZE_USER%"=="" (
  for /f "usebackq delims=" %%U in (`powershell -NoProfile -Command ^
    "[Environment]::GetEnvironmentVariable('GENOMIZE_USER','User')"`) do set "GENOMIZE_USER=%%U"
)
if "%GENOMIZE_USER%"=="" (
  set /p GENOMIZE_USER=Genomize kullanici adi:
)
echo   Kullanici : %GENOMIZE_USER%

REM --- Parola: gizli sorulur, HICBIR YERE KAYDEDILMEZ ----------------------
REM Yalnizca bu pencerenin omru boyunca bellekte tutulur.
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command ^
  "$s=Read-Host 'Genomize parolasi' -AsSecureString;" ^
  "$b=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);" ^
  "[Runtime.InteropServices.Marshal]::PtrToStringAuto($b)"`) do set "GENOMIZE_PASS=%%P"

if "%GENOMIZE_PASS%"=="" (
  echo.
  echo Parola girilmedi. Iptal edildi.
  echo.
  pause
  exit /b 1
)

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM --- Kilit: rutin ayni anda iki bilgisayarda (Windows / Mac) calismasin
python -c "import sys, yollar as Y; sys.exit(Y.kilit_al())"
if errorlevel 1 (
  set "GENOMIZE_PASS="
  echo.
  pause
  exit /b 1
)

echo.
echo ----------------------------------------------------------------------
echo   1/2  Klinik bilgiler MiSeq run listesinden dolduruluyor...
echo ----------------------------------------------------------------------
echo.
python klinik_dizin.py --doldur
if errorlevel 1 (
  echo.
  echo UYARI: Klinik doldurma adimi hata verdi. Analize yine de devam ediliyor;
  echo        klinik bilgisi bos kalan olgular hipotezsiz taranir.
  echo.
)

echo.
echo ----------------------------------------------------------------------
echo   Kalite/kapsama verisi (20x) eksik olgular icin tamamlaniyor...
echo ----------------------------------------------------------------------
python rutin.py --qc-doldur

echo.
echo ----------------------------------------------------------------------
echo   2/2  Bekleyen olgular taraniyor...
echo ----------------------------------------------------------------------
echo.
python rutin.py %*
set RC=%errorlevel%

python -c "import yollar as Y; Y.kilit_birak()"

REM --- parolayi bellekten sil ---------------------------------------------
set "GENOMIZE_PASS="

echo.
if not "%RC%"=="0" (
  echo Rutin hata koduyla bitti: %RC%
  echo log klasorunu kontrol edin.
)
echo Bu pencereyi kapatabilirsiniz.
pause
endlocal
