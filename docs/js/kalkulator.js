/* Kalkulator posisi & risiko (Meja Pantau IDX) */
(function(){
  const KEY = "kalk";
  const DEF = { modal:"", risk:"1", alok:"25", kode:"", entry:"", sl:"", t1:"", t2:"", fb:"0,15", fs:"0,25" };
  let built = false, root = null;

  function load(){
    try{ return Object.assign({}, DEF, JSON.parse(App.store.get(KEY) || "{}") || {}); }catch{ return Object.assign({}, DEF); }
  }
  function save(st){ App.store.set(KEY, JSON.stringify(st)); }

  // Rupiah/harga: titik = ribuan, koma = desimal
  function numRp(s){ s = String(s||"").replace(/[^\d,.-]/g,""); if(!s) return NaN; return parseFloat(s.replace(/\./g,"").replace(",", ".")); }
  // Persen: koma atau titik sebagai desimal
  function numPct(s){ s = String(s||"").trim().replace(/[^\d,.-]/g,""); if(!s) return NaN; return parseFloat(s.replace(",", ".")); }

  function tick(p){ return p < 200 ? 1 : p < 500 ? 2 : p < 2000 ? 5 : p < 5000 ? 10 : 25; }
  function roundTick(p, mode){
    const t = tick(p); const f = mode === "up" ? Math.ceil : mode === "down" ? Math.floor : Math.round;
    let r = f(p / t) * t; // re-check band after rounding
    const t2 = tick(r); if(t2 !== t) r = f(p / t2) * t2;
    return r;
  }
  function validTick(p){ return Math.abs(p / tick(p) - Math.round(p / tick(p))) < 1e-9; }

  function lastPrice(kode){
    const S = App.S || {}; kode = kode.toUpperCase();
    const q = S.quotes && S.quotes.stocks && S.quotes.stocks[kode];
    if(q && App.isNum(q.last)) return q.last;
    const rows = S.momentum && S.momentum.rows;
    const r = Array.isArray(rows) && rows.find(x => x.kode === kode);
    return r && App.isNum(r.harga) ? r.harga : null;
  }

  function css(){
    if(document.getElementById("kalkulator-css")) return;
    const s = document.createElement("style"); s.id = "kalkulator-css";
    s.textContent = `
#panel-kalkulator .kalk-form{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:8px 0 4px}
#panel-kalkulator .kalk-form label{display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted);min-width:0}
#panel-kalkulator .kalk-form input{font:inherit;font-size:15px;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:9px 10px;width:100%;box-sizing:border-box;min-width:0}
#panel-kalkulator .kalk-form input:focus{outline:2px solid var(--line2);outline-offset:0}
#panel-kalkulator .kalk-form input[aria-invalid="true"]{border-color:var(--down)}
#panel-kalkulator .kalk-msg{min-height:18px;margin:6px 0}
#panel-kalkulator .kalk-msg p{margin:2px 0;font-size:13px}
#panel-kalkulator .kalk-err{color:var(--down)}
#panel-kalkulator .kalk-warn{color:var(--accent)}
#panel-kalkulator .kalk-fix{font:inherit;font-size:12px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;padding:2px 8px;margin-left:6px;cursor:pointer}
#panel-kalkulator .kalk-out .cell small{display:block;font-size:12px;color:var(--muted);margin-top:2px}
#panel-kalkulator .kalk-ladder{margin:14px 0 6px;width:100%;overflow:hidden}
#panel-kalkulator .kalk-ladder svg{display:block;width:100%;height:auto}
#panel-kalkulator .kalk-ladder text{font-family:var(--font);font-size:12px}
#panel-kalkulator .kalk-act{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}
#panel-kalkulator .kalk-btn{font:inherit;font-weight:600;background:var(--btn);color:var(--btn-fg);border:0;border-radius:10px;padding:10px 16px;cursor:pointer}
#panel-kalkulator .kalk-btn:disabled{opacity:.45;cursor:not-allowed}
#panel-kalkulator .kalk-ok{color:var(--up);font-size:13px}
#panel-kalkulator .kalk-kode-info{font-size:12px;color:var(--faint);min-height:14px}
`;
    document.head.appendChild(s);
  }

  const FIELDS = [
    ["modal","Modal (Rp)","numeric","50.000.000"],
    ["risk","Risiko per trade (% modal)","decimal","1"],
    ["alok","Batas alokasi per saham (%)","decimal","25"],
    ["kode","Kode saham (opsional)","text","BBRI"],
    ["entry","Harga entry","numeric",""],
    ["sl","Stop loss (harga)","numeric",""],
    ["t1","Target 1","numeric",""],
    ["t2","Target 2 (opsional)","numeric",""],
    ["fb","Fee beli (%)","decimal","0,15"],
    ["fs","Fee jual (%)","decimal","0,25"],
  ];

  function shell(el){
    const st = load();
    el.innerHTML = `<div class="card">
      <h2>Kalkulator posisi</h2>
      <p>Hitung jumlah lot dari modal, risiko per trade, dan stop loss. 1 lot = 100 lembar. Alat bantu riset, bukan rekomendasi.</p>
      <div class="kalk-form">${FIELDS.map(([k,l,im,ph]) => `<label>${l}<input id="kalk-${k}" data-k="${k}" inputmode="${im}" autocomplete="off" ${k==="kode"?'maxlength="6" style="text-transform:uppercase"':""} placeholder="${App.esc(ph)}" value="${App.esc(st[k]||"")}">${k==="kode"?'<span class="kalk-kode-info" id="kalk-kinfo"></span>':""}</label>`).join("")}</div>
      <div class="kalk-msg" id="kalk-msg"></div>
      <div class="grid kalk-out" id="kalk-out"></div>
      <div class="kalk-ladder" id="kalk-ladder"></div>
      <div class="kalk-act"><button class="kalk-btn" id="kalk-save" type="button">Simpan ke Jurnal</button><span class="kalk-ok" id="kalk-ok" role="status"></span></div>
    </div>`;
    el.addEventListener("input", e => {
      const k = e.target.dataset && e.target.dataset.k; if(!k) return;
      const st = load(); st[k] = e.target.value;
      if(k === "kode") fillFromKode(st);
      save(st); update();
    });
    el.addEventListener("click", e => {
      const fx = e.target.closest(".kalk-fix");
      if(fx){ const inp = root.querySelector("#kalk-" + fx.dataset.f); inp.value = App.fmt(+fx.dataset.v); const st = load(); st[fx.dataset.f] = inp.value; save(st); update(); return; }
      if(e.target.id === "kalk-save") toJurnal();
    });
  }

  function fillFromKode(st){
    const kode = (st.kode||"").trim().toUpperCase(); const info = root.querySelector("#kalk-kinfo");
    if(kode.length < 4){ info.textContent = ""; return; }
    const p = lastPrice(kode);
    if(p != null){ st.entry = App.fmt(p); root.querySelector("#kalk-entry").value = st.entry; info.textContent = `Harga terakhir ${App.fmt(p)}`; }
    else info.textContent = "Kode tidak ditemukan";
  }

  function calc(){
    const st = load();
    const v = {
      modal:numRp(st.modal), risk:numPct(st.risk)/100, alok:numPct(st.alok)/100,
      entry:numRp(st.entry), sl:numRp(st.sl), t1:numRp(st.t1), t2:numRp(st.t2),
      fb:numPct(st.fb)/100, fs:numPct(st.fs)/100, kode:(st.kode||"").trim().toUpperCase()
    };
    if(!(v.fb >= 0)) v.fb = 0; if(!(v.fs >= 0)) v.fs = 0;
    return v;
  }

  function update(){
    if(!root) return;
    const v = calc(), N = App.isNum, msg = [], bad = {};
    const ok = x => N(x) && x > 0;
    ["entry","sl","t1","t2"].forEach(f => {
      const p = v[f];
      if(ok(p) && !validTick(p)){
        const r = roundTick(p); bad[f] = true;
        msg.push(`<p class="kalk-warn">${f==="entry"?"Entry":f==="sl"?"Stop loss":f==="t1"?"Target 1":"Target 2"} ${App.fmt(p)} tidak sesuai fraksi harga (kelipatan ${tick(p)}). Harga valid terdekat: <b>${App.fmt(r)}</b><button class="kalk-fix" type="button" data-f="${f}" data-v="${r}">Pakai</button></p>`);
      }
    });
    if(ok(v.entry) && ok(v.sl) && v.sl >= v.entry){ bad.sl = true; msg.unshift(`<p class="kalk-err">Stop loss harus di bawah harga entry.</p>`); }
    if(ok(v.entry) && ok(v.t1) && v.t1 <= v.entry) msg.push(`<p class="kalk-warn">Target 1 berada di bawah atau sama dengan entry.</p>`);
    if(ok(v.entry) && ok(v.t2) && v.t2 <= v.entry) msg.push(`<p class="kalk-warn">Target 2 berada di bawah atau sama dengan entry.</p>`);
    root.querySelectorAll(".kalk-form input").forEach(i => i.setAttribute("aria-invalid", bad[i.dataset.k] ? "true" : "false"));
    root.querySelector("#kalk-msg").innerHTML = msg.join("");

    const out = root.querySelector("#kalk-out"), btn = root.querySelector("#kalk-save");
    const ready = ok(v.modal) && ok(v.risk) && ok(v.alok) && ok(v.entry) && ok(v.sl) && v.sl < v.entry;
    if(!ready){
      out.innerHTML = `<p class="hint" style="grid-column:1/-1">Isi modal, harga entry, dan stop loss untuk melihat hasil.</p>`;
      root.querySelector("#kalk-ladder").innerHTML = ""; btn.disabled = true; kalkLast = null; return;
    }
    const perLembar = v.entry - v.sl;
    const lotRisk = (v.modal * v.risk) / (perLembar * 100);
    const lotAlok = (v.modal * v.alok) / (v.entry * 100);
    const lot = Math.max(0, Math.floor(Math.min(lotRisk, lotAlok)));
    const bound = lotRisk <= lotAlok ? "risiko" : "alokasi";
    const sh = lot * 100;
    const beli = sh * v.entry, feeB = beli * v.fb, total = beli + feeB;
    const jualSL = sh * v.sl, rugi = beli - jualSL + feeB + jualSL * v.fs;
    const riskPlan = sh * perLembar; // 1R tanpa fee
    const be = roundTick(v.entry * (1 + v.fb) / (1 - v.fs), "up");
    const tgt = t => { if(!ok(t)) return null; const j = sh * t; const p = j - beli - feeB - j * v.fs; return { p, pct: total ? p / total : NaN, r: rugi ? p / rugi : NaN }; };
    const T1 = tgt(v.t1), T2 = tgt(v.t2);
    const cell = (l, b, s, c) => `<div class="cell"><span>${l}</span><b class="${c||""}">${b}</b>${s?`<small>${s}</small>`:""}</div>`;
    const tCell = (n, t, T) => T ? cell(`Target ${n} (${App.fmt(t)})`, `Rp ${App.fmt(T.p)}`, `${App.pct(T.pct)} · ${App.isNum(T.r)?App.fmt(T.r,2):"–"}R`, App.cls(T.p)) : "";
    out.innerHTML =
      cell("Jumlah lot", `${App.fmt(lot)} lot`, `${App.fmt(sh)} lembar · dibatasi ${bound}${lot===0?" (modal kurang)":""}`) +
      cell("Nilai beli (+fee)", `Rp ${App.fmt(total)}`, `${App.pct(v.modal ? total / v.modal : NaN)} dari modal · fee Rp ${App.fmt(feeB)}`) +
      cell("Risiko (+fee)", `Rp ${App.fmt(rugi)}`, `${App.pct(v.modal ? rugi / v.modal : NaN, 2, false)} modal · tanpa fee Rp ${App.fmt(riskPlan)}`, "down") +
      cell("Jarak SL", App.pct(-perLembar / v.entry, 2), `${App.fmt(perLembar)} per lembar`, "down") +
      tCell(1, v.t1, T1) + tCell(2, v.t2, T2) +
      cell("Harga impas", App.fmt(be), "setelah fee beli & jual");
    ladder(v);
    btn.disabled = lot <= 0;
    kalkLast = { kode: v.kode, entry: v.entry, sl: v.sl, t1: ok(v.t1) ? v.t1 : null, t2: ok(v.t2) ? v.t2 : null, lot };
  }
  let kalkLast = null;

  function ladder(v){
    const pts = [["SL", v.sl, "var(--down)"], ["Entry", v.entry, "var(--blue)"]];
    if(v.t1 > 0) pts.push(["T1", v.t1, "var(--up)"]);
    if(v.t2 > 0) pts.push(["T2", v.t2, "var(--up)"]);
    const vals = pts.map(p => p[1]); let lo = Math.min(...vals), hi = Math.max(...vals);
    if(hi === lo){ hi += 1; lo -= 1; }
    const W = 600, H = 78, pad = 36, x = p => pad + (p - lo) / (hi - lo) * (W - 2 * pad);
    const ent = x(v.entry), sl = x(v.sl);
    const tmax = Math.max(v.entry, ...(pts.filter(p => p[0][0]==="T").map(p => p[1])));
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Tangga harga: stop loss, entry, dan target">`;
    s += `<line x1="${pad}" y1="40" x2="${W-pad}" y2="40" stroke="var(--line2)" stroke-width="2"/>`;
    s += `<rect x="${sl}" y="35" width="${Math.max(0, ent - sl)}" height="10" fill="var(--down)" opacity=".25"/>`;
    if(tmax > v.entry) s += `<rect x="${ent}" y="35" width="${x(tmax) - ent}" height="10" fill="var(--up)" opacity=".22"/>`;
    pts.forEach(([n, p, c], i) => {
      const X = x(p), top = i % 2 === 0;
      s += `<line x1="${X}" y1="28" x2="${X}" y2="52" stroke="${c}" stroke-width="3" stroke-linecap="round"/>`;
      s += `<text x="${X}" y="${top ? 20 : 68}" text-anchor="middle" fill="${c}" font-weight="700">${n} ${App.fmt(p)}</text>`;
    });
    root.querySelector("#kalk-ladder").innerHTML = s + `</svg>`;
  }

  function toJurnal(){
    if(!kalkLast || kalkLast.lot <= 0) return;
    let arr; try{ arr = JSON.parse(App.store.get("jurnal") || "[]"); }catch{ arr = []; }
    if(!Array.isArray(arr)) arr = [];
    const d = new Date(), tgl = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
    arr.push({ id: Date.now().toString(36) + Math.random().toString(36).slice(2,6), tgl, kode: kalkLast.kode, entry: kalkLast.entry, sl: kalkLast.sl, t1: kalkLast.t1, t2: kalkLast.t2, lot: kalkLast.lot, catatan: "", status: "rencana" });
    App.store.set("jurnal", JSON.stringify(arr));
    const o = root.querySelector("#kalk-ok"); o.textContent = `Tersimpan ke Jurnal (${kalkLast.kode || "tanpa kode"}, ${App.fmt(kalkLast.lot)} lot).`;
    clearTimeout(toJurnal._t); toJurnal._t = setTimeout(() => { o.textContent = ""; }, 3000);
  }

  App.register("kalkulator", {
    render(el){
      css();
      if(!built || root !== el || !el.querySelector("#kalk-out")){ root = el; shell(el); built = true; }
      // refresh label for kode info without overwriting user's entry
      const st = load(), info = root.querySelector("#kalk-kinfo"), k = (st.kode||"").trim().toUpperCase();
      if(info && k.length >= 4){ const p = lastPrice(k); info.textContent = p != null ? `Harga terakhir ${App.fmt(p)}` : (App.S && App.S.quotes ? "Kode tidak ditemukan" : ""); }
      update();
    }
  });
})();
