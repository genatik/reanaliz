# -*- coding: utf-8 -*-
"""hpo_otomatik.py regresyon testleri.   python3 -m unittest -v test_hpo_otomatik"""
import os
import sys
import unittest

# hpo_otomatik.py bir ust klasorde (wes_rutin/) durur; Drive kurulumunda ise
# testle ayni klasorde olabilir - ikisini de yola ekle.
_BU = os.path.dirname(os.path.abspath(__file__))
for _d in (_BU, os.path.dirname(_BU)):
    if _d not in sys.path:
        sys.path.insert(0, _d)
from hpo_otomatik import normalize, terimler, SOZLUK      # noqa: E402


class Normalizasyon(unittest.TestCase):
    def test_turkce_buyuk_harf(self):
        # Python'un varsayilan lower()'i I/i ve İ/i ayrimini yanlis yapar
        self.assertEqual(normalize("İŞİTME KAYBI"), "isitme kaybi")
        self.assertEqual(normalize("CK YÜKSEKLİĞİ"), "ck yuksekligi")

    def test_aksanlar_ascii_olur(self):
        self.assertEqual(normalize("bronşiektazi"), "bronsiektazi")
        self.assertEqual(normalize("Koagülopati?"), "koagulopati")

    def test_noktalama_ve_bosluk(self):
        self.assertEqual(normalize("--otizm,  PANDAS?"), "otizm pandas")
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize(None), "")


class Eslestirme(unittest.TestCase):
    def test_bugunku_kosunun_14_olgusu(self):
        beklenen = {
            "Herediter sferositoz": ["HP:0004444", "HP:0001878", "HP:0001744", "HP:0000952"],
            "Koagülopati?": ["HP:0001892", "HP:0003125"],
            "Kalıtsal hemolitik anemi?": ["HP:0001878", "HP:0001903"],
            "Genodermatoz?": ["HP:0000951"],
            "İşitme kaybı": ["HP:0000365"],
        }
        for klinik, hpo in beklenen.items():
            self.assertEqual(terimler(klinik), hpo, klinik)

    def test_coklu_bulgu_hepsini_yakalar(self):
        t = terimler("--NMGG, epilepsi, cafe au lait, atrofik bb")
        self.assertIn("HP:0012758", t)      # NMGG
        self.assertIn("HP:0001250", t)      # epilepsi
        self.assertIn("HP:0000957", t)      # cafe-au-lait

    def test_turkce_ek_alan_kelime(self):
        # "nobet" kalibi "nöbetleri" icinde de bulunmali (sondan eklemeli dil)
        self.assertIn("HP:0001250", terimler("2 nöbet geçirmiş"))
        self.assertIn("HP:0002650", terimler("torakolomber bölgede skolyozu var"))

    def test_kisa_kisaltma_kelime_icinde_eslesmez(self):
        # "ey" / "asd" gibi kisa kaliplar baska kelimenin icinde yakalanmamali
        self.assertEqual(terimler("eylül ayında başvurdu"), [])
        self.assertNotIn("HP:0001631", terimler("hastada basdurum yok"))

    def test_eslesme_yoksa_bos_doner(self):
        # Uydurmaktansa bos donmeli - o olgu kullaniciya sorulur
        self.assertEqual(terimler(""), [])
        self.assertEqual(terimler("bilgileri bulutta"), [])
        self.assertEqual(terimler("POL HASTASI. WES ISTEK KAGIDINI KAYBETMIS"), [])

    def test_ayni_terim_iki_kez_yazilmaz(self):
        t = terimler("işitme kaybı, bilateral işitme kaybı, sağırlık")
        self.assertEqual(t.count("HP:0000365"), 1)

    def test_ayrinti_kipi(self):
        d = terimler("Genodermatoz?", ayrinti=True)
        self.assertEqual(len(d), 1)
        hp, ad, kalip = d[0]
        self.assertEqual(hp, "HP:0000951")
        self.assertTrue(ad and kalip)


class SozlukSagligi(unittest.TestCase):
    def test_hp_kimlik_bicimi(self):
        import re
        for _, hpo, ad in SOZLUK:
            for h in hpo:
                self.assertRegex(h, r"^HP:\d{7}$", "%s (%s)" % (h, ad))

    def test_kaliplar_bos_degil(self):
        for kaliplar, _, ad in SOZLUK:
            self.assertTrue(kaliplar, ad)
            for k in kaliplar:
                self.assertTrue(normalize(k), "%s: bos kalip" % ad)

    def test_ayni_kalip_iki_girdide_olmasin(self):
        gorulen = {}
        for kaliplar, _, ad in SOZLUK:
            for k in kaliplar:
                n = normalize(k)
                self.assertNotIn(n, gorulen,
                                 "'%s' hem '%s' hem '%s' icinde" % (n, gorulen.get(n), ad))
                gorulen[n] = ad


if __name__ == "__main__":
    unittest.main(verbosity=2)
