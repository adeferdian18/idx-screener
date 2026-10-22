# Spesifikasi setup "Saham kuat yang sedang pullback"

Dirangkum dari halaman FAQ "cara hitung" situs referensi penyembuhluka.my.id (rekonstruksi
indikator DL-PHunter Pro di TradingView) dan dari data JSON-nya per 21 Okt 2026. Angka-angka
yang ditandai *(disimpulkan)* tidak tertulis di FAQ, tapi cocok dengan data situs. Tanda **(dikonfirmasi)**
= dicocokkan angka per angka oleh `pullback.py` terhadap 61 baris + riwayat situs 21 Okt 2026.

Data: harga TIDAK disesuaikan dividen (`auto_adjust=False`; PTBA 3210 -> 2800 pada ex-date 16 Okt muncul
apa adanya di situs) **(dikonfirmasi)**. Yahoo kadang melewatkan satu hari IHSG di data harian (21 Okt 2026);
`pullback.py` mengisinya dari candle 1 jam ^JKSE.

Data: harga harian 1 tahun Yahoo Finance (`KODE.JK`, IHSG `^JKSE`), seluruh saham BEI (~921).
Dihitung dua kali per hari bursa: setelah Sesi 1 (12:05 WIB, Jumat 11:35) dan setelah penutupan
(16:26 WIB). Di snapshot Sesi 1, candle hari ini belum tutup.

## 1. Tiga poin setup

| Poin | Rumus | Lolos jika |
|---|---|---|
| P1 Pullback | close ÷ SMA(close, 5) **(dikonfirmasi)** | < 1 |
| P2 Performance | (close ÷ close 50 bar lalu) ÷ (IHSG ÷ IHSG 50 bar lalu) **(dikonfirmasi 61/61)** | > 1,05 |
| P3 Volatility | ATR(5) ÷ close × 100; ATR = Wilder RMA dari True Range (benih TR pertama), bukan SMA **(dikonfirmasi: MARK 67,62)** | > 3 (%) |

Filter tampilan "Volat. 5 hari" (min 4–10%, maks 7–15%) hanya menyaring tabel, tidak mengubah sinyal.

## 2. Kekuatan relatif

- **Ranking 3 Bulan** (`rs3m_x`, di riwayat `r3`): persentil return 63 hari bursa dibanding semua saham
  yang dihitung hari itu, skala 0–100. Syarat setup: ≥ 70. Tabel diurutkan berdasarkan ini.
  ret63 = close ÷ close 63 bar lalu − 1 **(dikonfirmasi 61/61)**. Persentil = `rank(pct=True)×100` (1 desimal).
  Universe situs 921 termasuk ±78 saham suspensi (return 0%) yang tidak ada di scanner TradingView; tanpa
  mereka persentil di sekitar return 0% bergeser sampai ±1,7 poin.
- **Skor Momentum** (`rs_rating`, di riwayat `rs`): `raw_mom = ret63(saham) − ret63(IHSG)` dalam persen,
  lalu **percentrank 63 hari** dari deret raw_mom saham itu sendiri (`ta.percentrank`: % dari 63 nilai
  SEBELUMNYA yang ≤ nilai sekarang), dibulatkan ke bilangan bulat. Syarat trigger: ≥ 70.
  **(dikonfirmasi: 61/61 baris dan 52/52 titik riwayat)**
  Butuh ±6 bulan data; kurang dari itu status "Riwayat belum cukup".
- Label skor (keduanya): 90–100 Pemimpin, 70–89 Kuat, 50–69 Netral, 30–49 Laggard, 0–29 Lemah.

## 3. Garis Momentum (informasi, bukan syarat setup)

- Garis = close ÷ IHSG (`rl`), MA50-nya (`rm`) **(dikonfirmasi 52/52 titik riwayat)**.
- Momentum Positif (`rs_above_ma`): garis > MA50.
- Momentum Crossing (`rs_cross` = "Up"/"Down"): garis memotong MA50 hari itu.
- Momentum Puncak (`rs_high`): garis ≥ tertinggi 50 hari (termasuk hari ini) **(dikonfirmasi 61/61)**.
- Puncak+ (`rs_quality`): Puncak + harga naik hari itu + volume ≥ 1,2× rata-rata 5 hari sebelumnya + likuid.
- Momentum Duluan (`rs_lead`): Puncak, close belum tertinggi 50 hari, dan close ≥ close kemarin
  **(dikonfirmasi 61/61; 71 saham = isi tab Momentum Duluan situs)**.
  `lead_date` / `lead_days_ago` / `lead_close` = Momentum Duluan terakhir yang terjadi DI DALAM jendela
  watchlist (hari watchlist s.d. hari trigger / akhir jendela) dan ≤ 5 hari bursa lalu *(disimpulkan, 61/61)*.
  Momentum Duluan di luar jendela (mis. SGRO, PTBA 21 Okt) tidak mengisi `lead_date`.
- Momentum Penuh: Positif + Puncak + Duluan + Skor ≥ 70 + Ranking ≥ 70.

## 4. Status (mesin keadaan per saham)

1. **Setup valid**: P1, P2, P3 lolos dan Ranking 3 Bulan ≥ 70 pada hari yang sama.
2. **Watchlist**: hari pertama setup valid setelah hari yang tidak valid (▲ hijau di grafik). Watchlist baru
   menggantikan jendela lama, dan tetap boleh terbentuk walau posisi sebelumnya masih berjalan
   **(dikonfirmasi: model ini memberi 61/61 status; model "diblokir sampai posisi selesai" hanya 52/61)**.
   Bila hari setup-valid pertama sekaligus calon trigger jendela lama, yang berlaku watchlist baru (CLEO 20 Okt).
3. **Menunggu trigger**: jendela 5 candle setelah watchlist. `watch_days_left` = 5 − candle sejak watchlist
   (snapshot Sesi 1: + 1 karena candle hari ini belum tutup; 1 = hari ini terakhir).
   Candle watchlist sendiri tidak bisa memicu trigger.
4. **Entry trigger** (◆ biru), di dalam jendela, candle yang:
   - hijau (close > open),
   - volume ≥ 1,1× rata-rata volume 5 hari sebelumnya (`trig_vol_x`),
   - berpola bullish: Bullish Engulfing, Hammer, Inverted Hammer, Piercing Line, Bullish Harami,
     Morning Star, Bullish Marubozu (`pattern`),
   - Skor Momentum hari itu ≥ 70 (`trig_rs`).
   - KOREKSI: hari Momentum Duluan TETAP boleh jadi trigger (DMAS, AALI, AGII, CLAY, ABDA trigger di hari
     lead_date-nya); `trig_lead` hanya menandainya **(dikonfirmasi)**.
5. **Entry hari ini**: trigger di candle terakhir. **Entry baru**: trigger 1–5 hari bursa lalu.
   KOREKSI: selama 5 hari itu status TETAP "Entry baru" walau posisi sudah kena SL/TP (situs: 30 Entry baru =
   19 berjalan, 2 naik lagi, 7 kena SL, 2 kena TP; tidak ada baris berstatus "Kena SL"). Hasil posisi ada di
   `atr_trade`/`n_trade` ("Berjalan", "Belum terisi", "Kena SL", "Kena TP") dan `*_exit*`. "Kena SL, naik lagi" =
   `atr_trade` "Kena SL" dan close > `atr_sl`. Lewat 5 hari, status kembali dihitung biasa.
   `pullback.py` mereproduksi ringkasan 19/2/7/2 persis.
6. Jendela habis tanpa trigger → "Setup valid" (jendela trigger lewat) atau "Tidak ada sinyal".
   `rewatch_date` = watchlist terakhir setelah posisi SL/TP tetap (metode ATR) selesai; `rewatch_days_left`
   = sisa jendelanya bila masih berjalan *(disimpulkan, tidak ada di sampel)*.

## 5. Level harga (dibulatkan ke fraksi harga BEI, lihat `vcp.tick`)

- **ATR** (default): entry = close candle trigger; SL = entry − 1,5 × ATR(5) dibulatkan KE BAWAH;
  TP = entry + 3 × ATR(5) dibulatkan KE ATAS ke fraksi harga. ATR yang dipakai (kolom `atr`) = ATR di candle
  trigger, sedangkan P3 = ATR hari ini **(dikonfirmasi 59/61; 2 sisanya beda data Yahoo)**.
- **N-candle**: entry = high tertinggi 2 candle terakhir (order beli bersyarat, "Belum terisi" sampai
  tertembus); SL = low terendah 2 candle terakhir; TP = entry + 2 × (entry − SL) dibulatkan ke atas ke fraksi
  harga **(dikonfirmasi; DMAS 233 -> 234, BLTZ 6010 -> 6025)**.
- Saham yang belum trigger: level dihitung dari candle terakhir sebagai gambaran.
- **Lot** (`atr_lot`, `n_lot`): floor(Rp1.000.000 ÷ (risiko per lembar × 100)) dari level yang sudah
  dibulatkan **(dikonfirmasi 59/61)**.
- **Trailing stop**: stop awal = SL, naik mengikuti high tertinggi SETELAH candle trigger (high candle trigger
  sendiri tidak ikut) dengan jarak = risiko awal, dibulatkan ke bawah ke fraksi harga; tidak pernah turun, tanpa
  TP. Kenaikan stop dari high hari ini berlaku mulai candle berikutnya (nilai `atr_trail` yang ditampilkan sudah
  memuat high hari ini) **(dikonfirmasi 61/61 `atr_trail`, `atr_trail_out`, `n_trail_out`)**.
  Gap di bawah stop → keluar di harga open. Label "kemungkinan sudah kena" bila close < stop baru.
- Hasil posisi dicek dari high/low harian setelah trigger; bila SL dan TP tersentuh di hari yang sama,
  urutan tidak bisa dipastikan (anggap SL dulu, konservatif).

## 6. Kolom tambahan

- `adx`, `di_plus`, `di_minus`: ADX(14) Wilder gaya `ta.dmi` (RMA berbenih SMA) **(dikonfirmasi 57–59/61)**.
  `trend`: ADX < 25 "Lemah", 25–40 "Kuat", ≥ 40 "Sangat kuat"; "Naik" bila DI+ > DI−, selain itu "Turun"
  **(dikonfirmasi 61/61)**.
- KOREKSI: `value_avg` = rata-rata (close × volume) **5 hari termasuk hari ini** (bukan 20)
  **(dikonfirmasi 59/61)**; `liquid` = value_avg ≥ Rp1 M **(dikonfirmasi 61/61)**.
- `vol_ratio` = volume hari ini ÷ rata-rata 5 hari sebelumnya **(dikonfirmasi 60/61)**.
- `ext_atr` = (close − EMA(close, 21)) ÷ ATR(5) hari ini **(dikonfirmasi 61/61)**. Batas `extended` belum
  diketahui (semua contoh ≤ 2,61 dan false); `pullback.py` memakai > 3 *(ditebak)*.
  Filter likuiditas dan extended default mati.
- Pola candle (`pattern` = pola candle trigger untuk baris Entry, selain itu candle terakhir). Definisi
  *(disimpulkan, 61/61 baris; jumlah pola 21 Okt situs/kita: Engulfing 26/26, Marubozu 37/37, Harami 2/2,
  Piercing 1/1, Hammer 80/82, Inverted Hammer 6/5, Morning Star 6/3)*, tanpa filter tren:
  Engulfing (merah lalu hijau, open ≤ close kemarin, close ≥ open kemarin, badan lebih besar);
  Hammer (bayangan bawah ≥ 2× badan, atas ≤ 0,5× badan, badan > 0, boleh merah);
  Inverted Hammer (hijau setelah merah, atas ≥ 2× badan, bawah ≤ 0,5× badan, badan ≥ 10% rentang);
  Piercing (merah lalu hijau, open < low kemarin, close > tengah badan kemarin dan < open kemarin);
  Harami (merah lalu hijau, badan hijau tegas di dalam badan merah);
  Morning Star (H-2 merah, H-1 badan < 0,5× badan H-2 dan di bawah badan H-2, hari ini hijau tutup > tengah H-2);
  Marubozu (hijau, badan ≥ 85% rentang). Prioritas bila bentrok: Morning Star, Engulfing, Piercing, Hammer,
  Inverted Hammer, Harami, Marubozu. Dipakai juga lewat `pullback.detect_pattern(df)`.
- Kondisi pasar: IHSG vs MA50 (`ihsg_dist` %), `regime` Bullish/Bearish.
- Label Syariah (ISSI) dan HSC (High Shareholding Concentration) per saham.

## 7. Kontrak data di repo ini

Modul mesin: `pullback.py`. Fungsi publik yang dipakai modul lain:

- `pullback.compute(hist, ihsg, session="close") -> dict` — `hist`: `{KODE: DataFrame[Open,High,Low,Close,Volume]}`
  berindeks tanggal, `ihsg`: Series close IHSG. Mengembalikan objek JSON di bawah (belum ditulis ke disk).
- `pullback.main()` — unduh data, hitung, tulis file. CLI: `python pullback.py` (penutupan) dan
  `python pullback.py s1` (Sesi 1).

File keluaran (dibaca website `docs/index.html`):

```
docs/data/pullback.json      snapshot Penutupan
docs/data/pullback_s1.json   snapshot Sesi 1
{
  "market": {"as_of","session":"close|s1","session_label","generated_at","ihsg_close","ihsg_ma50",
             "ihsg_dist","regime":"Bullish|Bearish","universe"},
  "counts": {"Entry hari ini":n, "Entry baru":n, ...},
  "rows":   [ {satu objek per saham, NAMA KOLOM SAMA DENGAN SITUS REFERENSI:
               code,name,board,status,signal_date,days_since_signal,watch_days_left,last_trade,no_trade_today,
               close,chg,p1,p2,p3,p1_ok,p2_ok,p3_ok,rs_rating,raw_mom,rs_ok,ret3m,rs3m_x,rs3m_ok,
               rs_above_ma,rs_lead,rs_high,rs_quality,rs_cross,adx,di_plus,di_minus,trend,
               value_avg,value_today,vol_avg,vol_today,vol_ratio,liquid,ext_atr,extended,pattern,
               trig_lead,lead_date,lead_days_ago,lead_close,atr,atr_entry,atr_sl,atr_tp,n_entry,n_sl,n_tp,
               atr_lot,n_lot,atr_trade,n_trade,trig_vol_x,trig_rs,rewatch_date,rewatch_days_left,
               atr_exit,atr_exit_date,atr_pl,n_exit,n_exit_date,n_pl,
               atr_trail,atr_trail_out,atr_trail_exit,atr_trail_date,atr_trail_pl,
               n_trail,n_trail_out,n_trail_exit,n_trail_date,n_trail_pl,
               syariah,hsc} ]
}
docs/data/pullback_chart/KODE.json   (semua saham berstatus selain "Tidak ada sinyal")
{"code", "bars": [[tanggal,o,h,l,c,v,rs,r3,rl,rm], ...]  (±130 hari terakhir),
 "marks": {"watch":[tanggal..], "trigger":[tanggal..], "lead":[tanggal..], "rs_high":[..], "rs_cross":[..]}}
```

Status yang dipakai: "Entry hari ini", "Entry baru", "Menunggu trigger", "Setup valid", "Tidak ada sinyal",
"Riwayat belum cukup" (seperti situs; "Kena SL"/"Kena TP" hanya muncul di `atr_trade`/`n_trade`).
`market` juga memuat `lead_count` (isi tab Momentum Duluan) dan `patterns` (jumlah per pola).
`board` belum tersedia (null): universe.json tidak memuat papan pencatatan.
Nilai `*_trail_out`: "Berjalan", "Belum terisi", "Kena trailing", "Kemungkinan sudah kena".
Nilai kosong ditulis `null`.

## 8. Temuan backtest situs referensi (untuk konteks, bukan janji hasil)

- ~492 trigger Mei–Okt 2026 dengan SL tetap: rata-rata sekitar impas; volatilitas 3–7% paling baik,
  > 10% paling buruk.
- Trailing vs SL/TP tetap (1 tahun): ATR −0,14R vs −0,02R; N-candle −0,09R vs −0,11R per transaksi.
