// BAM okuyucu ve kesim noktası bulucu testi (ağ gerektirmez): node tests/bam.test.js
// Test dosyaları tests/make_bams.py ile üretilmiştir; gerçek kesim noktaları bam/truth.json içinde.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const B = require('../bam.js');

const dir = path.join(__dirname, 'bam');
const truth = JSON.parse(fs.readFileSync(path.join(dir, 'truth.json'), 'utf8'));
const inflate = (u8) => zlib.inflateRawSync(Buffer.from(u8.buffer, u8.byteOffset, u8.byteLength));
function src(file) {
  const buf = fs.readFileSync(file);
  return { size: buf.length, read: async (a, b) => buf.buffer.slice(buf.byteOffset + a, buf.byteOffset + Math.min(b, buf.length)) };
}
const REGION = 'chr7:117,548,001-117,568,000';

(async () => {
  for (const name of Object.keys(truth)) {
    const t = truth[name];
    const file = path.join(dir, name + '.bam');
    const bai = fs.readFileSync(file + '.bai');
    const ix = await B.readBam(src(file), bai.buffer.slice(bai.byteOffset, bai.byteOffset + bai.length), REGION, inflate);
    const plain = await B.readBam(src(file), null, REGION, inflate);
    assert.strictEqual(ix.mode, 'indexed');
    assert(ix.reads.length > 1000, name + ': okuma sayısı');
    assert.strictEqual(ix.reads.length, plain.reads.length, name + ': indeksli ve tam okuma aynı sayıda kayıt vermeli');
    const res = B.analyze(ix.reads, ix.region, {});
    const c = res.candidates[0];
    assert(c, name + ': aday bulunamadı');
    assert.strictEqual(c.type, t.type, name + ': tip ' + c.type + ' (beklenen ' + t.type + ')');
    assert(c.bp1.exact && c.bp2.exact, name + ': kesim noktaları kesin olmalı');
    assert(Math.abs(c.bp1.pos - t.bp1) <= 1, name + ': bp1 ' + c.bp1.pos + ' (beklenen ' + t.bp1 + ')');
    assert(Math.abs(c.bp2.pos - t.bp2) <= 1, name + ': bp2 ' + c.bp2.pos + ' (beklenen ' + t.bp2 + ')');
    if (t.chrom2) assert.strictEqual(c.bp2.chrom, t.chrom2);
    assert.strictEqual(c.zyg, t.zyg, name + ': zigosite ' + c.zyg + ' (beklenen ' + t.zyg + ')');
    assert.strictEqual(c.confidence, 'yüksek', name + ': güven');
    console.log('OK ' + name.padEnd(8) + ' ' + c.type + ' ' + c.bp1.chrom + ':' + c.bp1.pos + ' ↔ ' + c.bp2.chrom + ':' + c.bp2.pos +
      ' · split ' + c.support.split + ', çift ' + c.support.disc + ', kırpma ' + c.support.clip1 + '/' + c.support.clip2 +
      (c.depthRatio != null ? ', kapsam oranı ' + c.depthRatio.toFixed(2) : '') + ', AF ' + (c.af != null ? c.af.toFixed(2) : '-') + ', ' + c.zyg + ' · aday sayısı ' + res.candidates.length);
  }
  // SA etiketi olmayan hizalayıcı: kesim noktaları kırpma + anormal çiftten bulunmalı
  for (const name of ['del_het', 'dup_het']) {
    const f0 = path.join(dir, name + '.bam');
    const all = await B.readBam(src(f0), null, REGION, inflate);
    const noSA = all.reads.filter(r => !(r.flag & 2048)).map(r => Object.assign({}, r, { SA: null }));
    const res = B.analyze(noSA, all.region, {});
    const c = res.candidates[0], t = truth[name];
    assert.strictEqual(c.type, t.type, name + ' SA yok: tip ' + c.type);
    // kesinse 1 bp içinde, değilse gerçek kesim noktası pencerenin içinde olmalı
    const ok = (b, x) => b.exact ? Math.abs(b.pos - x) <= 1 : (b.window[0] <= x && x <= b.window[1]);
    assert(ok(c.bp1, t.bp1) && ok(c.bp2, t.bp2), name + ' SA yok: ' + JSON.stringify([c.bp1, c.bp2]));
    assert(c.bp1.exact || c.bp2.exact, name + ' SA yok: en az bir uç kırpmayla kesinleşmeli');
    const show = b => b.exact ? b.pos + ' (kesin)' : b.window.join('–') + ' (pencere)';
    console.log('OK ' + name + ' (SA etiketi yok): ' + c.type + ' ' + show(c.bp1) + ' ↔ ' + show(c.bp2) + ', kaynak: ' + c.source);
  }

  // Varyantsız bölge: yanlış pozitif olmamalı
  const f = path.join(dir, 'del_het.bam');
  const bai = fs.readFileSync(f + '.bai');
  const neg = await B.readBam(src(f), bai.buffer.slice(bai.byteOffset, bai.byteOffset + bai.length), 'chr7:117,561,000-117,567,500', inflate);
  const r = B.analyze(neg.reads, neg.region, {});
  assert.strictEqual(r.candidates.filter(c => c.confidence !== 'düşük').length, 0, 'normal bölgede aday çıkmamalı: ' + JSON.stringify(r.candidates.map(c => c.type + c.bp1.pos)));
  console.log('OK normal bölgede yanlış pozitif yok (insert medyanı ' + r.insert.median + ', kapsam medyanı ' + r.coverage.median + ')');
})().catch(e => { console.error(e); process.exit(1); });
