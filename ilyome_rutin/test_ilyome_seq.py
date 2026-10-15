# -*- coding: utf-8 -*-
"""ilyome_seq.py icin cevrimdisi testler (Ilyome'un demo yanitlariyla; giris gerekmez).

    python3 -m pytest -q test_ilyome_seq.py      ya da      python3 test_ilyome_seq.py
"""
import csv
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ilyome_seq as I  # noqa: E402

FX = os.path.join(HERE, "test_fixtures")


def fx(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


class SlimTest(unittest.TestCase):
    def setUp(self):
        self.rows = I.duzlestir(fx("snv-list.json")["data"])

    def test_duzlestir_gruplu(self):
        self.assertEqual(len(self.rows), 3)
        self.assertIn("variant_key", self.rows[0])

    def test_duzlestir_duz(self):
        rows = I.duzlestir(fx("snv-top-reportable.json")["data"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["symbol"], "RHO")

    def test_slim_alanlar(self):
        r = I.slim(self.rows[0])
        self.assertEqual(r["key"], "3:129528965:A:C")          # 'chr' on-eki yok (akrabalik.py bunu bekler)
        self.assertEqual(r["gene"], "RHO")
        self.assertEqual(r["genotype"], "het")                   # kucuk harf (akrabalik.py erkek_mi)
        self.assertEqual(r["hgvsc"], "c.232A>C")
        self.assertEqual(r["hgvsp"], "p.Asn78His")
        self.assertEqual(r["transcript"], "NM_000539.3")         # MANE Select tercih edilir
        self.assertEqual(r["pathogenicity"], "Likely pathogenic")
        self.assertEqual(r["depth"], 96)
        self.assertAlmostEqual(r["allele_fraction"], 0.4271, places=4)
        self.assertAlmostEqual(r["af_max"], 8.993e-07)
        self.assertAlmostEqual(r["gnomad_exome"], 6.84045e-07)
        self.assertEqual(r["gnomad_exome_hom"], 0)
        self.assertEqual(r["revel"], 0.567)
        self.assertEqual(r["spliceai"], 0.01)                   # splice_ai bos -> SpliceAI DS en buyugu
        self.assertEqual(r["dbsnp"], "rs1248203737")
        self.assertEqual(r["diseases"], 12)
        self.assertEqual(r["inheritance"], "AD/AR")
        self.assertIn("610445", r["omim"])

    def test_spliceai_ds_fallback(self):
        it = dict(self.rows[0]); it["splice_ai"] = None
        it["spliceai_pred_ds_dl"] = 0.42
        self.assertEqual(I.slim(it)["spliceai"], 0.42)

    def test_kucuk_kohort_artefakt_sayilmaz(self):
        r = I.slim(self.rows[0])                                 # cohort_an = 16 -> internal_freq bos
        self.assertIsNone(r["internal_freq"])
        self.assertFalse(I.is_artifact(r, 0.02))
        it = dict(self.rows[0]); it["cohort_an"] = 400; it["cohort_af"] = 0.05
        r2 = I.slim(it)
        self.assertEqual(r2["internal_freq"], 0.05)
        self.assertTrue(I.is_artifact(r2, 0.02))

    def test_csv_yazimi_genomize_sutunlari(self):
        rows = [I.slim(x) for x in self.rows]
        with tempfile.TemporaryDirectory() as d:
            p = I.write_csv(os.path.join(d, "x.csv"), rows)
            with open(p, encoding="utf-8-sig") as f:
                basliklar = next(csv.reader(f))
        for c in I.COLUMNS:
            self.assertIn(c, basliklar)
        self.assertEqual(basliklar[:len(I.COLUMNS)], I.COLUMNS)    # Genomize ile ayni sira, ekler sonda


class CnvTest(unittest.TestCase):
    def test_cnv_rows(self):
        rows = I.cnv_rows(fx("cnv-list.json")["data"])
        r = rows[0]
        self.assertEqual(r["chrom"], "chrX")
        self.assertEqual(r["state"], "DUP")
        self.assertEqual(r["copy_number"], 3)
        self.assertEqual(r["classification"], "Pathogenic")
        self.assertEqual(r["genes"], "NDP")
        self.assertAlmostEqual(r["length_kb"], 9.05)
        self.assertFalse(r["cohort_artifact"])                   # 16/145 < 0.3
        self.assertTrue(I.cnv_hedefte(r, ["NDP"]))
        self.assertFalse(I.cnv_hedefte(r, ["F8"]))


class PanelTest(unittest.TestCase):
    def test_panel_indeksi(self):
        idx = I.panel_indeksi(fx("snv-filter-panel.json"))
        self.assertIn(("consequence", "stop_gained"), idx)
        self.assertIn(("af_exomes", "af_exomes"), idx)
        self.assertIn(("af_genomes", "af_genomes"), idx)
        self.assertNotIn(("max_af", "max_af"), idx)            # Ilyome'da tek max_af filtresi YOK
        self.assertIn(("zyg", "HOM"), idx)
        self.assertIn(("clinvar_clnsig", "Likely_pathogenic"), idx)
        self.assertIn(("acmg_class", "Likely pathogenic"), idx)
        self.assertEqual(idx[("consequence", "stop_gained")]["selected"], False)

    def test_eksen_terimleri_panelde_var(self):
        """axes() icindeki her (filter, term) gercek panelde bulunmali."""
        idx = I.panel_indeksi(fx("snv-filter-panel.json"))
        for ad, spec in I.axes(["HP:0001250"], 1.0).items():
            for ft in spec.get("checkbox") or []:
                self.assertIn(ft, idx, "%s: %s" % (ad, ft))
            for ft in (spec.get("range") or {}):
                self.assertIn(ft, idx, "%s: %s" % (ad, ft))


class SampleTest(unittest.TestCase):
    def test_an(self):
        s = fx("samples-create-list.json")["data"][0]
        an = I.Seq._an(s)
        self.assertEqual(an["sample_name"], "2308-26-ZBS")
        self.assertEqual(an["genome_version"], "hg38")
        self.assertEqual(an["status_id"], 6)
        self.assertEqual(an["run"]["name"], "R325-Twist")
        self.assertEqual(an["sequencing_type"], "WES")
        self.assertEqual(an["hash"], an["id"])

    def test_kapsama_anahtarlari(self):
        m = fx("metrics-d-metrics.json")["metrics"]
        sec = [kv["key"] for kv in m["coverages"]
               if any(a in kv["key"].lower() for a in I.Seq.KAPSAMA_ANAHTAR)]
        self.assertTrue(any("20x" in k for k in sec), sec)
        self.assertTrue(any("Average alignment coverage" in k for k in sec), sec)


if __name__ == "__main__":
    unittest.main(verbosity=2)
