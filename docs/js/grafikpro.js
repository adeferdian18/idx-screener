/* Grafik Pro: candle + volume, MA, support/resistance, Fibonacci, trendline, checklist Trend Template (Meja Pantau IDX). */
(function(){
  const LWC_URL = "https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js";
  let lwc;
  function loadLWC(){
    if(window.LightweightCharts) return Promise.resolve();
    lwc ??= new Promise((ok, fail) => { const s = document.createElement("script"); s.src = LWC_URL; s.onload = ok; s.onerror = fail; document.head.append(s); });
    return lwc;
  }
  const st = { kode: "", per: "6", ma5: false, ma20: true, ma50: true, ma200: true, sr: true, fib: false, tl: false };
  try{ Object.assign(st, JSON.parse(App.store.get("gp") || "{}")); }catch{}
  const save = () => { try{ App.store.set("gp", JSON.stringify(st)); }catch{} };
  let built = false, chart = null, data = null, loadedKode = null, drawnDark = null, busy = false;
  const cache = {};

  const CSS = `
#panel-grafikpro .gp-wrap{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:16px;align-items:start}
@media (max-width:900px){#panel-grafikpro .gp-wrap{grid-template-columns:minmax(0,1fr)}}
#panel-grafikpro .gp-chart{height:440px;width:100%;min-width:0;position:relative}
@media (max-width:600px){#panel-grafikpro .gp-chart{height:340px}}
#panel-grafikpro .gp-msg{padding:24px 8px;color:var(--muted)}
#panel-grafikpro .gp-codes{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
#panel-grafikpro .gp-input{width:110px;text-transform:uppercase}
#panel-grafikpro .gp-layers{display:flex;flex-wrap:wrap;gap:4px 12px;margin:8px 0}
#panel-grafikpro .gp-list{list-style:none;margin:0;padding:0}
#panel-grafikpro .gp-list li{display:flex;gap:8px;padding:7px 0;border-bottom:1px solid var(--line);font-size:14px}
#panel-grafikpro .gp-list li:last-child{border-bottom:0}
#panel-grafikpro .gp-ok{color:var(--up);font-weight:700;width:16px}
#panel-grafikpro .gp-no{color:var(--down);font-weight:700;width:16px}
#panel-grafikpro .gp-score{font-family:var(--serif);font-size:32px;margin:4px 0 8px}
#panel-grafikpro .gp-legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--muted);margin-top:6px}
#panel-grafikpro .gp-legend i{display:inline-block;width:12px;height:3px;border-radius:2px;vertical-align:middle;margin-right:4px}
`;
  const COL = { ma5: "#E0A030", ma20: "#D0559A", ma50: "#2F9BD6", ma200: "" };
  const LAYERS = [["ma5","MA5"],["ma20","MA20"],["ma50","MA50"],["ma200","MA200"],["sr","Support & Resistance"],["fib","Fibonacci"],["tl","Garis tren"]];

  function codes(){
    const m = App.S.momentum, rows = Array.isArray(m) ? m : (m?.rows || []);
    return rows.filter(r => r.entry != null && r.entry !== false).map(r => r.kode).sort();
  }
  function sma(a, n){
    const out = new Array(a.length).fill(null); let s = 0, k = 0;
    for(let i = 0; i < a.length; i++){
      if(App.isNum(a[i])){ s += a[i]; k++; }
      if(i >= n){ if(App.isNum(a[i-n])){ s -= a[i-n]; k--; } }
      if(i >= n - 1 && k === n) out[i] = s / n;
    }
    return out;
  }
  function swings(d, from, w){
    const hi = [], lo = [];
    for(let i = Math.max(from, w); i < d.c.length - w; i++){
      let isH = true, isL = true;
      for(let j = i - w; j <= i + w; j++){ if(j === i) continue; if(d.h[j] > d.h[i]) isH = false; if(d.l[j] < d.l[i]) isL = false; }
      if(isH && App.isNum(d.h[i])) hi.push(i);
      if(isL && App.isNum(d.l[i])) lo.push(i);
    }
    return { hi, lo };
  }
  function srLevels(d){
    const n = d.c.length, from = Math.max(0, n - 120), sw = swings(d, from, 3);
    const pts = [...sw.hi.map(i => d.h[i]), ...sw.lo.map(i => d.l[i])].sort((a, b) => a - b);
    const cl = [];
    for(const p of pts){ const c = cl[cl.length - 1]; if(c && p <= c.avg * 1.02){ c.sum += p; c.n++; c.avg = c.sum / c.n; } else cl.push({ sum: p, n: 1, avg: p }); }
    const last = d.c[n - 1];
    const by = (a, b) => b.n - a.n;
    return { res: cl.filter(c => c.avg > last).sort(by).slice(0, 3), sup: cl.filter(c => c.avg <= last).sort(by).slice(0, 3) };
  }
  const barsFor = per => Math.round(+per * 21);
  function checks(d){
    const n = d.c.length, i = n - 1, c = d.c[i];
    const m50 = d.ma50[i], m150 = d.ma150[i], m200 = d.ma200[i], m200p = d.ma200[Math.max(0, i - 21)];
    const w = Math.max(0, n - 252);
    const hi52 = Math.max(...d.h.slice(w).filter(App.isNum)), lo52 = Math.min(...d.l.slice(w).filter(App.isNum));
    const r = (d.rsr || []).filter(App.isNum), rNow = r[r.length - 1], rPrev = r[r.length - 22];
    const ok = x => App.isNum(x);
    return [
      ["Harga di atas MA50", ok(m50) && c > m50],
      ["MA50 di atas MA150", ok(m50) && ok(m150) && m50 > m150],
      ["MA150 di atas MA200", ok(m150) && ok(m200) && m150 > m200],
      ["MA200 naik dalam 1 bulan", ok(m200) && ok(m200p) && m200 > m200p],
      [`Maks. 25% di bawah high 52 minggu (${App.fmt(hi52)})`, c >= hi52 * 0.75],
      [`Min. 30% di atas low 52 minggu (${App.fmt(lo52)})`, c >= lo52 * 1.3],
      ["RS naik dalam 1 bulan", ok(rNow) && ok(rPrev) && rNow > rPrev],
    ];
  }

  function shell(el){
    const cs = codes();
    el.innerHTML = `<div class="card">
      <h2>Grafik Pro</h2>
      <p>Grafik candle dengan MA, support dan resistance otomatis, Fibonacci, dan garis tren, plus checklist Trend Template.</p>
      <div class="toolbar">
        <input class="search gp-input" id="gp-kode" list="gp-dl" placeholder="Kode" autocomplete="off" value="${App.esc(st.kode)}" aria-label="Kode saham">
        <datalist id="gp-dl">${cs.map(k => `<option value="${App.esc(k)}">`).join("")}</datalist>
        <button class="chip" id="gp-go">Tampilkan</button>
        <span class="seg">${["3","6","12"].map(p => `<button data-gp-per="${p}" aria-pressed="${st.per === p}">${p} bln</button>`).join("")}</span>
        <button class="chip" id="gp-shot">Simpan gambar</button>
      </div>
      <div class="gp-layers">${LAYERS.map(([k, l]) => `<label class="ck"><input type="checkbox" data-gp-l="${k}" ${st[k] ? "checked" : ""}> ${l}</label>`).join("")}</div>
      <div class="gp-wrap">
        <div><div class="gp-chart" id="gp-chart"></div><div class="gp-legend" id="gp-legend"></div></div>
        <div class="card" id="gp-check"><p class="hint">Pilih saham untuk melihat checklist.</p></div>
      </div>
      <p class="hint">Alat bantu analisis, bukan rekomendasi beli atau jual.</p>
    </div>`;
    const go = () => { const v = el.querySelector("#gp-kode").value.trim().toUpperCase(); if(v){ st.kode = v; save(); load(el); } };
    el.querySelector("#gp-go").onclick = go;
    el.querySelector("#gp-kode").addEventListener("keydown", e => { if(e.key === "Enter") go(); });
    el.querySelector("#gp-kode").addEventListener("change", go);
    el.querySelectorAll("[data-gp-per]").forEach(b => b.onclick = () => {
      st.per = b.dataset.gpPer; save();
      el.querySelectorAll("[data-gp-per]").forEach(x => x.setAttribute("aria-pressed", x === b));
      draw(el);
    });
    el.querySelectorAll("[data-gp-l]").forEach(c => c.onchange = () => { st[c.dataset.gpL] = c.checked; save(); draw(el); });
    el.querySelector("#gp-shot").onclick = () => {
      if(!chart || !data) return;
      const cv = chart.takeScreenshot(), a = document.createElement("a");
      a.download = `${loadedKode}-${new Date().toISOString().slice(0, 10)}.png`;
      a.href = cv.toDataURL("image/png"); a.click();
    };
    el.addEventListener("click", e => { const b = e.target.closest("[data-gp-code]"); if(b){ st.kode = b.dataset.gpCode; el.querySelector("#gp-kode").value = st.kode; save(); load(el); } });
  }

  function missing(el, k){
    if(chart){ chart.remove(); chart = null; }
    data = null; loadedKode = null;
    const cs = codes();
    el.querySelector("#gp-chart").innerHTML = `<div class="gp-msg">${k ? `Data grafik untuk <b>${App.esc(k)}</b> belum tersedia.` : "Ketik kode saham lalu tekan Tampilkan."} Grafik tersedia untuk saham berikut:
      <div class="gp-codes">${cs.map(c => `<button class="chip" data-gp-code="${App.esc(c)}">${App.esc(c)}</button>`).join("") || "<span class='hint'>Memuat daftar…</span>"}</div></div>`;
    el.querySelector("#gp-legend").innerHTML = "";
    el.querySelector("#gp-check").innerHTML = `<p class="hint">Pilih saham untuk melihat checklist.</p>`;
  }

  async function load(el){
    const k = st.kode;
    if(!k){ missing(el, ""); return; }
    if(busy) return; busy = true;
    try{
      el.querySelector("#gp-chart").innerHTML = `<div class="gp-msg">Memuat grafik ${App.esc(k)}…</div>`;
      if(chart){ chart.remove(); chart = null; }
      const [d] = await Promise.all([cache[k] !== undefined ? cache[k] : App.getJSON("chart/" + k).catch(() => null), loadLWC().catch(() => null)]);
      cache[k] = d || null;
      if(!d || !d.t || !window.LightweightCharts){ missing(el, k); return; }
      data = d; loadedKode = k; draw(el);
    } finally { busy = false; if(st.kode !== k) load(el); }
  }

  function draw(el){
    if(!data || !window.LightweightCharts) return;
    const box = el.querySelector("#gp-chart");
    if(chart){ chart.remove(); chart = null; }
    box.innerHTML = "";
    const css = getComputedStyle(document.documentElement), col = n => css.getPropertyValue(n).trim();
    drawnDark = App.dark();
    const d = data, t = d.t, n = t.length;
    chart = LightweightCharts.createChart(box, {
      autoSize: true, layout: { background: { color: col("--surface") || "transparent" }, textColor: col("--muted"), fontFamily: col("--font") },
      grid: { vertLines: { visible: false }, horzLines: { color: col("--line") } },
      rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false }, crosshair: { mode: 0 },
      watermark: { visible: true, text: d === data ? loadedKode : "", fontSize: 42, color: col("--line") },
    });
    const cs = chart.addCandlestickSeries({ upColor: col("--up"), downColor: col("--down"), borderVisible: false, wickUpColor: col("--up"), wickDownColor: col("--down") });
    cs.setData(t.map((x, i) => ({ time: x, open: d.o[i], high: d.h[i], low: d.l[i], close: d.c[i] })).filter(b => App.isNum(b.close)));
    const vs = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    vs.setData(t.map((x, i) => ({ time: x, value: d.v[i] || 0, color: (d.c[i] >= d.o[i] ? col("--up") : col("--down")) + "66" })));
    const legend = [];
    const line = (arr, color, label, extra = {}) => {
      const s = chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, ...extra });
      s.setData(t.map((x, i) => ({ time: x, value: arr[i] })).filter(b => App.isNum(b.value)));
      legend.push([color, label]); return s;
    };
    if(st.ma5) line(sma(d.c, 5), COL.ma5, "MA5");
    if(st.ma20) line(sma(d.c, 20), COL.ma20, "MA20");
    if(st.ma50) line(d.ma50 || sma(d.c, 50), COL.ma50, "MA50");
    if(st.ma200) line(d.ma200 || sma(d.c, 200), col("--muted"), "MA200");
    if(st.sr){
      const { res, sup } = srLevels(d);
      res.forEach((c, i) => cs.createPriceLine({ price: c.avg, color: col("--down"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "R" + (i + 1) }));
      sup.forEach((c, i) => cs.createPriceLine({ price: c.avg, color: col("--up"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "S" + (i + 1) }));
      legend.push([col("--down"), "Resistance"], [col("--up"), "Support"]);
    }
    if(st.fib){
      const from = Math.max(0, n - barsFor(st.per));
      const hs = d.h.slice(from).filter(App.isNum), ls = d.l.slice(from).filter(App.isNum);
      const hi = Math.max(...hs), lo = Math.min(...ls);
      [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1].forEach(f => cs.createPriceLine({ price: hi - (hi - lo) * f, color: col("--accent") || "#C08A2E", lineWidth: 1, lineStyle: 1, axisLabelVisible: false, title: "Fib " + App.fmt(f * 100, 1) + "%" }));
      legend.push([col("--accent") || "#C08A2E", `Fibonacci ${st.per} bln`]);
    }
    if(st.tl){
      const sw = swings(d, Math.max(0, n - 250), 5);
      const tl = (idx, arr, color, label) => {
        if(idx.length < 2) return;
        const a = idx[idx.length - 2], b = idx[idx.length - 1], slope = (arr[b] - arr[a]) / (b - a);
        const vals = new Array(n).fill(null); for(let i = a; i < n; i++) vals[i] = arr[a] + slope * (i - a);
        line(vals, color, label, { lineWidth: 2 });
      };
      tl(sw.lo, d.l, col("--teal") || "#2A9D8F", "Tren swing low");
      tl(sw.hi, d.h, col("--orange") || "#E07B39", "Tren swing high");
    }
    const from = Math.max(0, n - barsFor(st.per));
    chart.timeScale().setVisibleRange({ from: t[from], to: t[n - 1] });
    el.querySelector("#gp-legend").innerHTML = legend.map(([c, l]) => `<span><i style="background:${App.esc(c)}"></i>${App.esc(l)}</span>`).join("");
    const ck = checks(d), score = ck.filter(x => x[1]).length;
    el.querySelector("#gp-check").innerHTML = `<h2>Checklist tren ${App.esc(loadedKode)}</h2>
      <div class="gp-score">${score}/7</div>
      <ul class="gp-list">${ck.map(([l, ok]) => `<li><span class="${ok ? "gp-ok" : "gp-no"}">${ok ? "✓" : "✗"}</span><span>${App.esc(l)}</span></li>`).join("")}</ul>
      <p class="hint">Harga terakhir ${App.fmt(d.c[n - 1])} · ${App.esc(t[n - 1])}</p>`;
  }

  App.register("grafikpro", {
    render(el){
      if(!document.getElementById("grafikpro-css")){ const s = document.createElement("style"); s.id = "grafikpro-css"; s.textContent = CSS; document.head.append(s); }
      if(!built || !el.querySelector("#gp-chart")){ shell(el); built = true; if(st.kode) load(el); else missing(el, ""); return; }
      // refresh 60 dtk: jangan sentuh input; perbarui datalist dan gambar ulang jika tema berubah
      const dl = el.querySelector("#gp-dl"), cs = codes();
      if(dl && dl.children.length !== cs.length) dl.innerHTML = cs.map(k => `<option value="${App.esc(k)}">`).join("");
      if(!data) missing(el, st.kode && cache[st.kode] === null ? st.kode : "");
      else if(drawnDark !== App.dark()) draw(el);
    },
  });
})();
