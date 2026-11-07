"""
Gerçek veri doğrulaması için GIAB HG002 BAM kesitlerini indirir (ağ ve pysam gerekir):
    python3 fetch_giab.py <klasör>
GIAB SV Tier1 v0.6 (GRCh37) listesinden 1-8 kb arası PASS delesyonlardan 3 heterozigot ve
3 homozigot seçer, HG002 2x250 novoalign BAM'inden her biri için ±4 kb kesit indirir.
"""
import gzip, os, random, sys, urllib.request
import pysam

OUT = sys.argv[1] if len(sys.argv) > 1 else 'giab'
os.makedirs(OUT, exist_ok=True)
G = 'https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/data/AshkenazimTrio'
VCF = G + '/analysis/NIST_SVs_Integration_v0.6/HG002_SVs_Tier1_v0.6.vcf.gz'
BAM = G + '/HG002_NA24385_son/NIST_Illumina_2x250bps/novoalign_bams/HG002.hs37d5.2x250.bam'
vcf = os.path.join(OUT, 'tier1.vcf.gz')
if not os.path.exists(vcf):
    urllib.request.urlretrieve(VCF, vcf)
random.seed(3)
dels = []
for line in gzip.open(vcf, 'rt'):
    if line[0] == '#':
        continue
    f = line.rstrip().split('\t')
    if f[6] != 'PASS' or f[0] not in [str(i) for i in range(1, 23)]:
        continue
    info = dict(x.split('=', 1) for x in f[7].split(';') if '=' in x)
    ln = abs(int(info.get('SVLEN', '0')))
    if info.get('SVTYPE') == 'DEL' and 1000 <= ln <= 8000 and f[9].split(':')[0] in ('0/1', '1/1'):
        dels.append((f[0], int(f[1]), ln, f[9].split(':')[0], info.get('REPTYPE', '')))
random.shuffle(dels)
sel = [d for d in dels if d[3] == '0/1'][:3] + [d for d in dels if d[3] == '1/1'][:3]
with open(os.path.join(OUT, 'sel.txt'), 'w') as fh:
    fh.write('\n'.join('\t'.join(map(str, d)) for d in sel))
bam = pysam.AlignmentFile(BAM, index_filename=BAM + '.bai')
for c, pos, ln, gt, rt in sel:
    name = os.path.join(OUT, 'hg002_%s_%d.bam' % (c, pos))
    out = pysam.AlignmentFile(name, 'wb', template=bam)
    for r in bam.fetch(c, pos - 4000, pos + ln + 4000):
        out.write(r)
    out.close()
    print(name)
