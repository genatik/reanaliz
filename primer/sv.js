/* CNV / yapısal varyant doğrulama: test önerisi, junction / long-range / qPCR primerleri, PCR koşulları */
(function () {
  'use strict';
  var E = window.PrimerEngine, U = null;
  var $ = function (id) { return document.getElementById(id); };
  var TYPES = { DEL: 'Delesyon', DUP: 'Duplikasyon', INV: 'İnversiyon', TRA: 'Translokasyon' };
  var MODES = { exact: 'Kesin (bp düzeyi)', exon: 'Ekzon düzeyi (WES/CES/panel)', manual: 'Elle belirsizlik' };
  var SV_STEPS = [
    ['parse', 'Varyant ve kesim noktası pencereleri belirleniyor'],
    ['genes', 'UCSC: bölgedeki genler, ekzonlar ve segmental duplikasyonlar'],
    ['bp1', 'UCSC: kesim noktası 1 çevresi (dizi, SNP, tekrar)'],
    ['bp2', 'UCSC: kesim noktası 2 çevresi (dizi, SNP, tekrar)'],
    ['design', 'Junction ve normal allel primerleri tasarlanıyor'],
    ['dosage', 'Doz analizi (qPCR/ddPCR) ve kesim noktası daraltma primerleri'],
    ['report', 'Test önerisi ve PCR koşulları hazırlanıyor']
  ];
  var STD_MAX = 3000, LONG_MAX = 15000, WALK_MAX = 300000;
  var S = null;

  function esc(x) { return U.esc(x); }
  function fmt(x, d) { return U.fmt(x, d); }
  function comma(x) { return U.comma(x); }
  function bp(n) {
    if (n == null) return '–';
    if (n < 1000) return n + ' bp';
    if (n < 1e6) return (n / 1000).toFixed(n < 10000 ? 2 : 1) + ' kb';
    return (n / 1e6).toFixed(2) + ' Mb';
  }
  function rangeTxt(r) { return !r ? '–' : (r.min === r.max ? bp(r.min) : bp(r.min) + ' – ' + bp(r.max)); }

  /* ---------------- UCSC istekleri (nazik hız sınırı) ---------------- */
  var lastReq = 0;
  async function ucsc(url, label) {
    var w = lastReq + 250 - Date.now();
    if (w > 0) await U.sleep(w);
    lastReq = Date.now();
    return U.getJSON(url, label);
  }
  async function track(build, chrom, s, e, t) {
    var d = await ucsc(U.UCSC_API + '/track?genome=' + build + ';chrom=' + chrom + ';start=' + Math.max(0, s) + ';end=' + e + ';track=' + t + ';maxItemsOutput=5000', 'UCSC ' + t);
    return d[t] || [];
  }
  async function region(build, chrom, s, e, withSD) {
    s = Math.max(0, Math.round(s)); e = Math.round(e);
    var d = await ucsc(U.UCSC_API + '/sequence?genome=' + build + ';chrom=' + chrom + ';start=' + s + ';end=' + e, 'UCSC dizi');
    var t = { seq: String(d.dna || '').toUpperCase(), start0: s, end0: e, chrom: chrom };
    if (!t.seq) throw new Error('UCSC ' + chrom + ':' + s + '-' + e + ' için dizi döndürmedi.');
    var snp = await track(build, chrom, s, e, 'dbSnp155Common');
    var rm = await track(build, chrom, s, e, 'rmsk');
    var sr = await track(build, chrom, s, e, 'simpleRepeat');
    var sd = withSD ? await track(build, chrom, s, e, 'genomicSuperDups') : [];
    t.snps = snp.map(function (x) { return { start0: x.chromStart, end0: Math.max(x.chromEnd, x.chromStart + 1), name: x.name, maf: U.maxMaf(x) }; });
    t.repeats = rm.map(function (r) { return { start0: r.genoStart, end0: r.genoEnd, name: r.repName + ' (' + r.repClass + ')' }; })
      .concat(sr.map(function (r) { return { start0: r.chromStart, end0: r.chromEnd, name: 'Basit tekrar' }; }));
    t.sds = sd.map(sdObj);
    return t;
  }
  function sdObj(x) { return { start0: x.chromStart, end0: x.chromEnd, other: x.otherChrom + ':' + comma(x.otherStart + 1) + '-' + comma(x.otherEnd), frac: x.fracMatch }; }
  function gcOf(seq) { return E.gcPercent(seq); }

  /* ---------------- Girdi çözümleme ---------------- */
  function chromFromNC(n) { n = parseInt(n, 10); return n === 23 ? 'chrX' : n === 24 ? 'chrY' : 'chr' + n; }
  function typeFromWord(w) {
    if (!w) return null; w = w.toLowerCase();
    if (/^del/.test(w)) return 'DEL';
    if (/^dup/.test(w)) return 'DUP';
    if (/^inv/.test(w)) return 'INV';
    return null;
  }
  function parseInterval(text) {
    var t = text.trim().replace(/,/g, '').replace(/\s+/g, ' ');
    var m;
    if ((m = t.match(/^(?:NC_0000(\d\d)\.\d+|(?:chr)?([0-9]{1,2}|X|Y)):g\.(\d+)(?:_(\d+))?\s*([a-z]+)?/i))) {
      return { chrom: m[1] ? chromFromNC(m[1]) : U.chromName(m[2]), start: +m[3], end: +(m[4] || m[3]), type: typeFromWord(m[5]) };
    }
    if ((m = t.match(/^(?:chr)?([0-9]{1,2}|X|Y)\s*[:_ ]\s*(\d+)\s*(?:-|_|–|\.\.)\s*(\d+)\s*([a-zçğıöşü]+)?$/i))) {
      return { chrom: U.chromName(m[1]), start: +m[2], end: +m[3], type: typeFromWord(m[4]) };
    }
    if ((m = t.match(/^(?:ekzon|exon|ex|e)\s*\.?\s*(\d+)\s*(?:(?:-|_|–|\.\.|to)\s*(?:ekzon|exon|ex|e)?\s*(\d+))?\s*([a-zçğıöşü]+)?$/i))) {
      return { exon: [+m[1], +(m[2] || m[1])], type: typeFromWord(m[3]) };
    }
    return null;
  }
  function parsePoint(text) {
    var t = text.trim().replace(/,/g, '');
    var m = t.match(/^(?:chr)?([0-9]{1,2}|X|Y)\s*[:_ ]\s*(\d+)$/i);
    return m ? { chrom: U.chromName(m[1]), pos: +m[2] } : null;
  }
  async function exonRange(gene, build, x, y) {
    var d = await U.getJSON(U.ENS[build] + '/lookup/symbol/homo_sapiens/' + encodeURIComponent(gene) + '?content-type=application/json', 'Ensembl gen araması');
    var chrom = U.chromName(d.seq_region_name);
    var txs = (await track(build, chrom, d.start - 1, d.end, 'ncbiRefSeqSelect')).map(U.parseGenePred).filter(function (t) { return t.gene === gene; });
    var tx = txs[0];
    if (!tx) throw new Error(gene + ' için RefSeq Select transkripti bulunamadı.');
    var lo = Math.min(x, y), hi = Math.max(x, y);
    var exs = tx.exons.filter(function (e) { return e.num >= lo && e.num <= hi; });
    if (exs.length !== hi - lo + 1) throw new Error(gene + ' ' + tx.name + ' transkriptinde ' + tx.exons.length + ' ekzon var; ekzon ' + lo + '–' + hi + ' bulunamadı.');
    return { chrom: chrom, start: Math.min.apply(null, exs.map(function (e) { return e.start0; })) + 1, end: Math.max.apply(null, exs.map(function (e) { return e.end0; })), tx: tx, lo: lo, hi: hi };
  }

  /* ---------------- Gen içeriği ---------------- */
  function compressNums(nums) {
    nums = nums.slice().sort(function (a, b) { return a - b; });
    var out = [], s = null, p = null;
    nums.forEach(function (n) { if (s == null) { s = p = n; } else if (n === p + 1) p = n; else { out.push(s === p ? '' + s : s + '–' + p); s = p = n; } });
    if (s != null) out.push(s === p ? '' + s : s + '–' + p);
    return out.join(', ');
  }
  function geneContent(txs, s0, e0) {
    var out = [];
    txs.forEach(function (t) {
      if (!(t.txStart < e0 && s0 < t.txEnd)) return;
      var inEx = t.exons.filter(function (e) { return e.start0 < e0 && s0 < e.end0; });
      var whole = t.txStart >= s0 && t.txEnd <= e0;
      out.push({ gene: t.gene, tx: t.name, strand: t.strand, n: t.exons.length, exons: inEx, whole: whole,
        text: whole ? 'tüm gen (' + t.exons.length + ' ekzon)' : inEx.length ? 'ekzon ' + compressNums(inEx.map(function (e) { return e.num; })) + ' / ' + t.exons.length : 'yalnızca intronik' });
    });
    return out;
  }

  /* ---------------- Ana akış ---------------- */
  async function runSV(ev) {
    if (ev) ev.preventDefault();
    U = window.PrimerUI;
    var type = $('svType').value, gene = $('svGene').value.trim().toUpperCase(), build = $('svBuild').value;
    var mode = $('svMode').value, unc = Math.max(0, parseInt($('svUnc').value, 10) || 0), zyg = $('svZyg').value, pcrPref = $('svPcr').value;
    var cond = { mv: parseFloat($('mv').value), dv: parseFloat($('dv').value), dntp: parseFloat($('dntp').value), dna: parseFloat($('dna').value) };
    saveSV();
    $('svGo').disabled = true;
    $('svResults').classList.add('hidden');
    $('progressCard').classList.remove('hidden');
    U.initSteps(SV_STEPS);
    var cur = 'parse';
    try {
      U.step('parse', 'run');
      var bps, iv = null, exInfo = null, chrom;
      if (type === 'TRA') {
        var A = parsePoint($('svRegion').value), B = parsePoint($('svRegionB').value);
        if (!A || !B) throw new Error('Translokasyon için iki kesim noktası girin (ör. chr9:130700000 ve chr22:23290000).');
        if (mode === 'exon') { mode = 'manual'; U.msg('info', 'Translokasyonda ekzon düzeyi pencere kullanılamaz; elle belirsizlik (±' + unc + ' bp) uygulandı.'); }
        var u0 = mode === 'exact' ? 0 : unc;
        bps = [{ chrom: A.chrom, a: A.pos - u0, b: A.pos + u0, label: 'A' }, { chrom: B.chrom, a: B.pos - u0, b: B.pos + u0, label: 'B' }];
      } else {
        var q = parseInterval($('svRegion').value);
        if (!q) throw new Error('Bölge anlaşılamadı. Örnekler: chrX:31950000-32100000, NC_000023.11:g.31950000_32100000del, ex45-50 (gen adı ile).');
        if (q.type && q.type !== type) { type = q.type; $('svType').value = type; U.msg('info', 'Varyant tipi gösterimden alındı: ' + TYPES[type] + '.'); }
        if (q.exon) {
          if (!gene) throw new Error('Ekzon aralığı için gen adını girin.');
          exInfo = await exonRange(gene, build, q.exon[0], q.exon[1]);
          iv = { chrom: exInfo.chrom, start: exInfo.start, end: exInfo.end };
          if (mode === 'exact') { mode = 'exon'; U.msg('info', 'Ekzon aralığı girildiği için kesim noktaları ekzon düzeyinde (komşu ekzonlar arasında) kabul edildi.'); }
        } else iv = q;
        if (iv.end < iv.start) { var tmp = iv.start; iv.start = iv.end; iv.end = tmp; }
        chrom = iv.chrom;
        var s0 = iv.start - 1, e0 = iv.end;
        var u1 = mode === 'manual' ? unc : 0;
        bps = [{ chrom: chrom, a: s0 - u1, b: s0 + u1, label: '1' }, { chrom: chrom, a: e0 - u1, b: e0 + u1, label: '2' }];
      }
      U.step('parse', 'ok', type === 'TRA' ? bps[0].chrom + ':' + comma(bps[0].a) + ' ↔ ' + bps[1].chrom + ':' + comma(bps[1].a) : iv.chrom + ':' + comma(iv.start) + '-' + comma(iv.end) + ' (' + bp(iv.end - iv.start + 1) + ')' + (exInfo ? ' · ' + gene + ' ekzon ' + exInfo.lo + '–' + exInfo.hi + ' (' + exInfo.tx.name + ')' : ''));

      cur = 'genes'; U.step('genes', 'run');
      var txs = [], genes = [];
      if (type !== 'TRA') {
        var gs = Math.max(0, iv.start - 1 - 500000), ge = iv.end + 500000;
        txs = (await track(build, chrom, gs, ge, 'ncbiRefSeqSelect')).map(U.parseGenePred);
        genes = geneContent(txs, iv.start - 1, iv.end);
        if (mode === 'exon') {
          var allEx = [];
          txs.forEach(function (t) { t.exons.forEach(function (e) { allEx.push(e); }); });
          var before = allEx.filter(function (e) { return e.end0 <= iv.start - 1; }).map(function (e) { return e.end0; });
          var after = allEx.filter(function (e) { return e.start0 >= iv.end; }).map(function (e) { return e.start0; });
          bps[0].a = before.length ? Math.max.apply(null, before) : gs;
          bps[1].b = after.length ? Math.min.apply(null, after) : ge;
          bps[0].b = iv.start - 1; bps[1].a = iv.end;
        }
      } else {
        for (var ti = 0; ti < 2; ti++) {
          var tt = (await track(build, bps[ti].chrom, bps[ti].a - 50000, bps[ti].b + 50000, 'ncbiRefSeqSelect')).map(U.parseGenePred);
          bps[ti].genes = tt.filter(function (t) { return t.txStart <= bps[ti].b && bps[ti].a <= t.txEnd; }).map(function (t) { return t.gene; });
        }
      }
      // segmental duplikasyon: kesim noktası pencereleri
      for (var bi = 0; bi < 2; bi++) {
        var w0 = bps[bi].a - 1000, w1 = Math.min(bps[bi].b + 1000, bps[bi].a + 2000000);
        bps[bi].sds = (await track(build, bps[bi].chrom, w0, w1, 'genomicSuperDups')).map(sdObj);
        bps[bi].maxSd = bps[bi].sds.reduce(function (m, x) { return Math.max(m, x.frac); }, 0);
      }
      U.step('genes', 'ok', (type === 'TRA' ? 'A: ' + (bps[0].genes.join(', ') || 'gen yok') + ' · B: ' + (bps[1].genes.join(', ') || 'gen yok') : genes.length + ' gen') +
        ' · kesim noktası pencereleri ' + bp(bps[0].b - bps[0].a) + ' / ' + bp(bps[1].b - bps[1].a) + (bps[0].sds.length || bps[1].sds.length ? ' · segmental duplikasyon var' : ''));

      // uygulanabilirlik
      var span = (bps[0].b - bps[0].a) + (bps[1].b - bps[1].a);
      var pcrMode;
      var dMaxStd = 450, dMaxLong = 900;
      var est = span + 2 * dMaxStd;
      if (pcrPref === 'std') pcrMode = 'std';
      else if (pcrPref === 'long') pcrMode = 'long';
      else pcrMode = est <= STD_MAX ? 'std' : 'long';
      var estLong = span + 2 * (pcrMode === 'long' ? dMaxLong : dMaxStd);
      if (estLong > LONG_MAX + 2 * dMaxLong) pcrMode = 'none';

      var design = null, tpls = [null, null];
      if (pcrMode !== 'none') {
        var prm = Object.assign(pcrMode === 'long' ? E.svParamsLong() : E.svParamsStd(), {
          dMin: mode === 'exact' ? 60 : 25, dMax: pcrMode === 'long' ? dMaxLong : dMaxStd, stdMax: STD_MAX, longMax: LONG_MAX, nAlt: 3, cond: cond, avoidRepeats: true
        });
        var ext = Math.round(prm.dMax * 1.6) + 80;
        for (var k = 0; k < 2; k++) {
          var sid = k === 0 ? 'bp1' : 'bp2';
          cur = sid; U.step(sid, 'run');
          var B0 = bps[k];
          if (B0.b - B0.a <= 30000) {
            var rg = await region(build, B0.chrom, B0.a - ext, B0.b + ext, true);
            B0.tplL = B0.tplR = rg;
          } else {
            B0.tplL = await region(build, B0.chrom, B0.a - ext, B0.a + 60, true);
            B0.tplR = await region(build, B0.chrom, B0.b - 60, B0.b + ext, true);
          }
          tpls[k] = B0;
          U.step(sid, 'ok', B0.chrom + ':' + comma(B0.a - ext) + '-' + comma(B0.b + ext) + ' · ' + (B0.tplL.snps.length + (B0.tplR !== B0.tplL ? B0.tplR.snps.length : 0)) + ' SNP, ' + (B0.tplL.repeats.length + (B0.tplR !== B0.tplL ? B0.tplR.repeats.length : 0)) + ' tekrar');
        }
        cur = 'design'; U.step('design', 'run');
        await U.sleep(20);
        var t0 = performance.now();
        design = E.designSV({ type: type, bps: bps }, prm);
        design.mode = pcrMode; design.prm = prm;
        U.step('design', design.sets.length ? 'ok' : 'err', design.sets.length + ' alternatif set (' + (pcrMode === 'long' ? 'long-range' : 'standart') + ' PCR primerleri), ' + Math.round(performance.now() - t0) + ' ms');
        if (!design.sets.length) U.msg('warn', 'Kesim noktası çevresinde uygun primer seti bulunamadı (tekrar bölgesi, SNP veya dimer kısıtları). Doz analizi ve alternatif yöntemler aşağıda önerildi.');
      } else {
        U.step('bp1', 'ok', 'atlandı: kesim noktası belirsizliği PCR için çok büyük');
        U.step('bp2', 'ok', 'atlandı');
        U.step('design', 'ok', 'junction PCR uygulanamaz (olası ürün > ' + bp(LONG_MAX) + ')');
      }

      // doz ve daraltma
      cur = 'dosage'; U.step('dosage', 'run');
      var dosage = [], walking = [];
      if (type === 'DEL' || type === 'DUP') {
        dosage = await designDosage(build, chrom, bps, txs, cond);
        if (pcrMode === 'none') walking = await designWalking(build, bps, cond);
      }
      U.step('dosage', 'ok', type === 'DEL' || type === 'DUP' ? dosage.filter(function (d) { return d.pair; }).length + ' doz hedefi' + (walking.length ? ', ' + walking.reduce(function (n, w) { return n + w.points.length; }, 0) + ' daraltma noktası' : '') : 'kopya sayısı değişmez; uygulanmadı');

      cur = 'report'; U.step('report', 'run');
      S = { type: type, gene: gene, build: build, mode: mode, unc: unc, zyg: zyg, iv: iv, exInfo: exInfo, bps: bps, txs: txs, genes: genes, design: design, pcrMode: pcrMode,
        dosage: dosage, walking: walking, cond: cond, sel: 0, size: iv ? iv.end - iv.start + 1 : null };
      S.base = (gene || (type === 'TRA' ? 't' + bps[0].chrom.replace('chr', '') + '_' + bps[1].chrom.replace('chr', '') : iv.chrom)) + '_' + type;
      S.recs = recommend(S);
      renderSV();
      U.step('report', 'ok');
      $('svResults').classList.remove('hidden');
    } catch (err) {
      U.step(cur, 'err');
      U.msg('err', esc(err.message || String(err)));
      if (window.console) console.warn(err);
    } finally {
      $('svGo').disabled = false;
    }
  }

  var QP = { sizeMin: 70, sizeMax: 150, sizeOpt: 100, lenMin: 18, lenOpt: 20, lenMax: 24, tmMin: 58, tmOpt: 60, tmMax: 62, tmDiffMax: 1.5, gcMin: 35, gcMax: 65, minDist: 1, numReturn: 1 };
  function qpcrAt(tpl, center, cond) {
    var input = { template: tpl.seq, tplStart0: tpl.start0, varStart0: center, varEnd0: center, snps: tpl.snps, repeats: tpl.repeats };
    var r = E.design(input, Object.assign({}, QP, { cond: cond }));
    if (!r.pairs.length) r = E.design(input, Object.assign({}, QP, { cond: cond, snpPolicy: 'relaxed', avoidRepeats: false, tmMin: 57, tmMax: 63, tmDiffMax: 2.5 }));
    return r.pairs[0] || null;
  }
  async function designDosage(build, chrom, bps, txs, cond) {
    var s0 = bps[0].b, e0 = bps[1].a; // kesin etkilenen bölge
    if (e0 - s0 < 60) return [];
    var targets = [];
    var exs = [];
    txs.forEach(function (t) { t.exons.forEach(function (e) { if (e.start0 >= s0 && e.end0 <= e0) exs.push({ gene: t.gene, num: e.num, start0: e.start0, end0: e.end0 }); }); });
    exs.sort(function (a, b) { return a.start0 - b.start0; });
    if (exs.length) {
      [exs[0], exs[Math.floor(exs.length / 2)], exs[exs.length - 1]].forEach(function (e) {
        if (targets.some(function (t) { return Math.abs(t.center - (e.start0 + e.end0) / 2) < 300; })) return;
        targets.push({ label: e.gene + ' ekzon ' + e.num, center: Math.round((e.start0 + e.end0) / 2) });
      });
    } else {
      var n = e0 - s0 < 1000 ? 1 : 3;
      for (var i = 1; i <= n; i++) { var c = Math.round(s0 + (e0 - s0) * i / (n + 1)); targets.push({ label: chrom + ':' + comma(c + 1), center: c }); }
    }
    for (var k = 0; k < targets.length; k++) {
      var t = targets[k];
      var tpl = await region(build, chrom, Math.max(s0, t.center - 400), Math.min(e0, t.center + 400), true);
      t.pair = qpcrAt(tpl, t.center, cond);
      t.chrom = chrom;
      if (t.pair) t.sd = tpl.sds.filter(function (d) { return d.frac >= 0.9 && d.start0 < t.pair.ampEnd0 && t.pair.ampStart0 < d.end0; })[0] || null;
    }
    return targets;
  }
  async function designWalking(build, bps, cond) {
    var out = [];
    for (var i = 0; i < 2; i++) {
      var B = bps[i], span = B.b - B.a;
      if (span <= LONG_MAX * 0.8) continue;
      if (span > WALK_MAX) { out.push({ bp: i + 1, span: span, tooLarge: true, points: [] }); continue; }
      var n = Math.min(6, Math.max(2, Math.ceil(span / 10000)));
      var tpl = await region(build, B.chrom, B.a, B.b, false);
      var pts = [];
      for (var k = 1; k <= n; k++) {
        var c = Math.round(B.a + span * k / (n + 1));
        var inSd = B.sds.filter(function (d) { return d.frac >= 0.9 && d.start0 < c + 300 && c - 300 < d.end0; })[0];
        if (inSd) { pts.push({ center: c, pair: null, chrom: B.chrom, sd: inSd }); continue; }
        var sub = sliceTpl(tpl, c - 400, c + 400);
        var pr = qpcrAt(sub, c, cond);
        // tasarlanamazsa biraz kaydırarak dene
        if (!pr) { sub = sliceTpl(tpl, c + 300, c + 1100); pr = qpcrAt(sub, c + 700, cond); }
        pts.push({ center: c, pair: pr, chrom: B.chrom });
      }
      out.push({ bp: i + 1, span: span, points: pts });
    }
    return out;
  }
  function sliceTpl(t, s, e) {
    s = Math.max(t.start0, s); e = Math.min(t.start0 + t.seq.length, e);
    var f = function (x) { return x.end0 > s && x.start0 < e; };
    return { seq: t.seq.substring(s - t.start0, e - t.start0), start0: s, snps: t.snps.filter(f), repeats: t.repeats.filter(f), sds: [] };
  }

  /* ---------------- Test önerisi ---------------- */
  function mainJunction(set) { return set ? set.assays.filter(function (a) { return a.role === 'junction'; }) : []; }
  function recommend(S) {
    var R = [], t = S.type, set = S.design && S.design.sets[0], J = mainJunction(set);
    var jOK = J.filter(function (a) { return a.pcr === 'std' || a.pcr === 'long'; });
    var cls = jOK.length ? (jOK.some(function (a) { return a.pcr === 'long'; }) ? 'long' : 'std') : null;
    var sdBoth = S.bps[0].maxSd >= 0.9 && S.bps[1].maxSd >= 0.9;
    var sdAny = S.bps[0].maxSd > 0 || S.bps[1].maxSd > 0;
    var exact = S.mode === 'exact';
    var hasDos = S.dosage.some(function (d) { return d.pair; });
    var xl = S.iv && S.iv.chrom === 'chrX';
    function add(level, title, text) { R.push({ level: level, title: title, text: text }); }
    var jRange = J.length ? J.map(function (a) { return a.id + ': ' + rangeTxt(a.mut); }).join(', ') : '';

    if (sdAny) {
      add('warn', 'Kesim noktası segmental duplikasyon içinde', 'Kesim noktası pencerelerinde segmental duplikasyon var (en yüksek benzerlik %' + (Math.max(S.bps[0].maxSd, S.bps[1].maxSd) * 100).toFixed(1) + '). ' +
        (sdBoth ? 'Her iki uçta da yüksek benzerlikli tekrar: olası NAHR (non-allelik homolog rekombinasyon) aracılı yeniden düzenlenme. Kesim noktası tekrar içinde olduğundan standart junction PCR genellikle özgül değildir; doz analizi (MLPA/qPCR/CMA) birincil yöntemdir. Kesim noktası gerekiyorsa paraloga özgü dizi farklılıklarına (PSV) dayalı long-range PCR veya uzun okuma dizileme kullanılır.' : 'Bu bölgeye yerleştirilen primerler ve qPCR noktaları paralog bölgeye de bağlanabilir; In-Silico PCR ve BLAT kontrolü zorunludur.'));
    }

    if (t === 'DEL' || t === 'DUP') {
      if (S.size != null && S.size < 50) add('primary', 'Küçük indel aralığı', 'Varyant ' + S.size + ' bp: SNV / küçük indel bölümündeki Sanger tasarımı daha uygundur.');
    }

    if (t === 'DEL') {
      if (cls && !sdBoth) {
        var j = J[0];
        var hasW1 = set.assays.some(function (a) { return a.id === 'W1'; });
        add('primary', (cls === 'std' ? 'Kesim noktası (junction) PCR + Sanger' : 'Long-range kesim noktası PCR\'ı'),
          'L1+R2 yalnızca delesyonlu allelde ürün verir (' + rangeTxt(j.mut) + '). ' +
          (hasW1 ? 'L1+R1 normal allel kontrolüdür; R1 delesyonlu bölgede olduğundan delesyonlu allelde bağlanamaz. ' + (cls === 'std' ? 'Üç primerli tek reaksiyon (L1 + R1 + R2) ile iki allel aynı tüpte ayrı boyda görülür. ' : '')
            : 'Kesim noktası belirsizliği silinen bölgenin tamamını kapsadığından delesyon içinde normal allel kontrolü tasarlanamadı; normal allel L1+R2 gap ürünüyle veya bağımsız bir pozitif kontrol amplikonuyla izlenmelidir. ') +
          (exact ? 'Junction ürününün Sanger ile dizilenmesi kesim noktasını baz düzeyinde doğrular.' : 'Kesim noktası tam bilinmediği için ürün boyu bir aralıkta beklenir; ürün dizilenerek (Sanger, primer walking veya amplikon NGS) kesim noktası belirlenir. Sonrasında aile taraması için kısa bir junction PCR tasarlanabilir.'));
        if (j.refPcr === 'std' || j.refPcr === 'long') add('info', 'Gap-PCR olarak da yorumlanabilir', 'L1+R2 normal allelde de ' + bp(j.ref) + ' ürün verebilir. Heterozigotta iki bant beklenir; kısa (delesyonlu) ürün tercihli çoğalabilir, bu yüzden normal allel kontrolü (L1+R1) ayrıca değerlendirilmelidir.');
        add('second', 'Bağımsız doz doğrulaması', hasDos ? 'qPCR/ddPCR (aşağıdaki doz primerleri; beklenen oran ≈ 0.5) veya gen için ticari kit varsa MLPA.' : 'qPCR/ddPCR veya MLPA. Kesim noktası belirsizliği nedeniyle kesin silinen bölge kalmadığından doz primeri tasarlanmadı; belirsizlik daraltıldığında yeniden çalıştırın.');
      } else {
        add('primary', 'Doz analizi: qPCR / ddPCR veya MLPA', (hasDos ? 'Etkilenen bölgede ' + S.dosage.filter(function (d) { return d.pair; }).length + ' doz hedefi için primer tasarlandı. ' : '') + 'Heterozigot delesyonda oran ≈ 0.5, homozigot/hemizigotta 0 beklenir. Gen için ticari MLPA kiti varsa ekzon düzeyinde doğrulama sağlar.');
        if (!cls && !sdBoth) add('info', 'Junction PCR şu an uygulanamaz', 'Kesim noktası belirsizliği nedeniyle olası junction ürünü long-range sınırını (' + bp(LONG_MAX) + ') aşıyor.');
      }
    }
    if (t === 'DUP') {
      add('primary', 'Doz analizi: qPCR / ddPCR veya MLPA', 'Kopya sayısı artışı (heterozigot duplikasyonda oran ≈ 1.5) ' + (hasDos ? 'aşağıdaki doz primerleriyle ' : '') + 'gösterilir. Gen için ticari MLPA kiti varsa ekzon düzeyinde doğrulama sağlar.');
      if (cls && !sdBoth) add(exact ? 'primary' : 'second', 'Tandem duplikasyon birleşme PCR\'ı', 'Referansta dışa bakan L2+R1 primerleri yalnızca baş-kuyruk (tandem, aynı yönde) duplikasyonda ürün verir (' + rangeTxt(J[0].mut) + '). Pozitif sonuç duplikasyonun tandem olduğunu ve kesim noktasını gösterir. Negatif sonuç duplikasyonu dışlamaz: ters yönlü veya başka bir lokusa eklenmiş olabilir.');
      var partial = S.genes.filter(function (g) { return !g.whole && g.exons.length; });
      if (partial.length) add('info', 'Gen içi (kısmi) duplikasyon', partial.map(function (g) { return g.gene + ' ' + g.text; }).join('; ') + '. Tandem kısmi duplikasyon okuma çerçevesini bozabilir; etkisinin değerlendirilmesi için RNA/cDNA analizi (RT-PCR) önerilir.');
      add('alt', 'Konum ve yönelim', 'Duplikasyonun tandem olup olmadığı ve yönü belirsiz kalırsa FISH, optik genom haritalama (OGM) veya uzun okuma dizileme.');
    }
    if (t === 'INV') {
      add('warn', 'Kopya sayısı değişmez', 'İnversiyon dengeli bir yeniden düzenlenmedir: MLPA, qPCR ve CMA ile saptanamaz.');
      if (cls) add('primary', 'İki birleşme noktası PCR\'ı + Sanger', 'Sol birleşme L1+L2, sağ birleşme R1+R2 ile amplifiye edilir (' + jRange + '). İkisinin de pozitif olması inversiyonu doğrular; normal allel kontrolleri (L1+R1, L2+R2) PCR başarısını gösterir. Ürünler Sanger ile dizilenir.');
      else add('primary', 'Uzun okuma dizileme veya OGM', 'Kesim noktası belirsizliği PCR için çok büyük. Uzun okuma dizileme (PacBio/ONT) veya OGM; büyük inversiyonlarda (≥ ~5 Mb) G-bant karyotip, daha küçüklerde FISH.');
      if (sdAny) add('alt', 'Ters yönlü tekrar aracılı inversiyon', 'Kesim noktaları tekrar içindeyse inverse PCR veya tekrarı aşan long-range PCR yaklaşımları gerekir.');
    }
    if (t === 'TRA') {
      add('primary', 'Sitogenetik doğrulama', 'Dengeli translokasyon için G-bant karyotip; translokasyona uğrayan segment küçükse FISH.');
      add('warn', 'Kopya sayısı değişmez', 'Dengeli translokasyon CMA, MLPA veya qPCR ile saptanamaz.');
      if (cls) add('primary', 'Türev kromozom birleşme PCR\'ları + Sanger', 'A-sol + B-sağ (L1+R2) ve B-sol + A-sağ (L2+R1) iki türev kromozomun birleşmeleridir. Yönelim bilinmiyorsa ters yönelim kombinasyonları (L1+L2, R1+R2) da denenir; taşıyıcıda iki kombinasyonun pozitif olması beklenir. Ürünler Sanger ile dizilenir.');
      else add('alt', 'Kesim noktası haritalama', 'PCR için belirsizlik çok büyük: OGM, uzun okuma dizileme veya FISH ile haritalama.');
      add('seg', 'Aile ve üreme danışmanlığı', 'Dengeli taşıyıcılarda dengesiz gamet riski vardır. Taşıyıcı ebeveynlerin çocuklarında dengesiz form CMA ile değerlendirilir; genetik danışmanlık önerilir.');
    }

    if ((t === 'DEL' || t === 'DUP') && S.size != null) {
      if (S.size >= 50000) add('second', 'CMA ile boyut ve gen içeriği', 'Kromozomal mikroarray (CMA) varyantın boyutunu ve gen içeriğini bağımsız olarak doğrular.');
      if (S.size >= 5000000) add('alt', 'Karyotip / FISH', '≥ ~5 Mb segmentler karyotipte görülebilir; türev kromozom veya insersiyonel yeniden düzenlenmeyi dışlamak için FISH.');
    }
    if (S.walking.length) {
      S.walking.forEach(function (w) {
        if (w.tooLarge) add('alt', 'Kesim noktası ' + w.bp + ' haritalama', 'Belirsizlik penceresi ' + bp(w.span) + ': qPCR ile daraltmak için çok büyük. CMA, OGM veya uzun okuma dizileme ile haritalayın.');
        else if (!w.points.some(function (p) { return p.pair; })) add('alt', 'Kesim noktası ' + w.bp + ' daraltma yapılamaz', 'Belirsizlik penceresi (' + bp(w.span) + ') yüksek benzerlikli segmental duplikasyon veya tekrar içinde: qPCR paralogları ayırt edemez. Kesim noktası için paraloga özgü dizi farklılığı (PSV) temelli PCR, uzun okuma dizileme veya OGM gerekir.');
        else add('second', 'Kesim noktası ' + w.bp + ' daraltma (qPCR walking)', bp(w.span) + ' belirsizlik penceresine ' + w.points.length + ' qPCR noktası tasarlandı. ' + (S.type === 'DEL' ? 'Oranı ≈ 0.5 olan' : 'Oranı ≈ 1.5 olan') + ' noktalar ile normal noktalar arasındaki aralık kesim noktasını sınırlar; aralık ' + bp(LONG_MAX) + ' altına inince long-range junction PCR tasarlanır.');
      });
    }
    if (S.zyg === 'hom' && t === 'DEL') add('info', 'Homozigot / hemizigot delesyon', 'Etkilenen bölgede (doz primerleriyle) hiç ürün alınmaz; bağımsız bir pozitif kontrol amplikonu ile basit PCR yeterli olabilir. Junction PCR\'da yalnızca mutant bant görülür.');
    if (S.design && S.design.sets[0]) {
      var relax = ['L1', 'R1', 'L2', 'R2'].filter(function (k) { var x = S.design.sets[0].primers[k]; return x && x.tier > 0; });
      if (relax.length) add('warn', 'Gevşetilmiş kriterle seçilen primerler', relax.join(', ') + ' sıkı kriterlerle bulunamadı (tekrar, SNP veya Tm). Uyarıları kontrol edin.');
    }
    var segTxt = t === 'TRA' ? null : (cls && !sdBoth) ? 'Aile bireylerinde junction PCR en pratik ve ucuz yöntemdir; normal allel kontrolü ile birlikte çalışın.' : 'Aile bireylerinde doz analizi (qPCR/ddPCR veya MLPA) kullanın.';
    if (segTxt) add('seg', 'Segregasyon', segTxt + (xl ? ' X kromozomunda: kadın taşıyıcılarda heterozigot durum (oran ≈ 0.5 / 1.5) gösterilmelidir; erkeklerde hemizigot.' : ''));
    add('info', 'Özgüllük kontrolü', 'Junction ürünleri referans genomda bulunmadığından UCSC In-Silico PCR\'da junction çiftleri ürün vermemeli, normal allel kontrolleri tek ürün vermelidir. Primer başına BLAT ile çoklu eşleşme kontrol edilmelidir.');
    return R;
  }

  /* ---------------- Görselleştirme ---------------- */
  function primerName(setIdx, k) { return S.base + '_S' + setIdx + '_' + k; }

  function schema(set) {
    var t = S.type, o = [], W = 860;
    var col = { A: 'var(--seg-a)', B: 'var(--var)', C: 'var(--seg-c)', A1: 'var(--seg-c)', A2: 'var(--seg-c2)', B1: 'var(--rev)', B2: 'var(--seg-b2)' };
    var y = 18;
    function rowLabel(txt) { o.push('<text x="10" y="' + y + '" class="rl">' + esc(txt) + '</text>'); y += 10; }
    function seg(x1, x2, c, txt, rev) {
      o.push('<rect x="' + x1 + '" y="' + y + '" width="' + (x2 - x1) + '" height="14" rx="2" fill="' + c + '" opacity=".85"/>');
      if (rev) for (var x = x1 + 18; x < x2 - 8; x += 26) o.push('<path d="M' + (x + 5) + ' ' + (y + 3) + ' L' + x + ' ' + (y + 7) + ' L' + (x + 5) + ' ' + (y + 11) + '" fill="none" stroke="#fff" stroke-width="1.5"/>');
      if (txt) o.push('<text x="' + ((x1 + x2) / 2) + '" y="' + (y + 27) + '" text-anchor="middle">' + esc(txt) + '</text>');
    }
    function pr(x, dir, name) {
      var has = set && set.primers[name];
      var c = name[0] === 'L' ? 'var(--fwd)' : 'var(--rev)';
      var yy = y - 9;
      o.push('<path d="M' + (x - 11 * dir) + ' ' + (yy - 3) + ' L' + (x - 3 * dir) + ' ' + (yy - 3) + ' L' + (x - 3 * dir) + ' ' + (yy - 6) + ' L' + (x + 4 * dir) + ' ' + yy + ' L' + (x - 3 * dir) + ' ' + (yy + 6) + ' L' + (x - 3 * dir) + ' ' + (yy + 3) + ' L' + (x - 11 * dir) + ' ' + (yy + 3) + ' Z" fill="' + c + '"' + (has ? '' : ' opacity=".3"') + '/>');
      o.push('<text x="' + x + '" y="' + (yy - 9) + '" text-anchor="middle" class="pn" style="fill:' + c + '">' + name + '</text>');
    }
    function brk(x1, x2, label) {
      var yy = y + 34;
      o.push('<path d="M' + x1 + ' ' + (yy - 5) + ' L' + x1 + ' ' + yy + ' L' + x2 + ' ' + yy + ' L' + x2 + ' ' + (yy - 5) + '" fill="none" stroke="var(--ink-2)" stroke-width="1.2"/>');
      o.push('<text x="' + ((x1 + x2) / 2) + '" y="' + (yy + 13) + '" text-anchor="middle" class="bl">' + esc(label) + '</text>');
    }
    function nextRow(h) { y += h || 82; }
    var A = set ? set.assays : [];
    function lab(id) { var a = A.filter(function (z) { return z.id === id; })[0]; if (!a) return id; return id + ': ' + (a.mut ? rangeTxt(a.mut) : bp(a.ref)); }
    var sizeTxt = S.size ? bp(S.size) : '';
    y = 30;
    if (t === 'DEL' || t === 'INV' || t === 'DUP') {
      rowLabel('Referans allel');
      seg(40, 280, col.A, 'sol komşu'); seg(280, 580, col.B, (t === 'DEL' ? 'silinen' : t === 'DUP' ? 'duplike' : 'ters dönen') + ' segment ' + sizeTxt); seg(580, 820, col.C, 'sağ komşu');
      pr(250, 1, 'L1'); pr(310, -1, 'R1'); pr(550, 1, 'L2'); pr(610, -1, 'R2');
      brk(250, 310, lab('W1')); brk(550, 610, lab('W2'));
      nextRow(96);
      if (t === 'DEL') {
        rowLabel('Delesyonlu allel');
        seg(40, 280, col.A, 'sol komşu'); seg(280, 520, col.C, 'sağ komşu');
        pr(250, 1, 'L1'); pr(310, -1, 'R2'); brk(250, 310, lab('J'));
      } else if (t === 'DUP') {
        rowLabel('Tandem duplikasyonlu allel');
        seg(40, 180, col.A, 'sol'); seg(180, 450, col.B, 'kopya 1'); seg(450, 720, col.B, 'kopya 2'); seg(720, 840, col.C, 'sağ');
        pr(420, 1, 'L2'); pr(480, -1, 'R1'); brk(420, 480, lab('J'));
      } else {
        rowLabel('İnversiyonlu allel');
        seg(40, 280, col.A, 'sol komşu'); seg(280, 580, col.B, 'ters segment', true); seg(580, 820, col.C, 'sağ komşu');
        pr(250, 1, 'L1'); pr(310, -1, 'L2'); pr(550, 1, 'R1'); pr(610, -1, 'R2');
        brk(250, 310, lab('J1')); brk(550, 610, lab('J2'));
      }
      nextRow(80);
    } else {
      rowLabel('Normal kromozom A (' + S.bps[0].chrom + ')');
      seg(40, 330, col.A1, 'A-sol'); seg(330, 620, col.A2, 'A-sağ'); pr(300, 1, 'L1'); pr(360, -1, 'R1'); brk(300, 360, lab('W1'));
      nextRow(90);
      rowLabel('Normal kromozom B (' + S.bps[1].chrom + ')');
      seg(40, 330, col.B1, 'B-sol'); seg(330, 620, col.B2, 'B-sağ'); pr(300, 1, 'L2'); pr(360, -1, 'R2'); brk(300, 360, lab('W2'));
      nextRow(90);
      rowLabel('Türev 1 (A-sol + B-sağ)');
      seg(40, 330, col.A1, 'A-sol'); seg(330, 620, col.B2, 'B-sağ'); pr(300, 1, 'L1'); pr(360, -1, 'R2'); brk(300, 360, lab('JA'));
      nextRow(90);
      rowLabel('Türev 2 (B-sol + A-sağ)');
      seg(40, 330, col.B1, 'B-sol'); seg(330, 620, col.A2, 'A-sağ'); pr(300, 1, 'L2'); pr(360, -1, 'R1'); brk(300, 360, lab('JB'));
      nextRow(80);
    }
    return '<div class="svgbox"><svg class="schema" viewBox="0 0 ' + W + ' ' + (y - 10) + '" role="img" aria-label="Yeniden düzenlenme şeması">' + o.join('') + '</svg></div>' +
      '<p class="hint">Şema ölçekli değildir. Ok yönü primerin 3\' ucunu gösterir; köşeli çizgiler beklenen ürünlerdir.</p>';
  }

  function interp(a) {
    var t = S.type;
    if (a.role === 'junction') {
      if (t === 'DEL') return 'Yalnızca delesyonlu allelde. Normal: yok' + (a.refPcr === 'std' || a.refPcr === 'long' ? ' (ya da ' + bp(a.ref) + ' normal ürün)' : '') + ' · Taşıyıcı: var';
      if (t === 'TRA') return 'Yalnızca taşıyıcıda; ' + (a.orient === 'std' ? 'standart yönelim' : 'ters yönelim') + ' kombinasyonu';
      return 'Yalnızca taşıyıcıda. Normal: yok';
    }
    if (t === 'DUP') return 'Tüm örneklerde (PCR pozitif kontrolü)';
    if (t === 'TRA') return 'Normal kromozomdan; heterozigot taşıyıcıda da var';
    return 'Normal ve heterozigotta var · homozigotta yok';
  }
  function pcrLabel(c) { return c === 'std' ? '<span class="badge b-ok">Standart PCR</span>' : c === 'long' ? '<span class="badge b-warn">Long-range PCR</span>' : '<span class="badge b-err">Uygulanamaz</span>'; }

  function renderSV() {
    // özet
    var rows = [['Tip', TYPES[S.type]], ['Genom', S.build], ['Kesim noktası çözünürlüğü', MODES[S.mode] + (S.mode === 'manual' ? ' (±' + comma(S.unc) + ' bp)' : '')]];
    if (S.type === 'TRA') {
      rows.push(['Kesim noktası A', S.bps[0].chrom + ':' + comma(S.bps[0].a) + (S.bps[0].b !== S.bps[0].a ? '–' + comma(S.bps[0].b) : '') + (S.bps[0].genes.length ? ' · ' + S.bps[0].genes.join(', ') : '')]);
      rows.push(['Kesim noktası B', S.bps[1].chrom + ':' + comma(S.bps[1].a) + (S.bps[1].b !== S.bps[1].a ? '–' + comma(S.bps[1].b) : '') + (S.bps[1].genes.length ? ' · ' + S.bps[1].genes.join(', ') : '')]);
    } else {
      rows.push(['Bölge', S.iv.chrom + ':' + comma(S.iv.start) + '-' + comma(S.iv.end)]);
      rows.push(['Boyut', bp(S.size)]);
      if (S.exInfo) rows.push(['Ekzon aralığı', S.gene + ' ekzon ' + S.exInfo.lo + '–' + S.exInfo.hi + ' (' + S.exInfo.tx.name + ')']);
    }
    var bpRows = S.bps.map(function (b, i) {
      var w = b.b - b.a;
      return ['Kesim noktası ' + (S.type === 'TRA' ? b.label : i + 1) + ' penceresi', w === 0 ? 'kesin' : b.chrom + ':' + comma(b.a + 1) + '-' + comma(b.b) + ' (' + bp(w) + ')' + (b.sds.length ? ' · segmental dup. %' + (b.maxSd * 100).toFixed(1) : '')];
    });
    rows = rows.concat(bpRows);
    $('svKv').innerHTML = rows.map(function (r) { return '<dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) + '</dd>'; }).join('');
    var g = S.genes.slice(0, 40);
    $('svGenes').innerHTML = S.type === 'TRA' ? '<p class="muted">Translokasyonda kesim noktalarındaki genler özet tablosunda listelenmiştir.</p>' :
      (g.length ? '<table><thead><tr><th>Gen</th><th>Transkript</th><th>Etkilenen kısım</th></tr></thead><tbody>' + g.map(function (x) { return '<tr><td class="mono">' + esc(x.gene) + '</td><td class="mono">' + esc(x.tx) + '</td><td>' + esc(x.text) + '</td></tr>'; }).join('') + '</tbody></table>' +
        (S.genes.length > 40 ? '<p class="hint">+' + (S.genes.length - 40) + ' gen daha</p>' : '') : '<p class="muted">Bölgede RefSeq Select geni yok (intergenik).</p>');

    // öneriler
    var lv = { primary: ['b-ok', 'Önerilen'], second: ['b-info', 'Tamamlayıcı'], alt: ['b-info', 'Alternatif'], warn: ['b-warn', 'Dikkat'], info: ['b-info', 'Not'], seg: ['b-ok', 'Aile'] };
    $('svRecs').innerHTML = S.recs.map(function (r) {
      var l = lv[r.level] || lv.info;
      return '<li class="rec rec-' + r.level + '"><div><span class="badge ' + l[0] + '">' + l[1] + '</span> <b>' + esc(r.title) + '</b></div><div class="rt">' + esc(r.text) + '</div></li>';
    }).join('');

    var sets = S.design ? S.design.sets : [];
    $('svDesignCard').classList.toggle('hidden', !sets.length);
    $('svSchemaFallback').innerHTML = sets.length ? '' : schema(null);
    if (sets.length) {
      $('svTabs').innerHTML = sets.map(function (s, i) { return '<button class="small' + (i === S.sel ? ' on' : '') + '" data-i="' + i + '">Set ' + s.idx + '</button>'; }).join('');
      Array.prototype.forEach.call($('svTabs').querySelectorAll('button'), function (b) { b.addEventListener('click', function () { S.sel = +b.getAttribute('data-i'); renderSV(); }); });
      renderSet(sets[S.sel]);
    }
    renderDosage();
    renderImgs();
  }

  function renderSet(set) {
    var keys = ['L1', 'R1', 'L2', 'R2'].filter(function (k) { return set.primers[k]; });
    var html = '<div class="row"><h2 style="margin:0">Set ' + set.idx + '</h2><span><span class="badge b-info">Tm aralığı ' + fmt(set.tmSpread) + ' °C</span> <span class="badge b-info">ceza ' + fmt(set.penalty, 2) + '</span></span></div>';
    html += schema(set);
    html += '<h3 style="margin-top:14px">Testler ve beklenen ürünler</h3><div class="tablewrap"><table><thead><tr><th>Test</th><th>Primerler</th><th>Mutant allel</th><th>Normal allel</th><th>PCR</th><th>Yorum</th></tr></thead><tbody>' +
      set.assays.map(function (a) {
        return '<tr><td><b>' + a.id + '</b> ' + esc(a.title) + '</td><td class="mono">' + a.primers.join(' + ') + '</td><td class="num">' + (a.mut ? rangeTxt(a.mut) : (a.both ? bp(a.ref) : 'yok')) + '</td><td class="num">' + (a.ref != null ? bp(a.ref) : 'yok') + '</td><td>' + pcrLabel(a.pcr) + '</td><td class="small">' + esc(interp(a)) + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    if (S.type === 'DEL' && set.assays.some(function (a) { return a.id === 'W1'; }) && set.assays.filter(function (a) { return a.pcr === 'std'; }).length >= 2) {
      var j = set.assays.filter(function (a) { return a.id === 'J'; })[0], w = set.assays.filter(function (a) { return a.id === 'W1'; })[0];
      if (j && w && j.pcr === 'std' && w.pcr === 'std') html += '<div class="alert info">Üç primerli tek tüp: L1 + R1 + R2. Normal allel ' + bp(w.ref) + ', delesyonlu allel ' + rangeTxt(j.mut) + (Math.abs(w.ref - j.mut.max) < 80 ? '. Bantlar birbirine yakın; jelde ayrım için %2–3 agaroz kullanın.' : '.') + '</div>';
    }
    // primer tablosu
    html += '<h3 style="margin-top:14px">Primerler</h3><div class="tablewrap"><table><thead><tr><th>Ad</th><th>Dizi (5\'→3\')</th><th class="num">Uz.</th><th class="num">Tm</th><th class="num">GC%</th><th class="num">Hairpin</th><th class="num">Self-dimer</th><th>Konum</th><th>Not</th></tr></thead><tbody>' +
      keys.map(function (k) {
        var p = set.primers[k], b = S.bps[k[1] === '1' ? 0 : 1];
        var dist = p.side === 'F' ? b.a - p.end0 : p.start0 - b.b;
        var notes = [];
        if (p.snps && p.snps.length) notes.push('SNP: ' + p.snps.map(function (x) { return x.name; }).join(', '));
        if (p.repeats && p.repeats.length) notes.push('tekrar: ' + p.repeats.join(', '));
        if (p.sds && p.sds.length) notes.push('segmental dup. (%' + (Math.max.apply(null, p.sds.map(function (x) { return x.frac; })) * 100).toFixed(1) + ')');
        if (p.tier) notes.push('gevşetilmiş');
        return '<tr><td class="mono" style="color:var(' + (k[0] === 'L' ? '--fwd' : '--rev') + ')">' + esc(primerName(set.idx, k)) + '</td><td class="seq">' + p.seq + ' <button class="small copy noprint" data-c="' + p.seq + '">kopyala</button></td><td class="num">' + p.len + '</td><td class="num">' + fmt(p.tm) + '</td><td class="num">' + fmt(p.gc, 0) + '</td><td class="num">' + fmt(p.hairpin) + '</td><td class="num">' + fmt(p.selfDimer) + '</td><td class="mono small">' + b.chrom + ':' + comma(p.start0 + 1) + '-' + comma(p.end0) + ' (' + (p.side === 'F' ? '+' : '−') + ')<br>kesim noktasına ' + comma(dist) + ' bp</td><td class="small">' + (notes.length ? '<span class="i-warn">⚠</span> ' + esc(notes.join(' · ')) : '<span class="i-ok">✓</span>') + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    html += '<p class="hint">En kötü çapraz dimer: ' + (set.worstDimer.pair ? set.worstDimer.pair.join(' × ') + ' ΔG ' + fmt(set.worstDimer.dg) + ' kcal/mol (3\' uç ' + fmt(set.worstDimer.dg3) + ')' : 'anlamlı dimer yok') + '. Tüm primerler aynı tüpte kullanılabilecek şekilde birlikte kontrol edildi.</p>';
    // bağlantılar
    html += '<div class="links noprint">' + set.assays.filter(function (a) { return a.role === 'wt'; }).map(function (a) {
      var f = set.primers[a.primers[0]], r = set.primers[a.primers[1]], chrom = S.bps[a.primers[0][1] === '1' ? 0 : 1].chrom;
      return '<a target="_blank" rel="noopener" href="' + U.UCSC + '/hgPcr?db=' + S.build + '&wp_target=genome&wp_f=' + f.seq + '&wp_r=' + r.seq + '&wp_size=' + Math.max(4000, a.ref + 1000) + '&wp_perfect=15&wp_good=15&boolshad.wp_flipReverse=0&Submit=submit">In-Silico PCR ' + a.id + ' (' + esc(chrom) + ') ↗</a>';
    }).join('') +
      '<a target="_blank" rel="noopener" href="' + U.UCSC + '/hgBlat?db=' + S.build + '&type=DNA&sort=query%2Cscore&output=hyperlink&userSeq=' + encodeURIComponent(keys.map(function (k) { return '>' + k + '\n' + set.primers[k].seq; }).join('\n')) + '&Submit=submit">BLAT (tüm primerler) ↗</a>' +
      '<a target="_blank" rel="noopener" href="' + browserUrl(set) + '">UCSC\'de göster ↗</a>' +
      '<button class="small" id="svCopySet">Seti kopyala</button><span class="copyok"></span></div>';
    // PCR koşulları
    var classes = {};
    set.assays.forEach(function (a) { if (a.pcr === 'std' || a.pcr === 'long') { var mx = a.mut ? a.mut.max : a.ref; classes[a.pcr] = Math.max(classes[a.pcr] || 0, mx); } });
    var tms = keys.map(function (k) { return set.primers[k].tm; });
    var gcs = [];
    S.bps.forEach(function (b) { [b.tplL, b.tplR].forEach(function (t) { if (t) gcs.push(gcOf(t.seq)); }); });
    var gcAvg = gcs.length ? gcs.reduce(function (x, y) { return x + y; }, 0) / gcs.length : null;
    html += '<h2 style="margin-top:22px">Önerilen PCR koşulları</h2>';
    Object.keys(classes).forEach(function (c) {
      html += U.renderPcr(E.pcrConditions({ kind: c, tms: tms, sizeMax: classes[c], gc: gcAvg, multiplex: S.type === 'DEL' && c === 'std', cond: S.cond,
        title: c === 'std' ? 'Standart PCR (junction ve normal allel testleri, en uzun ürün ' + bp(classes[c]) + ')' : 'Long-range PCR (en uzun ürün ' + bp(classes[c]) + ')' }));
    });
    if (!Object.keys(classes).length) html += '<p class="muted">Bu sette PCR ile uygulanabilir test yok.</p>';
    $('svSet').innerHTML = html;
    U.bindCopy($('svSet'));
    var cb = $('svCopySet');
    if (cb) cb.addEventListener('click', function () { U.copyText(keys.map(function (k) { return primerName(set.idx, k) + '\t' + set.primers[k].seq; }).join('\n')); });
  }

  function renderDosage() {
    var card = $('svDosageCard');
    var have = S.dosage.length || S.walking.length;
    card.classList.toggle('hidden', !have);
    if (!have) { $('svDosage').innerHTML = ''; return; }
    var html = '';
    var tms = [];
    if (S.dosage.length) {
      html += '<h3>Doz analizi hedefleri (etkilenen bölge içinde)</h3><div class="tablewrap"><table><thead><tr><th>Hedef</th><th>İleri primer</th><th>Geri primer</th><th class="num">Tm</th><th class="num">Ürün</th><th>Konum</th></tr></thead><tbody>' +
        S.dosage.map(function (d, i) {
          if (!d.pair) return '<tr><td>' + esc(d.label) + '</td><td colspan="5" class="muted">Uygun qPCR primeri bulunamadı (tekrar/SNP).</td></tr>';
          tms.push(d.pair.left.tm, d.pair.right.tm);
          return '<tr><td>' + esc(d.label) + '<div class="mono small muted">' + esc(S.base + '_Q' + (i + 1)) + '</div>' + (d.sd ? '<div class="small i-warn">⚠ segmental dup. içinde (%' + (d.sd.frac * 100).toFixed(1) + '): oran yanıltıcı olabilir</div>' : '') + '</td><td class="seq">' + d.pair.left.seq + '</td><td class="seq">' + d.pair.right.seq + '</td><td class="num">' + fmt(d.pair.left.tm) + ' / ' + fmt(d.pair.right.tm) + '</td><td class="num">' + d.pair.size + ' bp</td><td class="mono small">' + d.chrom + ':' + comma(d.pair.ampStart0 + 1) + '-' + comma(d.pair.ampEnd0) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    S.walking.forEach(function (w) {
      if (w.tooLarge) { html += '<p class="hint">Kesim noktası ' + w.bp + ' penceresi (' + bp(w.span) + ') qPCR ile daraltma için çok büyük.</p>'; return; }
      html += '<h3 style="margin-top:14px">Kesim noktası ' + w.bp + ' daraltma noktaları (qPCR walking, pencere ' + bp(w.span) + ')</h3><div class="tablewrap"><table><thead><tr><th>Nokta</th><th>İleri primer</th><th>Geri primer</th><th class="num">Ürün</th><th>Konum</th></tr></thead><tbody>' +
        w.points.map(function (p, i) {
          if (!p.pair) return '<tr><td>W' + w.bp + '.' + (i + 1) + '</td><td colspan="4" class="muted">' + (p.sd ? 'Segmental duplikasyon içinde (%' + (p.sd.frac * 100).toFixed(1) + ' benzer, eşi ' + esc(p.sd.other) + '); qPCR paralogu da ölçer, atlandı.' : 'Bu noktada primer bulunamadı.') + '</td></tr>';
          tms.push(p.pair.left.tm, p.pair.right.tm);
          return '<tr><td class="mono">' + esc(S.base + '_W' + w.bp + '.' + (i + 1)) + '</td><td class="seq">' + p.pair.left.seq + '</td><td class="seq">' + p.pair.right.seq + '</td><td class="num">' + p.pair.size + ' bp</td><td class="mono small">' + p.chrom + ':' + comma(p.pair.ampStart0 + 1) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    });
    if (tms.length) html += U.renderPcr(E.pcrConditions({ kind: 'qpcr', tms: tms, sizeMax: 150, cond: S.cond }));
    $('svDosage').innerHTML = html;
  }

  function customTrack(set) {
    var L = ['track name="SV_primerleri" description="Yapısal varyant primerleri" visibility=pack itemRgb=On'];
    if (S.iv) L.push([S.iv.chrom, S.iv.start - 1, S.iv.end, TYPES[S.type], 0, '.', S.iv.start - 1, S.iv.end, '194,65,12'].join('\t'));
    S.bps.forEach(function (b, i) { if (b.b > b.a) L.push([b.chrom, b.a, b.b, 'KN' + (i + 1) + '_pencere', 0, '.', b.a, b.b, '139,137,131'].join('\t')); });
    if (set) ['L1', 'R1', 'L2', 'R2'].forEach(function (k) {
      var p = set.primers[k]; if (!p) return;
      var b = S.bps[k[1] === '1' ? 0 : 1];
      L.push([b.chrom, p.start0, p.end0, primerName(set.idx, k), 0, p.side === 'F' ? '+' : '-', p.start0, p.end0, p.side === 'F' ? '45,95,78' : '109,40,217'].join('\t'));
    });
    S.dosage.forEach(function (d, i) { if (d.pair) L.push([d.chrom, d.pair.ampStart0, d.pair.ampEnd0, S.base + '_Q' + (i + 1), 0, '.', d.pair.ampStart0, d.pair.ampEnd0, '30,64,175'].join('\t')); });
    return L.join('\n');
  }
  function browserUrl(set, s, e, chrom) {
    chrom = chrom || (S.iv ? S.iv.chrom : S.bps[0].chrom);
    if (s == null) {
      if (S.iv) { var pad = Math.round((S.iv.end - S.iv.start) * 0.1) + 2000; s = S.iv.start - pad; e = S.iv.end + pad; }
      else { s = S.bps[0].a - 3000; e = S.bps[0].b + 3000; }
    }
    return U.UCSC + '/hgTracks?db=' + S.build + '&position=' + encodeURIComponent(chrom + ':' + Math.max(1, s) + '-' + e) + '&hgct_customText=' + encodeURIComponent(customTrack(set));
  }
  function renderImgs() {
    var set = S.design && S.design.sets[S.sel];
    var views = [];
    if (S.iv && S.size > 2000) { var pad = Math.round(S.size * 0.1) + 2000; views.push({ t: 'Tüm bölge', chrom: S.iv.chrom, s: S.iv.start - pad, e: S.iv.end + pad }); }
    S.bps.forEach(function (b, i) {
      var p = set ? ['L', 'R'].map(function (x) { return set.primers[x + (i + 1)]; }).filter(Boolean) : [];
      var s = Math.min.apply(null, [b.a - 600].concat(p.map(function (q) { return q.start0 - 150; })));
      var e = Math.max.apply(null, [b.b + 600].concat(p.map(function (q) { return q.end0 + 150; })));
      if (e - s > 3000000) return;
      views.push({ t: 'Kesim noktası ' + (S.type === 'TRA' ? b.label : i + 1), chrom: b.chrom, s: s, e: e });
    });
    $('svImgs').innerHTML = views.map(function (v) {
      var src = U.UCSC + '/hgRenderTracks?db=' + S.build + '&position=' + v.chrom + ':' + Math.max(1, v.s) + '-' + v.e + '&pix=1000&hideTracks=1&ncbiRefSeqSelect=pack&genomicSuperDups=dense&dbSnp155Common=dense&rmsk=dense&simpleRepeat=dense';
      return '<div style="margin-top:12px"><div class="row"><h3>' + esc(v.t) + ' · ' + esc(v.chrom + ':' + comma(Math.max(1, v.s)) + '-' + comma(v.e)) + '</h3><a class="small" target="_blank" rel="noopener" href="' + browserUrl(set, v.s, v.e, v.chrom) + '">UCSC\'de aç ↗</a></div>' +
        '<img class="ucscimg" alt="UCSC görüntüsü: ' + esc(v.t) + '" data-src="' + src + '"></div>';
    }).join('');
    // UCSC'yi yormamak için görüntüleri sırayla yükle
    var imgs = Array.prototype.slice.call($('svImgs').querySelectorAll('img[data-src]'));
    (function next(i) {
      if (i >= imgs.length) return;
      var im = imgs[i];
      im.onload = function () { setTimeout(function () { next(i + 1); }, 300); };
      im.onerror = function () { im.alt = 'UCSC görüntüsü yüklenemedi; "UCSC\'de aç" bağlantısını kullanın.'; setTimeout(function () { next(i + 1); }, 300); };
      im.src = im.getAttribute('data-src');
    })(0);
  }

  function orderRows() {
    var rows = [['Ad', 'Dizi (5\'-3\')', 'Uzunluk', 'Tm (°C)', 'GC (%)', 'Kullanım', 'Genomik konum (' + S.build + ')']];
    var set = S.design && S.design.sets[S.sel];
    if (set) ['L1', 'R1', 'L2', 'R2'].forEach(function (k) {
      var p = set.primers[k]; if (!p) return;
      var b = S.bps[k[1] === '1' ? 0 : 1];
      var use = set.assays.filter(function (a) { return a.primers.indexOf(k) >= 0; }).map(function (a) { return a.id; }).join('/');
      rows.push([primerName(set.idx, k), p.seq, p.len, fmt(p.tm), fmt(p.gc, 0), use, b.chrom + ':' + (p.start0 + 1) + '-' + p.end0]);
    });
    S.dosage.forEach(function (d, i) { if (d.pair) ['F', 'R'].forEach(function (x) { var p = x === 'F' ? d.pair.left : d.pair.right; rows.push([S.base + '_Q' + (i + 1) + '_' + x, p.seq, p.len, fmt(p.tm), fmt(p.gc, 0), 'qPCR doz: ' + d.label, d.chrom + ':' + (p.start0 + 1) + '-' + p.end0]); }); });
    S.walking.forEach(function (w) { w.points.forEach(function (pt, i) { if (pt.pair) ['F', 'R'].forEach(function (x) { var p = x === 'F' ? pt.pair.left : pt.pair.right; rows.push([S.base + '_W' + w.bp + '.' + (i + 1) + '_' + x, p.seq, p.len, fmt(p.tm), fmt(p.gc, 0), 'qPCR walking KN' + w.bp, pt.chrom + ':' + (p.start0 + 1) + '-' + p.end0]); }); }); });
    return rows;
  }

  /* ---------------- Form ---------------- */
  function syncForm() {
    var tra = $('svType').value === 'TRA';
    $('svRegionBWrap').classList.toggle('hidden', !tra);
    $('svRegionLabel').firstChild.nodeValue = tra ? 'Kesim noktası A ' : 'Bölge / ekzon aralığı ';
    $('svRegion').placeholder = tra ? 'chr9:130700000' : 'chrX:31950000-32100000 · NC_000023.11:g.31950000_32100000del · ex45-50';
    $('svUncWrap').classList.toggle('hidden', $('svMode').value !== 'manual');
  }
  function saveSV() {
    try { localStorage.setItem('sangerSV', JSON.stringify({ t: $('svType').value, g: $('svGene').value, r: $('svRegion').value, rb: $('svRegionB').value, m: $('svMode').value, u: $('svUnc').value, b: $('svBuild').value })); } catch (e) { /* yok */ }
  }
  function loadSV() {
    try {
      var d = JSON.parse(localStorage.getItem('sangerSV') || 'null');
      if (d) { $('svType').value = d.t || 'DEL'; $('svGene').value = d.g || ''; $('svRegion').value = d.r || ''; $('svRegionB').value = d.rb || ''; $('svMode').value = d.m || 'exact'; $('svUnc').value = d.u || '5000'; $('svBuild').value = d.b || 'hg38'; }
    } catch (e) { /* yok */ }
  }
  function setMode(m) {
    var sv = m === 'sv';
    $('modeSnv').classList.toggle('on', !sv); $('modeSv').classList.toggle('on', sv);
    $('formCard').classList.toggle('hidden', sv); $('svFormCard').classList.toggle('hidden', !sv);
    $('results').classList.add('hidden'); $('svResults').classList.add('hidden'); $('progressCard').classList.add('hidden');
    try { localStorage.setItem('sangerMode', m); } catch (e) { /* yok */ }
  }

  document.addEventListener('DOMContentLoaded', function () {
    U = window.PrimerUI;
    loadSV();
    $('modeSnv').addEventListener('click', function () { setMode('snv'); });
    $('modeSv').addEventListener('click', function () { setMode('sv'); });
    $('svType').addEventListener('change', syncForm);
    $('svMode').addEventListener('change', syncForm);
    $('svForm').addEventListener('submit', runSV);
    Array.prototype.forEach.call(document.querySelectorAll('.svchip'), function (c) {
      c.addEventListener('click', function () {
        $('svType').value = c.getAttribute('data-t'); $('svGene').value = c.getAttribute('data-g') || '';
        $('svRegion').value = c.getAttribute('data-r'); $('svRegionB').value = c.getAttribute('data-rb') || '';
        $('svMode').value = c.getAttribute('data-m'); $('svUnc').value = c.getAttribute('data-u') || '5000';
        $('svBuild').value = 'hg38';
        syncForm(); runSV();
      });
    });
    $('svCopyAll').addEventListener('click', function () { U.copyText(orderRows().map(function (r) { return r.join('\t'); }).join('\n')); });
    $('svTsv').addEventListener('click', function () {
      var blob = new Blob(['﻿' + orderRows().map(function (r) { return r.join('\t'); }).join('\n')], { type: 'text/tab-separated-values;charset=utf-8' });
      var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = S.base + '_primerleri.tsv'; a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
    });
    $('svPrint').addEventListener('click', function () { window.print(); });
    var qs = new URLSearchParams(location.search), saved = null;
    try { saved = localStorage.getItem('sangerMode'); } catch (e) { /* yok */ }
    if (qs.get('mode') === 'sv') {
      setMode('sv');
      ['type', 'gene', 'region', 'regionB', 'res', 'unc', 'build'].forEach(function (k) {
        var v = qs.get(k); if (v == null) return;
        var id = { type: 'svType', gene: 'svGene', region: 'svRegion', regionB: 'svRegionB', res: 'svMode', unc: 'svUnc', build: 'svBuild' }[k];
        $(id).value = v;
      });
      syncForm();
      if (qs.get('region')) runSV();
    } else if (!qs.get('variant') && saved === 'sv') setMode('sv');
    syncForm();
  });
})();
