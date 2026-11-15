/* Modul "porto": portofolio pribadi (App.store key "porto") + kartu "flexing" yang bisa disimpan sebagai PNG. */
(() => {
  const KEY = "porto";
  const COLORS = ["--up", "--blue", "--orange", "--teal", "--accent", "--down", "--muted", "--ink"];
  let built = false, ihsgHist = null, ihsgCode = null, hideRp = false, msg = "";

  const num = v => { const n = typeof v === "number" ? v : parseFloat(String(v ?? "").replace(/\./g, "").replace(",", ".")); return isFinite(n) ? n : null; };
  const load = () => { try{ const o = JSON.parse(App.store.get(KEY) || "{}"); return { rows: Array.isArray(o.rows) ? o.rows : [], start: o.start || "" }; }catch{ return { rows: [], start: "" }; } };
  const save = o => App.store.set(KEY, JSON.stringify(o));
  const rp = x => App.isNum(x) ? (x < 0 ? "-" : "") + "Rp" + App.fmt(Math.abs(Math.round(x))) : "–";
  const sgn = x => App.isNum(x) ? (x >= 0 ? "+" : "") : "";
  const pctS = x => App.isNum(x) ? sgn(x) + App.pct(x).replace(/^\+/, "") : "–";
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || "#888";

  function price(kode){
    const q = App.S.quotes?.stocks?.[kode]?.last;
    if(App.isNum(q)) return q;
    const r = App.S.momentum?.rows?.find(x => x.kode === kode);
    return r && App.isNum(r.harga) ? r.harga : null;
  }

  function compute(){
    const { rows, start } = load();
    const list = rows.map((r, i) => {
      const lot = num(r.lot), avg = num(r.avg), px = price(r.kode);
      const modal = lot != null && avg != null ? lot * 100 * avg : null;
      const nilai = lot != null && px != null ? lot * 100 * px : null;
      const pl = modal != null && nilai != null ? nilai - modal : null;
      return { i, kode: r.kode, lot, avg, px, modal, nilai, pl, ret: pl != null && modal ? pl / modal : null };
    });
    const ok = list.filter(x => x.nilai != null && x.modal != null);
    const modal = ok.reduce((s, x) => s + x.modal, 0), nilai = ok.reduce((s, x) => s + x.nilai, 0);
    list.forEach(x => x.w = x.nilai != null && nilai ? x.nilai / nilai : null);
    const pl = nilai - modal, ret = modal ? pl / modal : null;
    // IHSG pembanding
    const ih = App.S.quotes?.ihsg; let ihsg = null, ihsgLabel = "IHSG hari ini";
    if(start && ihsgHist && App.isNum(ih?.last)){
      let k = -1; ihsgHist.t.forEach((t, j) => { if(t <= start) k = j; });
      if(k < 0 && ihsgHist.t.length && start < ihsgHist.t[0]) k = 0;
      const base = k >= 0 ? ihsgHist.ihsg[k] : null;
      if(App.isNum(base)){ ihsg = ih.last / base - 1; ihsgLabel = "IHSG sejak " + ihsgHist.t[k]; }
    }
    if(ihsg == null && App.isNum(ih?.chg)) ihsg = ih.chg;
    return { list, ok, modal, nilai, pl, ret, ihsg, ihsgLabel, start };
  }

  async function ensureIhsg(start, rows){
    if(!start || ihsgHist || ihsgCode) return;
    ihsgCode = "loading";
    // hanya sebagian saham punya file chart; coba kode portofolio dulu, lalu saham momentum teratas
    const mom = (App.S.momentum?.rows || []).slice().sort((a, b) => (b.rs_rating || 0) - (a.rs_rating || 0)).map(r => r.kode);
    const cand = [...new Set([...rows.map(r => r.kode), ...mom.slice(0, 8), "AADI"])];
    for(const code of cand){
      try{ const d = await App.getJSON("chart/" + code); if(d && Array.isArray(d.t) && Array.isArray(d.ihsg)){ ihsgHist = d; update(); return; } }catch{}
    }
  }

  function shell(el){
    el.innerHTML = `
<div class="card"><h2>Portofolio</h2><p>Catat saham yang kamu pegang. Harga ikut data terbaru di situs ini.</p>
  <form class="porto-form" data-p="form">
    <label>Kode<input name="kode" maxlength="6" required autocomplete="off" placeholder="BBCA"></label>
    <label>Lot<input name="lot" type="number" min="1" step="1" required></label>
    <label>Harga rata-rata<input name="avg" type="number" min="1" step="any" required></label>
    <button class="porto-btn solid" type="submit">Tambah</button>
  </form>
  <div class="toolbar porto-tools">
    <button class="porto-btn" type="button" data-act="jurnal">Ambil dari Jurnal</button>
    <label class="porto-start">Mulai sejak<input type="date" data-p="start"></label>
    <span class="hint" data-p="msg"></span>
  </div>
  <div data-p="table"></div>
</div>
<div class="porto-two">
  <div class="card"><h2>Ringkasan</h2><div data-p="sum"></div></div>
  <div class="card"><h2>Bobot</h2><div data-p="donut"></div></div>
</div>
<div class="card"><h2>Kartu pamer</h2><p>Bagikan hasilmu tanpa membuka isi dompet.</p>
  <div class="toolbar"><button class="chip" type="button" data-act="hide" aria-pressed="false">Sembunyikan rupiah</button>
  <button class="porto-btn solid" type="button" data-act="png">Simpan gambar</button></div>
  <div data-p="card"></div>
</div>
<p class="hint">Data hanya tersimpan di perangkat ini. Bukan rekomendasi beli atau jual.</p>`;
    el.querySelector('[data-p="start"]').value = load().start;
    el.addEventListener("submit", onSubmit);
    el.addEventListener("click", onClick);
    el.addEventListener("change", ev => {
      if(ev.target.matches('[data-p="start"]')){ const o = load(); o.start = ev.target.value; save(o); update(); }
      else if(ev.target.matches("[data-edit]")){
        const o = load(), r = o.rows[+ev.target.dataset.i]; if(!r) return;
        const v = num(ev.target.value); if(v != null && v > 0){ r[ev.target.dataset.edit] = v; save(o); } update();
      }
    });
  }

  function onSubmit(ev){
    if(!ev.target.matches('[data-p="form"]')) return;
    ev.preventDefault();
    const f = ev.target, kode = f.kode.value.trim().toUpperCase().replace(/[^A-Z0-9]/g, ""), lot = num(f.lot.value), avg = num(f.avg.value);
    if(!kode || !lot || !avg) return;
    const o = load(), ex = o.rows.find(r => r.kode === kode);
    if(ex){ const L = num(ex.lot) + lot; ex.avg = (num(ex.lot) * num(ex.avg) + lot * avg) / L; ex.lot = L; msg = kode + " digabung, harga rata-rata dihitung ulang."; }
    else{ o.rows.push({ kode, lot, avg }); msg = ""; }
    save(o); f.reset(); f.kode.focus(); update();
  }

  function onClick(ev){
    const b = ev.target.closest("[data-act]"); if(!b) return;
    const act = b.dataset.act, o = load();
    if(act === "del"){ o.rows.splice(+b.dataset.i, 1); save(o); msg = ""; }
    else if(act === "jurnal") importJurnal();
    else if(act === "hide"){ hideRp = !hideRp; b.setAttribute("aria-pressed", hideRp); }
    else if(act === "png"){ savePNG(); return; }
    update();
  }

  function importJurnal(){
    let a; try{ a = JSON.parse(App.store.get("jurnal") || "[]"); }catch{ a = []; }
    const open = (Array.isArray(a) ? a : []).filter(e => e && e.status === "terbuka" && e.kode && num(e.lot) > 0 && num(e.entry) > 0);
    if(!open.length){ msg = "Tidak ada posisi berstatus Terbuka di Jurnal."; return; }
    const o = load(); let n = 0;
    open.forEach(e => {
      const kode = String(e.kode).toUpperCase(), lot = num(e.lot), avg = num(e.entry);
      if(o.rows.some(r => r.src === e.id)) return;
      o.rows.push({ kode, lot, avg, src: e.id }); n++;
      if(e.tgl && (!o.start || e.tgl < o.start)) o.start = e.tgl;
    });
    save(o);
    const s = document.querySelector('#panel-porto [data-p="start"]'); if(s) s.value = o.start || "";
    msg = n ? n + " posisi diambil dari Jurnal." : "Semua posisi Jurnal sudah ada.";
  }

  function table(d){
    if(!d.list.length) return `<p class="hint">Belum ada saham. Tambah lewat form di atas.</p>`;
    return `<div class="table-wrap"><table><thead><tr><th>Kode</th><th>Lot</th><th>Rata-rata</th><th>Harga</th><th>Nilai</th><th>P/L</th><th>%</th><th>Bobot</th><th></th></tr></thead><tbody>
${d.list.map(x => `<tr><td><button class="porto-code" type="button" data-code="${App.esc(x.kode)}">${App.esc(x.kode)}</button></td>
<td><input class="porto-in" type="number" min="1" step="1" data-edit="lot" data-i="${x.i}" value="${x.lot ?? ""}" aria-label="Lot ${App.esc(x.kode)}"></td>
<td><input class="porto-in" type="number" min="1" step="any" data-edit="avg" data-i="${x.i}" value="${x.avg != null ? +x.avg.toFixed(2) : ""}" aria-label="Rata-rata ${App.esc(x.kode)}"></td>
<td>${App.fmt(x.px)}</td><td>${rp(x.nilai)}</td><td class="${App.cls(x.pl)}">${x.pl > 0 ? "+" : ""}${rp(x.pl)}</td><td class="${App.cls(x.ret)}">${pctS(x.ret)}</td>
<td>${x.w != null ? App.pct(x.w) : "–"}</td><td><button class="porto-del" type="button" data-act="del" data-i="${x.i}" aria-label="Hapus ${App.esc(x.kode)}">×</button></td></tr>`).join("")}
</tbody></table></div>`;
  }

  function summary(d){
    const c = (l, v, k = "") => `<div class="cell"><span>${l}</span><b class="${k}">${v}</b></div>`;
    const diff = d.ret != null && d.ihsg != null ? d.ret - d.ihsg : null;
    return `<div class="grid">${c("Total modal", rp(d.modal))}${c("Nilai sekarang", rp(d.nilai))}${c("P/L", (d.pl > 0 ? "+" : "") + rp(d.pl), App.cls(d.pl))}
${c("Return", pctS(d.ret), App.cls(d.ret))}${c(App.esc(d.ihsgLabel), pctS(d.ihsg), App.cls(d.ihsg))}${c("Selisih vs IHSG", diff != null ? pctS(diff) : "–", App.cls(diff))}</div>
${d.start ? "" : `<p class="hint">Isi tanggal "Mulai sejak" agar pembanding IHSG dihitung dari tanggal itu.</p>`}`;
  }

  function donut(d){
    const xs = d.list.filter(x => x.w > 0).sort((a, b) => b.w - a.w);
    if(!xs.length) return `<p class="hint">Belum ada data.</p>`;
    const R = 60, C = 2 * Math.PI * R; let off = 0;
    const segs = xs.map((x, j) => { const len = x.w * C, s = `<circle r="${R}" cx="80" cy="80" fill="none" stroke="var(${COLORS[j % COLORS.length]})" stroke-width="28" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}"/>`; off += len; return s; }).join("");
    return `<div class="porto-donut"><svg viewBox="0 0 160 160" role="img" aria-label="Bobot per saham"><g transform="rotate(-90 80 80)">${segs}</g>
<text x="80" y="76" text-anchor="middle" class="porto-dn1">${xs.length}</text><text x="80" y="94" text-anchor="middle" class="porto-dn2">saham</text></svg>
<ul>${xs.map((x, j) => `<li><i style="background:var(${COLORS[j % COLORS.length]})"></i>${App.esc(x.kode)}<b>${App.pct(x.w)}</b></li>`).join("")}</ul></div>`;
  }

  function cardData(d){
    const top = d.list.filter(x => x.ret != null).sort((a, b) => b.ret - a.ret).slice(0, 3);
    const date = new Date().toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" });
    return { top, date };
  }
  function shareCard(d){
    const { top, date } = cardData(d);
    return `<div class="porto-share"><div class="porto-sh-top"><span>Meja Pantau IDX</span><span>${App.esc(date)}</span></div>
<div class="porto-sh-lbl">Return portofolio${d.start ? " sejak " + App.esc(d.start) : ""}</div>
<div class="porto-sh-big ${App.cls(d.ret)}">${pctS(d.ret)}</div>
<div class="porto-sh-vs">IHSG ${pctS(d.ihsg)}${d.ret != null && d.ihsg != null ? ` · ${d.ret >= d.ihsg ? "unggul" : "tertinggal"} ${App.pct(Math.abs(d.ret - d.ihsg))} poin` : ""}</div>
${hideRp ? "" : `<div class="porto-sh-rp">P/L ${d.pl > 0 ? "+" : ""}${rp(d.pl)} · Nilai ${rp(d.nilai)}</div>`}
<div class="porto-sh-list">${top.map((x, j) => `<div><span>${j + 1}. ${App.esc(x.kode)}</span><b class="${App.cls(x.ret)}">${pctS(x.ret)}</b></div>`).join("") || `<div><span>Belum ada saham</span></div>`}</div>
<div class="porto-sh-foot">Bukan rekomendasi beli atau jual.</div></div>`;
  }

  function savePNG(){
    const d = compute(), { top, date } = cardData(d);
    const W = 1080, H = 1350, cv = document.createElement("canvas"); cv.width = W; cv.height = H;
    const g = cv.getContext("2d");
    const CREAM = "#f6f1e7", INK = "#1f1d1a", MUTED = "#6f685d", LINE = "#e2d9c8", UP = "#1f7a4d", DOWN = "#b23a2e";
    const col = x => !App.isNum(x) ? INK : x >= 0 ? UP : DOWN;
    const sans = "'Plus Jakarta Sans', system-ui, sans-serif", serif = "Literata, Georgia, serif";
    g.fillStyle = CREAM; g.fillRect(0, 0, W, H);
    g.strokeStyle = LINE; g.lineWidth = 4; rr(g, 40, 40, W - 80, H - 80, 48); g.stroke();
    g.fillStyle = INK; g.font = `700 40px ${sans}`; g.textBaseline = "alphabetic"; g.fillText("Meja Pantau IDX", 100, 150);
    g.fillStyle = MUTED; g.font = `500 34px ${sans}`; g.textAlign = "right"; g.fillText(date, W - 100, 150); g.textAlign = "left";
    g.fillText("Return portofolio" + (d.start ? " sejak " + d.start : ""), 100, 300);
    g.fillStyle = col(d.ret); g.font = `700 200px ${serif}`; g.fillText(pctS(d.ret), 92, 500);
    g.fillStyle = INK; g.font = `600 40px ${sans}`;
    let vs = "IHSG " + pctS(d.ihsg); if(d.ret != null && d.ihsg != null) vs += ` · ${d.ret >= d.ihsg ? "unggul" : "tertinggal"} ${App.pct(Math.abs(d.ret - d.ihsg))} poin`;
    g.fillText(vs, 100, 590);
    if(!hideRp){ g.fillStyle = MUTED; g.font = `500 36px ${sans}`; g.fillText(`P/L ${d.pl > 0 ? "+" : ""}${rp(d.pl)} · Nilai ${rp(d.nilai)}`, 100, 650); }
    g.fillStyle = LINE; g.fillRect(100, 720, W - 200, 3);
    g.fillStyle = MUTED; g.font = `600 32px ${sans}`; g.fillText("TOP 3 SAHAM", 100, 800);
    top.forEach((x, j) => {
      const y = 900 + j * 110;
      g.fillStyle = INK; g.font = `700 60px ${serif}`; g.fillText(`${j + 1}. ${x.kode}`, 100, y);
      g.fillStyle = col(x.ret); g.textAlign = "right"; g.fillText(pctS(x.ret), W - 100, y); g.textAlign = "left";
    });
    g.fillStyle = MUTED; g.font = `500 28px ${sans}`; g.fillText("Bukan rekomendasi beli atau jual.", 100, H - 110);
    const url = cv.toDataURL("image/png");
    window.__portoLastPNG = url.length;
    const a = document.createElement("a"); a.href = url; a.download = "portofolio-" + new Date().toISOString().slice(0, 10) + ".png";
    document.body.appendChild(a); a.click(); a.remove();
  }
  function rr(g, x, y, w, h, r){ g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }

  let elRef = null;
  function update(){
    const el = elRef; if(!el) return;
    const o = load(); ensureIhsg(o.start, o.rows);
    const d = compute(), q = s => el.querySelector(`[data-p="${s}"]`);
    // jangan timpa tabel saat pengguna sedang mengedit input di dalamnya
    if(!(document.activeElement && q("table").contains(document.activeElement))) q("table").innerHTML = table(d);
    q("sum").innerHTML = summary(d); q("donut").innerHTML = donut(d); q("card").innerHTML = shareCard(d); q("msg").textContent = msg;
  }

  function injectCSS(){
    if(document.getElementById("porto-css")) return;
    const s = document.createElement("style"); s.id = "porto-css";
    s.textContent = `
#panel-porto .porto-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;align-items:end;margin:8px 0}
#panel-porto .porto-form label,#panel-porto .porto-start{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted)}
#panel-porto input{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:8px 10px;min-width:0}
#panel-porto .porto-start{flex-direction:row;align-items:center;gap:8px}
#panel-porto .porto-btn{font:inherit;font-weight:600;border:1px solid var(--line2);background:var(--surface);color:var(--ink);border-radius:10px;padding:9px 14px;cursor:pointer}
#panel-porto .porto-btn.solid{background:var(--btn);color:var(--btn-fg);border-color:var(--btn)}
#panel-porto .porto-tools{flex-wrap:wrap;gap:10px;margin-bottom:10px}
#panel-porto .porto-in{width:84px;padding:4px 6px;text-align:right}
#panel-porto .porto-code{font:inherit;font-weight:700;background:none;border:0;color:var(--ink);cursor:pointer;padding:0}
#panel-porto .porto-del{background:none;border:0;color:var(--muted);font-size:18px;cursor:pointer}
#panel-porto .porto-two{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
#panel-porto .porto-donut{display:flex;flex-wrap:wrap;gap:16px;align-items:center}
#panel-porto .porto-donut svg{width:160px;height:160px;flex:none}
#panel-porto .porto-dn1{font:700 26px var(--serif);fill:var(--ink)}#panel-porto .porto-dn2{font:12px var(--font);fill:var(--muted)}
#panel-porto .porto-donut ul{list-style:none;margin:0;padding:0;flex:1;min-width:140px}
#panel-porto .porto-donut li{display:flex;align-items:center;gap:8px;padding:3px 0;font-size:14px}
#panel-porto .porto-donut li i{width:10px;height:10px;border-radius:3px;flex:none}#panel-porto .porto-donut li b{margin-left:auto}
#panel-porto .porto-share{--c-bg:#f6f1e7;--c-ink:#1f1d1a;--c-mut:#6f685d;--c-line:#e2d9c8;--c-up:#1f7a4d;--c-down:#b23a2e;
 background:var(--c-bg);color:var(--c-ink);border:2px solid var(--c-line);border-radius:22px;padding:22px;max-width:420px;margin-top:12px;aspect-ratio:4/5;display:flex;flex-direction:column;box-sizing:border-box}
#panel-porto .porto-share .up{color:var(--c-up)}#panel-porto .porto-share .down{color:var(--c-down)}
#panel-porto .porto-sh-top{display:flex;justify-content:space-between;font-size:13px;color:var(--c-mut)}#panel-porto .porto-sh-top span:first-child{font-weight:700;color:var(--c-ink)}
#panel-porto .porto-sh-lbl{margin-top:28px;font-size:13px;color:var(--c-mut)}
#panel-porto .porto-sh-big{font:700 clamp(48px,16vw,72px)/1.05 var(--serif);margin:4px 0}
#panel-porto .porto-sh-vs{font-weight:600;font-size:14px}#panel-porto .porto-sh-rp{font-size:13px;color:var(--c-mut);margin-top:4px}
#panel-porto .porto-sh-list{border-top:1px solid var(--c-line);margin-top:18px;padding-top:12px;display:grid;gap:8px}
#panel-porto .porto-sh-list div{display:flex;justify-content:space-between;font:700 20px var(--serif)}
#panel-porto .porto-sh-foot{margin-top:auto;font-size:11px;color:var(--c-mut)}`;
    document.head.appendChild(s);
  }

  App.register("porto", {
    render(el){
      injectCSS();
      if(!built || !el.querySelector('[data-p="form"]')){ shell(el); built = true; }
      elRef = el; update();
    },
  });
})();
