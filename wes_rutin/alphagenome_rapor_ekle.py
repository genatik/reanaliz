#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alphagenome_rapor_ekle.py - var olan WES raporlarina AlphaGenome bolumunu ekler.

Onceden yazilmis .docx raporlari (kapsamli analiz / sonuc / resmi) bozmadan acar,
kanit/alphagenome.csv + alphagenome_ozet.json icerigine dayanan
"AlphaGenome Atlas degerlendirmesi" bolumunu ekler ve bugunun tarihiyle yeni bir
dosya olarak kaydeder. Eski dosyalar silinmez.

Kullanim (_sistem klasorunden):
    python alphagenome_rapor_ekle.py TUMU              # kanit + rapor olan tum olgular
    python alphagenome_rapor_ekle.py 218875-ECR-OZE    # tek olgu (birden fazla yazilabilir)
    python alphagenome_rapor_ekle.py TUMU --listele    # hicbir sey yazma, ne yapilacagini goster
    python alphagenome_rapor_ekle.py TUMU --uzerine    # raporda AlphaGenome varsa da yeniden yaz
    python alphagenome_rapor_ekle.py TUMU --kok "K:\\My Drive\\WES_CES_Rutin_Raporlar"

Sirasi:
    1) python rutin.py --alphagenome TUMU     (skorlari uretir; API anahtari gerekir)
    2) python alphagenome_rapor_ekle.py TUMU  (raporlara isler; internet gerekmez)

Notlar:
  * Raporda zaten "AlphaGenome" geciyorsa o olgu atlanir (--uzerine ile zorlanir).
  * Kapsamli rapora tablo + yorum, sonuc ve resmi rapora tek cumle eklenir.
  * Skorlar arastirma amaclidir; metinler bunu her raporda acikca yazar.
"""
from __future__ import print_function

import argparse
import csv
import datetime
import glob
import io
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SURUM = "1.0"


def log(m):
    sys.stdout.write("%s\n" % m)
    sys.stdout.flush()


def _sayi(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def vir(v, n=2):
    """Sayiyi Turkce ondalikla; bos ise tire."""
    f = _sayi(v)
    if f is None:
        return u"\u2013"
    return (u"%%.%df" % n % f).replace(u".", u",")


def kok():
    """WES_CES_Rutin_Raporlar klasoru: yollar.py varsa ondan, yoksa bir ust klasor."""
    try:
        import yollar
        k = yollar.veri_koku()
        if k:
            return k
    except Exception:
        pass
    burasi = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(burasi) if os.path.basename(burasi) == "_sistem" else burasi


# ---------------------------------------------------------------- XML kurma

def esc(t):
    return t.replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;")


def _rpr(bold, ital, sz, arial=True):
    f = u'<w:rFonts w:ascii="Arial" w:hAnsi="Arial"/>' if arial else u''
    return (u'<w:rPr>%s<w:b w:val="%s"/><w:i w:val="%s"/><w:sz w:val="%d"/>'
            u'<w:szCs w:val="%d"/></w:rPr>'
            % (f, u"1" if bold else u"0", u"1" if ital else u"0", sz, sz))


GEN_RE = re.compile(r"\*([A-Za-z0-9\-]+)\*")          # *GEN* -> italik


def runs(t, sz=20, bold=False, arial=True):
    out, son = [], 0
    for m in GEN_RE.finditer(t):
        if m.start() > son:
            out.append(u'<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>'
                       % (_rpr(bold, False, sz, arial), esc(t[son:m.start()])))
        out.append(u'<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>'
                   % (_rpr(bold, True, sz, arial), esc(m.group(1))))
        son = m.end()
    if son < len(t) or not out:
        out.append(u'<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>'
                   % (_rpr(bold, False, sz, arial), esc(t[son:])))
    return u"".join(out)


def baslik(t, renk="1F4E79", cizgi="2E8B8B", sz=24):
    # pPr icinde siralama sema geregi: pBdr, sonra spacing
    return (u'<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="%s"/>'
            u'</w:pBdr><w:spacing w:before="160" w:after="80"/></w:pPr><w:r><w:rPr>'
            u'<w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:b/><w:i w:val="0"/><w:color w:val="%s"/>'
            u'<w:sz w:val="%d"/><w:szCs w:val="%d"/></w:rPr>'
            u'<w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (cizgi, renk, sz, sz, esc(t)))


def altbaslik(t, renk="1F4E79"):
    return (u'<w:p><w:pPr><w:spacing w:before="80" w:after="40"/></w:pPr><w:r><w:rPr>'
            u'<w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:b/><w:i w:val="0"/><w:color w:val="%s"/>'
            u'<w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
            u'<w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (renk, esc(t)))


def para(t, sz=18, after=100, ind=0, arial=True, jc=None):
    p = u'<w:p><w:pPr><w:spacing w:after="%d"/>' % after
    if ind:
        p += u'<w:ind w:left="%d"/>' % ind
    if jc:
        p += u'<w:jc w:val="%s"/>' % jc
    return p + u'</w:pPr>' + runs(t, sz, arial=arial) + u'</w:p>'


def _hucre(t, w, sz, head, dolgu):
    if head:
        ic = (u'<w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:b/><w:i w:val="0"/>'
              u'<w:color w:val="FFFFFF"/><w:sz w:val="%d"/><w:szCs w:val="%d"/></w:rPr>'
              u'<w:t xml:space="preserve">%s</w:t></w:r>' % (sz, sz, esc(t)))
        shd = u'<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % dolgu
    else:
        ic, shd = runs(t, sz), u''
    return (u'<w:tc><w:tcPr><w:tcW w:type="dxa" w:w="%d"/>%s</w:tcPr>'
            u'<w:p><w:pPr><w:spacing w:after="20"/></w:pPr>%s</w:p></w:tc>' % (w, shd, ic))


def tablo(basliklar, satirlar, genisler, sz=15, dolgu="2E8B8B"):
    x = [u'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:type="dxa" w:w="%d"/>'
         u'<w:jc w:val="center"/><w:tblBorders>' % sum(genisler)]
    for k in ("top", "left", "bottom", "right", "insideH", "insideV"):
        x.append(u'<w:%s w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>' % k)
    x.append(u'</w:tblBorders><w:tblLook w:firstColumn="1" w:firstRow="1" w:lastColumn="0" '
             u'w:lastRow="0" w:noHBand="0" w:noVBand="1" w:val="04A0"/></w:tblPr><w:tblGrid>')
    x.append(u"".join(u'<w:gridCol w:w="%d"/>' % g for g in genisler))
    x.append(u'</w:tblGrid><w:tr><w:trPr><w:tblHeader/></w:trPr>')
    x.append(u"".join(_hucre(b, g, sz, True, dolgu) for b, g in zip(basliklar, genisler)))
    x.append(u'</w:tr>')
    for s in satirlar:
        x.append(u'<w:tr>' + u"".join(_hucre(c, g, sz, False, dolgu)
                                      for c, g in zip(s, genisler)) + u'</w:tr>')
    x.append(u'</w:tbl>')
    return u"".join(x)


# ---------------------------------------------------------------- docx okuma/yazma

def _ns_kaydet(ham):
    for pre, uri in re.findall(r'xmlns:([A-Za-z0-9_]+)="([^"]+)"', ham[:4000]):
        try:
            ET.register_namespace(pre, uri)
        except Exception:
            pass


def docx_metin(yol):
    """Belgedeki tum metin (arama icin)."""
    try:
        ham = zipfile.ZipFile(yol).read("word/document.xml").decode("utf-8")
    except Exception:
        return u""
    return u" ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", ham))


def _p_metin(el):
    return u"".join(t.text or u"" for t in el.iter(W + "t"))


def _yer_bul(cocuk, ankorlar):
    """Ilk eslesen ankor paragrafinin indeksi; yoksa sectPr'dan once."""
    for kalip in ankorlar:
        rx = re.compile(kalip, re.I)
        for i, el in enumerate(cocuk):
            if el.tag == W + "p" and rx.search(_p_metin(el).strip()):
                return i
    for i, el in enumerate(cocuk):
        if el.tag == W + "sectPr":
            return i
    return len(cocuk)


def docx_bolum_ekle(kaynak, hedef, eklemeler, tarihler=None):
    """eklemeler: [(bolum_xml, ankorlar), ...]; her biri kendi ankorundan once eklenir.

    tarihler: (eski, yeni) YYYY-MM-DD verilirse metindeki gg.aa.yyyy ve yyyy-aa-gg
    tarih yazimlari guncellenir."""
    z = zipfile.ZipFile(kaynak)
    ham = z.read("word/document.xml").decode("utf-8")
    _ns_kaydet(ham)
    kok_el = ET.fromstring(ham.encode("utf-8"))
    govde = kok_el.find(W + "body")
    cocuk = list(govde)

    isler = [(_yer_bul(cocuk, ank), xml) for xml, ank in eklemeler]
    for yer, bolum_xml in sorted(isler, key=lambda t: -t[0]):    # sondan basa: indeks kaymasin
        yeni = ET.fromstring((u'<w:root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
                              u'2006/main">' + bolum_xml + u'</w:root>').encode("utf-8"))
        for k, el in enumerate(list(yeni)):
            govde.insert(yer + k, el)

    cikti = ET.tostring(kok_el, encoding="utf-8").decode("utf-8")
    # ET yalniz kullandigi ad alanlarini yazar; mc:Ignorable'daki bildirimler kaybolmasin diye
    # ozgun <w:document ...> acilis etiketini geri koy.
    m_yeni = re.match(r"<[A-Za-z0-9_]+:document\b[^>]*>", cikti)
    m_eski = re.search(r"<[A-Za-z0-9_]+:document\b[^>]*>", ham)
    if m_yeni and m_eski:
        cikti = m_eski.group(0) + cikti[m_yeni.end():]
    if not cikti.startswith("<?xml"):
        cikti = u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + cikti
    if tarihler:
        try:
            ey, ea, eg = tarihler[0].split("-")
            yy, ya, yg = tarihler[1].split("-")
            cikti = cikti.replace(u"%s.%s.%s" % (eg, ea, ey), u"%s.%s.%s" % (yg, ya, yy))
            cikti = cikti.replace(tarihler[0], tarihler[1])
        except (ValueError, AttributeError):
            pass

    gecici = hedef + ".yeni"
    zo = zipfile.ZipFile(gecici, "w", zipfile.ZIP_DEFLATED)
    for it in z.infolist():
        veri = cikti.encode("utf-8") if it.filename == "word/document.xml" else z.read(it.filename)
        zo.writestr(it, veri)
    zo.close()
    z.close()
    if os.path.exists(hedef):
        os.remove(hedef)
    os.rename(gecici, hedef)
    return hedef


# ---------------------------------------------------------------- icerik

KAYNAKLAR = [
    u"Avsec Ž, Latysheva N, Cheng J, ve ark. Advancing regulatory variant effect prediction with "
    u"AlphaGenome. Nature. 2026;649(8099):1206-1218. doi:10.1038/s41586-025-10014-0",
    u"Cheng J, Taylor KR, Nicolaisen L, ve ark. AlphaGenome Atlas: in silico mutagenesis of the entire "
    u"human genome improves prioritization and interpretation of non-coding variants. 2026 "
    u"(ön baskı; https://alphagenome.google/atlas)",
]

SINIR = (u"Kısıtlılıklar ve kullanım koşulu: AlphaGenome skorları "
         u"araştırma amaçlı hesaplamalı öngörülerdir; ACMG/AMP "
         u"çerçevesinde PP3/BP4 kanıtı yerine geçmez, kalibre edilmiş "
         u"araçlarla (REVEL, SpliceAI, AlphaMissense) birlikte ve ikincil olarak "
         u"değerlendirilir. Düşük skor bir varyantı dışlamaz, "
         u"Atlas'ta kayıt bulunmaması kanıt değildir ve Atlas çıktıları "
         u"ticari olmayan araştırma kullanımıyla sınırlıdır; tek "
         u"başına klinik karar için kullanılamaz.")

DOSYA_NOT = (u"Ayrıntılı tablolar: kanıt klasöründe alphagenome.csv (varyant "
             u"başına tüm sütunlar), alphagenome_detay.csv (doku/gen bazlı en "
             u"yüksek skorlar) ve alphagenome_rapor.txt.")

YONTEM_CUMLE = (u"Aday varyantların düzenleyici ve splicing etkileri ayrıca Google DeepMind "
                u"AlphaGenome Atlas (AVI skoru, birleşik splicing skoru ve aktif dokularda modalite "
                u"bazlı kalibre kantil skorları; Avsec ve ark. 2026, Cheng ve ark. 2026) ile "
                u"değerlendirilmiştir. Bu skorlar araştırma amaçlı "
                u"hesaplamalı öngörülerdir; ACMG/AMP sınıflandırmasında "
                u"yalnızca destekleyici bağlamda kullanılmış, tek başına "
                u"klinik karar için kullanılmamıştır.")

AVI_YUKSEK, SPLICE_YUKSEK, SPLICE_ORTA = 20.0, 1.0, 0.5
KAT_TR = {"yuksek": u"yüksek", "orta": u"orta", "dusuk": u"düşük"}


def yontem_paragrafi(oz):
    aday = oz.get("aday", 0) or 0
    atlas = oz.get("atlas", 0) or 0
    model = oz.get("model", 0) or 0
    yok = (oz.get("bulunamadi", 0) or 0) + (oz.get("hata", 0) or 0) + (oz.get("sorulamadi", 0) or 0)
    p = (u"Yöntem: Aday varyantlar (%d) Google DeepMind AlphaGenome Atlas'a "
         u"(önhesaplanmış in siliko doygunluk mutagenezi, GRCh38; alphagenome %s) "
         u"sorulmuştur. Her varyant için AVI (AlphaGenome Variant Impact) PHRED skoru "
         u"(10 = tüm SNV'lerin en yüksek %%10'u, 20 = en yüksek %%1'i, 30 = en yüksek "
         u"%%0,1'i), birleşik splicing skoru ve modalite bazlı etki skorları (gen "
         u"ekspresyonu, splice site / splice site kullanımı / splice junction, poliadenilasyon, "
         u"kromatin erişilebilirliği, TF ve histon bağlanması, TSS aktivitesi, 3B "
         u"kontakt) ile bunların yaygın varyant arka planına göre kalibre kantil "
         u"değerleri alınmıştır. Kantiller yalnızca genin/elemanın aktif "
         u"olduğu dokularda (aktif alel skoru en aktif dokunun %%10'unun üzerinde) ve çoklu "
         u"karşılaştırma düzeltmesi sonrasında (Bonferroni; p = aktif doku/gen "
         u"hücresi sayısı × (1−|kantil|) ≤ 0,01) anlamlı "
         u"sayılmıştır. Birleşik splicing skoru = max(splice site) + max(splice "
         u"site kullanımı) + max(splice junction)/5; kanonik splice site varyantları tipik "
         u"olarak 2,5–3,5, ≥1,0 güçlü, 0,5–1,0 olası etki."
         % (aday, oz.get("paket") or u"?"))
    s = [u"%d varyant Atlas'ta önhesaplanmış olarak bulunmuştur" % atlas]
    if model:
        s.append(u"Atlas'ın desteklemediği %d indel/MNV canlı AlphaGenome modeliyle "
                 u"(1 Mb pencere; AVI skoru üretilmez) skorlanmıştır" % model)
    if yok:
        s.append(u"%d varyant skorlanamamıştır (Atlas'ta yok, hata ya da kapsam "
                 u"dışı)" % yok)
    return p + u" " + u"; ".join(s) + u"."


def ozet_paragrafi(oz):
    k = oz.get("kategori") or {}
    return (u"Özet: yüksek etki kategorisi %d, orta %d, düşük %d varyant. "
            u"Kategoriler sıralama yardımcısıdır (AVI ≥ 20 veya "
            u"birleşik splicing ≥ 1,0 → yüksek; AVI ≥ 10, splicing ≥ 0,5 ya da "
            u"aktif dokuda düzeltilmiş anlamlı bir modalite sinyali → orta) ve klinik "
            u"eşik değildir; yöntem sabit eşik yerine sıralama önerir."
            % (k.get("yuksek", 0), k.get("orta", 0), k.get("dusuk", 0)))


def _varyant_adi(r):
    v = (r.get("hgvsc") or r.get("key") or u"").strip()
    if r.get("hgvsp"):
        v = u"%s %s" % (v, r["hgvsp"])
    return v or u"–"


def _kisa_yorum(r):
    """CSV'deki uzun yorumdan rapor tablosuna girecek kisa hal."""
    p = []
    sp = _sayi(r.get("splicing_birlesik"))
    if r.get("durum") == "model":
        p.append(u"Atlas indel/MNV desteklemediği için canlı modelle skorlandı (AVI yok)")
    if sp is not None and sp >= SPLICE_YUKSEK:
        p.append(u"güçlü splicing etkisi öngörülüyor")
    elif sp is not None and sp >= SPLICE_ORTA:
        p.append(u"olası splicing etkisi")
    if r.get("duzenleyici_sinyal"):
        p.append(u"aktif dokuda düzeltilmiş düzenleyici sinyal")
    katki = (r.get("avi_katki") or u"").split(";")[0].strip()
    m = re.match(r"([A-Za-z0-9_]+):([+-]?[0-9.]+)", katki)
    if m:
        d = _sayi(m.group(2))
        p.append(u"AVI'yi süren özellik: %s (%s)"
                 % (m.group(1).replace(u"_", u" "),
                    (u"%+.2f" % d).replace(u".", u",") if d is not None else m.group(2)))
    kons = (r.get("consequence") or u"").lower()
    avi = _sayi(r.get("avi"))
    if any(t in kons for t in ("stop gained", "frameshift", "start lost", "stop lost")) \
            and (avi or 0) >= AVI_YUKSEK:
        p.append(u"LoF varyantında yüksek AVI beklenen bulgudur, ek bilgi taşımaz")
    if not p:
        p.append(u"belirgin splicing ya da düzenleyici sinyal yok")
    return u"; ".join(p)


T1_BAS = [u"Gen", u"Varyant", u"AVI", u"Splicing",
          u"Düzenleyici sinyal (modalite, doku)", u"Kat.", u"Değerlendirme"]
T1_GEN = [820, 1950, 520, 620, 1700, 560, 3242]
T2_BAS = [u"Gen", u"Varyant", u"AVI", u"Splicing", u"Kat.", u"AlphaGenome katkısı"]
T2_GEN = [900, 2350, 560, 660, 620, 4322]


def _satir(r, uzun=True):
    h = [u"*%s*" % r["gene"] if r.get("gene") else u"–", _varyant_adi(r),
         vir(r.get("avi"), 1), vir(r.get("splicing_birlesik"), 2)]
    if uzun:
        h.append((r.get("duzenleyici_sinyal") or u"–").replace(u"_", u" "))
    h += [KAT_TR.get(r.get("kategori"), r.get("kategori") or u"–"), _kisa_yorum(r)]
    return h


def tablolar(satirlar, rapor_metni, en_fazla=15):
    """(tablo1, tablo2): once en guclu sinyaller, sonra raporda adi gecen genler."""
    onem = [r for r in satirlar if r.get("kategori") in ("yuksek", "orta")]
    t1 = onem[:en_fazla]
    t1_key = set(r.get("key") for r in t1)
    gecen = []
    for r in satirlar:
        g = (r.get("gene") or u"").strip()
        if not g or r.get("key") in t1_key or len(g) < 3:
            continue
        if re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(g), rapor_metni):
            gecen.append(r)
    return t1, gecen[:en_fazla]


def yorum_paragraflari(satirlar, t1, t2):
    p = []
    guclu = [r for r in satirlar if (_sayi(r.get("splicing_birlesik")) or 0) >= SPLICE_YUKSEK]
    sinyalli = [r for r in satirlar if r.get("duzenleyici_sinyal")]
    if guclu:
        adlar = u", ".join(u"*%s*" % r["gene"] for r in guclu[:8] if r.get("gene"))
        p.append(u"Güçlü splicing öngörüsü (birleşik skor ≥ 1,0) "
                 u"%d varyantta saptanmıştır%s. Bu skorlar varyantın moleküler "
                 u"sonucunu tahmin eder, klinik önemini değil: varyantın popülasyon "
                 u"frekansı, kalıtım modeli ve fenotiple uyumu ayrıca "
                 u"değerlendirilmelidir." % (len(guclu), (u": " + adlar) if adlar else u""))
    else:
        p.append(u"Sorgulanan aday varyantların hiçbirinde güçlü splicing "
                 u"öngörüsü (birleşik skor ≥ 1,0) "
                 u"saptanmamıştır.")
    if sinyalli:
        adlar = u"; ".join(u"*%s* (%s)" % (r.get("gene") or u"?",
                                           (r.get("duzenleyici_sinyal") or u"").replace(u"_", u" "))
                           for r in sinyalli[:6])
        p.append(u"Aktif doku kapılaması ve çoklu karşılaştırma "
                 u"düzeltmesi sonrasında %d varyantta düzenleyici sinyal "
                 u"kalmıştır: %s. Bu bulgular hipotez düzeyindedir ve RNA ya da "
                 u"işlevsel veriyle desteklenmedikçe klinik ağırlık "
                 u"taşımaz." % (len(sinyalli), adlar))
    else:
        p.append(u"Aktif doku kapılaması ve çoklu karşılaştırma "
                 u"düzeltmesi sonrasında hiçbir varyantta anlamlı düzenleyici "
                 u"sinyal kalmamıştır.")
    if t2:
        p.append(u"Raporda tartışılan varyantların AlphaGenome "
                 u"karşılıkları Tablo AG-2'de verilmiştir; yüksek AVI "
                 u"değerlerinin bir bölümü kodlayıcı etkiden "
                 u"(AlphaMissense, korunmuşluk ya da protein kesilmesi) kaynaklanır ve bu durumda "
                 u"AVI, REVEL/AlphaMissense'in verdiği bilgiyi tekrarlar.")
    p.append(u"Sonuç: AlphaGenome bulguları mevcut varyant sınıflandırmalarını "
             u"ve raporun sonucunu değiştirmemiştir; değerlendirme destekleyici "
             u"kanıt olarak sunulmuştur. Ekzom kapsamı dışındaki "
             u"düzenleyici bölgeler ve kopya sayısı değişiklikleri bu "
             u"analizle değerlendirilememiştir.")
    return p


def bolum_xml(oz, satirlar, rapor_metni, baslik_no=u""):
    t1, t2 = tablolar(satirlar, rapor_metni)
    x = [baslik(u"%sAlphaGenome Atlas değerlendirmesi (araştırma amaçlı)" % baslik_no),
         para(yontem_paragrafi(oz)), para(ozet_paragrafi(oz))]
    if t1:
        x.append(altbaslik(u"Tablo AG-1 — AlphaGenome sinyali en güçlü varyantlar"))
        x.append(tablo(T1_BAS, [_satir(r) for r in t1], T1_GEN))
        x.append(para(u"", after=60))
    if t2:
        x.append(altbaslik(u"Tablo AG-2 — Raporda tartışılan varyantların "
                           u"AlphaGenome karşılıkları"))
        x.append(tablo(T2_BAS, [_satir(r, uzun=False) for r in t2], T2_GEN))
        x.append(para(u"", after=60))
    x.append(altbaslik(u"Yorum"))
    x += [para(t) for t in yorum_paragraflari(satirlar, t1, t2)]
    x += [para(SINIR), para(DOSYA_NOT), altbaslik(u"Kaynaklar (AlphaGenome)")]
    x += [para(u"%d. %s" % (i, k), sz=17, ind=200) for i, k in enumerate(KAYNAKLAR, 1)]
    return u"".join(x)


def kisa_cumle(satirlar):
    """Sonuc ve resmi rapora girecek tek cumle (gen adi saymaz; ayrinti kapsamli rapordadir)."""
    guclu = [r for r in satirlar if (_sayi(r.get("splicing_birlesik")) or 0) >= SPLICE_YUKSEK
             or r.get("duzenleyici_sinyal")]
    if not guclu:
        return (u"Aday varyantlar ayrıca AlphaGenome Atlas ile değerlendirilmiş; klinik tabloyu "
                u"açıklayabilecek bir splicing ya da düzenleyici etki saptanmamıştır "
                u"(araştırma amaçlı hesaplamalı öngörü).")
    return (u"Aday varyantlar ayrıca AlphaGenome Atlas ile değerlendirilmiştir; bir bölüm varyantta "
            u"öngörülen splicing ve düzenleyici etkiler araştırma amaçlı hesaplamalı bulgulardır, "
            u"varyant sınıflandırmasını ve rapor sonucunu tek başına değiştirmez. Ayrıntısı ve klinik "
            u"değerlendirmesi kapsamlı analiz raporunda sunulmuştur.")


# ---------------------------------------------------------------- olgu isleme

ANKOR_ANALIZ = [
    r"^\d+[a-z]?\.\s*(ikincil|insidental|sekonder)",
    r"^\d+[a-z]?\.\s*ta[sş][iı]y[iı]c[iı]l[iı]k",
    r"^\d+[a-z]?\.\s*sonu[cç]",
    r"^\d+[a-z]?\.\s*aday gen",
    r"^\d+[a-z]?\.\s*[oö]neriler",
    r"^\d+[a-z]?\.\s*tarama kapsam",
    r"^\d+[a-z]?\.\s*k[iı]s[iı]tl[iı]l[iı]k",
    r"^\d+[a-z]?\.\s*kaynak",
]
ANKOR_SONUC = [r"^[oö]neriler\b", r"^k[iı]s[iı]tl[iı]l[iı]k", r"imza:"]
# resmi rapor: yorum cumlesi 'Negatif test sonuclari...' paragrafindan once,
# yontem cumlesi metrik tablosunun/kisitliliklarin oncesine
ANKOR_RESMI_YORUM = [r"^negatif test sonu", r"^analiz t[uü]rk toplumunda",
                     r"^k[iı]s[iı]tl[iı]l[iı]klar"]
ANKOR_RESMI_YONTEM = [r"^k[iı]s[iı]tl[iı]l[iı]klar", r"^\*bu rapor", r"^\*\*bu sonu"]


def _rapor_dosyalari(klasor):
    """{tur: en yeni .docx}; bulunamayan tur icin None."""
    out = {}
    for tur, kalip in (("analiz", r"analiz"), ("sonuc", r"sonu[cç]"), ("resmi", r"resmi")):
        aday = [y for y in glob.glob(os.path.join(klasor, "*.docx"))
                if not os.path.basename(y).startswith("~$")
                and re.search(kalip, os.path.basename(y), re.I)]
        out[tur] = max(aday, key=os.path.getmtime) if aday else None
    return out


def _bolum_no(metin):
    """Kapsamli raporda CNV/kopya sayisi bolum numarasi -> '6b. ' gibi."""
    m = re.search(r"(\d+)[a-z]?\.\s*(kopya say|cnv)", metin, re.I)
    return u"%db. " % int(m.group(1)) if m else u""


def olgu_isle(klasor, kod, uzerine=False, listele=False, tarih=None):
    kanit = os.path.join(klasor, "kanit")
    yol_json = os.path.join(kanit, "alphagenome_ozet.json")
    yol_csv = os.path.join(kanit, "alphagenome.csv")
    if not (os.path.exists(yol_json) and os.path.exists(yol_csv)):
        return "veri_yok", u"kanit/alphagenome.csv yok (once: python rutin.py --alphagenome %s)" % kod
    try:
        with io.open(yol_json, encoding="utf-8") as f:
            oz = json.load(f)
    except (OSError, ValueError) as e:
        return "hata", u"ozet.json okunamadi: %s" % e
    if oz.get("durum") != "tamam":
        return "atlandi", u"AlphaGenome adimi '%s' (%s)" % (oz.get("durum"), oz.get("neden") or u"-")
    try:
        with io.open(yol_csv, encoding="utf-8-sig", newline="") as f:
            satirlar = list(csv.DictReader(f))
    except OSError as e:
        return "hata", u"alphagenome.csv okunamadi: %s" % e
    if not satirlar:
        return "atlandi", u"alphagenome.csv bos"

    dosyalar = _rapor_dosyalari(klasor)
    if not any(dosyalar.values()):
        return "rapor_yok", u"olgu klasorunde .docx rapor yok"

    tarih = tarih or datetime.date.today().strftime("%Y-%m-%d")
    yapilan = []
    for tur in ("analiz", "sonuc", "resmi"):
        kaynak = dosyalar.get(tur)
        if not kaynak:
            continue
        metin = docx_metin(kaynak)
        if u"AlphaGenome" in metin and not uzerine:
            yapilan.append(u"%s: zaten var" % tur)
            continue
        ad = os.path.basename(kaynak)
        yeni_ad = re.sub(r"\d{4}-\d{2}-\d{2}", tarih, ad)
        if yeni_ad == ad:
            yeni_ad = u"%s_%s.docx" % (os.path.splitext(ad)[0], tarih)
        hedef = os.path.join(klasor, yeni_ad)
        if os.path.abspath(hedef) == os.path.abspath(kaynak):
            hedef = os.path.join(klasor, u"%s_AG.docx" % os.path.splitext(ad)[0])
        if listele:
            yapilan.append(u"%s: %s -> %s" % (tur, ad, os.path.basename(hedef)))
            continue
        if tur == "analiz":
            ekle = [(bolum_xml(oz, satirlar, metin, _bolum_no(metin)), ANKOR_ANALIZ)]
        elif tur == "sonuc":
            ekle = [(para(kisa_cumle(satirlar), sz=18) + para(YONTEM_CUMLE, sz=18), ANKOR_SONUC)]
        else:                                   # resmi rapor: iki ayri yer
            ekle = [(para(kisa_cumle(satirlar), sz=20, arial=False, jc="both"), ANKOR_RESMI_YORUM),
                    (para(YONTEM_CUMLE, sz=20, arial=False, jc="both"), ANKOR_RESMI_YONTEM)]
        m_t = re.search(r"(\d{4}-\d{2}-\d{2})", ad)
        tarihler = (m_t.group(1), tarih) if m_t else None
        try:
            docx_bolum_ekle(kaynak, hedef, ekle, tarihler)
            yapilan.append(u"%s: %s" % (tur, os.path.basename(hedef)))
        except Exception as e:
            yapilan.append(u"%s: HATA %s: %s" % (tur, type(e).__name__, e))
    return "tamam", u"; ".join(yapilan)


def main():
    ap = argparse.ArgumentParser(description="Var olan WES raporlarina AlphaGenome bolumunu ekler")
    ap.add_argument("kodlar", nargs="+", help="olgu kodlari ya da TUMU")
    ap.add_argument("--uzerine", action="store_true", help="raporda AlphaGenome varsa da yeniden yaz")
    ap.add_argument("--listele", action="store_true", help="hicbir dosya yazma, ne yapilacagini goster")
    ap.add_argument("--tarih", help="dosya adindaki tarih (varsayilan: bugun)")
    ap.add_argument("--kok", help="WES_CES_Rutin_Raporlar klasoru (otomatik bulunamazsa)")
    a = ap.parse_args()

    r = a.kok or kok()
    if not r or not os.path.isdir(r):
        log("!! WES_CES_Rutin_Raporlar klasoru bulunamadi (--kok ile verebilirsiniz)")
        return 1
    kodlar = a.kodlar
    if [k.upper() for k in kodlar] == ["TUMU"]:
        kodlar = [k for k in sorted(os.listdir(r))
                  if os.path.isdir(os.path.join(r, k, "kanit")) and not k.startswith(("_", "."))]
    log("Kok: %s" % r)
    log("%d olgu%s" % (len(kodlar), " (LISTELEME: dosya yazilmayacak)" if a.listele else ""))
    sayac = {}
    for kod in kodlar:
        klasor = os.path.join(r, kod)
        if not os.path.isdir(klasor):
            log("  %-28s klasor_yok" % kod)
            sayac["klasor_yok"] = sayac.get("klasor_yok", 0) + 1
            continue
        durum, not_ = olgu_isle(klasor, kod, a.uzerine, a.listele, a.tarih)
        sayac[durum] = sayac.get(durum, 0) + 1
        log("  %-28s %-10s %s" % (kod, durum, not_))
    log("Ozet: " + ", ".join("%s=%d" % (k, v) for k, v in sorted(sayac.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
