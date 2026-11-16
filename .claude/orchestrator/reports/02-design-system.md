# 02 — Design system

## Diubah
- `docs/index.html` `<style>`: ditulis ulang jadi satu lembar berurutan (token → dasar → kerangka → komponen → modul → media → gerak). Hilang: 5× `.tab`, 2× `.chip/.seg[aria-pressed]`, 2× `:focus-visible`, 2× `dialog::backdrop`, 2× media tablet, blok "Header ringkas"/hero/ruler/spark yang tak dipakai, `.tabs` lama, `!important` di `.pb-status`. Nilai akhir yang tampil dipertahankan; blok "Gerak halus" (sidebar meluncur, penanda aktif, bayangan topbar, menu bawah menyingkir, transisi dialog/panel, reduced-motion) utuh.
- Token baru: `--fs-2xs..--fs-2xl`, `--fs-display`, `--sp-1..--sp-8`, `--r-sm/md/lg/pill`, `--ctl-h` (34px, 38px di HP), `--ctl-px`, `--focus`, `--ma50`, `--ma150` (terang & gelap). Ukuran font liar diganti token di mana aman (beberapa nilai unik dibiarkan: 14/16/20/26/30/34/40px).
- Kontrol seragam: chip, seg, search, `.input/.select` baru, `.pb-sel`, input kalkulator, tombol tutup → tinggi `--ctl-h`, radius `--r-md` (chip pill), fokus satu gaya.
- Badge: satu aturan `.badge` + varian `--good/--warn/--down/--muted/--solid`; `.hgm`, `.pb-tag`, `.sc`, `.mo`, `.wl-item .tag` jadi alias (modul tidak perlu diubah). `.lvl/.act/.verdict/.ev-type` berbagi varian warna.
- `tabular-nums` eksplisit di tabel, `.cell b`, nilai IHSG, pita, kartu pullback, harga.
- Warna hex grafik/legenda (`#2F9BD6`, `#9B7BD4`, `#2F6FDB`, `#E08A3C`, logo) → token.
- Komponen status: CSS `.skel` (shimmer) dan `.state`; helper `App.skeleton(n)`, `App.empty(text,title)`, `App.error(text)`. Dipakai di grafikpro, grup, kepemilikan, lonjakan, peta, setup (memuat + backtest kosong), grafik pullback; teks "Belum ada…/Tidak ada…" di jurnal, porto, setup, grup, index → `App.empty`.
- `.claude/skills/idx-design-system/SKILL.md`: bagian Scales, Badge, Loading/empty/error, Numbers, urutan CSS.

## QA
Server `site` (8765), cache di-bust. Klik 16 tab lewat skrip di 375, 900 (gelap), 1440: `scrollWidth` ≤ lebar viewport di semua tab. Klaim audit 971px di Jurnal/Kalkulator/Kepemilikan/Porto/Fundamental **tidak terulang** di 375px (tambahan pengaman: `.search` min-width 0 di HP, `.calc input` max-width 100%, `.table-wrap` max-width 100%). Mode gelap dicek visual (Pullback), terang (Momentum 1440, Jurnal 375). Konsol: hanya 404 lama (`data/setup_jurnal.json` dsb., F-5.4, milik fase 5) — tidak ada error baru.

## Sisa
- Inline `style=""` di index.html masih ada (~25, kebanyakan text-align di sel tabel kosong) → fase 3 bisa ganti ke `App.empty` dalam `<td>`.
- `getJSON` masih menelan error, jadi `App.error` belum dipasang otomatis (butuh perubahan alur data; cocok fase 5).
- Modul js/ masih punya beberapa font-size px sendiri di CSS yang diinjeksi; tidak disentuh agar aman.
