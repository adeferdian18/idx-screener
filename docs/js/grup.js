/* Grup konglomerat: kinerja rata-rata saham per grup usaha (Meja Pantau IDX).
   Pemetaan grup -> saham dari data/grup.json (disusun manual dari informasi publik). */
(function(){
  let data = null, loading = false, failed = false, shell = null;
  const st = { urut: "1d", q: "", buka: "" };
  try{ Object.assign(st, JSON.parse(App.store.get("grup") || "{}")); }catch{}
  st.q = "";

  if(!document.getElementById("grup-css")){
    const s = document.createElement("style"); s.id = "grup-css";
    s.textContent = `
#panel-grup .grup-list{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));margin-top:12px}
#panel-grup .grup-item{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px 14px;min-width:0}
#panel-grup .grup-item.grup-open{grid-column:1/-1;border-color:var(--line2)}
#panel-grup .grup-head{all:unset;cursor:pointer;display:block;width:100%;box-sizing:border-box}
#panel-grup .grup-head:focus-visible{outline:2px solid var(--line2);border-radius:8px}
#panel-grup .grup-nama{font-family:var(--serif);font-size:1.05rem;font-weight:600;color:var(--ink)}
#panel-grup .grup-sub{color:var(--muted);font-size:.82rem;margin:2px 0 8px}
#panel-grup .grup-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}
#panel-grup .grup-stats span{display:block;color:var(--faint);font-size:.7rem}
#panel-grup .grup-stats b{font-size:.92rem}
#panel-grup .grup-detail{margin-top:10px}
#panel-grup .grup-search{flex:1 1 180px;min-width:0}`;
    document.head.appendChild(s);
  }

  const num = App.isNum;
  function avg(xs){ xs = xs.filter(num); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; }
  function rowsOf(g){
    const m = App.S.momentum?.rows || [], q = App.S.quotes?.stocks || {};
    const by = rowsOf.idx && rowsOf.src === m ? rowsOf.idx : (rowsOf.src = m, rowsOf.idx = Object.fromEntries(m.map(r => [r.kode, r])));
    return g.saham.map(k => {
      const r = by[k] || {}, lq = q[k];
      return { kode: k, nama: r.nama, harga: num(lq?.last) ? lq.last : r.harga,
        d1: num(lq?.chg) ? lq.chg : r.chg_1d, m1: r.ret_1m, m3: r.ret_3m, rs: r.rs_rating, tt: r.lolos_tt, ada: !!by[k] };
    });
  }
  function groups(){
    const q = st.q.trim().toUpperCase();
    let gs = (data?.grup || []).map(g => {
      const rs = rowsOf(g);
      return { g, rs, d1: avg(rs.map(r => r.d1)), m1: avg(rs.map(r => r.m1)), m3: avg(rs.map(r => r.m3)), rs_: avg(rs.map(r => r.rs)) };
    });
    if(q) gs = gs.filter(x => x.g.nama.toUpperCase().includes(q) || (x.g.pengendali || "").toUpperCase().includes(q) || x.g.saham.some(s => s.includes(q)));
    const key = { "1d": "d1", "1m": "m1", "3m": "m3", rs: "rs_" }[st.urut];
    return gs.sort((a, b) => (num(b[key]) ? b[key] : -1e9) - (num(a[key]) ? a[key] : -1e9));
  }
  function card(x){
    const open = st.buka === x.g.nama, n = x.rs.filter(r => r.ada).length;
    const id = "grup-d-" + x.g.nama.replace(/[^a-z0-9]/gi, "");
    return `<div class="grup-item${open ? " grup-open" : ""}">
      <button class="grup-head" data-grup="${App.esc(x.g.nama)}" aria-expanded="${open}" aria-controls="${id}">
        <div class="grup-nama">${App.esc(x.g.nama)}</div>
        <div class="grup-sub">${App.esc(x.g.pengendali || "")} · ${x.g.saham.length} saham${n < x.g.saham.length ? ` (${n} ada data)` : ""}</div>
        <div class="grup-stats">
          <div><span>Hari ini</span><b class="${App.cls(x.d1)}">${num(x.d1) ? App.pct(x.d1) : "–"}</b></div>
          <div><span>1 bulan</span><b class="${App.cls(x.m1)}">${num(x.m1) ? App.pct(x.m1) : "–"}</b></div>
          <div><span>3 bulan</span><b class="${App.cls(x.m3)}">${num(x.m3) ? App.pct(x.m3) : "–"}</b></div>
          <div><span>RS rata²</span><b>${num(x.rs_) ? App.fmt(x.rs_, 0) : "–"}</b></div>
        </div>
      </button>
      ${open ? `<div class="grup-detail table-wrap" id="${id}"><table><thead><tr><th>Saham</th><th>Harga</th><th>Hari ini</th><th>3 bulan</th><th>RS</th><th>Trend Template</th></tr></thead><tbody>
        ${x.rs.map(r => `<tr data-code="${App.esc(r.kode)}" style="cursor:pointer">
          <td style="text-align:left"><b>${App.esc(r.kode)}</b><div class="hint">${App.esc((r.nama || (r.ada ? "" : "tidak ada data")).slice(0, 26))}</div></td>
          <td>${num(r.harga) ? App.fmt(r.harga) : "–"}</td>
          <td class="${App.cls(r.d1)}">${num(r.d1) ? App.pct(r.d1) : "–"}</td>
          <td class="${App.cls(r.m3)}">${num(r.m3) ? App.pct(r.m3) : "–"}</td>
          <td>${num(r.rs) ? App.fmt(r.rs, 0) : "–"}</td>
          <td>${r.tt ? '<span class="badge good">✓</span>' : "–"}</td>
        </tr>`).join("")}
      </tbody></table></div>` : ""}
    </div>`;
  }
  function drawList(el){
    const gs = groups(), box = el.querySelector(".grup-list");
    box.innerHTML = gs.length ? gs.map(card).join("") : `<p class="hint">Tidak ada grup atau saham yang cocok.</p>`;
    el.querySelector(".grup-count").textContent = `${gs.length} grup`;
    el.querySelectorAll("[data-urut]").forEach(b => b.setAttribute("aria-pressed", b.dataset.urut === st.urut));
  }
  function save(){ App.store.set("grup", JSON.stringify({ urut: st.urut, buka: st.buka })); }
  function buildShell(el){
    el.innerHTML = `<div class="card">
      <h2>Grup konglomerat</h2>
      <p>Kinerja rata-rata saham per grup usaha besar. Klik grup untuk melihat sahamnya, klik saham untuk grafik.</p>
      <div class="toolbar">
        <span class="seg">${[["1d","Hari ini"],["1m","1 bulan"],["3m","3 bulan"],["rs","RS"]].map(([v, l]) => `<button data-urut="${v}" aria-pressed="${st.urut === v}">${l}</button>`).join("")}</span>
        <input class="search grup-search" type="search" placeholder="Cari grup atau kode saham" aria-label="Cari grup atau kode saham">
        <span class="hint grup-count"></span>
      </div>
      <div class="grup-list"></div>
      <p class="hint">${App.esc(data.catatan || "")} (diperbarui ${App.esc(data.updated || "")}). Kepemilikan bisa berubah; rata-rata tidak berbobot. Alat bantu analisis, bukan rekomendasi beli atau jual.</p>
    </div>`;
    el.querySelector(".grup-search").addEventListener("input", e => { st.q = e.target.value; drawList(el); });
    el.addEventListener("click", e => {
      const u = e.target.closest("[data-urut]");
      if(u){ st.urut = u.dataset.urut; save(); drawList(el); return; }
      const h = e.target.closest("[data-grup]");
      if(h){ st.buka = st.buka === h.dataset.grup ? "" : h.dataset.grup; save(); drawList(el); }
    });
    shell = el;
  }

  App.register("grup", {
    render(el){
      if(!data){
        if(failed){ el.innerHTML = `<div class="card"><p>Data grup belum tersedia.</p></div>`; return; }
        if(!loading){
          loading = true;
          App.getJSON("grup").then(d => { data = d; loading = false; App.renderModule("grup"); })
            .catch(() => { loading = false; failed = true; App.renderModule("grup"); });
        }
        el.innerHTML = `<div class="card"><p>Memuat data…</p></div>`; return;
      }
      if(!App.S.momentum?.rows){ shell = null; el.innerHTML = `<div class="card"><h2>Grup konglomerat</h2><p>Memuat data momentum…</p></div>`; return; }
      if(shell !== el || !el.querySelector(".grup-list")) buildShell(el);
      drawList(el);
    },
  });
})();
