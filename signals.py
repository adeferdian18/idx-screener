"""
Matriks sinyal lintas saham (semua saham BEI sekaligus) yang dipakai momentum.py dan backtest.py.

  - rs_rating_matrix: RS Rating harian (persentil 1-99) untuk setiap saham, setiap hari.
  - trend_template_matrix: 8 poin Trend Template per hari.
  - reversal_matrix: setup kedua, "Pembalikan pemimpin RS" (RS leader reversal).

Pembalikan pemimpin RS (dipelajari dari setup DMAS 19 Okt 2026 di screener referensi):
saat pasar koreksi, saham yang RS Line-nya justru mencetak high 50 hari padahal harganya sedang
terkoreksi adalah pemimpin berikutnya (O'Neil/Minervini: saham yang paling tahan saat koreksi memimpin
saat pasar berbalik). Syarat di hari trigger:
  1. RS Line (harga / IHSG) mencetak high 50 hari                     -> institusi masih menahan/akumulasi
  2. Harga >= 8% di bawah high 20 hari                                -> sedang terkoreksi (RS "memimpin" harga)
  3. Pernah lolos Trend Template dalam 10 hari terakhir, harga > MA150 -> Stage 2 belum rusak
  4. RS Rating >= 80
  5. Candle bullish: tutup > open, tutup > tutup kemarin, tutup di separuh atas rentang hari itu
  6. Volume >= rata-rata 50 hari, saham likuid
Level dari candle trigger: entry = harga tutup, SL = 1 tick di bawah low candle (maks 8%), TP 2R & 3R.
"""

import numpy as np
import pandas as pd

import vcp

REV_PULLBACK = 0.08
REV_RS_MIN = 80
REV_TT_LOOKBACK = 10
REV_MAX_SL = 0.08      # bisa dilebarkan; ukuran posisi otomatis mengecil (modul hal. 11)


def matrices(hist, index):
    get = lambda k: pd.DataFrame({c: h[k] for c, h in hist.items()}).reindex(index)  # noqa: E731
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


def tradable_matrix(C, V, min_value):
    return ((C * V).rolling(20).mean() >= min_value) & ((V == 0).rolling(20).sum() < 5)


def reversal_matrix(O, H, L, C, V, ihsg, rs, tt, tradable):
    rsl = C.div(ihsg, axis=0)
    rs_new = rsl >= rsl.rolling(50, min_periods=40).max() * 0.999
    pulled = C <= H.rolling(20).max() * (1 - REV_PULLBACK)
    rng = (H - L).replace(0, np.nan)
    bull = (C > O) & (C > C.shift(1)) & ((C - L) >= 0.5 * rng)
    tt_recent = tt.astype(float).rolling(REV_TT_LOOKBACK, min_periods=1).max() > 0
    stage2 = C > C.rolling(150).mean()
    vol_ok = V >= V.rolling(50).mean().shift(1)
    return rs_new & pulled & bull & tt_recent & stage2 & (rs >= REV_RS_MIN) & vol_ok & tradable


def reversal_levels(low, close):
    entry = vcp.down(float(close))
    sl = vcp.down(low) - vcp.tick(low)
    risk = 1 - sl / entry
    ok = risk <= REV_MAX_SL
    if risk < vcp.MIN_SL:
        sl = vcp.down(entry * (1 - vcp.MIN_SL))
    r = entry - sl
    return {"entry": entry, "beli_maks": vcp.down(entry * 1.03), "sl": sl, "sl_pct": round(1 - sl / entry, 4),
            "sl_struktur_pct": round(risk, 4), "tp1": vcp.down(entry + 2 * r), "tp2": vcp.down(entry + 3 * r),
            "risiko_ok": bool(ok),
            "catatan_risiko": [] if ok else [f"SL di bawah low candle trigger {risk:.1%} > {REV_MAX_SL:.0%}: risiko tidak ideal"]}


def reversal_entry(h, trig):
    """Status setup pembalikan RS terbaru (<= 10 hari bursa) untuk satu saham. `trig`: Series boolean per tanggal."""
    trig = trig.reindex(h.index).fillna(False).to_numpy(bool)
    n = len(h)
    for d in range(n - 1, max(n - 2 - vcp.TRACK, 0), -1):
        if not trig[d]:
            continue
        lo, cl = float(h["Low"].iloc[d]), float(h["Close"].iloc[d])
        lv = reversal_levels(lo, cl)
        status, hit, days, r_now = vcp.simulate(h, d, lv)
        hi20 = float(h["High"].iloc[max(0, d - 19):d + 1].max())
        return {"setup": "reversal", "status": status, "label": vcp.LABEL[status] + " · pembalikan RS",
                "aktif": status in vcp.AKTIF, "extended": status in ("entry_hari_ini", "entry_baru", "berjalan")
                and float(h["Close"].iloc[-1]) > lv["beli_maks"] * 1.02,
                "tgl_trigger": f"{h.index[d]:%Y-%m-%d}", "hari_sejak": days, "r_sekarang": r_now, "hit": hit,
                "vol_breakout": None, "pola": {"koreksi": round(cl / hi20 - 1, 4), "low_trigger": lo}, "vcp": None, **lv}
    return None
