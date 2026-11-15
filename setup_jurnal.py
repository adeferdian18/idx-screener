"""Jurnal otomatis Setup A+: setiap saham yang lolos Setup A+ dicatat, lalu dilacak tiap hari
sampai kena TP, kena SL, atau waktu habis (out), lengkap dengan alasan teknikal dan fundamental.

Aturan sama dengan backtest_sweep.py (Setup A+):
- Order buy-stop di harga entry, berlaku 5 hari bursa setelah sinyal. Tidak tersentuh -> "batal".
- Open hari itu di atas entry (gap) -> "batal (gap)", karena Setup A+ hanya mengambil breakout tanpa gap.
- Hari entry: hanya penutupan di bawah SL yang dihitung. Hari berikutnya: open <= SL -> keluar di open,
  low <= SL -> keluar di SL, high >= TP -> keluar di TP. SL & TP di candle yang sama dihitung SL.
- Lewat 20 hari bursa sejak entry -> "waktu habis", keluar di penutupan hari ke-20 (dianggap sudah out).

Dipanggil dari momentum.py; hasilnya docs/data/setup_jurnal.json.
"""
import json
from pathlib import Path

import numpy as np

SITE = Path(__file__).parent / "docs" / "data"
FILE = SITE / "setup_jurnal.json"
ORDER_DAYS = 5
MAX_HOLD = 20
BUY_FEE, SELL_FEE, SLIP = 0.0015, 0.0025, 0.001


def _n(x):
    return f"{x:.1f}".replace(".", ",")


def _pct(x):
    return f"{x:+.1%}".replace(".", ",")


def alasan(keluar, hari, mfe_r, mae_r, vol_x, ihsg_chg, rs=None, fund=None, katalis=None):
    """Alasan yang bisa dibaca manusia untuk hasil sebuah trade. Return (teknikal[], fundamental[])."""
    tek = []
    if keluar == "TP":
        tek.append(f"Harga mencapai TP dalam {hari} hari bursa")
        if vol_x is not None:
            tek.append(f"Breakout didukung volume {_n(vol_x)}× rata-rata 50 hari" if vol_x >= 1.5
                       else f"Volume breakout hanya {_n(vol_x)}× rata-rata, tetapi harga tetap melanjutkan")
        if ihsg_chg is not None:
            tek.append(f"IHSG {_pct(ihsg_chg)} selama trade, " + ("pasar ikut mendukung" if ihsg_chg >= 0 else "saham tetap kuat walau pasar turun"))
        if mae_r is not None and mae_r > -0.5:
            tek.append("Harga hampir tidak pernah mundur ke arah SL (kekuatan tinggi)")
    elif keluar == "SL":
        tek.append(f"Harga turun ke SL pada hari ke-{hari}" + (" (breakout gagal di hari yang sama)" if hari == 0 else ""))
        if vol_x is not None and vol_x < 1.5:
            tek.append(f"Volume breakout lemah ({_n(vol_x)}× rata-rata 50 hari): kurang dukungan pembeli besar")
        if ihsg_chg is not None and ihsg_chg < -0.01:
            tek.append(f"IHSG {_pct(ihsg_chg)} selama trade: tekanan pasar menyeret saham")
        if mfe_r is not None:
            tek.append(f"Sempat naik {_n(mfe_r)}R sebelum berbalik" if mfe_r >= 0.5 else "Tidak pernah naik berarti setelah entry (breakout palsu)")
    elif keluar == "waktu":
        tek.append(f"{hari} hari bursa lewat tanpa menyentuh TP atau SL, dianggap out di penutupan")
        if mfe_r is not None:
            tek.append(f"Kenaikan tertinggi {_n(mfe_r)}R, belum cukup ke TP")
        if ihsg_chg is not None:
            tek.append(f"IHSG {_pct(ihsg_chg)} selama trade")
    if rs is not None:
        tek.append(f"RS Rating saat sinyal {int(rs)}")

    fun = []
    if fund:
        st = fund.get("status")
        if st and st != "data kurang":
            bag = []
            if fund.get("laba_yoy") is not None:
                bag.append(f"laba {_pct(fund['laba_yoy'])} YoY")
            if fund.get("penjualan_yoy") is not None:
                bag.append(f"penjualan {_pct(fund['penjualan_yoy'])} YoY")
            fun.append(f"Fundamental {st}" + (f" ({', '.join(bag)}, kuartal {fund.get('kuartal')})" if bag else ""))
        else:
            fun.append("Data laporan kuartalan tidak lengkap di Yahoo")
    for k in (katalis or [])[:2]:
        judul = k.get("judul") or k.get("title") if isinstance(k, dict) else str(k)
        if judul:
            fun.append(f"Katalis: {judul}")
    return tek, fun


def simulate(h, ihsg, t):
    """Lacak satu trade di DataFrame OHLCV `h` dari sinyal `t` (dict). Return field yang diperbarui."""
    idx = h.index
    tgl = np.datetime64(t["tgl_sinyal"])
    after = np.where(idx.values > tgl)[0]
    O, H, L, C = (h[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    V = h["Volume"].to_numpy(float)
    entry, sl, tp = t["entry"], t["sl"], t["tp"]
    out = {"status": "menunggu", "tgl_beli": None, "beli": None, "tgl_keluar": None, "harga_keluar": None,
           "keluar": None, "hari": None, "net_r": None, "ret": None, "mfe_r": None, "mae_r": None,
           "vol_x": None, "ihsg_chg": None, "sisa_hari": None, "terakhir": None}
    d = None
    for n, i in enumerate(after[:ORDER_DAYS]):
        if O[i] > entry:
            out.update(status="batal", keluar="gap", tgl_keluar=f"{idx[i]:%Y-%m-%d}")
            return out
        if H[i] >= entry:
            d = i
            break
    if d is None:
        if len(after) >= ORDER_DAYS:
            out.update(status="batal", keluar="tidak breakout", tgl_keluar=f"{idx[after[ORDER_DAYS - 1]]:%Y-%m-%d}")
        else:
            out["sisa_hari"] = int(ORDER_DAYS - len(after))
        return out

    buy = entry * (1 + SLIP)
    cost = buy * (1 + BUY_FEE)
    r = buy - sl
    v50 = float(np.nanmean(V[max(0, d - 50):d])) if d > 0 else np.nan
    out.update(status="berjalan", tgl_beli=f"{idx[d]:%Y-%m-%d}", beli=round(buy, 1),
               vol_x=round(float(V[d] / v50), 2) if v50 and np.isfinite(v50) else None)
    px = why = None
    last = d
    for i in range(d, len(C)):
        last = i
        if i == d:
            if C[i] <= sl:
                px, why = C[i], "SL"
                break
            continue
        if O[i] <= sl:
            px, why = O[i], "SL"
            break
        if L[i] <= sl:
            px, why = sl, "SL"
            break
        if H[i] >= tp:
            px, why = max(tp, O[i]), "TP"
            break
        if i - d >= MAX_HOLD:
            px, why = C[i], "waktu"
            break
    seg_h, seg_l = H[d:last + 1], L[d:last + 1]
    out["mfe_r"] = round(float((np.nanmax(seg_h) - buy) / r), 2)
    out["mae_r"] = round(float((np.nanmin(seg_l) - buy) / r), 2)
    ih = ihsg.reindex(idx).ffill().to_numpy(float)
    base = ih[d - 1] if d > 0 else ih[d]
    out["ihsg_chg"] = round(float(ih[last] / base - 1), 4) if np.isfinite(base) and base else None
    out["hari"] = int(last - d)
    if why is None:
        out["sisa_hari"] = int(MAX_HOLD - (last - d))
        out["terakhir"] = round(float(C[last]), 1)
        out["ret"] = round(float(C[last] * (1 - SLIP) * (1 - SELL_FEE) / cost - 1), 4)
        return out
    proceeds = px * (1 - SLIP) * (1 - SELL_FEE)
    out.update(status="selesai", keluar=why, tgl_keluar=f"{idx[last]:%Y-%m-%d}", harga_keluar=round(float(px), 1),
               net_r=round(float((proceeds - cost) / r), 3), ret=round(float(proceeds / cost - 1), 4))
    return out


def update(out_rows, frames, ihsg, market):
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"trades": []}
    trades = data["trades"]
    as_of = f"{ihsg.index[-1]:%Y-%m-%d}"
    aktif = {t["kode"] for t in trades if t["status"] in ("menunggu", "berjalan")}
    for z in out_rows:
        sa = z.get("setup_a") or {}
        if not sa.get("lolos") or z["kode"] in aktif:
            continue
        if any(t["kode"] == z["kode"] and t["tgl_sinyal"] == as_of for t in trades):
            continue
        v = (z.get("entry") or {}).get("vcp") or {}
        trades.append({
            "kode": z["kode"], "nama": z.get("nama"), "tgl_sinyal": as_of,
            "entry": sa["entry"], "sl": sa["sl"], "tp": sa["tp"], "sl_pct": sa.get("sl_pct"),
            "rs": z.get("rs_rating"), "pasar": market.get("status"), "kontraksi": v.get("kedalaman"),
            "fund": z.get("hgm"), "katalis": z.get("katalis") or [], "status": "menunggu",
        })
    for t in trades:
        if t["status"] in ("selesai", "batal"):
            continue
        h = frames.get(t["kode"])
        if h is None:
            continue
        t.update(simulate(h, ihsg, t))
        if t["status"] == "selesai":
            t["alasan_teknikal"], t["alasan_fundamental"] = alasan(
                t["keluar"], t["hari"], t["mfe_r"], t["mae_r"], t["vol_x"], t["ihsg_chg"],
                t.get("rs"), t.get("fund"), t.get("katalis"))
    done = [t for t in trades if t["status"] == "selesai"]
    data = {
        "updated": as_of,
        "aturan": {"order_hari": ORDER_DAYS, "maks_hari": MAX_HOLD, "biaya": {"beli": BUY_FEE, "jual": SELL_FEE, "slip": SLIP}},
        "ringkas": {
            "sinyal": len(trades),
            "selesai": len(done),
            "kena_tp": sum(t["keluar"] == "TP" for t in done),
            "kena_sl": sum(t["keluar"] == "SL" for t in done),
            "waktu_habis": sum(t["keluar"] == "waktu" for t in done),
            "berjalan": sum(t["status"] == "berjalan" for t in trades),
            "menunggu": sum(t["status"] == "menunggu" for t in trades),
            "batal": sum(t["status"] == "batal" for t in trades),
            "rata_r": round(float(np.mean([t["net_r"] for t in done])), 3) if done else None,
        },
        "trades": sorted(trades, key=lambda t: t["tgl_sinyal"], reverse=True),
    }
    FILE.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"  Jurnal Setup A+: {data['ringkas']}")
    return data
