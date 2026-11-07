// Yapısal varyant tasarımı ve PCR koşulu testleri (ağ gerektirmez): node tests/sv.test.js
const assert = require('assert');
const E = require('../engine.js');
const fx = require('./fixture_cftr_f508del.json');
const tpl = { seq: fx.template, start0: fx.tplStart0, snps: fx.snps, repeats: fx.repeats, sds: [] };
const J1 = 117559200, J2 = 117560000;
const bps = (u) => [{ a: J1 - u, b: J1 + u, tplL: tpl, tplR: tpl }, { a: J2 - u, b: J2 + u, tplL: tpl, tplR: tpl }];

function checkPrimer(p, prm) {
  const site = tpl.seq.substring(p.start0 - tpl.start0, p.end0 - tpl.start0);
  assert.strictEqual(p.side === 'F' ? p.seq : E.revcomp(p.seq), site, 'primer şablonla uyuşmuyor: ' + p.name);
  assert(p.tm >= prm.tmMin - 2 && p.tm <= prm.tmMax + 2, 'Tm aralık dışı: ' + p.name);
}

for (const type of ['DEL', 'DUP', 'INV']) {
  const prm = Object.assign(E.svParamsStd(), { dMin: 60, dMax: 400 });
  const r = E.designSV({ type, bps: bps(0) }, prm);
  assert(r.sets.length >= 2, type + ': en az 2 alternatif set beklenir');
  for (const s of r.sets) {
    const P = s.primers;
    Object.keys(P).forEach(k => P[k] && checkPrimer(P[k], prm));
    // yönler ve konumlar
    assert(P.L1.side === 'F' && P.L1.end0 <= J1 - 60, type + ': L1 kesim noktası 1 solunda olmalı');
    assert(P.R1.side === 'R' && P.R1.start0 >= J1 + 60 && P.R1.end0 <= J2, type + ': R1 segment içinde olmalı');
    assert(P.L2.side === 'F' && P.L2.start0 >= J1 && P.L2.end0 <= J2 - 60, type + ': L2 segment içinde olmalı');
    assert(P.R2.side === 'R' && P.R2.start0 >= J2 + 60, type + ': R2 kesim noktası 2 sağında olmalı');
    const A = Object.fromEntries(s.assays.map(a => [a.id, a]));
    // beklenen ürün boyları (kesin kesim noktası)
    if (type === 'DEL') {
      assert.strictEqual(A.J.mut.min, (J1 - P.L1.start0) + (P.R2.end0 - J2));
      assert.strictEqual(A.J.ref, P.R2.end0 - P.L1.start0);
      assert.strictEqual(A.W1.ref, P.R1.end0 - P.L1.start0);
    }
    if (type === 'DUP') assert.strictEqual(A.J.mut.min, (J2 - P.L2.start0) + (P.R1.end0 - J1));
    if (type === 'INV') {
      assert.strictEqual(A.J1.mut.min, (J1 - P.L1.start0) + (J2 - P.L2.start0));
      assert.strictEqual(A.J2.mut.min, (P.R1.end0 - J1) + (P.R2.end0 - J2));
    }
    s.assays.forEach(a => { if (a.mut) assert.strictEqual(a.mut.min, a.mut.max, 'kesin kesim noktasında aralık tek değer olmalı'); });
  }
  // alternatifler farklı konumlarda
  for (let i = 0; i < r.sets.length; i++) for (let j = i + 1; j < r.sets.length; j++)
    ['L1', 'R1', 'L2', 'R2'].forEach(k => assert(Math.abs(r.sets[i].primers[k].start0 - r.sets[j].primers[k].start0) >= 15));
  console.log('OK ' + type + ': ' + r.sets.length + ' set, set 1 testleri: ' + r.sets[0].assays.map(a => a.id + '=' + (a.mut ? a.mut.min : a.ref)).join(', '));
}

// belirsiz kesim noktası: ürün aralığı pencere genişliği kadar açılmalı
const ru = E.designSV({ type: 'DEL', bps: bps(50) }, Object.assign(E.svParamsStd(), { dMin: 25, dMax: 350 }));
const ju = ru.sets[0].assays.find(a => a.id === 'J');
assert.strictEqual(ju.mut.max - ju.mut.min, 200, 'belirsizlik ±50 iki uçta: aralık 200 bp olmalı');
console.log('OK belirsiz kesim noktası: junction ' + ju.mut.min + '–' + ju.mut.max + ' bp');

// PCR koşulları
const std = E.pcrConditions({ kind: 'std', tms: [59.6, 60.4], sizeMax: 640, gc: 50 });
assert.strictEqual(std.ta, 56.5);
assert(std.program.some(p => /72/.test(p.temp) && /45 s/.test(p.time)), 'uzama 640 bp için 45 s olmalı');
const gc = E.pcrConditions({ kind: 'std', tms: [60, 60], sizeMax: 500, gc: 68 });
assert(gc.notes.some(n => /DMSO/.test(n)) && gc.program.some(p => p.temp === '54.5 °C'), 'GC yüksekse DMSO ve düşük Ta');
const lng = E.pcrConditions({ kind: 'long', tms: [65, 66], sizeMax: 12000 });
assert(lng.ta === 68 && lng.program.some(p => /12 dk/.test(p.time)), 'long-range: iki aşamalı 68 °C, 12 dk uzama');
const q = E.pcrConditions({ kind: 'qpcr', tms: [59.5, 60.3] });
assert.strictEqual(q.ta, 60);
console.log('OK PCR koşulları: std Ta ' + std.ta + ' °C, GC-rich ' + gc.program[2].temp + ', long ' + lng.ta + ' °C, qPCR ' + q.ta + ' °C');

// Sanal PCR: mutant alleli oluştur, primerlerin gerçekten bağlandığı yerden ürün boyunu ölç
function vpcr(seq, a, b) {
  const sizes = [];
  for (const [f, r] of [[a, b], [b, a]]) {
    const rc = E.revcomp(r);
    let i = seq.indexOf(f);
    while (i >= 0) {
      const j = seq.indexOf(rc, i + f.length);
      if (j >= 0) sizes.push(j + rc.length - i);
      i = seq.indexOf(f, i + 1);
    }
  }
  return sizes.sort((x, y) => x - y);
}
const T = tpl.seq, o = tpl.start0, i1 = J1 - o, i2 = J2 - o;
const alleles = {
  DEL: T.slice(0, i1) + T.slice(i2),
  DUP: T.slice(0, i2) + T.slice(i1),
  INV: T.slice(0, i1) + E.revcomp(T.slice(i1, i2)) + T.slice(i2)
};
for (const type of ['DEL', 'DUP', 'INV']) {
  const r = E.designSV({ type, bps: bps(0) }, Object.assign(E.svParamsStd(), { dMin: 60, dMax: 400 }));
  for (const s of r.sets) for (const a of s.assays) {
    const [x, y] = a.primers.map(k => s.primers[k].seq);
    const onMut = vpcr(alleles[type], x, y), onRef = vpcr(T, x, y);
    if (a.role === 'junction') {
      assert(onMut.includes(a.mut.min), type + ' ' + a.id + ': mutant allelde ' + a.mut.min + ' bp bekleniyordu, bulunan ' + onMut);
      if (a.ref != null) assert(onRef.includes(a.ref), type + ' ' + a.id + ': referansta ' + a.ref + ' bp bekleniyordu');
      else assert.strictEqual(onRef.length, 0, type + ' ' + a.id + ': referansta ürün olmamalı');
    } else {
      assert(onRef.includes(a.ref), type + ' ' + a.id + ': referansta ' + a.ref + ' bp bekleniyordu');
      if (type === 'DEL') assert.strictEqual(onMut.length, 0, 'DEL ' + a.id + ': delesyonlu allelde normal kontrol ürünü olmamalı');
    }
  }
}
console.log('OK sanal PCR: tüm setlerde mutant ve referans allel ürün boyları öngörüyle aynı');
