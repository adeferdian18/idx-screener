# Rencana Upgrade Profesional — Meja Pantau IDX

Dibuat: 2026-11-16 14:06 WITA · Target selesai: 2026-11-17 06:00 WITA
Orkestrator: sesi Claude utama. Agen dijalankan **satu per satu** (tidak paralel), jadi tiap agen boleh menyentuh `docs/index.html` tanpa bentrok.

## Aturan untuk setiap agen
1. Baca dulu `.claude/skills/idx-design-system/SKILL.md`, `.claude/skills/idx-feature-module/SKILL.md`, `.claude/skills/idx-qa/SKILL.md`, lalu file laporan fase sebelumnya di `.claude/orchestrator/reports/`.
2. Jangan merusak fitur: semua tab (Setup A+, Momentum, Pullback, Analisa, Lonjakan, Peta, Grup, Grafik, Grafik Pro, Aksi, Insider, Screener, Kepemilikan, Kalkulator, Jurnal, Portofolio) tetap berfungsi.
3. Jangan mengubah logika data/sinyal Python kecuali fase itu memintanya. Jangan menyentuh `.github/workflows` kecuali diminta.
4. Bahasa UI: Indonesia. Tetap tema krem + mode gelap. Tidak memakai merek/nama Penyembuh Luka.
5. QA wajib sebelum selesai: server lokal `python -m http.server 8765 -d docs` (konfigurasi `site` di `.claude/launch.json`), cek konsol tanpa error baru, lebar 375 / 900 / 1440 tanpa geser horizontal, terang & gelap. Bust cache dengan `fetch(url,{cache:'reload'})` sebelum menguji.
6. **Tidak commit, tidak push.** Orkestrator yang memverifikasi dan commit per fase. Push hanya dengan izin pengguna.
7. Tulis laporan singkat ke `.claude/orchestrator/reports/<nomor>-<nama>.md`: apa yang diubah (file + ringkas), cara uji, sisa masalah.

## Fase (urut)
| # | Agen | Tujuan | Selesai bila |
|---|------|--------|--------------|
| 1 | Auditor UI/UX (read-only) | Audit seluruh situs: konsistensi visual, tipografi, jarak, tabel, status kosong/memuat, aksesibilitas, performa, SEO. Daftar temuan berprioritas. | `reports/01-audit.md` berisi ≥20 temuan berprioritas P1–P3 dengan lokasi file/selector |
| 2 | Desainer sistem | Rapikan design system: skala tipografi & spasi, tombol/chip/seg/input seragam, kartu, badge, angka `tabular-nums`, skeleton loading & status kosong yang seragam | Semua tab memakai komponen yang sama; tidak ada gaya liar |
| 3 | Spesialis tabel & data | Tabel profesional: header lengket, penanda urut, rata kanan angka, warna naik/turun konsisten, baris hover, di HP kolom penting tetap terbaca | Semua tabel utama konsisten |
| 4 | Shell & navigasi | Topbar & page-head profesional: status pasar (buka/tutup/sesi), waktu data terakhir, breadcrumb kelompok menu, palet perintah (cari menu+saham) | Navigasi cepat dan jelas di 3 ukuran layar |
| 5 | Performa & SEO/PWA | Meta deskripsi/OG/Twitter, favicon SVG, manifest + service worker (offline shell, cache data jaringan-dulu), versi aset untuk bust cache, modul dimuat saat perlu bila aman | Lighthouse-style cek manual: meta lengkap, bisa di-install, tidak ada regresi |
| 6 | Aksesibilitas | Kontras WCAG AA, focus ring, label aria, navigasi keyboard, `prefers-reduced-motion` | Tidak ada pelanggaran kontras di token; semua kontrol bisa di-tab |
| 7 | Konten & bantuan | Halaman "Panduan" (cara pakai tiap menu, glosarium RS/VCP/R, disclaimer), tooltip istilah, footer profesional | Pengguna baru paham alur tanpa bertanya |
| 8 | QA akhir | Uji menyeluruh semua tab, perbaiki bug kecil yang ditemukan, laporan akhir | `reports/08-qa.md` bersih |

## Log orkestrator
(diisi setelah tiap fase: waktu mulai/selesai, commit, catatan)

- Fase 1 selesai 14:09: reports/01-audit.md (30 temuan). Tidak ada perubahan kode.
