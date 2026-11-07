/* Kesim noktasını veriden bulma: BAM kesiti (yerel) ve IGV ekran görüntüsü (Claude ile) */
(function () {
  'use strict';
  var BT = window.BamTools, U = null;
  var $ = function (id) { return document.getElementById(id); };
  var TYPES = { DEL: 'Delesyon', DUP: 'Duplikasyon', INV: 'İnversiyon', TRA: 'Translokasyon' };
  var SDK_URL = 'https://cdn.jsdelivr.net/npm/@anthropic-ai/sdk@1.0.0/+esm';
  var KEY_STORE = 'sangerAnthropicKey';
  var bamState = null, imgState = null;

  function esc(x) { return U.esc(x); }
  function comma(x) { return U.comma(x); }
  function bp(n) {
    if (n == null) return '–';
    n = Math.abs(n);
    if (n < 1000) return n + ' bp';
    if (n < 1e6) return (n / 1000).toFixed(n < 10000 ? 2 : 1) + ' kb';
    return (n / 1e6).toFixed(2) + ' Mb';
  }
  function setStatus(id, kind, html) { $(id).innerHTML = html ? '<div class="alert ' + kind + '">' + html + '</div>' : ''; }

  /* =====================================================================
   * Ortak: adayı yapısal varyant formuna aktar ve tasarımı başlat
   * c = { type, chrom, a1, b1, chrom2, a2, b2, exact, zyg, build }
   *   a/b: 0-tabanlı sınır koordinatlarıyla kesim noktası penceresi (kesinse a = b)
   * ===================================================================== */
  function useCandidate(c) {
    var chr1 = BT.ucscChrom(c.chrom), chr2 = BT.ucscChrom(c.chrom2 || c.chrom);
    $('svType').value = c.type;
    var m1 = Math.round((c.a1 + c.b1) / 2), m2 = Math.round((c.a2 + c.b2) / 2);
    var unc = Math.max(c.b1 - c.a1, c.b2 - c.a2) / 2;
    if (c.type === 'TRA') {
      $('svRegion').value = chr1 + ':' + m1;
      $('svRegionB').value = chr2 + ':' + m2;
    } else {
      var s = Math.min(m1, m2), e = Math.max(m1, m2);
      $('svRegion').value = chr1 + ':' + (s + 1) + '-' + e;
    }
    if (c.exact && unc <= 2) $('svMode').value = 'exact';
    else { $('svMode').value = 'manual'; $('svUnc').value = Math.max(25, Math.ceil(unc / 25) * 25); }
    $('svZyg').value = /^hom/.test(c.zyg || '') ? 'hom' : 'het';
    if (c.build) $('svBuild').value = c.build;
    $('svType').dispatchEvent(new Event('change'));
    $('svMode').dispatchEvent(new Event('change'));
    $('svFormCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
    setTimeout(function () { $('svForm').requestSubmit(); }, 350);
  }

  /* =====================================================================
   * BAM kesiti
   * ===================================================================== */
  function guessBuild(refs) {
    for (var i = 0; i < refs.length; i++) {
      var r = refs[i];
      if (/^(chr)?1$/.test(r.name)) return r.len === 248956422 ? 'hg38' : r.len === 249250621 ? 'hg19' : null;
    }
    return null;
  }

  async function runBam() {
    U = window.PrimerUI;
    var files = Array.prototype.slice.call($('bamFiles').files || []);
    var bam = files.filter(function (f) { return /\.bam$/i.test(f.name); })[0];
    var bai = files.filter(function (f) { return /\.bai$/i.test(f.name); })[0];
    $('bamOut').innerHTML = '';
    if (!bam) { setStatus('bamStatus', 'err', 'Bir .bam dosyası seçin (isteğe bağlı olarak aynı dosyanın .bai indeksiyle birlikte).'); return; }
    var region = $('bamRegion').value.trim();
    if (!region && bam.size > 300e6) { setStatus('bamStatus', 'err', 'Büyük BAM dosyası için .bai indeksini de seçin ve bölge girin.'); return; }
    $('bamGo').disabled = true;
    setStatus('bamStatus', 'info', 'Okunuyor: ' + esc(bam.name) + (bai ? ' + indeks' : '') + ' (' + (Math.round(bam.size / 1e5) / 10) + ' MB). Dosya bilgisayarınızdan çıkmaz.');
    try {
      var t0 = performance.now();
      var baiBuf = bai ? await bai.arrayBuffer() : null;
      var res = await BT.readBam(BT.fileSource(bam), baiBuf, region || null, null, { maxReads: 600000 });
      var reads = res.reads;
      var reg = res.region;
      if (!reg) {
        // bölge verilmediyse: okumaların en yoğun olduğu kromozom ve kapsadığı aralık
        var cnt = {};
        reads.forEach(function (r) { if (r.refID >= 0 && !(r.flag & 4)) cnt[r.refID] = (cnt[r.refID] || 0) + 1; });
        var rid = Object.keys(cnt).sort(function (a, b) { return cnt[b] - cnt[a]; })[0];
        if (rid == null) throw new Error('Dosyada hizalanmış okuma yok.');
        rid = +rid;
        var rr = reads.filter(function (r) { return r.refID === rid && !(r.flag & 4); });
        var s = Math.min.apply(null, rr.map(function (r) { return r.pos; })), e = Math.max.apply(null, rr.map(function (r) { return r.end; }));
        reg = { refID: rid, chrom: res.header.refs[rid].name, start: s, end: e };
        if (e - s > 2000000) throw new Error('Kesit 2 Mb\'den geniş (' + bp(e - s) + '). Bölge girerek daraltın.');
      }
      var A = BT.analyze(reads, reg, { minMapq: +$('bamMapq').value || 20, minSupport: +$('bamMin').value || 3 });
      var build = guessBuild(res.header.refs);
      bamState = { A: A, region: reg, build: build, name: bam.name, ms: Math.round(performance.now() - t0), mode: res.mode, n: reads.length };
      setStatus('bamStatus', '', '');
      renderBam();
    } catch (err) {
      setStatus('bamStatus', 'err', esc(err.message || String(err)));
      if (window.console) console.warn(err);
    } finally {
      $('bamGo').disabled = false;
    }
  }

  function renderBam() {
    var S = bamState, A = S.A, R = S.region;
    var cands = A.candidates;
    var html = '<div class="row"><h3>' + esc(S.name) + ' · ' + esc(R.chrom) + ':' + comma(R.start + 1) + '-' + comma(R.end) + '</h3>' +
      '<span>' + (S.build ? '<span class="badge b-info">' + S.build + ' (başlıktan)</span> ' : '') + '<span class="badge b-info">' + comma(S.n) + ' okuma · ' + (S.mode === 'indexed' ? 'indeksli okuma' : 'tam dosya') + ' · ' + S.ms + ' ms</span></span></div>';
    html += '<p class="hint">Kapsam medyanı ' + A.coverage.median + '× · okuma uzunluğu ' + A.readLen + ' · insert medyanı ' + (A.insert.paired ? A.insert.median + ' bp (anormal eşiği ' + A.insert.threshold + ' bp)' : 'çift uçlu veri yok') +
      (A.coverage.targeted ? ' · hedefli veri (WES/panel) görünümü: kapsam tabanlı arama yapılmadı' : '') + '</p>';
    html += plot(A, R, cands);
    if (!cands.length) {
      html += '<div class="alert warn">Bu bölgede kesim noktası kanıtı bulunamadı. Bölgeyi kesim noktalarını içerecek şekilde genişletin; WES verisinde kesim noktası intronda ise BAM\'de görünmeyebilir. Minimum destek değerini düşürmeyi deneyebilirsiniz.</div>';
    } else {
      html += '<div class="tablewrap" style="margin-top:10px"><table><thead><tr><th>#</th><th>Tip</th><th>Kesim noktası 1</th><th>Kesim noktası 2</th><th class="num">Boyut</th><th>Destek</th><th>Doz / AF</th><th>Güven</th><th></th></tr></thead><tbody>' +
        cands.map(function (c, i) {
          var sp = c.support;
          var sup = [sp.split ? sp.split + ' bölünmüş' : '', sp.disc ? sp.disc + ' çift' : '', (sp.clip1 || sp.clip2) ? 'kırpma ' + sp.clip1 + '/' + sp.clip2 : ''].filter(Boolean).join(' · ') || c.source;
          var dz = (c.depthRatio != null ? 'oran ' + c.depthRatio.toFixed(2) : '') + (c.af != null ? (c.depthRatio != null ? ' · ' : '') + 'AF ' + c.af.toFixed(2) : '');
          var conf = { 'yüksek': 'b-ok', orta: 'b-warn', 'düşük': 'b-err' }[c.confidence] || 'b-info';
          return '<tr><td>' + (i + 1) + '</td><td><b>' + TYPES[c.type] + '</b><div class="small muted">' + esc(c.source) + '</div></td><td class="mono small">' + bpTxt(c.bp1) + '</td><td class="mono small">' + bpTxt(c.bp2) + '</td><td class="num">' + (c.size != null ? bp(c.size) : '–') + '</td><td class="small">' + esc(sup) + '</td><td class="small">' + esc(dz || '–') + '<div>' + esc(c.zyg || '') + '</div></td><td><span class="badge ' + conf + '">' + esc(c.confidence) + '</span></td><td><button class="small primary usebam" data-i="' + i + '">Bu adayı kullan</button></td></tr>' +
            (c.consensus1 || c.consensus2 ? '<tr class="sub"><td></td><td colspan="8" class="small muted">Kırpılmış dizi uzlaşısı: ' + [c.consensus1, c.consensus2].filter(function (x) { return x && x.replace(/N/g, '').length >= 20; }).map(function (x) {
              return '<span class="mono">' + esc(x) + '</span> <a target="_blank" rel="noopener" href="' + U.UCSC + '/hgBlat?db=' + (S.build || $('svBuild').value) + '&type=DNA&userSeq=' + x.replace(/N/g, '') + '&Submit=submit">BLAT ↗</a>';
            }).join(' · ') + '</td></tr>' : '');
        }).join('') + '</tbody></table></div>';
      html += '<p class="hint">"Bu adayı kullan" kesim noktalarını aşağıdaki forma aktarır ve test önerisi ile primer tasarımını başlatır. Koordinatlar ' + (S.build || 'BAM\'in genom sürümü') + ' üzerindedir; formdaki genom seçimi buna göre ayarlanır.</p>';
    }
    $('bamOut').innerHTML = html;
    Array.prototype.forEach.call($('bamOut').querySelectorAll('.usebam'), function (b) {
      b.addEventListener('click', function () {
        var c = cands[+b.getAttribute('data-i')];
        var w = function (x) { return x.exact ? [x.pos, x.pos] : x.window; };
        var w1 = w(c.bp1), w2 = w(c.bp2);
        useCandidate({ type: c.type, chrom: c.bp1.chrom, a1: w1[0], b1: w1[1], chrom2: c.bp2.chrom, a2: w2[0], b2: w2[1], exact: c.bp1.exact && c.bp2.exact, zyg: c.zyg, build: S.build });
      });
    });
  }
  function bpTxt(b) {
    var c = BT.ucscChrom(b.chrom);
    return b.exact ? esc(c) + ':' + comma(b.pos) + ' <span class="badge b-ok">kesin</span>' : esc(c) + ':' + comma(b.window[0]) + '–' + comma(b.window[1]) + ' <span class="badge b-warn">± ' + bp(Math.round((b.window[1] - b.window[0]) / 2)) + '</span>';
  }

  function plot(A, R, cands) {
    var W = 1000, ml = 60, mr = 10, pw = W - ml - mr, o = [];
    var L = R.end - R.start;
    var x = function (g) { return ml + (g - R.start) / L * pw; };
    var prof = A.coverage.profile, maxC = Math.max(1, Math.max.apply(null, prof) * 1.05);
    var y0 = 20, ch = 90;
    // kapsam
    var pts = prof.map(function (v, i) { return (ml + i / prof.length * pw).toFixed(1) + ',' + (y0 + ch - v / maxC * ch).toFixed(1); });
    o.push('<text x="4" y="' + (y0 + 12) + '">Kapsam</text>');
    o.push('<path d="M' + ml + ',' + (y0 + ch) + ' L' + pts.join(' L') + ' L' + (ml + pw) + ',' + (y0 + ch) + ' Z" fill="var(--rep)" opacity=".7"/>');
    if (A.coverage.median) { var ym = y0 + ch - A.coverage.median / maxC * ch; o.push('<line x1="' + ml + '" x2="' + (ml + pw) + '" y1="' + ym + '" y2="' + ym + '" stroke="var(--ink-3)" stroke-dasharray="4 3"/><text x="4" y="' + (ym + 4) + '" class="small">' + A.coverage.median + '×</text>'); }
    // cetvel
    var step = [100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000].filter(function (s) { return L / s <= 8; })[0] || 1000000;
    for (var t = Math.ceil(R.start / step) * step; t <= R.end; t += step) o.push('<line x1="' + x(t) + '" x2="' + x(t) + '" y1="' + (y0 + ch) + '" y2="' + (y0 + ch + 5) + '" stroke="var(--ink-3)"/><text x="' + x(t) + '" y="' + (y0 + ch + 16) + '" text-anchor="middle">' + comma(t) + '</text>');
    // kırpma kümeleri
    var yc = y0 + ch + 30;
    o.push('<text x="4" y="' + (yc + 10) + '">Kırpma</text>');
    var maxK = Math.max(1, Math.max.apply(null, A.clips.map(function (c) { return c.count; }).concat([1])));
    A.clips.forEach(function (c) {
      if (c.pos < R.start || c.pos > R.end) return;
      var h = 4 + c.count / maxK * 18, xx = x(c.pos), col = c.side === 'R' ? 'var(--fwd)' : 'var(--rev)';
      o.push('<rect x="' + (xx - 1.5) + '" y="' + (yc + 22 - h) + '" width="3" height="' + h + '" fill="' + col + '"><title>' + (c.side === 'R' ? 'sağdan' : 'soldan') + ' kırpılmış ' + c.count + ' okuma @ ' + comma(c.pos) + '</title></rect>');
    });
    // anormal çiftler (yaylar)
    var ya = yc + 34, ah = 70;
    o.push('<text x="4" y="' + (ya + 12) + '">Anormal</text><text x="4" y="' + (ya + 24) + '">çiftler</text>');
    var colT = { DEL: 'var(--danger)', DUP: 'var(--accent)', INV: 'var(--info)', TRA: 'var(--warn)' };
    Object.keys(A.discordant).forEach(function (t) {
      A.discordant[t].forEach(function (cl) {
        cl.pairs.forEach(function (p) {
          var a = x(Math.max(R.start, p[0])), b = p[2] != null && t !== 'TRA' ? x(Math.min(R.end, Math.max(R.start, p[2]))) : null;
          if (b == null) { o.push('<circle cx="' + a + '" cy="' + (ya + ah - 4) + '" r="2.5" fill="' + colT[t] + '" opacity=".7"><title>' + t + ' eş: ' + esc(cl.chromB) + ':' + comma(p[2]) + '</title></circle>'); return; }
          var mid = (a + b) / 2, hh = Math.min(ah - 6, Math.abs(b - a) / 2 + 6);
          o.push('<path d="M' + a + ' ' + (ya + ah) + ' Q' + mid + ' ' + (ya + ah - hh * 2) + ' ' + b + ' ' + (ya + ah) + '" fill="none" stroke="' + colT[t] + '" stroke-width="1" opacity=".55"/>');
        });
      });
    });
    // aday kesim noktaları
    var yb = ya + ah + 8;
    cands.slice(0, 4).forEach(function (c, i) {
      [c.bp1, c.bp2].forEach(function (b, k) {
        if (b.chrom !== R.chrom || b.pos < R.start || b.pos > R.end) return;
        if (b.exact) o.push('<line x1="' + x(b.pos) + '" x2="' + x(b.pos) + '" y1="' + y0 + '" y2="' + yb + '" stroke="var(--var)" stroke-width="1.5" stroke-dasharray="' + (i ? '3 3' : '0') + '"/>');
        else o.push('<rect x="' + x(b.window[0]) + '" y="' + y0 + '" width="' + Math.max(2, x(b.window[1]) - x(b.window[0])) + '" height="' + (yb - y0) + '" fill="var(--var)" opacity=".12"/>');
        o.push('<text x="' + x(b.pos) + '" y="' + (yb + 12) + '" text-anchor="middle" class="bl">' + (i + 1) + (k ? 'b' : 'a') + '</text>');
      });
    });
    var H = yb + 20;
    return '<div class="svgbox"><svg class="evid" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="BAM kanıt grafiği">' + o.join('') + '</svg></div>' +
      '<div class="legend"><span><i style="background:var(--rep)"></i>Kapsam</span><span><i style="background:var(--fwd)"></i>Sağdan kırpılmış</span><span><i style="background:var(--rev)"></i>Soldan kırpılmış</span>' +
      '<span><i style="background:var(--danger)"></i>Delesyon yönlü çift</span><span><i style="background:var(--accent)"></i>Duplikasyon yönlü</span><span><i style="background:var(--info)"></i>İnversiyon yönlü</span><span><i style="background:var(--warn)"></i>Farklı kromozom</span><span><i style="background:var(--var)"></i>Aday kesim noktası</span></div>';
  }

  /* =====================================================================
   * IGV ekran görüntüsü (Claude ile)
   * ===================================================================== */
  var SCHEMA = {
    type: 'object', additionalProperties: false,
    required: ['locus_text', 'genome_build', 'view', 'data_type', 'observations', 'candidates', 'limitations'],
    properties: {
      locus_text: { type: 'string' },
      genome_build: { type: 'string', enum: ['hg38', 'hg19', 'bilinmiyor'] },
      view: {
        type: 'object', additionalProperties: false, required: ['chrom', 'start', 'end', 'bp_per_pixel'],
        properties: { chrom: { type: 'string' }, start: { type: 'integer' }, end: { type: 'integer' }, bp_per_pixel: { type: 'number' } }
      },
      data_type: { type: 'string', enum: ['WGS', 'WES/panel', 'uzun okuma', 'bilinmiyor'] },
      observations: { type: 'array', items: { type: 'string' } },
      candidates: {
        type: 'array',
        items: {
          type: 'object', additionalProperties: false,
          required: ['type', 'chrom', 'bp1_start', 'bp1_end', 'chrom2', 'bp2_start', 'bp2_end', 'zygosity', 'confidence', 'evidence'],
          properties: {
            type: { type: 'string', enum: ['DEL', 'DUP', 'INV', 'TRA'] },
            chrom: { type: 'string' }, bp1_start: { type: 'integer' }, bp1_end: { type: 'integer' },
            chrom2: { type: 'string' }, bp2_start: { type: 'integer' }, bp2_end: { type: 'integer' },
            zygosity: { type: 'string', enum: ['het', 'hom', 'bilinmiyor'] },
            confidence: { type: 'string', enum: ['yüksek', 'orta', 'düşük'] },
            evidence: { type: 'string' }
          }
        }
      },
      limitations: { type: 'array', items: { type: 'string' } }
    }
  };
  var SYSTEM = [
    'Bir klinik genetik laboratuvarında IGV (Integrative Genomics Viewer) ekran görüntülerini yorumlayan bir uzmansın. Görevin, görüntüdeki yapısal varyant veya CNV kanıtını bulmak ve kesim noktalarını genomik koordinat olarak tahmin etmektir.',
    'Koordinatlar: Konum kutusundaki metni (ör. chr7:117,550,000-117,570,000) ve cetveli oku. Görünen aralığı ve piksel başına baz sayısını hesapla. Kesim noktalarını 1 tabanlı genomik koordinat olarak ver ve her biri için bir aralık (başlangıç-bitiş) belirt. Aralık genişliği en az birkaç piksel karşılığı olmalı; kesim noktası yazılı bir konuma tam hizalı değilse aralığı geniş tut.',
    'IGV görsel kuralları (kullanıcı ayarlarını değiştirmiş olabilir; renk açıklaması görünüyorsa onu kullan): kapsam izi gri sütun grafiğidir; kapsamın yaklaşık yarıya inmesi heterozigot, sıfıra inmesi homozigot delesyon, 1.5 kata çıkması heterozigot duplikasyon düşündürür. Okuma çiftleri insert boyuna göre renklendirildiğinde kırmızı beklenenden uzun insert (delesyon), mavi kısa insert (insersiyon) anlamına gelir. Yönelime göre renklendirmede yeşil RL (tandem duplikasyon), turkuaz/mavi LL ve RR (inversiyon) gösterir. Başka kromozoma eşlenen çiftler o kromozoma özgü renklerle boyanır (translokasyon). Aynı noktada dikey bir çizgi halinde biten, renkli (yumuşak kırpılmış) bazlar kesim noktasını gösterir.',
    'Kurallar: Yalnızca görüntüde gerçekten görülen kanıta dayan; koordinatları uydurma. Bir şeyi okuyamıyorsan bunu limitations alanına yaz. Kanıt yoksa candidates boş bir dizi olsun. Translokasyon dışındaki tiplerde chrom2 alanına chrom ile aynı değeri yaz. Kesim noktası görüntünün dışında kalıyorsa aralığı görüntünün kenarından dışarıya doğru genişlet ve bunu belirt. Bütün açıklamaları Türkçe yaz.'
  ].join('\n\n');

  function loadImageFile(file) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = function () { reject(new Error('Görüntü okunamadı.')); };
      img.src = URL.createObjectURL(file);
    });
  }
  async function setImage(file) {
    if (!file || !/^image\//.test(file.type)) { setStatus('imgStatus', 'err', 'Bir görüntü dosyası seçin (JPG veya PNG).'); return; }
    var img = await loadImageFile(file);
    var maxE = 2576, sc = Math.min(1, maxE / Math.max(img.naturalWidth, img.naturalHeight));
    var cv = $('imgCanvas');
    cv.width = Math.round(img.naturalWidth * sc); cv.height = Math.round(img.naturalHeight * sc);
    imgState = { img: img, rects: [], scale: sc, name: file.name };
    drawImg();
    $('imgWrap').classList.remove('hidden');
    setStatus('imgStatus', 'info', 'Görüntü yüklendi (' + cv.width + '×' + cv.height + ' piksel). Hasta adı, protokol numarası veya örnek kimliği görünüyorsa fareyle üzerinden sürükleyerek karartın.');
  }
  function drawImg() {
    var cv = $('imgCanvas'), ctx = cv.getContext('2d');
    ctx.drawImage(imgState.img, 0, 0, cv.width, cv.height);
    ctx.fillStyle = '#000';
    imgState.rects.forEach(function (r) { ctx.fillRect(r[0], r[1], r[2], r[3]); });
  }
  function bindRedaction() {
    var cv = $('imgCanvas'), start = null;
    function pt(ev) {
      var b = cv.getBoundingClientRect(), p = ev.touches ? ev.touches[0] : ev;
      return [(p.clientX - b.left) / b.width * cv.width, (p.clientY - b.top) / b.height * cv.height];
    }
    function down(ev) { if (!imgState) return; start = pt(ev); ev.preventDefault(); }
    function move(ev) {
      if (!start) return;
      var p = pt(ev); drawImg();
      var ctx = cv.getContext('2d'); ctx.fillStyle = 'rgba(0,0,0,.6)';
      ctx.fillRect(Math.min(start[0], p[0]), Math.min(start[1], p[1]), Math.abs(p[0] - start[0]), Math.abs(p[1] - start[1]));
      ev.preventDefault();
    }
    function up(ev) {
      if (!start) return;
      var p = ev.changedTouches ? pt({ clientX: ev.changedTouches[0].clientX, clientY: ev.changedTouches[0].clientY }) : pt(ev);
      var r = [Math.min(start[0], p[0]), Math.min(start[1], p[1]), Math.abs(p[0] - start[0]), Math.abs(p[1] - start[1])];
      if (r[2] > 3 && r[3] > 3) imgState.rects.push(r);
      start = null; drawImg();
    }
    cv.addEventListener('mousedown', down); cv.addEventListener('mousemove', move); window.addEventListener('mouseup', up);
    cv.addEventListener('touchstart', down, { passive: false }); cv.addEventListener('touchmove', move, { passive: false }); cv.addEventListener('touchend', up);
  }

  async function runImage() {
    U = window.PrimerUI;
    var key = $('imgKey').value.trim();
    $('imgOut').innerHTML = '';
    if (!imgState) { setStatus('imgStatus', 'err', 'Önce bir IGV ekran görüntüsü seçin.'); return; }
    if (!key) { setStatus('imgStatus', 'err', 'Anthropic API anahtarınızı girin.'); return; }
    if (!$('imgConsent').checked) { setStatus('imgStatus', 'err', 'Göndermeden önce görüntüde hasta kimliği bulunmadığını onaylayın.'); return; }
    try { if ($('imgRemember').checked) localStorage.setItem(KEY_STORE, key); else localStorage.removeItem(KEY_STORE); } catch (e) { /* yok */ }
    var model = $('imgModel').value;
    var data = $('imgCanvas').toDataURL('image/jpeg', 0.92).split(',')[1];
    var extra = $('imgNote').value.trim();
    var userText = 'Bu IGV ekran görüntüsündeki yapısal varyant / CNV kanıtını değerlendir ve kesim noktalarını tahmin et.' +
      (extra ? '\n\nKullanıcının verdiği ek bilgi: ' + extra : '') +
      '\n\nFormdaki genom seçimi: ' + $('svBuild').value + '. Görüntüde farklı bir sürüm görülüyorsa onu yaz.';
    $('imgGo').disabled = true;
    setStatus('imgStatus', 'info', 'Görüntü ' + esc(model) + ' modeline gönderildi, yanıt bekleniyor (genellikle 20–90 s)…');
    var t0 = Date.now();
    try {
      var mod = await import(SDK_URL);
      var Anthropic = mod.default || mod.Anthropic;
      var client = new Anthropic({ apiKey: key, dangerouslyAllowBrowser: true });
      var resp = await client.beta.messages.create({
        model: model,
        max_tokens: 16000,
        betas: ['server-side-fallback-2026-07-01'],
        fallbacks: 'default',
        output_config: { effort: 'high', format: { type: 'json_schema', schema: SCHEMA } },
        system: SYSTEM,
        messages: [{ role: 'user', content: [
          { type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: data } },
          { type: 'text', text: userText }
        ] }]
      });
      if (resp.stop_reason === 'refusal') throw new Error('Model isteği yanıtlamadı (güvenlik sınıflandırıcısı' + (resp.stop_details && resp.stop_details.category ? ': ' + resp.stop_details.category : '') + ').');
      if (resp.stop_reason === 'max_tokens') throw new Error('Yanıt uzunluk sınırında kesildi; tekrar deneyin.');
      var text = resp.content.filter(function (b) { return b.type === 'text'; }).map(function (b) { return b.text; }).join('');
      var out;
      try { out = JSON.parse(text); } catch (e) { throw new Error('Yanıt beklenen biçimde değil.'); }
      imgState.result = out;
      imgState.meta = { model: resp.model, sec: Math.round((Date.now() - t0) / 1000), usage: resp.usage };
      setStatus('imgStatus', '', '');
      await renderImage();
    } catch (err) {
      var m = err && err.status === 401 ? 'API anahtarı geçersiz (401).' : err && err.status === 429 ? 'İstek sınırına ulaşıldı (429); biraz sonra tekrar deneyin.' :
        err && err.status === 400 ? 'İstek reddedildi (400): ' + (err.message || '') : (err && err.message) || String(err);
      setStatus('imgStatus', 'err', esc(m));
      if (window.console) console.warn(err);
    } finally {
      $('imgGo').disabled = false;
    }
  }

  async function renderImage() {
    var r = imgState.result, M = imgState.meta;
    var build = r.genome_build === 'hg19' || r.genome_build === 'hg38' ? r.genome_build : $('svBuild').value;
    var html = '<div class="row"><h3>Görüntü yorumu</h3><span class="badge b-info">' + esc(M.model) + ' · ' + M.sec + ' s' +
      (M.usage ? ' · ' + comma(M.usage.input_tokens) + ' + ' + comma(M.usage.output_tokens) + ' token' : '') + '</span></div>';
    html += '<dl class="kv" style="margin-top:8px"><dt>Konum kutusu</dt><dd>' + esc(r.locus_text || '–') + '</dd><dt>Görünen aralık</dt><dd>' +
      esc(r.view.chrom + ':' + comma(r.view.start) + '-' + comma(r.view.end)) + ' (≈ ' + (r.view.bp_per_pixel ? r.view.bp_per_pixel.toFixed(1) : '?') + ' bp/piksel)</dd><dt>Genom / veri</dt><dd>' + esc(r.genome_build + ' · ' + r.data_type) + '</dd></dl>';
    if (r.observations.length) html += '<h3 style="margin-top:10px">Gözlemler</h3><ul class="notes">' + r.observations.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>';
    if (!r.candidates.length) html += '<div class="alert warn">Görüntüde yapısal varyant kanıtı bulunamadı.</div>';
    else {
      html += '<h3 style="margin-top:10px">Adaylar (düzenleyebilirsiniz)</h3>';
      html += r.candidates.map(function (c, i) {
        var conf = { 'yüksek': 'b-ok', orta: 'b-warn', 'düşük': 'b-err' }[c.confidence] || 'b-info';
        return '<div class="pcr imgcand" data-i="' + i + '"><div class="row"><b>' + (i + 1) + '. ' + TYPES[c.type] + '</b><span><span class="badge ' + conf + '">' + esc(c.confidence) + '</span> <span class="badge b-info">' + esc(c.zygosity) + '</span></span></div>' +
          '<p class="small" style="margin:6px 0">' + esc(c.evidence) + '</p>' +
          '<div class="grid g-adv">' +
          '<label>Tip<select class="f-type">' + Object.keys(TYPES).map(function (t) { return '<option value="' + t + '"' + (t === c.type ? ' selected' : '') + '>' + TYPES[t] + '</option>'; }).join('') + '</select></label>' +
          '<label>Kromozom<input class="f-chrom mono" value="' + esc(c.chrom) + '"></label>' +
          '<label>KN1 başlangıç<input class="f-a1 mono" type="number" value="' + c.bp1_start + '"></label>' +
          '<label>KN1 bitiş<input class="f-b1 mono" type="number" value="' + c.bp1_end + '"></label>' +
          '<label>Kromozom 2<input class="f-chrom2 mono" value="' + esc(c.chrom2 || c.chrom) + '"></label>' +
          '<label>KN2 başlangıç<input class="f-a2 mono" type="number" value="' + c.bp2_start + '"></label>' +
          '<label>KN2 bitiş<input class="f-b2 mono" type="number" value="' + c.bp2_end + '"></label>' +
          '</div><div class="genes small muted" style="margin-top:6px"></div>' +
          '<div class="links"><button class="small primary useimg">Bu adayı kullan</button><a target="_blank" rel="noopener" class="ucsclink" href="#">UCSC\'de bölgeyi aç ↗</a></div></div>';
      }).join('');
    }
    if (r.limitations.length) html += '<div class="alert warn"><b>Sınırlamalar:</b> ' + r.limitations.map(esc).join(' · ') + '</div>';
    html += '<p class="hint">Görüntüden okunan koordinatlar ekran çözünürlüğüyle sınırlıdır. Aday, belirsizlik aralığıyla (elle belirsizlik modu) aktarılır. Mümkünse aynı bölgenin BAM kesitiyle kesinleştirin.</p>';
    $('imgOut').innerHTML = html;
    Array.prototype.forEach.call($('imgOut').querySelectorAll('.imgcand'), function (box) {
      var get = function (cls) { return box.querySelector(cls).value; };
      var link = box.querySelector('.ucsclink');
      function refresh() {
        var ch = BT.ucscChrom(get('.f-chrom')), a = +get('.f-a1'), b = +get('.f-b2');
        var s = Math.min(a, b), e = Math.max(+get('.f-b1'), b, a);
        link.href = U.UCSC + '/hgTracks?db=' + build + '&position=' + encodeURIComponent(ch + ':' + Math.max(1, s - 2000) + '-' + (e + 2000));
      }
      refresh();
      box.addEventListener('input', refresh);
      // UCSC ile kontrol: bölgedeki genler
      (async function () {
        try {
          var ch = BT.ucscChrom(get('.f-chrom')), s = Math.min(+get('.f-a1'), +get('.f-a2')), e = Math.max(+get('.f-b1'), +get('.f-b2'));
          if (get('.f-type') === 'TRA') e = +get('.f-b1');
          if (!(e > s) || e - s > 5e6) return;
          var d = await U.getJSON(U.UCSC_API + '/track?genome=' + build + ';chrom=' + ch + ';start=' + Math.max(0, s - 1) + ';end=' + e + ';track=ncbiRefSeqSelect;maxItemsOutput=200', 'UCSC');
          var g = (d.ncbiRefSeqSelect || []).map(function (t) { return t.name2; });
          g = g.filter(function (x, i) { return g.indexOf(x) === i; });
          box.querySelector('.genes').textContent = 'UCSC (' + build + ') bu aralıkta: ' + (g.length ? g.slice(0, 20).join(', ') + (g.length > 20 ? ' …' : '') : 'RefSeq Select geni yok');
          var gene = $('svGene').value.trim().toUpperCase();
          if (gene && g.length && g.indexOf(gene) < 0) box.querySelector('.genes').innerHTML += ' <span class="i-warn">⚠ formdaki gen (' + esc(gene) + ') bu aralıkta değil</span>';
        } catch (e) { /* bilgi amaçlı */ }
      })();
      box.querySelector('.useimg').addEventListener('click', function () {
        var a1 = +get('.f-a1') - 1, b1 = +get('.f-b1'), a2 = +get('.f-a2') - 1, b2 = +get('.f-b2');
        useCandidate({ type: get('.f-type'), chrom: get('.f-chrom'), a1: Math.min(a1, b1), b1: Math.max(a1, b1), chrom2: get('.f-chrom2'), a2: Math.min(a2, b2), b2: Math.max(a2, b2), exact: false,
          zyg: imgState.result.candidates[+box.getAttribute('data-i')].zygosity, build: build });
      });
    });
  }

  /* ---------------- başlangıç ---------------- */
  document.addEventListener('DOMContentLoaded', function () {
    U = window.PrimerUI;
    if (!$('evBam')) return;
    function tab(which) {
      $('evTabBam').classList.toggle('on', which === 'bam'); $('evTabImg').classList.toggle('on', which === 'img');
      $('evBam').classList.toggle('hidden', which !== 'bam'); $('evImg').classList.toggle('hidden', which !== 'img');
    }
    $('evTabBam').addEventListener('click', function () { tab('bam'); });
    $('evTabImg').addEventListener('click', function () { tab('img'); });
    $('bamGo').addEventListener('click', runBam);
    $('imgFile').addEventListener('change', function () { if (this.files[0]) setImage(this.files[0]); });
    document.addEventListener('paste', function (ev) {
      if ($('evImg').classList.contains('hidden')) return;
      var it = Array.prototype.slice.call((ev.clipboardData || {}).items || []).filter(function (i) { return /^image\//.test(i.type); })[0];
      if (it) setImage(it.getAsFile());
    });
    $('imgUndo').addEventListener('click', function () { if (imgState) { imgState.rects.pop(); drawImg(); } });
    $('imgClear').addEventListener('click', function () { if (imgState) { imgState.rects = []; drawImg(); } });
    $('imgGo').addEventListener('click', runImage);
    try { var k = localStorage.getItem(KEY_STORE); if (k) { $('imgKey').value = k; $('imgRemember').checked = true; } } catch (e) { /* yok */ }
    bindRedaction();
  });
})();
