# Fase 3 — Tabel & data

## Yang diubah
- `docs/index.html` CSS tabel (satu definisi):
  - `.table-wrap` max-height `min(72vh,780px)` → header lengket di dalam wrap (pengecualian: `.is-short`, tabel dalam `dialog`). `border-collapse:separate` supaya sticky th/td rapi.
  - Header urut (`th[data-k|data-mk|data-pk|data-sort]`): pointer, ikon netral ↕ samar, ▲/▼ berwarna `--up` sesuai `aria-sort`, `:focus-visible` ring. Header biasa `cursor:default`.
  - Baris: hover halus untuk semua; `cursor:pointer` hanya untuk baris yang bisa diklik (`tr[data-code|data-mcode|data-pb|data-ljc]`).
  - Kelas baru: `td.td-empty` (pesan kosong di tabel), `td.td-wrap`, `th.l/td.l`, `table.num2` (kolom 2 angka → kanan; dipakai Grup, Lonjakan, Porto, Peta, sektor Kepemilikan, juga `#m-table/#bt-table/#an-sektor`), utilitas tata letak `.mt-2 .mt-4 .m-0 .mb-3 .row-between .bold .td-chg .code-link .pad-3 .span-all .grid-240 .table-wrap.inset .pb-card.is-static .kp-sort`.
  - ≤760px: kolom pertama lengket kiri (`position:sticky;left:0` + garis pemisah), di Screener (`#sc-table`) & Orang dalam (`#ins-table`) kolom 2 (kode) yang lengket karena kolom 1 = nomor/tanggal; padding sel lebih rapat.
- `docs/index.html` JS: `prepSortTh` + MutationObserver memberi `tabindex=0` dan `aria-sort="none"` ke semua header urut (termasuk yang dirender ulang); Enter/Spasi mengurut dan fokus kembali ke header yang sama setelah render.
- Inline style → kelas: index.html ~22 dibuang (sisa 10 = lebar bar/posisi/ warna legenda dinamis yang sah); `js/grup.js`, `lonjakan.js`, `kepemilikan.js`, `setup.js`, `peta.js`, `kalkulator.js` (gaya tabel/tata letak). `peta.js` tidak lagi menulis ▲▼ sendiri (pakai CSS).
- Data dan arti kolom tidak diubah.

## Cara uji
Server `site` 8765, cache di-bust. Skrip klik 16 tab di 375 (gelap), 900 (terang), 1440 (gelap): `scrollWidth` = lebar viewport di semua tab. Semua tabel data berada di `.table-wrap` (tabel lain di halaman = internal lightweight-charts). Keyboard: fokus header "Harga" Screener → Enter → `aria-sort=descending`, fokus tetap di header. Sticky kolom kode terverifikasi di 375 (left 1px saat wrap digeser). Konsol: hanya 404 lama `data/*.json` (fase 5).

## Sisa
- Portofolio/Jurnal/Kalkulator kosong di data lokal (tabel muncul setelah ada isian) — gaya mengikuti aturan global, belum dilihat dengan data.
- Pratinjau lokal selalu render terang; mode gelap hanya diandalkan lewat token.
- Helper tunggal `App.table()` (F-3.2) belum dibuat; renderer tetap terpisah tapi berbagi CSS/perilaku.
- Tabel tidak urut di modul (Kepemilikan pakai select urut, Grup, Lonjakan) tidak dijadikan sortable.
