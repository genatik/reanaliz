// Tasarım regresyon testi (ağ gerektirmez): node tests/design.test.js
const assert = require('assert');
const E = require('../engine.js');
const fx = require('./fixture_cftr_f508del.json');
const res = E.design(fx, {});
const p = res.params;
assert(res.pairs.length >= 3, 'en az 3 alternatif çift beklenir, bulunan: ' + res.pairs.length);
for (const pr of res.pairs) {
  for (const x of [pr.left, pr.right]) {
    assert(x.tm >= p.tmMin && x.tm <= p.tmMax, 'Tm aralık dışı: ' + x.seq);
    assert(x.gc >= p.gcMin && x.gc <= p.gcMax, 'GC aralık dışı: ' + x.seq);
    assert(!x.snps.length, 'sıkı modda primerde SNP olmamalı: ' + x.seq);
    assert(!x.repeats.length, 'primer tekrar bölgesinde olmamalı: ' + x.seq);
    // dizi şablonla birebir eşleşmeli
    const site = fx.template.substring(x.start0 - fx.tplStart0, x.end0 - fx.tplStart0);
    assert.strictEqual(x.side === 'F' ? x.seq : E.revcomp(x.seq), site, 'primer dizisi şablonla uyuşmuyor');
  }
  assert(pr.size >= p.sizeMin && pr.size <= p.sizeMax, 'ürün boyu aralık dışı');
  assert(pr.varFromF >= p.minDist && pr.varFromR >= p.minDist, 'varyant primerlere çok yakın');
  assert(pr.dTm <= p.tmDiffMax, 'ΔTm çok büyük');
  assert.strictEqual(pr.amplicon.length, pr.size);
  assert(pr.amplicon.startsWith(pr.left.seq) && pr.amplicon.endsWith(E.revcomp(pr.right.seq)), 'amplikon uçları primerlerle uyuşmuyor');
}
// alternatifler birbirinden farklı olmalı
for (let i = 0; i < res.pairs.length; i++) for (let j = i + 1; j < res.pairs.length; j++) {
  assert(Math.abs(res.pairs[i].left.start0 - res.pairs[j].left.start0) >= 10);
  assert(Math.abs(res.pairs[i].right.start0 - res.pairs[j].right.start0) >= 10);
}
console.log('OK: ' + res.pairs.length + ' çift, tüm kısıtlar sağlandı.');
res.pairs.forEach(pr => console.log('  ' + pr.left.seq + ' / ' + pr.right.seq + '  ' + pr.size + ' bp'));
