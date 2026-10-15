#!/bin/bash
# ILYOME WES / CES analiz rutini - Mac baslaticisi (Finder'da cift tiklayin).
# Yalniz Ilyome olgulari: Drive > Ilyome_Rutin_Raporlar/olgular.xlsx
# Genomize sistemi ile AYRI klasor, AYRI liste, AYRI kilit; birbirine karismaz.
# Ilyome parolasi gizli sorulur, HICBIR YERE KAYDEDILMEZ.

cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1

bitir() { echo; read -r -p "Kapatmak icin Enter'a basin... " _; exit "${1:-0}"; }

echo
echo "====================================================================="
echo "  ILYOME  WES / CES ANALIZ RUTINI  (Mac)"
echo "====================================================================="
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
if "$PY" -c "import alphagenome" >/dev/null 2>&1; then
  if [ -z "$ALPHAGENOME_API_KEY" ] && [ -f "$HOME/.alphagenome_api_key" ]; then
    ALPHAGENOME_API_KEY="$(tr -d '[:space:]' < "$HOME/.alphagenome_api_key")"
  fi
  if [ -z "$ALPHAGENOME_API_KEY" ]; then
    AG_SED='s/^[^=]*=[[:space:]]*//; s/[[:space:]]+#.*$//; s/;[[:space:]]*$//; s/[[:space:]]+$//; s/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/'
    for rc in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile"; do
      [ -f "$rc" ] || continue
      v="$(grep -E '^[[:space:]]*export[[:space:]]+ALPHAGENOME_API_KEY=' "$rc" | tail -1 | sed -E "$AG_SED")"
      if [ -n "$v" ]; then ALPHAGENOME_API_KEY="$v"; break; fi
    done
  fi
  if [ -n "$ALPHAGENOME_API_KEY" ]; then
    echo "  AlphaGenome: paket + API anahtari var"; export ALPHAGENOME_API_KEY
  else
    echo "  UYARI: ALPHAGENOME_API_KEY tanimli degil - AlphaGenome adimi atlanacak."
  fi
else
  echo "  UYARI: alphagenome paketi yok - AlphaGenome adimi atlanacak (pip install --user alphagenome)."
fi

# --- Veri klasoru (Drive > Ilyome_Rutin_Raporlar) ve ikinci kopya kontrolu
"$PY" -c "import sys, yollar as Y; sys.exit(Y.durum_yaz())" || bitir 1

# --- Ilyome kullanici adi (e-posta) hatirlanir; parola her seferinde gizli sorulur
KFILE="$HOME/.ilyome_rutin_kullanici"
if [ -z "$ILYOME_USER" ] && [ -f "$KFILE" ]; then
  ILYOME_USER="$(cat "$KFILE")"
fi
if [ -z "$ILYOME_USER" ]; then
  read -r -p "Ilyome e-posta: " ILYOME_USER
  [ -n "$ILYOME_USER" ] && printf '%s' "$ILYOME_USER" > "$KFILE"
fi
echo "  Ilyome kullanici: $ILYOME_USER"
export ILYOME_USER
read -r -s -p "Ilyome parolasi: " ILYOME_PASS; echo
if [ -z "$ILYOME_PASS" ]; then
  echo "Parola girilmedi. Iptal edildi."
  bitir 1
fi
export ILYOME_PASS

# --- Kilit: Ilyome rutini ayni anda iki bilgisayarda calismasin (Genomize kilidinden bagimsiz)
if ! "$PY" -c "import sys, yollar as Y; sys.exit(Y.kilit_al())"; then
  unset ILYOME_PASS; bitir 1
fi
temizle() { "$PY" -c "import yollar as Y; Y.kilit_birak()"; unset ILYOME_PASS; }
trap temizle EXIT

echo
echo "---------------------------------------------------------------------"
echo "  1/3  Kalite/kapsama verisi eksik olgular icin tamamlaniyor..."
echo "---------------------------------------------------------------------"
"$PY" rutin.py --qc-doldur || echo "UYARI: kalite verisi guncellenemedi."

echo
echo "---------------------------------------------------------------------"
echo "  2/3  Bekleyen Ilyome olgulari taraniyor..."
echo "---------------------------------------------------------------------"
"$PY" rutin.py "$@"
RC=$?
temizle; trap - EXIT

echo
echo "---------------------------------------------------------------------"
echo "  3/3  Raporlar (Claude Code)"
echo "---------------------------------------------------------------------"
if command -v claude >/dev/null 2>&1; then
  echo "  VERI_HAZIR olgular icin rapor surucusu yazdiriliyor (claude -p)..."
  claude -p "$("$PY" rapor_gorevi.py)" --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
    || echo "UYARI: Claude adimi hata verdi; raporlari Claude oturumundan isteyin."
  "$PY" raporla.py || echo "UYARI: raporla.py hata verdi (surucusu olmayan olgu VERI_HAZIR kaldi)."
else
  echo "  'claude' komutu yok. Raporlar icin Claude oturumunda sunu yazin:"
  echo "     \"Ilyome rutini calisti, raporlari yaz\""
  echo "  (Claude Code kurulumu: KURULUM_ILYOME.md)"
fi

if [ "$RC" != "0" ]; then
  echo "Rutin hata koduyla bitti: $RC  (_sistem/log klasorunu kontrol edin)"
fi
echo "Bu pencereyi kapatabilirsiniz."
bitir "$RC"
