// GIAB HG002 kesitlerinde kesim noktası bulucuyu doğrular: node run_giab.js <fetch_giab.py klasörü>
const fs = require('fs'), path = require('path'), zlib = require('zlib');
const B = require('../../bam.js');
const dir = process.argv[2] || 'giab';
const inflate = u => zlib.inflateRawSync(Buffer.from(u.buffer, u.byteOffset, u.byteLength));
(async () => {
  console.log('GIAB delesyonu | boyut | GT | tip | sonuç | KN1 farkı | KN2 farkı | zigosite | güven');
  for (const line of fs.readFileSync(path.join(dir, 'sel.txt'), 'utf8').trim().split('\n')) {
    const [c, pos, ln, gt, rt] = line.split('\t');
    const P = +pos, L = +ln;
    const buf = fs.readFileSync(path.join(dir, 'hg002_' + c + '_' + P + '.bam'));
    const src = { size: buf.length, read: async (a, b) => buf.buffer.slice(buf.byteOffset + a, buf.byteOffset + Math.min(b, buf.length)) };
    const r = await B.readBam(src, null, c + ':' + (P - 3999) + '-' + (P + L + 4000), inflate);
    const k = B.analyze(r.reads, r.region, {}).candidates[0];
    // VCF POS delesyondan önceki bazdır: kesim noktaları POS ve POS+uzunluk (0-tabanlı sınır)
    console.log([c + ':' + P, L, gt, rt, k ? k.type : '-', k ? (k.bp1.exact ? 'kesin' : 'pencere') + '/' + (k.bp2.exact ? 'kesin' : 'pencere') : '-',
      k ? k.bp1.pos - P : '-', k ? k.bp2.pos - (P + L) : '-', k ? k.zyg : '-', k ? k.confidence : '-'].join(' | '));
  }
})();
