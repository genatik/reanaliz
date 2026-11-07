"""
Sentetik BAM test dosyaları üretir (pysam gerekir):
    python3 make_bams.py <çıktı_klasörü>

Gerçek hg38 referans dizisi (UCSC) üzerinde iki haplotipten çift uçlu okumalar
simüle edilir. Haplotiplerden biri bilinen kesim noktalarıyla değiştirilir.
Kesim noktasını aşan okumalar, BWA-MEM'in yaptığı gibi yumuşak kırpılmış birincil
hizalama + sert kırpılmış ek (supplementary) hizalama ve SA etiketiyle yazılır.
Kesim noktaları truth.json dosyasına kaydedilir.
"""
import json
import os
import random
import sys
import urllib.request

import pysam

OUT = sys.argv[1] if len(sys.argv) > 1 else 'bams'
os.makedirs(OUT, exist_ok=True)
random.seed(7)

CHR7_LEN, CHR22_LEN = 159345973, 50818468
R7 = (117548000, 117568000)      # chr7 simülasyon bölgesi (0-tabanlı, yarı açık)
R22 = (23284000, 23296000)       # chr22 bölgesi (translokasyon eşi)


def fetch(chrom, s, e):
    url = 'https://api.genome.ucsc.edu/getData/sequence?genome=hg38;chrom=%s;start=%d;end=%d' % (chrom, s, e)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)['dna'].upper()


REF = {'chr7': (R7[0], fetch('chr7', *R7)), 'chr22': (R22[0], fetch('chr22', *R22))}
COMP = str.maketrans('ACGTN', 'TGCAN')


def rc(s):
    return s.translate(COMP)[::-1]


def refseq(chrom, s, e):
    off, seq = REF[chrom]
    return seq[s - off:e - off]


def hap_seq(segs):
    return ''.join(refseq(c, s, e) if st == '+' else rc(refseq(c, s, e)) for c, s, e, st in segs)


def map_part(segs, h0, h1):
    """Haplotip aralığını referans segmentlerine böl: [(chrom, rs, re, strand, h0, h1)]"""
    out, H = [], 0
    for c, s, e, st in segs:
        L = e - s
        a, b = max(h0, H), min(h1, H + L)
        if a < b:
            if st == '+':
                out.append((c, s + (a - H), s + (b - H), '+', a, b))
            else:
                out.append((c, e - (b - H), e - (a - H), '-', a, b))
        H += L
    return out


def flip(s):
    return '-' if s == '+' else '+'


REF7 = [('chr7', R7[0], R7[1], '+')]


def simulate(name, alt_segs, depth=25, read_len=150, ins=380, sd=35, ref_segs=None):
    ref_segs = ref_segs or REF7
    hdr = {'HD': {'VN': '1.6', 'SO': 'coordinate'},
           'SQ': [{'SN': 'chr7', 'LN': CHR7_LEN}, {'SN': 'chr22', 'LN': CHR22_LEN}],
           'RG': [{'ID': 'sim', 'SM': 'sim'}]}
    tmp = os.path.join(OUT, name + '.unsorted.bam')
    out = pysam.AlignmentFile(tmp, 'wb', header=hdr)
    rid = {'chr7': 0, 'chr22': 1}
    n = 0
    for hap in (ref_segs, alt_segs):
        hs = hap_seq(hap)
        npairs = int(depth * len(hs) / (2 * read_len) / 2)  # iki haplotip -> toplam derinlik ~depth
        for _ in range(npairs):
            fl = max(2 * read_len + 20, int(random.gauss(ins, sd)))
            h0 = random.randint(0, len(hs) - fl)
            frag = (h0, h0 + fl)
            reads = [(frag[0], frag[0] + read_len, '+', 64), (frag[1] - read_len, frag[1], '-', 128)]
            n += 1
            qname = 'r%06d' % n
            alns = []
            for (a, b, ori, rflag) in reads:
                rseq = hs[a:b] if ori == '+' else rc(hs[a:b])
                parts = map_part(hap, a, b)
                if ori == '-':
                    parts = parts[::-1]  # okuma yönünde sırala
                # okuma yönünde her parçanın okumadaki aralığı
                infos, q = [], 0
                for (c, s, e, st, pa, pb) in parts:
                    L = pb - pa
                    infos.append({'chrom': c, 'pos': s, 'end': e, 'strand': st if ori == '+' else flip(st), 'q0': q, 'q1': q + L})
                    q += L
                infos = [x for x in infos if x['q1'] - x['q0'] >= 1]
                prim = max(infos, key=lambda x: x['q1'] - x['q0'])
                others = [x for x in infos if x is not prim and x['q1'] - x['q0'] >= 20]
                alns.append((rflag, rseq, prim, others, len(rseq)))
            # birincil hizalamalar
            recs = []
            for (rflag, rseq, prim, others, rl) in alns:
                recs.append(make_aln(qname, rflag, rseq, prim, others, rl, rid, hard=False))
            # çift bilgisi
            r1, r2 = recs
            for x, m in ((r1, r2), (r2, r1)):
                x.flag |= 1
                x.next_reference_id = m.reference_id
                x.next_reference_start = m.reference_start
                if m.is_reverse:
                    x.flag |= 32
                if x.reference_id == m.reference_id:
                    lo = min(x.reference_start, m.reference_start)
                    hi = max(x.reference_end, m.reference_end)
                    t = hi - lo
                    x.template_length = t if x.reference_start <= m.reference_start else -t
                    fr = (not x.is_reverse and m.is_reverse and x.reference_start <= m.reference_start) or \
                         (x.is_reverse and not m.is_reverse and x.reference_start >= m.reference_start)
                    if fr and t < 1000:
                        x.flag |= 2
                x.set_tag('MC', m.cigarstring)
                out.write(x)
            # ek (supplementary) hizalamalar
            for (rflag, rseq, prim, others, rl), pr in zip(alns, recs):
                for o in others:
                    sup = make_aln(qname, rflag, rseq, o, [prim], rl, rid, hard=True)
                    sup.flag |= 1 | 2048
                    sup.next_reference_id = pr.next_reference_id
                    sup.next_reference_start = pr.next_reference_start
                    out.write(sup)
    out.close()
    final = os.path.join(OUT, name + '.bam')
    pysam.sort('-o', final, tmp)
    os.remove(tmp)
    pysam.index(final)
    return final


def cigar_for(x, rl, hard):
    clip_op = 5 if hard else 4
    before, after = x['q0'], rl - x['q1']
    if x['strand'] == '-':
        before, after = after, before
    c = []
    if before:
        c.append((clip_op, before))
    c.append((0, x['q1'] - x['q0']))
    if after:
        c.append((clip_op, after))
    return c


def cigar_str(c):
    return ''.join('%d%s' % (n, 'MIDNSHP=X'[op]) for op, n in c)


def make_aln(qname, rflag, rseq, x, others, rl, rid, hard):
    a = pysam.AlignedSegment()
    a.query_name = qname
    a.flag = rflag | (16 if x['strand'] == '-' else 0)
    a.reference_id = rid[x['chrom']]
    a.reference_start = x['pos']
    a.mapping_quality = 60
    a.cigartuples = cigar_for(x, rl, hard)
    stored = rseq if x['strand'] == '+' else rc(rseq)
    if hard:
        if x['strand'] == '+':
            stored = rseq[x['q0']:x['q1']]
        else:
            stored = rc(rseq[x['q0']:x['q1']])
    a.query_sequence = stored
    a.query_qualities = pysam.qualitystring_to_array('I' * len(stored))
    if others:
        a.set_tag('SA', ''.join('%s,%d,%s,%s,60,0;' % (o['chrom'], o['pos'] + 1, o['strand'], cigar_str(cigar_for(o, rl, False))) for o in others))
    a.set_tag('RG', 'sim')
    return a


truth = {}
S0, S1 = R7
# 1) heterozigot delesyon 5 kb
d = (117555000, 117560000)
simulate('del_het', [('chr7', S0, d[0], '+'), ('chr7', d[1], S1, '+')])
truth['del_het'] = {'type': 'DEL', 'bp1': d[0], 'bp2': d[1], 'zyg': 'het'}
# 2) tandem duplikasyon 3 kb
u = (117555000, 117558000)
simulate('dup_het', [('chr7', S0, u[1], '+'), ('chr7', u[0], S1, '+')])
truth['dup_het'] = {'type': 'DUP', 'bp1': u[0], 'bp2': u[1], 'zyg': 'het'}
# 3) inversiyon 6 kb
v = (117555000, 117561000)
simulate('inv_het', [('chr7', S0, v[0], '+'), ('chr7', v[0], v[1], '-'), ('chr7', v[1], S1, '+')])
truth['inv_het'] = {'type': 'INV', 'bp1': v[0], 'bp2': v[1], 'zyg': 'het'}
# 4) dengeli translokasyon: der(7) = chr7 sol + chr22 sağ ; der(22) = chr22 sol + chr7 sağ
t7, t22 = 117558000, 23290000
hdr_segs = [('chr7', S0, t7, '+'), ('chr22', t22, R22[1], '+')]
simulate('tra_het', hdr_segs)
truth['tra_het'] = {'type': 'TRA', 'bp1': t7, 'chrom2': 'chr22', 'bp2': t22, 'zyg': 'het'}
# 5) homozigot delesyon 2 kb (iki haplotip de delesyonlu)
h = (117552000, 117554000)
alt = [('chr7', S0, h[0], '+'), ('chr7', h[1], S1, '+')]
simulate('del_hom', alt, ref_segs=alt)
truth['del_hom'] = {'type': 'DEL', 'bp1': h[0], 'bp2': h[1], 'zyg': 'hom'}

json.dump(truth, open(os.path.join(OUT, 'truth.json'), 'w'), indent=1)
print('Yazıldı:', sorted(os.listdir(OUT)))
