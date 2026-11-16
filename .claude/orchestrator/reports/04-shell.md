# Fase 4 — Shell & navigasi

## Diubah (docs/index.html saja)
- **Sidebar dikelompokkan** jadi 5 bagian `.side-sec`: Sinyal (Setup A+, Momentum, Pullback) · Analisis pasar (Analisa, Lonjakan, Peta & sektor, Grup) · Grafik (Grafik, Grafik Pro) · Data emiten (Aksi, Orang dalam, Fundamental, Kepemilikan) · Alat (Kalkulator, Jurnal, Portofolio). Tiap tombol membawa `data-sec` + `data-desc`.
- **Semantik (F-6.2):** `role="tablist"/"tab"` + `aria-selected` di sidebar diganti `<nav>` biasa dengan `aria-current="page"` (selektor CSS ikut diganti). `#pb-tabs` belum disentuh (jatah fase 6).
- **HP (≤760px):** bilah bawah hanya Setup A+, Momentum, Analisa, Grafik (`.prio`) + tombol **Lainnya** (`#more-btn`) yang membuka `<dialog id="more-sheet">` lembar bawah beranimasi (meluncur naik/turun, Esc/klik luar/tombol tutup, hormati reduced-motion). Lainnya ikut menyala bila menu aktif ada di dalam lembar.
- **Rute hash:** `#setup`, `#momentum`, … klik menu = `pushState`, pemulihan programatik = `replaceState`; `hashchange` mengaktifkan menu (tombol Back jalan). Urutan pemulihan: hash → menu tersimpan → Momentum.
- **Topbar:** chip status pasar `#mkt-chip` (Pra-buka 08.45 / Sesi 1 / Istirahat / Sesi 2 / Pra-tutup 15.50 / Tutup / Libur akhir pekan; Jumat sesi 1 s.d. 11.30, sesi 2 mulai 14.00) dihitung dari jam WIB, diperbarui tiap 30 dtk. `#fresh` kini ringkas "Data terakhir 22 Okt, 12.07 WIB" (atau "Live …"); rincian 4 waktu pindah ke `title`. IHSG pill & kotak cari tetap. Hari libur bursa nasional belum dihitung.
- **Page head:** eyebrow = nama kelompok, judul, plus `#page-desc` satu baris per menu.
- **Palet perintah** `<dialog id="cmdk">`: Ctrl/⌘+K atau "/" (di luar input); kotak cari topbar (`#gq`) membuka palet saat difokus (jalur HP). Cari menu + kode/nama saham dari `S.momentum.rows`; ↑/↓, Enter, Esc; combobox/listbox + `aria-activedescendant`; animasi dialog yang sudah ada.
- CSS baru di blok "Shell" tepat sebelum "7. Gerak halus" (blok gerak tidak diubah).

## Cara uji (sudah dijalankan)
Server `site` :8765, cache di-bust. Semua 16 menu via hash → panel tampil, tanpa geser horizontal (900px, gelap). Back setelah `#setup` kembali ke `#pullback`. Ctrl+K "bb" → BB* tampil, ↓ memindah pilihan, "jurnal"+Enter → `#jurnal`. Palet "BBRI"+Enter → Momentum + detail BBRI. 375px: bilah bawah 5 tombol, lembar Lainnya 12 item, scrollWidth = 375. 1440px terang: tanpa overflow. Konsol: tidak ada error JS baru; 404 hanya `data/setup_jurnal.json` dan `data/chart/BBRI.json` (sudah ada sebelumnya, data belum dibuat).

## Sisa
- Hari libur bursa (Lebaran dsb.) tampil "Tutup"/"Sesi" sesuai jam — perlu daftar libur bila mau akurat.
- `#pb-tabs` masih tablist tanpa panah keyboard (fase 6).
- Tidak commit/push.
