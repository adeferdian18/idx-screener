"""
Backtest setup "Saham kuat yang sedang pullback" (pullback.py, lihat spesifikasi_pullback.md)
============================================================================================
Memakai fungsi pullback.py apa adanya (indikator, Ranking 3 Bulan lintas saham, mesin keadaan watchlist ->
jendela 5 candle -> entry trigger) lalu mensimulasikan SETIAP entry trigger di seluruh universe ±2 tahun data
(efektif ±1,5 tahun, karena Skor Momentum butuh ±6 bulan riwayat).

Eksekusi (tanpa look-ahead):
  - ATR      : beli di harga TUTUP candle trigger (trigger baru pasti saat candle tutup; praktiknya pre-closing).
               SL = entry - 1,5 ATR(5) (bulat ke bawah), TP = entry + 3 ATR (bulat ke atas). Risiko mulai besok.
  - N-candle : order beli bersyarat di high tertinggi 2 candle; terisi hanya bila high candle BERIKUTNYA menembus
               entry (harga isi = max(open, entry)), paling lama N_FILL candle, selain itu batal.
               SL = low terendah 2 candle, TP = entry + 2R.
  - SL tetap : keluar di SL atau TP. Gap open di bawah SL -> keluar di open (lebih buruk), gap di atas TP -> di open.
               SL dan TP tersentuh di candle yang sama -> anggap SL. Hari terisi (N-candle) langsung kena SL -> SL.
  - Trailing : stop awal SL, naik mengikuti high tertinggi SETELAH entry dikurangi risiko awal (bulat ke bawah),
               tidak pernah turun, tanpa TP; kenaikan stop dari high hari ini berlaku mulai besok.
  - Semua trigger dihitung (posisi boleh tumpang tindih, sama seperti situs yang menghitung tiap trigger).
    Posisi yang masih terbuka di akhir data TIDAK ikut statistik (dilaporkan jumlahnya).
  - Volatilitas P3 dikelompokkan pada candle trigger (<5% juga memuat sedikit trigger dengan P3 < 3 hari itu,
    karena syarat P3 berlaku di hari setup, bukan hari trigger).
  - Biaya: beli 0,15%, jual 0,25% (termasuk PPh final 0,1%), tanpa slippage tambahan; juga dihitung tanpa biaya.
  - R = (hasil jual bersih - modal beli bersih) / (harga isi - SL) per lembar.

Keterbatasan: universe = saham yang MASIH tercatat sekarang (survivorship bias; saham yang delisting/suspensi
lama tidak ada), data harian Yahoo (bisa bolong, tidak disesuaikan dividen sehingga ex-date tampak seperti
penurunan harga), ARB/ARA dan antrean tidak dimodelkan (order di SL dianggap pasti terisi), label Syariah memakai
daftar SAAT INI. Hasil masa lalu tidak menjamin hasil ke depan.

Pemakaian:
  python backtest_pullback.py                      unduh 2 tahun data Yahoo
  python backtest_pullback.py --cache raw.pkl      pakai cache pickle {"hist": {kode: df}, "ihsg": df/Series}
  python backtest_pullback.py --sampai 2026-10-21  abaikan data setelah tanggal ini
Hasil: docs/data/backtest_pullback.json + ringkasan di layar.
"""

import json
import math
import sys
import datetime as dt
import pickle

import numpy as np
import pandas as pd

import pullback as pb
import vcp

PERIOD = "2y"
BUY_FEE, SELL_FEE = 0.0015, 0.0025
N_FILL = 5                      # N-candle: order beli bersyarat berlaku maks 5 candle setelah trigger
OUT = pb.SITE / "backtest_pullback.json"
SITE_CLAIM = {
    "trigger_mei_okt_2026": 492,
    "catatan": "Situs referensi: ±492 trigger Mei–Okt 2026 dengan SL tetap, rata-rata sekitar impas; volatilitas 3–7% "
               "paling baik, >10% paling buruk. Satu tahun: ATR trailing -0,14R vs tetap -0,02R; N-candle trailing "
               "-0,09R vs tetap -0,11R per transaksi.",
    "atr_tetap_r": -0.02, "atr_trailing_r": -0.14, "n_tetap_r": -0.11, "n_trailing_r": -0.09,
}
COMBOS = [("atr", "tetap"), ("atr", "trailing"), ("n", "tetap"), ("n", "trailing")]


# ---------------------------------------------------------------- Data
def clean(h):
    """Sama dengan pembersihan di pullback.compute()."""
    h = h[["Open", "High", "Low", "Close", "Volume"]].copy()
    idx = pd.to_datetime(h.index)
    h.index = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
    h = h[~h.index.duplicated(keep="last")].sort_index().dropna(subset=["Close"])
    h = h[h["Close"] > 0]
    h["Volume"] = h["Volume"].fillna(0)
    for k in ("Open", "High", "Low"):
        h[k] = h[k].fillna(h["Close"])
    return h


def load_data(cache=None, sampai=None):
    meta = pb.load_universe()
    if cache:
        d = pickle.load(open(cache, "rb"))
        hist = {c: h for c, h in d["hist"].items() if c in meta}
        ih = d["ihsg"]["Close"] if isinstance(d["ihsg"], pd.DataFrame) else d["ihsg"]
        try:                                    # IHSG kecil: unduh ulang supaya hari yang bolong terisi
            ih = pb.download_ihsg(PERIOD)
        except Exception as e:  # noqa: BLE001
            print(f"  ! IHSG dari cache ({e})")
    else:
        print(f"Unduh {len(meta)} saham ({PERIOD})...")
        ih = pb.download_ihsg(PERIOD)
        hist = pb.download(list(meta), PERIOD)
    ih = ih.copy()
    ih.index = pd.to_datetime(ih.index)
    if ih.index.tz is not None:
        ih.index = ih.index.tz_localize(None)
    ih.index = ih.index.normalize()
    ih = ih[~ih.index.duplicated(keep="last")].sort_index().dropna()
    now = dt.datetime.now(pb.WIB)
    if sampai is None and now.time() < pb.CLOSE_READY:
        sampai = (now - dt.timedelta(days=1)).date()       # candle hari ini belum tutup
    frames = {}
    for c, h in hist.items():
        h = clean(h)
        if sampai is not None:
            h = h[h.index <= pd.Timestamp(sampai)]
        if len(h) >= 2:
            frames[c] = h
    if sampai is not None:
        ih = ih[ih.index <= pd.Timestamp(sampai)]
    return frames, ih, meta


# ---------------------------------------------------------------- Sinyal (pakai mesin pullback.py)
def find_triggers(frames, ih):
    X = {c: pb.indicators(h, ih) for c, h in frames.items()}
    R = pd.DataFrame({c: x["ret"] for c, x in X.items()})
    R3 = R.rank(axis=1, pct=True) * 100
    ma50 = ih.rolling(50).mean()
    syariah, hsc = pb.load_codes("syariah.json"), pb.load_codes("hsc.json")
    out = []
    for c, h in frames.items():
        x = X[c]
        x["r3"] = R3[c].reindex(x.index)
        if len(h) < pb.MIN_BARS:
            continue
        setup = ((x["p1"] < pb.P1_MAX) & (x["p2"] > pb.P2_MIN) & (x["p3"] > pb.P3_MIN)
                 & (x["r3"] >= pb.RS3M_MIN)).to_numpy()
        _, triggers, _ = pb.run_state(h, x, setup)
        for d in triggers:
            day = h.index[d]
            i_c = ih.asof(day)
            i_m = ma50.asof(day)
            out.append({"kode": c, "d": d, "tgl": day, "p3": float(x["p3"].iloc[d]), "atr": float(x["atr"].iloc[d]),
                        "rs": int(math.floor(x["rs"].iloc[d] + 0.5)), "r3": float(x["r3"].iloc[d]),
                        "pola": x["pattern"].iloc[d], "lead": bool(x["rs_lead"].iloc[d]),
                        "likuid": bool(x["value"].iloc[d] >= pb.LIQUID_IDR),
                        "pasar": "Bullish" if pb.ok(i_m) and i_c > i_m else "Bearish",
                        "syariah": c in syariah, "hsc": c in hsc})
    return out


# ---------------------------------------------------------------- Simulasi posisi
def simulate(h, d, entry, sl, tp, buy_stop, trailing):
    """Satu posisi. Semantik sama dengan pullback.fixed_trade / trail_trade, ditambah batas isi N_FILL candle
    untuk order bersyarat. Return dict {px, exit, i_in, i_out, sebab} atau None bila tidak terisi / masih jalan."""
    O, H, L = (h[k].to_numpy(float) for k in ("Open", "High", "Low"))
    n = len(h)
    risk = entry - sl
    if risk <= 0:
        return {"batal": "risiko <= 0"}
    filled, px, i_in = not buy_stop, entry, d
    stop, hh = sl, -np.inf
    for t in range(d + 1, n):
        if not filled:
            if t - d > N_FILL:
                return {"batal": "tidak terisi"}
            if H[t] < entry:
                continue
            filled, px, i_in = True, max(O[t], entry), t
            if L[t] <= stop:                     # hari terisi langsung jatuh ke SL (konservatif)
                return {"px": px, "exit": stop, "i_in": t, "i_out": t, "sebab": "SL"}
            if trailing:
                hh = H[t]
                stop = max(stop, vcp.down(hh - risk))
            # TP di hari terisi tidak dihitung (urutan intraday tidak diketahui)
            continue
        if L[t] <= stop:
            return {"px": px, "exit": min(O[t], stop), "i_in": i_in, "i_out": t,
                    "sebab": ("trailing" if stop > sl else "SL") if trailing else "SL"}
        if trailing:
            hh = max(hh, H[t])
            stop = max(stop, vcp.down(hh - risk))
        elif H[t] >= tp:
            return {"px": px, "exit": max(O[t], tp), "i_in": i_in, "i_out": t, "sebab": "TP"}
    return {"batal": "belum terisi" if not filled else "masih berjalan"}


def run(frames, trig):
    trades, skipped = [], {}
    for g in trig:
        h = frames[g["kode"]]
        d = g["d"]
        C = float(h["Close"].iloc[d])
        ae, asl, atp = pb.atr_levels(C, g["atr"])
        ne, nsl, ntp = pb.n_levels(h, d)
        for m, (e, sl, tp, bs) in (("atr", (ae, asl, atp, False)), ("n", (ne, nsl, ntp, True))):
            for mode in ("tetap", "trailing"):
                res = simulate(h, d, e, sl, tp, bs, mode == "trailing")
                if "batal" in res:
                    key = f"{m}/{mode}: {res['batal']}"
                    skipped[key] = skipped.get(key, 0) + 1
                    continue
                px, ex = res["px"], res["exit"]
                ru = px - sl
                if ru <= 0:          # terisi di atas entry karena gap, tapi SL tetap: risiko tetap positif
                    continue
                cost, proceeds = px * (1 + BUY_FEE), ex * (1 - SELL_FEE)
                trades.append({**{k: v for k, v in g.items() if k not in ("d",)},
                               "metode": m, "keluar_cara": mode, "entry": e, "sl": sl, "tp": tp if mode == "tetap" else None,
                               "px": px, "exit": ex, "sebab": res["sebab"],
                               "tgl_keluar": h.index[res["i_out"]], "hari": res["i_out"] - res["i_in"],
                               "r_kotor": (ex - px) / ru, "r": (proceeds - cost) / ru,
                               "ret_kotor": ex / px - 1, "ret": proceeds / cost - 1, "risk_pct": ru / px})
    return pd.DataFrame(trades), skipped


# ---------------------------------------------------------------- Statistik
def stats(t, col="r"):
    if not len(t):
        return {"trade": 0}
    r = t[col]
    wins, losses = r[r > 0], r[r <= 0]
    cur = t.sort_values("tgl_keluar")[col].cumsum()
    dd = float((cur - cur.cummax().clip(lower=0)).min()) if len(cur) else 0.0
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else None
    rc = "ret" if col == "r" else "ret_kotor"
    return {
        "trade": int(len(t)), "menang": round(float((r > 0).mean()), 3),
        "rata_r": round(float(r.mean()), 3), "median_r": round(float(r.median()), 3),
        # beberapa trade trailing bisa puluhan R (mis. saham naik 10x): rata-rata yang dipotong di persentil 99
        # menunjukkan seberapa besar hasil bergantung pada segelintir outlier
        "rata_r_p99": round(float(r.clip(upper=r.quantile(0.99)).mean()), 3), "maks_r": round(float(r.max()), 1),
        "se_r": round(float(r.std(ddof=1) / math.sqrt(len(r))), 3) if len(r) > 1 else None,
        "profit_factor": round(float(pf), 2) if pf else None,
        "total_r": round(float(r.sum()), 1), "max_dd_r": round(dd, 1),
        "rata_pct": round(float(t[rc].mean()) * 100, 2), "median_pct": round(float(t[rc].median()) * 100, 2),
        "rata_hari": round(float(t["hari"].mean()), 1),
    }


def bucket_p3(v):
    return "<5%" if v < 5 else "5–7%" if v < 7 else "7–10%" if v < 10 else ">10%"


def bucket_score(v):
    return "90–100" if v >= 90 else "80–89" if v >= 80 else "70–79"


def groups(t, col, order=None):
    keys = order or sorted(t[col].dropna().unique())
    return [{"kelompok": str(k), **stats(t[t[col] == k])} for k in keys if (t[col] == k).any()]


def report(t):
    t = t.copy()
    t["tahun"] = t["tgl"].dt.strftime("%Y")
    t["bulan"] = t["tgl"].dt.strftime("%Y-%m")
    t["volat"] = t["p3"].map(bucket_p3)
    t["skor"] = t["rs"].map(bucket_score)
    t["ranking"] = t["r3"].map(bucket_score)
    t["papan"] = np.where(t["likuid"], "Likuid (value ≥ Rp1 M)", "Tidak likuid")
    t["syr"] = np.where(t["syariah"], "Syariah", "Non-syariah")
    t["sebab_"] = t["sebab"]
    return {
        "ringkasan": stats(t), "tanpa_biaya": stats(t, "r_kotor"),
        "per_tahun": groups(t, "tahun"), "per_bulan": groups(t, "bulan"),
        "per_pasar": groups(t, "pasar", ["Bullish", "Bearish"]),
        "per_volatilitas": groups(t, "volat", ["<5%", "5–7%", "7–10%", ">10%"]),
        "per_skor_momentum": groups(t, "skor", ["70–79", "80–89", "90–100"]),
        "per_ranking_3bulan": groups(t, "ranking", ["70–79", "80–89", "90–100"]),
        "per_pola": groups(t, "pola"),
        "per_likuiditas": groups(t, "papan", ["Likuid (value ≥ Rp1 M)", "Tidak likuid"]),
        "per_syariah": groups(t, "syr", ["Syariah", "Non-syariah"]),
        "per_sebab_keluar": t["sebab_"].value_counts().to_dict(),
    }


def fr(x):
    return "-" if x is None else f"{x:+.2f}R".replace(".", ",")


def line(lbl, s):
    if not s.get("trade"):
        return f"  {lbl:<26} 0 trade"
    return (f"  {lbl:<26} {s['trade']:5} trade · menang {s['menang']:.0%} · rata {fr(s['rata_r'])} "
            f"(±{2 * (s['se_r'] or 0):.2f}; p99 {fr(s['rata_r_p99'])}) · median {fr(s['median_r'])} · PF {s['profit_factor']} · "
            f"total {s['total_r']:+.0f}R · DD {s['max_dd_r']:.0f}R · rata {s['rata_pct']:+.2f}%")


# ---------------------------------------------------------------- Main
def main():
    args = sys.argv[1:]
    cache = args[args.index("--cache") + 1] if "--cache" in args else None
    sampai = dt.date.fromisoformat(args[args.index("--sampai") + 1]) if "--sampai" in args else None
    frames, ih, meta = load_data(cache, sampai)
    print(f"Data: {len(frames)} saham, IHSG {ih.index[0]:%Y-%m-%d} s.d. {ih.index[-1]:%Y-%m-%d}")
    trig = find_triggers(frames, ih)
    print(f"Entry trigger: {len(trig)} (sejak {min(g['tgl'] for g in trig):%Y-%m-%d})")
    tr, skipped = run(frames, trig)
    if tr.empty:
        print("Tidak ada trade.")
        return
    last = max(h.index[-1] for h in frames.values())
    one_year = last - pd.Timedelta(days=365)
    mei_okt = (tr["tgl"] >= "2026-05-01") & (tr["tgl"] <= "2026-10-31")

    payload = {
        "updated": dt.datetime.now(pb.WIB).isoformat(timespec="minutes"),
        "periode": [f"{min(g['tgl'] for g in trig):%Y-%m-%d}", f"{last:%Y-%m-%d}"],
        "universe": len(frames), "trigger": len(trig),
        "trigger_per_bulan": pd.Series([f"{g['tgl']:%Y-%m}" for g in trig]).value_counts().sort_index().to_dict(),
        "asumsi": {
            "biaya_beli": BUY_FEE, "biaya_jual": SELL_FEE, "slippage": 0, "n_candle_batas_isi": N_FILL,
            "entry_atr": "harga tutup candle trigger", "entry_n": "buy-stop high 2 candle, terisi bila high besok menembus",
            "sl_tp_hari_sama": "anggap SL", "posisi_tumpang_tindih": True,
            "catatan": "Universe = saham yang masih tercatat sekarang (survivorship bias), data harian Yahoo tanpa "
                       "penyesuaian dividen, ARB/antrean tidak dimodelkan, label Syariah memakai daftar saat ini.",
        },
        "dilewati": skipped,
        "klaim_situs": SITE_CLAIM,
        "strategi": {},
    }
    print(f"\nPeriode trigger {payload['periode'][0]} s.d. {payload['periode'][1]} · {len(frames)} saham · "
          f"biaya beli {BUY_FEE:.2%} jual {SELL_FEE:.2%}")
    for m, mode in COMBOS:
        t = tr[(tr["metode"] == m) & (tr["keluar_cara"] == mode)]
        rep = report(t)
        rep["satu_tahun"] = {"bersih": stats(t[t["tgl"] >= one_year]), "tanpa_biaya": stats(t[t["tgl"] >= one_year], "r_kotor")}
        rep["mei_okt_2026"] = {"bersih": stats(t[mei_okt.loc[t.index]]),
                               "tanpa_biaya": stats(t[mei_okt.loc[t.index]], "r_kotor")}
        key = f"{m}_{mode}"
        payload["strategi"][key] = rep
        nama = f"{'ATR' if m == 'atr' else 'N-candle'} · SL/TP {mode}" if mode == "tetap" else \
            f"{'ATR' if m == 'atr' else 'N-candle'} · trailing"
        print(f"\n== {nama}")
        print(line("Semua (bersih)", rep["ringkasan"]))
        print(line("Semua (tanpa biaya)", rep["tanpa_biaya"]))
        print(line("1 tahun terakhir (bersih)", rep["satu_tahun"]["bersih"]))
        print(line("1 thn (tanpa biaya)", rep["satu_tahun"]["tanpa_biaya"]))
        print(line("Mei–Okt 2026 (bersih)", rep["mei_okt_2026"]["bersih"]))
        print(line("Mei–Okt 2026 (tanpa biaya)", rep["mei_okt_2026"]["tanpa_biaya"]))
        for sec in ("per_tahun", "per_pasar", "per_volatilitas", "per_skor_momentum", "per_ranking_3bulan",
                    "per_pola", "per_likuiditas", "per_syariah"):
            print(f"  -- {sec.replace('_', ' ')}")
            for g in rep[sec]:
                print("  " + line(g["kelompok"], g))
        print(f"  -- sebab keluar: {rep['per_sebab_keluar']}")
    print("\nDilewati:", skipped)
    payload["kesimpulan"] = kesimpulan(payload)
    print("\nKesimpulan:", *payload["kesimpulan"], sep="\n  ")
    OUT.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, default=str), encoding="utf-8")
    print(f"Tersimpan: {OUT}")


def kesimpulan(p):
    """Kalimat ringkas, apa adanya."""
    out = []
    for key, nama in (("atr_tetap", "ATR, SL/TP tetap"), ("atr_trailing", "ATR, trailing"),
                      ("n_tetap", "N-candle, SL/TP tetap"), ("n_trailing", "N-candle, trailing")):
        s = p["strategi"][key]["ringkasan"]
        g = p["strategi"][key]["tanpa_biaya"]
        lo, hi = s["rata_r"] - 2 * s["se_r"], s["rata_r"] + 2 * s["se_r"]
        out.append(f"{nama}: {s['trade']} trade, menang {s['menang']:.0%}, rata {fr(s['rata_r'])} setelah biaya "
                   f"({fr(g['rata_r'])} tanpa biaya; {fr(s['rata_r_p99'])} bila trade terbesar dipotong di persentil 99, "
                   f"trade terbesar {s['maks_r']:+.0f}R), PF {s['profit_factor']}, rentang ~95% {fr(lo)} s.d. {fr(hi)}"
                   + (": belum terbukti berbeda dari nol." if lo <= 0 < hi else ": positif secara statistik." if lo > 0
                      else ": negatif secara statistik."))
    return out


if __name__ == "__main__":
    main()
