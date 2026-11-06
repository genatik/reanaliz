/* Sanger primer tasarım arayüzü: veri toplama + görselleştirme */
(function () {
  'use strict';
  var E = window.PrimerEngine;
  var UCSC_API = 'https://api.genome.ucsc.edu/getData';
  var UCSC = 'https://genome.ucsc.edu/cgi-bin';
  var VV_API = 'https://rest.variantvalidator.org/VariantValidator/variantvalidator';
  var ENS = { hg38: 'https://rest.ensembl.org', hg19: 'https://grch37.rest.ensembl.org' };
  var M13F = 'TGTAAAACGACGGCCAGT', M13R = 'CAGGAAACAGCTATGAC';

  var $ = function (id) { return document.getElementById(id); };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var state = null;

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function fmt(n, d) { return (n == null || isNaN(n)) ? '–' : Number(n).toFixed(d == null ? 1 : d); }
  function comma(n) { return Number(n).toLocaleString('en-US'); }

  async function getJSON(url, label) {
    var r;
    try { r = await fetch(url); } catch (e) { throw new Error(label + ': bağlantı kurulamadı (' + e.message + ')'); }
    if (!r.ok) {
      var body = ''; try { body = (await r.text()).slice(0, 200); } catch (e2) { /* yok */ }
      throw new Error(label + ': HTTP ' + r.status + (body ? ' – ' + body : ''));
    }
    return r.json();
  }

  /* ---------------- Adımlar ---------------- */
  var STEPS = [
    ['resolve', 'Varyant genomik koordinata çevriliyor'],
    ['gene', 'UCSC: gen modeli (NCBI RefSeq Select)'],
    ['seq', 'UCSC: referans dizi'],
    ['snp', 'UCSC: yaygın SNP\'ler (dbSNP155 Common)'],
    ['rep', 'UCSC: tekrar bölgeleri (RepeatMasker, Simple Repeats)'],
    ['design', 'Primer adayları taranıyor ve puanlanıyor'],
    ['check', 'Çiftler kontrol ediliyor (dimer, SNP, tekrar, yerel yanlış bağlanma)']
  ];
  function initSteps() {
    $('steps').innerHTML = STEPS.map(function (s) { return '<li class="wait" id="st-' + s[0] + '"><span class="st"></span><span>' + s[1] + ' <span class="det"></span></span></li>'; }).join('');
    $('msgs').innerHTML = '';
  }
  function step(id, cls, det) {
    var li = $('st-' + id); if (!li) return;
    li.className = cls;
    if (det != null) li.querySelector('.det').textContent = det ? '· ' + det : '';
  }
  function msg(kind, html) { $('msgs').insertAdjacentHTML('beforeend', '<div class="alert ' + kind + '">' + html + '</div>'); }

  /* ---------------- Varyant çözümleme ---------------- */
  function chromName(c) {
    c = String(c).replace(/^chr/i, '');
    if (c === 'MT' || c === 'M') return 'chrM';
    return 'chr' + c.toUpperCase();
  }

  async function resolveVariant(gene, text, build) {
    var v = text.trim().replace(/\s+/g, ' ');
    var m;
    if ((m = v.match(/^rs\d+$/i))) return resolveRs(v, build);
    m = v.match(/^(?:chr)?([0-9]{1,2}|X|Y|M|MT)\s*[:\-_ ]\s*([\d,]+)(?:\s*[:\-_ ]\s*([ACGT]+)\s*[:\-_ >\/]+\s*([ACGT]+|-|\.))?$/i);
    if (m) {
      var pos = parseInt(m[2].replace(/,/g, ''), 10);
      var ref = (m[3] || '').toUpperCase(), alt = (m[4] || '').toUpperCase();
      return {
        source: 'Genomik koordinat (kullanıcı)', chrom: chromName(m[1]), pos: pos, ref: ref || null, alt: alt || null,
        start0: pos - 1, end0: pos - 1 + Math.max(1, ref.length), gene: gene, warnings: []
      };
    }
    return resolveHgvs(gene, v, build);
  }

  async function resolveRs(rs, build) {
    var d = await getJSON(ENS[build] + '/variation/human/' + rs + '?content-type=application/json', 'Ensembl');
    var asm = build === 'hg38' ? 'GRCh38' : 'GRCh37';
    var mp = (d.mappings || []).filter(function (x) { return x.assembly_name === asm && /^([0-9]{1,2}|X|Y|MT)$/.test(x.seq_region_name); })[0];
    if (!mp) throw new Error(rs + ' için ' + asm + ' üzerinde birincil kromozom konumu bulunamadı.');
    var a = Math.min(mp.start, mp.end), b = Math.max(mp.start, mp.end);
    var alleles = (mp.allele_string || '').split('/');
    return {
      source: 'Ensembl variation (' + rs + ')', chrom: chromName(mp.seq_region_name), pos: a,
      ref: alleles[0] && alleles[0] !== '-' ? alleles[0] : null, alt: alleles.slice(1).join(','),
      start0: a - 1, end0: b, rsid: rs, warnings: (d.mappings.length > 1 ? ['rsID birden fazla konuma eşleniyor; birincil kromozomdaki ilk konum kullanıldı.'] : []),
      hgvsG: mp.location
    };
  }

  async function resolveHgvs(gene, v, build) {
    var q = v.replace(/^\s*:/, '');
    if (!/^(NM_|NR_|NC_|NG_|ENST|LRG_|XM_|XR_)/i.test(q)) {
      if (!gene) throw new Error('Transkript belirtilmedi: gen adı girin ya da varyantı NM_... ile yazın.');
      if (!/^[cgnrm]\./.test(q)) q = 'c.' + q;
      q = gene.trim().toUpperCase() + ':' + q;
    }
    var asm = build === 'hg38' ? 'GRCh38' : 'GRCh37';
    var url = VV_API + '/' + asm + '/' + encodeURIComponent(q) + '/mane_select?content-type=application/json';
    var d = await getJSON(url, 'VariantValidator');
    var entries = Object.keys(d).filter(function (k) { return d[k] && typeof d[k] === 'object' && 'primary_assembly_loci' in d[k]; }).map(function (k) { return [k, d[k]]; });
    var hit = entries.filter(function (e) { var l = e[1].primary_assembly_loci; return l && l[build] && l[build].vcf; })[0];
    var allWarn = [];
    entries.forEach(function (e) { (e[1].validation_warnings || []).forEach(function (w) { allWarn.push(w); }); });
    if (!hit) {
      var useful = allWarn.filter(function (w) { return !/gene symbol|^Lovd|LovdSyntaxcheck/i.test(w); });
      throw new Error('VariantValidator varyantı doğrulayamadı: ' + (useful.length ? useful.join(' · ') : 'gösterimi kontrol edin (ör. c.1521_1523del, c.489+1G>T).'));
    }
    var r = hit[1], loc = r.primary_assembly_loci[build], vcf = loc.vcf;
    var pos = parseInt(vcf.pos, 10);
    var warnings = [];
    (r.validation_warnings || []).forEach(function (w) {
      if (/gene symbol/i.test(w)) warnings.push({ info: true, text: 'Gen sembolü yerine MANE Select transkripti kullanıldı: ' + (r.hgvs_transcript_variant || hit[0]).split(':')[0] });
      else if (/automap|chose|selected/i.test(w)) warnings.push({ info: true, text: w });
      else warnings.push({ text: w });
    });
    var exonPos = r.variant_exonic_positions && (r.variant_exonic_positions[loc.hgvs_genomic_description.split(':')[0]] || null);
    return {
      source: 'VariantValidator', chrom: chromName(vcf.chr), pos: pos, ref: vcf.ref, alt: vcf.alt,
      start0: pos - 1, end0: pos - 1 + vcf.ref.length,
      hgvsC: r.hgvs_transcript_variant || hit[0], hgvsG: loc.hgvs_genomic_description,
      hgvsP: r.hgvs_predicted_protein_consequence && (r.hgvs_predicted_protein_consequence.tlr || r.hgvs_predicted_protein_consequence.slr),
      gene: r.gene_symbol || gene, transcript: (r.hgvs_transcript_variant || hit[0]).split(':')[0],
      exonVV: exonPos, warnings: warnings
    };
  }

  /* ---------------- UCSC ---------------- */
  async function ucscTrack(build, chrom, s, e, track) {
    var d = await getJSON(UCSC_API + '/track?genome=' + build + ';chrom=' + chrom + ';start=' + s + ';end=' + e + ';track=' + track, 'UCSC ' + track);
    return d[track] || [];
  }
  function parseGenePred(rec) {
    var st = rec.exonStarts.split(',').filter(Boolean).map(Number), en = rec.exonEnds.split(',').filter(Boolean).map(Number);
    var exons = st.map(function (s, i) { return { start0: s, end0: en[i], num: rec.strand === '+' ? i + 1 : st.length - i }; });
    return { name: rec.name, gene: rec.name2, strand: rec.strand, txStart: rec.txStart, txEnd: rec.txEnd, cdsStart: rec.cdsStart, cdsEnd: rec.cdsEnd, exons: exons };
  }
  function locateInGene(tx, s0, e0) {
    if (!tx) return null;
    for (var i = 0; i < tx.exons.length; i++) {
      var ex = tx.exons[i];
      if (s0 < ex.end0 && ex.start0 < e0) {
        var dEdge = Math.min(Math.abs(s0 - ex.start0), Math.abs(ex.end0 - e0));
        return { kind: 'exon', exon: ex, text: 'Ekzon ' + ex.num + ' / ' + tx.exons.length + (dEdge <= 3 ? ' (ekzon kenarına ' + dEdge + ' bp; splice bölgesi)' : '') };
      }
    }
    for (var j = 0; j < tx.exons.length - 1; j++) {
      var a = tx.exons[j], b = tx.exons[j + 1];
      if (s0 >= a.end0 && e0 <= b.start0) {
        var n = tx.strand === '+' ? a.num : b.num;
        var d = Math.min(s0 - a.end0 + 1, b.start0 - e0 + 1);
        return { kind: 'intron', exon: null, intron: n, flank: [a, b], text: 'İntron ' + n + ' (en yakın ekzona ' + d + ' bp)' };
      }
    }
    return { kind: 'outside', text: 'Transkript dışı / UTR çevresi' };
  }
  function maxMaf(s) {
    var xs = String(s.minorAlleleFreq || '').split(',').map(Number).filter(function (x) { return isFinite(x) && x > 0; });
    return xs.length ? Math.max.apply(null, xs) : null;
  }

  /* ---------------- Parametreler ---------------- */
  var NUM_IDS = ['sizeMin', 'sizeMax', 'lenMin', 'lenOpt', 'lenMax', 'tmMin', 'tmOpt', 'tmMax', 'tmDiffMax', 'gcMin', 'gcMax', 'minDist', 'numReturn'];
  function readParams() {
    var p = {};
    NUM_IDS.forEach(function (id) { p[id] = parseFloat($(id).value); });
    p.sizeOpt = Math.round((p.sizeMin + p.sizeMax) / 2);
    p.numReturn = Math.max(1, Math.min(10, Math.round(p.numReturn)));
    p.cond = { mv: parseFloat($('mv').value), dv: parseFloat($('dv').value), dntp: parseFloat($('dntp').value), dna: parseFloat($('dna').value) };
    p.avoidRepeats = $('avoidRepeats').checked;
    p.snpPolicy = 'strict';
    return p;
  }

  // Kademeli gevşetme: önce sıkı kriterler, yeterli çift yoksa kontrollü gevşetme
  function designTiers(input, p) {
    var tiers = [
      { label: 'Sıkı kriterler', p: p },
      { label: 'Gevşetilmiş: primer 3\' ucunda olmayan yaygın SNP\'ye izin, Tm ±1 °C, GC %30–70', p: Object.assign({}, p, { snpPolicy: 'relaxed', tmMin: p.tmMin - 1, tmMax: p.tmMax + 1, gcMin: Math.min(p.gcMin, 30), gcMax: Math.max(p.gcMax, 70) }) },
      { label: 'Gevşetilmiş: tekrar bölgesine izin, ürün aralığı genişletildi, ΔTm 3.5 °C', p: Object.assign({}, p, { snpPolicy: 'relaxed', avoidRepeats: false, tmMin: p.tmMin - 2, tmMax: p.tmMax + 2, gcMin: 30, gcMax: 70, tmDiffMax: 3.5, sizeMin: Math.max(150, p.sizeMin - 100), sizeMax: p.sizeMax + 150, minDist: Math.max(45, p.minDist - 15) }) }
    ];
    var chosen = [], stats = [];
    for (var t = 0; t < tiers.length && chosen.length < p.numReturn; t++) {
      var res = E.design(input, tiers[t].p);
      stats.push({ tier: t, label: tiers[t].label, stats: res.stats, found: res.pairs.length });
      res.pairs.forEach(function (pr) {
        if (chosen.length >= p.numReturn) return;
        var dup = chosen.some(function (o) { return Math.abs(o.left.start0 - pr.left.start0) < 10 || Math.abs(o.right.start0 - pr.right.start0) < 10; });
        if (dup) return;
        pr.tier = t; pr.tierLabel = tiers[t].label;
        chosen.push(pr);
      });
    }
    return { pairs: chosen, tiers: stats };
  }

  /* ---------------- Ana akış ---------------- */
  async function run(ev) {
    if (ev) ev.preventDefault();
    var gene = $('gene').value.trim().toUpperCase(), varText = $('variant').value.trim(), build = $('build').value;
    if (!varText) return;
    saveInputs();
    var p = readParams();
    if (!(p.sizeMin < p.sizeMax && p.tmMin <= p.tmOpt && p.tmOpt <= p.tmMax && p.lenMin <= p.lenOpt && p.lenOpt <= p.lenMax)) {
      $('progressCard').classList.remove('hidden'); initSteps(); msg('err', 'Parametreler tutarsız (min ≤ opt ≤ max olmalı).'); return;
    }
    $('goBtn').disabled = true;
    $('results').classList.add('hidden');
    $('progressCard').classList.remove('hidden');
    initSteps();
    var cur = 'resolve';
    try {
      step('resolve', 'run');
      var V = await resolveVariant(gene, varText, build);
      step('resolve', 'ok', V.source + ' → ' + V.chrom + ':' + comma(V.pos) + (V.ref ? ' ' + V.ref + '>' + (V.alt || '?') : ''));
      (V.warnings || []).forEach(function (w) { if (typeof w === 'string') msg('warn', esc(w)); else msg(w.info ? 'info' : 'warn', esc(w.text)); });

      cur = 'gene'; step('gene', 'run');
      var genes = await ucscTrack(build, V.chrom, Math.max(0, V.start0 - 5), V.end0 + 5, 'ncbiRefSeqSelect');
      var txs = genes.map(parseGenePred);
      var tx = null;
      if (V.transcript) tx = txs.filter(function (t) { return t.name.split('.')[0] === V.transcript.split('.')[0]; })[0];
      if (!tx && gene) tx = txs.filter(function (t) { return t.gene === gene; })[0];
      if (!tx) tx = txs[0] || null;
      var where = locateInGene(tx, V.start0, V.end0);
      step('gene', 'ok', tx ? tx.gene + ' ' + tx.name + ' · ' + where.text : 'bu konumda RefSeq Select transkripti yok');
      if (gene && tx && tx.gene !== gene && !txs.some(function (t) { return t.gene === gene; })) {
        msg('warn', 'Girilen gen (<b>' + esc(gene) + '</b>) bu konumdaki gen ile uyuşmuyor: <b>' + esc(tx.gene) + '</b>. Varyant gösterimini kontrol edin.');
      }
      if (!tx && gene) msg('warn', 'Bu konumda ' + esc(gene) + ' için RefSeq Select transkripti bulunamadı.');

      // Kapsanacak bölge (ekzonun tamamı istenirse)
      var cover = null;
      if ($('cover').checked) {
        if (where && where.kind === 'exon') {
          var ex = where.exon, need = (ex.end0 - ex.start0) + 2 * p.minDist + 2 * p.lenMin;
          if (need > p.sizeMax) {
            msg('warn', 'Ekzon ' + ex.num + ' (' + (ex.end0 - ex.start0) + ' bp) seçilen maksimum ürün boyuna sığmıyor; yalnızca varyant çevresi için tasarlandı. Ekzonu kapsamak için ürün max değerini en az ' + need + ' bp yapın.');
          } else cover = { start0: ex.start0, end0: ex.end0, label: 'Ekzon ' + ex.num };
        } else msg('info', 'Varyant bir ekzon içinde değil; "ekzonun tamamını kapsa" seçeneği uygulanmadı.');
      }

      var needS = Math.min(V.start0, cover ? cover.start0 : V.start0), needE = Math.max(V.end0, cover ? cover.end0 : V.end0);
      var W = p.sizeMax + 250;
      var rs = Math.max(0, needE - W), re = needS + W;

      cur = 'seq'; step('seq', 'run');
      var seqd = await getJSON(UCSC_API + '/sequence?genome=' + build + ';chrom=' + V.chrom + ';start=' + rs + ';end=' + re, 'UCSC sequence');
      var tpl = String(seqd.dna || '').toUpperCase();
      if (!tpl) throw new Error('UCSC referans dizi döndürmedi.');
      var refAt = tpl.substring(V.start0 - rs, V.end0 - rs);
      V.refAt = refAt;
      V.refOk = V.ref ? (refAt === V.ref.toUpperCase()) : null;
      step('seq', 'ok', comma(tpl.length) + ' bp, ' + V.chrom + ':' + comma(rs + 1) + '-' + comma(re));
      if (V.refOk === false) msg('err', 'Referans uyuşmazlığı: varyantın REF alleli <b>' + esc(V.ref) + '</b>, UCSC ' + build + ' referansında bu konumda <b>' + esc(refAt) + '</b> var. Genom sürümünü kontrol edin.');
      await sleep(150);

      cur = 'snp'; step('snp', 'run');
      var snpRaw = await ucscTrack(build, V.chrom, rs, re, 'dbSnp155Common');
      var snps = snpRaw.map(function (s) { return { start0: s.chromStart, end0: Math.max(s.chromEnd, s.chromStart + 1), name: s.name, ref: s.ref, alts: String(s.alts || '').replace(/,$/, ''), maf: maxMaf(s), cls: s.class }; })
        .filter(function (s) { return !(s.start0 < V.end0 && V.start0 < s.end0); }); // varyantın kendisi maskelenmesin
      step('snp', 'ok', snps.length + ' yaygın SNP');
      await sleep(150);

      cur = 'rep'; step('rep', 'run');
      var rmsk = await ucscTrack(build, V.chrom, rs, re, 'rmsk'); await sleep(150);
      var simple = await ucscTrack(build, V.chrom, rs, re, 'simpleRepeat');
      var repeats = rmsk.map(function (r) { return { start0: r.genoStart, end0: r.genoEnd, name: r.repName + ' (' + r.repClass + ')', cls: r.repClass }; })
        .concat(simple.map(function (r) { return { start0: r.chromStart, end0: r.chromEnd, name: 'Basit tekrar ' + (r.sequence ? '(' + r.sequence + ')n' : ''), cls: 'Simple' }; }));
      step('rep', 'ok', rmsk.length + ' RepeatMasker, ' + simple.length + ' basit tekrar');

      cur = 'design'; step('design', 'run');
      await sleep(20);
      var input = { template: tpl, tplStart0: rs, chrom: V.chrom, varStart0: V.start0, varEnd0: V.end0, snps: snps, repeats: repeats, cover: cover };
      var t0 = performance.now();
      var D = designTiers(input, p);
      var st0 = D.tiers[0].stats;
      step('design', 'ok', comma(st0.leftCandidates + st0.rightCandidates) + ' aday, ' + comma(st0.leftOk) + ' ileri / ' + comma(st0.rightOk) + ' geri primer filtreyi geçti, ' + Math.round(performance.now() - t0) + ' ms');

      cur = 'check'; step('check', 'run');
      if (!D.pairs.length) throw new Error('Uygun primer çifti bulunamadı. Ürün boyunu büyütmeyi, Tm aralığını genişletmeyi veya tekrar bölgelerine izin vermeyi deneyin.');
      D.pairs.forEach(function (pr, i) { pr.idx = i + 1; pr.checks = buildChecks(pr, p, input); });
      var relaxed = D.pairs.filter(function (x) { return x.tier > 0; }).length;
      step('check', 'ok', D.pairs.length + ' çift' + (relaxed ? ' (' + relaxed + ' tanesi gevşetilmiş kriterle)' : ''));
      if (relaxed) msg('warn', 'Sıkı kriterlerle yeterli çift bulunamadı; ' + relaxed + ' alternatif gevşetilmiş kriterle tasarlandı. Bu çiftlerin kontrol listesindeki uyarılara dikkat edin.');

      state = { V: V, tx: tx, txs: txs, where: where, cover: cover, build: build, rs: rs, re: re, tpl: tpl, snps: snps, repeats: repeats, pairs: D.pairs, p: p, gene: (tx && tx.gene) || gene || V.gene || 'GEN', sel: 0 };
      renderAll();
      $('results').classList.remove('hidden');
    } catch (err) {
      step(cur, 'err');
      msg('err', esc(err.message || String(err)));
      if (window.console) console.warn(err);
    } finally {
      $('goBtn').disabled = false;
    }
  }

  /* ---------------- Kontrol listesi ---------------- */
  function buildChecks(pr, p, input) {
    var c = [], L = pr.left, R = pr.right;
    function add(kind, text) { c.push({ kind: kind, text: text }); }
    var tmOk = function (x) { return x.tm >= p.tmMin && x.tm <= p.tmMax; };
    add(tmOk(L) && tmOk(R) && pr.dTm <= p.tmDiffMax ? 'ok' : 'warn', 'Tm: F ' + fmt(L.tm) + ' °C, R ' + fmt(R.tm) + ' °C, ΔTm ' + fmt(pr.dTm) + ' °C (hedef ' + p.tmMin + '–' + p.tmMax + ', ΔTm ≤ ' + p.tmDiffMax + ')');
    add(L.gc >= p.gcMin && L.gc <= p.gcMax && R.gc >= p.gcMin && R.gc <= p.gcMax ? 'ok' : 'warn', 'GC: F %' + fmt(L.gc, 0) + ', R %' + fmt(R.gc, 0));
    var clamp = function (x) { return x.gcClamp >= 1 && x.gcClamp <= 3; };
    add(clamp(L) && clamp(R) ? 'ok' : 'warn', "3' GC kenetlenmesi (son 5 bazda 1–3 G/C): F " + L.gcClamp + ', R ' + R.gcClamp);
    add(L.maxRun <= 4 && R.maxRun <= 4 ? 'ok' : 'warn', 'Homopolimer en fazla 4: F ' + L.maxRun + ', R ' + R.maxRun);
    var hpWorst = Math.min(L.hairpin, R.hairpin);
    add(hpWorst > -2 ? 'ok' : 'warn', 'Hairpin ΔG: F ' + fmt(L.hairpin) + ', R ' + fmt(R.hairpin) + ' kcal/mol (eşik −2 uyarı, −3 ret)');
    var sdWorst = Math.min(L.selfDimer, R.selfDimer), edWorst = Math.min(L.endDimer, R.endDimer);
    add(sdWorst > -7 && edWorst > -5 ? 'ok' : 'warn', "Self-dimer ΔG: F " + fmt(L.selfDimer) + ', R ' + fmt(R.selfDimer) + " · 3' uç self-dimer: F " + fmt(L.endDimer) + ', R ' + fmt(R.endDimer) + ' kcal/mol');
    add(pr.heteroDimer > -7 && pr.heteroDimer3 > -5 ? 'ok' : 'warn', "F×R heterodimer ΔG " + fmt(pr.heteroDimer) + " · 3' uç heterodimer " + fmt(pr.heteroDimer3) + ' kcal/mol');
    add(L.endStab <= 9 && R.endStab <= 9 ? 'ok' : 'warn', "3' uç stabilitesi (son 5 baz): F " + fmt(L.endStab) + ', R ' + fmt(R.endStab) + ' kcal/mol (≤ 9)');
    var snpP = (L.snps || []).concat(R.snps || []);
    add(snpP.length ? 'warn' : 'ok', snpP.length ? 'Primer bölgesinde yaygın SNP: ' + snpP.map(function (s) { return s.name + " (3' uca " + s.distFrom3 + ' baz)'; }).join(', ') : 'Primer bağlanma bölgelerinde yaygın SNP yok (UCSC dbSNP155 Common)');
    var repP = (L.repeats || []).concat(R.repeats || []);
    add(repP.length ? 'warn' : 'ok', repP.length ? 'Primer tekrar bölgesinde: ' + repP.join(', ') : 'Primerler tekrar bölgesinde değil (UCSC RepeatMasker + Simple Repeats)');
    add('ok', "Şablonda (±" + comma(input.template.length >> 1) + " bp) primer 3' ucunun (12 baz) alternatif bağlanma yeri yok");
    add(pr.varFromF >= p.minDist && pr.varFromR >= p.minDist ? 'ok' : 'warn', 'Varyant konumu: ileri okumada primerden sonra ' + pr.varFromF + '. baz, geri okumada ' + pr.varFromR + '. baz');
    if (input.cover) add('ok', input.cover.label + ' tamamen amplikon içinde (kenarlardan en az ' + p.minDist + ' bp)');
    add(pr.ampGC <= 65 ? 'ok' : 'warn', 'Amplikon: ' + pr.size + ' bp, GC %' + fmt(pr.ampGC, 0) + ', tahmini Tm ' + fmt(pr.ampTm) + ' °C');
    (pr.warnings || []).forEach(function (w) { if (!/SNP|tekrar|60 bazdan/.test(w)) add('warn', w); });
    add('man', 'Genom geneli özgüllük: UCSC In-Silico PCR ve Primer-BLAST ile doğrulayın (aşağıdaki bağlantılar). Psödogen veya paralog gen varsa özellikle önemlidir.');
    return c;
  }

  /* ---------------- Görselleştirme ---------------- */
  function renderAll() {
    renderVariant(); renderMap(); renderTable(); renderTabs(); renderDetail(); renderUcsc();
  }

  function renderVariant() {
    var S = state, V = S.V;
    var rows = [
      ['Gen', S.gene],
      ['Transkript', V.transcript || (S.tx ? S.tx.name : '–')],
      ['HGVS c.', V.hgvsC || '–'],
      ['HGVS p.', V.hgvsP || '–'],
      ['HGVS g.', V.hgvsG || '–'],
      ['Kaynak', V.source]
    ];
    $('varKv').innerHTML = rows.map(function (r) { return '<dt>' + r[0] + '</dt><dd>' + esc(r[1]) + '</dd>'; }).join('');
    var loc = [
      ['Genom', S.build],
      ['Konum (VCF)', V.chrom + ':' + comma(V.pos) + (V.ref ? ' ' + V.ref + ' > ' + (V.alt || '?') : '')],
      ['Gen içi yer', S.where ? S.where.text : '–'],
      ['Referans (UCSC)', V.refAt || '–'],
      ['Bölgedeki yaygın SNP', S.snps.length],
      ['Bölgedeki tekrar', S.repeats.length]
    ];
    $('locKv').innerHTML = loc.map(function (r) { return '<dt>' + r[0] + '</dt><dd>' + esc(r[1]) + '</dd>'; }).join('');
    $('refCheck').innerHTML = V.refOk === true ? '<span class="badge b-ok">REF alleli UCSC referansı ile uyumlu</span>' : V.refOk === false ? '<span class="badge b-err">REF uyuşmazlığı</span>' : '<span class="badge b-info">REF alleli verilmedi</span>';
  }

  function regionOfPairs() {
    var S = state, a = Infinity, b = -Infinity;
    S.pairs.forEach(function (pr) { a = Math.min(a, pr.ampStart0); b = Math.max(b, pr.ampEnd0); });
    var pad = Math.round((b - a) * 0.06) + 20;
    return [Math.max(S.rs, a - pad), Math.min(S.re, b + pad)];
  }

  function renderMap() {
    var S = state, reg = regionOfPairs(), A = reg[0], B = reg[1];
    var Wd = 1000, ml = 110, mr = 20, pw = Wd - ml - mr;
    var x = function (g) { return ml + (g - A) / (B - A) * pw; };
    var y = 10, out = [];
    // cetvel
    var span = B - A, stepBp = [50, 100, 200, 250, 500, 1000].filter(function (s) { return span / s <= 10; })[0] || 1000;
    out.push('<line x1="' + ml + '" x2="' + (Wd - mr) + '" y1="' + (y + 16) + '" y2="' + (y + 16) + '" stroke="var(--line)"/>');
    for (var t = Math.ceil(A / stepBp) * stepBp; t <= B; t += stepBp) {
      out.push('<line x1="' + x(t) + '" x2="' + x(t) + '" y1="' + (y + 12) + '" y2="' + (y + 20) + '" stroke="var(--ink-3)"/><text x="' + x(t) + '" y="' + (y + 8) + '" text-anchor="middle">' + comma(t) + '</text>');
    }
    out.push('<text x="4" y="' + (y + 20) + '">' + esc(S.V.chrom) + '</text>');
    y += 34;
    // gen modeli
    out.push('<text x="4" y="' + (y + 12) + '">' + esc(S.tx ? S.tx.gene : 'Gen') + '</text>');
    if (S.tx) {
      var ta = Math.max(A, S.tx.txStart), tb = Math.min(B, S.tx.txEnd);
      if (ta < tb) out.push('<line x1="' + x(ta) + '" x2="' + x(tb) + '" y1="' + (y + 8) + '" y2="' + (y + 8) + '" stroke="var(--exon)" stroke-width="1.5"/>');
      // yön okları
      for (var g = A + stepBp / 2; g < B; g += stepBp / 2) {
        if (g > S.tx.txStart && g < S.tx.txEnd) {
          var ax = x(g), d = S.tx.strand === '+' ? 1 : -1;
          out.push('<path d="M' + (ax - 3 * d) + ' ' + (y + 5) + ' L' + ax + ' ' + (y + 8) + ' L' + (ax - 3 * d) + ' ' + (y + 11) + '" fill="none" stroke="var(--exon)" stroke-width="1"/>');
        }
      }
      S.tx.exons.forEach(function (ex) {
        var a = Math.max(A, ex.start0), b = Math.min(B, ex.end0);
        if (a >= b) return;
        var isCds = !(ex.end0 <= S.tx.cdsStart || ex.start0 >= S.tx.cdsEnd);
        var h = isCds ? 16 : 9;
        out.push('<rect x="' + x(a) + '" y="' + (y + 8 - h / 2) + '" width="' + Math.max(1.5, x(b) - x(a)) + '" height="' + h + '" fill="var(--exon)"><title>Ekzon ' + ex.num + ' (' + comma(ex.start0 + 1) + '-' + comma(ex.end0) + ')</title></rect>');
        var mid = (x(a) + x(b)) / 2;
        if (x(b) - x(a) > 28) out.push('<text x="' + mid + '" y="' + (y + 30) + '" text-anchor="middle">E' + ex.num + '</text>');
      });
    }
    y += 38;
    // tekrarlar
    out.push('<text x="4" y="' + (y + 10) + '">Tekrar</text>');
    S.repeats.forEach(function (r) {
      var a = Math.max(A, r.start0), b = Math.min(B, r.end0);
      if (a >= b) return;
      out.push('<rect x="' + x(a) + '" y="' + (y + 2) + '" width="' + Math.max(1.5, x(b) - x(a)) + '" height="10" fill="var(--rep)" opacity=".75"><title>' + esc(r.name) + ' ' + comma(r.start0 + 1) + '-' + comma(r.end0) + '</title></rect>');
    });
    y += 20;
    // SNP
    out.push('<text x="4" y="' + (y + 10) + '">SNP (common)</text>');
    S.snps.forEach(function (s) {
      if (s.end0 <= A || s.start0 >= B) return;
      out.push('<rect x="' + (x(s.start0) - 0.75) + '" y="' + (y + 1) + '" width="1.5" height="12" fill="var(--snp)"><title>' + esc(s.name) + ' ' + esc(s.ref) + '>' + esc(s.alts) + (s.maf ? ' · maks. MAF ' + s.maf.toFixed(3) : '') + '</title></rect>');
    });
    y += 22;
    // varyant çizgisi (aşağıda tüm satırları keser)
    var vy0 = y;
    var rowsH = S.pairs.length * 26 + 6;
    // çiftler
    var pairRows = S.pairs.map(function (pr, i) {
      var ry = y + i * 26;
      var f0 = x(pr.left.start0), f1 = x(pr.left.end0), r0 = x(pr.right.start0), r1 = x(pr.right.end0);
      return '<g class="pairrow' + (i === S.sel ? ' sel' : '') + '" data-i="' + i + '">' +
        '<rect class="hl" x="0" y="' + ry + '" width="' + Wd + '" height="24" rx="4" fill="transparent"/>' +
        '<text x="4" y="' + (ry + 16) + '">Çift ' + pr.idx + ' · ' + pr.size + ' bp' + (pr.tier ? ' *' : '') + '</text>' +
        '<line x1="' + f1 + '" x2="' + r0 + '" y1="' + (ry + 12) + '" y2="' + (ry + 12) + '" stroke="var(--ink-3)" stroke-width="2"/>' +
        '<path d="M' + f0 + ' ' + (ry + 7) + ' L' + (f1 - 4) + ' ' + (ry + 7) + ' L' + f1 + ' ' + (ry + 12) + ' L' + (f1 - 4) + ' ' + (ry + 17) + ' L' + f0 + ' ' + (ry + 17) + ' Z" fill="var(--fwd)"><title>F ' + pr.left.seq + '</title></path>' +
        '<path d="M' + r1 + ' ' + (ry + 7) + ' L' + (r0 + 4) + ' ' + (ry + 7) + ' L' + r0 + ' ' + (ry + 12) + ' L' + (r0 + 4) + ' ' + (ry + 17) + ' L' + r1 + ' ' + (ry + 17) + ' Z" fill="var(--rev)"><title>R ' + pr.right.seq + '</title></path>' +
        '</g>';
    });
    out.push(pairRows.join(''));
    var vx = x((S.V.start0 + S.V.end0) / 2);
    out.push('<line x1="' + vx + '" x2="' + vx + '" y1="' + (34 + 10) + '" y2="' + (vy0 + rowsH) + '" stroke="var(--var)" stroke-width="2" opacity=".85"/>');
    out.push('<rect x="' + (vx - 4) + '" y="' + (34 + 2) + '" width="8" height="8" rx="2" fill="var(--var)"><title>Varyant ' + esc(S.V.chrom + ':' + S.V.pos) + '</title></rect>');
    if (S.cover) {
      out.push('<rect x="' + x(S.cover.start0) + '" y="' + (vy0 - 3) + '" width="' + (x(S.cover.end0) - x(S.cover.start0)) + '" height="' + (rowsH) + '" fill="var(--var)" opacity=".08"/>');
    }
    var H = vy0 + rowsH + 4;
    $('mapBox').innerHTML = '<svg viewBox="0 0 ' + Wd + ' ' + H + '" role="img" aria-label="Primer çiftlerinin genomik haritası">' + out.join('') + '</svg>';
    Array.prototype.forEach.call($('mapBox').querySelectorAll('.pairrow'), function (g) {
      g.addEventListener('click', function () { select(+g.getAttribute('data-i')); });
    });
    $('regionLinks').innerHTML = '<a target="_blank" rel="noopener" href="' + ucscBrowserUrl(A, B) + '">Tüm çiftlerle UCSC\'de aç ↗</a>';
  }

  // Adlandırma: GEN_E11_c1521_F1 / GEN_IVS4_c489+1_R2
  function primerName(pr, side) {
    var S = state, parts = [S.gene], w = S.where;
    if (w && w.kind === 'exon') parts.push('E' + w.exon.num);
    else if (w && w.kind === 'intron') parts.push('IVS' + w.intron);
    var m = S.V.hgvsC && S.V.hgvsC.match(/:c\.([-*]?\d+(?:[+-]\d+)?)/);
    parts.push(m ? 'c' + m[1] : String(S.V.pos));
    return parts.join('_') + '_' + side + pr.idx;
  }

  function renderTable() {
    var S = state;
    var h = '<thead><tr><th>Çift</th><th>Primer</th><th>Dizi (5\'→3\')</th><th class="num">Uz.</th><th class="num">Tm</th><th class="num">GC%</th><th class="num">Ürün</th><th class="num">Varyant F/R</th><th>Durum</th></tr></thead><tbody>';
    S.pairs.forEach(function (pr, i) {
      var nWarn = pr.checks.filter(function (c) { return c.kind === 'warn'; }).length;
      var badge = nWarn === 0 ? '<span class="badge b-ok">Uygun</span>' : '<span class="badge b-warn">' + nWarn + ' uyarı</span>';
      if (pr.tier) badge += ' <span class="badge b-info">gevşetilmiş</span>';
      [['F', pr.left], ['R', pr.right]].forEach(function (x, k) {
        h += '<tr class="clickable' + (i === S.sel ? ' selrow' : '') + '" data-i="' + i + '">' +
          (k === 0 ? '<td rowspan="2"><b>' + pr.idx + '</b></td>' : '') +
          '<td class="mono" style="color:var(' + (x[0] === 'F' ? '--fwd' : '--rev') + ')">' + esc(primerName(pr, x[0])) + '</td>' +
          '<td class="seq">' + x[1].seq + '</td><td class="num">' + x[1].len + '</td><td class="num">' + fmt(x[1].tm) + '</td><td class="num">' + fmt(x[1].gc, 0) + '</td>' +
          (k === 0 ? '<td class="num" rowspan="2">' + pr.size + ' bp</td><td class="num" rowspan="2">' + pr.varFromF + ' / ' + pr.varFromR + '</td><td rowspan="2">' + badge + '</td>' : '') + '</tr>';
      });
    });
    $('pairTable').innerHTML = h + '</tbody>';
    Array.prototype.forEach.call($('pairTable').querySelectorAll('tr.clickable'), function (tr) {
      tr.addEventListener('click', function () { select(+tr.getAttribute('data-i')); });
    });
  }

  function renderTabs() {
    var S = state;
    $('tabs').innerHTML = S.pairs.map(function (pr, i) { return '<button class="small' + (i === S.sel ? ' on' : '') + '" data-i="' + i + '">Çift ' + pr.idx + '</button>'; }).join('');
    Array.prototype.forEach.call($('tabs').querySelectorAll('button'), function (b) { b.addEventListener('click', function () { select(+b.getAttribute('data-i')); }); });
  }

  function select(i) {
    state.sel = i;
    renderTabs(); renderDetail(); renderUcsc();
    Array.prototype.forEach.call($('mapBox').querySelectorAll('.pairrow'), function (g) { g.classList.toggle('sel', +g.getAttribute('data-i') === i); });
    Array.prototype.forEach.call($('pairTable').querySelectorAll('tr.clickable'), function (tr) { tr.classList.toggle('selrow', +tr.getAttribute('data-i') === i); });
  }

  function readSchematic(pr) {
    var S = state, Wd = 560, ml = 6, pw = 548, A = pr.ampStart0, B = pr.ampEnd0;
    var x = function (g) { return ml + (g - A) / (B - A) * pw; };
    var dead = 40, o = [];
    var vx = x((S.V.start0 + S.V.end0) / 2);
    // ileri okuma
    o.push('<text x="' + ml + '" y="14">İleri okuma (F primer ile) → varyant ' + pr.varFromF + '. bazda</text>');
    o.push('<rect x="' + x(pr.left.end0) + '" y="22" width="' + (x(B) - x(pr.left.end0)) + '" height="10" fill="var(--fwd-bg)"/>');
    o.push('<rect x="' + x(pr.left.end0) + '" y="22" width="' + (x(pr.left.end0 + dead) - x(pr.left.end0)) + '" height="10" fill="var(--rep)" opacity=".6"><title>İlk ~40 baz genellikle okunamaz</title></rect>');
    o.push('<rect x="' + x(A) + '" y="20" width="' + (x(pr.left.end0) - x(A)) + '" height="14" fill="var(--fwd)"/>');
    // geri okuma
    o.push('<text x="' + ml + '" y="58">← Geri okuma (R primer ile) → varyant ' + pr.varFromR + '. bazda</text>');
    o.push('<rect x="' + x(A) + '" y="66" width="' + (x(pr.right.start0) - x(A)) + '" height="10" fill="var(--rev-bg)"/>');
    o.push('<rect x="' + x(pr.right.start0 - dead) + '" y="66" width="' + (x(pr.right.start0) - x(pr.right.start0 - dead)) + '" height="10" fill="var(--rep)" opacity=".6"/>');
    o.push('<rect x="' + x(pr.right.start0) + '" y="64" width="' + (x(B) - x(pr.right.start0)) + '" height="14" fill="var(--rev)"/>');
    o.push('<line x1="' + vx + '" x2="' + vx + '" y1="18" y2="82" stroke="var(--var)" stroke-width="2.5"/>');
    o.push('<text x="' + ml + '" y="98">1</text><text x="' + (Wd - ml) + '" y="98" text-anchor="end">' + pr.size + ' bp</text>');
    return '<div class="svgbox"><svg class="rs" viewBox="0 0 ' + Wd + ' 104" role="img" aria-label="Sanger okuma şeması">' + o.join('') + '</svg></div>';
  }

  function seqView(pr) {
    var S = state, T0 = S.rs, A = pr.ampStart0, B = pr.ampEnd0;
    var cls = [];
    for (var g = A; g < B; g++) {
      var c = [];
      if (g >= pr.left.start0 && g < pr.left.end0) c.push('s-f');
      else if (g >= pr.right.start0 && g < pr.right.end0) c.push('s-r');
      if (g >= S.V.start0 && g < S.V.end0) c.push('s-v');
      if (S.snps.some(function (s) { return g >= s.start0 && g < s.end0; })) c.push('s-snp');
      if (S.tx && !S.tx.exons.some(function (e) { return g >= e.start0 && g < e.end0; })) c.push('s-intron');
      cls.push(c.join(' '));
    }
    var lines = [], width = 60;
    for (var i = 0; i < B - A; i += width) {
      var line = '<span class="pos">' + String(i + 1).padStart(4, ' ') + '  </span>';
      var run = '', runCls = null;
      for (var k = i; k < Math.min(i + width, B - A); k++) {
        var base = S.tpl[A - T0 + k];
        if (cls[k].indexOf('s-intron') >= 0) base = base.toLowerCase();
        if (cls[k] !== runCls) { if (run) line += runCls ? '<span class="' + runCls + '">' + run + '</span>' : run; run = ''; runCls = cls[k]; }
        run += base;
        if ((k + 1) % 10 === 0 && k + 1 < Math.min(i + width, B - A)) {
          line += runCls ? '<span class="' + runCls + '">' + run + '</span>' : run; run = ''; line += ' ';
        }
      }
      if (run) line += runCls ? '<span class="' + runCls + '">' + run + '</span>' : run;
      lines.push(line);
    }
    return '<div class="seqview">' + lines.join('\n') + '</div>' +
      '<div class="legend"><span><span class="s-f mono">ACGT</span> ileri primer</span><span><span class="s-r mono">ACGT</span> geri primer (bağlandığı üst iplik)</span><span><span class="s-v mono">A</span> varyant (REF)</span><span><span class="s-snp mono">A</span> yaygın SNP</span><span><span class="mono s-intron">acgt</span> intron · <span class="mono">ACGT</span> ekzon</span></div>';
  }

  function renderDetail() {
    var S = state, pr = S.pairs[S.sel];
    var icon = { ok: '✓', warn: '⚠', err: '✗', man: '☐' };
    var checks = '<ul class="checks">' + pr.checks.map(function (c) { return '<li><span class="i-' + c.kind + '">' + icon[c.kind] + '</span><span>' + esc(c.text) + '</span></li>'; }).join('') + '</ul>';
    var prow = function (x, side) {
      return '<tr><td class="mono" style="color:var(' + (side === 'F' ? '--fwd' : '--rev') + ')">' + esc(primerName(pr, side)) + '</td><td class="seq">' + x.seq + ' <button class="small noprint copy" data-c="' + x.seq + '">kopyala</button></td>' +
        '<td class="num">' + x.len + '</td><td class="num">' + fmt(x.tm) + '</td><td class="num">' + fmt(x.gc, 0) + '</td><td class="num">' + fmt(x.hairpin) + '</td><td class="num">' + fmt(x.selfDimer) + '</td><td class="num">' + fmt(x.endDimer) + '</td><td class="num">' + fmt(x.endStab) + '</td>' +
        '<td class="mono">' + S.V.chrom + ':' + comma(x.start0 + 1) + '-' + comma(x.end0) + ' (' + (side === 'F' ? '+' : '−') + ')</td></tr>';
    };
    var het = E.renderDuplex(pr.left.seq, pr.right.seq, pr.heteroAln);
    var sdF = E.renderDuplex(pr.left.seq, pr.left.seq, pr.left.selfDimerAln);
    var sdR = E.renderDuplex(pr.right.seq, pr.right.seq, pr.right.selfDimerAln);
    var html = '' +
      '<div class="row"><h2 style="margin:0">Çift ' + pr.idx + ' · ' + pr.size + ' bp</h2><span>' + (pr.tier ? '<span class="badge b-info" title="' + esc(pr.tierLabel) + '">gevşetilmiş kriter</span> ' : '') + '<span class="badge b-info">ceza puanı ' + fmt(pr.penalty, 2) + '</span></span></div>' +
      (pr.tier ? '<div class="alert info">' + esc(pr.tierLabel) + '</div>' : '') +
      '<div class="tablewrap" style="margin-top:12px"><table><thead><tr><th>Ad</th><th>Dizi (5\'→3\')</th><th class="num">Uz.</th><th class="num">Tm °C</th><th class="num">GC%</th><th class="num">Hairpin ΔG</th><th class="num">Self-dimer ΔG</th><th class="num">3\' dimer ΔG</th><th class="num">3\' stab.</th><th>Konum</th></tr></thead><tbody>' +
      prow(pr.left, 'F') + prow(pr.right, 'R') + '</tbody></table></div>' +
      '<div class="links noprint">' +
      '<a target="_blank" rel="noopener" href="' + isPcrUrl(pr) + '">UCSC In-Silico PCR ↗</a>' +
      '<a target="_blank" rel="noopener" href="' + blatUrl(pr) + '">UCSC BLAT (F + R) ↗</a>' +
      '<a target="_blank" rel="noopener" href="' + primerBlastUrl(pr) + '">NCBI Primer-BLAST ↗</a>' +
      '<a target="_blank" rel="noopener" href="' + ucscBrowserUrl(pr.ampStart0 - 50, pr.ampEnd0 + 50) + '">Bu çifti UCSC\'de göster ↗</a>' +
      '<button class="small copy" data-c="' + primerName(pr, 'F') + '\t' + pr.left.seq + '\n' + primerName(pr, 'R') + '\t' + pr.right.seq + '">Çifti kopyala</button>' +
      '</div>' +
      '<div class="two" style="margin-top:18px"><div><h3>Kontrol listesi</h3><div style="margin-top:8px">' + checks + '</div></div>' +
      '<div><h3>Sanger okuma planı</h3>' + readSchematic(pr) +
      '<p class="hint">Gri bölge primerden sonraki ilk ~40 baz; Sanger izinde bu kısım genellikle okunamaz. Heterozigot indellerde iz varyanttan sonra çift pik verir; diğer yönden okuma ile teyit edin.</p>' +
      '<h3 style="margin-top:14px">En stabil dimer hizalamaları</h3>' +
      '<div class="muted" style="font-size:12px;margin-top:6px">F × R heterodimer (ΔG ' + fmt(pr.heteroDimer) + ')</div><pre class="aln">' + esc(het || 'anlamlı dimer yok') + '</pre>' +
      '<div class="muted" style="font-size:12px;margin-top:6px">F self-dimer (ΔG ' + fmt(pr.left.selfDimer) + ')</div><pre class="aln">' + esc(sdF || 'anlamlı dimer yok') + '</pre>' +
      '<div class="muted" style="font-size:12px;margin-top:6px">R self-dimer (ΔG ' + fmt(pr.right.selfDimer) + ')</div><pre class="aln">' + esc(sdR || 'anlamlı dimer yok') + '</pre>' +
      '</div></div>' +
      '<h3 style="margin-top:18px">Amplikon dizisi (' + pr.size + ' bp)</h3><div style="margin-top:8px">' + seqView(pr) + '</div>' +
      (pr.ampliconSnps.length ? '<p class="hint">Amplikon içindeki yaygın SNP\'ler (segregasyonda bilgilendirici olabilir): ' + pr.ampliconSnps.map(function (s) { return esc(s.name) + (s.maf ? ' (MAF ≤ ' + s.maf.toFixed(2) + ')' : ''); }).join(', ') + '</p>' : '');
    $('detail').innerHTML = html;
    bindCopy($('detail'));
  }

  function renderUcsc() {
    var S = state, pr = S.pairs[S.sel];
    var a = pr.ampStart0 - 60, b = pr.ampEnd0 + 60;
    var src = UCSC + '/hgRenderTracks?db=' + S.build + '&position=' + S.V.chrom + ':' + (a + 1) + '-' + b + '&pix=1000&hideTracks=1&ncbiRefSeqSelect=pack&dbSnp155Common=pack&rmsk=dense&simpleRepeat=dense&cons100way=dense&gc5BaseBw=dense';
    var img = $('ucscImg');
    img.onerror = function () { img.alt = 'UCSC görüntüsü yüklenemedi; "UCSC\'de aç" bağlantısını kullanın.'; };
    img.src = src;
    $('ucscLinks').innerHTML = '<a target="_blank" rel="noopener" href="' + ucscBrowserUrl(a, b) + '">UCSC\'de aç (primerler özel iz olarak) ↗</a>' +
      '<a target="_blank" rel="noopener" href="' + isPcrUrl(pr) + '">In-Silico PCR ↗</a>';
  }

  /* ---------------- Bağlantılar ---------------- */
  function customTrack() {
    var S = state, L = [];
    L.push('track name="Sanger_primerleri" description="Sanger primer çiftleri" visibility=pack itemRgb=On');
    L.push([S.V.chrom, S.V.start0, Math.max(S.V.end0, S.V.start0 + 1), 'Varyant', 0, '.', S.V.start0, Math.max(S.V.end0, S.V.start0 + 1), '194,65,12'].join('\t'));
    S.pairs.forEach(function (pr) {
      L.push([S.V.chrom, pr.left.start0, pr.left.end0, primerName(pr, 'F'), 0, '+', pr.left.start0, pr.left.end0, '45,95,78'].join('\t'));
      L.push([S.V.chrom, pr.right.start0, pr.right.end0, primerName(pr, 'R'), 0, '-', pr.right.start0, pr.right.end0, '109,40,217'].join('\t'));
    });
    L.push('track name="Amplikonlar" description="Sanger amplikonları" visibility=pack');
    S.pairs.forEach(function (pr) { L.push([S.V.chrom, pr.ampStart0, pr.ampEnd0, 'Cift' + pr.idx + '_' + pr.size + 'bp'].join('\t')); });
    return L.join('\n');
  }
  function ucscBrowserUrl(a, b) {
    var S = state;
    return UCSC + '/hgTracks?db=' + S.build + '&position=' + encodeURIComponent(S.V.chrom + ':' + (Math.max(0, a) + 1) + '-' + b) + '&hgct_customText=' + encodeURIComponent(customTrack());
  }
  function isPcrUrl(pr) {
    return UCSC + '/hgPcr?db=' + state.build + '&wp_target=genome&wp_f=' + pr.left.seq + '&wp_r=' + pr.right.seq + '&wp_size=4000&wp_perfect=15&wp_good=15&boolshad.wp_flipReverse=0&Submit=submit';
  }
  function blatUrl(pr) {
    return UCSC + '/hgBlat?db=' + state.build + '&type=DNA&sort=query%2Cscore&output=hyperlink&userSeq=' + encodeURIComponent('>F\n' + pr.left.seq + '\n>R\n' + pr.right.seq) + '&Submit=submit';
  }
  function primerBlastUrl(pr) {
    return 'https://www.ncbi.nlm.nih.gov/tools/primer-blast/index.cgi?LINK_LOC=bookmark&PRIMER_LEFT_INPUT=' + pr.left.seq + '&PRIMER_RIGHT_INPUT=' + pr.right.seq + '&PRIMER_PRODUCT_MAX=4000&ORGANISM=Homo%20sapiens&PRIMER_SPECIFICITY_DATABASE=refseq_representative_genomes&SEARCH_SPECIFIC_PRIMER=on';
  }

  /* ---------------- Dışa aktarma ---------------- */
  function orderRows() {
    var S = state, m13 = $('m13').checked, rows = [['Ad', 'Dizi (5\'-3\')', 'Uzunluk', 'Tm (°C)', 'GC (%)', 'Ürün (bp)', 'Genomik konum (' + S.build + ')', 'Not']];
    S.pairs.forEach(function (pr) {
      [['F', pr.left, M13F], ['R', pr.right, M13R]].forEach(function (x) {
        var seq = m13 ? x[2] + x[1].seq : x[1].seq;
        rows.push([primerName(pr, x[0]) + (m13 ? '_M13' : ''), seq, seq.length, fmt(x[1].tm), fmt(x[1].gc, 0), pr.size + (m13 ? '+' + (M13F.length + M13R.length) : ''), S.V.chrom + ':' + (x[1].start0 + 1) + '-' + x[1].end0, (S.V.hgvsC || S.V.chrom + ':' + S.V.pos) + (pr.tier ? ' (gevşetilmiş)' : '')]);
      });
    });
    return rows;
  }
  function bindCopy(root) {
    Array.prototype.forEach.call(root.querySelectorAll('button.copy'), function (b) {
      b.addEventListener('click', function (e) { e.stopPropagation(); copyText(b.getAttribute('data-c').replace(/\\t/g, '\t')); });
    });
  }
  function copyText(t) {
    var done = function () { $('copyMsg').textContent = 'Kopyalandı'; setTimeout(function () { $('copyMsg').textContent = ''; }, 1600); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(done, function () { fallbackCopy(t); done(); });
    else { fallbackCopy(t); done(); }
  }
  function fallbackCopy(t) { var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) { /* yok */ } ta.remove(); }

  /* ---------------- Başlangıç ---------------- */
  function saveInputs() {
    try { localStorage.setItem('sangerPrimer', JSON.stringify({ g: $('gene').value, v: $('variant').value, b: $('build').value })); } catch (e) { /* yok */ }
  }
  function loadInputs() {
    try { var d = JSON.parse(localStorage.getItem('sangerPrimer') || 'null'); if (d) { $('gene').value = d.g || ''; $('variant').value = d.v || ''; $('build').value = d.b || 'hg38'; } } catch (e) { /* yok */ }
  }

  document.addEventListener('DOMContentLoaded', function () {
    loadInputs();
    // URL parametreleri: ?gene=CFTR&variant=c.1521_1523del&build=hg38
    var qs = new URLSearchParams(location.search);
    if (qs.get('gene')) $('gene').value = qs.get('gene');
    if (qs.get('variant')) $('variant').value = qs.get('variant');
    if (qs.get('build')) $('build').value = qs.get('build');
    $('form').addEventListener('submit', run);
    Array.prototype.forEach.call(document.querySelectorAll('.chip'), function (c) {
      c.addEventListener('click', function () { $('gene').value = c.getAttribute('data-g'); $('variant').value = c.getAttribute('data-v'); run(); });
    });
    $('copyAll').addEventListener('click', function () { copyText(orderRows().map(function (r) { return r.join('\t'); }).join('\n')); });
    $('dlTsv').addEventListener('click', function () {
      var blob = new Blob(['﻿' + orderRows().map(function (r) { return r.join('\t'); }).join('\n')], { type: 'text/tab-separated-values;charset=utf-8' });
      var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = state.gene + '_sanger_primerleri.tsv'; a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
    });
    $('printBtn').addEventListener('click', function () { window.print(); });
    $('themeBtn').addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      var dark = cur ? cur === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', dark ? 'light' : 'dark');
    });
    if (qs.get('variant')) run();
  });
})();
