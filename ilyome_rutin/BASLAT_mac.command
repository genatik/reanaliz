#!/bin/bash
# WES / CES analiz rutini - Mac baslaticisi (Finder'da cift tiklayin).
# Genomize VE Ilyome olgularini AYNI olgular.xlsx'ten isler ('Platform' sutunu).
# Parola yalniz gereken platform icin sorulur, gizli yazilir, HICBIR YERE KAYDEDILMEZ.

cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1

bitir() { echo; read -r -p "Kapatmak icin Enter'a basin... " _; exit "${1:-0}"; }

echo
echo "====================================================================="
echo "  WES / CES ANALIZ RUTINI  (Mac)  -  Genomize + Ilyome"
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

# --- Veri klasoru (Drive) ve ikinci kopya kontrolu
"$PY" -c "import sys, yollar as Y; sys.exit(Y.durum_yaz())" || bitir 1

# --- Hangi platformlarin parolasi gerekiyor? (BEKLIYOR olgulara gore)
PLATFORMLAR="$("$PY" rutin.py --platformlar 2>/dev/null | tail -1)"
[ -z "$PLATFORMLAR" ] && PLATFORMLAR="GENOMIZE"
echo "  Bekleyen olgularin platformlari: $PLATFORMLAR"

sor_kullanici() {   # $1 = etiket, $2 = dosya, $3 = degisken adi
  local kfile="$HOME/$2" deger=""
  [ -f "$kfile" ] && deger="$(cat "$kfile")"
  if [ -z "$deger" ]; then
    read -r -p "$1 kullanici adi / e-posta: " deger
    [ -n "$deger" ] && printf '%s' "$deger" > "$kfile"
  fi
  echo "  $1 kullanici: $deger"
  printf -v "$3" '%s' "$deger"; export "$3"
}

case " $PLATFORMLAR " in *" GENOMIZE "*)
  sor_kullanici "Genomize" ".wes_rutin_kullanici" GENOMIZE_USER
  read -r -s -p "Genomize parolasi: " GENOMIZE_PASS; echo
  [ -z "$GENOMIZE_PASS" ] && { echo "Parola girilmedi. Iptal."; bitir 1; }
  export GENOMIZE_PASS ;;
esac
case " $PLATFORMLAR " in *" ILYOME "*)
  sor_kullanici "Ilyome" ".wes_rutin_ilyome_kullanici" ILYOME_USER
  read -r -s -p "Ilyome parolasi: " ILYOME_PASS; echo
  [ -z "$ILYOME_PASS" ] && { echo "Parola girilmedi. Iptal."; bitir 1; }
  export ILYOME_PASS ;;
esac

# --- Kilit: rutin ayni anda iki bilgisayarda calismasin
if ! "$PY" -c "import sys, yollar as Y; sys.exit(Y.kilit_al())"; then
  unset GENOMIZE_PASS ILYOME_PASS; bitir 1
fi
temizle() { "$PY" -c "import yollar as Y; Y.kilit_birak()"; unset GENOMIZE_PASS ILYOME_PASS; }
trap temizle EXIT

echo
echo "---------------------------------------------------------------------"
echo "  1/3  Klinik bilgiler MiSeq run listesinden dolduruluyor..."
echo "---------------------------------------------------------------------"
"$PY" klinik_dizin.py --doldur || echo "UYARI: Klinik doldurma adimi hata verdi; devam ediliyor."

echo
echo "---------------------------------------------------------------------"
echo "  Kalite/kapsama verisi eksik olgular icin tamamlaniyor..."
echo "---------------------------------------------------------------------"
"$PY" rutin.py --qc-doldur || echo "UYARI: kalite verisi guncellenemedi."

echo
echo "---------------------------------------------------------------------"
echo "  2/3  Bekleyen olgular taraniyor..."
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
  echo "     \"WES rutini calisti, raporlari yaz\""
  echo "  (Claude Code kurulumu: KURULUM_ILYOME.md, Adim 2)"
fi

if [ "$RC" != "0" ]; then
  echo "Rutin hata koduyla bitti: $RC  (_sistem/log klasorunu kontrol edin)"
fi
echo "Bu pencereyi kapatabilirsiniz."
bitir "$RC"
