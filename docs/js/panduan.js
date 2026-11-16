/* Panduan: cara pakai tiap menu, glosarium (bisa dicari), FAQ, disclaimer.
   Juga menyediakan popover istilah: tombol [data-term="kunci"] (lihat App.term di index.html). */
(function(){
  const esc = s => App.esc(s);

  /* ---------- Glosarium ---------- */
  const GLOS = {
    rs: {t:"RS Rating", d:"Peringkat 1–99 kekuatan relatif harga: kinerja 12 bulan (kuartal terakhir dibobot ganda) dibanding seluruh saham BEI. RS 90 berarti lebih kuat dari ±90% saham lain. Ini Relative Strength, bukan RSI."},
    rsi: {t:"RSI (bukan RS)", d:"Relative Strength Index adalah osilator 0–100 dari satu saham saja. Situs ini tidak memakai RSI untuk sinyal; yang dipakai adalah RS Rating, yaitu perbandingan dengan saham lain."},
    rsline: {t:"RS Line", d:"Harga saham dibagi IHSG. Garis naik berarti saham mengungguli pasar. RS Line yang mencetak titik tertinggi baru sebelum harganya adalah tanda kekuatan."},
    tt: {t:"Trend Template", d:"8 syarat tren naik ala Minervini: harga di atas MA50, MA150 dan MA200; MA150 di atas MA200; MA200 naik; MA50 di atas MA150 dan MA200; harga ≥30% di atas titik terendah 52 minggu; dan dalam 25% dari titik tertinggi 52 minggu. Lolos = 8/8, hampir = 6–7/8."},
    stage2: {t:"Stage 2", d:"Fase tren naik dalam siklus harga (1 dasar, 2 naik, 3 puncak, 4 turun). Saham yang lolos Trend Template umumnya berada di Stage 2."},
    vcp: {t:"VCP", d:"Volatility Contraction Pattern: basis dengan koreksi yang makin kecil (mis. 20% → 10% → 5%) dan volume yang mengering. Menandakan penjual mulai habis sebelum harga menembus pivot."},
    pivot: {t:"Pivot", d:"Titik tertinggi kontraksi terakhir pada VCP. Breakout terjadi saat harga tutup di atas pivot dengan volume di atas rata-rata."},
    buystop: {t:"Buy-stop", d:"Order beli yang baru aktif bila harga naik menyentuh level tertentu (biasanya sedikit di atas pivot). Di Setup A+ order ini dianggap berlaku 5 hari bursa."},
    sltp: {t:"SL / TP", d:"Stop loss (SL): harga untuk keluar saat salah, membatasi rugi. Take profit (TP): harga target untuk mengunci untung. Tentukan keduanya sebelum membeli."},
    r: {t:"R (R-multiple)", d:"Satuan risiko. 1R = jarak entry ke stop loss. Untung 2R berarti untung dua kali risiko awal; rugi −1R berarti kena stop loss penuh. Memakai R membuat hasil antar-saham bisa dibandingkan."},
    expectancy: {t:"Expectancy", d:"Rata-rata hasil per trade dalam R: (win rate × rata-rata menang) − (loss rate × rata-rata kalah). Expectancy positif berarti sistem untung dalam jangka panjang di data uji, belum tentu di masa depan."},
    winrate: {t:"Win rate", d:"Persentase trade yang untung. Win rate tinggi belum tentu bagus bila kerugiannya jauh lebih besar dari keuntungannya; lihat juga expectancy."},
    atr: {t:"ATR", d:"Average True Range: rata-rata rentang harga harian (termasuk gap) dalam beberapa hari. Dipakai untuk menaruh stop loss dan target sesuai volatilitas saham, misalnya SL 1,5× ATR."},
    pullback: {t:"Pullback", d:"Koreksi sementara di dalam tren naik, biasanya ke area rata-rata bergerak. Tujuannya membeli saham kuat di harga yang lebih dekat ke stop loss."},
    likuid: {t:"Likuiditas", d:"Seberapa mudah saham dijual-beli tanpa menggeser harga. Di situs ini diukur dari rata-rata nilai transaksi harian; banyak tampilan memakai batas ≥ Rp1 miliar per hari."},
    hsc: {t:"HSC", d:"High Shareholding Concentration: saham yang kepemilikannya terkonsentrasi di sedikit pihak menurut BEI. Harganya bisa mudah digerakkan, jadi risikonya lebih tinggi."},
    syariah: {t:"Syariah", d:"Saham yang masuk Indeks Saham Syariah Indonesia (ISSI) / Daftar Efek Syariah OJK."},
    ksei: {t:"KSEI", d:"Kustodian Sentral Efek Indonesia. Menerbitkan data komposisi pemegang saham (asing, individu, reksa dana, institusi lokal, korporasi) bulanan; dipakai di menu Kepemilikan."},
    sesi: {t:"Sesi 1 / penutupan", d:"Jam BEI (WIB): Sesi 1 09.00–12.00 (Jumat sampai 11.30), Sesi 2 13.30–15.50 (Jumat mulai 14.00), lalu pra-tutup sampai 16.00. Data pullback dihitung setelah Sesi 1 dan setelah penutupan."},
    delay: {t:"Data tertunda 15 menit", d:"Harga diambil dari Yahoo Finance yang tertunda sekitar 15 menit dari BEI, lalu diperbarui tiap 15 menit di jam bursa. Jangan jadikan harga di sini patokan order real-time."},
  };

  /* ---------- Popover istilah (dipakai di seluruh situs) ---------- */
  let pop = null, popBtn = null;
  function closePop(focusBack){
    if(!pop) return;
    pop.remove(); pop = null;
    if(popBtn){ popBtn.setAttribute("aria-expanded", "false"); if(focusBack) popBtn.focus(); }
    popBtn = null;
  }
  function openPop(btn){
    const g = GLOS[btn.dataset.term]; if(!g) return;
    if(popBtn === btn) return closePop(true);
    closePop();
    pop = document.createElement("div");
    pop.className = "term-pop"; pop.id = "term-pop"; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", g.t);
    pop.innerHTML = `<b>${esc(g.t)}</b><p>${esc(g.d)}</p><a href="#panduan" data-glos="${esc(btn.dataset.term)}">Lihat di Panduan</a>`;
    document.body.appendChild(pop);
    const r = btn.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
    let x = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
    let y = r.bottom + 6; if(y + h > innerHeight - 8) y = Math.max(8, r.top - h - 6);
    pop.style.left = (x + scrollX) + "px"; pop.style.top = (y + scrollY) + "px";
    popBtn = btn; btn.setAttribute("aria-expanded", "true"); btn.setAttribute("aria-controls", "term-pop");
  }
  // Fase tangkap: jangan sampai klik/Enter di tombol istilah ikut mengurutkan kolom tabel
  addEventListener("click", e => {
    const b = e.target.closest?.(".term-i[data-term]");
    if(b){ e.preventDefault(); e.stopPropagation(); openPop(b); return; }
    const gl = e.target.closest?.("[data-glos]");
    if(gl && pop && pop.contains(gl)){ wantGlos = gl.dataset.glos; closePop(); setTimeout(focusGlos, 50); return; }
    if(pop && !pop.contains(e.target)) closePop();
  }, true);
  addEventListener("keydown", e => {
    const b = e.target.closest?.(".term-i[data-term]");
    if(b && (e.key === "Enter" || e.key === " ")){ e.preventDefault(); e.stopPropagation(); openPop(b); return; }
    if(e.key === "Escape" && pop){ e.stopPropagation(); closePop(true); }
  }, true);
  addEventListener("scroll", () => closePop(), {passive:true});
  addEventListener("resize", () => closePop());

  /* ---------- Isi panduan ---------- */
  const MENUS = [
    ["Sinyal", [
      ["setup", "Setup A+", "Daftar saham yang memenuhi semua syarat entry sekaligus: Trend Template, RS tinggi, VCP valid, volume, dan IHSG sedang mendukung. Ada juga daftar “hampir lolos”, jurnal otomatis tiap sinyal (dilacak sampai kena TP, SL, atau waktu habis), dan rekam jejak backtest.", "Saat mencari kandidat beli yang paling ketat. Bila daftar kosong, artinya hari ini tidak ada yang lolos; itu wajar."],
      ["momentum", "Momentum", "Peringkat RS Rating seluruh saham BEI, status Trend Template (titik 8 syarat), sinyal entry (breakout VCP atau pembalikan pemimpin RS) beserta entry, SL, TP1 (2R) dan TP2 (3R). Klik saham untuk grafik, RS Line dan checklist.", "Untuk menyusun watchlist saham terkuat dan memantau sinyal aktif. Tandai ★ untuk watchlist pribadi (tersimpan di perangkat ini)."],
      ["pullback", "Pullback", "Saham dalam tren naik yang sedang terkoreksi, dikelompokkan per kondisi, dengan level entry/SL/TP memakai ATR atau N-candle dan pilihan SL tetap atau trailing stop. Bisa disaring syariah, HSC, likuiditas, dan volatilitas. Tombol “FAQ · cara hitung” menjelaskan rumusnya.", "Bila ingin membeli saham kuat saat harganya turun sementara, bukan saat breakout. Data diperbarui setelah Sesi 1 dan setelah penutupan."],
    ]],
    ["Analisis pasar", [
      ["analisa", "Analisa pasar", "Briefing kondisi IHSG, lebar pasar (berapa saham di atas MA), pemimpin pasar, kekuatan sektor, dan hasil backtest strategi momentum.", "Langkah pertama setiap hari: bila pasar lemah, kurangi ukuran posisi atau tunggu."],
      ["lonjakan", "Lonjakan transaksi", "Saham yang volumenya hari ini berlipat dibanding rata-rata 5 hari. Lonjakan sambil naik sering berarti akumulasi, sambil turun sering distribusi.", "Untuk menemukan saham yang tiba-tiba ramai, lalu dicek di Momentum atau Grafik."],
      ["peta", "Peta & sektor", "Peta panas (ukuran = nilai transaksi, warna = perubahan harga) dan peta sektor (median RS Rating vs return 1 bulan).", "Untuk melihat sektor mana yang memimpin; saham pemenang sering datang berkelompok."],
      ["grup", "Grup konglomerat", "Kinerja rata-rata (tidak berbobot) saham per grup usaha besar, bisa diurut per hari ini, 1 bulan, 3 bulan, atau RS.", "Untuk melihat rotasi antar-grup konglomerat."],
    ]],
    ["Grafik", [
      ["grafik", "Grafik", "Grafik interaktif TradingView untuk satu saham.", "Untuk analisis bebas dengan alat gambar TradingView."],
      ["grafikpro", "Grafik Pro", "Grafik candle dengan MA, support/resistance otomatis, Fibonacci, garis tren, dan checklist Trend Template.", "Untuk memeriksa level entry dan stop loss sebelum menghitung lot."],
    ]],
    ["Data emiten", [
      ["aksi", "Aksi korporasi", "Jadwal dividen, RUPS, stock split, rights issue dan aksi korporasi lain dari berita dan jadwal dividen.", "Sebelum membeli, cek apakah ada cum date atau aksi yang bisa menggerakkan harga."],
      ["insider", "Orang dalam", "Pembelian dan penjualan oleh direksi, komisaris, dan pemegang saham ≥5% dari laporan kepemilikan, dilengkapi berita.", "Sebagai konfirmasi tambahan, bukan sinyal tunggal."],
      ["screener", "Fundamental", "Saring saham menurut valuasi dan kualitas (mis. PER, PBV, ROE) yang dihitung ulang tiap hari.", "Untuk memastikan saham teknikal yang kuat tidak punya fundamental yang buruk."],
      ["kepemilikan", "Kepemilikan", "Komposisi pemegang saham dari data KSEI bulanan beserta perubahannya, termasuk ringkasan “smart money” per sektor.", "Untuk melihat apakah institusi/asing sedang menambah atau mengurangi."],
    ]],
    ["Alat", [
      ["kalkulator", "Kalkulator", "Hitung jumlah lot dari modal, risiko per trade (%), entry, dan stop loss. Memeriksa fraksi harga BEI dan menampilkan target dalam R.", "Setiap kali sebelum order, supaya rugi bila kena SL tetap kecil dan terukur."],
      ["jurnal", "Jurnal", "Catat transaksi (entry, keluar, lot), lalu lihat P/L setelah fee, R, win rate, expectancy, dan kurva ekuitas. Bisa ekspor/impor.", "Setelah setiap transaksi. Data hanya tersimpan di browser ini, jadi ekspor berkala."],
      ["porto", "Portofolio", "Catat saham yang dipegang; harga mengikuti data terbaru situs ini dan bisa dibandingkan dengan IHSG.", "Untuk memantau posisi terbuka. Data hanya di perangkat ini."],
    ]],
  ];
  const GLOS_TERMS = Object.keys(GLOS);
  const FAQ = [
    ["Dari mana datanya dan seberapa terlambat?", "Harga dan volume dari Yahoo Finance, tertunda sekitar 15 menit dari BEI. Komposisi pemegang saham dari KSEI. Aksi korporasi dan transaksi orang dalam dari keterbukaan informasi BEI/KSEI dan berita media. Selalu cocokkan dengan sumber resmi di idx.co.id sebelum bertransaksi."],
    ["Kapan data diperbarui?", "Jadwal otomatis (WIB, hari bursa): harga tiap 15 menit pukul 09.00–16.45; aksi korporasi pukul 08.00, tiap ±10 menit pukul 09.00–16.50, dan 19.00; transaksi orang dalam tiap 15 menit 08.00–16.45 dan 17.00; pullback setelah Sesi 1 (12.05, Jumat 11.35) dan 16.26; fundamental, Momentum dan Setup A+ pukul 16.30; KSEI pukul 09.00 tanggal 1–12 tiap bulan; backtest tiap Sabtu 09.00. Jadwal GitHub kadang telat beberapa menit."],
    ["Kenapa tidak ada strategi yang 90% menang?", "Di pasar nyata, win rate setinggi itu hampir selalu berarti target sangat kecil dan rugi sesekali sangat besar, atau hasil yang “dipas-paskan” dengan data lama. Yang lebih penting adalah expectancy positif dan risiko per trade yang kecil. Bahkan kombinasi terbaik di Setup A+ hanya menang sekitar 70% di backtest, dan itu pun dengan filter IHSG."],
    ["Apakah hasil backtest menjamin hasil ke depan?", "Tidak. Backtest memakai data masa lalu, sudah memasukkan biaya dan slippage, tetapi pasar bisa berubah. Karena itu hasil dipisah menjadi periode pilih dan periode uji. Anggap backtest sebagai gambaran perilaku strategi, bukan janji."],
    ["Kenapa daftar sinyal hari ini kosong?", "Syaratnya memang ketat. Hari tanpa sinyal itu normal, terutama saat IHSG melemah. Tidak membeli juga sebuah keputusan."],
    ["Di mana data jurnal dan portofolio saya disimpan?", "Hanya di browser perangkat ini (localStorage). Tidak dikirim ke server. Gunakan tombol ekspor untuk cadangan."],
  ];

  let q = "", wantGlos = null, built = false;
  function glosHTML(){
    const s = q.trim().toLowerCase();
    const list = GLOS_TERMS.filter(k => !s || (GLOS[k].t + " " + GLOS[k].d + " " + k).toLowerCase().includes(s));
    return list.length ? `<dl class="pd-glos">${list.map(k => `<div id="glos-${k}" tabindex="-1"><dt>${esc(GLOS[k].t)}</dt><dd>${esc(GLOS[k].d)}</dd></div>`).join("")}</dl>`
      : App.empty(`Tidak ada istilah yang cocok dengan “${esc(q)}”.`);
  }
  function focusGlos(){
    if(!wantGlos) return;
    const el = document.getElementById("glos-" + wantGlos);
    if(el){ el.scrollIntoView({block:"center"}); el.focus({preventScroll:true}); el.classList.add("is-hit"); setTimeout(() => el.classList.remove("is-hit"), 1600); wantGlos = null; }
  }
  function css(){
    if(document.getElementById("panduan-css")) return;
    const st = document.createElement("style"); st.id = "panduan-css";
    st.textContent = `
#panel-panduan .pd-steps{list-style:none;margin:0;padding:0;display:grid;gap:var(--sp-3);grid-template-columns:repeat(auto-fit,minmax(220px,1fr));counter-reset:s}
#panel-panduan .pd-steps li{counter-increment:s;border:1px solid var(--line);border-radius:var(--r-md);padding:var(--sp-3) var(--sp-4);background:var(--bg)}
#panel-panduan .pd-steps li::before{content:counter(s);display:inline-grid;place-items:center;width:26px;height:26px;border-radius:50%;background:var(--accent-soft);color:var(--accent);font-weight:700;margin-bottom:6px}
#panel-panduan .pd-steps b{display:block;margin-bottom:2px}
#panel-panduan .pd-steps p{margin:0;color:var(--muted);font-size:var(--fs-sm)}
#panel-panduan .pd-menu{display:grid;gap:var(--sp-3);grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
#panel-panduan .pd-menu article{border:1px solid var(--line);border-radius:var(--r-md);padding:var(--sp-3) var(--sp-4)}
#panel-panduan .pd-menu h4{margin:0 0 4px;font-size:var(--fs-md)}
#panel-panduan .pd-menu p{margin:0 0 6px;font-size:var(--fs-sm);color:var(--muted)}
#panel-panduan .pd-menu .when{color:var(--ink)}
#panel-panduan .pd-glos{margin:var(--sp-3) 0 0;display:grid;gap:var(--sp-2) var(--sp-4);grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
#panel-panduan .pd-glos>div{padding:var(--sp-2) var(--sp-3);border-radius:var(--r-md);border:1px solid transparent;transition:background .3s,border-color .3s}
#panel-panduan .pd-glos>div.is-hit{background:var(--accent-soft);border-color:var(--accent)}
#panel-panduan .pd-glos dt{font-weight:700}
#panel-panduan .pd-glos dd{margin:2px 0 0;color:var(--muted);font-size:var(--fs-sm)}
#panel-panduan details{border-top:1px solid var(--line);padding:var(--sp-3) 0}
#panel-panduan details:first-of-type{border-top:0}
#panel-panduan summary{cursor:pointer;font-weight:600}
#panel-panduan details p{margin:var(--sp-2) 0 0;color:var(--muted)}
#panel-panduan .pd-disc p{margin:0 0 var(--sp-2);color:var(--muted)}
#panel-panduan h3{margin:var(--sp-4) 0 var(--sp-2);font-size:var(--fs-sm);text-transform:uppercase;letter-spacing:.06em;color:var(--faint)}
#panel-panduan .pd-go{background:none;border:0;padding:0;color:var(--accent);font:inherit;font-size:var(--fs-sm);cursor:pointer;text-decoration:underline}`;
    document.head.appendChild(st);
  }
  function build(el){
    css();
    el.innerHTML = `
    <div class="card"><h2>Mulai dalam 3 langkah</h2>
      <ol class="pd-steps">
        <li><b>Lihat tren pasar</b><p>Buka <button class="pd-go" data-go="analisa">Analisa pasar</button>. Bila IHSG dan lebar pasar lemah, kecilkan risiko atau tunggu.</p></li>
        <li><b>Cari sinyal</b><p>Cek <button class="pd-go" data-go="setup">Setup A+</button>, lalu <button class="pd-go" data-go="momentum">Momentum</button> dan <button class="pd-go" data-go="pullback">Pullback</button>. Klik saham untuk grafik, entry dan stop loss.</p></li>
        <li><b>Hitung lot & catat</b><p>Masukkan entry dan SL di <button class="pd-go" data-go="kalkulator">Kalkulator</button>, lalu catat transaksinya di <button class="pd-go" data-go="jurnal">Jurnal</button>.</p></li>
      </ol>
      <p class="hint mt-4">Tekan <kbd>Ctrl</kbd>+<kbd>K</kbd> (atau <kbd>/</kbd>) untuk mencari menu atau kode saham dari mana saja. Tombol <span aria-hidden="true">ⓘ</span> di samping istilah menampilkan artinya.</p>
    </div>
    <div class="card"><h2>Isi tiap menu</h2>
      ${MENUS.map(([sec, items]) => `<h3>${esc(sec)}</h3><div class="pd-menu">${items.map(([id, name, what, when]) => `
        <article><h4><button class="pd-go" data-go="${id}">${esc(name)}</button></h4><p>${esc(what)}</p><p class="when"><b>Kapan dipakai:</b> ${esc(when)}</p></article>`).join("")}</div>`).join("")}
    </div>
    <div class="card"><h2>Glosarium</h2>
      <div class="toolbar"><input class="search" id="pd-q" type="search" placeholder="Cari istilah, mis. ATR atau VCP" aria-label="Cari istilah di glosarium" value="${esc(q)}"></div>
      <div id="pd-glos" aria-live="polite">${glosHTML()}</div>
    </div>
    <div class="card"><h2>Pertanyaan umum</h2>
      ${FAQ.map(([a, b]) => `<details><summary>${esc(a)}</summary><p>${esc(b)}</p></details>`).join("")}
    </div>
    <div class="card pd-disc" id="pd-disclaimer"><h2>Disclaimer</h2>
      <p>Meja Pantau IDX adalah alat bantu riset dan edukasi. Semua daftar, skor, sinyal, level entry/SL/TP, dan narasi dihasilkan otomatis dari data publik dan aturan teknikal, <b>bukan rekomendasi atau ajakan untuk membeli maupun menjual</b> efek apa pun.</p>
      <p>Data bisa terlambat, tidak lengkap, atau keliru. Harga tertunda sekitar 15 menit. Hasil backtest dan kinerja masa lalu tidak menjamin hasil di masa depan. Investasi saham mengandung risiko, termasuk kehilangan sebagian atau seluruh modal.</p>
      <p>Keputusan transaksi sepenuhnya tanggung jawab Anda. Cocokkan selalu dengan keterbukaan informasi resmi di idx.co.id, dan pertimbangkan berkonsultasi dengan penasihat berizin OJK. Pengelola situs tidak bertanggung jawab atas kerugian yang timbul dari penggunaan informasi di sini.</p>
    </div>`;
    el.querySelector("#pd-q").addEventListener("input", e => { q = e.target.value; el.querySelector("#pd-glos").innerHTML = glosHTML(); });
    el.addEventListener("click", e => { const g = e.target.closest(".pd-go[data-go]"); if(g) location.hash = g.dataset.go; });
    built = true;
  }
  App.glossary = GLOS;
  App.register("panduan", {
    render(el){ if(!built || !el.querySelector("#pd-q")) build(el); setTimeout(focusGlos, 0); },
  });
})();
