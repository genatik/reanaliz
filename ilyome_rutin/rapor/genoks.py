# -*- coding: utf-8 -*-
"""Genoks (GenoXome) bicimli 'WES/CES/PANEL Analiz Raporu' TASLAGI - her olgunun 4. raporu.

Ozel Genoks Genetik Hastaliklar Degerlendirme Merkezi'nin (GNK.FR.87 rev.03) rapor duzeni
python-docx ile sifirdan kurulur; sablon dosyasina gerek yoktur. Uretilen belge laboratuvarin
antetli formuna aktarilmak uzere bir TASLAKTIR: logo, sertifika isaretleri ve dijital imza
yoktur, kimlik alanlari (ad, TC, dogum tarihi, protokol, numune tarihleri) olgu klasorundeki
istege bagli kimlik.json'dan okunur, yoksa [____] olarak birakilir.

Kullanim (vaka_<kod>.py icinden):
    from genoks import genoks_raporu, genoks_ebeveyn, gsatir, gsatir_vus
    ekle(genoks_raporu(KOD, SONUC_METNI, [gsatir(t, omim="OMIM#203700") for t in T_],
                       YORUMLAR, ONERILER))
    ekle(genoks_ebeveyn(KOD, "anne", "2407-26", PROBAND_TANI, SATIRLAR, YORUMLAR))

Varyant tablosu satiri (7 sutun): [Kromozom yeri (hg38), "GEN\\n(NM_...)", "c.…\\n(p.…)",
Genotip, Siniflandirma, Hastalik (OMIM#…), Kalitim]. gsatir() surucudeki T_ satirini
(gen, "chr1:109.066.220 A>T", "NM_…:c.…", "p.(…)", zigosite, hastalik, sinif) bu bicime cevirir.
"""
import io, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from build_reports import WARN_TR, shade, cell_text
from build7 import ROOT, TARIH, DOSYA_TARIH, test_tipi
from negatif import veri

LAB = u"ÖZEL GENOKS GENETİK HASTALIKLAR DEĞERLENDİRME MERKEZİ"
RAPOR_AD = u"WES/CES/PANEL Analiz Raporu"
RUHSAT = u"Ruhsat No: GHDM-SM/06.15/01"
ADRES = (u"Adres: Emniyet Mahallesi Silahtar Caddesi No: 67 Yenimahalle / Ankara\n"
         u"Tel: +90 312 229 78 59 / 444 8 732 Web: www.genoks.com.tr")
DOKUMAN = u"Doküman No: GNK.FR.87\nRevizyon No.: 03"
YAYIN = u"Yayın Tarihi: 16.05.2022\nRevizyon Tarihi: 15.08.2025"
GONDEREN = u"Prof. Dr. Tahir Atik"
NUMUNE_TURU = u"Periferik kan"
NUMUNE_YERI = u"İzmir"
BOS = u"[____]"

TEST_ADI = {"WES": u"Tüm Ekzom DNA Dizi Analizi\n(Whole Exome Sequencing)",
            "CES": u"Klinik Ekzom DNA Dizi Analizi\n(Clinical Exome Sequencing)"}
TIP_EK = {"solo": "SOLO", "duo": "DUO", "trio": "TRIO", "kuartet": "KUARTET"}

REANALIZ_METNI = (u"Bu raporun sonuçlandığı tarihinden itibaren hastalık ile ilişkili olabilecek yeni "
                  u"kanıtlara sahip herhangi bir varyant belirlenebileceği için ekzom verilerinin yeniden "
                  u"analizi talep edilebilir. Yeni genetik bilgilerin birikmesine izin vermek için yeniden "
                  u"analiz istemeden önce en az bir yıl beklemenizi öneririz. Daha fazla bilgi için lütfen "
                  u"yeniden analiz talep edildiğinde laboratuvar ile iletişime geçiniz.")
SEKONDER_YOK = (u"ACMG rehberleri tarafından, sekonder bulgular açısından değerlendirilmesi önerilen "
                u"genlerde herhangi bir patojenik veya olası patojenik varyant saptanmamıştır.")
TASIYICI_TARAMA = (u"Analiz Türk toplumunda sık görülen kistik fibrozis (CFTR), ailevi akdeniz ateşi (MEFV), "
                   u"beta talasemi (HBB), fenilketonüri (PAH), glukoz 6-fosfat dehidrogenaz eksikliği (G6PD), "
                   u"piruvat kinaz eksikliği (PKLR) ve biyotinidaz eksikliği (BTD) taşıyıcılıkları açısından "
                   u"incelenmiş; diğer otozomal resesif hastalıkların taşıyıcılıkları ise raporlanmamıştır.")
ONERI_EBEVEYN = [u"Saptanan varyantların klinik bulgular eşliğinde değerlendirilmesi önerilir.",
                 u"Segregasyon analizi için anne ve babadan da moleküler analiz yapılması önerilir.",
                 u"Hastanın genetik danışma alması gerekmektedir."]
ALT_NOTLAR = [u"İmzasız raporlar geçersizdir.",
              u"Bu sonuç yalnızca analizi yapılan numuneyi kapsamaktadır.",
              u"Bu rapor, Özel Genoks Genetik Hastalıklar Değerlendirme Merkezi'nin yazılı izni olmadan "
              u"3.kişi ve kurumlarla paylaşılamaz."]


def yontem_paragraflari(test, kit, cihaz, ag_cumlesi=None):
    """Yöntem bolumu; (bold etiket, metin) ciftleri ya da duz metin."""
    ad = u"Tüm Ekzom Dizileme" if test == "WES" else u"Klinik Ekzom Dizileme"
    p = [("Test Adı: ", ad),
         ("Metod: ", u"%s kiti ile hazırlanan library ürünleri %s cihazında dizilenir." % (kit, cihaz)),
         ("Açıklama: ", u"İnsan genomunun protein kodlayan bölgesi olup %1-2'sini oluşturan ekzom, "
                        u"hastalık yaptığı kanıtlanmış olan mutasyonların %85'ini içerir. Tüm ekzom "
                        u"dizileme testi ile çeşitli teknik nedenlerden dolayı tüm ekzonlar analiz edilemeyebilir."),
         u"Ekzom dizileme, ekzon ve ekzon-intron bağlantı noktalarındaki nokta mutasyonları ve küçük "
         u"delesyon/duplikasyonları (<20bp) tespit edebilirken, gende incelenemeyen bölgelerdeki (regülatör, "
         u"promoter, derin intronik vs.) değişimleri, büyük delesyon/duplikasyonları ve kompleks yeniden "
         u"düzenlenmeleri, dengeli translokasyonları, tekrarlayan dizi bölgelerini, kopya sayısı değişimlerini, "
         u"mozaisizmleri, mitokondriyal DNA mutasyonlarını, metilasyon bozuklukları gibi epigenetik değişimleri "
         u"tespit edemez. Ekzon-intron bağlantı noktalarındaki okunma derinlikleri değişkenlik gösterebilir.",
         u"Bu raporda, ACMG (American College of Medical Genetics and Genomics) kriterlerine göre sınıflandırılmış "
         u"fenotip ile ilişkili olduğu düşünülen Patojenik, Muhtemel Patojenik veya Klinik Önemi Bilinmeyen "
         u"Varyantlar listelenmiştir. Ayrıca, Klinik Önemi Bilinmeyen Varyantlar kendi içinde 'Güçlü Klinik Önemi "
         u"Bilinmeyen Varyantlar ve Zayıf Klinik Önemi Bilinmeyen Varyantlar' olarak sınıflandırılmaktadır. "
         u"Yapılacak ileri ek çalışmalar ile hastalığa neden olabileceği ispatlanabilecek varyantlar 'Güçlü Klinik "
         u"Önemi Bilinmeyen Varyantlar' sınıfında değerlendirilmektedir. Güçlü Klinik Önemi Bilinmeyen Varyantlar "
         u"raporlanmakta iken, Zayıf Klinik Önemi Bilinmeyen Varyantlar raporlanmamaktadır.",
         u"Bu varyantlar test edilen hastalıkla ilişkileri açısından güncel verilerle değerlendirilmelidir. Rapor "
         u"tarihinde patojenitesi anlaşılmamış ve raporda listelenmemiş olan bir varyasyon zaman içerisinde yapılan "
         u"bilimsel çalışmalarla patojenik olarak sınıflandırılabilir. Nadir polimorfizmler yanlış pozitif/negatifliğe "
         u"yol açabilir. Bu nedenle pozitif/negatif sonuçların klinik bulgular doğrultusunda hekim tarafından "
         u"değerlendirilmesi ve gerekli görüldüğü takdirde diğer tanı yöntemleri ile doğrulanması gerekmektedir.",
         u"Varyant analizi için Ilyome bioscience (ilyome.com) platformu kullanılmıştır."]
    if ag_cumlesi:
        p.append(ag_cumlesi)
    return p


# ---------------------------------------------------------------- yardimcilar
def _run(p, text, size=9, bold=False, italic=False, color=None):
    r = p.add_run(text)
    r.font.name = "Arial"; r.font.size = Pt(size); r.bold = bold; r.italic = italic
    if color:
        r.font.color.rgb = color
    return r


def _para(doc, text="", size=9, bold=False, space_after=4, align=None, italic=False):
    p = doc.add_paragraph()
    for i, part in enumerate(text.split("*")):
        if part:
            _run(p, part, size=size, bold=bold, italic=italic or (i % 2 == 1))
    p.paragraph_format.space_after = Pt(space_after)
    if align is not None:
        p.alignment = align
    return p


def _baslik(doc, text):
    p = _para(doc, text, size=10, bold=True, space_after=6)
    p.paragraph_format.space_before = Pt(10)
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr"); bot = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single"); bot.set(qn("w:sz"), "4")
    bot.set(qn("w:space"), "4"); bot.set(qn("w:color"), "BFBFBF")
    bdr.append(bot); pPr.append(bdr)
    return p


def _kenarsiz(t):
    tblPr = t._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for k in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:" + k); e.set(qn("w:val"), "nil"); b.append(e)
    tblPr.append(b)


def _hucre(cell, text, size=8, bold=False, align=None, italic_gen=False):
    """Hucre metni; satir sonlari '\\n' ile. italic_gen: ilk satir (gen adi) italik."""
    p = cell.paragraphs[0]
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    for i, line in enumerate(str(text).split("\n")):
        q = p if i == 0 else cell.add_paragraph()
        _run(q, line, size=size, bold=bold, italic=(italic_gen and i == 0))
        q.paragraph_format.space_after = Pt(0)
        if align is not None:
            q.alignment = align
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def _alan(cell, etiket, deger):
    p = cell.paragraphs[0]
    _run(p, etiket, size=8.5, bold=True)
    p.paragraph_format.space_after = Pt(0)
    for i, line in enumerate(str(deger).split("\n")):
        q = p if i == 0 else cell.add_paragraph()
        _run(q, (u": " if i == 0 else u"  ") + line, size=8.5)
        q.paragraph_format.space_after = Pt(0)


def _setup(doc, sayfa_etiketi):
    st = doc.styles["Normal"]
    st.font.name = "Arial"; st.font.size = Pt(9)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
    s = doc.sections[0]
    s.page_width = Cm(21.0); s.page_height = Cm(29.7)
    s.top_margin = Cm(2.6); s.bottom_margin = Cm(2.4)
    s.left_margin = Cm(1.8); s.right_margin = Cm(1.8)
    s.header_distance = Cm(0.8); s.footer_distance = Cm(0.8)
    h = s.header.paragraphs[0]; h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(h, LAB + "\n", size=9, bold=True)
    _run(h, RAPOR_AD + "\n", size=9, bold=True)
    _run(h, RUHSAT, size=7.5, bold=True)
    f = s.footer
    t = f.add_table(rows=1, cols=4, width=Cm(17.4))
    _kenarsiz(t)
    for i, w in enumerate([8.0, 3.4, 3.6, 2.4]):
        t.rows[0].cells[i].width = Cm(w)
    _hucre(t.rows[0].cells[0], ADRES, size=6.5)
    _hucre(t.rows[0].cells[1], DOKUMAN, size=6.5)
    _hucre(t.rows[0].cells[2], YAYIN, size=6.5)
    c = t.rows[0].cells[3]; p = c.paragraphs[0]
    _run(p, u"Sayfa No: ", size=6.5)
    for instr, sep in (("PAGE", "/"), ("NUMPAGES", "")):
        fld = OxmlElement("w:fldSimple"); fld.set(qn("w:instr"), instr)
        r = OxmlElement("w:r"); rp = OxmlElement("w:rPr")
        sz = OxmlElement("w:sz"); sz.set(qn("w:val"), "13"); rp.append(sz); r.append(rp)
        tx = OxmlElement("w:t"); tx.text = "1"; r.append(tx); fld.append(r)
        p._p.append(fld)
        if sep:
            _run(p, sep, size=6.5)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    # ilk paragraf: karar-destegi uyarisi (lab antetine aktarilirken silinir)
    w = doc.add_paragraph()
    r = _run(w, WARN_TR + u" Bu belge Genoks rapor düzeninde hazırlanmış bir TASLAKTIR; kimlik alanları "
                u"ve imzalar laboratuvarca tamamlanır.", size=7.5, bold=True,
             color=RGBColor(0xB0, 0x00, 0x00))
    w.paragraph_format.space_after = Pt(6)


def kimlik_oku(kod):
    """Olgu klasorundeki istege bagli kimlik.json (Ad Soyad, TC, Dogum Tarihi, Cinsiyet, Protokol No,
    Numune Alim, Lab Teslim, Onay, Numune Yeri; ebeveynler icin 'anne'/'baba' alt sozlukleri)."""
    p = os.path.join(ROOT, kod, "kimlik.json")
    if os.path.isfile(p):
        try:
            return json.load(io.open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _kunye(doc, k, ornek_no, endikasyon, test_adi):
    t = doc.add_table(rows=7, cols=2)
    _kenarsiz(t); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    sol = [(u"Ad Soyad", k.get("Ad Soyad") or BOS),
           (u"TC Kimlik No", k.get("TC") or BOS),
           (u"Doğum Tarihi", k.get("Dogum Tarihi") or BOS),
           (u"Cinsiyet", k.get("Cinsiyet") or BOS),
           (u"Protokol No", k.get("Protokol No") or BOS),
           (u"Gönderen Merkez / Hekim", k.get("Gonderen") or GONDEREN),
           (u"Endikasyon&Klinik Bilgi", endikasyon)]
    sag = [(u"Numune Türü", k.get("Numune Turu") or NUMUNE_TURU),
           (u"Numune Alım Yeri", k.get("Numune Yeri") or NUMUNE_YERI),
           (u"Örnek No", ornek_no),
           (u"Numune Alım Tarihi&Saati", k.get("Numune Alim") or BOS),
           (u"Lab. Teslim Tarihi&Saati", k.get("Lab Teslim") or BOS),
           (u"Uzm. Hekim Onay Tarihi&Saati", k.get("Onay") or BOS),
           (u"Test Adı", test_adi)]
    for i in range(7):
        _alan(t.rows[i].cells[0], sol[i][0], sol[i][1])
        _alan(t.rows[i].cells[1], sag[i][0], sag[i][1])
        t.rows[i].cells[0].width = Cm(8.9); t.rows[i].cells[1].width = Cm(8.5)
    return t


def _varyant_tablosu(doc, satirlar):
    bas = [u"Kromozom Yeri\n(hg38)", u"Gen /\nTranskript ID", u"Varyant", u"Genotip",
           u"Sınıflandırma", u"Hastalık", u"Kalıtım"]
    gen = [2.5, 2.6, 2.5, 1.9, 2.5, 4.3, 1.3]
    t = doc.add_table(rows=1, cols=7); t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(bas):
        c = t.rows[0].cells[i]; shade(c, "D9D9D9")
        _hucre(c, h, size=7.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    for s in satirlar:
        cells = t.add_row().cells
        for i, v in enumerate(s[:7]):
            _hucre(cells[i], v, size=7.5, align=WD_ALIGN_PARAGRAPH.CENTER, italic_gen=(i == 1))
    for row in t.rows:
        for i, w in enumerate(gen):
            row.cells[i].width = Cm(w)
    return t


def _yontem_ve_imza(doc, test, kit, cihaz, ag_cumlesi):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    _baslik(doc, u"Yöntem")
    for item in yontem_paragraflari(test, kit, cihaz, ag_cumlesi):
        p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(4)
        if isinstance(item, tuple):
            _run(p, item[0], size=8, bold=True); _run(p, item[1], size=8)
        else:
            _run(p, item, size=8)
    _para(doc, "", space_after=14)
    t = doc.add_table(rows=1, cols=2); _kenarsiz(t); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for c, (unvan, ad) in zip(t.rows[0].cells,
                              [(u"Laboratuvar Sorumlusu", BOS), (u"Tıbbi Genetik Doktoru", BOS + u"\nDiploma Tescil No: " + BOS)]):
        _hucre(c, unvan + "\n" + ad + u"\n\n\n(imza)", size=8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
        c.width = Cm(8.7)
    _para(doc, "", space_after=20)
    for n in ALT_NOTLAR:
        _para(doc, u"• " + n, size=7.5, space_after=1)


def _kit_cihaz(o, kit=None, cihaz=None):
    _kit = kit
    for b in (o.get("bireyler") or {}).values():
        _kit = _kit or b.get("kit")
    _kit = _kit or u"TWIST Exome 2.0"
    return _kit, (cihaz or u"DNBSEQ-T7")


def _ag_cumlesi(kod):
    """kanit/alphagenome_rapor.txt varsa yontem cumlesini al (ilk 'Yöntem' satiri)."""
    p = os.path.join(ROOT, kod, "kanit", "alphagenome_rapor.txt")
    if not os.path.isfile(p):
        return None
    try:
        for s in io.open(p, encoding="utf-8").read().splitlines():
            if s.lower().startswith(u"yöntem") or "AlphaGenome Atlas" in s and len(s) < 400:
                return s.split(":", 1)[-1].strip() if s.lower().startswith(u"yöntem") else s.strip()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- satir cevirici
_SINIF = [(u"patojenik/olası patojenik — taşıyıcı", u"Patojenik/Muhtemel Patojenik-Taşıyıcı"),
          (u"olası patojenik — taşıyıcı", u"Muhtemel Patojenik-Taşıyıcı"),
          (u"patojenik — taşıyıcı", u"Patojenik-Taşıyıcı"),
          (u"olası patojenik", u"Muhtemel Patojenik"),
          (u"patojenik", u"Patojenik"),
          (u"vus", u"Klinik Önemi Bilinmeyen (VUS)")]


def gsinif(s):
    k = (s or "").strip().lower()
    for anahtar, deger in _SINIF:
        if k.startswith(anahtar):
            return deger
    return s


def gkalitim(hastalik, varsayilan="OR"):
    h = hastalik or ""
    for et in ("XR", "XL", "XD", "OD/OR", "OD", "OR"):
        if "(%s" % et in h or " %s)" % et in h or h.endswith(et):
            return et
    return varsayilan


def gpos(konum):
    """'chr15:89.327.324 C>T' -> 'chr15:89327324'; 'chr8:91334331' aynen."""
    k = (konum or "").split()[0] if konum else u"—"
    return k.replace(".", "")


def gsatir(t, omim="", kalitim=None, genotip=None, sinif=None, hastalik=None):
    """Surucudeki T_ satirini (7 alan) Genoks tablosu satirina cevirir."""
    gen, konum, nmc, p, zig, hast, snf = t[:7]
    nm, c = (nmc.split(":", 1) + [""])[:2] if ":" in nmc else ("", nmc)
    pp = (p or u"—").strip()
    var = c if pp in (u"—", "", "-") else c + "\n(" + pp.replace("p.(", "p.").rstrip(")") + ")"
    hastalik_m = (hastalik or hast).strip()
    for et in (" (OR)", " (OD)", " (XR)", " (XL)", " (OD/OR)"):
        hastalik_m = hastalik_m.replace(et, "")
    if omim:
        hastalik_m += "\n" + omim
    return [gpos(konum), gen + ("\n(" + nm + ")" if nm else ""), var,
            genotip or zig.split(" (")[0], sinif or gsinif(snf), hastalik_m,
            kalitim or gkalitim(hast)]


def gsatir_vus(v, konum=u"—", omim="", kalitim=None, sinif=None, hastalik=None):
    """VUS_/varyant satirini ([gen, 'NM:c.\\np.', zigosite, kalitim, sinif, hastalik]) cevirir."""
    gen, nmcp, zig, kal, snf, hast = v[:6]
    nmc, p = (nmcp.split("\n") + [u"—"])[:2]
    nm, c = (nmc.split(":", 1) + [""])[:2] if ":" in nmc else ("", nmc)
    pp = p.strip()
    var = c if pp in (u"—", "", "-") else c + "\n(" + pp.replace("p.(", "p.").rstrip(")") + ")"
    hastalik_m = (hastalik or hast) + ("\n" + omim if omim else "")
    return [gpos(konum), gen + ("\n(" + nm + ")" if nm else ""), var, zig.split(" (")[0],
            sinif or gsinif(snf), hastalik_m, kalitim or (kal if kal not in (u"—", "") else "OR")]


# ---------------------------------------------------------------- proband raporu
def genoks_raporu(kod, sonuc_metni, satirlar, yorumlar, oneriler, sekonder=None,
                  endikasyon=None, reanaliz=True, kit=None, cihaz=None, ornek_no=None,
                  test_adi=None, ag_cumlesi=None):
    """Proband icin Genoks bicimli taslak. satirlar: 7 sutunlu listeler (gsatir ile uretilir).
    sekonder: None -> standart 'saptanmamistir' cumlesi; str -> o cumle; list -> tablo satirlari."""
    o = veri(kod)
    OUT = o["_klasor"]
    test = test_tipi(kod)
    k = kimlik_oku(kod)
    doc = Document(); _setup(doc, kod)
    ta = test_adi or (TEST_ADI.get(test, TEST_ADI["WES"]) + "\n(%s-%s)" % (test, TIP_EK.get(o.get("tip"), "SOLO")))
    _kunye(doc, k, ornek_no or kod, endikasyon or o["_klinik"], ta)

    _baslik(doc, u"Sonuç")
    for s in ([sonuc_metni] if isinstance(sonuc_metni, str) else sonuc_metni):
        _para(doc, s, size=9)

    _baslik(doc, u"Saptanan varyant(lar)")
    if satirlar:
        _varyant_tablosu(doc, satirlar)
    else:
        _para(doc, u"Klinik bulgularla ilişkili ya da raporlanması uygun görülen patojenik, olası patojenik "
                   u"veya güçlü klinik önemi bilinmeyen varyant saptanmamıştır.", size=9)

    _baslik(doc, u"Yorum")
    for y in yorumlar:
        _para(doc, y, size=9)

    _baslik(doc, u"Öneriler")
    for x in oneriler:
        p = _para(doc, u"• " + x, size=9, space_after=2)
        p.paragraph_format.left_indent = Cm(0.4)

    if reanaliz:
        _baslik(doc, u"Reanaliz"); _para(doc, REANALIZ_METNI, size=8.5)
    _baslik(doc, u"Sekonder Bulgular")
    if isinstance(sekonder, list):
        _varyant_tablosu(doc, sekonder)
    else:
        _para(doc, sekonder or SEKONDER_YOK, size=9)

    _kit, _cihaz = _kit_cihaz(o, kit, cihaz)
    _yontem_ve_imza(doc, test, _kit, _cihaz, ag_cumlesi if ag_cumlesi is not None else _ag_cumlesi(kod))
    p = os.path.join(OUT, "WES_genoks_%s_%s.docx" % (kod, DOSYA_TARIH))
    doc.save(p); return p


# ---------------------------------------------------------------- ebeveyn raporu
def genoks_ebeveyn(kod, kim, ornek_no, proband_tani, satirlar, yorumlar, aktarim=None,
                   oneriler=None, sekonder=None, tasiyici_tarama=True, kit=None, cihaz=None,
                   endikasyon=None, ag_cumlesi=None,
                   sonuc_baslik=u"Probandın klinik bulgularıyla ilişkili varyant saptanmamıştır."):
    """Anne/baba icin Genoks bicimli taslak (kim: 'anne' | 'baba'; ornek_no: ebeveynin ornek kodu)."""
    o = veri(kod)
    OUT = o["_klasor"]
    test = test_tipi(kod)
    k = (kimlik_oku(kod).get(kim) or {})
    doc = Document(); _setup(doc, kod)
    cocuk = u"Oğlunda" if (o["_alan"].get("Cinsiyet") or "").lower().startswith("e") else u"Çocuğunda"
    ta = TEST_ADI.get(test, TEST_ADI["WES"]) + "\n(%s-%s)" % (test, TIP_EK.get(o.get("tip"), "TRIO"))
    _kunye(doc, k, ornek_no, endikasyon or (cocuk + " " + proband_tani), ta)

    _baslik(doc, u"Sonuç")
    if sonuc_baslik:
        _para(doc, sonuc_baslik, size=9, bold=True, space_after=2)
    _para(doc, aktarim or
          (u"Probandda klinik bulguları açıklayan patojenik veya olası patojenik varyant saptanmadığından "
           u"probanda aktarılmış nedensel bir varyant bildirilememektedir. Aşağıda bu bireyin kendisine ait, "
           u"klinik tabloyla ilişkisiz ancak raporlanması uygun görülen taşıyıcılık bulguları sunulmuştur."), size=9)

    if satirlar:
        _para(doc, u"Probandın klinik bulgularıyla ilişkili olmasa da raporlanması uygun görülen patojenik ve "
                   u"olası patojenik varyantlar aşağıda belirtilmiştir:", size=9, bold=True)
        _varyant_tablosu(doc, satirlar)
    else:
        _para(doc, u"Probandın klinik bulgularıyla ilişkili olmayan, raporlanması uygun görülen patojenik veya "
                   u"olası patojenik varyant saptanmamıştır.", size=9)

    _baslik(doc, u"Analiz Yorumu")
    for y in yorumlar:
        _para(doc, y, size=9)
    if tasiyici_tarama:
        _para(doc, TASIYICI_TARAMA, size=9)

    _baslik(doc, u"Öneriler")
    for x in (oneriler or ONERI_EBEVEYN):
        p = _para(doc, u"• " + x, size=9, space_after=2)
        p.paragraph_format.left_indent = Cm(0.4)
    _baslik(doc, u"Reanaliz"); _para(doc, REANALIZ_METNI, size=8.5)
    _baslik(doc, u"Sekonder Bulgular")
    if isinstance(sekonder, list):
        _varyant_tablosu(doc, sekonder)
    else:
        _para(doc, sekonder or SEKONDER_YOK, size=9)

    _kit, _cihaz = _kit_cihaz(o, kit, cihaz)
    _yontem_ve_imza(doc, test, _kit, _cihaz, ag_cumlesi if ag_cumlesi is not None else _ag_cumlesi(kod))
    p = os.path.join(OUT, "WES_genoks_ebeveyn_%s_%s_%s.docx" % (kim, kod, DOSYA_TARIH))
    doc.save(p); return p
