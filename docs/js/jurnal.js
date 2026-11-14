/* Modul "jurnal": jurnal trading yang disimpan di browser (App.store key "jurnal"). */
(() => {
  const KEY = "jurnal", FEE_BELI = 0.0015, FEE_JUAL = 0.0025;
  let closingId = null; // id entri yang sedang ditutup (form harga keluar terbuka)

  const load = () => { try{ const a = JSON.parse(App.store.get(KEY) || "[]"); return Array.isArray(a) ? a : []; }catch{ return []; } };
  const save = a => App.store.set(KEY, JSON.stringify(a));
  const num = v => { const n = typeof v === "number" ? v : parseFloat(String(v ?? "").replace(",", ".")); return isFinite(n) ? n : null; };
  const today = () => { const d = new Date(); return new Date(d - d.getTimezoneOffset()*6e4).toISOString().slice(0,10); };
  const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2,6);

  function price(kode){
    const q = App.S.quotes?.stocks?.[kode]?.last;
    if(App.isNum(q)) return q;
    const r = App.S.momentum?.rows?.find(x => x.kode === kode);
    return r && App.isNum(r.harga) ? r.harga : null;
  }
  // P/L bersih dan R untuk harga keluar tertentu
  function calc(e, keluar){
    const en = num(e.entry), sl = num(e.sl), lot = num(e.lot), k = num(keluar);
    if(en == null || k == null || lot == null) return { pl:null, r:null };
    const sh = lot * 100;
    const pl = sh*(k - en) - sh*en*FEE_BELI - sh*k*FEE_JUAL;
    const risk = sl != null ? en - sl : null;
    return { pl, r: risk ? (k - en) / risk : null };
  }

  const CSS = `
#panel-jurnal .jurnal-wrap{display:grid;gap:16px}
#panel-jurnal .jurnal-form{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;align-items:end}
#panel-jurnal .jurnal-form label{display:grid;gap:4px;font-size:12px;color:var(--muted)}
#panel-jurnal .jurnal-form input,#panel-jurnal .jurnal-form select,#panel-jurnal .jurnal-close input{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--ink);font:inherit}
#panel-jurnal .jurnal-form .jurnal-wide{grid-column:1/-1}
#panel-jurnal .jurnal-btn{padding:7px 12px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--ink);font:inherit;font-size:13px;cursor:pointer}
#panel-jurnal .jurnal-btn:hover{border-color:var(--line2)}
#panel-jurnal .jurnal-btn.solid{background:var(--btn);color:var(--btn-fg);border-color:var(--btn)}
#panel-jurnal .jurnal-btn.danger{color:var(--down)}
#panel-jurnal .jurnal-pos{border:1px solid var(--line);border-radius:12px;padding:12px;display:grid;gap:10px;background:var(--bg2)}
#panel-jurnal .jurnal-pos-head{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
#panel-jurnal .jurnal-code{font-weight:700;background:none;border:0;padding:0;color:var(--ink);font:inherit;font-weight:700;font-size:16px;cursor:pointer;text-decoration:underline;text-decoration-color:var(--line2)}
#panel-jurnal .jurnal-acts{display:flex;flex-wrap:wrap;gap:6px}
#panel-jurnal .jurnal-close{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
#panel-jurnal .jurnal-close input{width:130px}
#panel-jurnal .jurnal-list{display:grid;gap:10px}
#panel-jurnal .pill.jurnal-sl{background:var(--warn-soft);color:var(--down)}
#panel-jurnal .pill.jurnal-t1{background:var(--good-soft);color:var(--up)}
#panel-jurnal .jurnal-eq{width:100%;height:120px;display:block;margin-top:12px}
#panel-jurnal .jurnal-note{color:var(--muted);font-size:13px;overflow-wrap:anywhere}
`;

  function shell(el){
    if(!document.getElementById("jurnal-css")){ const s = document.createElement("style"); s.id = "jurnal-css"; s.textContent = CSS; document.head.appendChild(s); }
    el.innerHTML = `<div class="jurnal-wrap">
  <div class="card"><h2>Statistik</h2><p>Dihitung dari transaksi berstatus selesai, sudah termasuk fee beli 0,15% dan jual 0,25%.</p><div data-j="stats"></div></div>
  <div class="card"><h2>Posisi terbuka &amp; rencana</h2><div data-j="open" class="jurnal-list"></div></div>
  <div class="card"><h2>Tambah catatan</h2>
    <form class="jurnal-form" data-j="form" autocomplete="off">
      <label>Kode<input name="kode" required maxlength="6" placeholder="BBCA" style="text-transform:uppercase"></label>
      <label>Tanggal<input name="tgl" type="date" required></label>
      <label>Entry<input name="entry" type="number" step="any" min="0" required></label>
      <label>Stop loss<input name="sl" type="number" step="any" min="0"></label>
      <label>Target 1<input name="t1" type="number" step="any" min="0"></label>
      <label>Lot<input name="lot" type="number" step="1" min="1" required></label>
      <label>Status<select name="status"><option value="rencana">Rencana</option><option value="terbuka">Terbuka</option></select></label>
      <label class="jurnal-wide">Catatan<input name="catatan" maxlength="300" placeholder="Alasan masuk, setup, dll."></label>
      <div><button class="jurnal-btn solid" type="submit">Simpan</button></div>
    </form>
  </div>
  <div class="card"><h2>Riwayat</h2>
    <div class="toolbar"><button class="jurnal-btn" type="button" data-j="export">Ekspor CSV</button>
      <label class="jurnal-btn" style="display:inline-block">Impor CSV/JSON<input type="file" accept=".csv,.json,application/json,text/csv" data-j="import" hidden></label></div>
    <p class="hint">Data jurnal hanya tersimpan di browser ini. Ekspor secara berkala untuk cadangan atau pindah perangkat.</p>
    <div data-j="hist"></div>
  </div>
</div>`;
    el.querySelector('[name=tgl]').value = today();
    el.dataset.jShell = "1";
    el.addEventListener("submit", onSubmit);
    el.addEventListener("click", onClick);
    el.querySelector('[data-j=import]').addEventListener("change", onImport);
  }

  function onSubmit(ev){
    const f = ev.target, el = f.closest("#panel-jurnal");
    ev.preventDefault();
    if(f.dataset.j === "form"){
      const d = Object.fromEntries(new FormData(f));
      const a = load();
      a.push({ id:newId(), tgl:d.tgl || today(), kode:String(d.kode).trim().toUpperCase().replace(".JK",""),
        entry:num(d.entry), sl:num(d.sl), t1:num(d.t1), t2:null, lot:num(d.lot), catatan:d.catatan || "", status:d.status || "rencana" });
      save(a); f.reset(); f.querySelector('[name=tgl]').value = today(); update(el);
    } else if(f.dataset.j === "close"){
      const k = num(f.querySelector("input").value);
      if(k == null || k <= 0){ f.querySelector("input").focus(); return; }
      const a = load(), e = a.find(x => x.id === f.dataset.id);
      if(e){ e.status = "selesai"; e.harga_keluar = k; e.tgl_keluar = today(); save(a); }
      closingId = null; update(el);
    }
  }

  function onClick(ev){
    const b = ev.target.closest("[data-act]"), el = ev.currentTarget;
    if(ev.target.closest('[data-j=export]')) return exportCSV();
    if(!b) return;
    const id = b.dataset.id, act = b.dataset.act, a = load(), e = a.find(x => x.id === id);
    if(act === "batal-tutup"){ closingId = null; return update(el); }
    if(!e) return;
    if(act === "mulai"){ e.status = "terbuka"; if(!e.tgl) e.tgl = today(); }
    else if(act === "tutup"){ closingId = id; return update(el); }
    else if(act === "batal"){ e.status = "batal"; e.tgl_keluar = today(); }
    else if(act === "hapus"){ if(!confirm(`Hapus catatan ${e.kode}? Tindakan ini tidak bisa dibatalkan.`)) return; a.splice(a.indexOf(e), 1); }
    save(a); update(el);
  }

  function stats(a){
    const done = a.filter(e => e.status === "selesai" && num(e.harga_keluar) != null)
      .sort((x,y) => String(x.tgl_keluar||x.tgl).localeCompare(String(y.tgl_keluar||y.tgl)));
    const res = done.map(e => ({ e, ...calc(e, e.harga_keluar) })).filter(x => x.pl != null);
    if(!res.length) return `<p class="hint">Belum ada transaksi selesai. Tutup posisi untuk melihat statistik.</p>`;
    const wins = res.filter(x => x.pl > 0), loss = res.filter(x => x.pl < 0);
    const gp = wins.reduce((s,x) => s + x.pl, 0), gl = -loss.reduce((s,x) => s + x.pl, 0);
    const rs = res.filter(x => x.r != null), avgR = rs.length ? rs.reduce((s,x) => s + x.r, 0) / rs.length : null;
    const tot = gp - gl, best = res.reduce((m,x) => x.pl > m.pl ? x : m), worst = res.reduce((m,x) => x.pl < m.pl ? x : m);
    const pf = gl > 0 ? App.fmt(gp/gl, 2) : (gp > 0 ? "∞" : "–");
    const cell = (l, v, c="") => `<div class="cell"><span>${l}</span><b class="${c}">${v}</b></div>`;
    // kurva ekuitas
    let cum = 0; const pts = [0, ...res.map(x => cum += x.pl)];
    const W = 600, H = 120, P = 6, mn = Math.min(...pts), mx = Math.max(...pts), rg = (mx - mn) || 1;
    const X = i => P + i * (W - 2*P) / Math.max(1, pts.length - 1), Y = v => H - P - (v - mn) * (H - 2*P) / rg;
    const path = pts.map((v,i) => `${i?"L":"M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join("");
    const col = tot >= 0 ? "var(--up)" : "var(--down)";
    return `<div class="grid">
      ${cell("Transaksi selesai", App.fmt(res.length))}
      ${cell("Win rate", App.pct(wins.length / res.length, 0, false))}
      ${cell("Rata-rata R", avgR == null ? "–" : (avgR > 0 ? "+" : "") + App.fmt(avgR, 2) + "R", App.cls(avgR))}
      ${cell("Total P/L", "Rp " + App.fmt(tot), App.cls(tot))}
      ${cell("Profit factor", pf)}
      ${cell("Terbaik", `${App.esc(best.e.kode)} · Rp ${App.fmt(best.pl)}`, App.cls(best.pl))}
      ${cell("Terburuk", `${App.esc(worst.e.kode)} · Rp ${App.fmt(worst.pl)}`, App.cls(worst.pl))}
    </div>
    <svg class="jurnal-eq" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Kurva ekuitas kumulatif">
      <line x1="${P}" x2="${W-P}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}" stroke="var(--line2)" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>
      <path d="${path}" fill="none" stroke="${col}" stroke-width="2" vector-effect="non-scaling-stroke"/>
    </svg><p class="hint">Kurva ekuitas: P/L kumulatif per transaksi selesai.</p>`;
  }

  function openList(a){
    const list = a.filter(e => e.status === "rencana" || e.status === "terbuka");
    if(!list.length) return `<p class="hint">Belum ada posisi terbuka atau rencana. Tambahkan lewat form di bawah atau dari Kalkulator.</p>`;
    return list.map(e => {
      const p = price(e.kode), { pl, r } = calc(e, p), sl = num(e.sl), t1 = num(e.t1);
      let flag = "";
      if(p != null && sl != null && p <= sl) flag = `<span class="pill jurnal-sl">kena SL</span>`;
      else if(p != null && t1 != null && p >= t1) flag = `<span class="pill jurnal-t1">capai T1</span>`;
      const cell = (l, v, c="") => `<div class="cell"><span>${l}</span><b class="${c}">${v}</b></div>`;
      const closing = closingId === e.id ? `<form class="jurnal-close" data-j="close" data-id="${App.esc(e.id)}">
          <span class="hint">Harga keluar</span><input type="number" step="any" min="0" required value="${p ?? num(e.entry) ?? ""}">
          <button class="jurnal-btn solid" type="submit">Simpan</button><button class="jurnal-btn" type="button" data-act="batal-tutup" data-id="${App.esc(e.id)}">Batal</button></form>` : "";
      const id = App.esc(e.id);
      return `<div class="jurnal-pos">
        <div class="jurnal-pos-head"><button class="jurnal-code" data-code="${App.esc(e.kode)}">${App.esc(e.kode)}</button>
          <span class="pill">${e.status === "terbuka" ? "Terbuka" : "Rencana"}</span>${flag}<span class="hint">${App.esc(e.tgl || "")}</span></div>
        <div class="grid">${cell("Entry", App.fmt(num(e.entry)))}${cell("SL", App.fmt(sl))}${cell("T1", App.fmt(t1))}${cell("Lot", App.fmt(num(e.lot)))}
          ${cell("Harga kini", App.fmt(p))}${cell("P/L berjalan", pl == null ? "–" : "Rp " + App.fmt(pl), App.cls(pl))}${cell("R", r == null ? "–" : App.fmt(r, 2) + "R", App.cls(r))}</div>
        ${e.catatan ? `<div class="jurnal-note">${App.esc(e.catatan)}</div>` : ""}
        <div class="jurnal-acts">
          ${e.status === "rencana" ? `<button class="jurnal-btn" data-act="mulai" data-id="${id}">Mulai</button>` : ""}
          <button class="jurnal-btn" data-act="tutup" data-id="${id}">Tutup</button>
          <button class="jurnal-btn" data-act="batal" data-id="${id}">Batal</button>
          <button class="jurnal-btn danger" data-act="hapus" data-id="${id}">Hapus</button>
        </div>${closing}</div>`;
    }).join("");
  }

  function history(a){
    const list = a.filter(e => e.status === "selesai" || e.status === "batal")
      .sort((x,y) => String(y.tgl_keluar||y.tgl).localeCompare(String(x.tgl_keluar||x.tgl)));
    if(!list.length) return `<p class="hint">Belum ada riwayat.</p>`;
    return `<div class="table-wrap"><table><thead><tr><th>Kode</th><th>Status</th><th>Masuk</th><th>Keluar</th><th>Entry</th><th>Harga keluar</th><th>Lot</th><th>P/L (Rp)</th><th>R</th><th></th></tr></thead><tbody>
      ${list.map(e => { const { pl, r } = e.status === "selesai" ? calc(e, e.harga_keluar) : {};
        return `<tr><td><button class="jurnal-code" data-code="${App.esc(e.kode)}">${App.esc(e.kode)}</button></td><td>${e.status === "selesai" ? "Selesai" : "Batal"}</td>
        <td>${App.esc(e.tgl || "")}</td><td>${App.esc(e.tgl_keluar || "")}</td><td>${App.fmt(num(e.entry))}</td><td>${App.fmt(num(e.harga_keluar))}</td><td>${App.fmt(num(e.lot))}</td>
        <td class="${App.cls(pl)}">${App.fmt(pl)}</td><td class="${App.cls(r)}">${r == null ? "–" : App.fmt(r, 2)}</td>
        <td><button class="jurnal-btn danger" data-act="hapus" data-id="${App.esc(e.id)}">Hapus</button></td></tr>`; }).join("")}
    </tbody></table></div>`;
  }

  const COLS = ["id","tgl","kode","entry","sl","t1","t2","lot","catatan","status","tgl_keluar","harga_keluar"];
  function exportCSV(){
    const q = v => { const s = v == null ? "" : String(v); return /[",;\n]/.test(s) ? `"${s.replace(/"/g,'""')}"` : s; };
    const csv = [COLS.join(","), ...load().map(e => COLS.map(c => q(e[c])).join(","))].join("\n");
    const url = URL.createObjectURL(new Blob(["﻿" + csv], { type:"text/csv;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = `jurnal-${today()}.csv`;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function parseCSV(t){
    const rows = []; let row = [], f = "", q = false;
    for(let i = 0; i < t.length; i++){
      const c = t[i];
      if(q){ if(c === '"'){ if(t[i+1] === '"'){ f += '"'; i++; } else q = false; } else f += c; }
      else if(c === '"') q = true; else if(c === ","){ row.push(f); f = ""; }
      else if(c === "\n" || c === "\r"){ if(c === "\r" && t[i+1] === "\n") i++; row.push(f); rows.push(row); row = []; f = ""; }
      else f += c;
    }
    if(f || row.length){ row.push(f); rows.push(row); }
    const [h, ...body] = rows.filter(r => r.some(x => x !== ""));
    if(!h) return [];
    const hd = h.map(x => x.trim().replace(/^﻿/, ""));
    return body.map(r => Object.fromEntries(hd.map((k,i) => [k, r[i] ?? ""])));
  }
  function onImport(ev){
    const file = ev.target.files?.[0], el = ev.target.closest("#panel-jurnal");
    if(!file) return;
    file.text().then(t => {
      let rows = /\.json$/i.test(file.name) || /^\s*[\[{]/.test(t) ? JSON.parse(t) : parseCSV(t.replace(/^﻿/, ""));
      if(!Array.isArray(rows)) rows = rows?.jurnal || [];
      const ST = ["rencana","terbuka","selesai","batal"];
      const clean = rows.filter(r => r && r.kode).map(r => ({
        id: String(r.id || newId()), tgl: String(r.tgl || ""), kode: String(r.kode).trim().toUpperCase(),
        entry:num(r.entry), sl:num(r.sl), t1:num(r.t1), t2:num(r.t2), lot:num(r.lot), catatan:String(r.catatan || ""),
        status: ST.includes(r.status) ? r.status : "rencana", tgl_keluar: r.tgl_keluar ? String(r.tgl_keluar) : undefined, harga_keluar: num(r.harga_keluar) ?? undefined }));
      const a = load(), ids = new Set(a.map(e => e.id)); let n = 0;
      clean.forEach(e => { if(!ids.has(e.id)){ a.push(e); ids.add(e.id); n++; } });
      save(a); update(el); alert(`${n} catatan diimpor${clean.length - n ? `, ${clean.length - n} dilewati (sudah ada)` : ""}.`);
    }).catch(err => alert("Gagal membaca file: " + err.message)).finally(() => { ev.target.value = ""; });
  }

  function update(el){
    const a = load();
    // jangan menimpa form tutup yang sedang diketik
    const typing = el.querySelector('[data-j=close] input') === document.activeElement;
    el.querySelector('[data-j=stats]').innerHTML = stats(a);
    if(!typing) el.querySelector('[data-j=open]').innerHTML = openList(a);
    el.querySelector('[data-j=hist]').innerHTML = history(a);
  }

  App.register("jurnal", {
    render(el){
      if(!el.dataset.jShell) shell(el);
      update(el);
    },
  });
})();
