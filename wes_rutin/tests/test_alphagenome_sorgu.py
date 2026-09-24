# -*- coding: utf-8 -*-
"""Offline tests for alphagenome_sorgu.py and its rutin.py hook.

The container cannot reach the Atlas API, so a fake client builds real
DenseVariantScores protos and feeds them through the genuine
`atlas.convert_variant_scores_to_anndata`, which exercises the exact AnnData
shapes the module will see in production.
"""
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
# module lives next to this tests/ folder (repo layout) or in ../genomize_pipeline (scratch layout)
PIPE = next(p for p in (os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "genomize_pipeline"))
            if os.path.exists(os.path.join(p, "alphagenome_sorgu.py")))
sys.path.insert(0, PIPE)

from alphagenome.atlas import atlas                       # noqa: E402
from alphagenome.protos import atlas_service_pb2 as asp   # noqa: E402
from alphagenome.protos import dna_model_pb2 as dmp       # noqa: E402

import alphagenome_sorgu as AG                            # noqa: E402


# ---------------------------------------------------------------- fake Atlas
def _tracks(n, prefix, curies=None, biosample=True):
    rows = []
    for i in range(n):
        r = {"name": "%s_track%d" % (prefix, i), "strand": "."}
        if curies:
            r["ontology_curie"] = curies[i % len(curies)]
        if biosample:
            r["biosample_name"] = ["beyin", "karaciger", "kan"][i % 3]
        rows.append(r)
    return pd.DataFrame(rows, index=[str(i) for i in range(n)])


CURIES = ["UBERON:0000955", "UBERON:0002107", "UBERON:0000178"]
GENE_SCORERS = ["RNA_SEQ", "SPLICE_SITES", "SPLICE_SITE_USAGE", "SPLICE_JUNCTIONS", "POLYADENYLATION"]
TRACK_SCORERS = ["ATAC", "DNASE", "CHIP_TF", "CHIP_HISTONE", "CAGE", "PROCAP", "CONTACT_MAPS"]
META = {}
for _s in GENE_SCORERS + TRACK_SCORERS:
    n = 2 if _s in ("SPLICE_SITES", "CONTACT_MAPS") else 3
    META[_s] = atlas.ScorerMetadata(name=_s, is_signed=_s in ("RNA_SEQ", "ATAC", "DNASE", "CHIP_TF",
                                                                "CHIP_HISTONE", "CAGE", "PROCAP"),
                                    track_metadata=_tracks(n, _s, CURIES, biosample=_s != "SPLICE_SITES"))
# Sunucudaki gercek adlar (24.09.2026 listesi): AVI_SCORE (1 iz), AVI_SCORE_FEATURE_IMPORTANCE (SHAP, 18),
# AVI_SCORE_MODEL_FEATURES (ham ozellikler, 18) ve 7 modalite icin *_ACTIVE (aktif alel) skorlari.
META["AVI_SCORE"] = atlas.ScorerMetadata(name="AVI_SCORE", is_signed=False,
                                         track_metadata=_tracks(1, "AVI_SCORE", biosample=False))
_OZELLIK = pd.DataFrame({"name": ["MAX_ABS_ATAC", "MERGED_SPLICING", "ALPHAMISSENSE", "PHASTCONS_470_WAY"],
                         "strand": "."}, index=["0", "1", "2", "3"])
META["AVI_SCORE_FEATURE_IMPORTANCE"] = atlas.ScorerMetadata(
    name="AVI_SCORE_FEATURE_IMPORTANCE", is_signed=True, track_metadata=_OZELLIK.copy())
META["AVI_SCORE_MODEL_FEATURES"] = atlas.ScorerMetadata(
    name="AVI_SCORE_MODEL_FEATURES", is_signed=True, track_metadata=_OZELLIK.copy())
META["RNA_SEQ_ACTIVE"] = atlas.ScorerMetadata(name="RNA_SEQ_ACTIVE", is_signed=False,
                                              track_metadata=_tracks(3, "RNA_SEQ", CURIES))
META["DNASE_ACTIVE"] = atlas.ScorerMetadata(name="DNASE_ACTIVE", is_signed=False,
                                            track_metadata=_tracks(3, "DNASE", CURIES))
ACTIVE_SCORERS = ["RNA_SEQ_ACTIVE", "DNASE_ACTIVE"]

# per-variant designed scores: key -> {scorer: (raw matrix, quantile matrix or None)}
STRONG = "chr12:13865958:C:T"     # splicing strong + AVI PHRED 31.4 + DNase signal (active tissue)
MILD = "chr6:80168944:C:T"        # expression signal in an active tissue (Bonferroni-significant) + a saturated
                                  # kantil -1.0 in an INACTIVE tissue that must be ignored
NOTFOUND = "chr1:12345:A:G"       # Atlas miss -> model fallback
INDEL = "chr17:7587073:TAGA:T"    # Atlas (v0.9) rejects ref/alt length > 1 -> model fallback
BAD = "chrM:123:A:G"              # cannot be queried


def _f32(a):
    return np.asarray(a, dtype=np.float32).tobytes()


def _gene_meta(names):
    md = asp.GeneScorersMetadata()
    for i, g in enumerate(names):
        gm = md.metadata.add()
        gm.gene_id = "ENSG%011d.3" % i
        gm.name = g
        if hasattr(gm, "strand"):
            try:
                gm.strand = dmp.Strand.Value("STRAND_POSITIVE")
            except ValueError:
                pass
    return asp.Metadata(gene_scorers=md)


def _design(key):
    genes = ["GRIN2B", "CACNA1C"]
    d = {}
    for s in GENE_SCORERS:
        n = len(META[s].track_metadata)
        raw = np.full((2, n), 0.01, dtype=np.float32)
        q = np.full((2, n), 0.30, dtype=np.float32)
        if key == STRONG and s == "SPLICE_SITES":
            raw[0, 1], q[0, 1] = 0.82, 0.9995
        if key == STRONG and s == "SPLICE_SITE_USAGE":
            raw[0, 0], q[0, 0] = 0.55, 0.998
        if key == STRONG and s == "SPLICE_JUNCTIONS":
            raw[0, 2], q[0, 2] = 2.5, 0.997
        if key == MILD and s == "RNA_SEQ":
            raw[1, 0], q[1, 0] = -0.9, -0.9999       # CACNA1C, beyin: aktif doku -> anlamli
            raw[0, 1], q[0, 1] = -0.05, -1.0         # GRIN2B, karaciger: gen ifade edilmiyor -> yok sayilmali
        d[s] = (raw, q, genes)
    # aktif alel (max(REF,ALT)) matrisleri: modalite ile ayni sekil
    act = np.array([[0.0, 0.0, 0.0], [10.0, 0.5, 9.0]], dtype=np.float32)   # GRIN2B hic aktif degil
    d["RNA_SEQ_ACTIVE"] = (act, None, genes)
    for s in TRACK_SCORERS:
        n = len(META[s].track_metadata)
        raw = np.full((1, n), 0.02, dtype=np.float32)
        q = np.full((1, n), 0.10, dtype=np.float32)
        if key == STRONG and s == "DNASE":
            raw[0, 2], q[0, 2] = -1.4, -0.999        # kan: aktif -> p = 2 x 0.001 = 0.002
            raw[0, 1], q[0, 1] = -0.3, -0.9999       # karaciger: aktif degil -> yok sayilir
        d[s] = (raw, q, None)
    d["DNASE_ACTIVE"] = (np.array([[5.0, 0.2, 8.0]], dtype=np.float32), None, None)
    # AVI: X = model logit (SHAP toplami), kalibre kantil -> PHRED. 0.999276 -> 31.4 ; 0.8095 -> 7.2
    d["AVI_SCORE"] = (np.array([[3.1 if key == STRONG else 0.4]], dtype=np.float32),
                      np.array([[0.999276 if key == STRONG else 0.8095]], dtype=np.float32), None)
    d["AVI_SCORE_FEATURE_IMPORTANCE"] = (np.array([[0.1, 2.3, 0.4, 0.9]], dtype=np.float32), None, None)
    d["AVI_SCORE_MODEL_FEATURES"] = (np.array([[0.02, 1.87, 0.0, 1.0]], dtype=np.float32), None, None)
    return d


def _proto(key, requested):
    krom, poz, ref, alt = key.split(":")
    dvs = asp.DenseVariantScores(variant=dmp.Variant(chromosome=krom, position=int(poz),
                                                     reference_bases=ref, alternate_bases=alt))
    for s, (raw, q, genes) in _design(key).items():
        if s not in requested:
            continue
        sc = dvs.scores.add()
        sc.variant_scorer.name = s
        sc.variant_scorer.is_signed = META[s].is_signed
        sc.shape.extend(list(raw.shape))
        sc.scores = _f32(raw)
        if q is not None:
            sc.calibrated_scores = _f32(q)
        if genes:
            sc.metadata.append(_gene_meta(genes))
    return dvs


class _SahteCall(Exception):
    """grpc.Call gibi .code() donduren sahte neden (handle_rpc_error 'raise ... from error')."""
    def __init__(self, ad):
        super(_SahteCall, self).__init__(ad)
        self._ad = ad

    def code(self):
        return types.SimpleNamespace(name=self._ad)


def _grpc_hata(kod, mesaj):
    e = IndexError(mesaj) if kod == "OUT_OF_RANGE" else ValueError(mesaj)
    e.__cause__ = _SahteCall(kod)
    return e


class FakeClient(object):
    def __init__(self):
        self.calls = []

    def scorer_metadata(self):
        return dict(META)

    def query_variants(self, variants, requested_scorers, ontology_terms=None, gene_ids=None,
                       gene_names=None, progress_bar=True, max_workers=10):
        assert len(variants) == 1
        v = variants[0]
        key = "%s:%d:%s:%s" % (v.chromosome, v.position, v.reference_bases, v.alternate_bases)
        self.calls.append(key)
        if key == NOTFOUND:
            raise _grpc_hata("NOT_FOUND", "Variant not found")   # mirrors handle_rpc_error NOT_FOUND
        if len(v.reference_bases) > 1 or len(v.alternate_bases) > 1:
            raise _grpc_hata("INVALID_ARGUMENT", "Reference or alternate bases length > 1 not yet supported.")
        meta = {k: m.track_metadata.copy() for k, m in META.items()}
        return atlas.convert_variant_scores_to_anndata([_proto(key, set(requested_scorers))], meta)


class FakeSorgu(AG.AtlasSorgu):
    def __init__(self, **kw):
        super(FakeSorgu, self).__init__(key="test-key", **kw)
        self.fake = FakeClient()
        self.model_calls = []

    def baglan(self):
        self._client = self.fake
        self.paket_surum = "0.9.0-test"
        return self._client

    def _model_tek(self, v):
        key = "%s:%d:%s:%s" % v
        self.model_calls.append(key)
        meta = {k: m.track_metadata.copy() for k, m in META.items()}
        # live model has no AVI; return modality scorers only (neutral design for NOTFOUND)
        return atlas.convert_variant_scores_to_anndata(
            [_proto(key, set(GENE_SCORERS + TRACK_SCORERS))], meta)


def _write_csv(path, rows):
    cols = ["key", "gene", "transcript", "hgvsc", "hgvsp", "consequence", "af_max", "internal_freq"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _kanit(tmp):
    os.makedirs(tmp, exist_ok=True)
    _write_csv(os.path.join(tmp, "222080_fenotip_iliskili.csv"), [
        {"key": STRONG, "gene": "GRIN2B", "hgvsc": "NM_000834.5:c.251G>A", "hgvsp": "p.(Arg84His)",
         "consequence": "Missense Variant", "af_max": "0.000012", "internal_freq": "0"},
        {"key": MILD, "gene": "BCKDHB", "hgvsc": "NM_183050.4:c.547C>T", "hgvsp": "p.(Arg183Trp)",
         "consequence": "Missense Variant", "af_max": "0.0003", "internal_freq": "0.01"},
        {"key": "chr2:100:A:T", "gene": "COMMON", "consequence": "Synonymous", "af_max": "0.2"},
        {"key": "chr3:200:A:T", "gene": "ARTEFAKT", "consequence": "Missense", "af_max": "0", "internal_freq": "0.05"},
    ])
    _write_csv(os.path.join(tmp, "222080_nadir_lof.csv"), [
        {"key": NOTFOUND, "gene": "SCN1A", "hgvsc": "c.1A>G", "consequence": "Start Lost", "af_max": ""},
        {"key": STRONG, "gene": "GRIN2B", "consequence": "Missense Variant", "af_max": "0.000012"},
        {"key": INDEL, "gene": "MPDU1", "hgvsc": "c.10_12del", "consequence": "Inframe Deletion", "af_max": "0"},
    ])
    _write_csv(os.path.join(tmp, "DENOVO_nadir_lof.csv"), [
        {"key": BAD, "gene": "MT-ND1", "consequence": "Missense", "af_max": ""},
    ])
    _write_csv(os.path.join(tmp, "222081_fenotip_iliskili.csv"), [
        {"key": "chr9:999:G:A", "gene": "PARENTONLY", "consequence": "Missense", "af_max": "0"},
    ])
    _write_csv(os.path.join(tmp, "222080_cnv.csv"), [])
    _write_csv(os.path.join(tmp, "222080_nadir_lof_ARTEFAKT.csv"), [{"key": "chr4:1:A:T", "gene": "X"}])


class YardimciTest(unittest.TestCase):
    def test_yuvarla_nan(self):
        self.assertIsNone(AG._yuvarla(float("nan")))
        self.assertIsNone(AG._yuvarla(float("inf")))
        self.assertIsNone(AG._yuvarla("x"))
        self.assertEqual(AG._yuvarla("0.12345", 3), 0.123)

    def test_lof_ve_siralama(self):
        self.assertTrue(AG.lof_mu("Stop Gained"))
        self.assertTrue(AG.lof_mu("frameshift_variant"))
        self.assertFalse(AG.lof_mu("Missense Variant"))
        a = {"kategori": "yuksek", "avi": 52.0, "splicing_birlesik": 0.1, "duzenleyici_sinyal": None}
        b = {"kategori": "yuksek", "avi": 21.0, "splicing_birlesik": 1.9, "duzenleyici_sinyal": "DNASE- (kan)"}
        c = {"kategori": "orta", "avi": 12.0}
        self.assertEqual(sorted([a, b, c], key=AG.sinyal_anahtari), [b, a, c])
        r = {k: None for k in AG.OZET_SUTUNLAR}
        r.update({"avi": 48.0, "avi_yorum": AG.avi_yorumla(48.0), "consequence": "Stop Gained"})
        self.assertIn("LoF varyantinda yuksek AVI beklenen", AG.yorumla(r))
        r["consequence"] = "Missense Variant"
        self.assertNotIn("LoF varyantinda", AG.yorumla(r))

    def test_sayim_cumlesi(self):
        s = AG._sayim_cumlesi({"atlas": 5, "model": 2, "bulunamadi": 1, "hata": 1, "sorulamadi": 1})
        self.assertIn("5 varyant Atlas'ta", s)
        self.assertIn("2 varyant canlı", s)
        self.assertIn("3 varyant skorlanamamıştır", s)
        s = AG._sayim_cumlesi({"atlas": 3})
        self.assertNotIn("canlı", s)
        self.assertNotIn("skorlanamamıştır", s)

    def test_nan_avi_ve_detay(self):
        import anndata
        s = FakeSorgu()
        s._secili = s.secili_skorlar()
        a = anndata.AnnData(X=np.array([[np.nan, 0.5]], dtype=np.float32),
                            obs=pd.DataFrame({"variant": ["v"]}, index=["0"]),
                            var=pd.DataFrame({"strand": [".", "."]}, index=["t0", "t1"]),
                            layers={"quantiles": np.array([[np.nan, 0.995]], dtype=np.float32)})
        avi = anndata.AnnData(X=np.array([[np.nan]], dtype=np.float32),
                              obs=pd.DataFrame({"variant": ["v"]}, index=["0"]), var=pd.DataFrame(index=["0"]))
        oz, det = s._ozetle("chr1:1:A:T", {"ATAC": a, "AVI_SCORE": avi}, "AVI_SCORE", None, "atlas")
        self.assertNotIn("avi", oz)
        self.assertNotIn("avi_ham", oz)
        self.assertEqual(oz["atac_kantil"], 0.995)
        self.assertEqual(oz["atac_doku"], "t1")            # var without name/biosample -> index
        self.assertEqual(len(det), 1)                       # NaN cell excluded from detail rows
        self.assertEqual(det[0]["kantil"], 0.995)


class VaryantAyristirTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(AG.varyant_ayristir("12:13865958:C:T"), ("chr12", 13865958, "C", "T"))
        self.assertEqual(AG.varyant_ayristir("chrX:100:AT:A"), ("chrX", 100, "AT", "A"))
        self.assertIsNone(AG.varyant_ayristir(BAD))
        self.assertIsNone(AG.varyant_ayristir("chr1:5:A:A"))
        self.assertIsNone(AG.varyant_ayristir("chr1:5:N:A"))
        self.assertIsNone(AG.varyant_ayristir("chr1:5:-:A"))
        self.assertIsNone(AG.varyant_ayristir("nonsense"))

    def test_avi_yorum(self):
        self.assertIn("en yuksek ~%1", AG.avi_yorumla(20))
        self.assertIn("%0.1", AG.avi_yorumla(30))
        self.assertTrue(AG.avi_yorumla(46).startswith("PHRED 46.0"))
        self.assertIsNone(AG.avi_yorumla(None))


class AdayToplaTest(unittest.TestCase):
    def test_topla(self):
        tmp = tempfile.mkdtemp()
        _kanit(tmp)
        dosyalar = [os.path.join(tmp, d) for d in os.listdir(tmp)
                    if d.startswith("222080_") or d.startswith("DENOVO_")]
        adaylar = AG.adaylari_topla(tmp, dosyalar=dosyalar)
        keys = [a["key"] for a in adaylar]
        self.assertIn(STRONG, keys)
        self.assertIn(MILD, keys)
        self.assertIn(NOTFOUND, keys)
        self.assertIn(BAD, keys)
        self.assertNotIn("chr2:100:A:T", keys)      # common
        self.assertNotIn("chr3:200:A:T", keys)      # internal artefact
        self.assertNotIn("chr4:1:A:T", keys)        # ARTEFAKT file skipped
        self.assertNotIn("chr9:999:G:A", keys)      # parent-only file not given
        strong = [a for a in adaylar if a["key"] == STRONG][0]
        self.assertEqual(strong["gene"], "GRIN2B")
        self.assertIn("fenotip_iliskili", strong["kaynak"])
        self.assertIn("nadir_lof", strong["kaynak"])
        self.assertEqual(keys[0], BAD)              # DENOVO first by priority

    def test_ayni_varyant_farkli_yazim(self):
        tmp = tempfile.mkdtemp()
        _kanit(tmp)
        with open(os.path.join(tmp, "222080_tier.csv"), "w", encoding="utf-8-sig", newline="") as f:
            f.write("key,gene,af_max\n12:13865958:C:T,GRIN2B,0\n12:13865958:C:T,GRIN2B,0\n")
        dosyalar = [os.path.join(tmp, d) for d in os.listdir(tmp) if d.startswith("222080_")]
        adaylar = AG.adaylari_topla(tmp, dosyalar=dosyalar)
        hits = [a for a in adaylar if AG.varyant_ayristir(a["key"]) == ("chr12", 13865958, "C", "T")]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["key"], "12:13865958:C:T")          # tier has priority
        self.assertEqual(set(hits[0]["kaynak"].split(",")),
                         {"222080_tier", "222080_nadir_lof", "222080_fenotip_iliskili"})


class SorguTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _kanit(self.tmp)
        self.dosyalar = [os.path.join(self.tmp, d) for d in os.listdir(self.tmp)
                         if d.startswith("222080_") or d.startswith("DENOVO_")]
        self.adaylar = AG.adaylari_topla(self.tmp, dosyalar=self.dosyalar)

    def test_secili_skorlar_and_avi(self):
        s = FakeSorgu()
        sec = s.secili_skorlar()
        self.assertIn("RNA_SEQ", sec)
        self.assertIn("AVI_SCORE", sec)
        self.assertIn("AVI_SCORE_FEATURE_IMPORTANCE", sec)
        self.assertIn("RNA_SEQ_ACTIVE", sec)                 # aktif alel skorlari kapilama icin istenir
        self.assertIn("DNASE_ACTIVE", sec)
        self.assertNotIn("ATAC_ACTIVE", sec)                 # sunucuda yoksa istenmez
        self.assertEqual(s.avi_adlari(sec), ("AVI_SCORE", "AVI_SCORE_FEATURE_IMPORTANCE"))

    def test_sorgula(self):
        s = FakeSorgu(model=True, model_max=25)
        ozet, detay = s.sorgula(self.adaylar, onbellek=None)
        by = {r["key"]: r for r in ozet}
        self.assertEqual(len(ozet), len(self.adaylar))
        st = by[STRONG]
        self.assertEqual(st["durum"], "atlas")
        self.assertAlmostEqual(st["avi"], 31.4, places=1)                # PHRED kalibre kantilden
        self.assertAlmostEqual(st["avi_ham"], 3.1, places=2)              # logit ayrica
        self.assertAlmostEqual(st["avi_kantil"], 0.999276, places=5)
        self.assertEqual(st["kategori"], "yuksek")
        self.assertAlmostEqual(st["splice_site_ham"], 0.82, places=2)
        self.assertAlmostEqual(st["splicing_birlesik"], 0.82 + 0.55 + 2.5 / 5.0, places=2)
        self.assertEqual(st["splice_site_gen"], "GRIN2B")
        self.assertAlmostEqual(st["dnase_kantil"], -0.999, places=3)      # aktif doku (kan), karaciger degil
        self.assertEqual(st["dnase_doku"], "kan")
        self.assertAlmostEqual(st["dnase_p"], 0.002, places=3)            # 2 aktif hucre x 0.001
        self.assertAlmostEqual(st["dnase_aktif"], 1.0, places=2)
        self.assertEqual(st["duzenleyici_sinyal"], "DNASE- (kan)")
        self.assertIn("MERGED_SPLICING:+2.30", st["avi_katki"])
        self.assertIn("splicing etkisi guclu", st["yorum"])
        self.assertIn("DNase kantil -0.999", st["yorum"])
        self.assertIn("PHRED 31.4", st["avi_yorum"])
        mi = by[MILD]
        self.assertEqual(mi["kategori"], "orta")                          # yalniz duzeltilmis sinyalle
        self.assertAlmostEqual(mi["avi"], 7.2, places=1)
        self.assertAlmostEqual(mi["ekspresyon_kantil"], -0.9999, places=4)
        self.assertEqual(mi["ekspresyon_gen"], "CACNA1C")                 # GRIN2B/karaciger (-1.0, inaktif) degil
        self.assertEqual(mi["ekspresyon_doku"], "beyin")
        self.assertEqual(mi["duzenleyici_sinyal"], "RNA_SEQ- (beyin)")
        self.assertIn("azalma", mi["yorum"])
        self.assertIn("aktif doku", mi["yorum"])
        nf = by[NOTFOUND]
        self.assertEqual(nf["durum"], "model")
        self.assertIsNone(nf["avi"])
        self.assertEqual(nf["kategori"], "dusuk")
        self.assertIn("ongorulmuyor", nf["yorum"])
        self.assertIn("anlamli sinyal yok", nf["yorum"])
        ind = by[INDEL]
        self.assertEqual(ind["durum"], "model")                           # Atlas reddetti -> canli model
        self.assertIn("indel/MNV", ind["yorum"])
        self.assertEqual(sorted(s.model_calls), sorted([NOTFOUND, INDEL]))
        self.assertFalse(s.hatalar)
        bad = by[BAD]
        self.assertEqual(bad["durum"], "sorulamadi")
        self.assertEqual(bad["kategori"], "-")
        # detail rows: top-N per scorer, gene carried from candidate
        st_det = [d for d in detay if d["key"] == STRONG]
        self.assertTrue(st_det)
        self.assertEqual(st_det[0]["gene"], "GRIN2B")
        self.assertLessEqual(max(sum(1 for d in st_det if d["skor"] == sc) for sc in set(d["skor"] for d in st_det)),
                             AG.DETAY_DOKU_N)
        # AVI and active-allele scorers are not detail rows; detail rows carry activity
        self.assertFalse([d for d in st_det if d["skor"] in ("AVI_SCORE", "DNASE_ACTIVE", "RNA_SEQ_ACTIVE")])
        dn = [d for d in st_det if d["skor"] == "DNASE"]
        self.assertTrue(dn and all(d["doku"] != "karaciger" for d in dn))   # inaktif doku detayda da yok
        self.assertEqual(dn[0]["aktif"], 1.0)
        # input order preserved
        self.assertEqual([r["key"] for r in ozet], [a["key"] for a in self.adaylar])

    def test_model_kapali(self):
        s = FakeSorgu(model=False)
        ozet, _ = s.sorgula(self.adaylar, onbellek=None)
        nf = [r for r in ozet if r["key"] == NOTFOUND][0]
        self.assertEqual(nf["durum"], "bulunamadi")
        self.assertEqual(s.model_calls, [])

    def test_onbellek(self):
        s = FakeSorgu(model=False)
        ob = AG.Onbellek(os.path.join(self.tmp, "cache"))
        s.sorgula(self.adaylar, onbellek=ob)
        n1 = len(s.fake.calls)
        s2 = FakeSorgu(model=False)
        ozet2, detay2 = s2.sorgula(self.adaylar, onbellek=ob)
        self.assertEqual(len(s2.fake.calls), 0)          # everything served from cache
        self.assertEqual(n1, 4)                           # STRONG, MILD, NOTFOUND, INDEL (BAD never queried)
        self.assertEqual([r["key"] for r in ozet2], [a["key"] for a in self.adaylar])
        self.assertTrue([d for d in detay2 if d["key"] == STRONG])

    def test_doku_filtresi(self):
        s = FakeSorgu(model=False, doku=["UBERON:0000955"])   # only 'beyin' tracks (index 0)
        ozet, _ = s.sorgula(self.adaylar, onbellek=None)
        st = [r for r in ozet if r["key"] == STRONG][0]
        # DNase peak sits in track 2 (kan) -> filtered out; summary must fall back to brain track
        self.assertEqual(st["dnase_doku"], "beyin")
        self.assertNotAlmostEqual(st["dnase_kantil"] or 0, -0.999, places=2)


class CalistirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _kanit(self.tmp)
        self.dosyalar = [os.path.join(self.tmp, d) for d in os.listdir(self.tmp)
                         if d.startswith("222080_") or d.startswith("DENOVO_")]
        self.adaylar = AG.adaylari_topla(self.tmp, dosyalar=self.dosyalar)
        self._orig = AG.AtlasSorgu
        self._orig_key = AG.api_key
        AG.AtlasSorgu = FakeSorgu
        AG.api_key = lambda: "test-key"

    def tearDown(self):
        AG.AtlasSorgu = self._orig
        AG.api_key = self._orig_key

    def test_calistir_yazar(self):
        oz = AG.calistir(self.tmp, adaylar=self.adaylar, genome="hg38", onbellek=False, sessiz=True)
        self.assertEqual(oz["durum"], "tamam")
        self.assertEqual(oz["aday"], 5)
        self.assertEqual(oz["atlas"], 2)
        self.assertEqual(oz["model"], 2)
        self.assertEqual(oz["sorulamadi"], 1)
        self.assertEqual(oz["hata"], 0)
        self.assertEqual(oz["kategori"]["yuksek"], 1)
        self.assertEqual(oz["kategori"]["orta"], 1)
        self.assertEqual(oz["yuksek_varyantlar"][0]["gene"], "GRIN2B")
        for ad in ("alphagenome.csv", "alphagenome_detay.csv", "alphagenome_ozet.json", "alphagenome_rapor.txt"):
            self.assertTrue(os.path.exists(os.path.join(self.tmp, ad)), ad)
        rows = AG.csv_oku(os.path.join(self.tmp, "alphagenome.csv"))
        self.assertEqual(rows[0]["key"], STRONG)               # sorted: yuksek first
        self.assertEqual(rows[0]["kategori"], "yuksek")
        self.assertEqual(list(rows[0].keys()), AG.OZET_SUTUNLAR)
        with open(os.path.join(self.tmp, "alphagenome_rapor.txt"), encoding="utf-8") as f:
            rapor = f.read()
        self.assertIn("GRIN2B", rapor)
        self.assertIn("ALPHAGENOME ATLAS DEĞERLENDİRMESİ", rapor)
        self.assertIn("Analiz Yöntemi", rapor)
        self.assertIn("10.1038/s41586-025-10014-0", rapor)
        self.assertIn("31,4", rapor)
        j = json.load(open(os.path.join(self.tmp, "alphagenome_ozet.json"), encoding="utf-8"))
        self.assertIn("AVI_SCORE", j["sunucu_skorlari"])
        self.assertEqual(j["avi_skoru"], "AVI_SCORE")
        # second read via ozet_oku
        oz2, satirlar = AG.ozet_oku(self.tmp)
        self.assertEqual(oz2["durum"], "tamam")
        self.assertEqual(len(satirlar), 5)

    def test_hg19_atlanir(self):
        oz = AG.calistir(self.tmp, adaylar=self.adaylar, genome="hg19", onbellek=False, sessiz=True)
        self.assertEqual(oz["durum"], "atlandi")
        self.assertIn("hg19", oz["neden"])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "alphagenome_ozet.json")))

    def test_anahtar_yok(self):
        AG.api_key = lambda: None
        oz = AG.calistir(self.tmp, adaylar=self.adaylar, genome="hg38", onbellek=False, sessiz=True)
        self.assertEqual(oz["durum"], "atlandi")
        self.assertIn("ALPHAGENOME_API_KEY", oz["neden"])
        bolum, yontem, kaynak = AG.rapor_metni(oz, [])
        self.assertIn("çalıştırılamadı", bolum)
        self.assertEqual(yontem, "")

    def test_baglanti_hatasi(self):
        class Kirik(FakeSorgu):
            def baglan(self):
                raise TimeoutError("channel not ready")
        AG.AtlasSorgu = Kirik
        oz = AG.calistir(self.tmp, adaylar=self.adaylar, genome="hg38", onbellek=False, sessiz=True)
        self.assertEqual(oz["durum"], "hata")
        self.assertIn("TimeoutError", oz["neden"])

    def test_aday_yok(self):
        oz = AG.calistir(self.tmp, adaylar=[], genome="hg38", onbellek=False, sessiz=True)
        self.assertEqual(oz["durum"], "tamam")
        self.assertEqual(oz["aday"], 0)

    def test_yazim_hatasi_istisna_firlatmaz(self):
        """Review #2: sorgula/yaz_csv/rapor asamasindaki bir hata calistir()'dan disari cikmamali."""
        orig = AG.yaz_csv
        AG.yaz_csv = lambda *a, **k: (_ for _ in ()).throw(OSError("disk dolu"))
        try:
            oz = AG.calistir(self.tmp, adaylar=self.adaylar, genome="hg38", onbellek=False, sessiz=True)
        finally:
            AG.yaz_csv = orig
        self.assertEqual(oz["durum"], "hata")
        self.assertIn("disk dolu", oz["neden"])
        self.assertIn(oz["neden"], oz["hatalar"])
        j = json.load(open(os.path.join(self.tmp, "alphagenome_ozet.json"), encoding="utf-8"))
        self.assertEqual(j["durum"], "hata")

    def test_varyant_komutu_bulunulan_klasoru_kirletmez(self):
        """Review #2: `--varyant` klasorsuz cagrildiginda ciktilar cwd'ye degil gecici klasore yazilir."""
        cwd, argv, out = os.getcwd(), sys.argv, sys.stdout
        bos = tempfile.mkdtemp()
        os.chdir(bos)
        sys.argv = ["alphagenome_sorgu.py", "--varyant", STRONG, "--onbellek-yok"]
        sys.stdout = io.StringIO()
        try:
            AG.main()
            cikti = sys.stdout.getvalue()
        finally:
            sys.stdout, sys.argv = out, argv
            os.chdir(cwd)
        self.assertEqual(os.listdir(bos), [])
        self.assertIn(STRONG, cikti)
        self.assertIn('"durum": "tamam"', cikti)
        self.assertNotIn('"rapor_dosya"', cikti)
        self.assertFalse([d for d in os.listdir(tempfile.gettempdir()) if d.startswith("alphagenome_")
                          and os.path.exists(os.path.join(tempfile.gettempdir(), d, "alphagenome.csv"))])


class IncelemeDuzeltmeTest(unittest.TestCase):
    """Bagimsiz incelemede bulunan kusurlarin regresyon testleri."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _kanit(self.tmp)
        self.dosyalar = [os.path.join(self.tmp, d) for d in os.listdir(self.tmp)
                         if d.startswith("222080_") or d.startswith("DENOVO_")]
        self.adaylar = AG.adaylari_topla(self.tmp, dosyalar=self.dosyalar)

    def test_bulunamadi_mi(self):
        self.assertTrue(AG._bulunamadi_mi(_grpc_hata("NOT_FOUND", "x")))
        self.assertTrue(AG._bulunamadi_mi(_grpc_hata("OUT_OF_RANGE", "x")))
        self.assertFalse(AG._bulunamadi_mi(_grpc_hata("INVALID_ARGUMENT", "Invalid filter")))
        self.assertFalse(AG._bulunamadi_mi(ValueError("var must have as many rows as X has columns")))
        self.assertTrue(AG._bulunamadi_mi(ValueError("Variant not found")))

    def test_gecersiz_arguman_hata_sayilir(self):
        class Kirik(FakeSorgu):
            def _atlas_tek(self, v):
                raise _grpc_hata("INVALID_ARGUMENT", "Invalid filter")
        s = Kirik(model=True)
        ozet, _ = s.sorgula(self.adaylar, onbellek=None)
        durumlar = {r["key"]: r["durum"] for r in ozet}
        self.assertEqual(durumlar[STRONG], "hata")
        self.assertEqual(s.model_calls, [])                    # hata -> model denenmez
        self.assertTrue(s.hatalar)

    def test_hata_onbellege_girmez(self):
        ob = AG.Onbellek(os.path.join(self.tmp, "cache"))
        class Zaman(FakeSorgu):
            def _atlas_tek(self, v):
                raise TimeoutError("Deadline Exceeded")
        s1 = Zaman(model=False)
        ozet1, _ = s1.sorgula(self.adaylar, onbellek=ob)
        self.assertEqual({r["durum"] for r in ozet1 if r["key"] != BAD}, {"hata"})
        s2 = FakeSorgu(model=False)
        ozet2, _ = s2.sorgula(self.adaylar, onbellek=ob)
        self.assertEqual(len(s2.fake.calls), 4)                 # yeniden soruldu
        self.assertEqual([r for r in ozet2 if r["key"] == STRONG][0]["durum"], "atlas")

    def test_onbellek_model_bayragi(self):
        ob = AG.Onbellek(os.path.join(self.tmp, "cache"))
        s1 = FakeSorgu(model=False)
        s1.sorgula(self.adaylar, onbellek=ob)                  # NOTFOUND -> bulunamadi (model kapali)
        s2 = FakeSorgu(model=True)
        ozet2, _ = s2.sorgula(self.adaylar, onbellek=ob)
        nf = [r for r in ozet2 if r["key"] == NOTFOUND][0]
        self.assertEqual(nf["durum"], "model")                 # model acilinca yeniden denendi
        self.assertEqual(sorted(s2.model_calls), sorted([NOTFOUND, INDEL]))
        s3 = FakeSorgu(model=True)
        s3.sorgula(self.adaylar, onbellek=ob)
        self.assertEqual(s3.model_calls, [])                   # model sonucu onbellekten

    def test_kaynak_korunur(self):
        s = FakeSorgu(model=False)
        ozet, _ = s.sorgula(self.adaylar, onbellek=None)
        st = [r for r in ozet if r["key"] == STRONG][0]
        self.assertIn("222080_nadir_lof", st["kaynak"])
        self.assertEqual(st["durum"], "atlas")

    def test_ham_ve_kantil_ayni_hucre(self):
        import anndata
        s = FakeSorgu()
        s._secili = s.secili_skorlar()
        X = np.array([[-0.9, .05, .05], [.05, .05, .40]], dtype=np.float32)
        Q = np.array([[-.80, .1, .1], [.1, .1, .97]], dtype=np.float32)
        a = anndata.AnnData(X=X, obs=pd.DataFrame({"gene_name": ["GENE1", "GENE2"], "variant": ["v", "v"]},
                                                  index=["0", "1"]),
                            var=_tracks(3, "RNA_SEQ", CURIES), layers={"quantiles": Q})
        oz, det = s._ozetle("chr1:1:A:T", {"RNA_SEQ": a}, None, None, "atlas")
        self.assertEqual(oz["ekspresyon_kantil"], 0.97)
        self.assertEqual(oz["ekspresyon_gen"], "GENE2")
        self.assertAlmostEqual(oz["ekspresyon_ham"], 0.40, places=2)   # ayni hucre
        self.assertEqual(oz["ekspresyon_doku"], "kan")

    def test_splicing_birlesik_max_ham(self):
        import anndata
        s = FakeSorgu()
        s._secili = s.secili_skorlar()
        X = np.array([[0.9, 0.1]], dtype=np.float32)
        Q = np.array([[0.5, 0.99]], dtype=np.float32)     # kantil hucresi != max ham hucresi
        a = anndata.AnnData(X=X, obs=pd.DataFrame({"gene_name": ["G"], "variant": ["v"]}, index=["0"]),
                            var=_tracks(2, "SPLICE_SITES", CURIES), layers={"quantiles": Q})
        oz, _ = s._ozetle("chr1:1:A:T", {"SPLICE_SITES": a}, None, None, "atlas")
        self.assertAlmostEqual(oz["splicing_birlesik"], 0.9, places=2)   # makale: max ham
        self.assertAlmostEqual(oz["splice_site_ham"], 0.1, places=2)      # tablo: kantil hucresi

    def test_tum_nan_kantil(self):
        import anndata
        s = FakeSorgu()
        s._secili = s.secili_skorlar()
        a = anndata.AnnData(X=np.array([[0.3, -0.2]], dtype=np.float32),
                            obs=pd.DataFrame({"variant": ["v"]}, index=["0"]),
                            var=_tracks(2, "ATAC", CURIES),
                            layers={"quantiles": np.array([[np.nan, np.nan]], dtype=np.float32)})
        oz, det = s._ozetle("chr1:1:A:T", {"ATAC": a}, None, None, "atlas")
        self.assertEqual(oz["atac_ham"], 0.3)
        self.assertIsNone(oz["atac_kantil"])
        self.assertTrue(det)

    def test_nan_biosample(self):
        var = pd.DataFrame({"name": ["t0", "t1"], "biosample_name": ["brain", np.nan]}, index=["0", "1"])
        self.assertEqual(AG.AtlasSorgu._doku_adlari(var), ["brain", "t1"])

    def test_avi_phred(self):
        self.assertAlmostEqual(AG.avi_phred(0.9), 10.0, places=1)
        self.assertAlmostEqual(AG.avi_phred(0.99), 20.0, places=1)
        self.assertAlmostEqual(AG.avi_phred(0.999276), 31.4, places=1)
        self.assertEqual(AG.avi_phred(1.0), 60.0)
        self.assertEqual(AG.avi_phred(-0.9), 10.0)                        # isaret goz ardi
        self.assertIsNone(AG.avi_phred(None))
        self.assertIsNone(AG.avi_phred(float("nan")))

    def test_avi_kantilsiz_ham_kalir(self):
        """Sunucu AVI icin kalibre kantil gondermezse PHRED hesaplanmaz, ham (logit) yazilir."""
        import anndata
        s = FakeSorgu()
        s._secili = s.secili_skorlar()
        avi = anndata.AnnData(X=np.array([[2.4]], dtype=np.float32),
                              obs=pd.DataFrame({"variant": ["v"]}, index=["0"]), var=pd.DataFrame(index=["0"]))
        oz, _ = s._ozetle("chr1:1:A:T", {"AVI_SCORE": avi}, "AVI_SCORE", None, "atlas")
        self.assertNotIn("avi", oz)
        self.assertAlmostEqual(oz["avi_ham"], 2.4, places=2)
        r = {k: None for k in AG.OZET_SUTUNLAR}; r.update(oz)
        self.assertEqual(AG.kategori(r), "dusuk")
        self.assertIn("PHRED hesaplanamadi", AG.yorumla(r))

    def test_coklu_karsilastirma(self):
        """Yuzlerce izde max |kantil| ~0,99 sanstir: Bonferroni sonrasi anlamli sayilmamali."""
        import anndata
        s = FakeSorgu()
        s._secili = s.secili_skorlar()
        n = 300
        rng = np.random.RandomState(0)
        Q = rng.uniform(-0.999, 0.999, size=(1, n)).astype(np.float32)   # null: uniform kantiller
        X = (Q * 0.1).astype(np.float32)
        a = anndata.AnnData(X=X, obs=pd.DataFrame({"variant": ["v"]}, index=["0"]),
                            var=_tracks(n, "ATAC", CURIES), layers={"quantiles": Q})
        oz, _ = s._ozetle("chr1:1:A:T", {"ATAC": a}, None, None, "atlas")
        self.assertGreaterEqual(abs(oz["atac_kantil"]), 0.99)           # ham max hala ~0,99
        self.assertGreater(oz["atac_p"], AG.KANTIL_P)                    # ama anlamli degil
        self.assertNotIn("duzenleyici_sinyal", oz)
        r = {k: None for k in AG.OZET_SUTUNLAR}; r.update(oz)
        self.assertEqual(AG.kategori(r), "dusuk")
        self.assertIn("anlamli sinyal yok", AG.yorumla(r))
        # gercek sinyal: tek izde kantil 1.0 -> p = 0
        Q[0, 7] = 1.0; X[0, 7] = 2.0
        a2 = anndata.AnnData(X=X, obs=pd.DataFrame({"variant": ["v"]}, index=["0"]),
                             var=_tracks(n, "ATAC", CURIES), layers={"quantiles": Q})
        oz2, _ = s._ozetle("chr1:1:A:T", {"ATAC": a2}, None, None, "atlas")
        self.assertEqual(oz2["atac_p"], 0.0)
        self.assertTrue(oz2["duzenleyici_sinyal"].startswith("ATAC+ ("))

    def test_aktif_kapilama_inaktif_dokuyu_eler(self):
        """Ifade edilmeyen gen/dokudaki doygun kantil (-1.0) secilmemeli; aktif matris yoksa kapilama yok."""
        import anndata
        s = FakeSorgu()
        s._secili = s.secili_skorlar()
        X = np.array([[-0.05, -0.9, 0.1]], dtype=np.float32)
        Q = np.array([[-1.0, -0.9995, 0.2]], dtype=np.float32)
        obs = pd.DataFrame({"gene_name": ["G"], "variant": ["v"]}, index=["0"])
        a = anndata.AnnData(X=X, obs=obs, var=_tracks(3, "RNA_SEQ", CURIES), layers={"quantiles": Q})
        act = anndata.AnnData(X=np.array([[0.0, 8.0, 6.0]], dtype=np.float32), obs=obs.copy(),
                              var=_tracks(3, "RNA_SEQ", CURIES))
        oz, det = s._ozetle("chr1:1:A:T", {"RNA_SEQ": a, "RNA_SEQ_ACTIVE": act}, None, None, "atlas")
        self.assertEqual(oz["ekspresyon_doku"], "karaciger")             # track 1, aktif
        self.assertAlmostEqual(oz["ekspresyon_kantil"], -0.9995, places=4)
        self.assertAlmostEqual(oz["ekspresyon_p"], 0.001, places=3)      # 2 aktif hucre
        self.assertEqual(oz["ekspresyon_aktif"], 1.0)
        self.assertTrue(all(d["doku"] != "beyin" for d in det))
        oz2, _ = s._ozetle("chr1:1:A:T", {"RNA_SEQ": a}, None, None, "atlas")   # aktif matris yok
        self.assertEqual(oz2["ekspresyon_doku"], "beyin")                # kapilamasiz: max |q| = -1.0
        self.assertIsNone(oz2["ekspresyon_aktif"])
        self.assertEqual(oz2["ekspresyon_p"], 0.0)

    def test_desteklenmeyen_varyant_modele_gider(self):
        self.assertTrue(AG._desteklenmiyor_mu(ValueError("Reference or alternate bases length > 1 not yet supported.")))
        self.assertFalse(AG._desteklenmiyor_mu(ValueError("Invalid filter")))
        class Yok(FakeSorgu):
            def _atlas_tek(self, v):
                raise _grpc_hata("INVALID_ARGUMENT", "Reference or alternate bases length > 1 not yet supported.")
        s = Yok(model=False)
        ozet, _ = s.sorgula(self.adaylar, onbellek=None)
        st = [r for r in ozet if r["key"] == STRONG][0]
        self.assertEqual(st["durum"], "bulunamadi")                       # model kapali: hata degil
        self.assertIn("desteklemiyor", st["yorum"])
        self.assertFalse(s.hatalar)

    def test_model_araligi(self):
        from alphagenome.data import genome
        from alphagenome.models import dna_client
        a = AG.AtlasSorgu._model_araligi(genome.Variant("chr1", 12345, "A", "G"))
        self.assertEqual(a.start, 0)
        self.assertEqual(a.width, dna_client.SEQUENCE_LENGTH_1MB)
        b = AG.AtlasSorgu._model_araligi(genome.Variant("chr12", 13865958, "C", "T"))
        self.assertEqual(b.width, dna_client.SEQUENCE_LENGTH_1MB)
        self.assertTrue(b.start < 13865958 < b.end)

    def test_avi_yok_uyarisi(self):
        class AviSiz(FakeSorgu):
            def secili_skorlar(self):
                return [s for s in super(AviSiz, self).secili_skorlar() if "AVI" not in s]
        orig, orig_key = AG.AtlasSorgu, AG.api_key
        AG.AtlasSorgu, AG.api_key = AviSiz, (lambda: "k")
        try:
            oz = AG.calistir(self.tmp, adaylar=self.adaylar, genome="hg38", onbellek=False, sessiz=True)
        finally:
            AG.AtlasSorgu, AG.api_key = orig, orig_key
        self.assertIsNone(oz["avi_skoru"])
        self.assertIn("AVI", oz["uyari"])
        rapor = open(os.path.join(self.tmp, "alphagenome_rapor.txt"), encoding="utf-8").read()
        self.assertNotIn("PHRED skoru (10 =", rapor)
        self.assertIn("Uyarı:", rapor)

    def test_hicbiri_bulunamadi_uyarisi(self):
        class Yok(FakeSorgu):
            def _atlas_tek(self, v):
                raise _grpc_hata("NOT_FOUND", "not found")
        orig, orig_key = AG.AtlasSorgu, AG.api_key
        AG.AtlasSorgu, AG.api_key = Yok, (lambda: "k")
        try:
            oz = AG.calistir(self.tmp, adaylar=self.adaylar, genome="hg38", onbellek=False, sessiz=True,
                             model=False)
        finally:
            AG.AtlasSorgu, AG.api_key = orig, orig_key
        self.assertEqual(oz["durum"], "tamam")
        self.assertIn("Atlas'ta bulunamadi", oz["uyari"])


@unittest.skipUnless(os.path.exists(os.path.join(PIPE, "rutin.py")),
                     "rutin.py lives in the Drive _sistem folder, not in this checkout")
class RutinHookTest(unittest.TestCase):
    """rutin.py imports openpyxl/genomize_seq/akrabalik/yollar at module level; stub them."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        rapor = os.path.join(self.tmp, "rapor")
        os.makedirs(os.path.join(rapor, "_sistem"), exist_ok=True)
        for name, attrs in {
            "openpyxl": {"load_workbook": lambda *a, **k: None},
            "genomize_seq": {"is_artifact": lambda r, m: False, "write_csv": lambda *a, **k: None},
            "akrabalik": {"kontrol": lambda *a, **k: ([], [])},
            "yollar": {"olgular_xlsx": lambda: os.path.join(rapor, "olgular.xlsx"),
                       "rapor_koku": lambda: rapor},
            "drive_esitle": {"esitle": lambda **k: None},
        }.items():
            m = types.ModuleType(name)
            for k, v in attrs.items():
                setattr(m, k, v)
            sys.modules[name] = m
        sys.modules.pop("rutin", None)
        import rutin                                      # noqa: F401
        self.rutin = rutin
        self.rapor = rapor
        self._orig = AG.AtlasSorgu
        self._orig_key = AG.api_key
        self._orig_cache = AG.onbellek_klasoru
        AG.AtlasSorgu = FakeSorgu
        AG.api_key = lambda: "test-key"
        AG.onbellek_klasoru = lambda k: os.path.join(self.tmp, "cache")   # never touch the real cache

    def tearDown(self):
        AG.AtlasSorgu = self._orig
        AG.api_key = self._orig_key
        AG.onbellek_klasoru = self._orig_cache

    def _olgu(self, kod="222080-DOR-HAY"):
        out = os.path.join(self.rapor, kod)
        kanit = os.path.join(out, "kanit")
        _kanit(kanit)
        ozet = {"olgu": kod, "etkilenen": ["222080"],
                "bireyler": {"222080": {"genom": "hg38"}, "222081": {"genom": "hg38"}}}
        with open(os.path.join(out, "ozet.json"), "w", encoding="utf-8") as f:
            json.dump(ozet, f)
        with open(os.path.join(out, "KLINIK.txt"), "w", encoding="utf-8") as f:
            f.write("Olgu Kodu   : %s\nProband     : 222080\nAnne        : 222081\n" % kod)
        return out, ozet

    def test_dosya_secimi(self):
        out, _ = self._olgu()
        d = [os.path.basename(x) for x in self.rutin.alphagenome_dosyalari(os.path.join(out, "kanit"), "222080")]
        self.assertEqual(sorted(d), ["222080_fenotip_iliskili.csv", "222080_nadir_lof.csv", "DENOVO_nadir_lof.csv"])

    def test_alphagenome_calistir(self):
        out, ozet = self._olgu()
        sonuc = self.rutin.alphagenome_calistir(out, ozet, "222080")
        self.assertEqual(sonuc["durum"], "tamam")
        self.assertEqual(ozet["alphagenome"]["kategori"]["yuksek"], 1)
        self.assertTrue(os.path.exists(os.path.join(out, "kanit", "alphagenome_rapor.txt")))
        self.assertEqual(self.rutin.alphagenome_ozet_metni(ozet), "AlphaGenome yuksek 1 / orta 1")

    def test_hata_olguyu_dusurmez(self):
        out, ozet = self._olgu()
        class Patlak(FakeSorgu):
            def secili_skorlar(self):
                raise RuntimeError("boom")
        AG.AtlasSorgu = Patlak
        sonuc = self.rutin.alphagenome_calistir(out, ozet, "222080")
        self.assertIn(sonuc["durum"], ("hata", "atlandi"))
        self.assertEqual(self.rutin.alphagenome_ozet_metni(ozet), "AlphaGenome %s" % sonuc["durum"])

    def test_komut_alphagenome(self):
        out, _ = self._olgu()
        self.rutin.komut_alphagenome(["TUMU"])
        with open(os.path.join(out, "ozet.json"), encoding="utf-8") as f:
            ozet = json.load(f)
        self.assertEqual(ozet["alphagenome"]["durum"], "tamam")
        self.assertEqual(ozet["alphagenome"]["aday"], 5)

    def test_komut_alphagenome_degismeyince_yazmaz(self):
        """Review #2: sonuc aynıysa (or. anahtar yok -> atlandi) ozet.json yeniden yazilmaz."""
        out, _ = self._olgu()
        AG.api_key = lambda: None
        yol = os.path.join(out, "ozet.json")
        self.rutin.komut_alphagenome(["222080-DOR-HAY"])
        with open(yol, encoding="utf-8") as f:
            ilk = f.read()
        self.assertIn('"atlandi"', ilk)
        os.utime(yol, (1000000000, 1000000000))
        self.rutin.komut_alphagenome(["222080-DOR-HAY"])
        self.assertEqual(int(os.stat(yol).st_mtime), 1000000000)      # dokunulmadi
        with open(yol, encoding="utf-8") as f:
            self.assertEqual(f.read(), ilk)

    def test_modul_yoksa(self):
        out, ozet = self._olgu()
        ag, self.rutin.AG, self.rutin.AG_HATA = self.rutin.AG, None, "ImportError: x"
        try:
            sonuc = self.rutin.alphagenome_calistir(out, ozet, "222080")
        finally:
            self.rutin.AG = ag
        self.assertEqual(sonuc["durum"], "atlandi")
        self.assertIn("ImportError", sonuc["neden"])


MAC_BASLATICI = os.path.join(PIPE, "BASLAT_mac.command")


@unittest.skipUnless(os.path.exists(MAC_BASLATICI) and shutil.which("bash") and shutil.which("sed"),
                     "BASLAT_mac.command / bash / sed yok")
class BaslatMacTest(unittest.TestCase):
    """Review #2: rc dosyasindaki export satirindan anahtar; yorum, ';' ve tirnaklar atilmali."""

    def _anahtar(self, satir):
        with open(MAC_BASLATICI, encoding="utf-8") as f:
            tanim = next(l.strip() for l in f if l.strip().startswith("AG_SED="))
        komut = "%s; printf '%%s\\n' \"$1\" | grep -E '^[[:space:]]*export[[:space:]]+ALPHAGENOME_API_KEY=' " \
                "| tail -1 | sed -E \"$AG_SED\"" % tanim
        return subprocess.run(["bash", "-c", komut, "_", satir], capture_output=True, text=True).stdout.rstrip("\n")

    def test_bicimler(self):
        for satir, beklenen in [
            ('export ALPHAGENOME_API_KEY="AIza-abc_123"', "AIza-abc_123"),
            ("export ALPHAGENOME_API_KEY='AIza-abc_123'", "AIza-abc_123"),
            ("export ALPHAGENOME_API_KEY=AIza-abc_123", "AIza-abc_123"),
            ('export ALPHAGENOME_API_KEY="AIza-abc_123"  # alphagenome.google/api', "AIza-abc_123"),
            ("export ALPHAGENOME_API_KEY='AIza-abc_123' ;", "AIza-abc_123"),
            ("export ALPHAGENOME_API_KEY=AIza-abc_123; # yorum", "AIza-abc_123"),
            ("  export   ALPHAGENOME_API_KEY=AIza-abc_123   ", "AIza-abc_123"),
            ("# export ALPHAGENOME_API_KEY=eski", ""),
            ("export OTHER_KEY=x", ""),
        ]:
            self.assertEqual(self._anahtar(satir), beklenen, satir)


if __name__ == "__main__":
    unittest.main(verbosity=2)
