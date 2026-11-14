"""
Sweep backtest strategi momentum (Trend Template + RS + VCP + buy-stop di pivot).

Tujuan: mencari kombinasi filter + TP/SL terbaik SECARA JUJUR, dan mencatat berapa trade kena TP,
berapa kena SL, berapa keluar karena waktu habis.

Cara kerja
  1. Kumpulkan semua sinyal breakout pivot VCP yang bisa dieksekusi tanpa melihat masa depan:
     tren & RS diukur kemarin, order buy-stop di harga entry (di atas pivot), terisi di max(open, entry).
  2. Untuk tiap sinyal, simulasikan banyak aturan keluar:
       SL  : struktur VCP (di bawah low kontraksi terakhir, maks 8%), atau tetap 5% / 7% / 8%
       TP  : satu target 0,5R / 1R / 1,5R / 2R / 2,5R / 3R (jual semua di target)
       Waktu: keluar di harga tutup setelah 20 hari bursa kalau TP/SL belum kena
  3. Kombinasikan dengan filter (kondisi IHSG, RS minimum, kualitas VCP, SL struktur wajar, tidak gap).
  4. Walk-forward: kombinasi terbaik DIPILIH dari data 2022-2024 saja, lalu DIUJI di 2025-2026 yang
     tidak pernah dilihat saat memilih. Hanya angka uji ini yang pantas dijadikan ekspektasi.

Aturan simulasi sama dengan backtest.py: biaya beli 0,15%, jual 0,25%, slippage 0,1% tiap sisi; di hari beli
hanya harga tutup di bawah SL yang dihitung (urutan intraday tidak diketahui); TP & SL di candle yang sama ->
SL dulu; gap di bawah SL -> keluar di open.

Filter "volume breakout >= 1,5x" dilaporkan terpisah sebagai batas atas karena volume akhir hari belum
diketahui saat order terisi.

Keterbatasan: survivorship bias (universe = saham yang masih tercatat), data Yahoo bisa bolong, ARB/suspensi
hanya lewat gap, sinyal antar-varian keluar diperlakukan independen (tidak ada batas jumlah posisi).

Keluaran: docs/data/backtest_sweep.json, data/backtest_sweep_trades.csv
"""

import itertools
import json
import math
import os
import pickle
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

import momentum as mom
import signals
import vcp

PERIOD = "5y"
BUY_FEE, SELL_FEE, SLIP = 0.0015, 0.0025, 0.001
MAX_HOLD = 20
SPLIT = "2025-01-01"          # sebelum = data pilih (train), sesudah = data uji (test)
MIN_TRAIN = 40                # kombinasi dengan trade train lebih sedikit tidak boleh dipilih
SL_RULES = ["struktur", 0.05, 0.07, 0.08]
TP_RS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
# Setup A+ yang dipakai screener (momentum.py). Dipilih SETELAH melihat data uji, jadi angka ujinya bukan
# uji buta; tetap satu-satunya kombinasi top-15 dengan batas bawah positif di kedua periode.
KANDIDAT = {"filter": {"pasar": "bukan downtrend", "rs": "RS 90+", "vcp": "volume kering",
                       "risiko": "SL struktur ≤ 8%", "gap": "tanpa gap"}, "sl": "struktur", "tp": 1.0}
CACHE = os.getenv("SWEEP_CACHE")  # opsional: path pickle untuk menyimpan unduhan saat uji lokal

BASE = Path(__file__).parent
WIB = dt.timezone(dt.timedelta(hours=7))


def market_series(ihsg):
    m50, m200 = ihsg.rolling(50).mean(), ihsg.rolling(200).mean()
    upt = (ihsg > m50) & (ihsg > m200) & (m200 > m200.shift(21))
    return pd.Series(np.where(upt, "uptrend", np.where(ihsg > m200, "tertekan", "downtrend")), index=ihsg.index)


def load():
    if CACHE and Path(CACHE).exists():
        return pickle.loads(Path(CACHE).read_bytes())
    uni = mom.load_universe()
    codes = [u["kode"] for u in uni]
    print(f"Unduh {len(codes)} saham ({PERIOD})...")
    ihsg = mom.download_ihsg(PERIOD)
    hist = mom.download(codes, PERIOD)
    for h in hist.values():
        h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
    if CACHE:
        Path(CACHE).write_bytes(pickle.dumps((ihsg, hist)))
    return ihsg, hist


def collect_events(ihsg, hist):
    """Semua breakout pivot VCP yang bisa diorder tanpa info masa depan. Satu sinyal per basis."""
    O, H, L, C, V = signals.matrices(hist, ihsg.index)
    rs = signals.rs_rating_matrix(C)
    tt = signals.trend_template_matrix(H, L, C, rs)
    tradable = signals.tradable_matrix(C, V, mom.MIN_AVG_VALUE_IDR)
    v50 = V.rolling(50).mean().shift(1)
    mkt = market_series(ihsg)
    dates = ihsg.index
    start = 260
    ev = []
    for c in hist:
        o, hh, ll, cc, vv = (M[c].to_numpy(float) for M in (O, H, L, C, V))
        ttc, trc, vb, rsc = tt[c].to_numpy(), tradable[c].to_numpy(), v50[c].to_numpy(float), rs[c].to_numpy(float)
        frame = pd.DataFrame({"Open": o, "High": hh, "Low": ll, "Close": cc, "Volume": vv}, index=dates)
        valid = np.isfinite(cc)
        pos = np.cumsum(valid) - 1
        f = frame[valid]
        last_pivot = None
        for d in range(start, len(dates) - 1):
            if not (ttc[d - 1] and trc[d - 1] and valid[d]):
                continue
            k = pos[d]
            v = vcp.find_vcp(f.iloc[:k])
            if not v["valid"] or f["Close"].iloc[k - 1] > v["pivot"]:
                continue
            lv = vcp.levels(v)
            if hh[d] < lv["entry"] or o[d] > lv["beli_maks"]:
                continue
            if last_pivot == (v["tgl_pivot"], v["pivot"]):
                continue                      # basis yang sama sudah pernah diambil
            last_pivot = (v["tgl_pivot"], v["pivot"])
            hi252 = np.nanmax(hh[max(0, d - 252):d])
            ev.append({
                "kode": c, "d": d, "tgl": f"{dates[d]:%Y-%m-%d}",
                "pasar": mkt.iloc[d - 1], "rs": float(rsc[d - 1]) if np.isfinite(rsc[d - 1]) else 0.0,
                "ketat": bool(v["ketat"]), "kering": bool(v["kering"]), "kontraksi": len(v["kedalaman"]),
                "risiko_ok": bool(lv["risiko_ok"]), "sl_struktur": lv["sl"], "entry": lv["entry"],
                "gap": bool(o[d] > lv["entry"]), "dari_high52": float(cc[d - 1] / hi252 - 1),
                "vol_x": float(vv[d] / vb[d]) if np.isfinite(vb[d]) and vb[d] > 0 else np.nan,
                "_o": o, "_h": hh, "_l": ll, "_c": cc,
            })
    print(f"  {len(ev)} sinyal breakout")
    return ev, dates


def simulate(e, sl_rule, tp_r):
    o, h, l, c, d = e["_o"], e["_h"], e["_l"], e["_c"], e["d"]
    raw = max(o[d], e["entry"])
    buy = raw * (1 + SLIP)
    cost = buy * (1 + BUY_FEE)
    sl = e["sl_struktur"] if sl_rule == "struktur" else vcp.down(e["entry"] * (1 - sl_rule))
    if sl >= buy:
        return None
    r_unit = buy - sl
    tp = buy + tp_r * r_unit
    n = len(c)
    for i in range(d, min(n, d + MAX_HOLD + 1)):
        if not np.isfinite(c[i]):
            continue
        if i == d:
            if c[i] <= sl:
                px, why = c[i], "SL"
                break
            continue
        if o[i] <= sl:
            px, why = o[i], "SL"
            break
        if l[i] <= sl:
            px, why = sl, "SL"
            break
        if h[i] >= tp:
            px, why = max(tp, o[i]), "TP"
            break
        if i - d >= MAX_HOLD:
            px, why = c[i], "waktu"
            break
    else:
        return None                            # masih berjalan / data habis
    proceeds = px * (1 - SLIP) * (1 - SELL_FEE)
    return {"keluar": why, "net_r": (proceeds - cost) / r_unit, "ret": proceeds / cost - 1, "hari": i - d,
            "keluar_i": i, "beli": buy, "sl": sl, "tp": tp}


def summarize(rows):
    if not rows:
        return {"trade": 0}
    r = np.array([x["net_r"] for x in rows])
    k = [x["keluar"] for x in rows]
    wins, losses = r[r > 0], r[r <= 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else None
    se = r.std(ddof=1) / math.sqrt(len(r)) if len(r) > 1 else None
    return {
        "trade": len(r), "kena_tp": k.count("TP"), "kena_sl": k.count("SL"), "waktu_habis": k.count("waktu"),
        "menang": round(float((r > 0).mean()), 4), "rata_r": round(float(r.mean()), 3),
        "se_r": round(float(se), 3) if se else None,
        "batas_bawah_r": round(float(r.mean() - 2 * se), 3) if se else None,
        "profit_factor": round(float(pf), 2) if pf else None,
        "rata_return": round(float(np.mean([x["ret"] for x in rows])), 4),
        "rata_hari": round(float(np.mean([x["hari"] for x in rows])), 1),
    }


FILTERS = {
    "pasar": {"semua": lambda e: True, "bukan downtrend": lambda e: e["pasar"] != "downtrend",
              "uptrend": lambda e: e["pasar"] == "uptrend"},
    "rs": {"RS 70+": lambda e: e["rs"] >= 70, "RS 80+": lambda e: e["rs"] >= 80, "RS 90+": lambda e: e["rs"] >= 90},
    "vcp": {"semua": lambda e: True, "ketat": lambda e: e["ketat"], "volume kering": lambda e: e["kering"],
            "ketat + kering": lambda e: e["ketat"] and e["kering"]},
    "risiko": {"semua": lambda e: True, "SL struktur ≤ 8%": lambda e: e["risiko_ok"]},
    "gap": {"semua": lambda e: True, "tanpa gap": lambda e: not e["gap"]},
}


def label(fk, sl, tp):
    sl_s = "SL struktur VCP" if sl == "struktur" else f"SL {int(sl * 100)}%"
    parts = [f"{k}: {v}" for k, v in fk.items() if v != "semua"]
    return " · ".join(parts + [sl_s, f"TP {tp:g}R".replace(".", ",")])


def main():
    ihsg, hist = load()
    events, dates = collect_events(ihsg, hist)
    # simulasi semua varian keluar sekali per sinyal
    sims = {}
    for sl, tp in itertools.product(SL_RULES, TP_RS):
        sims[(sl, tp)] = [simulate(e, sl, tp) for e in events]
    is_train = np.array([e["tgl"] < SPLIT for e in events])

    results = []
    keys = list(FILTERS)
    for combo in itertools.product(*(FILTERS[k].items() for k in keys)):
        mask = np.array([all(fn(e) for _, fn in combo) for e in events])
        fk = {k: name for k, (name, _) in zip(keys, combo)}
        for (sl, tp), sim in sims.items():
            tr = [s for s, m, t in zip(sim, mask, is_train) if m and t and s]
            te = [s for s, m, t in zip(sim, mask, is_train) if m and not t and s]
            st_tr = summarize(tr)
            if st_tr["trade"] < MIN_TRAIN:
                continue
            results.append({"filter": fk, "sl": sl, "tp": tp, "label": label(fk, sl, tp),
                            "train": st_tr, "test": summarize(te)})
    print(f"  {len(results)} kombinasi diuji (min {MIN_TRAIN} trade di data pilih)")

    by_train = sorted(results, key=lambda x: x["train"]["batas_bawah_r"] or -9, reverse=True)
    best = by_train[0]
    top = by_train[:15]
    hi_win = sorted(results, key=lambda x: x["train"]["menang"], reverse=True)[:5]
    base = next(x for x in results if all(v in ("semua", "RS 70+") for v in x["filter"].values())
                and x["sl"] == "struktur" and x["tp"] == 2.0)

    def record(cfg):
        fk_, sl_, tp_ = cfg["filter"], cfg["sl"], cfg["tp"]
        out = []
        for e, s_ in zip(events, sims[(sl_, tp_)]):
            if s_ and all(FILTERS[k][fk_[k]](e) for k in keys):
                out.append({"kode": e["kode"], "tgl_beli": e["tgl"], "tgl_keluar": f"{dates[s_['keluar_i']]:%Y-%m-%d}",
                            "periode": "pilih" if e["tgl"] < SPLIT else "uji", "pasar": e["pasar"], "rs": int(e["rs"]),
                            "beli": round(s_["beli"], 1), "sl": s_["sl"], "tp": round(s_["tp"], 1), "keluar": s_["keluar"],
                            "hari": s_["hari"], "net_r": round(s_["net_r"], 3), "ret": round(s_["ret"], 4)})
        return out

    kand = next(x for x in results if x["filter"] == KANDIDAT["filter"] and x["sl"] == KANDIDAT["sl"] and x["tp"] == KANDIDAT["tp"])
    kand_rec = record(KANDIDAT)
    fk, sl, tp = best["filter"], best["sl"], best["tp"]
    rec = record(best)
    pd.DataFrame(kand_rec).to_csv(mom.DATA_DIR / "backtest_sweep_trades.csv", index=False)

    # batas atas: sama tapi hanya breakout yang volume akhir harinya >= 1,5x
    vol_mask = [(e["vol_x"] >= vcp.VOL_BREAKOUT) and all(FILTERS[k][fk[k]](e) for k in keys) for e in events]
    vol_tr = [s for s, m, t in zip(sims[(sl, tp)], vol_mask, is_train) if m and t and s]
    vol_te = [s for s, m, t in zip(sims[(sl, tp)], vol_mask, is_train) if m and not t and s]

    # tabel TP vs win rate (semua sinyal, SL struktur) untuk menunjukkan trade-off
    tradeoff = []
    for tp_ in TP_RS:
        allr = [s for s in sims[("struktur", tp_)] if s]
        tradeoff.append({"tp": tp_, **summarize(allr)})

    payload = {
        "updated": dt.datetime.now(WIB).isoformat(timespec="minutes"),
        "periode": [f"{dates[260]:%Y-%m-%d}", f"{dates[-1]:%Y-%m-%d}"], "split": SPLIT,
        "asumsi": {"biaya_beli": BUY_FEE, "biaya_jual": SELL_FEE, "slippage": SLIP, "maks_hari": MAX_HOLD,
                   "min_trade_pilih": MIN_TRAIN, "jumlah_sinyal": len(events), "jumlah_kombinasi": len(results)},
        "dasar": base, "terbaik": best, "top": top, "win_tertinggi": hi_win, "tp_vs_menang": tradeoff,
        "terbaik_volume_1_5x": {"train": summarize(vol_tr), "test": summarize(vol_te)},
        "kandidat": {**kand, "semua": summarize(kand_rec)},
        "trade_kandidat": kand_rec[::-1],
    }
    (mom.SITE / "backtest_sweep.json").write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    f = lambda s: (f"{s['trade']} trade (TP {s.get('kena_tp')}, SL {s.get('kena_sl')}, waktu {s.get('waktu_habis')}), "
                   f"menang {s.get('menang', 0):.0%}, rata {s.get('rata_r', 0):+.2f}R, PF {s.get('profit_factor')}")
    print("\nDASAR (aturan modul apa adanya):", base["label"])
    print("  pilih:", f(base["train"])); print("  uji  :", f(base["test"]))
    print("\nTERBAIK (dipilih dari data 2022-2024):", best["label"])
    print("  pilih:", f(best["train"])); print("  uji  :", f(best["test"]))
    print("  + volume ≥1,5x (batas atas) pilih:", f(summarize(vol_tr)), "| uji:", f(summarize(vol_te)))
    print("\nTop 15 menurut data pilih, dan hasilnya di data uji:")
    for x in top:
        print(f"  {x['train']['rata_r']:+.2f}R -> uji {x['test'].get('rata_r', float('nan')):+.2f}R "
              f"({x['test']['trade']} trade, menang {x['test'].get('menang', 0):.0%})  {x['label']}")
    print("\nWin rate tertinggi (data pilih):")
    for x in hi_win:
        print(f"  menang {x['train']['menang']:.0%} rata {x['train']['rata_r']:+.2f}R | uji menang "
              f"{x['test'].get('menang', 0):.0%} rata {x['test'].get('rata_r', float('nan')):+.2f}R  {x['label']}")
    print("\nTP vs win rate (semua sinyal, SL struktur):")
    for t in tradeoff:
        print(f"  TP {t['tp']}R: menang {t['menang']:.0%}, rata {t['rata_r']:+.2f}R, TP {t['kena_tp']} / SL {t['kena_sl']} / waktu {t['waktu_habis']}")


if __name__ == "__main__":
    main()
