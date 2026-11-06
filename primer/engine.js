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

  return {
    revcomp: revcomp, thermo: thermo, tm: tm, gcPercent: gcPercent,
    naEquivalent: naEquivalent, endStability: endStability,
    hairpin: hairpin, dimer: dimer, dimer3: dimer3, renderDuplex: renderDuplex,
    maxRun: maxRun, design: design, evalPrimer: evalPrimer,
    defaultParams: defaultParams, defaultConditions: defaultConditions,
    localMispriming: localMispriming
  };
});
