# Fase 5 — Performa & SEO/PWA

## Hasil terukur (data/*.json, buka #momentum, `performance.getEntriesByType('resource')`)
| | Sebelum | Sesudah |
|---|---|---|
| Kunjungan pertama | 10 file, **4.126.134 B** (quotes, screener, corporate_actions, momentum, insider, live, pullback, pullback_s1, ksei, chart) | 4 file, **908.916 B** (quotes, momentum, live, chart/ULTJ) |
| Kunjungan ulang (data sama) | 4,1 MB lagi (`no-store` + `?t=`) | **~900 B** (304 Not Modified) |
Audit menyebut ~5,6 MB termasuk font/pustaka; bagian data turun ~78% di kunjungan pertama.

## Diubah
- **docs/index.html**
  - `getJSON(name, {optional})`: tanpa `no-store`/`?t=`. quotes, momentum, live: `cache:"no-cache"` (validasi ulang ETag/Last-Modified). File lain: `?v=<quotes.updated>` + cache default; menunggu `DATA.ready` (versi data) sebelum fetch. Gagal → `null` + `DATA.err[file]`; file opsional 404 tidak dihitung gagal dan diingat per versi di `localStorage["data-miss"]` (setup_jurnal.json hanya 404 sekali per versi data).
  - Pemuatan per tab: `need(key)` (dibagi antar-tab, tanpa permintaan ganda) + `TAB_NEEDS` (pullback/lonjakan→pb, aksi→actions, insider→insider+actions+ksei, screener→screener, kepemilikan→ksei) + `ensureTab()` saat menu dibuka. Detail saham (`openDetail`, kini async) memuat screener+aksi bila perlu. `loadAll` (60 dtk) hanya quotes + live; momentum tiap 10 menit. Bila `quotes.updated` berubah, data tab yang sudah dimuat ditandai basi dan dimuat ulang untuk tab aktif.
  - Status: kerangka memuat saat data tab belum datang; `App.error(teks, retryKey)` kini punya tombol **Coba lagi** (`[data-retry]`; "core" = quotes+momentum, "mod:x" = modul). Dipakai di Screener, Insider, Aksi, Pullback, Momentum (tabel & daftar terminal), Kepemilikan, Lonjakan, Grup, Setup. `.td-state` menjaga pesan di tabel tetap terbaca di HP.
  - `App.hasChart(kode)` (rumus sama dengan momentum.py: likuid && (tt_skor ≥ 6 || entry), cocok 78/78 file) → tidak ada lagi 404 `chart/BBRI.json`.
  - `<head>`: description, canonical, robots, Open Graph (+ukuran/alt gambar), Twitter summary_large_image, theme-color terang/gelap, color-scheme, favicon SVG, apple-touch-icon, manifest. Script modul `js/*.js?v=20261116`. Registrasi service worker hanya di https/localhost.
- **docs/js**: lonjakan memakai `App.need("pb")` (pullback.json tidak diunduh dua kali; sebelumnya juga ada potensi loop saat gagal); grup/setup: error + coba lagi, setup tidak lagi mengulang fetch tanpa henti bila gagal, setup_jurnal opsional; kepemilikan `App.dataState("ksei")`; grafikpro & porto cek `App.hasChart` dulu.
- **Baru**: `docs/manifest.webmanifest`, `docs/sw.js` (precache kerangka; data/*.json jaringan-dulu → cache saat offline, satu entri per file; font Google/unpkg stale-while-revalidate; cache `shell-<VERSION>` lama dihapus saat activate), `docs/favicon.svg`, `docs/og.png` 1200×630, `docs/icon-192.png`, `docs/icon-512.png` (maskable, zona aman 12%), `docs/apple-touch-icon.png`, `docs/robots.txt`, `docs/sitemap.xml`, `tools/brand_assets.py` (menggambar semua ikon/OG; jalankan ulang bila warna berubah).

## Cara uji (sudah dijalankan, server `site` :8765)
- Byte sebelum/sesudah seperti tabel di atas; kunjungan ulang 304.
- 16 menu diklik di 375 (gelap), 900 (terang), 1440 (gelap): `scrollWidth` = lebar viewport, tidak ada `.skel`/`.is-error` tertinggal, tabel terisi (insider 146, KSEI 121, screener 57, pullback 33 baris). Tidak ada respons ≥400 di dua muat terakhir (setup_jurnal diingat). Tidak ada error JS.
- Gagal jaringan disimulasikan (fetch ditolak untuk insider/screener) → kartu "Gagal memuat" + Coba lagi → klik → data tampil.
- Detail BBRI dari muat segar: screener+aksi dimuat saat itu, dialog terisi, tanpa 404 grafik.
- Offline: server dihentikan → reload → kerangka + Momentum + IHSG tampil dari cache SW; tab yang belum pernah dibuka (Screener) menampilkan error + Coba lagi.
- Manifest, ikon, og.png, robots, sitemap, sw.js → 200; 14 meta OG/Twitter.

## Sisa / catatan
- Naikkan `VERSION` di `docs/sw.js` **dan** `?v=` pada tag script tiap kali js/*.js berubah (keduanya `20261116`).
- robots.txt di subfolder `/idx-screener/` tidak dibaca crawler (robots hanya di root domain); sitemap tetap bisa dikirim lewat Search Console.
- Versi data mengikuti `quotes.updated`; jika suatu file (mis. ksei) diterbitkan ulang tanpa quotes berubah, browser memakai salinan lama paling lama sampai quotes berikutnya / max-age GitHub Pages (10 menit) + revalidasi.
- Ditemukan (tidak diubah): ada dua `function renderMarket` di index.html; yang kedua (chip status pasar) menimpa yang pertama (kotak `#mkt` momentum), jadi kotak `#mkt` tidak pernah dirender. Perlu dicek fase QA.
- Font Google tidak di-hosting sendiri; offline memakai cache runtime bila pernah dimuat.
- Tidak commit/push.
