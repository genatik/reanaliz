#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ilyome_seq.py - Ilyome (ilyome.com) uzerinden WES/CES veri toplama istemcisi.

genomize_seq.py'nin Ilyome karsiligi. rutin.py her iki platformu da AYNI
arayuzle kullanir (resolve / warmup / dashboard / kapsama / sanity / hpo_search /
run_axes / cnv) ve kanit/ klasorune AYNI sutun duzeninde CSV yazar; boylece
raporu yazan adim (Claude) ve akrabalik.py / alphagenome_sorgu.py degismez.

Ilyome veri modeli (Genomize'dan farki):
  * Ornek  = "sample" (sampleid, run, status). Isitma (warmup) yoktur; ornek
    durumu "Finished" ise sorgulanabilir.
  * Filtre = "search theme" (sunucuda saklanan filtre sablonu). Rutin kendi
    sablonunu (WES_RUTIN) acar, her eksen icin sifirlar ve degerleri PUT ile
    ayarlar; kullanicinin kendi sablonlarina DOKUNMAZ.
  * Varyant listesi: GET samples/<id>/snv/<theme>/?page=..&page_size=..
  * CNV listesi    : GET samples/<id>/cnv/<theme>/?page=..&page_size=..
  * Merkez on-eki  : ilcore / sample-run uclari /api/c/<merkez>/... altindadir.

Kurulum (bir kez):  python3 -m pip install --user requests
Giris bilgisi: ILYOME_USER (e-posta) ve ILYOME_PASS ortam degiskenleri ya da
calisma aninda sorulur; parola HICBIR YERE KAYDEDILMEZ.

Kullanim:
    python ilyome_seq.py kesfet 2308-26-ZBS      # API kesfi: ham yanitlari JSON'a yazar
    python ilyome_seq.py resolve 2308-26-ZBS     # ornegi bul
    python ilyome_seq.py qc 2308-26-ZBS          # kalite/kapsama
    python ilyome_seq.py scan 2308-26-ZBS --hpo HP:0001250 --out ./deneme
    python ilyome_seq.py hpo "seizure"           # HPO terimi ara
"""
from __future__ import print_function

import argparse
import csv
import datetime
import getpass
import json
import os
import re
import sys
import time

import requests

BASE = os.environ.get("ILYOME_BASE", "https://ilyome.com").rstrip("/")
VARSAYILAN_MERKEZ = "general"           # frontend'deki l1 sabiti
TEMA_ADI = os.environ.get("ILYOME_TEMA", "WES_RUTIN")   # rutinin kendi filtre sablonu
SAYFA = int(os.environ.get("ILYOME_SAYFA", "200"))     # sayfa basina kayit

# Merkez on-eki alan uc on-ekleri (frontend: sR dizisi)
MERKEZLI = ("/api/ilcore", "/api/file", "/api/sample-run", "/api/download/shared",
            "/api/upload/", "/api/report-settings", "/api/payment")

# Yikici sonuclar - VEP sequence ontology adlariyla (Ilyome 'consequence' terimleri)
DESTRUCTIVE = ["stop_gained", "frameshift_variant", "splice_donor_variant",
               "splice_acceptor_variant", "start_lost", "stop_lost",
               "inframe_deletion", "inframe_insertion"]
ACMG_PLV = ["Pathogenic", "Likely pathogenic", "Uncertain significance"]
CLINVAR_P = ["Pathogenic", "Likely_pathogenic", "Conflicting"]

# Genomize ile AYNI sutun duzeni (kanit CSV'leri) + Ilyome'a ozgu ek sutunlar.
try:
    from genomize_seq import COLUMNS as _G_COLUMNS, CNV_COLUMNS as _G_CNV_COLUMNS
    from genomize_seq import cnv_hedefte, HEDEF_PENCERE          # noqa: F401
    COLUMNS = list(_G_COLUMNS)
    CNV_COLUMNS = list(_G_CNV_COLUMNS)
except Exception:                                                  # tek basina kullanim
    COLUMNS = ["key", "gene", "gene_mim", "transcript", "canonical", "hgvsc", "hgvsp",
               "consequence", "exon", "pathogenicity", "autopat_score", "acmg",
               "clinvar", "clinvar_star", "genotype", "quality", "allele_fraction",
               "depth", "genotype_quality", "af_max", "gnomad_exome", "gnomad_genome",
               "gnomad_exome_hom", "gme", "revel", "sift", "polyphen", "splice_ada",
               "splice_rf", "spliceai", "internal_freq", "internal_global", "internal_n", "dbsnp",
               "diseases"]
    CNV_COLUMNS = ["chrom", "start", "end", "length_kb", "copy_number", "state", "caller",
                   "classification", "cohort_nondiploid", "cohort_total", "cohort_artifact",
                   "n_genes", "genes"]
    HEDEF_PENCERE = {"F8": ("X", 154600000, 155800000)}

    def cnv_hedefte(row, genler):
        hedef = set(g.upper() for g in genler)
        if set(g.upper() for g in (row.get("genes_all") or [])) & hedef:
            return True
        krom = str(row.get("chrom") or "").replace("chr", "")
        bas, son = row.get("start"), row.get("end") or row.get("start")
        for g in hedef:
            w = HEDEF_PENCERE.get(g)
            if w and krom == w[0] and bas is not None and bas <= w[2] and son >= w[1]:
                return True
        return False

EK_SUTUNLAR = ["cadd_phred", "alphamissense", "impact", "inheritance", "ilyome_score",
               "ilyome_color", "is_reported", "omim", "cohort_af", "cohort_an", "ilyome_id"]
ILYOME_COLUMNS = COLUMNS + EK_SUTUNLAR


# --------------------------------------------------------------------------
def env(name):
    v = os.environ.get(name)
    return v.strip() if v else None


def _log(msg):
    sys.stderr.write(msg + "\n")


class IlyomeHata(RuntimeError):
    pass


ZARF_ANAHTARLARI = {"data", "message", "status", "success", "code", "detail", "errors"}


def zarf_ac(j):
    """Ilyome bazi yanitlari {"data": {...}} zarfina sarar (ornek: giris -> {"data": {"access": ..}}).

    Zarf, yalniz data + mesaj alanlarindan olusan bir sozlukse icindeki nesne dondurulur.
    {"total": N, "data": [...]} gibi liste yanitlari (total anahtari zarfta yok) oldugu gibi kalir.
    """
    while isinstance(j, dict) and "data" in j and isinstance(j["data"], dict) \
            and set(j.keys()) <= ZARF_ANAHTARLARI:
        j = j["data"]
    return j


def _gizli_metin(r, n=200):
    """Hata mesajinda token/parola gorunmesin (log ve Excel'e yazilir)."""
    t = r.text or ""
    if any(k in t for k in ("access", "refresh", "token", "password")):
        return "<gizli: %d bayt yanit>" % len(t)
    return t[:n]


# --------------------------------------------------------------------------
class Seq(object):
    """Ilyome oturumu. Arayuz genomize_seq.Seq ile uyumludur."""

    PLATFORM = "Ilyome"

    def __init__(self, username=None, password=None, center=None):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "ilyome_seq/0.1 (WES rutini)"
        self.s.headers["Accept"] = "application/json"
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            rt = Retry(total=4, backoff_factor=2, status_forcelist=(500, 502, 503, 504),
                       allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE", "PATCH"]))
            self.s.mount("https://", HTTPAdapter(max_retries=rt))
        except Exception:
            pass
        self.access = self.refresh = None
        self.user = {}
        self.center = center or env("ILYOME_CENTER")
        self.skipped_axes = {}
        self._tema = None
        self._panel_onbellek = {}
        self.ham_kayit = None          # kesfet modunda ham yanitlari toplar

        u = username or env("ILYOME_USER") or input("Ilyome e-posta: ")
        p = password or env("ILYOME_PASS") or getpass.getpass("Ilyome parolasi: ")
        self._login(u, p)

    # -- kimlik ----------------------------------------------------------
    def _login(self, email, password):
        r = self.s.post(BASE + "/api/users/login/", json={"email": email, "password": password},
                        timeout=60)
        if r.status_code == 401:
            sys.exit("Ilyome girisi basarisiz (401): e-posta/parola hatali olabilir. %s" % r.text[:160])
        if r.status_code != 200:
            # Bazi hesaplarda tek kullanimlik kod (OTP) istenir.
            if r.status_code in (400, 403) and "otp" in r.text.lower():
                return self._login_otp(email)
            sys.exit("Ilyome girisi basarisiz (%s): %s" % (r.status_code, r.text[:200]))
        j = zarf_ac(r.json())
        if not (isinstance(j, dict) and j.get("access") and j.get("refresh")):
            if "otp" in json.dumps(j).lower():
                return self._login_otp(email)
            sys.exit("Ilyome girisi: beklenmeyen yanit (anahtarlar: %s)"
                     % ", ".join(sorted(j.keys())[:8]) if isinstance(j, dict) else "Ilyome girisi: beklenmeyen yanit")
        self._token_al(j)

    def _login_otp(self, email):
        _log("Ilyome tek kullanimlik kod istiyor; e-postanizi kontrol edin.")
        r = self.s.post(BASE + "/api/users/login/otp/request/", json={"email": email}, timeout=60)
        if r.status_code >= 400:
            sys.exit("OTP istegi basarisiz (%s): %s" % (r.status_code, r.text[:160]))
        kod = input("E-postaya gelen kod: ").strip()
        r = self.s.post(BASE + "/api/users/login/otp/verify/", json={"email": email, "code": kod},
                        timeout=60)
        if r.status_code != 200:
            sys.exit("OTP dogrulama basarisiz (%s): %s" % (r.status_code, r.text[:160]))
        self._token_al(zarf_ac(r.json()))

    def _token_al(self, j):
        self.access, self.refresh = j["access"], j.get("refresh") or self.refresh
        self.user = j.get("user") or self.user or {}
        self.s.headers["Authorization"] = "Bearer " + self.access
        if not self.center:
            c = self.user.get("center")
            if isinstance(c, dict):
                c = c.get("name")
            self.center = (c or VARSAYILAN_MERKEZ)
        _log("giris: %s  (merkez: %s, rol: %s)" % (self.user.get("email"), self.center,
                                                   self.user.get("role")))

    def _yenile(self):
        if not self.refresh:
            return False
        r = self.s.post(BASE + "/api/users/login/refresh/", json={"refresh": self.refresh}, timeout=60)
        j = zarf_ac(r.json()) if r.status_code == 200 else {}
        if isinstance(j, dict) and j.get("access"):
            self.access = j["access"]
            self.s.headers["Authorization"] = "Bearer " + self.access
            return True
        return False

    def whoami(self):
        return zarf_ac(self.get("/api/users/whoami/").json())

    # -- istek ------------------------------------------------------------
    def url(self, path):
        """/api/ilcore/... -> https://ilyome.com/api/c/<merkez>/ilcore/..."""
        if any(path.startswith(p) for p in MERKEZLI):
            path = path.replace("/api/", "/api/c/%s/" % self.center, 1)
        return BASE + path

    def _istek(self, method, path, **kw):
        timeout = kw.pop("timeout", 180)
        r = self.s.request(method, self.url(path), timeout=timeout, **kw)
        if r.status_code == 401 and self._yenile():
            r = self.s.request(method, self.url(path), timeout=timeout, **kw)
        if self.ham_kayit is not None:
            self.ham_kayit.append({"method": method, "url": r.url, "status": r.status_code,
                                   "body": kw.get("json"), "yanit": _json_or_text(r)})
        return r

    def get(self, path, **kw):
        return self._istek("GET", path, **kw)

    def post(self, path, payload=None, **kw):
        return self._istek("POST", path, json=payload, **kw)

    def put(self, path, payload=None, **kw):
        r = self._istek("PUT", path, json=payload, **kw)
        if r.status_code == 405:                       # sunucu PATCH bekliyorsa
            r = self._istek("PATCH", path, json=payload, **kw)
        return r

    def delete(self, path, **kw):
        return self._istek("DELETE", path, **kw)

    def _json(self, r, ne):
        if r.status_code >= 400:
            if r.status_code == 403 and "legal_consent_required" in (r.text or ""):
                raise IlyomeHata(
                    "Ilyome yeni Kullanim Kosullari / Gizlilik Politikasi onayi istiyor "
                    "(legal_consent_required). Tarayicida ilyome.com'a girip kosullari kabul edin, "
                    "sonra olguyu yeniden BEKLIYOR yapip rutini tekrar calistirin.")
            raise IlyomeHata("%s basarisiz (%s): %s" % (ne, r.status_code, _gizli_metin(r)))
        try:
            return zarf_ac(r.json())
        except ValueError:
            raise IlyomeHata("%s: JSON degil: %s" % (ne, _gizli_metin(r, 120)))

    # -- ornek ------------------------------------------------------------
    def samples(self, arama=None, page=1, page_size=50):
        q = {"ordering": "-id", "page": page, "page_size": page_size}
        if arama:
            q["sampleid"] = arama
        j = self._json(self.get("/api/sample-run/samples/create-list/", params=q), "ornek listesi")
        return j.get("data") or [], j.get("total") or 0

    @staticmethod
    def _an(s):
        """Ilyome sample -> rutin'in bekledigi 'analiz' sozlugu (Genomize alan adlari)."""
        run = s.get("run") or {}
        ref = str(run.get("reference") or "").upper()
        genom = "hg38" if "38" in ref else ("hg19" if "19" in ref or "37" in ref else ref.lower() or None)
        kit = run.get("run_name") or ""
        if run.get("capture_type"):
            kit = "%s (%s)" % (kit, run.get("capture_type"))
        return {
            "id": s.get("id"), "hash": s.get("id"),
            "sample_name": s.get("sampleid") or s.get("patient_name"),
            "patient_name": s.get("patient_name"),
            "genome_version": genom, "kit": kit,
            "sequencing_type": run.get("sequencing_type"),
            "workers": run.get("workers"),
            "status": (s.get("status") or {}).get("status"),
            "status_id": (s.get("status") or {}).get("id"),
            "run": {"name": run.get("run_name"), "id": run.get("id")},
            "latest_annotation_tag": None,
            "numberofmutations": None,          # dashboard() doldurur
            "_sample": s,
        }

    def resolve(self, code):
        """Ornek kodu -> analiz sozlugu. Tam olarak 1 eslesme bekler."""
        code = str(code).strip()
        data, _ = self.samples(code, page_size=50)
        tam = [s for s in data if str(s.get("sampleid") or "").strip() == code
               or str(s.get("patient_name") or "").strip() == code]
        aday = tam or data
        if not aday:
            sys.exit("Ornek bulunamadi: %s" % code)
        if len(aday) > 1:
            adlar = ", ".join(str(s.get("sampleid")) for s in aday[:6])
            _log("UYARI: %s icin %d eslesme:" % (code, len(aday)))
            for s in aday:
                _log("   %s  %s  %s" % (s.get("id"), s.get("sampleid"), (s.get("run") or {}).get("run_name")))
            raise ValueError("'%s' %d ornekle eslesti, hangisi oldugu belirsiz. "
                             "Proband No sutununa tam ornek adini yazin. Eslesenler: %s"
                             % (code, len(aday), adlar))
        an = self._an(aday[0])
        try:
            d = self.dashboard(an)
            an["numberofmutations"] = d.get("total_variants")
        except Exception:
            pass
        return an

    def warmup(self, an, wait=0, toplam=None):
        """Ilyome'da isitma yok: ornek 'Finished' ise hazirdir."""
        if an.get("status_id") == 6 or str(an.get("status") or "").lower() == "finished":
            return True
        _log("  ornek henuz bitmemis: %s (%s)" % (an.get("sample_name"), an.get("status")))
        return False

    def dashboard(self, an):
        r = self.get("/api/sample-run/samples/%s/overview/" % an["id"])
        d = zarf_ac(r.json()) if r.status_code == 200 else {}
        if isinstance(d, dict):
            d.setdefault("average_depth", d.get("quality_score_mean_coverage"))
            d.setdefault("total_annotation", d.get("total_variants"))
        return d if isinstance(d, dict) else {}

    KAPSAMA_ANAHTAR = ("coverage", "depth", "uniformity", "duplicat", "q30", "het/hom", "hethom",
                       "mean", "median", "[  20x", "[  50x", "[ 100x", "[  10x", "[   1x", "reads",
                       "mapped", "bases", "ti/tv", "titv")

    def kapsama(self, an):
        """Dragen metriklerini duzlestir; anahtar adi eslesmesiyle QC alanlarini sec."""
        r = self.get("/api/ilcore/samples/%s/d-metrics/" % an["id"])
        d = zarf_ac(r.json()) if r.status_code == 200 else {}
        out, m = {}, (d.get("metrics") if isinstance(d, dict) else None) or {}
        for bolum in ("coverages", "mapping_metrics", "vcf_metrics", "hethom_metrics"):
            for kv in m.get(bolum) or []:
                k = str(kv.get("key") or "")
                if any(a in k.lower() for a in self.KAPSAMA_ANAHTAR):
                    out["%s.%s" % (bolum, k)] = kv.get("value")
        ov = self.dashboard(an)
        for k in ("quality_score", "quality_score_mean_coverage", "hethom_ratio", "titv_ratio",
                  "duplication_ratio", "total_variants", "snv_variants", "indel_variants",
                  "cnv_events", "q30_bases", "total_bases"):
            if ov.get(k) is not None:
                out["overview." + k] = ov.get(k)
        return out, d

    def sanity(self, an):
        """Filtresiz toplam varyant sayisi (sessiz bos sonucu yakalamak icin)."""
        j = self._json(self.get("/api/ilcore/samples/%s/snv/count/" % an["id"]), "snv count")
        return j.get("total") or 0

    # -- yardimci ---------------------------------------------------------
    def hpo_search(self, keyword):
        r = self.get("/api/db/hpo/search/", params={"search": keyword, "page_size": 20})
        if r.status_code != 200:
            return []
        j = zarf_ac(r.json())
        items = j.get("data") if isinstance(j, dict) else j
        return [{"id": x.get("term_id") or x.get("hpo_id") or x.get("id"), "name": x.get("name")}
                for x in (items or [])]

    def gene_ids(self, symbols):
        """Gen sembolu -> NCBI gen kaydi id'si (search-theme gen filtresi icin)."""
        out, yok = {}, []
        for sym in symbols:
            r = self.get("/api/db/genes/ncbi/", params={"search": sym, "symbol_i": sym.upper(),
                                                        "length": "true", "page_size": 20})
            jj = zarf_ac(r.json()) if r.status_code == 200 else {}
            data = (jj.get("data") if isinstance(jj, dict) else jj) or []
            hit = [g for g in data if str(g.get("Symbol") or g.get("symbol") or "").upper() == sym.upper()]
            if hit:
                out[sym.upper()] = hit[0].get("id")
            else:
                yok.append(sym)
        return out, yok

    # -- filtre sablonu (search theme) -------------------------------------
    def tema(self):
        """Rutinin kendi sablonu; yoksa olusturur. Kullanici sablonlarina dokunulmaz."""
        if self._tema:
            return self._tema
        j = self._json(self.get("/api/ilcore/search-theme/", params={"page_size": 100}), "sablon listesi")
        for t in (j.get("data") if isinstance(j, dict) else j) or []:
            if t.get("name") == TEMA_ADI:
                self._tema = t["id"]
                return self._tema
        j = self._json(self.post("/api/ilcore/search-theme/create/", {"name": TEMA_ADI, "is_center": False}),
                       "sablon olusturma")
        self._tema = j["id"]
        _log("  Ilyome filtre sablonu olusturuldu: %s (id %s)" % (TEMA_ADI, self._tema))
        return self._tema

    def panel(self, tema_id, variant_type="snv", taze=False):
        k = (tema_id, variant_type)
        if taze or k not in self._panel_onbellek:
            self._panel_onbellek[k] = self._json(
                self.get("/api/ilcore/search-theme/%s/" % tema_id, params={"variant_type": variant_type}),
                "sablon paneli")
        return self._panel_onbellek[k]

    def tema_sifirla(self, tema_id):
        """Tum filtre degerlerini, fenotip/gen/ornek listelerini temizle."""
        r = self.delete("/api/ilcore/search-theme/%s/reset/" % tema_id)
        if r.status_code == 405:
            r = self.post("/api/ilcore/search-theme/%s/reset/" % tema_id, {})
        if r.status_code >= 400:
            raise IlyomeHata("sablon sifirlama basarisiz (%s): %s" % (r.status_code, _gizli_metin(r, 160)))
        for yol in ("phenotype/clear-all", "gene/clear-all", "sample/clear-all", "genepanel/clear-all",
                    "disease/clear-all"):
            self.delete("/api/ilcore/search-theme/%s/%s/" % (tema_id, yol))
        self._panel_onbellek = {k: v for k, v in self._panel_onbellek.items() if k[0] != tema_id}

    def deger_ayarla(self, value_id, min_=None, max_=None, isnull=False, selected=False):
        body = {"id": value_id, "min": min_, "max": max_, "isnull": bool(isnull),
                "selected": bool(selected), "logic": "and"}
        r = self.put("/api/ilcore/search-theme/update-value/%s/" % value_id, body)
        if r.status_code >= 400:
            raise IlyomeHata("filtre degeri yazilamadi (%s %s): %s" % (value_id, r.status_code, _gizli_metin(r, 160)))

    def filtre_uygula(self, tema_id, spec, variant_type="snv"):
        """spec = {"checkbox": [(filter, term), ...],
                   "range": {(filter, term): (min, max)},
                   "hpo": [...], "genes": [...]}  -> sablonu sifirlayip ayarlar."""
        self.tema_sifirla(tema_id)
        p = self.panel(tema_id, variant_type, taze=True)
        indeks = panel_indeksi(p)
        eksik = []
        for (f, t) in spec.get("checkbox") or []:
            v = indeks.get((f, t))
            if not v:
                eksik.append("%s:%s" % (f, t))
                continue
            self.deger_ayarla(v["id"], selected=True)
        for (f, t), aralik in (spec.get("range") or {}).items():
            mn, mx = aralik[0], aralik[1]
            isnull = bool(aralik[2]) if len(aralik) > 2 else False
            v = indeks.get((f, t))
            if not v:
                eksik.append("%s:%s" % (f, t))
                continue
            # isnull=True: alani BOS olan varyantlar da gelsin (gnomAD'de hic gorulmemis =
            # en nadir); yoksa frekans filtresi 'populasyonda yok' varyantlari sessizce eler.
            # Ilyome arayuzu aralik girildiginde selected=True gonderir; selected=False olursa
            # sunucu araligi yok sayar (ilk gercek kosuda frekans filtresi bu yuzden uygulanmadi).
            self.deger_ayarla(v["id"], min_=mn, max_=mx, isnull=isnull, selected=True)
        if eksik:
            raise IlyomeHata("Ilyome filtre panelinde bulunmayan terimler: %s" % ", ".join(eksik))
        if spec.get("hpo"):
            self.fenotip_ekle(tema_id, spec["hpo"])
        if spec.get("genes"):
            ids, yok = self.gene_ids(spec["genes"])
            for sym, gid in ids.items():
                r = self.put("/api/ilcore/search-theme/%s/gene/%s/" % (tema_id, gid))
                if r.status_code >= 400:
                    raise IlyomeHata("gen eklenemedi %s: %s" % (sym, _gizli_metin(r, 120)))
            if yok:
                _log("  UYARI: Ilyome gen veritabaninda bulunmadi: %s" % ", ".join(yok))
            spec["_gen_bulunamayan"] = yok
        return self.panel(tema_id, variant_type, taze=True)

    def fenotip_ekle(self, tema_id, hpo_ids):
        r = self.put("/api/ilcore/search-theme/%s/phenotype/bulk-add/" % tema_id,
                     {"search": ",".join(hpo_ids)})
        if r.status_code >= 400:
            raise IlyomeHata("HPO eklenemedi (%s): %s" % (r.status_code, _gizli_metin(r, 160)))
        j = zarf_ac(r.json()) if r.text else {}
        n = j.get("count") if isinstance(j, dict) else None
        if n is not None and n < len(hpo_ids):
            _log("  UYARI: %d HPO teriminden %s eklendi" % (len(hpo_ids), n))
        return n

    def fenotipler(self, tema_id):
        r = self.get("/api/ilcore/search-theme/%s/phenotype/" % tema_id, params={"page_size": 200})
        jj = zarf_ac(r.json()) if r.status_code == 200 else {}
        return (jj.get("data") if isinstance(jj, dict) else jj) or []

    # -- aile iliskisi (trio sablonu; simdilik yalniz kesif/ileri kullanim) --
    def iliski_ayarla(self, tema_id, rol, sample_id):
        """rol: mother | father | spouse. sample_id None ise iliski kaldirilir."""
        yol = "/api/ilcore/search-theme/%s/sample/relation/%s/" % (tema_id, rol)
        if sample_id is None:
            return self.delete(yol).status_code
        return self.put(yol + "%s/" % sample_id).status_code

    def ornek_ekle(self, tema_id, sample_id):
        return self.put("/api/ilcore/search-theme/%s/sample/%s/" % (tema_id, sample_id)).status_code

    # -- varyant listeleri ---------------------------------------------------
    def _sayfala(self, path, params, cap, ne):
        rows, page = [], 1
        while True:
            q = dict(params, page=page, page_size=SAYFA)
            j = self._json(self.get(path, params=q, timeout=300), ne)
            parca = duzlestir(j.get("data") or [])
            rows.extend(parca)
            toplam = j.get("total")
            if not parca or (toplam is not None and len(rows) >= toplam) or len(rows) >= cap \
                    or len(parca) < SAYFA:
                if toplam is not None and len(rows) < min(toplam, cap) and parca:
                    page += 1
                    continue
                break
            page += 1
        if len(rows) >= cap:
            _log("  UYARI: %s %d kayitta kesildi (cap)" % (ne, cap))
        return rows

    def snv_list(self, an, tema_id, cap=20000):
        return self._sayfala("/api/ilcore/samples/%s/snv/%s/" % (an["id"], tema_id),
                             {"ordering": "-id"}, cap, "snv listesi")

    def top_reportable(self, an, cap=2000):
        """Ilyome'un kendi onceliklendirmesi (Tier karsiligi)."""
        return self._sayfala("/api/sample-run/samples/%s/overview/snv/top-reportable/" % an["id"],
                             {"ordering": "-id"}, cap, "top-reportable")

    def cnv_list(self, an, tema_id, cap=20000):
        return self._sayfala("/api/ilcore/samples/%s/cnv/%s/" % (an["id"], tema_id),
                             {"ordering": "-id"}, cap, "cnv listesi")

    # Genomize arayuz uyumu (rutin.py cnv_batch/cnvs cagirir)
    def cnv_batch(self, an):
        return {"id": an["id"]}

    def cnvs(self, an, batch):
        tema = self.tema()
        self.tema_sifirla(tema)
        return self.cnv_list(an, tema), None


# --------------------------------------------------------------------------
# yardimcilar
# --------------------------------------------------------------------------
def _json_or_text(r):
    try:
        return r.json()
    except ValueError:
        return r.text[:2000]


def duzlestir(data):
    """Ilyome snv/cnv listesi: duz satirlar ya da {samples:[{ornek:[satir]}]} gruplari."""
    out = []
    for e in data or []:
        if isinstance(e, dict) and isinstance(e.get("samples"), list):
            for s in e["samples"]:
                for _, rows in (s or {}).items():
                    out.extend(rows or [])
        elif isinstance(e, dict) and isinstance(e.get("variants"), list):
            out.extend(e["variants"])
        elif isinstance(e, dict):
            out.append(e)
    return out


def panel_gruplari(panels):
    """panels ic ice liste olabilir -> duz grup listesi."""
    out = []

    def gez(x):
        if isinstance(x, list):
            for y in x:
                gez(y)
        elif isinstance(x, dict):
            out.append(x)
    gez(panels)
    return out


def panel_indeksi(panel):
    """(filter, term) -> value sozlugu."""
    idx = {}
    for grp in panel_gruplari(panel.get("panels") or []):
        for terms in grp.get("terms") or []:
            for t in (terms if isinstance(terms, list) else [terms]):
                if isinstance(t, dict) and t.get("value"):
                    idx[(t.get("filter"), t.get("term"))] = t["value"]
    return idx


def _f(v):
    if v is None or v == "":
        return None
    try:
        return None if float(v) < 0 else v
    except (TypeError, ValueError):
        return v


def _spliceai(it):
    sa = it.get("splice_ai")
    if sa is not None:
        return _f(sa)
    ds = [it.get(k) for k in ("spliceai_pred_ds_ag", "spliceai_pred_ds_al",
                              "spliceai_pred_ds_dg", "spliceai_pred_ds_dl")]
    ds = [d for d in ds if isinstance(d, (int, float))]
    return max(ds) if ds else None


def _omim(it):
    ids = []
    for d in it.get("disease") or []:
        did = str(d.get("disease_id") or "")
        if did.startswith("OMIM:"):
            ids.append(did.split(":", 1)[1])
    return ";".join(sorted(set(ids)))


def _kalitim(it):
    inh = it.get("inheritance") or {}
    if isinstance(inh, dict):
        return "/".join(inh.get("hpo") or inh.get("monarch") or [])
    return str(inh)


def _hgvs(s):
    """'ENST00000296271.4:c.232A>C' -> 'c.232A>C' (transkript ayri sutunda)."""
    if not s:
        return None
    return s.split(":", 1)[1] if ":" in s else s


def slim(it):
    """Ilyome varyant kaydi -> kanit CSV satiri (Genomize sutun adlariyla)."""
    zyg = str(it.get("zyg") or "").lower()
    af = it.get("allelefraction")
    cohort_an = it.get("cohort_an") or 0
    cohort_af = it.get("cohort_af")
    # Merkez kohortu kucukse (ör. 16 alel) frekans artefakt kriteri olarak ANLAMSIZDIR;
    # tek bir het bile %6 verir ve her seyi artefakt yapar. 200 alelin altinda bos birak.
    internal = cohort_af if (cohort_an and cohort_an >= 200) else None
    tx = it.get("mane_select") or it.get("feature")
    return {
        "key": it.get("variant_key") or "%s:%s:%s:%s" % (
            str(it.get("chrom") or "").replace("chr", ""), it.get("pos"), it.get("ref"), it.get("alt")),
        "gene": it.get("symbol"), "gene_mim": None,
        "transcript": tx, "canonical": (str(it.get("canonical") or "").upper() == "YES"),
        "hgvsc": _hgvs(it.get("hgvsc")), "hgvsp": _hgvs(it.get("hgvsp")),
        "consequence": it.get("consequence"), "exon": it.get("exon") or it.get("intron"),
        "pathogenicity": it.get("acmg_class"), "autopat_score": it.get("score_raw"),
        "acmg": ",".join(it.get("acmg") or []) if isinstance(it.get("acmg"), list) else (it.get("acmg") or ""),
        "clinvar": it.get("clinvar_clnsig"), "clinvar_star": None,
        "genotype": zyg, "quality": it.get("filter"),
        "allele_fraction": (round(af / 100.0, 4) if isinstance(af, (int, float)) and af > 1 else af),
        "depth": it.get("dp"), "genotype_quality": it.get("qual"),
        "af_max": _f(it.get("max_af")),
        "gnomad_exome": _f(it.get("af_exomes")), "gnomad_genome": _f(it.get("af_genomes")),
        "gnomad_exome_hom": _f(it.get("nhomalt_exomes")),
        "gme": _f(it.get("genoks_af")),                    # Turk kohort frekansi (Genoks) - GME yerine
        "revel": _f(it.get("revel_score")), "sift": _f(it.get("sift_score")),
        "polyphen": _f(it.get("polyphen2_hdiv_score")),
        "splice_ada": None, "splice_rf": None, "spliceai": _spliceai(it),
        "internal_freq": internal, "internal_global": None, "internal_n": cohort_an or None,
        "dbsnp": it.get("existing_variation") or "",
        "diseases": len(it.get("disease") or []),
        # Ilyome'a ozgu
        "cadd_phred": _f(it.get("cadd_phred")), "alphamissense": _f(it.get("alphamissense_score")),
        "impact": it.get("impact"), "inheritance": _kalitim(it),
        "ilyome_score": it.get("score"), "ilyome_color": it.get("color"),
        "is_reported": it.get("is_reported"), "omim": _omim(it),
        "cohort_af": cohort_af, "cohort_an": cohort_an or None, "ilyome_id": it.get("id"),
    }


def write_csv(path, rows, columns=None):
    columns = columns or ILYOME_COLUMNS
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def is_artifact(row, internal_max):
    f = row.get("internal_freq")
    try:
        return f is not None and f != "" and float(f) >= internal_max
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------
# tarama eksenleri (Genomize eksenlerinin Ilyome karsiliklari)
# --------------------------------------------------------------------------
def pop_frekans(yuzde):
    """Populasyon frekansi ust siniri (yuzde) -> Ilyome aralik filtreleri.

    Ilyome panelinde Genomize'daki gibi tek bir 'max_af' filtresi YOK; gnomAD ekzom ve
    gnomAD genom frekanslari ayri ayri sinirlanir (ikisi de <= esik, bos olanlar dahil).
    Satirdaki max_af sutunu yine de CSV'ye yazilir (af_max), Claude son kontrolu yapar.
    """
    esik = yuzde / 100.0
    return {("af_exomes", "af_exomes"): (None, esik, True),
            ("af_genomes", "af_genomes"): (None, esik, True)}


def axes(hpo_ids=None, max_freq=1.0):
    """ad -> filtre spec. max_freq yuzde cinsinden (1.0 = %1). Genomize eksenlerinin karsiligi."""
    out = {}
    if hpo_ids:
        out["fenotip_iliskili"] = {"hpo": list(hpo_ids), "range": pop_frekans(max_freq)}
    out["nadir_lof"] = {"checkbox": [("consequence", c) for c in DESTRUCTIVE],
                        "range": pop_frekans(0.1)}
    out["clinvar_patojenik"] = {"checkbox": [("clinvar_clnsig", c) for c in CLINVAR_P]}
    out["tier"] = {"_top_reportable": True}        # Ilyome onceliklendirmesi; filtre gerekmez
    out["homozigot_nadir"] = {"checkbox": [("zyg", "HOM"), ("zyg", "HEM")] +
                                          [("acmg_class", a) for a in ACMG_PLV],
                              "range": pop_frekans(0.5)}
    return out


def _pop_af(r):
    """slim() satiri icin populasyon frekansi (gnomAD ekzom/genom ve max_af'in en buyugu); yoksa None."""
    v = [r.get(k) for k in ("af_max", "gnomad_exome", "gnomad_genome")]
    v = [x for x in v if isinstance(x, (int, float))]
    return max(v) if v else None


def frekans_suz(rows, max_freq):
    """Istemci tarafi son kontrol: populasyon frekansi > esik (yuzde) olan satirlari ele.
    Sunucu filtresi uygulanmazsa (ya da baska bir alan uzerinden calisirsa) eksenler sik
    varyantla dolmasin diye; frekansi bilinmeyen (gnomAD'de yok) satirlar KALIR."""
    esik = max_freq / 100.0
    kalan = [r for r in rows if (_pop_af(r) is None or _pop_af(r) <= esik)]
    return kalan, len(rows) - len(kalan)


AXIS_CAP = int(os.environ.get("ILYOME_EKSEN_CAP", "20000"))


def run_axes(seq, an, hpo_ids, internal_max, max_freq):
    """Tum eksenleri calistir -> {eksen: [satir]} (satirlar slim() ile duzlestirilmis).

    seq.skipped_axes: atlanan eksen -> neden.  seq.kesilen_eksenler: cap'e takilan eksen -> cap.
    seq.frekans_elenen: eksen -> istemci tarafinda frekans nedeniyle elenen satir sayisi."""
    seq.skipped_axes = {}
    seq.kesilen_eksenler = {}
    seq.frekans_elenen = {}
    tema = seq.tema()
    res = {}
    esikler = {"fenotip_iliskili": max_freq, "nadir_lof": 0.1, "homozigot_nadir": 0.5}
    for name, spec in axes(hpo_ids, max_freq).items():
        _log("  eksen: %s" % name)
        try:
            if spec.get("_top_reportable"):
                ham = seq.top_reportable(an)
            else:
                seq.filtre_uygula(tema, spec)
                ham = seq.snv_list(an, tema, cap=AXIS_CAP)
        except IlyomeHata as e:
            seq.skipped_axes[name] = str(e)[:160]
            _log("  eksen: %s ATLANDI (%s)" % (name, str(e)[:120]))
            continue
        rows = [slim(x) for x in ham]
        if name in esikler:
            rows, elenen = frekans_suz(rows, esikler[name])
            if elenen:
                seq.frekans_elenen[name] = elenen
                _log("  eksen: %s - istemci frekans kontrolu %d satir eledi (>%%%s); sunucu filtresi "
                     "uygulanmamis olabilir" % (name, elenen, esikler[name]))
        if len(ham) >= AXIS_CAP:
            seq.kesilen_eksenler[name] = AXIS_CAP
            _log("  eksen: %s %d kayitta KESILDI; liste eksik olabilir" % (name, AXIS_CAP))
        res[name] = rows
    return res


def run_hedef(seq, an, genler, cap=20000):
    """Hedefe yonelik mod: yalniz verilen genlerdeki TUM varyantlar (intronik/UTR dahil)."""
    tema = seq.tema()
    spec = {"genes": list(genler)}
    seq.filtre_uygula(tema, spec)
    ham = seq.snv_list(an, tema, cap=cap)
    rows = [slim(x) for x in ham]
    bulunan = sorted({r["gene"] for r in rows if r.get("gene")})
    bilgi = {"satir": len(rows), "genler": list(genler),
             "varyant_bulunan_genler": bulunan,
             "varyantsiz_genler": [g for g in genler if g.upper() not in {b.upper() for b in bulunan}],
             "gen_bulunamayan": spec.get("_gen_bulunamayan") or [],
             "kesildi": len(rows) >= cap}
    return rows, bilgi


def cnv_rows(items, cohort_artifact=0.3):
    out = []
    for x in items or []:
        genes = [g.strip() for g in str(x.get("protein_coding_genes") or "").split(",") if g.strip()]
        tot = x.get("ilyomedb_total_filter") or 0
        nd = x.get("ilyomedb_total") or 0
        size_kb = x.get("cnv_size")
        if size_kb is None and x.get("start") is not None and x.get("end") is not None:
            size_kb = round((x["end"] - x["start"]) / 1000.0, 2)
        out.append({
            "chrom": x.get("chrom"), "start": x.get("start"), "end": x.get("end"),
            "length_kb": size_kb, "copy_number": x.get("copy_number"),
            "state": x.get("cnvtype"), "caller": x.get("filter"),
            "classification": x.get("acmg_class"),
            "cohort_nondiploid": nd, "cohort_total": tot,
            "cohort_artifact": bool(tot and nd / float(tot) >= cohort_artifact),
            "n_genes": len(genes), "genes": ";".join(genes[:20]),
            "genes_all": genes,
            "dosage_sensitive": x.get("dosage_sensitive_genes"),
            "total_score": x.get("total_score"), "omim": _omim(x),
            "inheritance": _kalitim(x), "ilyome_id": x.get("id"),
        })
    return out


ILYOME_CNV_COLUMNS = CNV_COLUMNS + ["dosage_sensitive", "total_score", "omim", "inheritance", "ilyome_id"]


# --------------------------------------------------------------------------
# komutlar
# --------------------------------------------------------------------------
def _ozet_satir(r):
    return "%-22s %-10s %-28s %-22s %-5s AF=%s  %s" % (
        r["key"], r["gene"] or "-", (r["hgvsc"] or "")[:28], (r["pathogenicity"] or "")[:22],
        r["genotype"], r["af_max"], r["consequence"])


def cmd_resolve(seq, a):
    an = seq.resolve(a.code)
    for k in ("id", "sample_name", "patient_name", "genome_version", "kit", "sequencing_type",
              "workers", "status", "numberofmutations"):
        print("%-18s %s" % (k, an.get(k)))
    print("%-18s %s" % ("run", an.get("run")))


def cmd_qc(seq, a):
    an = seq.resolve(a.code)
    kap, _ = seq.kapsama(an)
    for k in sorted(kap):
        print("%-70s %s" % (k, kap[k]))
    print("filtresiz varyant sayisi:", seq.sanity(an))


def cmd_hpo(seq, a):
    for t in seq.hpo_search(a.keyword):
        print("%-12s %s" % (t["id"], t["name"]))


def cmd_scan(seq, a):
    an = seq.resolve(a.code)
    if not seq.warmup(an):
        sys.exit("ornek hazir degil")
    out = a.out or ("ilyome_%s" % an["sample_name"])
    os.makedirs(out, exist_ok=True)
    ham = run_axes(seq, an, a.hpo or [], a.internal_max, a.max_freq)
    ozet = {"ornek": an["sample_name"], "id": an["id"], "genom": an.get("genome_version"),
            "kit": an.get("kit"), "filtresiz": seq.sanity(an), "eksenler": {},
            "atlanan": seq.skipped_axes, "tarih": datetime.datetime.now().isoformat(timespec="seconds")}
    for eksen, rows in ham.items():
        temiz = [x for x in rows if not is_artifact(x, a.internal_max)]
        write_csv(os.path.join(out, "%s_%s.csv" % (an["sample_name"], eksen)), temiz)
        ozet["eksenler"][eksen] = {"toplam": len(rows), "temiz": len(temiz)}
        print("\n== %s: %d satir" % (eksen, len(rows)))
        for r in temiz[:8]:
            print("  " + _ozet_satir(r))
    items, _ = seq.cnvs(an, None)
    rows = cnv_rows(items)
    write_csv(os.path.join(out, "%s_cnv.csv" % an["sample_name"]), rows, ILYOME_CNV_COLUMNS)
    ozet["cnv"] = len(rows)
    with open(os.path.join(out, "ozet.json"), "w", encoding="utf-8") as f:
        json.dump(ozet, f, indent=1, ensure_ascii=False)
    print("\nyazildi:", out)


def _gizle(o):
    """Kesif ciktisindan token/parola benzeri alanlari sil."""
    if isinstance(o, dict):
        return {k: ("***" if any(s in k.lower() for s in ("token", "access", "refresh", "password", "secret"))
                    else _gizle(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_gizle(x) for x in o]
    return o


def cmd_kesfet(seq, a):
    """API kesfi: her adimin ham yanitini JSON'a yazar (tokenlar gizlenir).

    Bu ciktilar Claude'un filtre semantigini (OR/AND, sayfa boyutu, alan adlari)
    dogrulamasi icin gerekir; hasta verisi icerir, yalniz Drive'daki _sistem/ilyome_kesif/
    klasorunde tutun, baska yere gondermeyin.
    """
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ilyome_kesif",
                                datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out, exist_ok=True)
    seq.ham_kayit = []
    rapor = {"base": BASE, "merkez": seq.center, "kullanici": _gizle(seq.user), "adimlar": {}}

    def adim(ad, fn):
        try:
            v = fn()
            rapor["adimlar"][ad] = {"durum": "ok", "ozet": v}
            print("  ok   %s: %s" % (ad, json.dumps(v, ensure_ascii=False)[:160]))
        except BaseException as e:
            rapor["adimlar"][ad] = {"durum": "hata", "hata": "%s: %s" % (type(e).__name__, str(e)[:300])}
            print("  HATA %s: %s" % (ad, str(e)[:200]))

    adim("whoami", lambda: _gizle(seq.whoami()))
    adim("ornek_listesi", lambda: {"toplam": seq.samples(page_size=5)[1]})
    an = {}

    def _resolve():
        an.update(seq.resolve(a.code))
        return {k: an.get(k) for k in ("id", "sample_name", "genome_version", "kit", "status", "numberofmutations")}
    adim("resolve", _resolve)
    if not an:
        print("Ornek bulunamadi; kesif yarim kaldi.")
    else:
        adim("overview", lambda: {k: v for k, v in seq.dashboard(an).items()
                                  if not isinstance(v, (dict, list))})
        adim("kapsama", lambda: dict(list(seq.kapsama(an)[0].items())[:12]))
        adim("snv_count", lambda: seq.sanity(an))
        adim("hpo_search", lambda: seq.hpo_search("HP:0001250"))
        adim("gene_ids", lambda: seq.gene_ids(["SCN1A", "F8"]))
        adim("tema", lambda: seq.tema())
        tema = seq._tema
        if tema:
            adim("panel_snv", lambda: {"terim_sayisi": len(panel_indeksi(seq.panel(tema, "snv", taze=True))),
                                       "gruplar": [g.get("description") for g in
                                                   panel_gruplari(seq.panel(tema, "snv").get("panels"))]})
            adim("panel_cnv", lambda: {"terim_sayisi": len(panel_indeksi(seq.panel(tema, "cnv", taze=True)))})
            adim("sifirla", lambda: seq.tema_sifirla(tema) or "ok")
            adim("filtresiz_ilk_sayfa", lambda: {
                "ilk": [_ozet_satir(slim(x)) for x in duzlestir(
                    seq._json(seq.get("/api/ilcore/samples/%s/snv/%s/" % (an["id"], tema),
                                      params={"page": 1, "page_size": 5, "ordering": "-id"}), "snv").get("data"))]})
            # Filtre semantigi: tek checkbox, iki checkbox (OR mu AND mi?), aralik, HPO
            def _say(spec):
                seq.filtre_uygula(tema, spec)
                j = seq._json(seq.get("/api/ilcore/samples/%s/snv/%s/" % (an["id"], tema),
                                      params={"page": 1, "page_size": 2, "ordering": "-id"}), "snv")
                return {"total": j.get("total"), "ornek": [slim(x)["consequence"] for x in duzlestir(j.get("data"))]}
            adim("f_stop_gained", lambda: _say({"checkbox": [("consequence", "stop_gained")]}))
            adim("f_stop_gained_VEYA_frameshift", lambda: _say(
                {"checkbox": [("consequence", "stop_gained"), ("consequence", "frameshift_variant")]}))
            adim("f_pop_frekans_0_1", lambda: _say({"range": pop_frekans(0.1)}))
            adim("f_pop_frekans_0_1_nullsuz", lambda: _say(
                {"range": {("af_exomes", "af_exomes"): (None, 0.001, False)}}))
            adim("f_hom", lambda: _say({"checkbox": [("zyg", "HOM")]}))
            adim("f_clinvar_P_LP", lambda: _say({"checkbox": [("clinvar_clnsig", c) for c in CLINVAR_P]}))
            adim("f_hpo_nobet", lambda: _say({"hpo": ["HP:0001250"]}))
            adim("f_gen_SCN1A", lambda: _say({"genes": ["SCN1A"]}))
            adim("fenotipler", lambda: seq.fenotipler(tema)[:3])
            adim("top_reportable", lambda: {"n": len(seq.top_reportable(an)),
                                            "ilk": [_ozet_satir(slim(x)) for x in seq.top_reportable(an)[:3]]})
            adim("sifirla_son", lambda: seq.tema_sifirla(tema) or "ok")
            adim("cnv", lambda: {"n": len(seq.cnv_list(an, tema)),
                                 "ilk": cnv_rows(seq.cnv_list(an, tema)[:2])})
            adim("eksenler_tam", lambda: {k: len(v) for k, v in
                                          run_axes(seq, an, ["HP:0001250"], 0.02, 1.0).items()})

    with open(os.path.join(out, "kesif_ozet.json"), "w", encoding="utf-8") as f:
        json.dump(rapor, f, indent=1, ensure_ascii=False)
    with open(os.path.join(out, "ham_istekler.json"), "w", encoding="utf-8") as f:
        json.dump(_gizle(seq.ham_kayit), f, indent=1, ensure_ascii=False)
    seq.ham_kayit = None
    print("\nKesif yazildi: %s" % out)
    print("  kesif_ozet.json   - adim adim ozet")
    print("  ham_istekler.json - her istegin URL/durum/yanit (tokenlar gizli)")
    print("Bu klasoru Drive'da birakin; Claude'a 'Ilyome kesfi hazir' deyin.")


def main():
    ap = argparse.ArgumentParser(description="Ilyome WES/CES veri toplama")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("resolve"); p.add_argument("code")
    p = sub.add_parser("qc"); p.add_argument("code")
    p = sub.add_parser("hpo"); p.add_argument("keyword")
    p = sub.add_parser("kesfet"); p.add_argument("code"); p.add_argument("--out")
    p = sub.add_parser("scan"); p.add_argument("code"); p.add_argument("--hpo", nargs="*")
    p.add_argument("--out"); p.add_argument("--internal-max", type=float, default=0.02)
    p.add_argument("--max-freq", type=float, default=1.0)
    a = ap.parse_args()
    if not a.cmd:
        ap.print_help(); return 1
    seq = Seq()
    return {"resolve": cmd_resolve, "qc": cmd_qc, "hpo": cmd_hpo, "kesfet": cmd_kesfet,
            "scan": cmd_scan}[a.cmd](seq, a) or 0


if __name__ == "__main__":
    sys.exit(main())
