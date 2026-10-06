# -*- coding: utf-8 -*-
r"""hpo_otomatik.py - Klinik Bilgi metninden HPO terimlerini kendisi uretir.

NEDEN: HPO el sikismasi (HPO_BEKLIYOR) acik bir Claude oturumu gerektiriyordu.
Oturum yoksa rutin 15 dk bekleyip "HPO'suz devam edilsin mi?" diye soruyor,
fenotip ekseni calismiyordu. Oysa klinik metinlerin buyuk bolumu tekrar eden
kaliplardir ("Koagulopati?", "isitme kaybi", "NMGG, epilepsi"...).

NASIL: Asagidaki SOZLUK, olgular.xlsx'in KENDI gecmisinden cikarilmistir -
her HP kimligi daha once bu sayfada kullanilmis ve hpo_yaz.py tarafindan
ontology.jax.org'da dogrulanmistir. Eslesme deterministiktir: ayni metin her
zaman ayni terimleri verir, tahmin yurutmez.

SINIR: Eslesmeyen metin icin BOS liste doner. O olgu eskisi gibi el sikismaya
girer ve size sorulur. Betik "bir sey bulamadim" demeyi, yanlis terim
uydurmaya tercih eder.

    python hpo_otomatik.py                 # bekleyen olgulari tara, YAZMA
    python hpo_otomatik.py --yaz           # dogrula ve yaz
    python hpo_otomatik.py --metin "..."   # tek bir metni dene

rutin.py icinden:  from hpo_otomatik import terimler
"""
from __future__ import print_function
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

BASLIK = 3

# Turkce buyuk/kucuk harf duzeltmesi (I/i ve İ/i ayrimi Python'un varsayilani
# ile dogru calismaz).
_BUYUK = "İIŞĞÜÖÇ"
_KUCUK = "iişğüöç"
_CEVIR = dict(zip(_BUYUK, _KUCUK))

# Aksanlar ASCII'ye indirilir: sozluk ASCII yazilir, metin "YÜKSEKLİĞİ" de olsa
# "yukseklıgı" -> "yuksekligi" olur ve eslesir. (Ilk surumde eksikti: metindeki
# Turkce karakterler yuzunden olgularin yarisi eslesmiyordu.)
_ASCII = {"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o",
          "ç": "c", "â": "a", "î": "i", "û": "u", "ä": "a",
          "é": "e", "ô": "o"}


def normalize(s):
    """Kucuk harfe cevir, aksanlari ASCII'ye indir, noktalamayi sadelestir."""
    s = "".join(_CEVIR.get(ch, ch) for ch in (s or ""))
    s = s.lower()
    s = "".join(_ASCII.get(ch, ch) for ch in s)
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


# (anahtar kaliplar, [HP kimlikleri], terim adi)
# Kaliplar normalize edilmis metinde ARANIR; biri yeterlidir.
# Sira onemlidir: ozel olanlar once, genel olanlar sonra gelir.
SOZLUK = [
    # --- hematoloji / koagulasyon
    (["herediter sferositoz", "herediter sferostoz", "sferositoz", "sferostoz"],
     ["HP:0004444", "HP:0001878", "HP:0001744", "HP:0000952"], "Herediter sferositoz"),
    (["kalitsal hemolitik anemi", "hemolitik anemi"],
     ["HP:0001878", "HP:0001903"], "Hemolitik anemi"),
    (["koagulopati", "pihtilasma bozuklugu"],
     ["HP:0001892", "HP:0003125"], "Koagulopati"),
    (["vwf eksikligi", "von willebrand"],
     ["HP:0001892", "HP:0012146"], "VWF eksikligi"),
    (["hemofili"], ["HP:0003125"], "Hemofili"),
    (["bisitopeni", "pansitopeni"], ["HP:0001903", "HP:0001873"], "Sitopeni"),
    (["trombositopeni"], ["HP:0001873"], "Trombositopeni"),
    (["hiperferritinemi"], ["HP:0003281"], "Hiperferritinemi"),
    (["lenfoma"], ["HP:0002665"], "Lenfoma"),

    # --- immunoloji
    (["hipogamaglobulinemi", "hipogamagobulinemi"], ["HP:0004313"], "Hipogamaglobulinemi"),
    (["immun yetmezlik", "immun yetersizlik", "cvid"], ["HP:0002721"], "Immun yetmezlik"),
    (["sik enfeksiyon", "tekrarlayan enfeksiyon"], ["HP:0002719"], "Tekrarlayan enfeksiyon"),
    (["tekrarlayan akciger enfeksiyonu", "sik akciger enfeksiyonu"],
     ["HP:0002783"], "Tekrarlayan pnomoni"),
    (["sik otit", "tekrarlayan otit"], ["HP:0000403"], "Tekrarlayan otit"),
    (["bronsektazi", "bronsiektazi"], ["HP:0002110"], "Bronsektazi"),
    (["eozinofili"], ["HP:0001880"], "Eozinofili"),
    (["ig e yuksekligi", "ige yuksekligi"], ["HP:0003212"], "IgE yuksekligi"),
    (["otoimmun hepatit"], ["HP:0002960"], "Otoimmun hepatit"),

    # --- noroloji / gelisim
    (["nmgg", "noromotor gelisme geriligi", "noromotor gelisim geriligi"],
     ["HP:0012758"], "Noromotor gelisme geriligi"),
    (["motor gelisim geriligi", "motor gelisme geriligi"], ["HP:0001270"], "Motor gelisim geriligi"),
    (["gelisim geriligi", "gelisme geriligi", "global gelisme geriligi"],
     ["HP:0001263"], "Gelisimsel gerilik"),
    (["zihinsel yetersizlik", "zih yet", "entelektuel yetersizlik", "entellektuel yetersizlik"],
     ["HP:0001249"], "Zihinsel yetersizlik"),
    (["konusma gecikmesi", "konusma ve dil gelisiminde gecikme"],
     ["HP:0000750"], "Konusma gecikmesi"),
    (["iess", "infantil spazm"], ["HP:0012469"], "Infantil spazm"),
    (["dalma seklinde nobet", "absans"], ["HP:0002121"], "Absans"),
    (["epilepsi", "nobet", "konvulziyon"], ["HP:0001250"], "Nobet"),
    (["mikrosefali"], ["HP:0000252"], "Mikrosefali"),
    (["ince korpus kallozum", "ince kk"], ["HP:0033725"], "Ince korpus kallozum"),
    (["serebral atrofi"], ["HP:0002059"], "Serebral atrofi"),
    (["pvl", "periventrikuler lokomalazi"], ["HP:0006970"], "Periventrikuler lokomalazi"),
    (["spastik diparezi"], ["HP:0001264"], "Spastik diparezi"),
    (["paraparezi"], ["HP:0002385"], "Paraparezi"),
    (["otizm", "otistik"], ["HP:0000717", "HP:0000729"], "Otizm"),
    (["hiperaktivite"], ["HP:0000752"], "Hiperaktivite"),
    (["durtusellik"], ["HP:0100710"], "Durtusellik"),
    (["dehb", "dikkat eksikligi"], ["HP:0007018"], "DEHB"),
    (["tethered cord", "tathered cord"], ["HP:0002144"], "Tethered cord"),

    # --- goz / kulak
    (["isitme kaybi", "isitme esigi", "sagirlik"], ["HP:0000365"], "Isitme kaybi"),
    (["ic kulak anomalisi"], ["HP:0011390"], "Ic kulak anomalisi"),
    (["mikrotia", "microtia"], ["HP:0008551"], "Mikrotia"),
    (["strabismus", "sasilik"], ["HP:0000486"], "Strabismus"),
    (["ileri miyopi", "miyopi"], ["HP:0011003"], "Yuksek miyopi"),
    (["pitozis"], ["HP:0000508"], "Pitozis"),
    (["blefarofimozis", "bleferofimozis"], ["HP:0000581"], "Blefarofimozis"),

    # --- kalp / damar
    (["fallot"], ["HP:0001636"], "Fallot tetralojisi"),
    (["asd", "atriyal septal defekt"], ["HP:0001631"], "Atriyal septal defekt"),
    (["vsd", "ventrikuler septal defekt"], ["HP:0001629"], "Ventrikuler septal defekt"),
    (["mvp", "mitral valv prolapsus"], ["HP:0001634"], "Mitral valv prolapsusu"),
    (["kardiyomiyopati", "kmp"], ["HP:0001637"], "Kardiyomiyopati"),
    (["myokardit", "miyokardit"], ["HP:0012819"], "Miyokardit"),
    (["kor triatrum", "kor triatriatum"], ["HP:0031134"], "Kor triatriatum"),

    # --- bobrek / urogenital
    (["at nali bobrek", "at nali bb"], ["HP:0000085"], "At nali bobrek"),
    (["multikistik displastik bobrek", "mkdb"], ["HP:0000003"], "Multikistik displastik bobrek"),
    (["renal agenezi"], ["HP:0000104"], "Renal agenezi"),
    (["hipospadias"], ["HP:0000047"], "Hipospadias"),
    (["inmemis testis"], ["HP:0000028"], "Inmemis testis"),

    # --- gastrointestinal / karaciger
    (["anal atrezi"], ["HP:0002023"], "Anal atrezi"),
    (["kolestaz"], ["HP:0001396"], "Kolestaz"),
    (["ast yuksekligi"], ["HP:0031956"], "AST yuksekligi"),
    (["transaminaz yuksekligi", "alt yuksekligi"],
     ["HP:0002910"], "Transaminaz yuksekligi"),
    (["hepatomegali"], ["HP:0002240"], "Hepatomegali"),
    (["hsm", "hepatosplenomegali"], ["HP:0001433"], "Hepatosplenomegali"),
    (["ibh", "inflamatuar barsak"], ["HP:0002583"], "Inflamatuar barsak hastaligi"),

    # --- iskelet / baglayici doku
    (["boy kisaligi"], ["HP:0004322"], "Boy kisaligi"),
    (["uzun boy"], ["HP:0000098"], "Uzun boy"),
    (["skolyoz"], ["HP:0002650"], "Skolyoz"),
    (["pektus ekskavatum", "pectus excavatum"], ["HP:0000767"], "Pektus ekskavatum"),
    (["pektus karinatum", "pectus carinatum"], ["HP:0000768"], "Pektus karinatum"),
    (["eklem laksitesi", "eklem gevsekligi"], ["HP:0001382"], "Eklem laksitesi"),
    (["cilt laksitesi"], ["HP:0000974"], "Cilt laksitesi"),
    (["bifid uvula"], ["HP:0000193"], "Bifid uvula"),
    (["oligosindaktili"], ["HP:0012165", "HP:0001159"], "Oligosindaktili"),
    (["sindaktili"], ["HP:0001159"], "Sindaktili"),
    (["kontraktur"], ["HP:0034391"], "Kontraktur"),

    # --- cilt
    (["cafe au lait", "cafeaulait", "cafe aulait"], ["HP:0000957"], "Cafe-au-lait lekesi"),
    (["genodermatoz"], ["HP:0000951"], "Deri anomalisi"),
    (["fotosensivite", "fotosensitivite"], ["HP:0000992"], "Fotosensitivite"),
    (["hipohidrozis", "hipohidroz"], ["HP:0000966"], "Hipohidroz"),
    (["sac seyrekligi"], ["HP:0008070"], "Sac seyrekligi"),
    (["dis eksikligi"], ["HP:0000668"], "Dis eksikligi"),

    # --- metabolik / endokrin
    (["hipoketotik hipoglisemi"], ["HP:0001985"], "Hipoketotik hipoglisemi"),
    (["fku", "fenilketonuri"], ["HP:0004923"], "Hiperfenilalaninemi"),
    (["obezite"], ["HP:0001513"], "Obezite"),
    (["ck yuksekligi", "ck yukseklik"], ["HP:0003236"], "CK yuksekligi"),

    # --- diger
    (["yarik damak dudak"], ["HP:0000175", "HP:0000202"], "Yarik damak-dudak"),
    (["yarik damak"], ["HP:0000175"], "Yarik damak"),
    (["yarik dudak"], ["HP:0000202"], "Yarik dudak"),
    (["koanal darlik", "koanal atrezi"], ["HP:0000452"], "Koanal atrezi"),
    (["laringomalazi"], ["HP:0001601"], "Laringomalazi"),
    (["situs inersus", "situs inversus"], ["HP:0001696"], "Situs inversus"),
    (["pcd", "siliyer diskinezi"], ["HP:0012262"], "Siliyer diskinezi"),
    (["inguinal herni"], ["HP:0000023"], "Inguinal herni"),
    (["heterotaksi"], ["HP:0030853"], "Heterotaksi"),
    (["reaktif hava yolu", "astim"], ["HP:0002099"], "Astim"),
    (["preterm dogum", "prematurite"], ["HP:0001622"], "Preterm dogum"),
    (["buyume geriligi"], ["HP:0001510"], "Buyume geriligi"),
    (["dismorfik yuz", "dismorfik bulgu", "dismorfik"], ["HP:0001999"], "Dismorfik yuz"),
    (["glial kitle", "glioma", "gliom"], ["HP:0009733"], "Gliom"),
    (["hepatoblastom"], ["HP:0002884"], "Hepatoblastom"),
]


def _desen(kalip):
    """Kalibi duzenli ifadeye cevirir.

    Turkce sondan eklemelidir: "nobet" kalibi "nobetleri" icinde de bulunmali.
    Bu yuzden kelime siniri YALNIZCA bastadir, son serbesttir. Kisa
    kisaltmalar (asd, pcd, ey, kmp) kelime ICINDE yanlis eslesmesin diye
    her iki ucta da sinir aranir.
    """
    k = normalize(kalip)
    parca = [re.escape(x) for x in k.split()]
    govde = r"\s+".join(parca)
    return re.compile(r"\b" + govde + (r"\b" if len(k) <= 4 else ""))


_DERLI = None


def _derle():
    global _DERLI
    if _DERLI is None:
        _DERLI = [([(_desen(k), k) for k in kaliplar], hpo, ad)
                  for kaliplar, hpo, ad in SOZLUK]
    return _DERLI


def terimler(klinik, ayrinti=False):
    """Klinik metinden HP kimliklerini dondurur (eslesme yoksa bos liste).

    ayrinti=True ise [(HP, terim_adi, eslesen_kalip), ...] dondurur.
    """
    m = normalize(klinik)
    if not m:
        return [] if not ayrinti else []
    bulunan, gorulen = [], set()
    for desenler, hpo, ad in _derle():
        for rx, k in desenler:
            if rx.search(m):
                for h in hpo:
                    if h not in gorulen:
                        gorulen.add(h)
                        bulunan.append((h, ad, k))
                break
    return bulunan if ayrinti else [h for h, _, _ in bulunan]


# --------------------------------------------------------------------------
def _satirlar(ws, H):
    """HPO'su bos ve islenmeyi bekleyen satirlar."""
    out = []
    for r in range(BASLIK + 1, ws.max_row + 1):
        kod = str(ws.cell(r, H["Olgu Kodu"]).value or "").strip()
        if not kod:
            continue
        durum = str(ws.cell(r, H["Durum"]).value or "").strip().upper()
        hpo = str(ws.cell(r, H["HPO (istege bagli)"]).value or "").strip()
        if durum in ("HPO_BEKLIYOR", "BEKLIYOR") and not re.search(r"HP:\d{7}", hpo):
            out.append((r, kod, str(ws.cell(r, H["Klinik Bilgi"]).value or "").strip()))
    return out


def main():
    ap = argparse.ArgumentParser(description="Klinik bilgiden otomatik HPO")
    ap.add_argument("--yaz", action="store_true", help="dogrula ve olgular.xlsx'e yaz")
    ap.add_argument("--metin", help="tek bir klinik metni dene (dosyaya dokunmaz)")
    a = ap.parse_args()

    if a.metin:
        d = terimler(a.metin, ayrinti=True)
        if not d:
            print("eslesme yok.")
            return 1
        for h, ad, k in d:
            print("  %s  %-28s (kalip: %s)" % (h, ad, k))
        return 0

    from openpyxl import load_workbook
    import yollar as Y

    p = Y.olgular_xlsx()
    kilit = os.path.join(os.path.dirname(p), "~$" + os.path.basename(p))
    if os.path.exists(kilit):
        print("!! olgular.xlsx Excel'de ACIK. Kapatip tekrar calistirin.")
        return 1

    wb = load_workbook(p)
    ws = wb["OLGULAR"]
    H = {str(ws.cell(BASLIK, c).value).strip(): c
         for c in range(1, ws.max_column + 1) if ws.cell(BASLIK, c).value}

    eslesen, eslesmeyen = [], []
    for r, kod, klinik in _satirlar(ws, H):
        d = terimler(klinik, ayrinti=True)
        (eslesen if d else eslesmeyen).append((r, kod, klinik, d))

    for r, kod, klinik, d in eslesen:
        print("  %-22s %s" % (kod, klinik[:60]))
        for h, ad, _ in d:
            print("      %s  %s" % (h, ad))
    if eslesmeyen:
        print("\n  -- eslesme yok (size sorulacak):")
        for r, kod, klinik, _ in eslesmeyen:
            print("     %-22s %s" % (kod, klinik[:60] or "(klinik bilgi bos)"))

    if not a.yaz:
        print("\n(deneme) %d olgu eslesti, %d olgu elle bakilacak. Yazmak icin --yaz."
              % (len(eslesen), len(eslesmeyen)))
        return 0
    if not eslesen:
        print("\nYazilacak olgu yok.")
        return 1

    from hpo_yaz import dogrula
    bellek, yazilacak, hatali = {}, [], []
    for r, kod, _, d in eslesen:
        kotu = []
        for h, _, _ in d:
            if h not in bellek:
                bellek[h] = dogrula([h])[0]
            _, ad, eski = bellek[h]
            if not ad or eski or ad.startswith("?"):
                kotu.append((h, ad))
        if kotu:
            hatali.append((kod, kotu))
        else:
            yazilacak.append((r, kod, [h for h, _, _ in d]))

    if hatali:
        print("\n  !! Ontolojide dogrulanamayan terim (o olgu yazilmadi):")
        for kod, kotu in hatali:
            for h, ad in kotu:
                print("     %-22s %s  %s" % (kod, h, ad or "BULUNAMADI"))
    if not yazilacak:
        print("\nHicbir olgu yazilmadi.")
        return 1

    for r, kod, hpo in yazilacak:
        ws.cell(r, H["HPO (istege bagli)"]).value = ", ".join(hpo)
        if str(ws.cell(r, H["Durum"]).value or "").strip().upper() == "HPO_BEKLIYOR":
            ws.cell(r, H["Durum"]).value = "BEKLIYOR"
    wb.save(p)
    print("\n%d olguya HPO yazildi." % len(yazilacak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
