"""
Fase 4 (A10): Backtest strategi momentum (Trend Template + RS + VCP + pivot breakout) di seluruh saham BEI.

Dua cara eksekusi diuji terpisah:
  A. "Beli besok pagi": sinyal (tutup di atas pivot + volume 1,5x) baru diketahui setelah pasar tutup,
     beli di OPEN hari berikutnya. Dilewati kalau open sudah di atas zona beli (+5%) atau di bawah SL.
  B. "Buy-stop di pivot" (alur modul: pasang alert malam hari, eksekusi di jam bursa): beli saat harga
     menembus entry di hari itu, di max(open, entry). Syarat volume hari itu >= 1,5x rata-rata dipakai sebagai
     pengganti "laju volume" intraday. Di hari beli, SL hanya dihitung kena jika harga TUTUP di bawah SL dan
     TP belum dihitung (urutan intraday tidak diketahui).
  C. "Buy-stop tanpa syarat volume": sama dengan B tapi tanpa filter volume, karena volume akhir hari belum
     diketahui saat order terisi. Selisih B dan C menunjukkan seberapa besar hasil B bergantung pada informasi
     yang baru pasti setelah pasar tutup.
  D. "Beli menjelang tutup": harga tutup di atas pivot dan volume >= 1,5x sudah terlihat menjelang penutupan
     (pre-closing 15:50-16:00 WIB), beli di harga TUTUP hari itu. Dilewati jika tutup > zona beli.
  - Biaya: beli 0,15%, jual 0,25% (termasuk PPh final 0,1%), slippage 0,1% tiap sisi.
  - Gap: kalau open sudah di bawah stop, keluar di harga open (lebih buruk dari SL).
  - Keluar bertahap: 50% di 2R, stop sisa posisi naik ke titik impas, sisanya di 3R.
    Time stop 7 hari bursa jika belum naik 1R; paksa keluar setelah 40 hari.
  - SL dan TP tersentuh di candle yang sama -> anggap SL lebih dulu.
  - Ekuitas: risiko 1% modal per trade, nilai posisi maksimal 25% modal.

Keterbatasan yang tetap ada: universe = saham yang MASIH tercatat hari ini (survivorship bias, hasil cenderung
sedikit terlalu bagus), data Yahoo bisa bolong, dan ARB/suspensi tidak dimodelkan selain lewat gap.

Hasil: docs/data/backtest.json dan data/backtest_trades.csv. Dijalankan mingguan (bukan harian) karena berat.
"""

import json
import math
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

import momentum as mom
import vcp

PERIOD = "5y"
BUY_FEE, SELL_FEE, SLIP = 0.0015, 0.0025, 0.001
RISK, MAX_POS = 0.01, 0.25
MAX_HOLD = 40
MIN_VALUE = mom.MIN_AVG_VALUE_IDR

BASE = Path(__file__).parent
WIB = dt.timezone(dt.timedelta(hours=7))


def matrices(hist, ihsg):
    idx = ihsg.index
    get = lambda k: pd.DataFrame({c: h[k] for c, h in hist.items()}).reindex(idx)  # noqa: E731
    return get("Open"), get("High"), get("Low"), get("Close"), get("Volume").fillna(0)


def rs_rating_matrix(C):
    roc = lambda k: C / C.shift(k) - 1  # noqa: E731
    raw = 0.4 * roc(63) + 0.2 * roc(126) + 0.2 * roc(189) + 0.2 * roc(252)
    return raw.rank(axis=1, pct=True) * 98 + 1


def trend_template_matrix(H, L, C, rs):
    m50, m150, m200 = C.rolling(50).mean(), C.rolling(150).mean(), C.rolling(200).mean()
    hi52, lo52 = H.rolling(252, min_periods=200).max(), L.rolling(252, min_periods=200).min()
    return ((C > m150) & (C > m200) & (m150 > m200) & (m200 > m200.shift(21)) & (m50 > m150) & (m50 > m200)
            & (C > m50) & (C >= lo52 * 1.25) & (C >= hi52 * 0.75) & (rs >= 70))


def market_series(ihsg):
    m50, m200 = ihsg.rolling(50).mean(), ihsg.rolling(200).mean()
    up = (ihsg > m50) & (ihsg > m200) & (m200 > m200.shift(21))
    return pd.Series(np.where(up, "uptrend", np.where(ihsg > m200, "tertekan", "downtrend")), index=ihsg.index)


def run_trade(o, h, l, c, d, lv, mode):
    """Simulasi satu trade dari sinyal di hari d. Return (dict, None) atau (None, alasan dilewati)."""
    n = len(c)
    if mode == "eod":
        e_i = d + 1
        if e_i >= n or not np.isfinite(o[e_i]):
            return None, "belum ada hari berikutnya"
        if o[e_i] > lv["beli_maks"]:
            return None, "gap di atas zona beli"
        if o[e_i] <= lv["sl"]:
            return None, "gap di bawah SL"
        raw = o[e_i]
    elif mode == "close":
        e_i = d
        if c[d] > lv["beli_maks"]:
            return None, "tutup di atas zona beli"
        raw = c[d]
    else:
        e_i = d
        if o[d] > lv["beli_maks"]:
            return None, "gap di atas zona beli"
        raw = max(o[d], lv["entry"])
    buy = raw * (1 + SLIP)
    cost = buy * (1 + BUY_FEE)
    sl = lv["sl"]
    r_unit = buy - sl
    tp1, tp2 = buy + 2 * r_unit, buy + 3 * r_unit
    stop, left, proceeds, half_done = sl, 1.0, 0.0, False
    exit_i, why = None, None

    def sell(px, frac):
        nonlocal proceeds, left
        proceeds += frac * px * (1 - SLIP) * (1 - SELL_FEE)
        left -= frac

    for i in range(e_i, n):
        oi, hi, lo, ci = o[i], h[i], l[i], c[i]
        if not np.isfinite(ci):
            continue
        if i == e_i and mode == "close":            # beli di harga tutup: risiko baru mulai besok
            continue
        if i == e_i and mode == "pivot":            # beli di tengah candle: hanya harga tutup yang pasti
            if ci <= stop:
                sell(ci, left); exit_i, why = i, "SL"
                break
            continue
        if i > e_i and oi <= stop:                  # gap turun melewati stop
            sell(oi, left); exit_i, why = i, "gap SL" if not half_done else "gap impas"
            break
        if lo <= stop:
            sell(stop, left); exit_i, why = i, "SL" if not half_done else "impas"
            break
        if not half_done and hi >= tp1:
            sell(max(tp1, oi) if i > e_i else tp1, 0.5); half_done, stop = True, buy
        if half_done and hi >= tp2:
            sell(max(tp2, oi) if i > e_i else tp2, left); exit_i, why = i, "TP2"
            break
        held = i - e_i
        if not half_done and held >= vcp.TIME_STOP and ci < buy + r_unit:
            sell(ci, left); exit_i, why = i, "time stop"
            break
        if held >= MAX_HOLD:
            sell(ci, left); exit_i, why = i, "maks 40 hari"
            break
    if exit_i is None:
        return None, "masih berjalan"
    net_r = (proceeds - cost) / r_unit
    return {"beli": round(buy, 2), "sl": sl, "r_pct": r_unit / buy, "keluar_i": exit_i, "alasan": why,
            "net_r": net_r, "ret": proceeds / cost - 1, "hari": exit_i - e_i + 1}, None


def stats(tr):
    if not len(tr):
        return {"trade": 0}
    r = tr["net_r"]
    wins, losses = r[r > 0], r[r <= 0]
    streak = best = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        best = max(best, streak)
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else None
    return {
        "trade": int(len(tr)), "menang": round(float((r > 0).mean()), 4),
        "rata_r": round(float(r.mean()), 3), "median_r": round(float(r.median()), 3),
        "se_r": round(float(r.std(ddof=1) / math.sqrt(len(r))), 3) if len(r) > 1 else None,
        "rata_menang_r": round(float(wins.mean()), 3) if len(wins) else None,
        "rata_kalah_r": round(float(losses.mean()), 3) if len(losses) else None,
        "profit_factor": round(float(pf), 2) if pf else None,
        "rata_hari": round(float(tr["hari"].mean()), 1), "kalah_beruntun_maks": int(best),
        "rata_return": round(float(tr["ret"].mean()), 4),
    }


def equity(tr, dates):
    """Ekuitas dengan risiko 1%/trade (nilai posisi maks 25%), dibukukan di tanggal keluar."""
    eq, curve = 1.0, {}
    for _, t in tr.sort_values("tgl_keluar").iterrows():
        risk = min(RISK, MAX_POS * t["r_pct"])
        eq *= 1 + risk * t["net_r"]
        curve[t["tgl_keluar"]] = eq
    s = pd.Series(curve)
    s.index = pd.to_datetime(s.index)
    s = s.reindex(dates).ffill().fillna(1.0)
    dd = float((s / s.cummax() - 1).min())
    years = max((dates[-1] - dates[0]).days / 365.25, 0.1)
    return s, {"total": round(float(s.iloc[-1] - 1), 4), "cagr": round(float(s.iloc[-1] ** (1 / years) - 1), 4),
               "max_dd": round(dd, 4)}


def main():
    uni = mom.load_universe()
    codes = [u["kode"] for u in uni]
    print(f"Backtest: unduh {len(codes)} saham ({PERIOD})...")
    ihsg = mom.download_ihsg(PERIOD)
    hist = mom.download(codes, PERIOD)
    for c, h in hist.items():
        h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
    O, H, L, C, V = matrices(hist, ihsg)
    rs = rs_rating_matrix(C)
    tt = trend_template_matrix(H, L, C, rs)
    value20 = (C * V).rolling(20).mean()
    zero20 = (V == 0).rolling(20).sum()
    tradable = (value20 >= MIN_VALUE) & (zero20 < 5)
    v50 = V.rolling(50).mean().shift(1)
    mkt = market_series(ihsg)
    dates = ihsg.index
    start = 260  # perlu 252 hari untuk RS & high/low 52 minggu
    print(f"  periode uji {dates[start]:%Y-%m-%d} s.d. {dates[-1]:%Y-%m-%d}")

    results = {}
    for mode in ("close", "pivot", "pivot_semua", "eod"):
        results[mode] = scan(mode, hist, dates, start, O, H, L, C, V, tt, tradable, v50, rs, mkt)
    payload = {
        "updated": dt.datetime.now(WIB).isoformat(timespec="minutes"),
        "periode": [f"{dates[start]:%Y-%m-%d}", f"{dates[-1]:%Y-%m-%d}"],
        "asumsi": {
            "biaya_beli": BUY_FEE, "biaya_jual": SELL_FEE, "slippage": SLIP, "risiko_per_trade": RISK,
            "posisi_maks": MAX_POS, "keluar": "50% di 2R, stop ke impas, sisa di 3R; time stop 7 hari; maks 40 hari",
            "catatan": "Universe = saham yang masih tercatat hari ini (survivorship bias). Hasil masa lalu tidak menjamin hasil ke depan.",
        },
        "ihsg": {"total": round(float(ihsg.iloc[-1] / ihsg.iloc[start] - 1), 4)},
        "strategi": {},
    }
    labels = {"close": "Beli menjelang tutup (volume sudah terkonfirmasi)", "pivot": "Buy-stop di pivot + volume 1,5x", "pivot_semua": "Buy-stop di pivot tanpa syarat volume",
              "eod": "Beli besok pagi (setelah sinyal EOD)"}
    for mode, (tr, skipped) in results.items():
        if tr.empty:
            continue
        payload["strategi"][mode] = report(tr, skipped, dates[start:], ihsg, labels[mode])
        tr.to_csv(mom.DATA_DIR / f"backtest_trades_{mode}.csv", index=False)
        s_ = payload["strategi"][mode]["ringkasan"]
        print(f"[{labels[mode]}] {s_['trade']} trade, menang {s_['menang']:.0%}, rata {s_['rata_r']:+.2f}R, "
              f"PF {s_['profit_factor']}, ekuitas {s_['total']:+.0%} (CAGR {s_['cagr']:+.1%}, max DD {s_['max_dd']:.1%}), dilewati {skipped}")
        for g in payload["strategi"][mode]["per_pasar"]:
            print(f"    {g['kelompok']:10} {g['trade']:4} trade, menang {g['menang']:.0%}, rata {g['rata_r']:+.2f}R")
    payload["kesimpulan"] = kesimpulan(payload["strategi"], payload["ihsg"]["total"])
    print("Kesimpulan:", *payload["kesimpulan"], sep="\n  ")
    (mom.SITE / "backtest.json").write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print("Tersimpan: docs/data/backtest.json")


def kesimpulan(st, ihsg_total):
    """Kalimat ringkas dari angka backtest, ditulis apa adanya (termasuk kalau hasilnya buruk)."""
    f = lambda x: f"{x:+.2f}".replace(".", ",") + "R"  # noqa: E731
    p = lambda x: f"{x * 100:+.0f}%"  # noqa: E731
    out = []
    a, b, c = st.get("pivot", {}).get("ringkasan"), st.get("pivot_semua", {}).get("ringkasan"), st.get("eod", {}).get("ringkasan")
    cl = st.get("close", {}).get("ringkasan")
    if b:
        out.append(f"Cara yang benar-benar bisa dijalankan tanpa data intraday, buy-stop di pivot, menghasilkan "
                   f"{f(b['rata_r'])} per trade setelah biaya ({b['trade']} trade, menang {b['menang']:.0%}, "
                   f"ekuitas {p(b['total'])}, penurunan terdalam {p(b['max_dd'])}; IHSG {p(ihsg_total)}).")
        lo, hi = b["rata_r"] - 2 * b["se_r"], b["rata_r"] + 2 * b["se_r"]
        out.append(f"Rentang kepercayaan ~95% untuk rata-rata itu {f(lo)} sampai {f(hi)}"
                   + (": belum terbukti berbeda dari nol, jadi anggap edge-nya tipis atau belum ada." if lo <= 0 < hi
                      else ": positif secara statistik."))
    if a and b:
        out.append(f"Kalau hanya breakout yang volumenya akhirnya ≥ 1,5× rata-rata yang diambil, hasilnya {f(a['rata_r'])} "
                   f"per trade. Selisih ini menunjukkan edge strategi ada di konfirmasi volume saat breakout, tapi "
                   f"volume akhir hari belum diketahui saat order terisi: angka ini batas atas, bukan janji.")
    if c and cl:
        out.append(f"Menunggu konfirmasi lalu membeli saat tutup ({f(cl['rata_r'])}) atau besok pagi ({f(c['rata_r'])}) "
                   f"menghapus hampir seluruh edge, karena keuntungan breakout terjadi di hari breakout itu sendiri.")
    out.append("Praktiknya: pasang alert di entry pada malam hari, eksekusi di jam bursa hanya jika laju volume "
               "hari itu terproyeksi ≥ 1,5× rata-rata; data realtime (misalnya DSI) membuat cek laju volume ini jauh lebih akurat.")
    return out


def scan(mode, hist, dates, start, O, H, L, C, V, tt, tradable, v50, rs, mkt):
    trades, skipped = [], {}
    for c in hist:
        o, hh, ll, cc, vv = (M[c].to_numpy(float) for M in (O, H, L, C, V))
        ttc, trc, vb, rsc = tt[c].to_numpy(), tradable[c].to_numpy(), v50[c].to_numpy(float), rs[c].to_numpy(float)
        frame = pd.DataFrame({"Open": o, "High": hh, "Low": ll, "Close": cc, "Volume": vv}, index=dates)
        valid_rows = np.isfinite(cc)
        pos = np.cumsum(valid_rows) - 1          # posisi baris di frame tanpa NaN
        f = frame[valid_rows]
        d = start
        while d < len(dates) - 1:
            # mode pivot hanya memakai informasi sebelum hari itu dibuka (tren kemarin)
            intraday = mode.startswith("pivot")
            tr_ok = ttc[d - 1] if intraday else ttc[d]
            vol_ok = mode == "pivot_semua" or (np.isfinite(vb[d]) and vv[d] >= vcp.VOL_BREAKOUT * vb[d])
            if not (tr_ok and trc[d - 1] and valid_rows[d] and vol_ok):
                d += 1
                continue
            k = pos[d]
            v = vcp.find_vcp(f.iloc[:k])
            if not v["valid"] or f["Close"].iloc[k - 1] > v["pivot"]:
                d += 1
                continue
            lv = vcp.levels(v)
            hit = hh[d] >= lv["entry"] if intraday else cc[d] > v["pivot"]
            if not hit:
                d += 1
                continue
            res, why = run_trade(o, hh, ll, cc, d, lv, "pivot" if intraday else mode)
            if res is None:
                skipped[why] = skipped.get(why, 0) + 1
                d += 1
                continue
            trades.append({
                "kode": c, "tgl_sinyal": f"{dates[d]:%Y-%m-%d}", "tgl_keluar": f"{dates[res['keluar_i']]:%Y-%m-%d}",
                "pasar": mkt.iloc[d - 1], "rs": int(rsc[d - 1]) if np.isfinite(rsc[d - 1]) else None,
                "kontraksi": len(v["kedalaman"]), "ketat": v["ketat"], "kering": v["kering"],
                "risiko_ok": lv["risiko_ok"], "sl_pct": lv["sl_pct"],
                **{k2: res[k2] for k2 in ("beli", "sl", "r_pct", "alasan", "net_r", "ret", "hari")},
            })
            d = res["keluar_i"] + 1             # satu posisi per saham pada satu waktu
    tr = pd.DataFrame(trades)
    if not tr.empty:
        tr = tr.sort_values("tgl_sinyal").reset_index(drop=True)
    return tr, skipped


def report(tr, skipped, test_dates, ihsg, label):
    eq_all, sum_all = equity(tr, test_dates)
    up = tr[tr["pasar"] == "uptrend"]
    eq_up, sum_up = equity(up, test_dates) if len(up) else (None, {})
    ih = ihsg.loc[test_dates]

    def grp(col, order=None):
        keys = order or sorted(tr[col].dropna().unique())
        return [{"kelompok": str(k), **stats(tr[tr[col] == k])} for k in keys if (tr[col] == k).any()]

    tr["tahun"] = tr["tgl_sinyal"].str[:4]
    tr["rs_kelompok"] = np.where(tr["rs"] >= 90, "RS 90+", "RS 70-89")
    tr["kualitas"] = np.where(tr["ketat"] & tr["kering"], "ketat + volume kering",
                              np.where(tr["ketat"] | tr["kering"], "salah satu", "tidak keduanya"))
    step = max(1, len(test_dates) // 260)
    return {
        "label": label,
        "ringkasan": {**stats(tr), **sum_all},
        "hanya_uptrend": {**stats(up), **sum_up},
        "dilewati": skipped,
        "per_pasar": grp("pasar", ["uptrend", "tertekan", "downtrend"]),
        "per_tahun": grp("tahun"),
        "per_rs": grp("rs_kelompok", ["RS 90+", "RS 70-89"]),
        "per_kualitas": grp("kualitas", ["ketat + volume kering", "salah satu", "tidak keduanya"]),
        "per_alasan_keluar": tr["alasan"].value_counts().to_dict(),
        "kurva": [{"t": f"{d:%Y-%m-%d}", "semua": round(float(eq_all.loc[d]), 4),
                   "uptrend": round(float(eq_up.loc[d]), 4) if eq_up is not None else None,
                   "ihsg": round(float(ih.loc[d] / ih.iloc[0]), 4)} for d in test_dates[::step]],
        "trade_terakhir": json.loads(tr.tail(60).iloc[::-1].drop(columns=["tahun", "rs_kelompok", "kualitas"])
                                     .to_json(orient="records")),
    }


if __name__ == "__main__":
    main()
