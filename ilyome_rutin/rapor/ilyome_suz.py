# -*- coding: utf-8 -*-
"""ilyome_suz.py - Ilyome kanit CSV'lerini (kanit/) istemci tarafinda suz ve onceliklendir.

Ilyome sunucu tarafindaki sIklik filtresi ilk kosuda uygulanmadi; bu betik gnomAD ekzom/genom
ve max_af sutunlarinin en buyugunu alip esik uygular, kanonik olmayan transkript tekrarlarini
birlestirir ve trio'da ebeveyn genotiplerini ekler. Karar vermez; Claude'un okuyacagi kisa
aday listesini uretir.

    python3 ilyome_suz.py <olgu klasoru> [--proband KOD --anne KOD --baba KOD] [--genler A,B,C]
"""
import argparse, csv, glob, json, os, re, sys, collections

def f(v):
    try:
        x = float(v)
        return x
    except (TypeError, ValueError):
        return None

def oku(p):
    with open(p, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))

def pop_af(r):
    vals = [f(r.get("af_max")), f(r.get("gnomad_exome")), f(r.get("gnomad_genome"))]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None

def kalite(r):
    q = (r.get("quality") or "").strip()
    dp, af = f(r.get("depth")), f(r.get("allele_fraction"))
    lq = q != "PASS" or (dp is not None and dp < 15) or (af is not None and r.get("genotype") == "het" and (af < 0.25 or af > 0.8))
    return "LQ" if lq else "HQ"

def birey_tablosu(kanit, kod, eksenler=("fenotip_iliskili", "nadir_lof", "clinvar_patojenik", "tier", "homozigot_nadir", "hedef_gen")):
    """key -> satir (ilk gorulen kanonik satir), eksen etiketleri ile."""
    d = {}
    for e in eksenler:
        p = os.path.join(kanit, "%s_%s.csv" % (kod, e))
        if not os.path.exists(p):
            continue
        for r in oku(p):
            k = r["key"]
            r = dict(r)
            if k in d:
                d[k]["_eksen"].add(e)
                # kanonik transkript satirini tercih et
                if str(r.get("canonical")) == "True" and str(d[k].get("canonical")) != "True":
                    eks = d[k]["_eksen"]; r["_eksen"] = eks; d[k] = r
            else:
                r["_eksen"] = {e}
                d[k] = r
    return d

def ana():
    ap = argparse.ArgumentParser()
    ap.add_argument("klasor")
    ap.add_argument("--proband"); ap.add_argument("--anne"); ap.add_argument("--baba")
    ap.add_argument("--af", type=float, default=0.01, help="populasyon frekansi ust siniri (varsayilan 0.01)")
    ap.add_argument("--genler", default="", help="fenotiple iliskili gen listesi (virgul)")
    ap.add_argument("--json", help="suzulmus adaylari JSON olarak yaz")
    a = ap.parse_args()
    kanit = os.path.join(a.klasor, "kanit")
    kl = {}
    for s in open(os.path.join(a.klasor, "KLINIK.txt"), encoding="utf-8"):
        if ":" in s and not s.startswith("KLINIK"):
            x, y = s.split(":", 1); kl[x.strip()] = y.strip()
    prob = a.proband or kl.get("Proband", "").split(",")[0].strip()
    anne = a.anne or kl.get("Anne", "").split(",")[0].strip()
    baba = a.baba or kl.get("Baba", "").split(",")[0].strip()
    genler = {g.strip().upper() for g in a.genler.split(",") if g.strip()}

    P = birey_tablosu(kanit, prob)
    A = birey_tablosu(kanit, anne) if anne else {}
    B = birey_tablosu(kanit, baba) if baba else {}
    print("proband satir (benzersiz key): %d | anne %d | baba %d" % (len(P), len(A), len(B)))

    adaylar = []
    for k, r in P.items():
        af = pop_af(r)
        if af is not None and af > a.af:
            continue
        hom_n = f(r.get("gnomad_exome_hom"))
        cons = r.get("consequence") or ""
        r["_af"] = af; r["_kalite"] = kalite(r)
        r["_anne"] = (A.get(k) or {}).get("genotype", "-") if anne else "?"
        r["_baba"] = (B.get(k) or {}).get("genotype", "-") if baba else "?"
        g = (r.get("gene") or "").upper()
        r["_fenotip_gen"] = g in genler
        lof = any(x in cons for x in ("stop_gained", "frameshift", "splice_acceptor", "splice_donor_variant", "start_lost", "stop_lost"))
        plp = (r.get("pathogenicity") or "") in ("Pathogenic", "Likely pathogenic")
        cvp = any(x in (r.get("clinvar") or "") for x in ("Pathogenic", "Likely_pathogenic")) and "Benign" not in (r.get("clinvar") or "")
        puan = 0
        puan += 3 if r["_fenotip_gen"] else 0
        puan += 2 if lof else 0
        puan += 3 if cvp else 0
        puan += 2 if plp else 0
        puan += 1 if r.get("genotype") in ("hom", "hem") else 0
        puan += 2 if (anne and baba and r["_anne"] == "-" and r["_baba"] == "-") else 0   # olasi de novo
        puan += 1 if (f(r.get("revel")) or 0) >= 0.644 else 0
        puan += 1 if (f(r.get("spliceai")) or 0) >= 0.2 else 0
        puan -= 2 if r["_kalite"] == "LQ" else 0
        puan -= 2 if "Benign" in (r.get("clinvar") or "") and "Pathogenic" not in (r.get("clinvar") or "") else 0
        r["_puan"] = puan
        adaylar.append(r)
    adaylar.sort(key=lambda r: (-r["_puan"], r.get("gene") or ""))
    print("AF <= %s olan proband varyanti: %d" % (a.af, len(adaylar)))
    print("%-22s %-10s %-4s %-3s %-2s %-2s %-5s %-9s %-26s %-12s %-20s %-16s %-6s %-5s %s" % (
        "key", "gen", "gt", "kal", "A", "B", "puan", "AF", "hgvs", "ACMG", "ClinVar", "omim", "REVEL", "SpAI", "eksen"))
    for r in adaylar[:120]:
        print("%-22s %-10s %-4s %-3s %-2s %-2s %5d %-9s %-26s %-12s %-20s %-16s %-6s %-5s %s" % (
            r["key"][:22], (r.get("gene") or "-")[:10], r.get("genotype"), r["_kalite"], r["_anne"][:2], r["_baba"][:2],
            r["_puan"], ("%.2e" % r["_af"]) if r["_af"] is not None else "yok",
            ((r.get("hgvsc") or "") + " " + (r.get("hgvsp") or ""))[:26],
            (r.get("pathogenicity") or "-")[:12], (r.get("clinvar") or "-")[:20], (r.get("omim") or "-")[:16],
            (r.get("revel") or "-")[:6], (r.get("spliceai") or "-")[:5], ",".join(sorted(r["_eksen"]))))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump([{k: v for k, v in r.items() if k != "_eksen"} | {"_eksen": sorted(r["_eksen"])} for r in adaylar], fh, ensure_ascii=False, indent=1)
    return adaylar

if __name__ == "__main__":
    ana()
