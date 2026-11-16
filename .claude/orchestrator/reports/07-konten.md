# Fase 7 — Konten & bantuan

## Diubah
- **docs/js/panduan.js (baru)**: modul `panduan` (#panduan). Isi: "Mulai dalam 3 langkah" (tombol langsung ke Analisa → Setup A+/Momentum/Pullback → Kalkulator/Jurnal), satu kartu per menu (16 menu, isi dari UI/kode yang ada: apa, kapan dipakai), glosarium 20 istilah yang bisa dicari (RS Rating, RSI, RS Line, Trend Template, Stage 2, VCP, pivot, buy-stop, SL/TP, R, expectancy, win rate, ATR, pullback, likuiditas, HSC, syariah, KSEI, sesi, data tertunda), FAQ 6 butir (sumber & keterlambatan, jadwal sesuai cron di .github/workflows, kenapa tidak 90% menang, backtest bukan jaminan, sinyal kosong, penyimpanan lokal), disclaimer lengkap. CSS diawali `#panel-panduan`.
- Popover istilah juga ada di panduan.js: tombol `.term-i[data-term]` membuka popover (role=dialog, aria-expanded, Esc menutup dan fokus kembali, klik di luar/gulir menutup, tautan "Lihat di Panduan" melompat & menyorot istilah). Handler fase-tangkap sehingga klik/Enter di tombol dalam `<th>` tidak ikut mengurutkan kolom.
- **docs/index.html**: helper `termI(key,label)` = `App.term`; tombol istilah di header Momentum (RS, Trend Template), header "R saat ini" tabel sinyal, dan di samping seg ATR/N-candle Pullback. Grup menu baru "Bantuan" + tombol Panduan (otomatis masuk palet Ctrl+K dan lembar "Lainnya"). `<section id="panel-panduan">`. Footer baru `.site-foot` (nama situs, disclaimer singkat, "bukan rekomendasi beli/jual", sumber data Yahoo ±15 menit/KSEI/keterbukaan BEI, jadwal pembaruan, tautan Panduan, tahun otomatis). Jadwal aksi korporasi lama di footer ("12:30") tidak cocok dengan workflow → diperbaiki di FAQ. CSS `.term-i`, `.term-pop`, `.site-foot`.
- **js/setup.js**: ⓘ di header RS, R, dan judul "VCP". **js/jurnal.js**: ⓘ di header R.
- Microcopy: sapaan diseragamkan ke "Anda" (index.html 3 tempat, porto.js 2 tempat: "kamu"/"hasilmu").
- Versi aset: semua `?v=` → `20261116b`, `VERSION` di sw.js → `20261116b`, `panduan` ditambah ke daftar precache.

## Uji
Server `site` (8765), SW & cache dibersihkan, aset di-fetch `cache:'reload'`.
- 1440 terang, 900 terang, 375 gelap: tidak ada geser horizontal di panduan, momentum, pullback, setup, jurnal, porto. Footer satu kolom ≤900px.
- Glosarium: cari "atr" → 1 hasil; kosong → 20.
- Popover: klik ⓘ di th → popover tampil, aria-sort th tidak berubah; Esc menutup; "Lihat di Panduan" → #panduan, fokus ke `#glos-rs`. Di 375px popover tetap dalam layar.
- Panduan muncul di palet perintah dan di lembar "Lainnya" HP.
- Konsol: tidak ada error JS. Ada entri 404/ERR_FAILED lama di log jaringan dari saat cache SW dibersihkan; semua permintaan aset/data setelah muat ulang 200.

## Sisa
- Tooltip belum ditaruh di Pullback (kolom), Grafik Pro, Kalkulator; sengaja dibatasi agar tidak ramai.
- Tinjauan microcopy hanya dangkal (sapaan, satu jadwal salah); tidak ada salah ketik nyata yang ditemukan lewat pencarian pola. `side-note` di sidebar tetap (menduplikasi footer, tidak mengganggu).
