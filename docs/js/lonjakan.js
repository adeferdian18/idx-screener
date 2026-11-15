/* Lonjakan transaksi: saham dengan volume hari ini jauh di atas rata-rata (Meja Pantau IDX).
   Data dari pullback.json (Sesi 1 dan Penutupan). Yahoo tidak memberi jumlah transaksi (frekuensi),
   jadi yang dipakai adalah volume lembar dibanding rata-rata 5 hari sebelumnya. */
(function(){
  let data = null, loading = false;
  const st = { min: "2", liq: "1", arah: "semua" };
  try{ Object.assign(st, JSON.parse(App.store.get("lj") || "{}")); }catch{}

  function rows(){
    const min = +st.min;
    let xs = (data?.rows || []).filter(r => App.isNum(r.vol_ratio) && r.vol_ratio >= min && r.vol_today > 0 && !r.no_trade_today);
    if(st.liq === "1") xs = xs.filter(r => (r.value_today || 0) >= 1e9);
    if(st.arah === "naik") xs = xs.filter(r => r.chg > 0);
    if(st.arah === "turun") xs = xs.filter(r => r.chg < 0);
    return xs.sort((a, b) => b.vol_ratio - a.vol_ratio);
  }
  function rp(v){
    if(!App.isNum(v)) return "–";
    return v >= 1e12 ? App.fmt(v / 1e12, 1) + " T" : v >= 1e9 ? App.fmt(v / 1e9, 1) + " M" : App.fmt(v / 1e6, 0) + " jt";
  }
  function seg(key, opts){
    return `<span class="seg">${opts.map(([v, l]) => `<button data-lj="${key}" data-v="${v}" aria-pressed="${st[key] === v}">${l}</button>`).join("")}</span>`;
  }
  function draw(el){
    const xs = rows(), m = data?.market || {};
    const naik = xs.filter(r => r.chg > 0).length, turun = xs.filter(r => r.chg < 0).length;
    el.innerHTML = `
      <div class="card">
        <h2>Lonjakan transaksi</h2>
        <p>Saham yang volumenya hari ini berlipat dibanding rata-rata 5 hari sebelumnya. Lonjakan sambil naik sering menandakan akumulasi; lonjakan sambil turun sering distribusi. Data ${App.esc(m.session_label || "")} ${App.esc(m.as_of || "")}.</p>
        <div class="toolbar">
          ${seg("min", [["1.5","≥1,5×"],["2","≥2×"],["3","≥3×"],["5","≥5×"]])}
          ${seg("arah", [["semua","Semua"],["naik","Naik"],["turun","Turun"]])}
          <label class="ck"><input type="checkbox" id="lj-liq" ${st.liq === "1" ? "checked" : ""}> Nilai transaksi ≥ Rp1 M</label>
          <span class="hint">${xs.length} saham · <span class="up">${naik} naik</span> · <span class="down">${turun} turun</span></span>
        </div>
        <div class="table-wrap"><table><thead><tr><th>Saham</th><th>Harga</th><th>Hari ini</th><th>Lonjakan</th><th>Volume (lembar)</th><th>Nilai</th><th>Sinyal pullback</th></tr></thead><tbody>
          ${xs.length ? xs.slice(0, 150).map(r => `<tr data-ljc="${App.esc(r.code)}" style="cursor:pointer">
            <td style="text-align:left"><b>${App.esc(r.code)}</b><div class="hint">${App.esc((r.name || "").slice(0, 28))}</div></td>
            <td>${App.fmt(r.close)}</td>
            <td class="${App.cls(r.chg)}">${App.pct(r.chg)}</td>
            <td><b>${App.fmt(r.vol_ratio, 1)}×</b><span class="bar"><i style="width:${Math.min(100, r.vol_ratio / 10 * 100)}%"></i></span></td>
            <td>${App.fmt(r.vol_today)}</td>
            <td>${rp(r.value_today)}</td>
            <td>${r.status && r.status !== "Tidak ada sinyal" ? App.esc(r.status) : "–"}</td>
          </tr>`).join("") : `<tr><td colspan="7" style="text-align:left">Tidak ada saham yang memenuhi filter ini.</td></tr>`}
        </tbody></table></div>
        <p class="hint">Yahoo Finance tidak menyediakan jumlah transaksi (frekuensi), jadi ukuran yang dipakai adalah volume lembar. Klik baris untuk grafik dan rincian. Alat bantu analisis, bukan rekomendasi beli atau jual.</p>
      </div>`;
  }
  function save(){ App.store.set("lj", JSON.stringify(st)); }

  App.register("lonjakan", {
    render(el){
      if(!data){
        if(!loading){
          loading = true;
          el.innerHTML = `<div class="card"><p>Memuat data…</p></div>`;
          App.getJSON("pullback").then(d => { data = d; loading = false; App.renderModule("lonjakan"); })
            .catch(() => { loading = false; el.innerHTML = `<div class="card"><p>Data belum tersedia.</p></div>`; });
        }
        return;
      }
      draw(el);
      if(!el.dataset.wired){
        el.dataset.wired = "1";
        el.addEventListener("click", e => {
          const b = e.target.closest("[data-lj]");
          if(b){ st[b.dataset.lj] = b.dataset.v; save(); draw(el); return; }
          const tr = e.target.closest("[data-ljc]");
          if(tr) App.openStock(tr.dataset.ljc);
        });
        el.addEventListener("change", e => {
          if(e.target.id === "lj-liq"){ st.liq = e.target.checked ? "1" : "0"; save(); draw(el); }
        });
      }
    }
  });
})();
