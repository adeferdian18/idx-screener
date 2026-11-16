# 01 — Audit UI/UX (read-only)

Tanggal: 2026-11-16. Sumber: baca `docs/index.html` (2293 baris, CSS + JS inline), `docs/js/*.js` (9 modul), uji di server lokal `site` (port 8765), klik semua 16 tab lewat skrip.

Catatan uji: konsol menunjukkan **2 error 404** saat muat awal (lihat F-5.4). Ukuran pane berubah di tengah uji 375px sehingga angka `scrollWidth` untuk Jurnal/Kalkulator/Kepemilikan/Porto/Fundamental (971px) **belum terverifikasi** — fase 2/3 wajib cek ulang di 375px. Mode gelap dan 900px hanya diperiksa lewat kode (token), tidak visual.

---

## Fase 2 — Design system

**F-2.1 · P1 · CSS berlapis, aturan saling menimpa** — `docs/index.html` `<style>`: `.tab[aria-selected]` didefinisikan di baris 80, 373, 483, 511, 557; `.chip[aria-pressed]` di 85 dan 422; `.seg button[aria-pressed]` di 273 dan 422; `:focus-visible` di 45 (accent) lalu 357 (up); `dialog::backdrop` di 130 dan 449; `@media (max-width:1100px) and (min-width:761px)` dua kali (457, 540). Gaya lama tetap dimuat lalu ditimpa → sulit dirawat, mudah regresi.
*Perbaikan:* gabungkan jadi satu blok per komponen (tokens → base → layout → components → tab-specific → media), hapus definisi lama yang tertimpa.

**F-2.2 · P1 · Tidak ada skala tipografi** — 25 nilai `font-size` berbeda (10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 15, 16, 17, 18, 20, 22, 24, 26, 28, 30, 34, 40 px + 3 `clamp`), termasuk `15px !important`.
*Perbaikan:* token `--fs-xs:11px; --fs-sm:12px; --fs-base:14px; --fs-md:16px; --fs-lg:20px; --fs-xl:26px; --fs-2xl:clamp(28px,3vw,34px)` dan ganti semua nilai liar.

**F-2.3 · P2 · Radius tidak konsisten** — `border-radius` 2/3/4/6/8/10/12/14/16/999px/50%.
*Perbaikan:* `--r-sm:6px` (badge, kbd), `--r-md:10px` (input, chip, tombol), `--r-lg:16px` (card), `--r-pill:999px`.

**F-2.4 · P1 · Badge/tag diduplikasi 6×** — `.badge` (149), `.hgm` (201), `.wl-item .tag` (236), `.pb-tag` (317), `.sc` (319), `.mo` (322): semua "inline-block, 10–11px, 700, padding 1px 5–6px, radius 4px" dengan sedikit beda margin.
*Perbaikan:* satu `.badge` + varian `.badge--good/--warn/--down/--muted`; kelas lama jadi alias sementara.

**F-2.5 · P1 · Warna hard-coded melanggar token** — `.lv-e{color:#2F6FDB}` (164), `.logo svg path{stroke:#7FD8B4}`/`circle{fill:#F2C04A}` (367), legend inline `#2F9BD6`, `#9B7BD4` (699, 1404), seri grafik `#2F9BD6`, `#9B7BD4`, `#2F6FDB`, `#E08A3C` (1273, 1295, 1305, 1308, 1480, 1543). Tidak ikut mode gelap dan beda dengan `--blue` (#2F679E) yang di skill disebut warna entry.
*Perbaikan:* tambah token `--ma50`, `--ma150`, `--entry` (pakai `--blue`), `--purple`; baca lewat `col("--…")` di JS.

**F-2.6 · P2 · Gaya inline tersebar** — 34 `style="…"` di index.html dan 23 di `js/*.js` (mis. `<p class="hint" style="padding:12px">Memuat grafik…</p>` baris 2012).
*Perbaikan:* kelas utilitas kecil (`.pad`, `.mt-2`, `.legend i.--ma50`) atau komponen status (F-2.7).

**F-2.7 · P1 · Status memuat/kosong/error tidak seragam** — teks lepas "Memuat data…", "Memuat data pullback…", "Memuat hasil backtest…", "Memuat grafik…"; 33 varian teks kosong ("Tidak ada…", "Belum ada…") dengan markup berbeda; `getJSON` (806) menelan error → `null` sehingga gagal jaringan tampil sama dengan "kosong".
*Perbaikan:* `App.state(el, "loading"|"empty"|"error", pesan, aksiCoba)` menghasilkan `.state` (skeleton baris tabel untuk loading, ikon + kalimat + tombol "Coba lagi" untuk error).

**F-2.8 · P2 · Angka tanpa `tabular-nums`** — tabel, pita harga, `.cell b`, nilai IHSG tidak memakai `font-variant-numeric:tabular-nums`, kolom angka bergoyang saat live update.
*Perbaikan:* `table, .cell b, .index-val, .tape-track{font-variant-numeric:tabular-nums}`.

**F-2.9 · P2 · Kontrol form campur** — select memakai `.pb-sel`, input kalkulator `.calc input`, pencarian `.search`/`.t-search`/`.gsearch`, fokus ditangani terpisah (427, 379).
*Perbaikan:* satu `.input`/`.select` dengan tinggi 36px (40px di HP), radius `--r-md`, fokus seragam.

## Fase 3 — Tabel

**F-3.1 · P1 · Header urut tidak bisa dipakai keyboard** — `<th data-k>` / `data-mk` / `data-pk` (1038, 1152, 1865) hanya klik; tidak fokusable, tanpa `aria-sort="none"` pada kolom yang bisa diurut, penanda ▾/▴ hanya muncul pada kolom aktif.
*Perbaikan:* `<th aria-sort="none"><button class="th-sort">Label</button></th>`; ikon netral ↕ samar untuk kolom yang bisa diurut.

**F-3.2 · P2 · Tiga renderer tabel terpisah** — `COLS`, `MCOLS`, kolom pullback masing-masing punya kode header/sort sendiri; modul js/ membangun tabel dengan HTML string sendiri.
*Perbaikan:* helper `App.table({cols, rows, sort, onSort})` dengan definisi kolom `{key,label,align,fmt,mobile:true}`.

**F-3.3 · P1 · Tabel lebar di HP** — kemungkinan geser horizontal halaman pada Jurnal, Kalkulator, Kepemilikan, Porto, Fundamental (terukur 971px, belum terverifikasi). Kolom pertama (kode) tidak lengket saat tabel digeser.
*Perbaikan:* pastikan semua tabel di dalam `.table-wrap`; `td:first-child, th:first-child{position:sticky;left:0;background:var(--surface)}`; kolom sekunder `data-mobile="hide"` di <600px.

**F-3.4 · P3 · Baris klik tanpa affordance konsisten** — baris dengan `data-code` membuka detail, tapi hover/cursor dan fokus baris tidak seragam antar tab.
*Perbaikan:* `tr[data-code]{cursor:pointer} tr[data-code]:hover{background:var(--bg)}` + kode saham sebagai `<button>` agar bisa di-tab.

## Fase 4 — Shell & navigasi

**F-4.1 · P1 · 16 menu datar tanpa pengelompokan** — `.side-nav` (577–597) memuat Setup A+ … Jurnal berturut-turut; hanya pemisah visual. Pengguna baru tidak tahu urutan alur (sinyal → riset → eksekusi).
*Perbaikan:* grup berlabel "Sinyal" (Setup A+, Momentum, Pullback), "Pasar" (Analisa, Lonjakan, Peta, Grup), "Grafik", "Data emiten" (Aksi, Orang dalam, Fundamental, Kepemilikan), "Alat saya" (Portofolio, Kalkulator, Jurnal); eyebrow halaman menampilkan grup.

**F-4.2 · P1 · Tidak ada URL per tab** — tidak ada `location.hash`/`history`; tab tersimpan hanya lewat localStorage, sehingga tautan tidak bisa dibagikan dan tombol Back keluar situs.
*Perbaikan:* `#momentum`, `#saham/BBCA`; `hashchange` → pilih tab.

**F-4.3 · P2 · Status data di topbar terlalu padat** — `#fresh` (612, render di `renderHero` ~818) menulis 4 waktu ("Harga …, Momentum …, fundamental …, aksi korporasi …") dalam satu blok kecil; tidak ada status pasar buka/tutup/sesi.
*Perbaikan:* chip ringkas "Pasar tutup · data 16 Nov 16.15" + popover detail per sumber.

**F-4.4 · P2 · Pencarian global hanya kode** — `#gq` (606) mencari saham; tidak bisa lompat ke menu. Shortcut `/` ada tapi tidak diumumkan selain `<kbd>`.
*Perbaikan:* palet perintah (Ctrl+K dan `/`) mencari menu + saham.

**F-4.5 · P3 · Tombol tema memuat ulang halaman** — `location.reload()` (2267) saat ganti tema; terasa kasar.
*Perbaikan:* ganti token tanpa reload, lalu `applyOptions` tema ke grafik LWC yang aktif; TradingView embed saja yang dibangun ulang.

**F-4.6 · P3 · Elemen tersembunyi warisan** — `<div hidden aria-hidden="true">` berisi `#ruler-mark`, `#low52`, `#peak52`, `#ruler-note` (614) masih ditulis oleh `renderHero`.
*Perbaikan:* hapus elemen dan kode penulisnya, atau tampilkan di kartu IHSG.

## Fase 5 — Performa, SEO, PWA

**F-5.1 · P1 · ~4–5 MB data dimuat saat awal, tanpa cache** — `init` (2186) memuat paralel quotes, screener, corporate_actions (343 KB), momentum (830 KB), insider, live, `loadPullback` → pullback.json + pullback_s1.json (2×1,19 MB), lalu ksei (287 KB) — apa pun tab yang dibuka. Total transfer terukur ~5,6 MB. `getJSON` (806) memakai `?t=Date.now()` + `cache:"no-store"` sehingga tidak pernah ter-cache.
*Perbaikan:* muat per tab (lazy) seperti modul js/ sudah lakukan; ganti cache-busting dengan versi dari `quotes.updated` atau `fetch(..., {cache:"no-cache"})` (revalidasi ETag); ringkas JSON (bulatkan desimal) di pipeline Python bila fase itu mengizinkan.

**F-5.2 · P1 · Tidak ada meta SEO/OG/manifest** — `<head>` (1–11) hanya charset, viewport, title. Tidak ada `meta description`, `theme-color`, Open Graph, Twitter card, `manifest.webmanifest`, `apple-touch-icon`, canonical.
*Perbaikan:* tambah semuanya; `theme-color` dua nilai (`media="(prefers-color-scheme:dark)"`).

**F-5.3 · P2 · Favicon emoji** — `<link rel="icon">` data-URI `📈` (7) tampil beda per OS dan tidak profesional.
*Perbaikan:* SVG logo garis tren yang sama dengan `.logo` (warna token tetap), plus PNG 192/512 untuk manifest.

**F-5.4 · P2 · 404 saat muat** — konsol: 2× "Failed to load resource 404". Kandidat: `data/setup_jurnal.json` (js/setup.js:202, file tidak ada di `docs/data/`) dan satu file lain (cek Network).
*Perbaikan:* buat file kosong default di pipeline atau cek keberadaan sebelum fetch; jangan memunculkan error konsol.

**F-5.5 · P2 · Skrip tidak di-versi, pustaka dari unpkg dua tempat** — `js/*.js` (2283–2291) tanpa `?v=`; lightweight-charts dimuat dari unpkg di `loadLWC` (1245) dan di js/grafikpro.js:3 (URL diduplikasi).
*Perbaikan:* konstanta tunggal `App.LWC_URL`, `?v=<commit>` pada skrip, `<link rel="preconnect" href="https://unpkg.com">` atau self-host di `docs/vendor/`.

**F-5.6 · P2 · Monolit 2.300 baris** — CSS (~570 baris) dan JS (~1.500 baris) inline di index.html, tidak bisa di-cache terpisah.
*Perbaikan:* pindahkan ke `docs/css/app.css` dan `docs/js/app.js` dengan versi; service worker cache-first untuk shell, network-first untuk `data/`.

**F-5.7 · P3 · Google Fonts memuat 9 berat** — Plus Jakarta 400–800 + Literata 4 varian (10).
*Perbaikan:* pangkas ke 400/600/700 + Literata 600; `preload` satu woff2 utama.

## Fase 6 — Aksesibilitas

**F-6.1 · P1 · Kontras token gagal AA (terang)** — perkiraan: `--faint #80887F` di `--bg #F6F2EA` ≈ 3,3:1 (dipakai untuk label 11px, `.gsearch kbd`, `.index-name`); `--down #C4554A` di putih ≈ 4,3:1 (angka merah kecil); `--accent #A86F1C` di `--accent-soft #F6EAD3` ≈ 3,6:1 (`.badge`).
*Perbaikan:* `--faint:#6B7369`, `--down:#B2463C`, `--accent:#8F5C12`; verifikasi dengan alat kontras di kedua tema.

**F-6.2 · P1 · `role="tablist"` tanpa pola keyboard** — `.side-nav` (577) dan `#pb-tabs` (675) bertanda tablist/tab, tetapi tidak ada `aria-controls`, `tabindex` roving, atau panah kiri/kanan/atas/bawah (grep `ArrowDown` kosong).
*Perbaikan:* untuk sidebar lebih tepat `<nav>` + `aria-current="page"` (bukan tablist); untuk `#pb-tabs` implementasikan pola tab lengkap.

**F-6.3 · P2 · Dua gaya focus ring** — `:focus-visible` accent (45) lalu up (357); input memakai `outline:0` + box-shadow `--good-soft` (427) yang di mode terang kontrasnya rendah.
*Perbaikan:* satu `--focus` token, `outline:2px solid var(--focus);outline-offset:2px` untuk semua termasuk input.

**F-6.4 · P2 · Gerak** — pita harga animasi 90 detik (70) dan `.live-dot` pulse (262) tidak dimatikan di `prefers-reduced-motion` (hanya `.ruler-mark` dan sidebar yang ditangani di 350/474/563).
*Perbaikan:* matikan `animation` `.tape-track` & `.live-dot` di blok reduced-motion; pita tetap bisa digeser manual.

**F-6.5 · P2 · Info hanya lewat warna** — naik/turun memakai `.up`/`.down` warna saja di banyak sel; sebagian sudah ada tanda "+", nilai negatif tanpa panah.
*Perbaikan:* tanda ▲/▼ kecil atau tanda +/− selalu tampil; `aria-label` di sel penting.

**F-6.6 · P3 · Wilayah dinamis tidak diumumkan** — `#fresh`, status pullback `#pb-status`, hasil filter jumlah saham tidak memakai `aria-live`.
*Perbaikan:* `aria-live="polite"` pada status dan penghitung hasil.

## Fase 7 — Konten

**F-7.1 · P1 · Tidak ada panduan/onboarding** — istilah RS, VCP, Trend Template, ATR, N-candle, R, "Lolos/Hampir (6–7 dari 8)" muncul tanpa penjelasan, kecuali FAQ pullback (`#pb-faq`).
*Perbaikan:* halaman "Panduan" + glosarium; `<abbr title>`/tooltip `ⓘ` di label chip dan header kolom.

**F-7.2 · P1 · Disclaimer tidak menonjol / tidak ada footer** — tidak ada footer berisi sumber data, waktu pembaruan, dan pernyataan "alat bantu riset, bukan ajakan beli/jual".
*Perbaikan:* footer tetap di semua tab + satu kalimat disclaimer di halaman Setup A+.

**F-7.3 · P2 · Label campur Inggris/Indonesia** — "Setup A+", "Trailing stop", "N-candle", "Snapshot data", "FAQ · cara hitung", "Watchlist saya", "Grafik Pro".
*Perbaikan:* pertahankan istilah teknis yang lazim (RS, VCP, ATR) tetapi beri padanan: "Snapshot" → "Data per tanggal", "FAQ" → "Cara hitung", "Watchlist" konsisten satu istilah ("Pantauan").

**F-7.4 · P3 · Judul tab vs label menu berbeda** — `data-title="Peta saham & sektor"` vs label "Peta & sektor", "Transaksi orang dalam" vs "Orang dalam", "Screener fundamental" vs "Fundamental".
*Perbaikan:* sengaja boleh (label pendek), tapi tampilkan label menu sebagai eyebrow agar pengguna mengenali halaman yang sama.

---

## Top 10 dikerjakan dulu
1. F-5.1 Muat data per tab + hentikan `no-store`/`?t=` (≈5 MB per kunjungan).
2. F-2.1 Bersihkan CSS berlapis jadi satu definisi per komponen.
3. F-2.7 Komponen status loading/kosong/error seragam + "Coba lagi".
4. F-6.1 Perbaiki kontras `--faint`, `--down`, `--accent`.
5. F-3.3 Verifikasi & perbaiki geser horizontal 375px (Jurnal, Kalkulator, Kepemilikan, Porto, Fundamental) + kolom kode lengket.
6. F-2.2 / F-2.4 Skala tipografi token + satu komponen badge.
7. F-5.2 / F-5.3 Meta SEO/OG/theme-color, manifest, favicon SVG.
8. F-4.1 / F-4.2 Grup menu + URL hash per tab.
9. F-3.1 / F-6.2 Header urut berbasis tombol; perbaiki semantik tablist.
10. F-7.1 / F-7.2 Panduan + glosarium + footer disclaimer.
