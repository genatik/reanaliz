"""Primer3 (primer3-py) referans değerlerini üretir: python3 make_reference.py > primer3_reference.json"""
import json, random
import primer3
random.seed(42)
seqs = []
while len(seqs) < 300:
    L = random.randint(18, 27)
    s = ''.join(random.choice('ACGT') for _ in range(L))
    gc = (s.count('G') + s.count('C')) / L
    if 0.3 <= gc <= 0.7:
        seqs.append(s)
# bilinen bazı zorlu örnekler (hairpin / dimer)
seqs += ['GGGAAACCCTTTTGGGTTTCCC', 'ACGTACGTACGTACGTACGT', 'GCGCGCATATGCGCGC', 'CCTGCAGGTTTTCCTGCAGG']
conds = [dict(mv_conc=50, dv_conc=1.5, dntp_conc=0.6, dna_conc=50),
         dict(mv_conc=50, dv_conc=2.0, dntp_conc=0.2, dna_conc=200)]
out = []
for c in conds:
    for i, s in enumerate(seqs):
        b = seqs[(i + 1) % len(seqs)]
        out.append(dict(seq=s, other=b, cond=dict(mv=c['mv_conc'], dv=c['dv_conc'], dntp=c['dntp_conc'], dna=c['dna_conc']),
                        tm=primer3.calc_tm(s, **c),
                        hairpin=primer3.calc_hairpin(s, **c).dg / 1000,
                        homodimer=primer3.calc_homodimer(s, **c).dg / 1000,
                        heterodimer=primer3.calc_heterodimer(s, b, **c).dg / 1000,
                        ))
print(json.dumps(out))
