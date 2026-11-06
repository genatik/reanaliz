// Motoru Primer3 referansıyla karşılaştırır: node tests/compare.js
const E = require('../engine.js');
const ref = require('./primer3_reference.json');
function stats(name, xs) {
  xs.sort((a, b) => a - b);
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  console.log(`${name.padEnd(28)} n=${xs.length}  ort.|fark|=${mean.toFixed(3)}  medyan=${xs[xs.length >> 1].toFixed(3)}  max=${xs[xs.length - 1].toFixed(3)}`);
  return { mean, max: xs[xs.length - 1] };
}
function pearson(a, b) {
  const n = a.length, ma = a.reduce((x, y) => x + y) / n, mb = b.reduce((x, y) => x + y) / n;
  let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < n; i++) { sab += (a[i] - ma) * (b[i] - mb); saa += (a[i] - ma) ** 2; sbb += (b[i] - mb) ** 2; }
  return sab / Math.sqrt(saa * sbb);
}
const tmd = [], hp = [[], []], hd = [[], []], ht = [[], []];
for (const r of ref) {
  tmd.push(Math.abs(E.tm(r.seq, r.cond) - r.tm));
  hp[0].push(E.hairpin(r.seq, r.cond).dG); hp[1].push(Math.min(0, r.hairpin));
  hd[0].push(E.dimer(r.seq, r.seq, r.cond).dG); hd[1].push(Math.min(0, r.homodimer));
  ht[0].push(E.dimer(r.seq, r.other, r.cond).dG); ht[1].push(Math.min(0, r.heterodimer));
}
const t = stats('Tm farkı (°C)', tmd);
console.log('Hairpin ΔG korelasyonu      r=' + pearson(hp[0], hp[1]).toFixed(3));
console.log('Self-dimer ΔG korelasyonu   r=' + pearson(hd[0], hd[1]).toFixed(3));
console.log('Heterodimer ΔG korelasyonu  r=' + pearson(ht[0], ht[1]).toFixed(3));
stats('Self-dimer |ΔG farkı|', hd[0].map((x, i) => Math.abs(x - hd[1][i])));
stats('Heterodimer |ΔG farkı|', ht[0].map((x, i) => Math.abs(x - ht[1][i])));
stats('Hairpin |ΔG farkı|', hp[0].map((x, i) => Math.abs(x - hp[1][i])));
if (t.max > 0.1) { console.error('HATA: Tm Primer3 ile 0.1 °C içinde uyuşmuyor'); process.exit(1); }
console.log('OK: Tm Primer3 ile uyumlu.');
