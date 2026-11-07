/*
 * Sanger primer tasarım motoru
 * ---------------------------------------------------------------
 * - Tm: SantaLucia 1998 nearest-neighbor (Primer3 "santalucia" yöntemi ile aynı),
 *   tuz düzeltmesi SantaLucia 1998, Mg2+/dNTP -> Na+ eşdeğeri von Ahsen 2001.
 * - İkincil yapı (hairpin, self-dimer, 3' dimer, heterodimer): basitleştirilmiş
 *   termodinamik hizalama (NN stack + loop cezaları). Primer3'ün "thal"
 *   algoritmasının yaklaşık bir karşılığıdır; mutlak değerler birkaç kcal/mol
 *   farklı olabilir, sıralama ve eşik kontrolü için uygundur.
 * - Tarayıcıda ve Node.js'de çalışır (UMD).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PrimerEngine = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var R = 1.987; // cal/(K*mol)
  var T37 = 310.15;

  // SantaLucia 1998 unified NN parametreleri: dH (kcal/mol), dS (cal/K/mol)
  var NN = {
    AA: [-7.9, -22.2], TT: [-7.9, -22.2],
    AT: [-7.2, -20.4],
    TA: [-7.2, -21.3],
    CA: [-8.5, -22.7], TG: [-8.5, -22.7],
    GT: [-8.4, -22.4], AC: [-8.4, -22.4],
    CT: [-7.8, -21.0], AG: [-7.8, -21.0],
    GA: [-8.2, -22.2], TC: [-8.2, -22.2],
    CG: [-10.6, -27.2],
    GC: [-9.8, -24.4],
    GG: [-8.0, -19.9], CC: [-8.0, -19.9]
  };
  var INIT_GC = [0.1, -2.8];
  var INIT_AT = [2.3, 4.1];
  var SYM = [0, -1.4];

  // Hairpin loop başlatma ΔG37 (SantaLucia & Hicks 2004)
  var HP_LOOP = { 3: 3.5, 4: 3.5, 5: 3.3, 6: 4.0, 7: 4.2, 8: 4.3, 9: 4.5, 10: 4.6, 12: 5.0, 14: 5.1, 16: 5.3, 18: 5.5, 20: 5.7, 25: 6.1, 30: 6.3 };
  var DUPLEX_INIT_DG = 1.96;
  // Uç uyumsuzlukları / sarkan uçlar (dangling end) için ortalama katkı.
  // Primer3 thal ile 608 oligo üzerinde kalibre edildi (bkz. tests/compare.js).
  var DUPLEX_END_DG = -1.9;
  var HAIRPIN_END_DG = -0.8;
  var TERMINAL_AT_DG = 0.05;

  var COMP = { A: 'T', T: 'A', G: 'C', C: 'G', N: 'N' };

  function revcomp(s) {
    var o = '';
    for (var i = s.length - 1; i >= 0; i--) o += COMP[s[i]] || 'N';
    return o;
  }
  function isComp(a, b) { return COMP[a] === b && a !== 'N'; }

  function defaultConditions() {
    // Primer3 varsayılanları
    return { mv: 50, dv: 1.5, dntp: 0.6, dna: 50 };
  }

  // von Ahsen 2001 / Primer3 divalent_to_monovalent (mM)
  function naEquivalent(c) {
    var dv = c.dv, dntp = c.dntp;
    if (dv < 0) dv = 0;
    if (dntp < 0) dntp = 0;
    var free = dv > dntp ? dv - dntp : 0;
    return c.mv + 120 * Math.sqrt(free);
  }

  function isSelfComplementary(s) { return s === revcomp(s); }

  function nnSums(s) {
    var dH = 0, dS = 0;
    for (var i = 0; i < s.length - 1; i++) {
      var p = NN[s.substr(i, 2)];
      if (!p) return null;
      dH += p[0]; dS += p[1];
    }
    return [dH, dS];
  }

  // Primer3 oligotm (santalucia + santalucia salt) eşleniği
  function thermo(seq, cond) {
    cond = cond || defaultConditions();
    var s = seq.toUpperCase();
    var sums = nnSums(s);
    if (!sums || s.length < 2) return null;
    var dH = sums[0], dS = sums[1];
    var first = s[0], last = s[s.length - 1];
    var ia = (first === 'A' || first === 'T') ? INIT_AT : INIT_GC;
    var ib = (last === 'A' || last === 'T') ? INIT_AT : INIT_GC;
    dH += ia[0] + ib[0];
    dS += ia[1] + ib[1];
    var sym = isSelfComplementary(s);
    if (sym) { dH += SYM[0]; dS += SYM[1]; }
    var na = naEquivalent(cond) / 1000; // M
    var dSsalt = dS + 0.368 * (s.length - 1) * Math.log(na);
    var ct = cond.dna * 1e-9;
    var tm = (dH * 1000) / (dSsalt + R * Math.log(sym ? ct : ct / 4)) - 273.15;
    var dG37 = dH - T37 * dSsalt / 1000;
    return { tm: tm, dH: dH, dS: dSsalt, dG: dG37 };
  }
  function tm(seq, cond) { var t = thermo(seq, cond); return t ? t.tm : NaN; }

  function gcPercent(s) {
    if (!s.length) return 0;
    var n = 0;
    for (var i = 0; i < s.length; i++) if (s[i] === 'G' || s[i] === 'C') n++;
    return 100 * n / s.length;
  }

  // Tek bir stack'in tuz düzeltmeli ΔG37'si
  function stackDG(di, saltTerm) {
    var p = NN[di];
    if (!p) return 0;
    return p[0] - T37 * (p[1] + saltTerm) / 1000;
  }
  function saltTerm(cond) { return 0.368 * Math.log(naEquivalent(cond) / 1000); }

  // 3' uç stabilitesi (son 5 baz duplex ΔG, Primer3 "end stability" benzeri, pozitif büyüklük)
  function endStability(seq, cond) {
    var s = seq.slice(-5);
    var st = saltTerm(cond || defaultConditions());
    var g = DUPLEX_INIT_DG;
    for (var i = 0; i < s.length - 1; i++) g += stackDG(s.substr(i, 2), st);
    if (s[0] === 'A' || s[0] === 'T') g += TERMINAL_AT_DG;
    if (s[4] === 'A' || s[4] === 'T') g += TERMINAL_AT_DG;
    return -g; // kcal/mol (büyük = daha stabil 3' uç)
  }

  /*
   * İki oligo arasındaki en stabil antiparalel hizalama (dimer).
   * a, b: 5'->3'. a[i] ile b[k] eşleşir (k = s - i), i artarken k azalır.
   * Ardışık komplementer bloklar (>=2 bp) NN stack ile puanlanır; aralarında
   * 1 veya 2 bazlık uyumsuzluk varsa iç loop cezası ile birleştirilir.
   * Döner: { dG, s, i0, i1, k0, k1, end3a, end3b }
   */
  function bestDuplexImpl(a, b, st, opts) {
    var n = a.length, m = b.length;
    var best = null;
    var need3a = opts.require3a, need3b = opts.require3b, needAny3 = opts.requireAny3;
    for (var s = 0; s <= n + m - 2; s++) {
      var iMin = Math.max(0, s - (m - 1)), iMax = Math.min(n - 1, s);
      var blocks = [];
      var i = iMin;
      while (i <= iMax) {
        if (isComp(a[i], b[s - i])) {
          var j = i;
          while (j + 1 <= iMax && isComp(a[j + 1], b[s - j - 1])) j++;
          if (j > i) blocks.push([i, j]); // en az 2 bp
          i = j + 1;
        } else i++;
      }
      if (!blocks.length) continue;
      var bdg = [];
      for (var q = 0; q < blocks.length; q++) {
        var gg = 0;
        for (var x = blocks[q][0]; x < blocks[q][1]; x++) gg += stackDG(a[x] + a[x + 1], st);
        bdg.push(gg);
      }
      for (var sb = 0; sb < blocks.length; sb++) {
        var g = bdg[sb];
        for (var eb = sb; eb < blocks.length; eb++) {
          if (eb > sb) {
            var gap = blocks[eb][0] - blocks[eb - 1][1] - 1;
            if (gap > 2) break;
            g += (gap === 1 ? 0.8 : 1.3) + bdg[eb];
          }
          var i0 = blocks[sb][0], i1 = blocks[eb][1];
          var k0 = s - i0, k1 = s - i1; // k0 > k1
          var has3a = i1 === n - 1;      // a'nın 3' ucu eşleşmiş
          var has3b = k0 === m - 1;      // b'nin 3' ucu eşleşmiş
          if (need3a && !has3a) continue;
          if (need3b && !has3b) continue;
          if (needAny3 && !has3a && !has3b) continue;
          var total = g + DUPLEX_INIT_DG + DUPLEX_END_DG;
          if (a[i0] === 'A' || a[i0] === 'T') total += TERMINAL_AT_DG;
          if (a[i1] === 'A' || a[i1] === 'T') total += TERMINAL_AT_DG;
          if (!best || total < best.dG) best = { dG: total, s: s, i0: i0, i1: i1, k0: k0, k1: k1, end3a: has3a, end3b: has3b };
        }
      }
    }
    if (!best) return { dG: 0, s: -1 };
    if (best.dG > 0) best.dG = 0;
    return best;
  }

  function dimer(a, b, cond) { return bestDuplexImpl(a, b, saltTerm(cond || defaultConditions()), {}); }
  function dimer3(a, b, cond) { return bestDuplexImpl(a, b, saltTerm(cond || defaultConditions()), { requireAny3: true }); }

  // Hairpin: kök (stem) + loop >= 3
  function hairpin(seq, cond) {
    var st = saltTerm(cond || defaultConditions());
    var n = seq.length;
    var best = { dG: 0 };
    // dış eşleşme (i, j), iç doğru büyüyen kök: (i+t, j-t)
    for (var i = 0; i < n; i++) {
      for (var j = n - 1; j > i + 3; j--) {
        if (!isComp(seq[i], seq[j])) continue;
        // yalnızca maksimal kökleri başlat (dışarıda eşleşme yoksa)
        if (i > 0 && j < n - 1 && isComp(seq[i - 1], seq[j + 1])) continue;
        var t = 0, g = 0;
        while (true) {
          var ii = i + t + 1, jj = j - t - 1;
          if (jj - ii - 1 < 3) break;
          if (!isComp(seq[ii], seq[jj])) break;
          g += stackDG(seq[i + t] + seq[ii], st);
          t++;
        }
        if (t < 2) continue; // en az 3 bp kök
        var loop = (j - t) - (i + t) - 1;
        if (loop < 3) continue;
        var total = g + loopPenalty(loop) + HAIRPIN_END_DG;
        if (seq[i] === 'A' || seq[i] === 'T') total += TERMINAL_AT_DG;
        if (total < best.dG) best = { dG: total, i: i, j: j, stem: t + 1, loop: loop, involves3: j >= n - 3 };
      }
    }
    return best;
  }
  function loopPenalty(L) {
    if (HP_LOOP[L] != null) return HP_LOOP[L];
    var keys = Object.keys(HP_LOOP).map(Number).sort(function (x, y) { return x - y; });
    if (L > 30) return 6.3 + 1.75 * 0.616 * Math.log(L / 30);
    for (var q = 0; q < keys.length - 1; q++) {
      if (L > keys[q] && L < keys[q + 1]) {
        var a = HP_LOOP[keys[q]], b = HP_LOOP[keys[q + 1]];
        return a + (b - a) * (L - keys[q]) / (keys[q + 1] - keys[q]);
      }
    }
    return 6.3;
  }

  // Dimer hizalamasını metin olarak göster (Primer3 tarzı)
  function renderDuplex(a, b, d) {
    if (!d || d.s < 0) return '';
    // a üstte 5'->3', b altta 3'->5'
    var bRev = b.split('').reverse().join(''); // 3'->5'
    // a[i] ile b[s-i] eşleşir. bRev indeksinde: b[k] = bRev[m-1-k]
    // a[i] karşısına bRev[m-1-(s-i)] = bRev[i + m - 1 - s] gelir -> kaydırma
    var m = b.length;
    var shift = m - 1 - d.s; // bRev index = i + shift
    var padA = Math.max(0, shift), padB = Math.max(0, -shift);
    var top = repeat(' ', padA) + a;
    var bot = repeat(' ', padB) + bRev;
    var mid = '';
    var len = Math.max(top.length, bot.length);
    for (var x = 0; x < len; x++) {
      var ai = x - padA, bi = x - padB;
      var ca = top[x], cb = bot[x];
      var inSeg = ai >= d.i0 && ai <= d.i1;
      mid += (ca && cb && isComp(ca, cb) && inSeg) ? '|' : ' ';
    }
    return "5' " + top + " 3'\n   " + mid + "\n3' " + bot + " 5'";
  }
  function repeat(c, n) { var o = ''; for (var i = 0; i < n; i++) o += c; return o; }

  function maxRun(s) {
    var best = 1, cur = 1;
    for (var i = 1; i < s.length; i++) {
      if (s[i] === s[i - 1]) { cur++; if (cur > best) best = cur; } else cur = 1;
    }
    return best;
  }
  function maxDinucRepeat(s) {
    var best = 1;
    for (var i = 0; i + 4 <= s.length; i++) {
      var di = s.substr(i, 2);
      if (di[0] === di[1]) continue;
      var c = 1, j = i + 2;
      while (j + 2 <= s.length && s.substr(j, 2) === di) { c++; j += 2; }
      if (c > best) best = c;
    }
    return best;
  }

  function overlaps(a0, a1, b0, b1) { return a0 < b1 && b0 < a1; }

  /*
   * Ana tasarım fonksiyonu.
   * input = {
   *   template: 'ACGT...' (üst iplik, büyük harf),
   *   tplStart0: şablonun genomik 0-tabanlı başlangıcı,
   *   chrom, varStart0, varEnd0 (0-tabanlı, yarı açık),
   *   snps: [{start0,end0,name,maf}], repeats:[{start0,end0,name}],
   *   cover: {start0,end0} | null   // örn. ekzonun tamamını kapsa
   * }
   * p = parametreler (aşağıda varsayılanlar)
   */
  function defaultParams() {
    return {
      sizeMin: 300, sizeMax: 650, sizeOpt: 450,
      lenMin: 18, lenOpt: 21, lenMax: 26,
      tmMin: 57, tmOpt: 60, tmMax: 63, tmDiffMax: 2.5,
      gcMin: 35, gcMax: 65,
      minDist: 60,       // primer 3' ucu ile varyant arası en az baz (Sanger ilk ~40 baz okunamaz)
      maxPolyX: 4,
      maxEndStability: 9.0,
      hairpinMax: -3.0,  // kcal/mol; bundan negatifse ret
      selfDimerMax: -9.0,
      endDimerMax: -6.0,
      heteroDimerMax: -9.0,
      snpPolicy: 'strict', // strict: primerde common SNP yok; relaxed: yalnızca 3' son 5 bazda yok
      avoidRepeats: true,
      numReturn: 5,
      cond: defaultConditions()
    };
  }

  function evalPrimer(seq, side, start0, ctx, p) {
    // side: 'F' veya 'R'; start0: üst iplikteki genomik başlangıç
    var L = seq.length;
    var t = thermo(seq, p.cond);
    if (!t) return null;
    var gc = gcPercent(seq);
    var res = { seq: seq, side: side, start0: start0, end0: start0 + L, len: L, tm: t.tm, gc: gc, issues: [], hard: false };
    if (seq.indexOf('N') >= 0) { res.hard = true; res.issues.push('N içeriyor'); return res; }
    if (t.tm < p.tmMin || t.tm > p.tmMax) { res.hard = true; }
    if (gc < p.gcMin || gc > p.gcMax) { res.hard = true; }
    var run = maxRun(seq);
    res.maxRun = run;
    if (run > p.maxPolyX) { res.hard = true; }
    if (maxDinucRepeat(seq) >= 4) { res.hard = true; }
    var last5 = seq.slice(-5);
    var gcLast5 = (last5.match(/[GC]/g) || []).length;
    res.gcClamp = gcLast5;
    if (gcLast5 > 3) res.hard = true;
    if (res.hard) return res;
    res.endStab = endStability(seq, p.cond);
    if (res.endStab > p.maxEndStability) { res.hard = true; return res; }

    // SNP kontrolü (3' uç pozisyonu: F için end0-1, R için start0)
    var three = side === 'F' ? res.end0 - 1 : res.start0;
    res.snps = [];
    for (var i = 0; i < ctx.snps.length; i++) {
      var s = ctx.snps[i];
      if (overlaps(s.start0, s.end0, res.start0, res.end0)) {
        var distFrom3 = side === 'F' ? (three - (s.end0 - 1)) : (s.start0 - three);
        if (distFrom3 < 0) distFrom3 = 0;
        res.snps.push({ name: s.name, maf: s.maf, distFrom3: distFrom3 });
      }
    }
    var snp3 = res.snps.some(function (x) { return x.distFrom3 < 5; });
    if (res.snps.length && (p.snpPolicy === 'strict' || snp3)) { res.hard = true; res.issues.push('primerde yaygın SNP'); return res; }

    res.repeats = [];
    for (var r = 0; r < ctx.repeats.length; r++) {
      var rp = ctx.repeats[r];
      if (overlaps(rp.start0, rp.end0, res.start0, res.end0)) res.repeats.push(rp.name);
    }
    if (res.repeats.length && p.avoidRepeats) { res.hard = true; res.issues.push('tekrar bölgesi'); return res; }

    res.sds = [];
    var sds = ctx.sds || [];
    for (var d = 0; d < sds.length; d++) {
      if (overlaps(sds[d].start0, sds[d].end0, res.start0, res.end0)) res.sds.push(sds[d]);
    }

    // ikincil yapılar
    var hp = hairpin(seq, p.cond);
    var sd = dimer(seq, seq, p.cond);
    var ed = dimer3(seq, seq, p.cond);
    res.hairpin = hp.dG; res.hairpinInfo = hp;
    res.selfDimer = sd.dG; res.selfDimerAln = sd;
    res.endDimer = ed.dG; res.endDimerAln = ed;
    if (hp.dG < p.hairpinMax || sd.dG < p.selfDimerMax || ed.dG < p.endDimerMax) { res.hard = true; return res; }

    // ceza (Primer3 tarzı ağırlıklar)
    var pen = 0;
    pen += Math.abs(t.tm - p.tmOpt) * 1.0;
    pen += Math.abs(L - p.lenOpt) * 0.5;
    pen += Math.abs(gc - 50) * 0.05;
    pen += Math.max(0, -hp.dG - 1) * 0.6;
    pen += Math.max(0, -sd.dG - 5) * 0.4;
    pen += Math.max(0, -ed.dG - 3) * 0.6;
    if (gcLast5 === 0) pen += 1.0;
    var last = seq[L - 1];
    if (last !== 'G' && last !== 'C') pen += 0.4;
    if (res.snps.length) pen += 3 * res.snps.length;
    if (res.repeats.length) pen += 4;
    if (res.sds.length) pen += 6;
    res.penalty = pen;
    return res;
  }

  // Şablonda başka bir yerde 3' uç eşleşmesi (yerel yanlış bağlanma) - her iki iplik
  function localMispriming(seq, ownStart0, template, tplStart0, k) {
    k = k || 12;
    var tail = seq.slice(-k);
    var rc = revcomp(tail);
    var hits = 0, idx;
    idx = template.indexOf(tail);
    while (idx >= 0) { if (Math.abs(tplStart0 + idx - (ownStart0)) > 30) hits++; idx = template.indexOf(tail, idx + 1); }
    idx = template.indexOf(rc);
    while (idx >= 0) { if (Math.abs(tplStart0 + idx - (ownStart0)) > 30) hits++; idx = template.indexOf(rc, idx + 1); }
    return hits;
  }

  function design(input, params) {
    var p = Object.assign(defaultParams(), params || {});
    p.cond = Object.assign(defaultConditions(), (params && params.cond) || {});
    var tpl = input.template.toUpperCase();
    var T0 = input.tplStart0;
    var ctx = { snps: input.snps || [], repeats: input.repeats || [] };
    var vS = input.varStart0, vE = input.varEnd0;
    var needS = vS, needE = vE;
    if (input.cover) { needS = Math.min(needS, input.cover.start0); needE = Math.max(needE, input.cover.end0); }

    var stats = { leftCandidates: 0, rightCandidates: 0, leftOk: 0, rightOk: 0, pairsEvaluated: 0 };
    var lefts = [], rights = [];
    // Sol primer: 3' ucu (end0) <= needS - minDist ; ürün <= sizeMax
    for (var L = p.lenMin; L <= p.lenMax; L++) {
      for (var st0 = Math.max(T0, needE + p.minDist - p.sizeMax); st0 + L <= needS - p.minDist; st0++) {
        var off = st0 - T0;
        if (off < 0 || off + L > tpl.length) continue;
        stats.leftCandidates++;
        var e = evalPrimer(tpl.substr(off, L), 'F', st0, ctx, p);
        if (e && !e.hard) lefts.push(e);
      }
      // Sağ primer: üst iplikte [q, q+L), q >= needE + minDist
      for (var q = needE + p.minDist; q + L <= Math.min(T0 + tpl.length, needS - p.minDist + p.sizeMax); q++) {
        var offR = q - T0;
        if (offR < 0 || offR + L > tpl.length) continue;
        stats.rightCandidates++;
        var er = evalPrimer(revcomp(tpl.substr(offR, L)), 'R', q, ctx, p);
        if (er && !er.hard) rights.push(er);
      }
    }
    stats.leftOk = lefts.length; stats.rightOk = rights.length;
    lefts.sort(function (a, b) { return a.penalty - b.penalty; });
    rights.sort(function (a, b) { return a.penalty - b.penalty; });
    var LT = lefts.slice(0, 250), RT = rights.slice(0, 250);

    var pairs = [];
    for (var a = 0; a < LT.length; a++) {
      for (var b = 0; b < RT.length; b++) {
        var l = LT[a], r = RT[b];
        var size = r.end0 - l.start0;
        if (size < p.sizeMin || size > p.sizeMax) continue;
        var dTm = Math.abs(l.tm - r.tm);
        if (dTm > p.tmDiffMax) continue;
        var pen = l.penalty + r.penalty + dTm * 0.5 + Math.abs(size - p.sizeOpt) * 0.01;
        // varyantın amplikonda daha ortada olması (her iki yönden okunabilirlik)
        var dF = vS - l.end0, dR = r.start0 - vE;
        // Sanger: varyantın her iki yönden de primerden >= ~100 baz uzakta olması ideal
        var dMin = Math.min(dF, dR);
        if (dMin < 100) pen += (100 - dMin) * 0.04;
        pen += Math.abs(dF - dR) / Math.max(1, size) * 1;
        pairs.push({ left: l, right: r, size: size, dTm: dTm, penalty: pen });
      }
    }
    pairs.sort(function (x, y) { return x.penalty - y.penalty; });
    stats.pairsEvaluated = pairs.length;

    // heterodimer ve yerel yanlış bağlanma kontrolü, çeşitlilik
    var chosen = [];
    for (var c = 0; c < pairs.length && chosen.length < p.numReturn && c < 4000; c++) {
      var pr = pairs[c];
      var div = chosen.every(function (o) {
        return Math.abs(o.left.start0 - pr.left.start0) >= 10 && Math.abs(o.right.start0 - pr.right.start0) >= 10;
      });
      if (!div) continue;
      var hd = dimer(pr.left.seq, pr.right.seq, p.cond);
      var hd3 = dimer3(pr.left.seq, pr.right.seq, p.cond);
      if (hd.dG < p.heteroDimerMax || hd3.dG < p.endDimerMax) continue;
      var mpL = localMispriming(pr.left.seq, pr.left.start0, tpl, T0);
      var mpR = localMispriming(pr.right.seq, pr.right.start0, tpl, T0);
      if (mpL + mpR > 0) continue;
      pr.heteroDimer = hd.dG; pr.heteroAln = hd;
      pr.heteroDimer3 = hd3.dG; pr.heteroAln3 = hd3;
      pr.penalty += Math.max(0, -hd.dG - 5) * 0.4 + Math.max(0, -hd3.dG - 3) * 0.6;
      annotatePair(pr, input, p, tpl, T0);
      chosen.push(pr);
    }
    chosen.sort(function (x, y) { return x.penalty - y.penalty; });
    return { pairs: chosen, stats: stats, params: p };
  }

  function annotatePair(pr, input, p, tpl, T0) {
    var l = pr.left, r = pr.right;
    var amp = tpl.substring(l.start0 - T0, r.end0 - T0);
    pr.amplicon = amp;
    pr.ampStart0 = l.start0; pr.ampEnd0 = r.end0;
    pr.ampGC = gcPercent(amp);
    var na = naEquivalent(p.cond) / 1000;
    pr.ampTm = 81.5 + 16.6 * Math.log10(na) + 0.41 * pr.ampGC - 675 / amp.length;
    pr.varFromF = input.varStart0 - l.end0;     // ileri okumada varyantın primer sonrası konumu
    pr.varFromR = r.start0 - input.varEnd0;     // geri okumada
    pr.warnings = [];
    if (pr.ampGC > 65) pr.warnings.push('Amplikon GC oranı yüksek (%' + pr.ampGC.toFixed(0) + '): DMSO/betain veya GC-rich tampon gerekebilir.');
    // varyant ile primer arasında homopolimer (Sanger kayması)
    var between = tpl.substring(l.end0 - T0, input.varStart0 - T0);
    var betweenR = tpl.substring(input.varEnd0 - T0, r.start0 - T0);
    if (maxRun(between) >= 9) pr.warnings.push('İleri primer ile varyant arasında ≥9 bazlık homopolimer: ileri okuma kalitesi düşebilir, geri okumaya güvenin.');
    if (maxRun(betweenR) >= 9) pr.warnings.push('Varyant ile geri primer arasında ≥9 bazlık homopolimer: geri okuma kalitesi düşebilir, ileri okumaya güvenin.');
    var snpsIn = (input.snps || []).filter(function (s) { return overlaps(s.start0, s.end0, l.end0, r.start0); });
    pr.ampliconSnps = snpsIn;
    if (pr.varFromF < 60 || pr.varFromR < 60) pr.warnings.push('Varyant primerlerden birine 60 bazdan yakın: o yöndeki okuma güvenilir olmayabilir.');
    if (l.snps && l.snps.length || r.snps && r.snps.length) pr.warnings.push('Primerde (3\' uçta değil) yaygın SNP var: allel düşmesi (allele drop-out) riski.');
    if (l.repeats && l.repeats.length || r.repeats && r.repeats.length) pr.warnings.push('Primer tekrar bölgesine (RepeatMasker/simple repeat) denk geliyor: genom genelinde özgüllüğü mutlaka kontrol edin.');
  }


  /* =====================================================================
   * Yapısal varyant (CNV / SV) tasarımı
   * Her kesim noktası i için gerçek birleşme noktası x_i, [a_i, b_i]
   * aralığındadır (0-tabanlı sınır koordinatı; kesin ise a_i = b_i).
   * Her kesim noktasında iki primer aranır:
   *   L_i: kesim noktasının solunda, sağa bakan (ileri) primer
   *   R_i: kesim noktasının sağında, sola bakan (geri) primer
   * Testler (junction / normal allel) bu dört primerin kombinasyonlarıdır.
   * ===================================================================== */
  function svParamsStd() {
    return { lenMin: 20, lenOpt: 23, lenMax: 27, tmMin: 58, tmOpt: 60, tmMax: 62.5, gcMin: 35, gcMax: 65 };
  }
  function svParamsLong() {
    return { lenMin: 24, lenOpt: 27, lenMax: 32, tmMin: 62.5, tmOpt: 65, tmMax: 68, gcMin: 38, gcMax: 62, maxEndStability: 9.5 };
  }

  // Bir pencere içinde belirli yönde en iyi primerler (çeşitlendirilmiş)
  function pickPrimers(tpl, side, winS, winE, p, n) {
    var cand = [];
    if (winE - winS < p.lenMin) return cand;
    for (var L = p.lenMin; L <= p.lenMax; L++) {
      for (var s0 = winS; s0 + L <= winE; s0++) {
        var off = s0 - tpl.start0;
        if (off < 0 || off + L > tpl.seq.length) continue;
        var raw = tpl.seq.substr(off, L);
        var e = evalPrimer(side === 'F' ? raw : revcomp(raw), side, s0, tpl, p);
        if (e && !e.hard) cand.push(e);
      }
    }
    cand.sort(function (x, y) { return x.penalty - y.penalty; });
    var out = [];
    for (var i = 0; i < cand.length && out.length < n; i++) {
      var c = cand[i];
      if (out.some(function (o) { return Math.abs(o.start0 - c.start0) < 15; })) continue;
      if (localMispriming(c.seq, c.start0, tpl.seq, tpl.start0) > 0) continue;
      out.push(c);
    }
    return out;
  }

  function svWindows(input, p) {
    var b = input.bps, dMin = p.dMin, dMax = p.dMax;
    var w = {
      L1: [b[0].a - dMax, b[0].a - dMin], R1: [b[0].b + dMin, b[0].b + dMax],
      L2: [b[1].a - dMax, b[1].a - dMin], R2: [b[1].b + dMin, b[1].b + dMax]
    };
    if (input.type !== 'TRA') {
      // R1 ve L2 etkilenen segmentin içinde kalmalı (b1, a2)
      w.R1[1] = Math.min(w.R1[1], b[1].a);
      w.L2[0] = Math.max(w.L2[0], b[0].b);
    }
    return w;
  }

  var SV_SIDES = [['L1', 0, 'F', 'tplL'], ['R1', 0, 'R', 'tplR'], ['L2', 1, 'F', 'tplL'], ['R2', 1, 'R', 'tplR']];

  // Bir primer seti için testler ve beklenen ürün boyları
  function svAssays(type, c, bps) {
    var a1 = bps[0].a, b1 = bps[0].b, a2 = bps[1].a, b2 = bps[1].b;
    var L1 = c.L1, R1 = c.R1, L2 = c.L2, R2 = c.R2, out = [];
    function add(o) { if (o.primers.every(function (k) { return c[k]; })) out.push(o); }
    function rng(x, y) { return { min: Math.min(x, y), max: Math.max(x, y) }; }
    if (type === 'DEL') {
      if (L1 && R2) add({ id: 'J', role: 'junction', title: 'Delesyon kesim noktası (junction) PCR', primers: ['L1', 'R2'],
        mut: rng((a1 - L1.start0) + (R2.end0 - b2), (b1 - L1.start0) + (R2.end0 - a2)), ref: R2.end0 - L1.start0 });
      if (L1 && R1) add({ id: 'W1', role: 'wt', title: 'Normal allel kontrolü (kesim noktası 1)', primers: ['L1', 'R1'], mut: null, ref: R1.end0 - L1.start0 });
      if (L2 && R2) add({ id: 'W2', role: 'wt', title: 'Normal allel kontrolü (kesim noktası 2)', primers: ['L2', 'R2'], mut: null, ref: R2.end0 - L2.start0 });
    } else if (type === 'DUP') {
      if (L2 && R1) add({ id: 'J', role: 'junction', title: 'Tandem duplikasyon birleşme (junction) PCR', primers: ['L2', 'R1'],
        mut: rng((a2 - L2.start0) + (R1.end0 - b1), (b2 - L2.start0) + (R1.end0 - a1)), ref: null });
      if (L1 && R1) add({ id: 'W1', role: 'wt', title: 'Kesim noktası 1 referans ürünü (pozitif kontrol)', primers: ['L1', 'R1'], mut: null, ref: R1.end0 - L1.start0, both: true });
      if (L2 && R2) add({ id: 'W2', role: 'wt', title: 'Kesim noktası 2 referans ürünü (pozitif kontrol)', primers: ['L2', 'R2'], mut: null, ref: R2.end0 - L2.start0, both: true });
    } else if (type === 'INV') {
      if (L1 && L2) add({ id: 'J1', role: 'junction', title: 'İnversiyon birleşme 1 (sol)', primers: ['L1', 'L2'],
        mut: rng((a1 - L1.start0) + (a2 - L2.start0), (b1 - L1.start0) + (b2 - L2.start0)), ref: null });
      if (R1 && R2) add({ id: 'J2', role: 'junction', title: 'İnversiyon birleşme 2 (sağ)', primers: ['R1', 'R2'],
        mut: rng((R1.end0 - b1) + (R2.end0 - b2), (R1.end0 - a1) + (R2.end0 - a2)), ref: null });
      if (L1 && R1) add({ id: 'W1', role: 'wt', title: 'Normal allel kontrolü (kesim noktası 1)', primers: ['L1', 'R1'], mut: null, ref: R1.end0 - L1.start0 });
      if (L2 && R2) add({ id: 'W2', role: 'wt', title: 'Normal allel kontrolü (kesim noktası 2)', primers: ['L2', 'R2'], mut: null, ref: R2.end0 - L2.start0 });
    } else if (type === 'TRA') {
      if (L1 && R2) add({ id: 'JA', role: 'junction', title: 'Türev kromozom 1: A-sol + B-sağ', primers: ['L1', 'R2'], orient: 'std',
        mut: rng((a1 - L1.start0) + (R2.end0 - b2), (b1 - L1.start0) + (R2.end0 - a2)), ref: null });
      if (L2 && R1) add({ id: 'JB', role: 'junction', title: 'Türev kromozom 2: B-sol + A-sağ', primers: ['L2', 'R1'], orient: 'std',
        mut: rng((a2 - L2.start0) + (R1.end0 - b1), (b2 - L2.start0) + (R1.end0 - a1)), ref: null });
      if (L1 && L2) add({ id: 'JC', role: 'junction', title: 'Ters yönelim: A-sol + B-sol', primers: ['L1', 'L2'], orient: 'inv',
        mut: rng((a1 - L1.start0) + (a2 - L2.start0), (b1 - L1.start0) + (b2 - L2.start0)), ref: null });
      if (R1 && R2) add({ id: 'JD', role: 'junction', title: 'Ters yönelim: A-sağ + B-sağ', primers: ['R1', 'R2'], orient: 'inv',
        mut: rng((R1.end0 - b1) + (R2.end0 - b2), (R1.end0 - a1) + (R2.end0 - a2)), ref: null });
      if (L1 && R1) add({ id: 'W1', role: 'wt', title: 'Normal kromozom A kontrolü', primers: ['L1', 'R1'], mut: null, ref: R1.end0 - L1.start0 });
      if (L2 && R2) add({ id: 'W2', role: 'wt', title: 'Normal kromozom B kontrolü', primers: ['L2', 'R2'], mut: null, ref: R2.end0 - L2.start0 });
    }
    return out;
  }

  function pcrClass(size, p) {
    if (size == null) return null;
    if (size <= p.stdMax) return 'std';
    if (size <= p.longMax) return 'long';
    return 'none';
  }

  /*
   * input = { type: 'DEL'|'DUP'|'INV'|'TRA',
   *           bps: [{ a, b, tplL:{seq,start0,snps,repeats,sds}, tplR:{...} }, {...}] }
   * params: primer parametreleri + dMin, dMax, nAlt, stdMax, longMax
   */
  function designSV(input, params) {
    var p = Object.assign(defaultParams(), { dMin: 60, dMax: 450, nAlt: 3, stdMax: 3000, longMax: 15000, perSide: 6 }, params || {});
    p.cond = Object.assign(defaultConditions(), (params && params.cond) || {});
    var tiers = [
      { label: 'Sıkı kriterler', p: p },
      { label: "Gevşetilmiş: 3' ucunda olmayan yaygın SNP'ye izin, Tm ±1 °C, GC %30–70", p: Object.assign({}, p, { snpPolicy: 'relaxed', tmMin: p.tmMin - 1, tmMax: p.tmMax + 1, gcMin: Math.min(p.gcMin, 30), gcMax: Math.max(p.gcMax, 70) }) },
      { label: 'Gevşetilmiş: tekrar bölgesine izin, arama penceresi genişletildi', p: Object.assign({}, p, { snpPolicy: 'relaxed', avoidRepeats: false, tmMin: p.tmMin - 2, tmMax: p.tmMax + 2, gcMin: 30, gcMax: 70, dMax: Math.round(p.dMax * 1.6) }) }
    ];
    var lists = {}, sideInfo = {};
    SV_SIDES.forEach(function (sd) {
      var name = sd[0], bp = input.bps[sd[1]], side = sd[2], tpl = bp[sd[3]];
      lists[name] = []; sideInfo[name] = { tier: null };
      if (!tpl) return;
      for (var t = 0; t < tiers.length && lists[name].length < 2; t++) {
        var w = svWindows(input, tiers[t].p)[name];
        var got = pickPrimers(tpl, side, w[0], w[1], tiers[t].p, p.perSide);
        got.forEach(function (g) {
          if (lists[name].some(function (o) { return Math.abs(o.start0 - g.start0) < 15; })) return;
          g.tier = t; g.tierLabel = tiers[t].label; g.name = name; lists[name].push(g);
        });
        if (got.length && sideInfo[name].tier == null) sideInfo[name].tier = t;
      }
      lists[name] = lists[name].slice(0, p.perSide);
    });

    // çapraz dimer önbelleği
    var names = SV_SIDES.map(function (s) { return s[0]; });
    var dim = {};
    function dkey(a, i, b, j) { return a + i + '|' + b + j; }
    for (var x = 0; x < names.length; x++) for (var y = x + 1; y < names.length; y++) {
      lists[names[x]].forEach(function (pa, i) {
        lists[names[y]].forEach(function (pb, j) {
          dim[dkey(names[x], i, names[y], j)] = { dg: dimer(pa.seq, pb.seq, p.cond).dG, dg3: dimer3(pa.seq, pb.seq, p.cond).dG };
        });
      });
    }

    var combos = [];
    var idx = {};
    (function rec(k) {
      if (k === names.length) {
        var c = {}, pen = 0, tms = [], worst = { dg: 0, dg3: 0, pair: null }, ok = true;
        names.forEach(function (n) { c[n] = idx[n] == null ? null : lists[n][idx[n]]; if (c[n]) { pen += c[n].penalty; tms.push(c[n].tm); } });
        if (tms.length < 2) return;
        for (var u = 0; u < names.length && ok; u++) for (var v = u + 1; v < names.length; v++) {
          if (idx[names[u]] == null || idx[names[v]] == null) continue;
          var d = dim[dkey(names[u], idx[names[u]], names[v], idx[names[v]])];
          if (d.dg < p.heteroDimerMax || d.dg3 < p.endDimerMax) { ok = false; break; }
          pen += Math.max(0, -d.dg - 5) * 0.4 + Math.max(0, -d.dg3 - 3) * 0.6;
          if (d.dg < worst.dg) worst = { dg: d.dg, dg3: d.dg3, pair: [names[u], names[v]] };
        }
        if (!ok) return;
        var spread = Math.max.apply(null, tms) - Math.min.apply(null, tms);
        pen += spread * 1.0;
        var assays = svAssays(input.type, c, input.bps);
        var j = assays.filter(function (z) { return z.role === 'junction'; });
        j.forEach(function (z) { pen += z.mut.max / 1000 * 0.6; });
        combos.push({ primers: c, penalty: pen, tmSpread: spread, worstDimer: worst, assays: assays });
        return;
      }
      var n = names[k];
      if (!lists[n].length) { idx[n] = null; rec(k + 1); return; }
      for (var i = 0; i < lists[n].length; i++) { idx[n] = i; rec(k + 1); }
    })(0);
    combos.sort(function (u, v) { return u.penalty - v.penalty; });

    var sets = [];
    for (var ci = 0; ci < combos.length && sets.length < p.nAlt; ci++) {
      var cb = combos[ci];
      var disjoint = sets.every(function (s) {
        return names.every(function (n) { return !cb.primers[n] || !s.primers[n] || Math.abs(cb.primers[n].start0 - s.primers[n].start0) >= 15; });
      });
      if (!disjoint) continue;
      cb.assays.forEach(function (z) {
        var mx = z.mut ? z.mut.max : z.ref;
        z.pcr = pcrClass(mx, p);
        z.refPcr = pcrClass(z.ref, p);
      });
      cb.idx = sets.length + 1;
      sets.push(cb);
    }
    return { sets: sets, lists: lists, sideInfo: sideInfo, params: p };
  }

  /* =====================================================================
   * PCR koşulu önerisi
   * o = { kind: 'std'|'long'|'qpcr', tms: [..], sizeMax, gc, multiplex, cond }
   * ===================================================================== */
  function round05(x) { return Math.round(x * 2) / 2; }
  function fmtTime(sec) {
    if (sec < 60) return sec + ' s';
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ' dk' + (s ? ' ' + s + ' s' : '');
  }
  function pcrConditions(o) {
    var cond = o.cond || defaultConditions();
    var tmMin = Math.min.apply(null, o.tms), tmMax = Math.max.apply(null, o.tms);
    var gc = o.gc, size = o.sizeMax || 500;
    var r = { kind: o.kind, notes: [], mix: [], program: [], touchdown: null };
    var dmso = gc != null && gc > 60;
    r.basis = 'Tm değerleri ' + cond.mv + ' mM Na⁺/K⁺, ' + cond.dv + ' mM Mg²⁺, ' + cond.dntp + ' mM dNTP ve ' + cond.dna + ' nM primer için SantaLucia yöntemiyle hesaplandı.';
    if (o.kind === 'qpcr') {
      var taq = tmMin >= 58 ? 60 : 58;
      r.title = 'qPCR (SYBR Green / EvaGreen) – doz analizi';
      r.polymerase = 'Hazır SYBR Green qPCR master mix (hot-start polimeraz içerir)';
      r.ta = taq; r.gradient = [taq - 3, taq + 2];
      r.mix = [['2× SYBR master mix', '1×'], ['Her primer', '200–400 nM'], ['Genomik DNA', '5–20 ng (tüm örneklerde eşit)'], ['Toplam hacim', '10–20 µL'], ['Tekrar', 'Her örnek üçlü (triplicate)']];
      r.program = [
        { step: 'Polimeraz aktivasyonu', temp: '95 °C', time: '2–10 dk (kite göre)', cycles: 1 },
        { step: 'Denatürasyon', temp: '95 °C', time: '15 s', cycles: 40, group: true },
        { step: 'Bağlanma + uzama (okuma)', temp: taq + ' °C', time: '60 s', cycles: 40, group: true },
        { step: 'Erime eğrisi', temp: '65 → 95 °C', time: '0.5 °C adım', cycles: 1 }
      ];
      if (tmMin < 58) r.notes.push('Bazı primerlerin Tm değeri 58 °C\'nin altında (en düşük ' + tmMin.toFixed(1) + ' °C): bağlanma 58 °C önerildi; bu hedefleri gradyanla doğrulayın.');
      r.notes.push('Her çalışmada bir referans lokus (ör. laboratuvarınızda valide RNase P/RPPH1 veya ALB assay\'i), normal kontrol DNA ve kalıpsız kontrol (NTC) kullanın.');
      r.notes.push('Primer verimliliğini 5 noktalı seri dilüsyonla doğrulayın (%90–110, R² > 0.98). Erime eğrisinde tek pik olmalı.');
      r.notes.push('ΔΔCt ile beklenen oranlar: heterozigot delesyon ≈ 0.5, homozigot/hemizigot delesyon 0, heterozigot duplikasyon ≈ 1.5, normal ≈ 1.0.');
      r.notes.push('ddPCR tercih edilirse aynı primerler EvaGreen ile kullanılabilir; bağlanma sıcaklığını 55–62 °C gradyan ile optimize edin.');
      return r;
    }
    if (o.kind === 'long') {
      var twoStep = tmMin >= 63.5;
      var ta = twoStep ? 68 : round05(tmMin - 3);
      var extMin = Math.max(1, Math.ceil(size / 1000));
      r.title = 'Long-range PCR';
      r.polymerase = 'Long-range / yüksek doğruluklu polimeraz (ör. LongAmp Taq, PrimeSTAR GXL, KAPA LongRange, TaKaRa LA Taq)';
      r.ta = ta; r.gradient = twoStep ? null : [ta - 2, ta + 3];
      r.mix = [['Tampon (kitle gelen)', '1× (Mg²⁺ kitteki gibi, genellikle 1.5–2.5 mM)'], ['dNTP', '0.3–0.4 mM (her biri)'], ['Her primer', '0.2–0.4 µM' + (o.multiplex ? ' (multipleks: 0.2 µM)' : '')], ['Polimeraz', 'Üretici önerisi'], ['Genomik DNA', '50–200 ng yüksek molekül ağırlıklı DNA'], ['Toplam hacim', '25–50 µL']];
      r.program = [{ step: 'Başlangıç denatürasyonu', temp: '94 °C', time: '1–2 dk (98 °C\'lik kitlerde 30 s)', cycles: 1 },
        { step: 'Denatürasyon', temp: '94 °C', time: '10–15 s (98 °C\'de 10 s)', cycles: 30, group: true }];
      if (!twoStep) r.program.push({ step: 'Bağlanma', temp: ta + ' °C', time: '15–20 s', cycles: 30, group: true });
      r.program.push({ step: twoStep ? 'Bağlanma + uzama (iki aşamalı)' : 'Uzama', temp: '68 °C', time: extMin + ' dk (≈1 dk/kb)', cycles: 30, group: true });
      r.program.push({ step: 'Son uzama', temp: '68 °C', time: '10 dk', cycles: 1 });
      r.program.push({ step: 'Bekleme', temp: '4–10 °C', time: '∞', cycles: 1 });
      r.notes.push('DNA bütünlüğü kritik: vortekslemeyin, geniş uçlu pipet kullanın; mümkünse DIN ≥ 7 ve A260/280 ≈ 1.8 olmalı.');
      if (size > 10000) r.notes.push('10 kb üzeri ürünlerde son 15 döngüde her döngü uzama süresine +10–20 s eklemek (auto-extension) verimi artırır.');
      r.notes.push('Ürünü %0.6–0.8 agaroz jelde, geniş aralıklı (ör. 1 kb extended) merdivenle ve uzun süre koşturun.');
      r.notes.push('Ürün Sanger için uzunsa, iç primerlerle (primer walking) veya amplikon NGS / uzun okuma ile dizileyin.');
    } else {
      var ta2 = round05(tmMin - 3);
      var ext = Math.max(30, Math.ceil(size / 1000 * 60 / 15) * 15);
      r.title = 'Standart PCR (Sanger amplikonu)';
      r.polymerase = 'Hot-start Taq polimeraz (ör. HotStarTaq, AmpliTaq Gold, GoTaq Hot Start)';
      r.ta = ta2; r.gradient = [ta2 - 3, ta2 + 3];
      r.mix = [['PCR tamponu', '1×'], ['MgCl₂', cond.dv + ' mM (Tm hesabındaki değer; ürün zayıfsa 2.0–2.5 mM)'], ['dNTP', '0.2 mM (her biri)'], ['Her primer', o.multiplex ? '0.2 µM (multipleks)' : '0.2–0.4 µM'], ['Polimeraz', '0.5–1.25 U'], ['Genomik DNA', '20–50 ng'], ['Toplam hacim', '25 µL']];
      r.program = [
        { step: 'Başlangıç denatürasyonu / hot-start aktivasyonu', temp: '95 °C', time: '2–15 dk (polimeraza göre)', cycles: 1 },
        { step: 'Denatürasyon', temp: '95 °C', time: '30 s', cycles: 35, group: true },
        { step: 'Bağlanma', temp: (dmso ? round05(ta2 - 2.5) : ta2) + ' °C', time: '30 s', cycles: 35, group: true },
        { step: 'Uzama', temp: '72 °C', time: fmtTime(ext) + ' (≈1 dk/kb)', cycles: 35, group: true },
        { step: 'Son uzama', temp: '72 °C', time: '5–7 dk', cycles: 1 },
        { step: 'Bekleme', temp: '4–10 °C', time: '∞', cycles: 1 }
      ];
      r.touchdown = '10 döngü: bağlanma ' + (ta2 + 5) + ' °C\'den başlayıp her döngüde 0.5 °C düşürülür; ardından 25 döngü ' + ta2 + ' °C.';
      r.notes.push('Ürünü %' + (size < 1000 ? '1.5–2' : '1') + ' agaroz jelde kontrol edin; Sanger öncesi ExoSAP veya kolonla temizleyin ve aynı primerlerle (ya da M13 kuyruklarıyla) dizileyin.');
    }
    if (o.title) r.title = o.title;
    if (dmso) r.notes.push('Amplikon GC oranı yüksek (%' + gc.toFixed(0) + '): %5 DMSO veya 1 M betain ekleyin. %5 DMSO Tm\'yi ~3 °C düşürür; programdaki bağlanma sıcaklığı buna göre ' + (o.kind === 'long' ? 'gerekirse' : '2.5 °C') + ' düşürüldü.' + (gc > 70 ? ' GC > %70 için GC-rich tampon/polimeraz tercih edin.' : ''));
    if (tmMax - tmMin > 2.5) r.notes.push('Primer Tm farkı ' + (tmMax - tmMin).toFixed(1) + ' °C: touchdown programı veya gradyan ile optimizasyon önerilir.');
    if (o.multiplex) r.notes.push('Multipleks reaksiyondan önce her primer çiftini tekli reaksiyonda doğrulayın; uzama süresi en uzun ürüne göre ayarlandı.');
    r.notes.push('Bu bir başlangıç önerisidir. İlk denemede ' + (r.gradient ? r.gradient[0] + '–' + r.gradient[1] + ' °C gradyan ile, ' : '') + 'normal kontrol ve kalıpsız kontrol (NTC) ile doğrulayın.');
    return r;
  }

  return {
    designSV: designSV, svAssays: svAssays, svWindows: svWindows, pickPrimers: pickPrimers, pcrConditions: pcrConditions,
    svParamsStd: svParamsStd, svParamsLong: svParamsLong, pcrClass: pcrClass,
    revcomp: revcomp, thermo: thermo, tm: tm, gcPercent: gcPercent,
    naEquivalent: naEquivalent, endStability: endStability,
    hairpin: hairpin, dimer: dimer, dimer3: dimer3, renderDuplex: renderDuplex,
    maxRun: maxRun, design: design, evalPrimer: evalPrimer,
    defaultParams: defaultParams, defaultConditions: defaultConditions,
    localMispriming: localMispriming
  };
});
