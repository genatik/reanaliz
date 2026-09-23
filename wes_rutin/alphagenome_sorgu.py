#!/usr/bin/env python3
"""
alphagenome_sorgu.py - AlphaGenome Atlas API ile varyant etki skorlari.

Genomize eksen CSV'lerindeki aday varyantlari (key = krom:poz:ref:alt, hg38)
Google DeepMind AlphaGenome Atlas'a sorar; her varyant icin:

  * AVI (AlphaGenome Variant Impact) PHRED skoru  - 10 = en yuksek %10,
    20 = en yuksek %1, 30 = en yuksek %0.1 (tum SNV'ler icinde siralama)
  * AVI ozellik katkilari (SHAP) - skoru hangi modalite surukluyor
  * Modalite bazli etki skorlari (RNA-seq ekspresyon, splice site /
    splice site usage / splice junction, poliadenilasyon, ATAC, DNase,
    ChIP-TF, ChIP-Histone, CAGE, PROCAP, kontakt haritasi) - ham deger ve
    kalibre kantil (-1..1; |0.99| = yaygin varyant arka planinin en uc %1'i)
  * Birlesik splicing skoru (makaledeki formul: max(SS)+max(SSU)+max(SJ)/5)

Atlas'ta bulunmayan varyantlar (ornegin nadir indel'ler) istenirse canli
AlphaGenome modeliyle (1 Mb pencere) skorlanir (--model, ust sinir --model-max).

Ciktilar (olgu klasorune):
    alphagenome.csv        - varyant basina tek satir ozet (rapora giren tablo)
    alphagenome_detay.csv  - varyant x skor x doku uzun tablo (en yuksek N doku)
    alphagenome_ozet.json  - calisma bilgisi (surum, skor adlari, sayimlar, hatalar)
    alphagenome_rapor.txt  - rapora girecek hazir Turkce bolum + yontem cumlesi + kaynakca

Kurulum (bir kez):
    pip install alphagenome            (Python >= 3.10)
    API anahtari: https://alphagenome.google/api  (ticari olmayan kullanim)
    Windows: setx ALPHAGENOME_API_KEY "..."
    macOS  : anahtari ~/.alphagenome_api_key dosyasina yazin (ya da ~/.zprofile'da export)

Kullanim:
    python alphagenome_sorgu.py <olgu_klasoru>                # eksen CSV'lerinden adaylari toplar
    python alphagenome_sorgu.py <olgu_klasoru> --csv aday.csv # belirli bir CSV (key sutunu)
    python alphagenome_sorgu.py --varyant chr12:13865958:C:T  # tek varyant, ekrana
    python alphagenome_sorgu.py --skorlar-listele             # sunucudaki skor adlarini listele

Notlar:
  * Referans genom GRCh38/hg38 olmalidir; hg19 olgularda adim ATLANIR (liftover yok).
  * AlphaGenome ciktilari arastirma amaclidir; tek basina klinik karar
    verdirmez. Rapor metninde bu sinir acikca yazilir (bkz. rutin.py).
  * Skorlar diskte onbellege alinir (_sistem/alphagenome_onbellek/); ayni
    varyant ikinci kez sorulmaz (ebeveynlerle paylasilan varyantlar dahil).
"""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

SURUM = "1.0"

# Raporda gosterilen modaliteler (Atlas skor adi -> kisa ad, aciklama).
# Adlar RECOMMENDED_VARIANT_SCORERS anahtarlariyla aynidir; sunucu farkli
# adlandirirsa `--skorlar` ile bakip ALPHAGENOME_SKORLAR ile ezilebilir.
MODALITELER = [
    ("RNA_SEQ",           "ekspresyon",   "Gen ekspresyonu (RNA-seq, log-FC)"),
    ("SPLICE_SITES",      "splice_site",  "Splice site olasiligi degisimi"),
    ("SPLICE_SITE_USAGE", "splice_usage", "Splice site kullanimi degisimi"),
    ("SPLICE_JUNCTIONS",  "splice_junc",  "Splice junction okuma degisimi (log-FC)"),
    ("POLYADENYLATION",   "polyA",        "Poliadenilasyon bolgesi kullanimi"),
    ("ATAC",              "atac",         "Kromatin erisilebilirligi (ATAC)"),
    ("DNASE",             "dnase",        "Kromatin erisilebilirligi (DNase)"),
    ("CHIP_TF",           "tf",           "Transkripsiyon faktoru baglanmasi (ChIP-TF)"),
    ("CHIP_HISTONE",      "histon",       "Histon isaretleri (ChIP-Histone)"),
    ("CAGE",              "cage",         "TSS aktivitesi (CAGE)"),
    ("PROCAP",            "procap",       "TSS aktivitesi (PRO-cap)"),
    ("CONTACT_MAPS",      "kontakt",      "3B kontakt haritasi"),
]
MOD_KISA = {ad: kisa for ad, kisa, _ in MODALITELER}
SPLICE_SKORLAR = ("SPLICE_SITES", "SPLICE_SITE_USAGE", "SPLICE_JUNCTIONS")

# Rapor/siralama esikleri. Makale (Cheng ve ark. 2026) sabit esik yerine
# siralama onerir; bunlar yalnizca tabloyu okunur kilan yol gostericilerdir.
AVI_YUKSEK, AVI_ORTA = 20.0, 10.0          # PHRED: %1 ve %10
KANTIL_YUKSEK, KANTIL_ORTA = 0.99, 0.95    # |kalibre kantil|
SPLICE_YUKSEK, SPLICE_ORTA = 1.0, 0.5      # birlesik splicing (dokumantasyon: >1 buyuk etki)

DETAY_DOKU_N = 5          # detay CSV'de skor basina en yuksek kac doku
VARSAYILAN_ADAY_UST = 400  # olgu basina en fazla kac varyant sorulsun
ISCI = 4                   # es zamanli Atlas sorgusu

OZET_SUTUNLAR = ["key", "krom", "poz", "ref", "alt", "gene", "hgvsc", "hgvsp", "consequence",
                 "kaynak", "durum", "kategori", "avi", "avi_yorum", "avi_katki",
                 "en_yuksek_kantil", "en_yuksek_modalite", "splicing_birlesik"]
for _ad, _kisa, _ in MODALITELER:
    OZET_SUTUNLAR += ["%s_ham" % _kisa, "%s_kantil" % _kisa, "%s_doku" % _kisa, "%s_gen" % _kisa]
OZET_SUTUNLAR += ["yorum"]

DETAY_SUTUNLAR = ["key", "gene", "skor", "gen_ag", "doku", "ontoloji", "ham", "kantil"]


# --------------------------------------------------------------------------
# ortam / yardimci
# --------------------------------------------------------------------------

def env(name):
    """os.environ, yoksa Windows kullanici kayit defteri (setx sonrasi yeniden
    baslatma gerekmesin diye). genomize_seq.env ile ayni davranis."""
    v = os.environ.get(name)
    if v:
        return v
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0] or None
    except (ImportError, OSError):
        return None


def api_key():
    """ALPHAGENOME_API_KEY ortam degiskeni; yoksa ~/.alphagenome_api_key dosyasi
    (Mac'te cift tiklanan .command dosyasi ~/.zshrc'yi gormez)."""
    k = (env("ALPHAGENOME_API_KEY") or "").strip()
    if k:
        return k
    yol = os.path.join(os.path.expanduser("~"), ".alphagenome_api_key")
    try:
        with open(yol, encoding="utf-8") as f:
            k = f.read().strip()
    except OSError:
        k = ""
    return k or None


def log(msg):
    sys.stderr.write("  AG: %s\n" % msg)


_KROM_RE = re.compile(r"^(chr)?([0-9]{1,2}|X|Y|M|MT)$", re.I)


def varyant_ayristir(key):
    """'krom:poz:ref:alt' -> (chrom, pos, ref, alt) ya da None (sorulamaz)."""
    if not key:
        return None
    p = str(key).strip().split(":")
    if len(p) != 4:
        return None
    krom, poz, ref, alt = p
    m = _KROM_RE.match(krom.strip())
    if not m:
        return None
    k = m.group(2).upper()
    if k in ("M", "MT"):
        return None                       # mitokondriyal genom Atlas'ta yok
    try:
        poz = int(float(poz))
    except (TypeError, ValueError):
        return None
    ref, alt = ref.strip().upper(), alt.strip().upper()
    if not ref or not alt or ref == alt:
        return None
    if not re.match(r"^[ACGT]+$", ref) or not re.match(r"^[ACGT]+$", alt):
        return None                       # N, '-', '*' vb. sorulamaz
    if len(ref) > 50 or len(alt) > 50:
        return None                       # buyuk indel / SV kapsam disi
    return "chr" + k, poz, ref, alt


def _hg38(genome):
    g = (genome or "hg38").lower()
    return g in ("hg38", "grch38")


def _yuvarla(x, n=3):
    """float'a cevirip yuvarla; None/NaN/inf -> None (CSV'ye 'nan' sizmasin)."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return round(f, n)


def avi_yorumla(avi):
    """PHRED -> Turkce okunus. PHRED p: en yuksek 10^(-p/10) dilimi."""
    if avi is None:
        return None
    try:
        p = float(avi)
    except (TypeError, ValueError):
        return None
    oran = 10 ** (-p / 10.0) * 100
    if oran >= 1:
        dilim = "en yuksek ~%%%.0f" % oran
    elif oran >= 0.1:
        dilim = "en yuksek ~%%%.1f" % oran
    else:
        dilim = "en yuksek ~%%%.2f" % oran
    if p >= 45:
        s = "cok yuksek (protein/splicing etkisi duzeyi)"
    elif p >= AVI_YUKSEK:
        s = "yuksek"
    elif p >= AVI_ORTA:
        s = "orta (duzenleyici bolge duzeyi olabilir)"
    else:
        s = "dusuk"
    return "PHRED %.1f, %s - %s" % (p, dilim, s)


# --------------------------------------------------------------------------
# onbellek
# --------------------------------------------------------------------------

class Onbellek(object):
    """Varyant basina JSON dosyasi; anahtar = key + skor seti."""

    def __init__(self, klasor):
        self.klasor = klasor
        if klasor:
            os.makedirs(klasor, exist_ok=True)

    def _yol(self, key, etiket):
        h = hashlib.sha1(("%s|%s" % (key, etiket)).encode("utf-8")).hexdigest()[:20]
        return os.path.join(self.klasor, h + ".json")

    def al(self, key, etiket):
        if not self.klasor:
            return None
        y = self._yol(key, etiket)
        if not os.path.exists(y):
            return None
        try:
            with open(y, encoding="utf-8") as f:
                d = json.load(f)
            return d if d.get("surum") == SURUM else None
        except (OSError, ValueError):
            return None

    def yaz(self, key, etiket, veri):
        if not self.klasor:
            return
        veri = dict(veri, surum=SURUM, key=key, etiket=etiket)
        with open(self._yol(key, etiket), "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False)


# --------------------------------------------------------------------------
# Atlas istemcisi
# --------------------------------------------------------------------------

def _bulunamadi_mi(e):
    """atlas.handle_rpc_error NOT_FOUND -> ValueError(from grpc.Call), OUT_OF_RANGE -> IndexError.
    gRPC kodunu __cause__ uzerinden oku; kutuphane kaynakli ValueError'lar hata sayilir."""
    if isinstance(e, IndexError):
        return True
    c = getattr(e, "__cause__", None)
    kod = getattr(c, "code", None)
    try:
        kod = kod() if callable(kod) else kod
    except Exception:
        kod = None
    ad = getattr(kod, "name", None) or (str(kod) if kod is not None else "")
    if ad.endswith("NOT_FOUND") or ad.endswith("OUT_OF_RANGE"):
        return True
    return c is None and "not found" in str(e).lower()


class AtlasSorgu(object):
    """alphagenome.atlas uzerinden sorgu; skor metaverisi bir kez cekilir."""

    def __init__(self, key=None, skorlar=None, doku=None, model=False, model_max=25):
        self.key = key or api_key()
        self.istenen = skorlar            # None -> otomatik secim
        self.doku = [d for d in (doku or []) if d]
        self.model_ac = model
        self.model_max = model_max
        self._client = None
        self._meta = None
        self._model = None
        self._model_sayac = 0
        self._kilit = threading.Lock()
        self.skor_adlari = []
        self.hatalar = []
        self.paket_surum = None
        self.avi_ad = None
        self.katki_ad = None

    # -- baglanti -----------------------------------------------------------
    def baglan(self):
        if self._client is not None:
            return self._client
        if not self.key:
            raise RuntimeError("ALPHAGENOME_API_KEY tanimli degil")
        try:
            import alphagenome
            from alphagenome.atlas import atlas
        except ImportError as e:
            raise RuntimeError("alphagenome paketi kurulu degil (pip install alphagenome): %s" % e)
        self.paket_surum = getattr(alphagenome, "__version__", "?")
        self._client = atlas.create(self.key, timeout=60)
        return self._client

    def meta(self):
        """{skor adi: ScorerMetadata}; tek RPC, sonra onbellekten."""
        if self._meta is None:
            c = self.baglan()
            self._meta = c.scorer_metadata()
            self.skor_adlari = sorted(self._meta.keys())
            # query_variants her cagrida scorer_metadata() cekiyor; varyant
            # basina ~MB'larca metaveri inmesin diye bellekten ver.
            # Her cagrida kopya: query_variants var.index'i yerinde degistiriyor,
            # es zamanli is parcaciklari ayni DataFrame'i paylasmasin.
            import dataclasses
            meta = self._meta

            def _kopya():
                return {k: dataclasses.replace(m, track_metadata=m.track_metadata.copy())
                        for k, m in meta.items()}
            c.scorer_metadata = _kopya
        return self._meta

    def secili_skorlar(self):
        """Sorulacak skor adlari: istenenler, yoksa modaliteler + AVI benzerleri."""
        adlar = set(self.meta().keys())
        if self.istenen:
            sec = [s for s in self.istenen if s in adlar]
            eksik = [s for s in self.istenen if s not in adlar]
            if eksik:
                log("sunucuda olmayan skor(lar) atlandi: %s" % ", ".join(eksik))
            return sec
        sec = [ad for ad, _, _ in MODALITELER if ad in adlar]
        # AVI ve ozellik katkilari: ad sunucuya gore degisebilir, desenle sec.
        for ad in sorted(adlar):
            u = ad.upper()
            if ad not in sec and ("AVI" in u or "VARIANT_IMPACT" in u):
                sec.append(ad)
        return sec

    def avi_adlari(self, secili):
        avi, katki = None, None
        for ad in secili:
            u = ad.upper()
            if "AVI" not in u and "VARIANT_IMPACT" not in u:
                continue
            m = self.meta().get(ad)
            n = len(m.track_metadata) if m is not None and m.track_metadata is not None else 0
            if any(k in u for k in ("SHAP", "ATTRIB", "KATKI", "FEATURE", "CONTRIB")):
                katki = katki or ad
            elif avi is None:
                avi = ad
            elif n > 1 and katki is None:
                katki = ad
        if avi is None:
            log("UYARI: sunucu skor listesinde AVI skoru bulunamadi; yalniz modalite skorlari alinacak")
        return avi, katki

    # -- sorgu ------------------------------------------------------------
    def _atlas_tek(self, v):
        from alphagenome.data import genome
        c = self.baglan()
        var = genome.Variant(chromosome=v[0], position=v[1], reference_bases=v[2], alternate_bases=v[3])
        return c.query_variants([var], requested_scorers=self._secili, progress_bar=False, max_workers=1)

    @staticmethod
    def _model_araligi(var):
        """1 Mb pencere; kromozom basinda negatif baslangic olusursa saga kaydir."""
        from alphagenome.models import dna_client
        aralik = var.reference_interval.resize(dna_client.SEQUENCE_LENGTH_1MB)
        if aralik.start < 0:
            aralik = aralik.shift(-aralik.start)
        return aralik

    def _model_tek(self, v):
        """Atlas'ta olmayan varyant icin canli model (1 Mb pencere)."""
        from alphagenome.data import genome
        from alphagenome.models import dna_client, variant_scorers
        with self._kilit:                      # tek kanal; is parcaciklari ayni istemciyi paylasir
            if self._model is None:
                self._model = dna_client.create(self.key, timeout=60)
        var = genome.Variant(chromosome=v[0], position=v[1], reference_bases=v[2], alternate_bases=v[3])
        aralik = self._model_araligi(var)
        adlar = [ad for ad, _, _ in MODALITELER if ad in variant_scorers.RECOMMENDED_VARIANT_SCORERS]
        sk = [variant_scorers.RECOMMENDED_VARIANT_SCORERS[ad] for ad in adlar]
        cikti = self._model.score_variant(interval=aralik, variant=var, variant_scorers=sk)
        # score_variant istenen sirayla bir AnnData listesi dondurur.
        return dict(zip(adlar, cikti))

    def sorgula(self, adaylar, onbellek=None, ilerleme=None):
        """adaylar: [{'key':..., 'gene':..., ...}] -> (ozet satirlari, detay satirlari)."""
        self._secili = self.secili_skorlar()
        avi_ad, katki_ad = self.avi_adlari(self._secili)
        self.avi_ad, self.katki_ad = avi_ad, katki_ad
        etiket = "atlas:%s|doku:%s|model:%d" % (",".join(self._secili), ",".join(self.doku), int(self.model_ac))
        ozet, detay = [], []
        isler = {}
        with ThreadPoolExecutor(max_workers=ISCI) as ex:
            for a in adaylar:
                v = varyant_ayristir(a.get("key"))
                if v is None:
                    ozet.append(self._satir(a, None, durum="sorulamadi", not_="key ayristirilamadi ya da kapsam disi"))
                    continue
                c = onbellek.al(a["key"], etiket) if onbellek else None
                if c:
                    ozet.append(self._satir(a, c.get("ozet"), durum=c.get("durum"), not_=c.get("not")))
                    detay.extend(c.get("detay") or [])
                    continue
                isler[ex.submit(self._sorgu_guvenli, v)] = (a, v)
            for n, fut in enumerate(as_completed(isler), 1):
                a, v = isler[fut]
                durum, sonuc, not_ = fut.result()
                oz, det = None, []
                if sonuc is not None:
                    try:
                        oz, det = self._ozetle(a["key"], sonuc, avi_ad, katki_ad, durum)
                    except Exception as e:      # beklenmedik cikti bicimi toplu isi durdurmasin
                        self.hatalar.append("ozetleme %s: %s" % (type(e).__name__, str(e)[:160]))
                        durum, not_ = "hata", "ozetleme: %s: %s" % (type(e).__name__, str(e)[:120])
                        oz, det = None, []
                for d in det:
                    d["gene"] = a.get("gene")
                # Yalniz kalici sonuclar onbellege girer: gecici hata / yetki / kota
                # sorunlari ve model kapaliyken "bulunamadi" bir sonraki calismada
                # yeniden denenmeli.
                kalici = durum in ("atlas", "model") or (durum == "bulunamadi" and not self.model_ac)
                if onbellek and kalici:
                    onbellek.yaz(a["key"], etiket, {"durum": durum, "not": not_, "ozet": oz, "detay": det})
                ozet.append(self._satir(a, oz, durum=durum, not_=not_))
                detay.extend(det)
                if ilerleme and (n % 25 == 0 or n == len(isler)):
                    ilerleme(n, len(isler))
        # Girdi sirasini koru (as_completed karistirir).
        sira = {a["key"]: i for i, a in enumerate(adaylar)}
        ozet.sort(key=lambda r: sira.get(r["key"], 1e9))
        return ozet, detay

    def _sorgu_guvenli(self, v):
        """(durum, {skor: AnnData} | None, not). Hatalar toplu isi durdurmaz."""
        try:
            s = self._atlas_tek(v)
            if s and any(getattr(a, "n_obs", 0) > 0 for a in s.values()):
                return "atlas", s, None
            durum, not_ = "bulunamadi", "Atlas'ta kayit yok"
        except (ValueError, IndexError) as e:
            # handle_rpc_error: NOT_FOUND/INVALID_ARGUMENT -> ValueError, OUT_OF_RANGE -> IndexError.
            # Yalniz NOT_FOUND/OUT_OF_RANGE "kayit yok"tur; digerleri (gecersiz filtre,
            # kutuphane hatasi) gercek hatadir ve sessizce negatif sonuca donusmemeli.
            if not _bulunamadi_mi(e):
                self.hatalar.append("%s: %s" % (type(e).__name__, str(e)[:160]))
                return "hata", None, "Atlas: %s: %s" % (type(e).__name__, str(e)[:120])
            durum, not_ = "bulunamadi", "Atlas'ta kayit yok"
        except PermissionError as e:
            self.hatalar.append("yetki: %s" % e)
            return "hata", None, "API anahtari reddedildi: %s" % str(e)[:120]
        except Exception as e:                     # zaman asimi, ag, protokol
            self.hatalar.append("%s: %s" % (type(e).__name__, str(e)[:160]))
            return "hata", None, "%s: %s" % (type(e).__name__, str(e)[:120])
        with self._kilit:
            model_dene = self.model_ac and self._model_sayac < self.model_max
            if model_dene:
                self._model_sayac += 1
        if model_dene:
            try:
                s = self._model_tek(v)
                return "model", s, "Atlas'ta yok; canli AlphaGenome modeli (1 Mb) ile skorlandi"
            except Exception as e:
                self.hatalar.append("model %s: %s" % (type(e).__name__, str(e)[:160]))
                return "hata", None, "model: %s: %s" % (type(e).__name__, str(e)[:120])
        return durum, None, not_

    # -- ozetleme ---------------------------------------------------------
    def _ozetle(self, key, sonuc, avi_ad, katki_ad, durum):
        """{skor: AnnData} -> (ozet dict, detay satirlari)."""
        import numpy as np
        oz, det = {}, []
        genel = []                       # (|kantil|, modalite)
        hammax = {}                      # kisa ad -> max |ham| (birlesik splicing icin)
        for ad, a in sonuc.items():
            X = np.asarray(a.X, dtype=float)
            if X.size == 0:
                continue
            q = a.layers["quantiles"] if "quantiles" in a.layers else None
            q = np.asarray(q, dtype=float) if q is not None else None
            var = a.var
            obs = a.obs
            doku_ad = self._doku_adlari(var)
            gen_ad = list(obs["gene_name"]) if "gene_name" in obs else [None] * X.shape[0]
            onto = list(var["ontology_curie"]) if "ontology_curie" in var else [None] * X.shape[1]

            if ad == avi_ad:
                if np.isfinite(X).any():
                    oz["avi"] = _yuvarla(np.nanmax(X), 1)
                continue
            if ad == katki_ad:
                oz["avi_katki"] = self._katki_ozet(X, doku_ad)
                continue

            # doku filtresi (istenmisse) yalnizca ozet degerleri etkiler
            sut = list(range(X.shape[1]))
            if self.doku and any(o for o in onto):
                sut = [j for j in sut if onto[j] in self.doku] or sut

            Xs = X[:, sut]
            qs = q[:, sut] if q is not None else None
            if Xs.size == 0 or not np.isfinite(Xs).any():
                continue
            i, j = np.unravel_index(np.nanargmax(np.abs(Xs)), Xs.shape)
            ham_max = _yuvarla(Xs[i, j])
            kantil = None
            if qs is not None and np.isfinite(qs).any():
                iq, jq = np.unravel_index(np.nanargmax(np.abs(qs)), qs.shape)
                kantil = _yuvarla(qs[iq, jq], 4)
                i, j = iq, jq            # ham/doku/gen etiketi AYNI hucreden (kantile gore)
            ham = _yuvarla(Xs[i, j])
            kisa = MOD_KISA.get(ad, ad.lower())
            hammax[kisa] = ham_max
            oz["%s_ham" % kisa] = ham
            oz["%s_kantil" % kisa] = kantil
            oz["%s_doku" % kisa] = doku_ad[sut[j]]
            oz["%s_gen" % kisa] = gen_ad[i]
            if ad in MOD_KISA and not ad.endswith("_ACTIVE") and kantil is not None:
                genel.append((abs(kantil), kantil, ad))

            # detay: en yuksek |kantil| (yoksa |ham|) olan N hucre
            skor = qs if (qs is not None and np.isfinite(qs).any()) else Xs
            duz = np.abs(skor).ravel()
            duz = np.where(np.isfinite(duz), duz, -1.0)      # NaN hucreler en sona
            n = min(DETAY_DOKU_N, int((duz >= 0).sum()))
            for idx in np.argpartition(-duz, n - 1)[:n] if n else []:
                ii, jj = np.unravel_index(idx, skor.shape)
                det.append({"key": key, "skor": ad, "gen_ag": gen_ad[ii],
                            "doku": doku_ad[sut[jj]], "ontoloji": onto[sut[jj]],
                            "ham": _yuvarla(Xs[ii, jj]),
                            "kantil": _yuvarla(qs[ii, jj], 4) if qs is not None else None})

        if genel:
            _, kantil, ad = max(genel)
            oz["en_yuksek_kantil"] = kantil
            oz["en_yuksek_modalite"] = ad
        # Birlesik splicing makaledeki gibi gen/doku uzerinden MAX ham degerlerle
        ss = hammax.get("splice_site"); su = hammax.get("splice_usage"); sj = hammax.get("splice_junc")
        if any(x is not None for x in (ss, su, sj)):
            oz["splicing_birlesik"] = _yuvarla(abs(ss or 0) + abs(su or 0) + abs(sj or 0) / 5.0)
        det.sort(key=lambda r: -abs(r["kantil"] if r["kantil"] is not None else (r["ham"] or 0)))
        return oz, det

    @staticmethod
    def _doku_adlari(var):
        """Doku etiketi: biosample_name, bos/NaN ise track adi, o da yoksa indeks."""
        adlar = [str(x) for x in (var["name"] if "name" in var else var.index)]
        if "biosample_name" not in var:
            return adlar
        out = []
        for b, n in zip(var["biosample_name"], adlar):
            s = "" if b is None else str(b).strip()
            out.append(n if s in ("", "nan", "None", "<NA>") else s)
        return out

    @staticmethod
    def _katki_ozet(X, adlar):
        """SHAP katkilari: mutlak degeri en buyuk 3 ozellik 'ad:+deger' bicimi."""
        import numpy as np
        v = np.asarray(X, dtype=float).ravel()
        if v.size != len(adlar):
            adlar = ["ozellik%d" % i for i in range(v.size)]
        sira = np.argsort(-np.abs(v))[:3]
        return "; ".join("%s:%+.2f" % (adlar[i], v[i]) for i in sira if np.isfinite(v[i]))

    # -- satir ------------------------------------------------------------
    def _satir(self, a, oz, durum, not_=None):
        v = varyant_ayristir(a.get("key")) or (None, None, None, None)
        r = {k: None for k in OZET_SUTUNLAR}
        r.update({"key": a.get("key"), "krom": v[0], "poz": v[1], "ref": v[2], "alt": v[3],
                  "gene": a.get("gene"), "hgvsc": a.get("hgvsc"), "hgvsp": a.get("hgvsp"),
                  "consequence": a.get("consequence"), "kaynak": a.get("kaynak"),
                  "durum": durum})
        if oz:
            for k, val in oz.items():
                if k in r:
                    r[k] = val
            r["avi_yorum"] = avi_yorumla(r.get("avi"))
            r["kategori"] = kategori(r)
            r["yorum"] = yorumla(r)
        else:
            r["kategori"] = "-"
            r["yorum"] = not_ or durum
        return r


def kategori(r):
    """yuksek / orta / dusuk - siralama yardimcisi, klinik esik degil."""
    avi = r.get("avi"); q = r.get("en_yuksek_kantil"); sp = r.get("splicing_birlesik")
    q = abs(q) if q is not None else None
    if (avi is not None and avi >= AVI_YUKSEK) or (q is not None and q >= KANTIL_YUKSEK) \
            or (sp is not None and sp >= SPLICE_YUKSEK):
        return "yuksek"
    if (avi is not None and avi >= AVI_ORTA) or (q is not None and q >= KANTIL_ORTA) \
            or (sp is not None and sp >= SPLICE_ORTA):
        return "orta"
    return "dusuk"


LOF_SONUC = ("stop gained", "frameshift", "start lost", "stop lost", "stop_gained",
             "frameshift_variant", "start_lost", "stop_lost")


def lof_mu(consequence):
    c = (consequence or "").lower()
    return any(t in c for t in LOF_SONUC)


def sinyal_anahtari(r):
    """Siralama: kategori, sonra AlphaGenome'a ozgu sinyal (splicing, kantil), sonra AVI.

    Kodlayici LoF varyantlarda AVI zaten yuksektir; tabloyu gercek splicing /
    duzenleyici sinyali olan varyantlar acsin diye AVI en sona konur.
    """
    k = {"yuksek": 0, "orta": 1, "dusuk": 2}.get(r.get("kategori"), 3)
    return (k, -(_sayi(r.get("splicing_birlesik")) or 0), -abs(_sayi(r.get("en_yuksek_kantil")) or 0),
            -(_sayi(r.get("avi")) or 0))


def yorumla(r):
    """Satirdan kisa Turkce yorum (rapor tablosunun son sutunu)."""
    p = []
    if r.get("avi") is not None:
        p.append("AVI %s" % r["avi_yorum"])
    sp = r.get("splicing_birlesik")
    if sp is not None:
        if sp >= SPLICE_YUKSEK:
            p.append("splicing etkisi guclu (birlesik %.2f)" % sp)
        elif sp >= SPLICE_ORTA:
            p.append("olasi splicing etkisi (birlesik %.2f)" % sp)
        else:
            p.append("splicing etkisi ongorulmuyor (birlesik %.2f)" % sp)
    ek = r.get("ekspresyon_kantil")
    if ek is not None and abs(ek) >= KANTIL_ORTA:
        yon = "azalma" if ek < 0 else "artis"
        g = r.get("ekspresyon_gen") or r.get("gene") or ""
        p.append("%s ekspresyonunda %s (log-FC %s, kantil %s, %s)"
                 % (g, yon, r.get("ekspresyon_ham"), ek, r.get("ekspresyon_doku")))
    for kisa, ad in (("atac", "ATAC"), ("dnase", "DNase"), ("tf", "TF baglanma"),
                     ("histon", "histon"), ("cage", "CAGE"), ("procap", "PRO-cap"),
                     ("polyA", "poliadenilasyon"), ("kontakt", "kontakt")):
        q = r.get("%s_kantil" % kisa)
        if q is not None and abs(q) >= KANTIL_YUKSEK:
            p.append("%s kantil %s (%s)" % (ad, q, r.get("%s_doku" % kisa)))
    if r.get("avi_katki"):
        p.append("AVI katki: %s" % r["avi_katki"])
    if lof_mu(r.get("consequence")) and (r.get("avi") or 0) >= AVI_YUKSEK:
        p.append("LoF varyantinda yuksek AVI beklenen bulgudur, ek bilgi degildir")
    if not p:
        p.append("belirgin duzenleyici/splicing etkisi ongorulmuyor")
    return "; ".join(p)


# --------------------------------------------------------------------------
# aday toplama ve dosya islemleri
# --------------------------------------------------------------------------

# Olgu klasorundeki eksen CSV'leri (oncelik sirasi). rutin.py'nin yazdigi
# de novo / trio dosyalari da 'key' sutunu tasidigi surece toplanir.
EKSEN_ONCELIK = ["de_novo", "denovo", "tier", "clinvar_patojenik", "nadir_lof",
                 "homozigot_nadir", "fenotip_iliskili", "hedef", "ortak_"]


def _oncelik(dosya):
    ad = os.path.basename(dosya).lower()
    for i, e in enumerate(EKSEN_ONCELIK):
        if e in ad:
            return i
    return len(EKSEN_ONCELIK)


def _aday_dosyasi(dosya):
    a = os.path.basename(dosya).lower()
    return (a.endswith(".csv") and "artefakt" not in a and "_cnv" not in a
            and not a.startswith("cnv") and not a.startswith("alphagenome"))


def csv_oku(yol):
    with open(yol, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _sayi(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def adaylari_topla(klasor, ust=VARSAYILAN_ADAY_UST, dosyalar=None, max_af=0.02, max_ic=0.02):
    """Klasordeki (ARTEFAKT olmayan) CSV'lerden 'key' sutunlu satirlari topla.

    max_af: populasyon frekansi (af_max) bu degerin ustundeki varyantlar atlanir
    (yaygin varyantta duzenleyici skor klinik soru degildir); frekansi
    bilinmeyenler tutulur. max_ic: dahili kohort frekansi esigi (artefakt).
    """
    if dosyalar is None:
        dosyalar = [os.path.join(klasor, d) for d in os.listdir(klasor)]
    # Artefakt, CNV ve kendi ciktilarimiz hicbir kosulda aday kaynagi degildir.
    dosyalar = [d for d in dosyalar if _aday_dosyasi(d)]
    dosyalar = sorted(dosyalar, key=_oncelik)
    gorulen, out = {}, []
    for d in dosyalar:
        try:
            satirlar = csv_oku(d)
        except OSError:
            continue
        kaynak = os.path.splitext(os.path.basename(d))[0]
        for r in satirlar:
            k = (r.get("key") or "").strip()
            if not k:
                continue
            nk = varyant_ayristir(k) or k        # '12:..' ve 'chr12:..' ayni varyant
            af = _sayi(r.get("af_max"))
            if max_af is not None and af is not None and af > max_af:
                continue
            ic = _sayi(r.get("internal_freq"))
            if max_ic is not None and ic is not None and ic >= max_ic:
                continue
            if nk in gorulen:
                g = gorulen[nk]
                if kaynak not in g["kaynak"].split(","):
                    g["kaynak"] += "," + kaynak
                for alan in ("gene", "hgvsc", "hgvsp", "consequence"):   # eksik alani sonrakinden doldur
                    if not g.get(alan) and r.get(alan):
                        g[alan] = r.get(alan)
                continue
            a = {"key": k, "gene": r.get("gene"), "hgvsc": r.get("hgvsc"), "hgvsp": r.get("hgvsp"),
                 "consequence": r.get("consequence"), "kaynak": kaynak}
            gorulen[nk] = a
            out.append(a)
    if len(out) > ust:
        log("aday sayisi %d > %d; ilk %d (oncelik sirasina gore) sorulacak" % (len(out), ust, ust))
        out = out[:ust]
    return out


def yaz_csv(yol, satirlar, sutunlar):
    with open(yol, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=sutunlar, extrasaction="ignore")
        w.writeheader()
        for r in satirlar:
            w.writerow(r)
    return yol


def onbellek_klasoru(olgu_klasoru):
    """_sistem/alphagenome_onbellek: rutin dizininde; bulunamazsa olgu klasoru."""
    burasi = os.path.dirname(os.path.abspath(__file__))
    for aday in (os.path.join(burasi, "alphagenome_onbellek"),
                 os.path.join(olgu_klasoru or ".", "_alphagenome_onbellek")):
        try:
            os.makedirs(aday, exist_ok=True)
            return aday
        except OSError:
            continue
    return None


def calistir(olgu_klasoru, adaylar=None, genome="hg38", doku=None, model=True, model_max=25,
             ust=VARSAYILAN_ADAY_UST, skorlar=None, onbellek=True, sessiz=False):
    """Ana giris: olgu klasorune alphagenome.csv / _detay.csv / _ozet.json yazar.

    Donus: ozet sozlugu (durum, sayimlar, hata) - rutin.py rapor metnine kullanir.
    Hicbir kosulda istisna firlatmaz; adim atlandiysa 'durum' bunu soyler.
    """
    t0 = time.time()
    ozet = {"surum": SURUM, "durum": "atlandi", "neden": None, "aday": 0, "atlas": 0,
            "model": 0, "bulunamadi": 0, "hata": 0, "sorulamadi": 0, "skorlar": [],
            "kategori": {"yuksek": 0, "orta": 0, "dusuk": 0}, "paket": None, "sure_sn": 0,
            "doku": list(doku or []), "hatalar": []}
    yol_json = os.path.join(olgu_klasoru, "alphagenome_ozet.json")

    def bitir():
        ozet["sure_sn"] = round(time.time() - t0, 1)
        try:
            with open(yol_json, "w", encoding="utf-8") as f:
                json.dump(ozet, f, indent=1, ensure_ascii=False)
        except OSError:
            pass
        return ozet

    if not _hg38(genome):
        ozet["neden"] = "referans genom %s; Atlas yalnizca hg38 (liftover yapilmadi)" % genome
        return bitir()
    if not api_key():
        ozet["neden"] = "ALPHAGENOME_API_KEY tanimli degil (setx ALPHAGENOME_API_KEY ...)"
        return bitir()
    import importlib.util
    if importlib.util.find_spec("alphagenome") is None:
        ozet["neden"] = "alphagenome paketi kurulu degil (pip install alphagenome)"
        return bitir()

    try:
        if adaylar is None:
            adaylar = adaylari_topla(olgu_klasoru, ust=ust)
        ozet["aday"] = len(adaylar)
        if not adaylar:
            ozet["durum"] = "tamam"
            ozet["neden"] = "sorulacak aday varyant yok"
            return bitir()

        skor_listesi = skorlar or [s.strip() for s in (env("ALPHAGENOME_SKORLAR") or "").split(",") if s.strip()]
        sorgu = AtlasSorgu(skorlar=skor_listesi or None, doku=doku, model=model, model_max=model_max)
        try:
            sorgu.meta()
        except Exception as e:
            ozet["durum"] = "hata"
            ozet["neden"] = "Atlas'a baglanilamadi: %s: %s" % (type(e).__name__, str(e)[:200])
            ozet["hatalar"] = [ozet["neden"]]
            return bitir()
        ozet["paket"] = sorgu.paket_surum
        ozet["skorlar"] = sorgu.secili_skorlar()
        ozet["sunucu_skorlari"] = sorgu.skor_adlari

        ob = Onbellek(onbellek_klasoru(olgu_klasoru)) if onbellek else None
        if not sessiz:
            log("%d aday varyant Atlas'a soruluyor (%d skor)" % (len(adaylar), len(ozet["skorlar"])))
        satirlar, detay = sorgu.sorgula(
            adaylar, onbellek=ob,
            ilerleme=None if sessiz else (lambda n, t: log("  %d/%d" % (n, t))))

        for r in satirlar:
            d = r.get("durum")
            if d in ("atlas", "model", "bulunamadi", "hata", "sorulamadi"):
                ozet[d] += 1
            if r.get("kategori") in ozet["kategori"]:
                ozet["kategori"][r["kategori"]] += 1
        ozet["hatalar"] = sorgu.hatalar[:20]
        ozet["avi_skoru"] = sorgu.avi_ad
        ozet["katki_skoru"] = sorgu.katki_ad
        ozet["durum"] = "tamam" if (ozet["atlas"] + ozet["model"]) > 0 else ("hata" if ozet["hata"] else "tamam")
        if ozet["durum"] == "hata":
            ozet["neden"] = "hicbir varyant skorlanamadi; ilk hata: %s" % (sorgu.hatalar[0] if sorgu.hatalar else "?")
        elif ozet["atlas"] + ozet["model"] == 0 and ozet["bulunamadi"] > 0:
            ozet["uyari"] = ("hicbir aday varyant Atlas'ta bulunamadi (%d); genom surumu, key bicimi ve "
                             "skor adlari (sunucu_skorlari) kontrol edilmeli" % ozet["bulunamadi"])
            log("UYARI: " + ozet["uyari"])
        if sorgu.avi_ad is None:
            ozet.setdefault("uyari", "AVI skoru sunucu skor listesinde bulunamadi; yalniz modalite skorlari alindi")

        # Siralama: kategori, sonra AlphaGenome'a ozgu sinyal (splicing/kantil), sonra AVI
        satirlar.sort(key=sinyal_anahtari)
        ozet["dosya"] = yaz_csv(os.path.join(olgu_klasoru, "alphagenome.csv"), satirlar, OZET_SUTUNLAR)
        ozet["detay_dosya"] = yaz_csv(os.path.join(olgu_klasoru, "alphagenome_detay.csv"),
                                      detay, DETAY_SUTUNLAR)
        ozet["yuksek_varyantlar"] = [
            {"key": r["key"], "gene": r["gene"], "avi": r["avi"], "kategori": r["kategori"], "yorum": r["yorum"]}
            for r in satirlar if r.get("kategori") == "yuksek"][:30]
        try:
            ozet["rapor_dosya"] = rapor_dosyasi_yaz(olgu_klasoru, ozet, satirlar)
        except OSError as e:
            ozet["hatalar"].append("rapor metni yazilamadi: %s" % e)
        return bitir()
    except Exception as e:                    # hicbir kosulda istisna firlatma (rutin.py'ye soz)
        ozet["durum"] = "hata"
        ozet["neden"] = "AlphaGenome adimi beklenmedik hata: %s: %s" % (type(e).__name__, str(e)[:200])
        ozet.setdefault("hatalar", []).append(ozet["neden"])
        return bitir()


def _fmt(v, n=2):
    if v is None or v == "":
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return ("%%.%df" % n % f).replace(".", ",")


KAYNAKCA = [
    "Avsec Ž, Latysheva N, Cheng J, ve ark. Advancing regulatory variant effect prediction with "
    "AlphaGenome. Nature. 2026;649(8099):1206-1218. doi:10.1038/s41586-025-10014-0",
    "Cheng J, Taylor KR, Nicolaisen L, ve ark. AlphaGenome Atlas: in silico mutagenesis of the entire "
    "human genome improves prioritization and interpretation of non-coding variants. 2026 (ön baskı; "
    "https://alphagenome.google/atlas)",
]


def _sayim_cumlesi(ozet):
    """Atlas / canlı model / skorlanamayan sayımları (durum sayaçları birbirini dışlar)."""
    atlas = ozet.get("atlas", 0) or 0
    model = ozet.get("model", 0) or 0
    yok = (ozet.get("bulunamadi", 0) or 0) + (ozet.get("hata", 0) or 0) + (ozet.get("sorulamadi", 0) or 0)
    p = ["%d varyant Atlas'ta önhesaplanmış olarak bulunmuştur" % atlas]
    if model:
        p.append("Atlas'ta bulunmayan %d varyant canlı AlphaGenome modeliyle (1 Mb pencere; AVI skoru yok) "
                 "skorlanmıştır" % model)
    if yok:
        p.append("%d varyant skorlanamamıştır (Atlas'ta yok, hata ya da kapsam dışı)" % yok)
    return "; ".join(p) + "."


def rapor_metni(ozet, satirlar, en_fazla=15):
    """alphagenome_ozet.json + alphagenome.csv -> raporlara girecek Türkçe metin.

    Üç blok döner: (1) kapsamlı analiz raporu bölümü (tablo + yorum + sınır),
    (2) resmi/sonuç raporu için tek paragraflık yöntem cümlesi, (3) kaynakça.
    Claude (rapor yazan) bu metni olduğu gibi ya da düzenleyerek kullanır.
    """
    ozet = ozet or {}
    durum = ozet.get("durum")
    b = []
    b.append("ALPHAGENOME ATLAS DEĞERLENDİRMESİ (araştırma amaçlı; klinik karar için tek başına kullanılmaz)")
    b.append("")
    if durum != "tamam" or not satirlar:
        neden = ozet.get("neden") or "sorgu yapılamadı"
        b.append("AlphaGenome Atlas sorgusu bu olguda çalıştırılamadı: %s. Aşağıdaki değerlendirme "
                 "yalnızca standart açıklama ve tahmin araçlarına (REVEL, SpliceAI vb.) dayanır." % neden)
        return "\n".join(b), "", KAYNAKCA
    n = ozet.get("aday", 0)
    kat = ozet.get("kategori") or {}
    avi_var = bool(ozet.get("avi_skoru", True))     # eski ozet.json'larda alan yok -> var say
    avi_cumle = ("AVI (AlphaGenome Variant Impact) PHRED skoru (10 = tüm SNV'lerin en yüksek %10'u, "
                 "20 = en yüksek %1'i, 30 = en yüksek %0,1'i), " if avi_var else "")
    b.append("Yöntem: Aday varyantlar (%d) Google DeepMind AlphaGenome Atlas'a (önhesaplanmış in silico "
             "doygunluk mutagenezi, GRCh38; alphagenome %s) sorulmuştur. Her varyant için %s"
             "modalite bazlı etki skorları (gen ekspresyonu, splice site / "
             "splice site kullanımı / splice junction, poliadenilasyon, kromatin erişilebilirliği, TF ve "
             "histon bağlanması, TSS aktivitesi, 3B kontakt) ve bunların yaygın varyant arka planına göre "
             "kalibre kantil değerleri (|0,99| = arka planın en uç %%1'i) alınmıştır. Birleşik splicing skoru "
             "= max(splice site) + max(splice site kullanımı) + max(splice junction)/5; >1,0 genellikle "
             "büyük etki. %s"
             % (n, ozet.get("paket") or "?", avi_cumle, _sayim_cumlesi(ozet)))
    b.append("")
    if ozet.get("uyari"):
        b.append("Uyarı: %s." % ozet["uyari"])
        b.append("")
    b.append("Özet: yüksek etki kategorisi %d, orta %d, düşük %d varyant. Kategoriler sıralama yardımcısıdır "
             "(AVI ≥ 20 veya |kantil| ≥ 0,99 veya birleşik splicing ≥ 1,0 → yüksek; AVI ≥ 10 / |kantil| ≥ 0,95 / "
             "splicing ≥ 0,5 → orta); makale sabit eşik yerine bölgeye/uygulamaya duyarlı sıralama önerir."
             % (kat.get("yuksek", 0), kat.get("orta", 0), kat.get("dusuk", 0)))
    b.append("")
    secilen = sorted([r for r in satirlar if r.get("kategori") in ("yuksek", "orta")],
                     key=sinyal_anahtari)[:en_fazla]
    if secilen:
        b.append("Öne çıkan varyantlar (AlphaGenome):")
        b.append("Gen | Varyant | Kaynak | AVI (PHRED) | En yüksek kantil (modalite) | Birleşik splicing | "
                 "Ekspresyon log-FC (doku) | Kategori | Yorum")
        for r in secilen:
            var = r.get("hgvsc") or r.get("key")
            if r.get("hgvsp"):
                var = "%s %s" % (var, r["hgvsp"])
            b.append(" | ".join([
                r.get("gene") or "-", var or "-", (r.get("kaynak") or "-").replace(",", ", "),
                _fmt(r.get("avi"), 1),
                "%s (%s)" % (_fmt(r.get("en_yuksek_kantil"), 4), r.get("en_yuksek_modalite") or "-"),
                _fmt(r.get("splicing_birlesik"), 2),
                "%s (%s)" % (_fmt(r.get("ekspresyon_ham"), 2), r.get("ekspresyon_doku") or "-"),
                r.get("kategori") or "-", r.get("yorum") or ""]))
        b.append("")
    else:
        b.append("Sorgulanan aday varyantların hiçbiri AlphaGenome'da yüksek ya da orta etki kategorisine "
                 "girmemiştir; bu, kodlayıcı-olmayan/düzenleyici bir mekanizma lehine ek kanıt bulunmadığı "
                 "anlamına gelir (bir genetik nedeni dışlamaz).")
        b.append("")
    b.append("Tablo, AlphaGenome'a özgü sinyali (splicing, kantil) yüksek olan varyantları öne alır; "
             "kodlayıcı LoF (stop-gain/frameshift) varyantlarında yüksek AVI protein kesilmesinden beklenen "
             "bir bulgudur ve tek başına ek bilgi taşımaz.")
    b.append("")
    b.append("Yorumlama ilkeleri: (i) Yüksek AVI ve güçlü splicing/ekspresyon sinyali olan bir varyant, "
             "fenotiple uyumlu bir gende ise öncelik kazanır ve RNA düzeyinde doğrulama (RT-PCR / RNA-seq) "
             "önerilir; (ii) AlphaGenome skorları ACMG/AMP çerçevesinde PP3/BP4 kanıtı yerine geçmez, "
             "kalibre edilmiş araçlarla (REVEL, SpliceAI) birlikte ve ikincil olarak değerlendirilir; "
             "(iii) düşük skor bir varyantı dışlamaz (özellikle kodlayıcı missense etkisi AlphaMissense/REVEL "
             "ile değerlendirilir); (iv) sonuçlar ticari olmayan araştırma kullanımı koşullarına tabidir ve "
             "tek başına klinik karar vermek için kullanılamaz.")
    b.append("")
    b.append("Ayrıntılı tablolar: kanit/alphagenome.csv (varyant başına özet), kanit/alphagenome_detay.csv "
             "(doku/gen bazlı en yüksek skorlar).")
    yontem = ("Aday varyantların düzenleyici ve splicing etkileri Google DeepMind AlphaGenome Atlas "
              "(AVI skoru ve modalite bazlı kalibre kantil skorları; Avsec ve ark. 2026, Cheng ve ark. 2026) "
              "ile ayrıca değerlendirilmiştir. Bu skorlar araştırma amaçlı hesaplamalı öngörülerdir; ACMG/AMP "
              "sınıflandırmasında yalnızca destekleyici bağlamda kullanılmış, tek başına klinik karar için "
              "kullanılmamıştır.")
    return "\n".join(b), yontem, KAYNAKCA


def rapor_dosyasi_yaz(olgu_klasoru, ozet, satirlar):
    """kanit/alphagenome_rapor.txt: rapor yazan (Claude) için hazır Türkçe bloklar."""
    bolum, yontem, kaynakca = rapor_metni(ozet, satirlar)
    yol = os.path.join(olgu_klasoru, "alphagenome_rapor.txt")
    with open(yol, "w", encoding="utf-8") as f:
        f.write("### KAPSAMLI ANALİZ RAPORU - bölüm (Öncelikli bulgular / İkincil adaylar bölümünden sonra)\n\n")
        f.write(bolum + "\n\n")
        f.write("### RESMİ VE SONUÇ RAPORU - 'Analiz Yöntemi' paragrafına eklenecek cümle\n\n")
        f.write((yontem or "(AlphaGenome çalıştırılamadı; yöntem cümlesi eklenmez.)") + "\n\n")
        f.write("### KAYNAKÇA\n\n")
        for i, k in enumerate(kaynakca, 1):
            f.write("%d. %s\n" % (i, k))
    return yol


def ozet_oku(olgu_klasoru):
    """rutin.py icin: daha once yazilmis alphagenome_ozet.json + csv satirlari."""
    y = os.path.join(olgu_klasoru, "alphagenome_ozet.json")
    c = os.path.join(olgu_klasoru, "alphagenome.csv")
    oz, satirlar = None, []
    if os.path.exists(y):
        try:
            with open(y, encoding="utf-8") as f:
                oz = json.load(f)
        except (OSError, ValueError):
            oz = None
    if os.path.exists(c):
        try:
            satirlar = csv_oku(c)
        except OSError:
            satirlar = []
    return oz, satirlar


# --------------------------------------------------------------------------
# komut satiri
# --------------------------------------------------------------------------

def _cmd_skorlar():
    s = AtlasSorgu()
    m = s.meta()
    print("alphagenome %s - Atlas skorlari (%d):" % (s.paket_surum, len(m)))
    for ad in sorted(m):
        tm = m[ad].track_metadata
        n = len(tm) if tm is not None else 0
        print("  %-28s isaretli=%-5s doku/ozellik=%d" % (ad, m[ad].is_signed, n))
    print("\nSecilecekler:", ", ".join(s.secili_skorlar()))


def main():
    p = argparse.ArgumentParser(description="AlphaGenome Atlas varyant skorlari")
    p.add_argument("klasor", nargs="?", help="olgu klasoru (eksen CSV'lerinin oldugu yer)")
    p.add_argument("--csv", action="append", help="yalnizca bu CSV'lerdeki key'ler (tekrarlanabilir)")
    p.add_argument("--varyant", action="append", help="tek varyant: chr12:13865958:C:T (tekrarlanabilir)")
    p.add_argument("--genome", default="hg38")
    p.add_argument("--doku", help="virgulle UBERON/CL terimleri (or. UBERON:0000955 beyin)")
    p.add_argument("--skorlar", help="virgulle Atlas skor adlari (varsayilan: otomatik)")
    p.add_argument("--ust", type=int, default=VARSAYILAN_ADAY_UST)
    p.add_argument("--model", dest="model", action="store_true", default=True,
                   help="Atlas'ta olmayanlari canli modelle skorla (varsayilan acik)")
    p.add_argument("--model-yok", dest="model", action="store_false")
    p.add_argument("--model-max", type=int, default=25)
    p.add_argument("--onbellek-yok", dest="onbellek", action="store_false", default=True)
    p.add_argument("--skorlar-listele", dest="listele", action="store_true", help="sunucudaki skor adlari")
    a = p.parse_args()

    if a.listele:
        _cmd_skorlar()
        return
    doku = [d.strip() for d in (a.doku or "").split(",") if d.strip()]
    skorlar = [s.strip() for s in (a.skorlar or "").split(",") if s.strip()]
    if a.varyant:
        # Klasor verilmediyse ciktilar gecici bir klasore yazilir (bulunulan klasor kirletilmez);
        # onbellek yine _sistem/alphagenome_onbellek'tedir.
        gecici = None if a.klasor else tempfile.mkdtemp(prefix="alphagenome_")
        klasor = a.klasor or gecici
        adaylar = [{"key": v, "gene": None, "kaynak": "komut"} for v in a.varyant]
        try:
            oz = calistir(klasor, adaylar=adaylar, genome=a.genome, doku=doku, model=a.model,
                          model_max=a.model_max, skorlar=skorlar, onbellek=a.onbellek)
            _, satirlar = ozet_oku(klasor)
        finally:
            if gecici:
                shutil.rmtree(gecici, ignore_errors=True)
        for r in satirlar:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        gizle = ("yuksek_varyantlar",) + (("dosya", "detay_dosya", "rapor_dosya") if gecici else ())
        print(json.dumps({k: v for k, v in oz.items() if k not in gizle}, ensure_ascii=False, indent=1))
        return
    if not a.klasor:
        p.error("olgu klasoru ya da --varyant gerekli")
    adaylar = adaylari_topla(a.klasor, ust=a.ust, dosyalar=a.csv) if a.csv else None
    oz = calistir(a.klasor, adaylar=adaylar, genome=a.genome, doku=doku, model=a.model,
                  model_max=a.model_max, ust=a.ust, skorlar=skorlar, onbellek=a.onbellek)
    print(json.dumps({k: v for k, v in oz.items() if k != "sunucu_skorlari"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
