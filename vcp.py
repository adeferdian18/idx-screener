"""
Fase 2: Pola VCP, titik pivot, entry trigger, stop loss / target, dan status posisi.
Dipanggil oleh momentum.py untuk saham yang lolos (atau hampir lolos) Trend Template.

Aturan dari modul Momentum Trading Blueprint:
  - VCP: 2-6 kontraksi yang makin dangkal (mis. 25% -> 12% -> 5% -> 2%), volume mengering di ujung.
  - Pivot: puncak kontraksi terakhir (garis resistensi terkecil).
  - Entry trigger: harga tutup di atas pivot dengan volume >= 1,5x rata-rata 50 hari.
  - Jangan kejar: zona beli maksimal +5% dari pivot.
  - Stop loss di bawah low kontraksi terakhir, maksimal 7-8%. Struktur yang butuh SL lebih lebar = tidak ideal.
  - Target 2R dan 3R. Setelah TP1, stop naik ke titik impas.
  - Time stop (tambahan untuk momentum singkat): 7 hari bursa belum naik 1R -> keluar.
"""

import math

import numpy as np

LOOKBACK = 130        # panjang maksimal basis yang dicari (~6 bulan)
MIN_BASE = 10         # basis minimal 2 minggu
ZZ = 0.04             # ayunan minimal 4% untuk dihitung sebagai kontraksi
MAX_FIRST = 0.40      # kontraksi pertama terlalu dalam = bukan basis sehat
MAX_LAST = 0.10       # kontraksi terakhir harus ketat
TIGHT = 0.06
VOL_BREAKOUT = 1.5
DRYUP = 0.7           # rata-rata volume 5 hari terakhir basis / rata-rata 50 hari
BUY_ZONE = 0.05
MAX_SL = 0.08
MIN_SL = 0.03         # SL lebih rapat dari ini kena noise harian
TRACK = 10            # trigger dilacak sampai 10 hari bursa
ACTIVE = 5            # "entry baru" = trigger 1-5 hari lalu
TIME_STOP = 7


# ---------------------------------------------------------------- Fraksi harga BEI
def tick(p):
    if p < 200:
        return 1
    if p < 500:
        return 2
    if p < 2000:
        return 5
    if p < 5000:
        return 10
    return 25


def up(p):
    t = tick(p)
    return math.ceil(p / t - 1e-9) * t


def down(p):
    t = tick(p)
    return math.floor(p / t + 1e-9) * t


# ---------------------------------------------------------------- VCP
def zigzag(high, low, th=ZZ):
    """Titik ayunan bergantian H/L, dimulai dari puncak basis di indeks 0."""
    pts = [["H", 0, high[0]]]
    for i in range(1, len(high)):
        kind, _, v = pts[-1]
        if kind == "H":
            if high[i] >= v:
                pts[-1] = ["H", i, high[i]]
            elif low[i] <= v * (1 - th):
                pts.append(["L", i, low[i]])
        else:
            if low[i] <= v:
                pts[-1] = ["L", i, low[i]]
            elif high[i] >= v * (1 + th):
                pts.append(["H", i, high[i]])
    return pts


def find_vcp(h):
    """Cari VCP pada data `h` (DataFrame OHLCV, baris terakhir = hari terakhir basis).
    Return dict dengan `valid`, `alasan` (aturan yang gagal), pivot, low kontraksi terakhir, dll."""
    seg = h.tail(LOOKBACK)
    hi, lo, vol = seg["High"].to_numpy(float), seg["Low"].to_numpy(float), seg["Volume"].to_numpy(float)
    p0 = int(np.argmax(hi))
    base_len = len(seg) - p0
    if base_len < MIN_BASE:
        return {"valid": False, "alasan": ["belum ada basis (harga masih di puncak baru)"]}

    bh, bl = hi[p0:], lo[p0:]
    pts = zigzag(bh, bl)
    highs = [p for p in pts if p[0] == "H"]
    contractions = []
    for k, (_, i, v) in enumerate(highs):
        j = highs[k + 1][1] if k + 1 < len(highs) else len(bh)
        if j <= i + 1:
            continue
        lo_i = i + 1 + int(np.argmin(bl[i + 1:j]))
        contractions.append({"hi_i": i, "hi": v, "lo_i": lo_i, "lo": bl[lo_i], "depth": 1 - bl[lo_i] / v, "bars": j - i})
    # Sisi kanan basis: ayunan naik yang baru 1-2 hari dan belum terkoreksi adalah harga yang sedang
    # bergerak menuju pivot, bukan kontraksi baru. Pivot tetap puncak kontraksi sebelumnya.
    if len(contractions) > 1 and pts[-1][0] == "H" and contractions[-1]["bars"] < 3:
        contractions.pop()
    if not contractions:
        return {"valid": False, "alasan": ["belum ada kontraksi"]}
    # Urutan VCP dimulai dari koreksi terdalam (T1, penjual panik); ayunan kecil sebelumnya bukan bagian pola
    k0 = int(np.argmax([c["depth"] for c in contractions]))
    contractions = contractions[k0:]

    alasan = []
    last = contractions[-1]
    depths = [c["depth"] for c in contractions]
    n = len(contractions)
    if n < 2:
        alasan.append("kontraksi terakhir masih yang terdalam (VCP butuh 2-6 kontraksi menyusut)")
    if n > 6:
        alasan.append(f"{n} kontraksi, basis terlalu berantakan")
    if last["bars"] < 3:
        alasan.append("kontraksi terakhir baru 1-2 hari, pivot belum teruji")
    if depths[0] > MAX_FIRST:
        alasan.append(f"koreksi pertama {depths[0]:.0%} terlalu dalam (maks {MAX_FIRST:.0%})")
    if depths[-1] > MAX_LAST:
        alasan.append(f"kontraksi terakhir {depths[-1]:.0%} belum ketat (maks {MAX_LAST:.0%})")
    if n >= 2 and depths[-1] > depths[0] * 0.6:
        alasan.append("volatilitas belum menyusut cukup")
    if n >= 2 and depths[-1] > depths[-2] * 1.25 + 0.01:
        alasan.append("kontraksi terakhir melebar lagi")
    orderly = all(depths[k + 1] <= depths[k] * 1.15 + 0.005 for k in range(n - 1))

    v50 = float(np.mean(h["Volume"].to_numpy(float)[-50:]))
    dry = float(np.mean(vol[-5:]) / v50) if v50 > 0 else None

    idx = seg.index
    return {
        "valid": not alasan,
        "alasan": alasan,
        "pivot": float(last["hi"]),
        "tgl_pivot": f"{idx[p0 + last['hi_i']]:%Y-%m-%d}",
        "low_akhir": float(last["lo"]),
        "puncak_basis": float(bh[0]),
        "tgl_basis": f"{idx[p0]:%Y-%m-%d}",
        "basis_hari": base_len,
        "kedalaman": [round(float(d), 4) for d in depths],
        "rapi": bool(orderly),
        "ketat": bool(depths[-1] <= TIGHT),
        "dryup": round(dry, 3) if dry is not None else None,
        "kering": bool(dry is not None and dry <= DRYUP),
        "vol50": v50,
    }


# ---------------------------------------------------------------- Level & risiko
def levels(v):
    entry = up(v["pivot"])
    if entry <= v["pivot"]:
        entry += tick(entry)        # harus diperdagangkan DI ATAS pivot
    sl_struct = down(v["low_akhir"]) - tick(v["low_akhir"])
    sl_struct_pct = 1 - sl_struct / entry
    catatan = []
    sl = sl_struct
    if sl_struct_pct > MAX_SL:
        sl = down(entry * (1 - MAX_SL))
        catatan.append(f"SL struktur {sl_struct_pct:.1%} > {MAX_SL:.0%}; dipotong ke {MAX_SL:.0%}, risiko tidak ideal")
    elif sl_struct_pct < MIN_SL:
        sl = down(entry * (1 - MIN_SL))
    risk = entry - sl
    return {
        "entry": entry, "beli_maks": down(entry * (1 + BUY_ZONE)), "sl": sl,
        "sl_pct": round(1 - sl / entry, 4), "sl_struktur_pct": round(sl_struct_pct, 4),
        "tp1": down(entry + 2 * risk), "tp2": down(entry + 3 * risk),
        "risiko_ok": bool(sl_struct_pct <= MAX_SL), "catatan_risiko": catatan,
    }


# ---------------------------------------------------------------- Trigger & status
def simulate(h, d, lv):
    """Telusuri candle setelah hari trigger `d`. Kalau SL dan TP tersentuh di candle yang sama,
    anggap SL lebih dulu (konservatif). Setelah TP1, stop naik ke titik impas."""
    e, sl, tp1, tp2 = lv["entry"], lv["sl"], lv["tp1"], lv["tp2"]
    risk = e - sl
    hit = {"tp1": None, "tp2": None, "sl": None, "impas": None}
    stop = sl
    for i in range(d + 1, len(h)):
        hi, lo = float(h["High"].iloc[i]), float(h["Low"].iloc[i])
        day = f"{h.index[i]:%Y-%m-%d}"
        if lo <= stop:
            hit["impas" if hit["tp1"] else "sl"] = day
            break
        if hit["tp1"] is None and hi >= tp1:
            hit["tp1"] = day
            stop = e
        if hi >= tp2:
            hit["tp2"] = day
            break
    close = float(h["Close"].iloc[-1])
    days = len(h) - 1 - d
    max_close = float(h["Close"].iloc[d:].max())
    if hit["tp2"]:
        status = "kena_tp2"
    elif hit["impas"]:
        status = "tp1_impas"
    elif hit["sl"]:
        status = "sl_naik_lagi" if close > sl else "kena_sl"
    elif hit["tp1"]:
        status = "kena_tp1"
    elif days >= TIME_STOP and max_close < e + risk:
        status = "time_stop"
    elif days == 0:
        status = "entry_hari_ini"
    elif days <= ACTIVE:
        status = "entry_baru"
    else:
        status = "berjalan"
    return status, hit, days, round(float((close - e) / risk), 2) if risk > 0 else None


LABEL = {
    "entry_hari_ini": "Entry hari ini", "entry_baru": "Entry baru", "berjalan": "Berjalan",
    "kena_tp1": "Kena TP1 · stop di impas", "kena_tp2": "Kena TP2", "tp1_impas": "TP1 lalu keluar impas",
    "kena_sl": "Kena SL", "sl_naik_lagi": "Kena SL, naik lagi · watchlist lagi", "time_stop": "Time stop",
    "setup": "Setup · dekat pivot", "vcp": "VCP terbentuk", "volume_kurang": "Tembus pivot, volume kurang",
    "extended": "Extended · jangan kejar",
}
AKTIF = {"entry_hari_ini", "entry_baru", "berjalan", "kena_tp1", "sl_naik_lagi"}


def analyze(h):
    """Status entry untuk satu saham. Return None kalau tidak ada VCP/trigger yang relevan."""
    n = len(h)
    if n < 80:
        return None
    close, vol = h["Close"].to_numpy(float), h["Volume"].to_numpy(float)

    # 1) Trigger terbaru dalam TRACK hari: basis dinilai dengan data SEBELUM hari trigger
    for d in range(n - 1, n - 2 - TRACK, -1):
        v = find_vcp(h.iloc[:d])
        if not v["valid"]:
            continue
        vr = vol[d] / v["vol50"] if v["vol50"] > 0 else 0
        if close[d] > v["pivot"] and close[d - 1] <= v["pivot"] and vr >= VOL_BREAKOUT:
            lv = levels(v)
            status, hit, days, r_now = simulate(h, d, lv)
            if status in ("entry_hari_ini", "entry_baru", "berjalan") and close[-1] > lv["beli_maks"]:
                ext = True
            else:
                ext = False
            return {"status": status, "label": LABEL[status], "aktif": status in AKTIF, "extended": ext,
                    "tgl_trigger": f"{h.index[d]:%Y-%m-%d}", "hari_sejak": days, "vol_breakout": round(float(vr), 2),
                    "r_sekarang": r_now, "hit": hit, "vcp": _vcp_out(v), **lv}

    # 2) Belum trigger: nilai basis yang sedang berjalan (termasuk hari ini)
    v_prev = find_vcp(h.iloc[:-1])
    if v_prev["valid"] and close[-1] > v_prev["pivot"]:
        lv = levels(v_prev)
        st = "extended" if close[-1] > lv["beli_maks"] else "volume_kurang"
        return {"status": st, "label": LABEL[st], "aktif": False, "extended": st == "extended",
                "vol_breakout": round(float(vol[-1] / v_prev["vol50"]), 2) if v_prev["vol50"] > 0 else None,
                "vcp": _vcp_out(v_prev), **lv}
    v = find_vcp(h)
    if v.get("pivot") is None:
        return {"status": None, "label": None, "aktif": False, "vcp": _vcp_out(v)}
    lv = levels(v)
    if v["valid"]:
        st = "setup" if close[-1] >= v["pivot"] * (1 - BUY_ZONE) else "vcp"
        return {"status": st, "label": LABEL[st], "aktif": False, "jarak_pivot": round(float(close[-1] / lv["entry"] - 1), 4),
                "vcp": _vcp_out(v), **lv}
    # basis ada tapi belum memenuhi syarat VCP: simpan alasannya untuk briefing
    return {"status": None, "label": None, "aktif": False, "jarak_pivot": round(float(close[-1] / lv["entry"] - 1), 4),
            "vcp": _vcp_out(v), **lv}


def _vcp_out(v):
    keep = ("valid", "alasan", "pivot", "tgl_pivot", "low_akhir", "puncak_basis", "tgl_basis", "basis_hari",
            "kedalaman", "rapi", "ketat", "dryup", "kering", "vol50")
    return {k: v.get(k) for k in keep}
