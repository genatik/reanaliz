/*
 * BAM / BAI okuyucu ve yapısal varyant kanıt analizi
 * ---------------------------------------------------------------
 * - Tamamen istemci tarafında çalışır; dosyalar hiçbir yere gönderilmez.
 * - BGZF blokları tek tek açılır. Açma fonksiyonu dışarıdan verilir:
 *   tarayıcıda DecompressionStream('deflate-raw'), Node.js'de zlib.inflateRawSync.
 * - BAI varsa yalnızca istenen bölgenin blokları okunur (büyük BAM dosyaları için).
 * - Analiz: kapsam, yumuşak kırpma (soft-clip) kümeleri, bölünmüş okumalar (SA etiketi),
 *   anormal okuma çiftleri (insert boyu / yönelim / farklı kromozom) ve bunlardan
 *   kesim noktası adayları.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.BamTools = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var CIGAR_OPS = 'MIDNSHP=X';
  var SEQ_CODES = '=ACMGRSVTWYHKDBN';

  /* ---------------- açma (inflate) ---------------- */
  async function browserInflateRaw(u8) {
    if (typeof DecompressionStream === 'undefined') throw new Error('Tarayıcınız sıkıştırılmış veri açmayı desteklemiyor (DecompressionStream). Güncel Chrome, Edge, Firefox veya Safari kullanın.');
    var ds = new DecompressionStream('deflate-raw');
    var stream = new Blob([u8]).stream().pipeThrough(ds);
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }

  /* BGZF: sıkıştırılmış tampondaki blokları aç.
   * Döner: { data: Uint8Array, blocks: [{coff, uoff}] } (coff: bloğun dosyadaki ofseti, uoff: açılmış verideki başlangıcı) */
  async function inflateBgzf(buf, baseOffset, inflate, maxBytes) {
    var u8 = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
    var parts = [], blocks = [], pos = 0, total = 0;
    while (pos + 18 <= u8.length) {
      if (u8[pos] !== 31 || u8[pos + 1] !== 139) throw new Error('Geçersiz BGZF bloğu (dosya BAM değil ya da bozuk).');
      var xlen = u8[pos + 10] | (u8[pos + 11] << 8);
      var bsize = -1, x = pos + 12, xend = pos + 12 + xlen;
      while (x < xend) {
        var si1 = u8[x], si2 = u8[x + 1], slen = u8[x + 2] | (u8[x + 3] << 8);
        if (si1 === 66 && si2 === 67) bsize = u8[x + 4] | (u8[x + 5] << 8);
        x += 4 + slen;
      }
      if (bsize < 0) throw new Error('BGZF blok boyutu okunamadı.');
      var size = bsize + 1;
      if (pos + size > u8.length) break; // son blok yarım: bırak
      var cdata = u8.subarray(pos + 12 + xlen, pos + size - 8);
      var isize = (u8[pos + size - 4] | (u8[pos + size - 3] << 8) | (u8[pos + size - 2] << 16) | (u8[pos + size - 1] << 24)) >>> 0;
      blocks.push({ coff: baseOffset + pos, uoff: total });
      if (isize > 0) {
        var out = await inflate(cdata);
        parts.push(out instanceof Uint8Array ? out : new Uint8Array(out));
        total += isize;
      }
      pos += size;
      if (maxBytes && total > maxBytes) throw new Error('Seçilen bölge çok büyük (açılmış veri ' + Math.round(total / 1e6) + ' MB). Bölgeyi daraltın.');
    }
    var data = new Uint8Array(total), o = 0;
    parts.forEach(function (p) { data.set(p, o); o += p.length; });
    return { data: data, blocks: blocks, consumed: pos };
  }

  /* ---------------- başlık ---------------- */
  function parseHeader(data) {
    var dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
    if (data.length < 12 || data[0] !== 66 || data[1] !== 65 || data[2] !== 77 || data[3] !== 1) throw new Error('BAM sihirli dizisi bulunamadı (dosya BAM değil). CRAM desteklenmez; samtools view -b ile BAM\'e çevirin.');
    var lText = dv.getInt32(4, true), p = 8 + lText;
    if (p + 4 > data.length) return null;
    var text = new TextDecoder().decode(data.subarray(8, 8 + lText));
    var nRef = dv.getInt32(p, true); p += 4;
    var refs = [];
    for (var i = 0; i < nRef; i++) {
      if (p + 4 > data.length) return null;
      var ln = dv.getInt32(p, true); p += 4;
      if (p + ln + 4 > data.length) return null;
      var name = new TextDecoder().decode(data.subarray(p, p + ln - 1)); p += ln;
      var len = dv.getInt32(p, true); p += 4;
      refs.push({ name: name, len: len });
    }
    return { text: text, refs: refs, end: p };
  }

  /* ---------------- kayıtlar ---------------- */
  function readTags(data, p, end) {
    var tags = {};
    var dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
    while (p + 3 <= end) {
      var tag = String.fromCharCode(data[p], data[p + 1]), t = String.fromCharCode(data[p + 2]); p += 3;
      var v;
      switch (t) {
        case 'A': v = String.fromCharCode(data[p]); p += 1; break;
        case 'c': v = dv.getInt8(p); p += 1; break;
        case 'C': v = data[p]; p += 1; break;
        case 's': v = dv.getInt16(p, true); p += 2; break;
        case 'S': v = dv.getUint16(p, true); p += 2; break;
        case 'i': v = dv.getInt32(p, true); p += 4; break;
        case 'I': v = dv.getUint32(p, true); p += 4; break;
        case 'f': v = dv.getFloat32(p, true); p += 4; break;
        case 'Z': case 'H': { var s = p; while (p < end && data[p] !== 0) p++; v = new TextDecoder().decode(data.subarray(s, p)); p++; break; }
        case 'B': {
          var st = String.fromCharCode(data[p]), n = dv.getInt32(p + 1, true); p += 5;
          var w = { c: 1, C: 1, s: 2, S: 2, i: 4, I: 4, f: 4 }[st] || 1;
          p += n * w; v = null; break;
        }
        default: return tags; // bilinmeyen tip: dur
      }
      if (tag === 'SA' || tag === 'NM' || tag === 'MC') tags[tag] = v;
    }
    return tags;
  }

  // Tek kayıt: p kayıt başlangıcı (block_size alanı). Döner {rec, next} veya null (yarım)
  function parseRecord(data, dv, p, refs, wantSeq) {
    if (p + 4 > data.length) return null;
    var bs = dv.getInt32(p, true);
    var end = p + 4 + bs;
    if (end > data.length) return null;
    var q = p + 4;
    var refID = dv.getInt32(q, true), pos = dv.getInt32(q + 4, true);
    var lName = data[q + 8], mapq = data[q + 9];
    var nCig = dv.getUint16(q + 12, true), flag = dv.getUint16(q + 14, true);
    var lSeq = dv.getInt32(q + 16, true);
    var nRefID = dv.getInt32(q + 20, true), nPos = dv.getInt32(q + 24, true), tlen = dv.getInt32(q + 28, true);
    var r = q + 32;
    var name = new TextDecoder().decode(data.subarray(r, r + lName - 1)); r += lName;
    var cigar = [], refLen = 0, clipL = 0, clipR = 0, hardL = 0, hardR = 0;
    for (var i = 0; i < nCig; i++) {
      var c = dv.getUint32(r, true); r += 4;
      var op = CIGAR_OPS[c & 15], len = c >>> 4;
      cigar.push([op, len]);
      if (op === 'M' || op === 'D' || op === 'N' || op === '=' || op === 'X') refLen += len;
    }
    if (cigar.length) {
      var f = cigar[0], fi = 0;
      if (f[0] === 'H') { hardL = f[1]; fi = 1; f = cigar[1]; }
      if (f && f[0] === 'S') clipL = f[1];
      var l = cigar[cigar.length - 1], li = cigar.length - 1;
      if (l[0] === 'H') { hardR = l[1]; li--; l = cigar[li]; }
      if (l && l[0] === 'S' && li > fi) clipR = l[1];
    }
    var seq = '';
    if (wantSeq && lSeq > 0) {
      var a = [];
      for (var k = 0; k < lSeq; k++) { var b = data[r + (k >> 1)]; a.push(SEQ_CODES[(k & 1) ? (b & 15) : (b >> 4)]); }
      seq = a.join('');
    }
    r += ((lSeq + 1) >> 1) + lSeq; // seq + qual
    var tags = readTags(data, r, end);
    return {
      next: end,
      rec: {
        name: name, chrom: refID >= 0 ? refs[refID].name : null, refID: refID, pos: pos, end: pos + refLen, mapq: mapq, flag: flag,
        cigar: cigar, clipL: clipL, clipR: clipR, hardL: hardL, hardR: hardR, seq: seq, lSeq: lSeq,
        mateChrom: nRefID >= 0 ? refs[nRefID].name : null, mateRefID: nRefID, matePos: nPos, tlen: tlen,
        SA: tags.SA || null, MC: tags.MC || null
      }
    };
  }

  function parseRecords(data, start, refs, region, opts) {
    opts = opts || {};
    var dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
    var out = [], p = start, n = 0;
    while (true) {
      var r = parseRecord(data, dv, p, refs, true);
      if (!r) break;
      p = r.next;
      var rec = r.rec;
      n++;
      if (region) {
        if (rec.refID !== region.refID) { if (rec.refID > region.refID && region.sorted) break; continue; }
        if (rec.pos >= region.end) { if (region.sorted) break; continue; }
        if (rec.end <= region.start && !(rec.flag & 4)) continue;
      }
      out.push(rec);
      if (opts.maxReads && out.length > opts.maxReads) throw new Error('Bölgede çok fazla okuma var (> ' + opts.maxReads + '). Bölgeyi daraltın.');
    }
    return { reads: out, scanned: n };
  }

  /* ---------------- BAI ---------------- */
  function voff(dv, p) {
    var lo = dv.getUint32(p, true), hi = dv.getUint32(p + 4, true);
    return { c: hi * 65536 + (lo >>> 16), u: lo & 0xffff };
  }
  function parseBai(buf, refID) {
    var u8 = new Uint8Array(buf), dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    if (u8[0] !== 66 || u8[1] !== 65 || u8[2] !== 73 || u8[3] !== 1) throw new Error('BAI dosyası geçersiz.');
    var nRef = dv.getInt32(4, true), p = 8, res = null;
    for (var i = 0; i < nRef; i++) {
      var nBin = dv.getInt32(p, true); p += 4;
      var bins = {};
      for (var b = 0; b < nBin; b++) {
        var bin = dv.getUint32(p, true), nChunk = dv.getInt32(p + 4, true); p += 8;
        var chunks = [];
        for (var c = 0; c < nChunk; c++) { chunks.push([voff(dv, p), voff(dv, p + 8)]); p += 16; }
        if (i === refID) bins[bin] = chunks;
      }
      var nIntv = dv.getInt32(p, true); p += 4;
      var lin = [];
      if (i === refID) for (var k = 0; k < nIntv; k++) lin.push(voff(dv, p + k * 8));
      p += nIntv * 8;
      if (i === refID) { res = { bins: bins, linear: lin }; }
    }
    return res;
  }
  function reg2bins(beg, end) {
    var list = [0], k;
    end -= 1;
    for (k = 1 + (beg >> 26); k <= 1 + (end >> 26); k++) list.push(k);
    for (k = 9 + (beg >> 23); k <= 9 + (end >> 23); k++) list.push(k);
    for (k = 73 + (beg >> 20); k <= 73 + (end >> 20); k++) list.push(k);
    for (k = 585 + (beg >> 17); k <= 585 + (end >> 17); k++) list.push(k);
    for (k = 4681 + (beg >> 14); k <= 4681 + (end >> 14); k++) list.push(k);
    return list;
  }
  function vlt(a, b) { return a.c < b.c || (a.c === b.c && a.u < b.u); }

  /* ---------------- bölge çözümleme ---------------- */
  function parseRegion(text) {
    if (!text) return null;
    var t = String(text).trim().replace(/,/g, '');
    var m = t.match(/^([A-Za-z0-9_.\-]+)\s*[:\s]\s*(\d+)\s*(?:-|_|\.\.)\s*(\d+)$/);
    if (!m) return null;
    return { chrom: m[1], start: Math.max(0, +m[2] - 1), end: +m[3] };
  }
  function findRef(refs, chrom) {
    var cands = [chrom, chrom.replace(/^chr/i, ''), 'chr' + chrom.replace(/^chr/i, '')];
    if (/^(chr)?(M|MT)$/i.test(chrom)) cands.push('chrM', 'MT', 'M');
    for (var i = 0; i < refs.length; i++) if (cands.indexOf(refs[i].name) >= 0) return i;
    return -1;
  }
  function ucscChrom(name) {
    var c = String(name).replace(/^chr/i, '');
    if (c === 'MT' || c === 'M') return 'chrM';
    return 'chr' + c;
  }

  /* ---------------- dosya okuma ----------------
   * src = { size, read(start, end) -> Promise<ArrayBuffer> }
   * bai = ArrayBuffer | null
   */
  async function readBam(src, bai, regionText, inflate, opts) {
    opts = opts || {};
    inflate = inflate || browserInflateRaw;
    // başlık
    var hdr = null, chunk = 1 << 18;
    while (!hdr) {
      var len = Math.min(src.size, chunk);
      var z = await inflateBgzf(await src.read(0, len), 0, inflate);
      hdr = parseHeader(z.data);
      if (!hdr && len >= src.size) throw new Error('BAM başlığı okunamadı.');
      if (!hdr) chunk *= 4;
      else hdr.headZ = z;
    }
    var region = null, reg = parseRegion(regionText);
    if (regionText && !reg) throw new Error('Bölge anlaşılamadı. Örnek: chr7:117,550,000-117,570,000');
    if (reg) {
      var rid = findRef(hdr.refs, reg.chrom);
      if (rid < 0) throw new Error(reg.chrom + ' bu BAM dosyasının referans listesinde yok (ör. ' + hdr.refs.slice(0, 3).map(function (r) { return r.name; }).join(', ') + ').');
      region = { refID: rid, chrom: hdr.refs[rid].name, start: reg.start, end: Math.min(reg.end, hdr.refs[rid].len), sorted: /SO:coordinate/.test(hdr.text) };
      if (region.end - region.start > (opts.maxRegion || 2000000)) throw new Error('Bölge en fazla ' + ((opts.maxRegion || 2000000) / 1e6) + ' Mb olabilir.');
    }
    var res;
    if (bai && region) {
      var idx = parseBai(bai, region.refID);
      if (!idx) throw new Error('İndekste bu kromozom yok.');
      var chunks = [];
      reg2bins(region.start, region.end).forEach(function (b) { (idx.bins[b] || []).forEach(function (c) { chunks.push(c); }); });
      var li = region.start >> 14, minOff = idx.linear[Math.min(li, idx.linear.length - 1)] || { c: 0, u: 0 };
      chunks = chunks.filter(function (c) { return vlt(minOff, c[1]); });
      if (!chunks.length) return { header: hdr, region: region, reads: [], scanned: 0, mode: 'indexed' };
      var beg = chunks.reduce(function (m, c) { return vlt(c[0], m) ? c[0] : m; }, chunks[0][0]);
      var endV = chunks.reduce(function (m, c) { return vlt(m, c[1]) ? c[1] : m; }, chunks[0][1]);
      if (vlt(beg, minOff)) beg = minOff;
      var cEnd = Math.min(src.size, endV.c + 65536 + 1024);
      if (cEnd - beg.c > (opts.maxCompressed || 400e6)) throw new Error('Bölge için okunacak veri çok büyük; bölgeyi daraltın.');
      var zb = await inflateBgzf(await src.read(beg.c, cEnd), beg.c, inflate, opts.maxInflated || 1.5e9);
      var startBlock = zb.blocks.filter(function (b) { return b.coff === beg.c; })[0];
      if (!startBlock) throw new Error('İndeks ile BAM uyuşmuyor (blok bulunamadı). BAI dosyasının bu BAM\'e ait olduğundan emin olun.');
      res = parseRecords(zb.data, startBlock.uoff + beg.u, hdr.refs, region, opts);
      res.mode = 'indexed';
    } else {
      if (src.size > (opts.maxPlain || 300e6)) throw new Error('Dosya büyük (' + Math.round(src.size / 1e6) + ' MB). Ya BAI indeks dosyasını da seçip bölge girin ya da samtools ile küçük bir kesit çıkarın.');
      var all = await inflateBgzf(await src.read(0, src.size), 0, inflate, opts.maxInflated || 1.5e9);
      var h2 = parseHeader(all.data);
      res = parseRecords(all.data, h2.end, hdr.refs, region ? Object.assign({}, region, { sorted: false }) : null, opts);
      res.mode = 'tam dosya';
    }
    res.header = hdr;
    res.region = region;
    return res;
  }

  /* =====================================================================
   * Kanıt analizi
   * ===================================================================== */
  function median(xs) { if (!xs.length) return 0; var s = xs.slice().sort(function (a, b) { return a - b; }); return s[s.length >> 1]; }
  function parseSA(sa) {
    return String(sa).split(';').filter(Boolean).map(function (x) {
      var f = x.split(',');
      var cig = [], re = /(\d+)([MIDNSHP=X])/g, m;
      while ((m = re.exec(f[3]))) cig.push([m[2], +m[1]]);
      var refLen = 0; cig.forEach(function (c) { if ('MDN=X'.indexOf(c[0]) >= 0) refLen += c[1]; });
      var lc = cig.length && (cig[0][0] === 'S' || cig[0][0] === 'H') ? cig[0][1] : 0;
      var rc = cig.length > 1 && (cig[cig.length - 1][0] === 'S' || cig[cig.length - 1][0] === 'H') ? cig[cig.length - 1][1] : 0;
      return { chrom: f[0], pos: +f[1] - 1, end: +f[1] - 1 + refLen, strand: f[2], mapq: +f[4], clipL: lc, clipR: rc };
    });
  }
  function consensus(seqs, fromRight, n) {
    n = n || 30;
    var out = '';
    for (var i = 0; i < n; i++) {
      var cnt = {}, tot = 0;
      seqs.forEach(function (s) {
        var c = fromRight ? s[s.length - 1 - i] : s[i];
        if (c && c !== 'N') { cnt[c] = (cnt[c] || 0) + 1; tot++; }
      });
      if (tot < 2) break;
      var best = Object.keys(cnt).sort(function (a, b) { return cnt[b] - cnt[a]; })[0];
      out += cnt[best] / tot >= 0.6 ? best : 'N';
    }
    return fromRight ? out.split('').reverse().join('') : out;
  }

  /*
   * reads: readBam çıktısı; region: {chrom, start, end}
   * opts: { minMapq: 20, minClip: 5, minSupport: 3 }
   */
  function analyze(reads, region, opts) {
    opts = Object.assign({ minMapq: 20, minClip: 5, minSupport: 3 }, opts || {});
    var chrom = region.chrom;
    var rs = region.start, re = region.end, L = re - rs;
    var cov = new Uint16Array(Math.max(1, L));
    var prim = [], used = 0, readLens = [];
    reads.forEach(function (r) {
      if (r.flag & (4 | 256 | 512 | 1024)) return;
      if (r.mapq < opts.minMapq) return;
      if (r.chrom !== chrom) return;
      used++;
      var supp = !!(r.flag & 2048);
      if (!supp) {
        prim.push(r);
        if (r.lSeq) readLens.push(r.lSeq);
        var g = r.pos;
        r.cigar.forEach(function (c) {
          var op = c[0], n = c[1];
          if (op === 'M' || op === '=' || op === 'X') { for (var k = Math.max(g, rs); k < Math.min(g + n, re); k++) cov[k - rs]++; g += n; }
          else if (op === 'D' || op === 'N') g += n;
        });
      }
    });
    var readLen = median(readLens) || 150;

    // insert boyu (uygun çiftler)
    var ins = prim.filter(function (r) { return (r.flag & 1) && (r.flag & 2) && r.tlen > 0 && r.mateChrom === r.chrom; }).map(function (r) { return r.tlen; });
    var insMed = median(ins), mad = median(ins.map(function (x) { return Math.abs(x - insMed); })) || 30;
    var insThr = insMed ? Math.max(insMed + 6 * 1.4826 * mad, insMed * 1.6) : 1000;
    var paired = ins.length > 20;

    // kapsam özetleri
    var covArr = Array.prototype.slice.call(cov);
    var covMed = median(covArr.filter(function (x) { return x > 0; }));
    var zeroFrac = covArr.filter(function (x) { return x < 3; }).length / covArr.length;
    var targeted = zeroFrac > 0.5;
    function meanCov(a, b) {
      a = Math.max(rs, a); b = Math.min(re, b);
      if (b <= a) return null;
      var s = 0; for (var i = a; i < b; i++) s += cov[i - rs];
      return s / (b - a);
    }

    // 1) yumuşak kırpma kümeleri
    var clipMap = {};
    reads.forEach(function (r) {
      if (r.flag & (4 | 256 | 512 | 1024) || r.mapq < opts.minMapq || r.chrom !== chrom) return;
      var lc = Math.max(r.clipL, r.hardL), rc = Math.max(r.clipR, r.hardR);
      if (lc >= opts.minClip) add(r.pos, 'L', r, r.clipL ? r.seq.slice(0, r.clipL) : '');
      if (rc >= opts.minClip) add(r.end, 'R', r, r.clipR ? r.seq.slice(r.seq.length - r.clipR) : '');
    });
    function add(pos, side, r, cseq) {
      var k = side + pos;
      var c = clipMap[k] || (clipMap[k] = { pos: pos, side: side, count: 0, seqs: [], sa: [] });
      c.count++;
      if (cseq) c.seqs.push(cseq);
      if (r.SA) c.sa.push({ read: r, sa: parseSA(r.SA)[0] });
    }
    var clips = Object.keys(clipMap).map(function (k) { return clipMap[k]; });
    // ±2 bp içindeki kümeleri birleştir
    clips.sort(function (a, b) { return a.side < b.side ? -1 : a.side > b.side ? 1 : a.pos - b.pos; });
    var merged = [];
    clips.forEach(function (c) {
      var last = merged[merged.length - 1];
      if (last && last.side === c.side && c.pos - last.pos <= 2) {
        if (c.count > last.count) last.pos = c.pos;
        last.count += c.count; last.seqs = last.seqs.concat(c.seqs); last.sa = last.sa.concat(c.sa);
      } else merged.push({ pos: c.pos, side: c.side, count: c.count, seqs: c.seqs.slice(), sa: c.sa.slice() });
    });
    clips = merged.filter(function (c) { return c.count >= opts.minSupport; });
    clips.forEach(function (c) {
      c.depth = cov[Math.min(L - 1, Math.max(0, c.pos - rs - (c.side === 'L' ? -1 : 1)))] || 0;
      c.consensus = consensus(c.seqs, c.side === 'L', 30);
    });

    // 2) bölünmüş okumalardan bağlantılar
    var junctions = [];
    clips.forEach(function (c) {
      c.sa.forEach(function (x) {
        var p = x.sa; if (!p || p.mapq < opts.minMapq) return;
        var pSide = p.clipL >= p.clipR ? 'L' : 'R';
        var pPos = pSide === 'L' ? p.pos : p.end;
        var pChrom = p.chrom;
        var j = junctions.filter(function (q) { return q.a.side === c.side && Math.abs(q.a.pos - c.pos) <= 2 && q.b.chrom === pChrom && q.b.side === pSide && Math.abs(q.b.pos - pPos) <= 10; })[0];
        if (!j) { j = { a: { chrom: chrom, pos: c.pos, side: c.side }, b: { chrom: pChrom, pos: pPos, side: pSide, list: [] }, split: 0 }; junctions.push(j); }
        j.split++; j.b.list.push(pPos);
      });
    });
    junctions.forEach(function (j) { j.b.pos = median(j.b.list); delete j.b.list; });

    // 3) anormal okuma çiftleri
    var disc = { DEL: [], DUP: [], INV: [], TRA: [] };
    if (paired) prim.forEach(function (r) {
      if (!(r.flag & 1) || (r.flag & 8)) return;
      var rev = !!(r.flag & 16), mrev = !!(r.flag & 32);
      if (r.mateChrom !== r.chrom) { disc.TRA.push({ r: r, mateChrom: r.mateChrom, matePos: r.matePos, rev: rev, mrev: mrev }); return; }
      if (r.pos > r.matePos || (r.pos === r.matePos && (r.flag & 128))) return; // her çifti bir kez say
      var mateEnd = r.matePos + readLen;
      var span = mateEnd - r.pos;
      if (!rev && mrev) { if (span > insThr) disc.DEL.push({ r: r, lEnd: r.end, rStart: r.matePos, span: span }); }
      else if (rev && !mrev) { if (span > readLen * 1.2) disc.DUP.push({ r: r, lEnd: r.end, rStart: r.matePos, lStart: r.pos, rEnd: mateEnd }); }
      else disc.INV.push({ r: r, lEnd: r.end, rStart: r.matePos, lStart: r.pos, rEnd: mateEnd, orient: rev ? 'RR' : 'FF' });
    });
    function clusterPairs(list, keyB) {
      list.sort(function (a, b) { return a.r.pos - b.r.pos; });
      var cl = [];
      list.forEach(function (x) {
        var c = cl.filter(function (q) { return (!keyB || q.chromB === x.mateChrom) && Math.abs(q.p0 - x.r.pos) <= insThr && Math.abs(q.m0 - (x.rStart != null ? x.rStart : x.matePos)) <= insThr * 1.5; })[0];
        if (!c) { c = { p0: x.r.pos, m0: x.rStart != null ? x.rStart : x.matePos, chromB: x.mateChrom, items: [] }; cl.push(c); }
        c.items.push(x);
      });
      return cl.filter(function (c) { return c.items.length >= opts.minSupport; });
    }
    var dcl = {
      DEL: clusterPairs(disc.DEL), DUP: clusterPairs(disc.DUP), INV: clusterPairs(disc.INV),
      TRA: clusterPairs(disc.TRA.map(function (x) { x.rStart = x.matePos; return x; }), true)
    };

    // 4) adaylar
    var cands = [];
    var win = Math.max(50, Math.round(insThr - readLen));
    function typeOf(a, b) {
      if (a.chrom !== b.chrom) return 'TRA';
      var x = a.pos <= b.pos ? a : b, y = a.pos <= b.pos ? b : a;
      if (x.side === 'R' && y.side === 'L') return 'DEL';
      if (x.side === 'L' && y.side === 'R') return 'DUP';
      return 'INV';
    }
    function clipAt(pos, side, tol) {
      return clips.filter(function (c) { return c.side === side && Math.abs(c.pos - pos) <= (tol || 3); }).sort(function (a, b) { return b.count - a.count; })[0] || null;
    }
    function discSupport(type, p1, p2, chromB) {
      var list = dcl[type] || [];
      var n = 0;
      list.forEach(function (c) {
        if (type === 'TRA') {
          if (c.chromB !== chromB) return;
          if (Math.abs(c.p0 - p1) <= insThr * 1.5 && Math.abs(c.m0 - p2) <= insThr * 1.5) n += c.items.length;
          return;
        }
        var lEnd = Math.max.apply(null, c.items.map(function (i) { return i.lEnd; }));
        var rStart = Math.min.apply(null, c.items.map(function (i) { return i.rStart; }));
        if (Math.abs(lEnd - p1) <= insThr && Math.abs(rStart - p2) <= insThr) n += c.items.length;
        else if (type !== 'DEL' && Math.abs(c.p0 - p1) <= insThr * 1.5 && Math.abs(c.m0 - p2) <= insThr * 1.5) n += c.items.length;
      });
      return n;
    }
    function refSpanning(pos) {
      return prim.filter(function (r) { return r.pos <= pos - 10 && r.end >= pos + 10 && r.clipL < opts.minClip && r.clipR < opts.minClip && !r.cigar.some(function (c) { return (c[0] === 'D' || c[0] === 'N') && c[1] > 50; }); }).length;
    }

    junctions.forEach(function (j) {
      var t = typeOf(j.a, j.b);
      var p1 = j.a.chrom === j.b.chrom ? Math.min(j.a.pos, j.b.pos) : j.a.pos;
      var p2 = j.a.chrom === j.b.chrom ? Math.max(j.a.pos, j.b.pos) : j.b.pos;
      var dup = cands.filter(function (c) { return c.type === t && Math.abs(c.bp1.pos - p1) <= 5 && Math.abs(c.bp2.pos - p2) <= 10 && c.bp2.chrom === j.b.chrom; })[0];
      if (dup) { dup.support.split += j.split; return; }
      cands.push({ type: t, bp1: { chrom: chrom, pos: p1, exact: true }, bp2: { chrom: j.b.chrom, pos: p2, exact: true }, support: { split: j.split }, source: 'bölünmüş okuma' });
    });
    // SA olmadan eşleşen kırpma çiftleri (DEL: R ... L)
    clips.filter(function (c) { return c.side === 'R'; }).forEach(function (cr) {
      if (cands.some(function (k) { return k.bp1.chrom === chrom && Math.abs(k.bp1.pos - cr.pos) <= 3; })) return;
      dcl.DEL.forEach(function (c) {
        var lEnd = Math.max.apply(null, c.items.map(function (i) { return i.lEnd; }));
        var rStart = Math.min.apply(null, c.items.map(function (i) { return i.rStart; }));
        if (cr.pos < lEnd || cr.pos > lEnd + win) return;
        var cl = clips.filter(function (x) { return x.side === 'L' && x.pos <= rStart && x.pos >= rStart - win; }).sort(function (a, b) { return b.count - a.count; })[0];
        if (cl) cands.push({ type: 'DEL', bp1: { chrom: chrom, pos: cr.pos, exact: true }, bp2: { chrom: chrom, pos: cl.pos, exact: true }, support: { split: 0 }, source: 'kırpma + anormal çift' });
      });
    });
    // yalnızca anormal çift kümeleri (belirsiz pencere)
    ['DEL', 'DUP', 'INV', 'TRA'].forEach(function (t) {
      dcl[t].forEach(function (c) {
        var lEnd = Math.max.apply(null, c.items.map(function (i) { return i.lEnd != null ? i.lEnd : i.r.end; }));
        var rStart = Math.min.apply(null, c.items.map(function (i) { return i.rStart; }));
        var covered = cands.some(function (k) { return (k.type === t || t === 'TRA' && k.type === 'TRA') && Math.abs(k.bp1.pos - lEnd) <= insThr * 1.5 && (t === 'TRA' ? k.bp2.chrom === c.chromB : Math.abs(k.bp2.pos - rStart) <= insThr * 1.5); });
        if (covered) return;
        var w1, w2;
        if (t === 'DEL') { w1 = [lEnd, lEnd + win]; w2 = [rStart - win, rStart]; }
        else if (t === 'DUP') {
          // sağdaki ileri okuma kesim noktasında kırpılmış olabilir: başlangıç + okuma uzunluğu tahmini için tolerans bırak
          var ls = Math.min.apply(null, c.items.map(function (i) { return i.lStart; }));
          var rS = Math.max.apply(null, c.items.map(function (i) { return i.rStart; }));
          w1 = [ls - win, ls]; w2 = [rS, rS + readLen + win];
        }
        else if (t === 'INV') { w1 = [lEnd, lEnd + win]; w2 = [rStart - win, rStart + readLen]; }
        else { w1 = [c.items[0].rev ? c.p0 - win : lEnd, c.items[0].rev ? c.p0 : lEnd + win]; w2 = [rStart - win, rStart + win]; }
        // pencere içindeki en güçlü kırpma ile kesinleştir
        function refine(w, sides) {
          var best = clips.filter(function (x) { return sides.indexOf(x.side) >= 0 && x.pos >= w[0] - 5 && x.pos <= w[1] + 5; }).sort(function (a, b) { return b.count - a.count; })[0];
          return best ? { pos: best.pos, exact: true } : { pos: Math.round((w[0] + w[1]) / 2), exact: false, window: w };
        }
        var b1 = refine(w1, t === 'DEL' ? ['R'] : t === 'DUP' ? ['L'] : ['R', 'L']);
        var b2 = t === 'TRA' ? { pos: Math.round((w2[0] + w2[1]) / 2), exact: false, window: w2 } : refine(w2, t === 'DEL' ? ['L'] : t === 'DUP' ? ['R'] : ['R', 'L']);
        b1.chrom = chrom; b2.chrom = t === 'TRA' ? c.chromB : chrom;
        cands.push({ type: t, bp1: b1, bp2: b2, support: { split: 0 }, source: 'anormal okuma çifti' });
      });
    });

    // destekleri ve doz
    cands.forEach(function (k) {
      var s = k.support;
      var c1 = clipAt(k.bp1.pos, k.type === 'DUP' ? 'L' : k.type === 'DEL' ? 'R' : null) || clips.filter(function (x) { return Math.abs(x.pos - k.bp1.pos) <= 3; }).sort(function (a, b) { return b.count - a.count; })[0];
      var c2 = k.bp2.chrom === chrom ? (clipAt(k.bp2.pos, k.type === 'DUP' ? 'R' : k.type === 'DEL' ? 'L' : null) || clips.filter(function (x) { return Math.abs(x.pos - k.bp2.pos) <= 3; }).sort(function (a, b) { return b.count - a.count; })[0]) : null;
      s.clip1 = c1 ? c1.count : 0; s.clip2 = c2 ? c2.count : 0;
      k.consensus1 = c1 ? c1.consensus : ''; k.consensus2 = c2 ? c2.consensus : '';
      s.disc = discSupport(k.type, k.bp1.pos, k.bp2.pos, k.bp2.chrom);
      var alt = Math.max(s.split, s.clip1, s.disc);
      var ref1 = refSpanning(k.bp1.pos);
      k.refSpan = ref1;
      k.af = alt + ref1 > 0 ? alt / (alt + ref1) : null;
      if (k.bp2.chrom === chrom && (k.type === 'DEL' || k.type === 'DUP') && k.bp2.pos - k.bp1.pos > 200) {
        var inside = meanCov(k.bp1.pos + 30, k.bp2.pos - 30);
        var fl = [meanCov(k.bp1.pos - 1500, k.bp1.pos - 100), meanCov(k.bp2.pos + 100, k.bp2.pos + 1500)].filter(function (x) { return x != null && x > 0; });
        var flank = fl.length ? fl.reduce(function (a, b) { return a + b; }, 0) / fl.length : null;
        k.depthRatio = inside != null && flank ? inside / flank : null;
        k.insideCovered = inside != null && k.bp2.pos <= re && k.bp1.pos >= rs;
      }
      // zigosite
      if (k.type === 'DEL' && k.depthRatio != null && k.insideCovered) k.zyg = k.depthRatio < 0.2 ? 'hom' : k.depthRatio < 0.75 ? 'het' : '?';
      else if (k.type === 'DUP' && k.depthRatio != null && k.insideCovered) k.zyg = k.depthRatio > 1.8 ? 'hom?' : k.depthRatio > 1.25 ? 'het' : '?';
      else if (k.af != null) k.zyg = k.af > 0.85 ? 'hom' : k.af > 0.2 ? 'het' : 'düşük AF';
      else k.zyg = '?';
      var score = s.split * 2 + s.disc + (s.clip1 + s.clip2) / 2;
      k.score = score;
      k.confidence = (s.split >= 3 || (s.clip1 >= 3 && s.clip2 >= 3)) && s.disc >= 3 ? 'yüksek' : score >= 8 ? 'orta' : 'düşük';
      k.size = k.bp2.chrom === chrom ? k.bp2.pos - k.bp1.pos : null;
    });
    cands = cands.filter(function (k) { return !(k.size != null && k.size < 50 && k.type !== 'TRA'); });
    cands.sort(function (a, b) { return b.score - a.score; });

    // kapsam tabanlı aday (yalnızca WGS benzeri veride ve kırık kanıtı yoksa)
    var covCands = [];
    if (!targeted && covMed >= 8 && L >= 3000) {
      var bin = Math.max(500, Math.round(L / 80));
      var bins = [];
      for (var s0 = rs; s0 < re; s0 += bin) bins.push({ s: s0, e: Math.min(re, s0 + bin), m: meanCov(s0, Math.min(re, s0 + bin)) });
      var run = null;
      bins.forEach(function (b, i) {
        var r = b.m / covMed, state = r < 0.65 ? 'low' : r > 1.4 ? 'high' : null;
        if (state && run && run.state === state) { run.e = b.e; run.n++; run.sum += r; }
        else { if (run && run.n >= 3) covCands.push(run); run = state ? { state: state, s: b.s, e: b.e, n: 1, sum: r } : null; }
        if (i === bins.length - 1 && run && run.n >= 3) covCands.push(run);
      });
      covCands = covCands.filter(function (r) { return r.s > rs + bin && r.e < re - bin && r.e - r.s >= 1500; });
      // yalnızca orta/yüksek güvenli bir kırık adayı ile örtüşen kapsam adaylarını gizle
      covCands = covCands.filter(function (r) { return !cands.some(function (k) { return k.confidence !== 'düşük' && k.bp2.chrom === chrom && k.bp1.pos < r.e && r.s < k.bp2.pos; }); })
        .map(function (r) {
          var ratio = r.sum / r.n, del = r.state === 'low';
          // kenarları yakındaki kırpma kümeleriyle keskinleştir
          function edge(pos, side) {
            var c = clips.filter(function (x) { return x.side === side && Math.abs(x.pos - pos) <= bin * 1.5; }).sort(function (a, b) { return b.count - a.count; })[0];
            return c ? { chrom: chrom, pos: c.pos, exact: true, clip: c } : { chrom: chrom, pos: pos, exact: false, window: [pos - bin, pos + bin] };
          }
          var e1 = edge(r.s, del ? 'R' : 'L'), e2 = edge(r.e, del ? 'L' : 'R');
          var strong = del ? ratio < 0.25 : ratio > 1.6;
          return { type: del ? 'DEL' : 'DUP', bp1: e1, bp2: e2,
            support: { split: 0, disc: 0, clip1: e1.clip ? e1.clip.count : 0, clip2: e2.clip ? e2.clip.count : 0 },
            consensus1: e1.clip ? e1.clip.consensus : '', consensus2: e2.clip ? e2.clip.consensus : '',
            depthRatio: ratio, size: e2.pos - e1.pos, source: 'kapsam' + (e1.clip || e2.clip ? ' + kırpma' : ''),
            confidence: strong && r.e - r.s >= 1500 ? 'orta' : 'düşük', zyg: del ? (ratio < 0.2 ? 'hom' : 'het') : (ratio > 1.8 ? 'hom?' : 'het'), score: strong ? 7 : 3 };
        });
    }

    // grafik için kapsam profili
    var nb = Math.min(600, L), bsz = L / nb, prof = [];
    for (var i = 0; i < nb; i++) { var a = rs + Math.floor(i * bsz), b2 = rs + Math.floor((i + 1) * bsz); prof.push(meanCov(a, Math.max(a + 1, b2)) || 0); }

    return {
      region: region, readsUsed: used, primary: prim.length, readLen: readLen,
      insert: { median: insMed, mad: mad, threshold: Math.round(insThr), paired: paired },
      coverage: { median: covMed, profile: prof, targeted: targeted },
      clips: clips.map(function (c) { return { pos: c.pos, side: c.side, count: c.count, depth: c.depth, consensus: c.consensus, withSA: c.sa.length }; }),
      discordant: ['DEL', 'DUP', 'INV', 'TRA'].reduce(function (o, t) {
        o[t] = dcl[t].map(function (c) { return { n: c.items.length, chromB: c.chromB, pairs: c.items.slice(0, 60).map(function (i) { return [i.r.pos, i.r.end, i.matePos != null && t === 'TRA' ? i.matePos : i.rStart]; }) }; });
        return o;
      }, {}),
      candidates: cands.concat(covCands).sort(function (a, b) { return (b.score || 0) - (a.score || 0); })
    };
  }

  // Tarayıcıda File nesnesini kaynak olarak sar
  function fileSource(file) {
    return { size: file.size, name: file.name, read: function (a, b) { return file.slice(a, b).arrayBuffer(); } };
  }

  return {
    readBam: readBam, analyze: analyze, inflateBgzf: inflateBgzf, parseHeader: parseHeader, parseBai: parseBai, reg2bins: reg2bins,
    parseRegion: parseRegion, findRef: findRef, ucscChrom: ucscChrom, fileSource: fileSource, browserInflateRaw: browserInflateRaw, parseSA: parseSA
  };
});
