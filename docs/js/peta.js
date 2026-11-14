/* Meja Pantau IDX: modul "Peta & sektor" (treemap saham + rotasi sektor) */
(function(){
  "use strict";
  const METRIK = {
    chg_1d: { label: "1 hari", clamp: 0.05 },
    ret_1m: { label: "1 bulan", clamp: 0.20 },
    ret_3m: { label: "3 bulan", clamp: 0.40 },
  };
  let metrik = "chg_1d", hanyaLikuid = true, urut = { k: "rs", dir: -1 };
  try{ const m = App.store.get("peta-metrik"); if(m && METRIK[m]) metrik = m; const l = App.store.get("peta-likuid"); if(l === "0" || l === false) hanyaLikuid = false; }catch{}
  let lastEl = null, resizeT = null, lastW = 0;

  const CSS = `
#panel-peta .peta-map{position:relative;width:100%;border-radius:10px;overflow:hidden;background:var(--bg2);margin-top:12px}
#panel-peta .peta-sec{position:absolute;box-sizing:border-box;border:1px solid var(--bg);overflow:hidden}
#panel-peta .peta-sec-l{position:absolute;left:0;top:0;right:0;height:16px;padding:0 5px;font-size:11px;font-weight:600;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:16px;background:var(--bg2)}
#panel-peta .peta-box{position:absolute;box-sizing:border-box;border:1px solid var(--bg);border-radius:3px;cursor:pointer;padding:0;display:flex;flex-direction:column;align-items:center;justify-content:center;overflow:hidden;color:var(--ink);font:inherit;text-align:center;line-height:1.15}
#panel-peta .peta-box:hover{outline:2px solid var(--ink);outline-offset:-2px;z-index:2}
#panel-peta .peta-box b{font-size:12px;font-weight:700}
#panel-peta .peta-box span{font-size:11px}
#panel-peta .peta-box.peta-big b{font-size:15px}
#panel-peta .peta-box.peta-big span{font-size:12.5px}
#panel-peta .peta-legend{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:12px;color:var(--muted)}
#panel-peta .peta-legend i{flex:1;max-width:280px;height:10px;border-radius:5px;border:1px solid var(--line)}
#panel-peta .peta-quad svg{width:100%;height:auto;display:block;margin-top:12px}
#panel-peta .peta-quad text{font-family:var(--font)}
#panel-peta th[data-sort]{cursor:pointer;user-select:none}
#panel-peta th[data-sort]:hover{color:var(--ink)}
#panel-peta .peta-q{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
#panel-peta .peta-q-lead{background:var(--good-soft);color:var(--up)}
#panel-peta .peta-q-weak{background:var(--accent-soft);color:var(--ink)}
#panel-peta .peta-q-lag{background:var(--warn-soft);color:var(--down)}
#panel-peta .peta-q-imp{background:color-mix(in srgb,var(--blue) 18%,var(--surface));color:var(--blue)}
#panel-peta .peta-card + .peta-card{margin-top:16px}
`;
  function injectCSS(){
    if(document.getElementById("peta-css")) return;
    const s = document.createElement("style"); s.id = "peta-css"; s.textContent = CSS; document.head.appendChild(s);
  }

  const num = v => App.isNum(v) ? +v : null;
  function median(a){
    const v = a.filter(App.isNum).map(Number).sort((x, y) => x - y);
    if(!v.length) return null;
    const m = v.length >> 1;
    return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
  }
  function color(v, clamp){
    if(!App.isNum(v)) return "var(--surface)";
    const t = Math.max(-1, Math.min(1, v / clamp));
    const p = Math.round(Math.abs(t) * 85);
    if(p < 3) return "var(--surface)";
    return `color-mix(in srgb, ${t > 0 ? "var(--up)" : "var(--down)"} ${p}%, var(--surface))`;
  }
  function inkFor(v, clamp){
    // teks putih di atas warna pekat
    return App.isNum(v) && Math.abs(v / clamp) > 0.55 ? "#fff" : "var(--ink)";
  }

  /* ---------- squarified treemap ---------- */
  // items: [{v,...}], rect {x,y,w,h}; returns items with x,y,w,h
  function squarify(items, rect){
    const out = [];
    const total = items.reduce((s, d) => s + d.v, 0);
    if(!total || rect.w <= 0 || rect.h <= 0) return out;
    const scale = rect.w * rect.h / total;
    const list = items.map(d => ({ d, a: d.v * scale })).sort((a, b) => b.a - a.a);
    let { x, y, w, h } = rect, i = 0;
    const worst = (row, side) => {
      let s = 0, mx = 0, mn = Infinity;
      for(const r of row){ s += r.a; mx = Math.max(mx, r.a); mn = Math.min(mn, r.a); }
      const s2 = s * s, side2 = side * side;
      return Math.max(side2 * mx / s2, s2 / (side2 * mn));
    };
    while(i < list.length){
      const side = Math.min(w, h);
      let row = [list[i++]];
      while(i < list.length && worst(row.concat(list[i]), side) <= worst(row, side)) row.push(list[i++]);
      const s = row.reduce((t, r) => t + r.a, 0);
      if(w >= h){ // kolom di kiri
        const cw = s / h; let cy = y;
        for(const r of row){ const rh = r.a / cw; out.push(Object.assign({}, r.d, { x, y: cy, w: cw, h: rh })); cy += rh; }
        x += cw; w -= cw;
      }else{ // baris di atas
        const rh = s / w; let cx = x;
        for(const r of row){ const rw = r.a / rh; out.push(Object.assign({}, r.d, { x: cx, y, w: rw, h: rh })); cx += rw; }
        y += rh; h -= rh;
      }
    }
    return out;
  }

  /* ---------- shell ---------- */
  function shell(el){
    el.innerHTML = `
<div class="card peta-card">
  <h2>Peta saham</h2>
  <p>Ukuran kotak = rata-rata nilai transaksi harian, warna = perubahan harga. Klik kotak untuk membuka detail saham.</p>
  <div class="toolbar">
    <span class="hint">Warna:</span>
    <div class="seg" id="peta-seg">${Object.entries(METRIK).map(([k, m]) => `<button type="button" data-m="${k}" aria-pressed="${k === metrik}">${m.label}</button>`).join("")}</div>
    <button type="button" class="chip" id="peta-likuid" aria-pressed="${hanyaLikuid}">Hanya likuid</button>
  </div>
  <div class="peta-map" id="peta-map"></div>
  <div class="peta-legend" id="peta-legend"></div>
  <p class="hint" id="peta-note"></p>
</div>
<div class="card peta-card peta-quad">
  <h2>Rotasi sektor</h2>
  <p>Median RS Rating (kekuatan relatif, sumbu datar) dan median return 1 bulan (momentum, sumbu tegak) per sektor, hanya saham likuid dan sektor dengan minimal 3 saham. Ukuran gelembung = jumlah saham.</p>
  <div id="peta-quad"></div>
  <div class="table-wrap" id="peta-table" style="margin-top:14px"></div>
</div>`;
    el.querySelector("#peta-seg").addEventListener("click", e => {
      const b = e.target.closest("button[data-m]"); if(!b) return;
      metrik = b.dataset.m; App.store.set("peta-metrik", metrik);
      el.querySelectorAll("#peta-seg button").forEach(x => x.setAttribute("aria-pressed", x === b));
      drawMap(el);
    });
    el.querySelector("#peta-likuid").addEventListener("click", e => {
      hanyaLikuid = !hanyaLikuid; App.store.set("peta-likuid", hanyaLikuid ? "1" : "0");
      e.currentTarget.setAttribute("aria-pressed", hanyaLikuid);
      drawMap(el);
    });
    el.querySelector("#peta-table").addEventListener("click", e => {
      const th = e.target.closest("th[data-sort]"); if(!th) return;
      const k = th.dataset.sort;
      urut = { k, dir: urut.k === k ? -urut.dir : (k === "sektor" || k === "kuadran" ? 1 : -1) };
      drawTable(el);
    });
  }

  /* ---------- treemap ---------- */
  function drawMap(el){
    const box = el.querySelector("#peta-map");
    const rows = (App.S.momentum?.rows || []).filter(r => App.isNum(r.nilai_rata2) && r.nilai_rata2 > 0 && (!hanyaLikuid || r.likuid));
    const W = Math.max(280, Math.floor(box.clientWidth || el.clientWidth || 320));
    lastW = W;
    const narrow = W < 600;
    const limit = narrow ? 80 : 150;
    const top = rows.slice().sort((a, b) => b.nilai_rata2 - a.nilai_rata2).slice(0, limit);
    const m = METRIK[metrik];
    if(!top.length){ box.style.height = "auto"; box.innerHTML = `<div class="empty"><p class="hint">Tidak ada saham yang cocok.</p></div>`; return; }
    const H = narrow ? Math.round(W * 1.5) : Math.round(Math.min(640, Math.max(420, W * 0.55)));
    box.style.height = H + "px";
    // sqrt agar saham raksasa tidak menelan seluruh peta
    const groups = {};
    for(const r of top){ const s = r.sektor || "Lainnya"; (groups[s] = groups[s] || []).push(r); }
    const secs = Object.entries(groups).map(([s, list]) => ({ s, list, v: list.reduce((t, r) => t + Math.sqrt(r.nilai_rata2), 0) }));
    const laid = squarify(secs, { x: 0, y: 0, w: W, h: H });
    let html = "";
    for(const g of laid){
      const lab = g.h > 34 && g.w > 40 ? 16 : 0;
      html += `<div class="peta-sec" style="left:${g.x}px;top:${g.y}px;width:${g.w}px;height:${g.h}px">${lab ? `<div class="peta-sec-l" title="${App.esc(g.s)}">${App.esc(g.s)}</div>` : ""}`;
      const kids = squarify(g.list.map(r => ({ r, v: Math.sqrt(r.nilai_rata2) })), { x: 1, y: lab + 1, w: g.w - 2, h: g.h - lab - 2 });
      for(const k of kids){
        const r = k.r, v = num(r[metrik]);
        const showCode = k.w >= 30 && k.h >= 16, showPct = k.w >= 40 && k.h >= 30;
        const big = k.w >= 90 && k.h >= 55;
        const tip = `${r.kode} · ${r.nama || ""}\n${r.sektor || ""}\nHarga ${App.fmt(r.harga)} · ${m.label}: ${v == null ? "–" : App.pct(v)}\nNilai rata-rata ${App.fmt(r.nilai_rata2 / 1e9, 1)} M`;
        html += `<button type="button" class="peta-box${big ? " peta-big" : ""}" data-code="${App.esc(r.kode)}" title="${App.esc(tip)}" aria-label="${App.esc(r.kode + " " + (v == null ? "" : App.pct(v)))}" style="left:${k.x - 1}px;top:${k.y - lab - 1}px;width:${k.w}px;height:${k.h}px;background:${color(v, m.clamp)};color:${inkFor(v, m.clamp)}">${showCode ? `<b>${App.esc(r.kode)}</b>` : ""}${showPct ? `<span>${v == null ? "–" : App.pct(v)}</span>` : ""}</button>`;
      }
      html += `</div>`;
    }
    box.innerHTML = html;
    const c = m.clamp;
    el.querySelector("#peta-legend").innerHTML = `<span>${App.pct(-c, 0)}</span><i style="background:linear-gradient(90deg,${color(-c, c)},${color(-c / 2, c)},var(--surface),${color(c / 2, c)},${color(c, c)})"></i><span>${App.pct(c, 0)}</span>`;
    el.querySelector("#peta-note").textContent = `${top.length} saham dengan nilai transaksi terbesar${hanyaLikuid ? " (hanya likuid)" : ""} dari ${rows.length} yang tersedia.`;
  }

  /* ---------- rotasi sektor ---------- */
  const QUAD = {
    lead: { nama: "Memimpin", c: "var(--up)" },
    weak: { nama: "Melemah", c: "var(--accent)" },
    lag:  { nama: "Tertinggal", c: "var(--down)" },
    imp:  { nama: "Membaik", c: "var(--blue)" },
  };
  function sectors(){
    const rows = (App.S.momentum?.rows || []).filter(r => r.likuid);
    const g = {};
    for(const r of rows){ const s = r.sektor || "Lainnya"; (g[s] = g[s] || []).push(r); }
    return Object.entries(g).filter(([, l]) => l.length >= 3).map(([sektor, l]) => {
      const rs = median(l.map(r => r.rs_rating)), r1 = median(l.map(r => r.ret_1m)), r3 = median(l.map(r => r.ret_3m));
      const ada = l.filter(r => App.isNum(r.chg_1d));
      const naik = ada.length ? ada.filter(r => r.chg_1d > 0).length / ada.length : null;
      const kanan = (rs ?? 50) >= 50, atas = (r1 ?? 0) >= 0;
      const q = kanan ? (atas ? "lead" : "weak") : (atas ? "imp" : "lag");
      return { sektor, n: l.length, rs, r1, r3, naik, q };
    });
  }
  function drawQuad(el, data){
    const W = 640, H = 420, P = { l: 44, r: 16, t: 16, b: 36 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const ys = data.map(d => d.r1).filter(App.isNum);
    let ymax = Math.max(0.05, ...ys.map(Math.abs)) * 1.15;
    const X = v => P.l + (Math.max(0, Math.min(100, v)) / 100) * iw;
    const Y = v => P.t + ih / 2 - (Math.max(-ymax, Math.min(ymax, v)) / ymax) * (ih / 2);
    const nMax = Math.max(1, ...data.map(d => d.n));
    const R = n => 6 + Math.sqrt(n / nMax) * 22;
    const tick = [-ymax, -ymax / 2, 0, ymax / 2, ymax];
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Kuadran rotasi sektor">`;
    s += `<rect x="${P.l}" y="${P.t}" width="${iw}" height="${ih}" fill="var(--bg2)" stroke="var(--line)" rx="8"/>`;
    s += `<rect x="${X(50)}" y="${P.t}" width="${iw / 2}" height="${ih / 2}" fill="var(--good-soft)" opacity=".55"/>`;
    s += `<rect x="${P.l}" y="${Y(0)}" width="${iw / 2}" height="${ih / 2}" fill="var(--warn-soft)" opacity=".55"/>`;
    s += `<line x1="${X(50)}" y1="${P.t}" x2="${X(50)}" y2="${P.t + ih}" stroke="var(--line2)" stroke-dasharray="4 4"/>`;
    s += `<line x1="${P.l}" y1="${Y(0)}" x2="${P.l + iw}" y2="${Y(0)}" stroke="var(--line2)" stroke-dasharray="4 4"/>`;
    for(const t of tick) s += `<text x="${P.l - 6}" y="${Y(t) + 4}" text-anchor="end" font-size="11" fill="var(--faint)">${App.pct(t)}</text>`;
    for(const t of [0, 25, 50, 75, 100]) s += `<text x="${X(t)}" y="${P.t + ih + 15}" text-anchor="middle" font-size="11" fill="var(--faint)">${t}</text>`;
    s += `<text x="${P.l + iw / 2}" y="${H - 4}" text-anchor="middle" font-size="12" fill="var(--muted)">Median RS Rating →</text>`;
    const ql = [["Membaik", P.l + 8, P.t + 18, "start", "var(--blue)"], ["Memimpin", P.l + iw - 8, P.t + 18, "end", "var(--up)"],
                ["Tertinggal", P.l + 8, P.t + ih - 8, "start", "var(--down)"], ["Melemah", P.l + iw - 8, P.t + ih - 8, "end", "var(--accent)"]];
    for(const [t, x, y, a, c] of ql) s += `<text x="${x}" y="${y}" text-anchor="${a}" font-size="13" font-weight="700" fill="${c}">${t}</text>`;
    const pts = data.filter(d => App.isNum(d.rs) && App.isNum(d.r1)).sort((a, b) => b.n - a.n);
    for(const d of pts){
      const cx = X(d.rs), cy = Y(d.r1), r = R(d.n), c = QUAD[d.q].c;
      s += `<g><title>${App.esc(d.sektor)}: ${d.n} saham, RS ${App.fmt(d.rs, 0)}, 1B ${App.pct(d.r1)}</title>`;
      s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${c}" fill-opacity=".28" stroke="${c}" stroke-width="1.5"/>`;
      const anchor = cx > P.l + iw * 0.75 ? "end" : "start", lx = anchor === "end" ? cx - r - 3 : cx + r + 3;
      s += `<text x="${lx}" y="${cy + 4}" text-anchor="${anchor}" font-size="11.5" fill="var(--ink)">${App.esc(d.sektor)}</text></g>`;
    }
    s += `</svg>`;
    el.querySelector("#peta-quad").innerHTML = pts.length ? s : `<p class="hint">Belum cukup data sektor.</p>`;
  }
  function drawTable(el, data){
    data = data || sectors();
    const key = { sektor: d => d.sektor, n: d => d.n, rs: d => d.rs, r1: d => d.r1, r3: d => d.r3, naik: d => d.naik, kuadran: d => QUAD[d.q].nama }[urut.k] || (d => d.rs);
    data.sort((a, b) => {
      const x = key(a), y = key(b);
      if(x == null) return 1; if(y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y, "id") : x - y) * urut.dir;
    });
    const th = (k, t) => `<th data-sort="${k}" aria-sort="${urut.k === k ? (urut.dir > 0 ? "ascending" : "descending") : "none"}">${t}${urut.k === k ? (urut.dir > 0 ? " ▲" : " ▼") : ""}</th>`;
    const sp = v => v == null ? "–" : `<span class="${App.cls(v)}">${App.pct(v)}</span>`;
    el.querySelector("#peta-table").innerHTML = data.length ? `<table><thead><tr>${th("sektor", "Sektor")}${th("n", "Saham")}${th("rs", "Median RS")}${th("r1", "Median 1B")}${th("r3", "Median 3B")}${th("naik", "% naik hari ini")}${th("kuadran", "Kuadran")}</tr></thead><tbody>${
      data.map(d => `<tr><td>${App.esc(d.sektor)}</td><td>${d.n}</td><td>${d.rs == null ? "–" : App.fmt(d.rs, 0)}</td><td>${sp(d.r1)}</td><td>${sp(d.r3)}</td><td>${d.naik == null ? "–" : App.fmt(d.naik * 100, 0) + "%"}</td><td><span class="peta-q peta-q-${d.q}">${QUAD[d.q].nama}</span></td></tr>`).join("")
    }</tbody></table>` : `<p class="hint" style="padding:12px">Belum cukup data sektor.</p>`;
  }

  App.register("peta", {
    render(el){
      injectCSS();
      lastEl = el;
      if(!App.S.momentum){
        if(!el.querySelector(".peta-card")) el.innerHTML = `<div class="card"><p class="hint">Memuat data…</p></div>`;
        return;
      }
      if(!el.querySelector("#peta-map")) shell(el);
      drawMap(el);
      const data = sectors();
      drawQuad(el, data);
      drawTable(el, data);
    },
  });

  addEventListener("resize", () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => {
      if(!lastEl || lastEl.hidden || !lastEl.querySelector("#peta-map") || !App.S.momentum) return;
      const w = Math.floor(lastEl.querySelector("#peta-map").clientWidth);
      if(Math.abs(w - lastW) > 4) drawMap(lastEl);
    }, 150);
  });
})();
