#!/bin/bash
# WES / CES analiz rutini - Mac baslaticisi (Finder'da cift tiklayin).
# Windows'taki BASLAT.bat ile ayni kodu, ayni Drive klasorunde calistirir.
# Genomize parolasi gizli sorulur, HICBIR YERE KAYDEDILMEZ.

cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1

bitir() { echo; read -r -p "Kapatmak icin Enter'a basin... " _; exit "${1:-0}"; }

echo
echo "======================================================================"
echo "  WES / CES ANALIZ RUTINI  (Mac)"
echo "======================================================================"
echo

PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "HATA: python3 bulunamadi. python.org'dan Python 3 kurun."
  bitir 1
fi
if ! "$PY" -c "import requests, openpyxl" >/dev/null 2>&1; then
  echo "HATA: eksik Python paketi. Terminal'de bir kez calistirin:"
  echo "   python3 -m pip install --user requests openpyxl"
  bitir 1
fi
# --- AlphaGenome Atlas (istege bagli): paket ve API anahtari yoksa adim atlanir.
#     Cift tiklanan .command ~/.zshrc'yi gormez; anahtar ~/.alphagenome_api_key
#     dosyasindan ya da ~/.zprofile / ~/.zshrc icindeki export satirindan okunur.
if "$PY" -c "import alphagenome" >/dev/null 2>&1; then
  if [ -z "$ALPHAGENOME_API_KEY" ] && [ -f "$HOME/.alphagenome_api_key" ]; then
    ALPHAGENOME_API_KEY="$(tr -d '[:space:]' < "$HOME/.alphagenome_api_key")"
  fi
  if [ -z "$ALPHAGENOME_API_KEY" ]; then
    for rc in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile"; do
      [ -f "$rc" ] || continue
      v="$(grep -E '^[[:space:]]*export[[:space:]]+ALPHAGENOME_API_KEY=' "$rc" | tail -1 \
           | sed -E 's/^[^=]*=//; s/^["'"'"']//; s/["'"'"'][[:space:]]*$//')"
      if [ -n "$v" ]; then ALPHAGENOME_API_KEY="$v"; break; fi
    done
  fi
  if [ -n "$ALPHAGENOME_API_KEY" ]; then
    echo "  AlphaGenome: paket + API anahtari var"
    export ALPHAGENOME_API_KEY
  else
    echo "  UYARI: ALPHAGENOME_API_KEY tanimli degil - AlphaGenome adimi atlanacak."
    echo "         Anahtari ~/.alphagenome_api_key dosyasina yazin (https://alphagenome.google/api)"
  fi
else
  echo "  UYARI: alphagenome paketi yok - AlphaGenome adimi atlanacak."
  echo "         Kurmak icin: python3 -m pip install --user alphagenome"
fi

# --- Veri klasoru (Drive) ve ikinci kopya kontrolu
"$PY" -c "import sys, yollar as Y; sys.exit(Y.durum_yaz())" || bitir 1

# --- Kullanici adi (parola degil) ev klasorunde hatirlanir
KFILE="$HOME/.wes_rutin_kullanici"
if [ -z "$GENOMIZE_USER" ] && [ -f "$KFILE" ]; then
  GENOMIZE_USER="$(cat "$KFILE")"
fi
if [ -z "$GENOMIZE_USER" ]; then
  read -r -p "Genomize kullanici adi: " GENOMIZE_USER
  [ -n "$GENOMIZE_USER" ] && printf '%s' "$GENOMIZE_USER" > "$KFILE"
fi
echo "  Kullanici : $GENOMIZE_USER"
export GENOMIZE_USER

# --- Parola: gizli sorulur, yalniz bu pencerenin omru boyunca bellekte
read -r -s -p "Genomize parolasi: " GENOMIZE_PASS
echo
if [ -z "$GENOMIZE_PASS" ]; then
  echo "Parola girilmedi. Iptal edildi."
  bitir 1
fi
export GENOMIZE_PASS

# --- Kilit: rutin ayni anda iki bilgisayarda calismasin
if ! "$PY" -c "import sys, yollar as Y; sys.exit(Y.kilit_al())"; then
  unset GENOMIZE_PASS
  bitir 1
fi
temizle() { "$PY" -c "import yollar as Y; Y.kilit_birak()"; unset GENOMIZE_PASS; }
trap temizle EXIT

echo
echo "----------------------------------------------------------------------"
echo "  1/2  Klinik bilgiler MiSeq run listesinden dolduruluyor..."
echo "----------------------------------------------------------------------"
"$PY" klinik_dizin.py --doldur || {
  echo
  echo "UYARI: Klinik doldurma adimi hata verdi. Analize yine de devam ediliyor."
}

echo
echo "----------------------------------------------------------------------"
echo "  Kalite/kapsama verisi (20x) eksik olgular icin tamamlaniyor..."
echo "----------------------------------------------------------------------"
"$PY" rutin.py --qc-doldur || echo "UYARI: kalite verisi guncellenemedi."

echo
echo "----------------------------------------------------------------------"
echo "  2/2  Bekleyen olgular taraniyor..."
echo "----------------------------------------------------------------------"
"$PY" rutin.py "$@"
RC=$?
temizle; trap - EXIT          # kilit rutin biter bitmez birakilir (pencere acik kalsa da)
if [ "$RC" != "0" ]; then
  echo "Rutin hata koduyla bitti: $RC  (_sistem/log klasorunu kontrol edin)"
fi
echo "Bu pencereyi kapatabilirsiniz."
bitir "$RC"
