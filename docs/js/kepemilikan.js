/* Modul Kepemilikan: aliran kepemilikan saham bulanan dari data KSEI. */
(function(){
  const NAME = "kepemilikan";
  const GROUPS = [
    ["asing", "Asing", "var(--blue)"],
    ["reksadana", "Reksa dana", "var(--teal)"],
    ["institusi_lokal", "Institusi lokal", "var(--orange)"],
    ["korporasi", "Korporasi", "var(--faint)"],
    ["individu", "Individu", "var(--accent)"],
  ];
  const SORTS = { d_smart: "Δ smart money", d_asing: "Δ asing", d_reksadana: "Δ reksa dana", asing: "% asing" };
  const st = {
    q: "",
    sig: App.store.get("kp-sig") || "semua",
    liq: App.store.get("kp-liq") === "1",
    sort: SORTS[App.store.get("kp-sort")] ? App.store.get("kp-sort") : "d_smart",
    limit: 100,
  };
  let built = false, lastKey = "";

  function css(){
    if(document.getElementById(NAME + "-css")) return;
    const s = document.createElement("style");
    s.id = NAME + "-css";
    s.textContent = `
#panel-kepemilikan .kp-bar{display:flex;height:6px;border-radius:3px;overflow:hidden;background:var(--line);margin-top:4px;min-width:70px}
#panel-kepemilikan .kp-bar i{display:block;height:100%}
#panel-kepemilikan .kp-legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--muted);margin:4px 0 12px}
#panel-kepemilikan .kp-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
#panel-kepemilikan .kp-sig{margin-left:0;text-transform:capitalize}
#panel-kepemilikan .kp-sig.dist{background:var(--warn-soft);color:var(--down)}
#panel-kepemilikan .kp-sig.net{background:var(--bg2);color:var(--muted)}
#panel-kepemilikan .kp-nama{max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-size:13px}
#panel-kepemilikan .kp-code{background:none;border:0;padding:0;font:inherit;font-weight:700;color:var(--ink);cursor:pointer}
#panel-kepemilikan .kp-more{margin-top:12px;text-align:center}
#panel-kepemilikan .kp-note{font-size:14px;color:var(--muted);margin:0 0 12px;line-height:1.5}
#panel-kepemilikan .card+.card{margin-top:16px}
#panel-kepemilikan .search{min-width:0;flex:1 1 180px}
#panel-kepemilikan td,#panel-kepemilikan th{white-space:nowrap}
`;
    document.head.appendChild(s);
  }

  const esc = s => App.esc(s);
  const pp = x => App.isNum(x) ? App.pct(x, 1, true).replace("%", " pp") : "–";
  const sc = x => App.isNum(x) ? (x > 0 ? "up" : x < 0 ? "down" : "") : "";
  const sigCls = s => s === "akumulasi" ? "good" : s === "distribusi" ? "dist" : "net";
  const median = a => { if(!a.length) return null; const b = [...a].sort((x, y) => x - y), m = b.length >> 1; return b.length % 2 ? b[m] : (b[m-1] + b[m]) / 2; };
  const fmtDate = d => { try{ return new Date(d + "T00:00:00").toLocaleDateString("id-ID", {month:"long", year:"numeric"}); }catch{ return d || "–"; } };

  function rows(S){
    const meta = {};
    for(const r of (S.momentum?.rows || [])) meta[r.kode] = r;
    return Object.entries(S.ksei.rows || {}).map(([kode, r]) => {
      const m = meta[kode] || {};
      return { kode, ...r, nama: m.nama || "", sektor: m.sektor || "Lainnya", likuid: !!m.likuid };
    });
  }

  function shell(el, S){
    const k = S.ksei, all = rows(S);
    const acc = all.filter(r => r.sinyal === "akumulasi").length, dis = all.filter(r => r.sinyal === "distribusi").length;
    const top = all.filter(r => App.isNum(r.d_asing)).sort((a, b) => b.d_asing - a.d_asing).slice(0, 3);
    el.innerHTML = `
<div class="card">
  <h2>Kepemilikan saham (KSEI)</h2>
  <p>Data bulanan KSEI: periode <b>${esc(fmtDate(k.periode))}</b> dibanding <b>${esc(fmtDate(k.periode_lalu))}</b>. Sumber: ${esc(k.sumber || "KSEI")}.</p>
  <p class="kp-note"><b>Smart money</b> = asing + reksa dana + institusi lokal. <b>Δ smart</b> adalah perubahan porsinya dalam sebulan (poin persen, pp). Naik bisa berarti akumulasi, turun bisa berarti distribusi. Ini alat bantu riset, bukan rekomendasi beli/jual.</p>
  <div class="grid">
    <div class="cell"><span>Saham akumulasi</span><b class="up">${App.fmt(acc, 0)}</b></div>
    <div class="cell"><span>Saham distribusi</span><b class="down">${App.fmt(dis, 0)}</b></div>
    <div class="cell"><span>Total saham</span><b>${App.fmt(all.length, 0)}</b></div>
    ${top.map((r, i) => `<div class="cell"><span>Asing naik #${i+1}</span><b><button class="kp-code" data-code="${esc(r.kode)}">${esc(r.kode)}</button> <small class="up">${pp(r.d_asing)}</small></b></div>`).join("")}
  </div>
</div>
<div class="card">
  <h2>Aliran kepemilikan</h2>
  <div class="toolbar">
    <input class="search kp-q" type="search" placeholder="Cari kode atau nama…" aria-label="Cari saham">
    <div class="seg kp-seg" role="group" aria-label="Sinyal">
      <button data-sig="semua">Semua</button><button data-sig="akumulasi">Akumulasi</button><button data-sig="distribusi">Distribusi</button>
    </div>
    <button class="chip kp-liq" aria-pressed="false">Hanya likuid</button>
    <select class="search kp-sort" aria-label="Urutkan" style="flex:0 1 auto">
      ${Object.entries(SORTS).map(([v, t]) => `<option value="${v}">Urut: ${t}</option>`).join("")}
    </select>
  </div>
  <div class="kp-legend">${GROUPS.map(g => `<span><i style="background:${g[2]}"></i>${g[1]}</span>`).join("")}</div>
  <p class="hint kp-count"></p>
  <div class="table-wrap"><table>
    <thead><tr><th>Kode</th><th>Nama</th><th>Harga</th><th>% asing</th><th>Δ asing</th><th>Δ reksa dana</th><th>Δ inst. lokal</th><th>Δ individu</th><th>Δ smart</th><th>Sinyal</th></tr></thead>
    <tbody class="kp-body"></tbody>
  </table></div>
  <div class="kp-more"><button class="chip kp-morebtn">Tampilkan lebih banyak</button></div>
</div>
<div class="card">
  <h2>Sektor</h2>
  <p>Median Δ smart money per sektor dan jumlah saham akumulasi/distribusi.</p>
  <div class="table-wrap"><table>
    <thead><tr><th>Sektor</th><th>Saham</th><th>Median Δ smart</th><th>Akumulasi</th><th>Distribusi</th></tr></thead>
    <tbody class="kp-sek"></tbody>
  </table></div>
</div>`;
    const q = el.querySelector(".kp-q");
    q.value = st.q;
    q.addEventListener("input", () => { st.q = q.value; st.limit = 100; update(el); });
    el.querySelector(".kp-seg").addEventListener("click", e => {
      const b = e.target.closest("button[data-sig]"); if(!b) return;
      st.sig = b.dataset.sig; st.limit = 100; App.store.set("kp-sig", st.sig); update(el);
    });
    el.querySelector(".kp-liq").addEventListener("click", () => { st.liq = !st.liq; st.limit = 100; App.store.set("kp-liq", st.liq ? "1" : "0"); update(el); });
    const so = el.querySelector(".kp-sort");
    so.value = st.sort;
    so.addEventListener("change", () => { st.sort = so.value; App.store.set("kp-sort", st.sort); update(el); });
    el.querySelector(".kp-morebtn").addEventListener("click", () => { st.limit += 100; update(el); });
    sektor(el, all);
  }

  function sektor(el, all){
    const g = {};
    for(const r of all){ (g[r.sektor] ||= []).push(r); }
    const list = Object.entries(g).map(([s, a]) => ({
      s, n: a.length, med: median(a.map(r => r.d_smart).filter(App.isNum)),
      acc: a.filter(r => r.sinyal === "akumulasi").length, dis: a.filter(r => r.sinyal === "distribusi").length,
    })).sort((a, b) => (b.med ?? -9) - (a.med ?? -9));
    el.querySelector(".kp-sek").innerHTML = list.map(x => `<tr><td>${esc(x.s)}</td><td>${App.fmt(x.n, 0)}</td><td class="${sc(x.med)}">${pp(x.med)}</td><td class="up">${x.acc}</td><td class="down">${x.dis}</td></tr>`).join("");
  }

  function bar(r){
    const tot = GROUPS.reduce((s, g) => s + (App.isNum(r[g[0]]) ? r[g[0]] : 0), 0) || 1;
    return `<div class="kp-bar" title="${GROUPS.map(g => g[1] + " " + App.pct(r[g[0]], 1, false)).join(" · ")}">${GROUPS.map(g => App.isNum(r[g[0]]) && r[g[0]] > 0 ? `<i style="width:${(r[g[0]] / tot * 100).toFixed(2)}%;background:${g[2]}"></i>` : "").join("")}</div>`;
  }

  function update(el){
    const all = rows(App.S), q = st.q.trim().toLowerCase();
    let list = all.filter(r =>
      (st.sig === "semua" || r.sinyal === st.sig) &&
      (!st.liq || r.likuid) &&
      (!q || r.kode.toLowerCase().includes(q) || r.nama.toLowerCase().includes(q)));
    const k = st.sort;
    list.sort((a, b) => (App.isNum(b[k]) ? b[k] : -9) - (App.isNum(a[k]) ? a[k] : -9));
    el.querySelectorAll(".kp-seg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.sig === st.sig)));
    el.querySelector(".kp-liq").setAttribute("aria-pressed", String(st.liq));
    const shown = list.slice(0, st.limit);
    el.querySelector(".kp-count").textContent = list.length ? `Menampilkan ${App.fmt(shown.length, 0)} dari ${App.fmt(list.length, 0)} saham.` : "";
    el.querySelector(".kp-body").innerHTML = shown.length ? shown.map(r => `<tr data-code="${esc(r.kode)}" style="cursor:pointer">
<td><b>${esc(r.kode)}</b></td><td class="kp-nama" title="${esc(r.nama)}">${esc(r.nama || "–")}</td>
<td>${App.fmt(r.harga, 0)}</td>
<td>${App.pct(r.asing, 1, false)}${bar(r)}</td>
<td class="${sc(r.d_asing)}">${pp(r.d_asing)}</td><td class="${sc(r.d_reksadana)}">${pp(r.d_reksadana)}</td>
<td class="${sc(r.d_institusi_lokal)}">${pp(r.d_institusi_lokal)}</td><td class="${sc(r.d_individu)}">${pp(r.d_individu)}</td>
<td class="${sc(r.d_smart)}"><b>${pp(r.d_smart)}</b></td>
<td><span class="badge kp-sig ${sigCls(r.sinyal)}">${esc(r.sinyal || "–")}</span></td></tr>`).join("")
      : `<tr><td colspan="10" class="hint">Tidak ada saham yang cocok dengan filter.</td></tr>`;
    el.querySelector(".kp-more").hidden = list.length <= st.limit;
  }

  App.register(NAME, {
    render(el){
      css();
      const S = App.S;
      if(!S.ksei || !S.ksei.rows){ built = false; el.innerHTML = `<div class="card"><p class="hint">Memuat data…</p></div>`; return; }
      const key = (S.ksei.updated || "") + "|" + (S.momentum ? "m" : "");
      if(!built || key !== lastKey || !el.querySelector(".kp-body")){
        const focused = document.activeElement?.classList.contains("kp-q");
        shell(el, S); built = true; lastKey = key;
        if(focused) el.querySelector(".kp-q").focus();
      }
      update(el);
    },
  });
})();
