/* Setup A+: hasil backtest_sweep.py + kandidat hari ini dari momentum.json (field setup_a). */
(() => {
  const css = `
#panel-setup .sa-rule{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px;margin:10px 0 4px}
#panel-setup .sa-rule div{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:10px 12px;font-size:13.5px}
#panel-setup .sa-rule b{display:block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);margin-bottom:2px}
#panel-setup .sa-gate{display:flex;gap:12px;align-items:center;border-radius:12px;padding:12px 14px;margin:12px 0;font-size:14.5px}
#panel-setup .sa-gate.ok{background:var(--good-soft);color:var(--up)} #panel-setup .sa-gate.no{background:var(--warn-soft);color:var(--down)}
#panel-setup .sa-stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin:8px 0 14px}
#panel-setup .sa-stats .cell b{font-family:var(--serif);font-weight:600;font-size:22px}
#panel-setup .sa-res{display:inline-block;font-size:11px;font-weight:800;padding:2px 8px;border-radius:6px}
#panel-setup .sa-res.TP{background:var(--good-soft);color:var(--up)} #panel-setup .sa-res.SL{background:var(--warn-soft);color:var(--down)}
#panel-setup .sa-res.waktu{background:var(--bg);color:var(--muted)}
#panel-setup .sa-miss{font-size:12px;color:var(--down);white-space:normal;min-width:180px;text-align:left}
#panel-setup .sa-cmp td:nth-child(n+3),#panel-setup .sa-cmp th:nth-child(n+3){text-align:right}
#panel-setup .sa-warn{background:var(--accent-soft);border-radius:12px;padding:12px 14px;font-size:14px;margin-top:10px}
#panel-setup h3{font-size:15px;margin:16px 0 8px}`;
  const st = document.createElement("style"); st.id = "setup-css"; st.textContent = css; document.head.appendChild(st);

  let sweep = null, loading = false, recFilter = "semua", built = false;
  const R = x => App.isNum(x) ? (x > 0 ? "+" : "") + x.toLocaleString("id-ID", {minimumFractionDigits:2, maximumFractionDigits:2}) + "R" : "–";
  const pctS = x => App.isNum(x) ? (x * 100).toLocaleString("id-ID", {maximumFractionDigits:0}) + "%" : "–";

  function statCells(s){
    if(!s || !s.trade) return `<p class="hint">Belum ada trade.</p>`;
    const c = (l, v, k="") => `<div class="cell"><span>${l}</span><b class="${k}">${v}</b></div>`;
    return `<div class="sa-stats">${c("Jumlah trade", App.fmt(s.trade))}${c("Kena TP", App.fmt(s.kena_tp), "up")}${c("Kena SL", App.fmt(s.kena_sl), "down")}
      ${c("Waktu habis", App.fmt(s.waktu_habis))}${c("Menang", pctS(s.menang))}${c("Rata-rata / trade", R(s.rata_r), App.cls(s.rata_r))}
      ${c("Profit factor", s.profit_factor ? s.profit_factor.toLocaleString("id-ID") : "–")}${c("Rata lama pegang", (s.rata_hari ?? "–") + " hari")}</div>`;
  }

  function cmpRow(name, x){
    const t = x.train, u = x.test;
    const f = s => s && s.trade ? `${s.trade} · ${pctS(s.menang)} · <b class="${App.cls(s.rata_r)}">${R(s.rata_r)}</b>` : "–";
    return `<tr><td>${name}</td><td style="white-space:normal;min-width:220px">${App.esc(x.label)}</td><td>${f(t)}</td><td>${f(u)}</td></tr>`;
  }

  function candidates(){
    const m = App.S.momentum;
    if(!m) return `<p class="hint">Memuat data screener…</p>`;
    const rows = m.rows.filter(z => z.setup_a);
    const pass = rows.filter(z => z.setup_a.lolos);
    const near = rows.filter(z => !z.setup_a.lolos && z.setup_a.skor >= z.setup_a.dari - 2)
                     .sort((a, b) => b.setup_a.skor - a.setup_a.skor || b.rs_rating - a.rs_rating).slice(0, 20);
    const gateOk = m.pasar?.status !== "downtrend";
    const gate = `<div class="sa-gate ${gateOk ? "ok" : "no"}"><b>${gateOk ? "Pasar terbuka" : "Pasar tertutup"}</b>
      <span>IHSG status <b>${App.esc(m.pasar?.status || "–")}</b>. ${gateOk ? "Setup A+ boleh dieksekusi." :
      "Backtest: breakout saat IHSG downtrend lebih sering gagal. Tidak ada entry baru sampai IHSG keluar dari downtrend."}</span></div>`;
    const tbl = (list, miss) => `<div class="table-wrap"><table><thead><tr><th>Kode</th><th>Nama</th><th>RS</th><th>Harga</th>
      <th>Entry (buy-stop)</th><th>SL</th><th>TP 1R</th><th>Risiko</th>${miss ? "<th>Belum terpenuhi</th>" : ""}</tr></thead><tbody>${list.map(z => {
        const s = z.setup_a;
        return `<tr data-code="${App.esc(z.kode)}"><td class="code">${App.esc(z.kode)}</td><td>${App.esc((z.nama || "").slice(0, 28))}</td>
          <td>${z.rs_rating}</td><td>${App.fmt(z.harga)}</td><td class="lv-e">${App.fmt(s.entry)}</td><td class="down">${App.fmt(s.sl)}</td>
          <td class="up">${App.fmt(s.tp)}</td><td>${pctS(s.sl_pct)}</td>${miss ? `<td class="sa-miss">${s.syarat.filter(x => !x[1]).map(x => App.esc(x[0])).join(" · ")}</td>` : ""}</tr>`;
      }).join("")}</tbody></table></div>`;
    return gate + `<h3>Lolos semua syarat (${pass.length})</h3>` +
      (pass.length ? tbl(pass, false) : `<p class="hint">Tidak ada saham yang lolos hari ini. Tidak trading juga keputusan yang sah.</p>`) +
      `<h3>Hampir lolos (kurang 1–2 syarat)</h3>` + (near.length ? tbl(near, true) : `<p class="hint">Tidak ada.</p>`) +
      `<p class="hint">Data screener ${App.esc(m.tgl_data || "")}. Klik baris untuk grafik.</p>`;
  }

  function record(){
    const all = sweep.trade_kandidat || [];
    const list = recFilter === "semua" ? all : all.filter(t => t.keluar === recFilter);
    return `<div class="toolbar"><span class="seg">${["semua", "TP", "SL", "waktu"].map(k =>
        `<button data-sarec="${k}" aria-pressed="${recFilter === k}">${k === "semua" ? "Semua" : k === "waktu" ? "Waktu habis" : "Kena " + k} (${k === "semua" ? all.length : all.filter(t => t.keluar === k).length})</button>`).join("")}</span></div>
      <div class="table-wrap"><table><thead><tr><th>Kode</th><th>Tgl beli</th><th>Tgl keluar</th><th>Periode</th><th>IHSG</th><th>RS</th>
      <th>Beli</th><th>SL</th><th>TP</th><th>Hasil</th><th>Hari</th><th>Return</th><th>R</th></tr></thead><tbody>${list.map(t => `
      <tr data-code="${App.esc(t.kode)}"><td class="code">${App.esc(t.kode)}</td><td>${t.tgl_beli}</td><td>${t.tgl_keluar}</td>
      <td>${t.periode === "uji" ? "uji 2025-26" : "pilih 2022-24"}</td><td>${App.esc(t.pasar)}</td><td>${t.rs}</td>
      <td>${App.fmt(t.beli)}</td><td>${App.fmt(t.sl)}</td><td>${App.fmt(t.tp)}</td>
      <td><span class="sa-res ${t.keluar}">${t.keluar === "waktu" ? "Waktu" : t.keluar}</span></td><td>${t.hari}</td>
      <td class="${App.cls(t.ret)}">${App.pct(t.ret)}</td><td class="${App.cls(t.net_r)}">${R(t.net_r)}</td></tr>`).join("")}</tbody></table></div>`;
  }

  function build(el){
    if(!sweep){ el.innerHTML = `<div class="card"><p>${loading ? "Memuat hasil backtest…" : "Hasil backtest belum tersedia. Jalankan <code>python backtest_sweep.py</code>."}</p></div>`; return; }
    const k = sweep.kandidat, f = k.filter;
    el.innerHTML = `
    <div class="card">
      <h2>Setup A+ · VCP momentum, TP 1R</h2>
      <p>Satu-satunya kombinasi dari ${App.fmt(sweep.asumsi.jumlah_kombinasi)} yang diuji (filter × SL × TP, ${App.fmt(sweep.asumsi.jumlah_sinyal)} sinyal breakout
      ${sweep.periode[0]} s.d. ${sweep.periode[1]}) yang untung di <b>kedua</b> periode dengan batas bawah keyakinan ~95% di atas nol.</p>
      <div class="sa-rule">
        <div><b>Pasar</b>IHSG ${App.esc(f.pasar)} (di atas MA200)</div>
        <div><b>Kekuatan</b>${App.esc(f.rs)}, lolos Trend Template</div>
        <div><b>Pola</b>VCP valid + ${App.esc(f.vcp)}</div>
        <div><b>Risiko</b>${App.esc(f.risiko)}, SL di bawah low kontraksi terakhir</div>
        <div><b>Entry</b>Buy-stop 1 tick di atas pivot; batal kalau open gap di atasnya</div>
        <div><b>Keluar</b>TP 1R (jual semua) · SL disiplin · maks ${sweep.asumsi.maks_hari} hari</div>
      </div>
    </div>
    <div class="card"><h2>Kandidat hari ini</h2><div id="sa-cand"></div></div>
    <div class="card">
      <h2>Rekam jejak backtest</h2>
      <p>Biaya beli ${App.pct(sweep.asumsi.biaya_beli, 2, false)}, jual ${App.pct(sweep.asumsi.biaya_jual, 2, false)}, slippage ${App.pct(sweep.asumsi.slippage, 1, false)} per sisi sudah dihitung.</p>
      <h3>Seluruh periode</h3>${statCells(k.semua)}
      <h3>Periode pilih (2022–2024)</h3>${statCells(k.train)}
      <h3>Periode uji (2025–2026)</h3>${statCells(k.test)}
      <h3>Daftar trade</h3><div id="sa-rec"></div>
    </div>
    <div class="card">
      <h2>Kenapa bukan 90% menang?</h2>
      <p>Semua sinyal breakout, SL struktur, hanya TP yang diubah. Makin dekat TP, makin sering menang, tapi untung per trade tidak ikut naik.</p>
      <div class="table-wrap"><table class="sa-cmp"><thead><tr><th>TP</th><th>Trade</th><th>Kena TP</th><th>Kena SL</th><th>Waktu habis</th><th>Menang</th><th>Rata-rata</th></tr></thead><tbody>
      ${sweep.tp_vs_menang.map(t => `<tr><td>${String(t.tp).replace(".", ",")}R</td><td>${t.trade}</td><td class="up">${t.kena_tp}</td><td class="down">${t.kena_sl}</td><td>${t.waktu_habis}</td><td>${pctS(t.menang)}</td><td class="${App.cls(t.rata_r)}">${R(t.rata_r)}</td></tr>`).join("")}
      </tbody></table></div>
      <div class="sa-warn">Win rate 90% dengan SL yang disiplin hanya bisa dicapai dengan TP sangat dekat, dan satu kali kena SL menghapus beberapa kali TP.
      Yang menentukan untung adalah <b>rata-rata R per trade</b> setelah biaya, bukan win rate.</div>
    </div>
    <div class="card">
      <h2>Uji jujur: pilih di masa lalu, uji di masa depan</h2>
      <p>Kombinasi dipilih dengan data 2022–2024 saja, lalu diuji di 2025–2026. Kolom: jumlah trade · menang · rata-rata R.</p>
      <div class="table-wrap"><table class="sa-cmp"><thead><tr><th></th><th>Aturan</th><th>Pilih 2022–24</th><th>Uji 2025–26</th></tr></thead><tbody>
        ${cmpRow("Aturan modul asli", sweep.dasar)}${cmpRow("Juara di data pilih", sweep.terbaik)}${cmpRow("Setup A+", k)}
        ${sweep.top.slice(0, 10).map((x, i) => cmpRow(`Peringkat ${i + 1}`, x)).join("")}
      </tbody></table></div>
      <div class="sa-warn">"Juara di data pilih" justru rugi di data uji: tanda overfitting. Setup A+ dipilih setelah melihat kedua periode dan sampelnya kecil
      (${k.semua.trade} trade), jadi anggap angkanya optimis. Ukur lagi dengan uang kecil dan catat di Jurnal sebelum menambah modal.
      Survivorship bias: saham yang sudah delisting tidak ikut diuji. Alat bantu riset, bukan rekomendasi beli atau jual.</div>
    </div>`;
    built = true;
  }

  function update(){
    const c = document.getElementById("sa-cand"); if(c) c.innerHTML = candidates();
    const r = document.getElementById("sa-rec"); if(r && sweep) r.innerHTML = record();
  }

  document.addEventListener("click", e => {
    const b = e.target.closest("[data-sarec]");
    if(!b) return;
    recFilter = b.dataset.sarec; update();
  });

  App.register("setup", {
    render(el){
      if(!sweep && !loading){
        loading = true;
        App.getJSON("backtest_sweep").then(d => { sweep = d; loading = false; built = false; App.renderModule("setup"); });
      }
      if(!built || !el.querySelector("#sa-cand")) build(el);
      update();
    },
  });
})();
