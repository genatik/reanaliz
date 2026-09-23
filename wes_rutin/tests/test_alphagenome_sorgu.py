# -*- coding: utf-8 -*-
"""Offline tests for alphagenome_sorgu.py and its rutin.py hook.

The container cannot reach the Atlas API, so a fake client builds real
DenseVariantScores protos and feeds them through the genuine
`atlas.convert_variant_scores_to_anndata`, which exercises the exact AnnData
shapes the module will see in production.
"""
import csv
import json
import os
import struct
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
META["AVI"] = atlas.ScorerMetadata(name="AVI", is_signed=False, track_metadata=_tracks(1, "AVI", biosample=False))
META["AVI_FEATURE_ATTRIBUTIONS"] = atlas.ScorerMetadata(
    name="AVI_FEATURE_ATTRIBUTIONS", is_signed=True,
    track_metadata=pd.DataFrame({"name": ["ATAC", "SPLICING", "ALPHAMISSENSE", "PHASTCONS"], "strand": "."},
                                index=["0", "1", "2", "3"]))
META["RNA_SEQ_ACTIVE"] = atlas.ScorerMetadata(name="RNA_SEQ_ACTIVE", is_signed=False,
                                              track_metadata=_tracks(3, "RNA_SEQ_ACTIVE", CURIES))

# per-variant designed scores: key -> {scorer: (raw matrix, quantile matrix or None)}
STRONG = "chr12:13865958:C:T"     # splicing strong + AVI 31
MILD = "chr6:80168944:C:T"        # expression mild
NOTFOUND = "chr1:12345:A:G"       # Atlas miss -> model fallback
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
            raw[1, 0], q[1, 0] = -0.9, -0.96
        d[s] = (raw, q, genes)
    for s in TRACK_SCORERS:
        n = len(META[s].track_metadata)
        raw = np.full((1, n), 0.02, dtype=np.float32)
        q = np.full((1, n), 0.10, dtype=np.float32)
        if key == STRONG and s == "DNASE":
            raw[0, 2], q[0, 2] = -1.4, -0.993
        d[s] = (raw, q, None)
    d["AVI"] = (np.array([[31.4 if key == STRONG else 7.2]], dtype=np.float32), None, None)
    d["AVI_FEATURE_ATTRIBUTIONS"] = (np.array([[0.1, 2.3, 0.4, 0.9]], dtype=np.float32), None, None)
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
            raise ValueError("Variant not found")          # mirrors handle_rpc_error NOT_FOUND
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
    ])
    _write_csv(os.path.join(tmp, "DENOVO_nadir_lof.csv"), [
        {"key": BAD, "gene": "MT-ND1", "consequence": "Missense", "af_max": ""},
    ])
    _write_csv(os.path.join(tmp, "222081_fenotip_iliskili.csv"), [
        {"key": "chr9:999:G:A", "gene": "PARENTONLY", "consequence": "Missense", "af_max": "0"},
    ])
    _write_csv(os.path.join(tmp, "222080_cnv.csv"), [])
    _write_csv(os.path.join(tmp, "222080_nadir_lof_ARTEFAKT.csv"), [{"key": "chr4:1:A:T", "gene": "X"}])


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
        self.assertIn("AVI", sec)
        self.assertIn("AVI_FEATURE_ATTRIBUTIONS", sec)
        self.assertNotIn("RNA_SEQ_ACTIVE", sec)
        self.assertEqual(s.avi_adlari(sec), ("AVI", "AVI_FEATURE_ATTRIBUTIONS"))

    def test_sorgula(self):
        s = FakeSorgu(model=True, model_max=25)
        ozet, detay = s.sorgula(self.adaylar, onbellek=None)
        by = {r["key"]: r for r in ozet}
        self.assertEqual(len(ozet), len(self.adaylar))
        st = by[STRONG]
        self.assertEqual(st["durum"], "atlas")
        self.assertAlmostEqual(st["avi"], 31.4, places=1)
        self.assertEqual(st["kategori"], "yuksek")
        self.assertAlmostEqual(st["splice_site_ham"], 0.82, places=2)
        self.assertAlmostEqual(st["splicing_birlesik"], 0.82 + 0.55 + 2.5 / 5.0, places=2)
        self.assertEqual(st["splice_site_gen"], "GRIN2B")
        self.assertAlmostEqual(st["dnase_kantil"], -0.993, places=3)
        self.assertEqual(st["dnase_doku"], "kan")
        self.assertIn("SPLICING:+2.30", st["avi_katki"])
        self.assertIn("splicing etkisi guclu", st["yorum"])
        self.assertIn("PHRED 31.4", st["avi_yorum"])
        mi = by[MILD]
        self.assertEqual(mi["kategori"], "orta")
        self.assertAlmostEqual(mi["ekspresyon_kantil"], -0.96, places=2)
        self.assertEqual(mi["ekspresyon_gen"], "CACNA1C")
        self.assertIn("azalma", mi["yorum"])
        nf = by[NOTFOUND]
        self.assertEqual(nf["durum"], "model")
        self.assertIsNone(nf["avi"])
        self.assertEqual(nf["kategori"], "dusuk")
        self.assertIn("ongorulmuyor", nf["yorum"])
        self.assertEqual(s.model_calls, [NOTFOUND])
        bad = by[BAD]
        self.assertEqual(bad["durum"], "sorulamadi")
        self.assertEqual(bad["kategori"], "-")
        # detail rows: top-N per scorer, gene carried from candidate
        st_det = [d for d in detay if d["key"] == STRONG]
        self.assertTrue(st_det)
        self.assertEqual(st_det[0]["gene"], "GRIN2B")
        self.assertLessEqual(max(sum(1 for d in st_det if d["skor"] == sc) for sc in set(d["skor"] for d in st_det)),
                             AG.DETAY_DOKU_N)
        # AVI is not a detail row
        self.assertFalse([d for d in st_det if d["skor"] == "AVI"])
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
        self.assertEqual(n1, 3)                           # STRONG, MILD, NOTFOUND (BAD never queried)
        self.assertEqual([r["key"] for r in ozet2], [a["key"] for a in self.adaylar])
        self.assertTrue([d for d in detay2 if d["key"] == STRONG])

    def test_doku_filtresi(self):
        s = FakeSorgu(model=False, doku=["UBERON:0000955"])   # only 'beyin' tracks (index 0)
        ozet, _ = s.sorgula(self.adaylar, onbellek=None)
        st = [r for r in ozet if r["key"] == STRONG][0]
        # DNase peak sits in track 2 (kan) -> filtered out; summary must fall back to brain track
        self.assertEqual(st["dnase_doku"], "beyin")
        self.assertNotAlmostEqual(st["dnase_kantil"] or 0, -0.993, places=2)


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
        self.assertEqual(oz["aday"], 4)
        self.assertEqual(oz["atlas"], 2)
        self.assertEqual(oz["model"], 1)
        self.assertEqual(oz["sorulamadi"], 1)
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
        self.assertIn("AVI", j["sunucu_skorlari"])
        # second read via ozet_oku
        oz2, satirlar = AG.ozet_oku(self.tmp)
        self.assertEqual(oz2["durum"], "tamam")
        self.assertEqual(len(satirlar), 4)

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
        self.assertEqual(ozet["alphagenome"]["aday"], 4)

    def test_modul_yoksa(self):
        out, ozet = self._olgu()
        ag, self.rutin.AG, self.rutin.AG_HATA = self.rutin.AG, None, "ImportError: x"
        try:
            sonuc = self.rutin.alphagenome_calistir(out, ozet, "222080")
        finally:
            self.rutin.AG = ag
        self.assertEqual(sonuc["durum"], "atlandi")
        self.assertIn("ImportError", sonuc["neden"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
