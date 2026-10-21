"""
IDX Momentum Screener — Fase 1: Relative Strength + Trend Template
==================================================================
Memindai SELURUH saham BEI (data/universe.json) dengan kerangka SEPA Mark Minervini:

  - RS Rating (gaya IBD/O'Neil)  -> persentil 1-99 kinerja 12 bulan berbobot dibanding semua saham BEI.
                                    Ini Relative Strength / Relative Performance, BUKAN RSI.
  - RS Line                       -> harga saham / IHSG. Menanjak = saham mengalahkan pasar.
  - Ketahanan koreksi             -> seberapa kuat saham bertahan saat IHSG turun.
  - Trend Template 8 poin         -> syarat mutlak Stage 2.
  - Perkiraan Stage Weinstein     -> 1 basing, 2 naik, 3 puncak, 4 turun.
  - Arah pasar (IHSG)             -> momentum hanya dieksekusi saat pasar mendukung.

  - Fase 2 (vcp.py): pola VCP, pivot, entry trigger, SL/TP dan status posisi.
  - Fase 3 (analisa.py): skor setup, briefing per saham, breadth & sektor.
  - Fase 4 (hgm.py): pertumbuhan laba & penjualan kuartalan (HGM) dan katalis aksi korporasi.
  - Setup kedua (signals.py): pembalikan pemimpin RS saat pasar koreksi.

Hasil: docs/data/momentum.json (dibaca website), docs/data/chart/KODE.json (grafik kandidat)
dan data/momentum_YYYY-MM-DD.csv.
Data harian Yahoo Finance (bisa telat/bolong untuk saham kecil). Alat bantu riset, BUKAN rekomendasi.
"""

import json
import math
import os
import datetime as dt
from pathlib import Path

import pandas as pd
import yfinance as yf

import analisa
import hgm
import signals
import vcp

# ---------------------------------------------------------------- Pengaturan
MIN_AVG_VALUE_IDR = float(os.getenv("MOM_MIN_VALUE_IDR", 1e9))  # likuiditas min watchlist: Rp1 miliar/hari
RS_MIN = 70            # syarat Trend Template
RS_FOCUS = 90          # fokus utama modul
CHUNK = 100            # jumlah ticker per permintaan yf.download
CHART_BARS = 260       # panjang data grafik per kandidat (~1 tahun)

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
SITE = BASE / "docs" / "data"
WIB = dt.timezone(dt.timedelta(hours=7))

# Hari bursa per periode
D1M, D3M, D6M, D9M, D12M = 21, 63, 126, 189, 252

TT_LABELS = [
    "Harga > MA150 & MA200",
    "MA150 > MA200",
    "MA200 menanjak min. 1 bulan",
    "MA50 > MA150 & MA200",
    "Harga > MA50",
    "Harga ≥ 25% di atas low 52 minggu",
    "Harga dalam 25% dari high 52 minggu",
    f"RS Rating ≥ {RS_MIN}",
]


# ---------------------------------------------------------------- Utilitas
def ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def r(x, d=4):
    return round(float(x), d) if ok(x) else None


def load_universe():
    p = DATA_DIR / "universe.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))["rows"]
    # cadangan: daftar manual screener fundamental
    codes = [ln.strip().upper() for ln in (BASE / "tickers.txt").read_text().splitlines()
             if ln.strip() and not ln.startswith("#")]
    return [{"kode": c, "nama": c, "sektor": "-"} for c in dict.fromkeys(codes)]


# ---------------------------------------------------------------- Ambil data
def download(codes, period="2y"):
    """Histori harian ~2 tahun (butuh 252 hari + MA200 + kemiringan MA200). Return {kode: DataFrame}."""
    out = {}
    for i in range(0, len(codes), CHUNK):
        part = codes[i:i + CHUNK]
        print(f"  unduh {i + 1}-{i + len(part)} dari {len(codes)}")
        df = yf.download([f"{c}.JK" for c in part], period=period, interval="1d", group_by="ticker",
                         auto_adjust=True, threads=True, progress=False)
        for c in part:
            try:
                h = df[f"{c}.JK"] if isinstance(df.columns, pd.MultiIndex) else df
            except KeyError:
                continue
            h = h.dropna(subset=["Close"])
            h = h[h["Close"] > 0]
            if len(h) >= 60:
                out[c] = h
    return out


def download_ihsg(period="2y"):
    h = yf.Ticker("^JKSE").history(period=period, auto_adjust=True)
    h = h.dropna(subset=["Close"])
    h.index = h.index.tz_localize(None).normalize()
    return h["Close"]


# ---------------------------------------------------------------- Relative Strength
def rs_raw(close):
    """Skor kinerja berbobot ala IBD: kuartal terakhir dibobot ganda.
    = 40% ROC 3 bln + 20% ROC 6 bln + 20% ROC 9 bln + 20% ROC 12 bln.
    Saham yang listing < 6 bulan tidak diberi skor (belum cukup bukti)."""
    n = len(close)
    if n <= D6M:
        return None
    p = close.iloc[-1]

    def roc(k):
        return p / close.iloc[-1 - k] - 1 if n > k else None

    parts = [(0.4, roc(D3M)), (0.2, roc(D6M)), (0.2, roc(D9M)), (0.2, roc(D12M))]
    parts = [(w, v) for w, v in parts if ok(v)]
    tw = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / tw


def rs_line_stats(close, ihsg):
    """RS Line = harga / IHSG (diselaraskan per tanggal)."""
    idx = ihsg.reindex(close.index, method="ffill")
    line = (close / idx).dropna()
    if len(line) < D3M:
        return {}
    win = line.tail(D12M)
    high_now = bool(line.tail(5).max() >= win.max() * 0.999)       # RS Line cetak rekor 52 minggu (5 hari terakhir)
    price_win = close.tail(D12M)
    price_high_now = bool(close.tail(5).max() >= price_win.max() * 0.999)
    return {
        "rs_line_naik_1b": bool(line.iloc[-1] > line.iloc[-1 - D1M]),
        "rs_line_naik_3b": bool(line.iloc[-1] > line.iloc[-1 - D3M]),
        "rs_line_high": high_now,
        # sinyal kunci: RS Line sudah di puncak sementara harga belum -> institusi akumulasi lebih dulu
        "rs_line_mendahului": high_now and not price_high_now,
    }


def ihsg_correction(ihsg):
    """Koreksi IHSG terdalam dalam 3 bulan terakhir: (tanggal puncak, tanggal dasar, % turun)."""
    w = ihsg.tail(D3M)
    dd = w / w.cummax() - 1
    trough = dd.idxmin()
    peak = w.loc[:trough].idxmax()
    return peak, trough, float(dd.min())


def resilience(close, peak, trough, ihsg_drop):
    """Kinerja saham selama periode koreksi IHSG, dikurangi penurunan IHSG.
    Positif = saham lebih tahan dari pasar. Hanya dihitung jika IHSG turun >= 5%."""
    if ihsg_drop > -0.05:
        return None
    try:
        a = close.loc[:peak].iloc[-1]
        b = close.loc[:trough].iloc[-1]
    except IndexError:
        return None
    return float(b / a - 1 - ihsg_drop)


# ---------------------------------------------------------------- Tren & Stage
def trend_and_stage(h):
    close, high, low = h["Close"], h["High"], h["Low"]
    p = float(close.iloc[-1])
    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()
    m50, m150, m200 = (float(s.iloc[-1]) if ok(s.iloc[-1]) else None for s in (ma50, ma150, ma200))

    # Berapa hari berturut-turut MA200 naik dibanding 1 bulan sebelumnya
    up = (ma200 > ma200.shift(D1M)).dropna()
    ma200_up_days = 0
    for v in reversed(up.tolist()):
        if not v:
            break
        ma200_up_days += 1

    hi52 = float(high.tail(D12M).max())
    lo52 = float(low.tail(D12M).min())

    have = all(ok(x) for x in (m50, m150, m200)) and len(close) > 200 + D1M
    checks = [
        p > m150 and p > m200 if have else None,
        m150 > m200 if have else None,
        ma200_up_days >= 1 if have else None,
        m50 > m150 and m50 > m200 if have else None,
        p > m50 if ok(m50) else None,
        p >= lo52 * 1.25,
        p >= hi52 * 0.75,
        None,  # RS, diisi setelah persentil dihitung
    ]

    # Perkiraan Stage dari MA150 (~30 minggu, acuan Weinstein)
    stage = None
    if ok(m150) and len(ma150.dropna()) > D1M:
        slope = m150 / float(ma150.iloc[-1 - D1M]) - 1
        rising, falling = slope > 0.01, slope < -0.01
        if p > m150 and rising:
            stage = 2
        elif p < m150 and falling:
            stage = 4
        elif p < m150 and rising:
            stage = 3   # tren naik mulai patah
        elif p > m150 and falling:
            stage = 1   # mulai pulih dari dasar
        else:            # MA150 datar: basing setelah turun (1) atau distribusi setelah naik (2->3)
            back = ma150.dropna()
            stage = 3 if len(back) > D6M and m150 > float(back.iloc[-1 - D6M]) * 1.10 else 1

    return {
        "harga": p, "ma50": m50, "ma150": m150, "ma200": m200,
        "ma200_naik_hari": ma200_up_days if have else None,
        "high52": hi52, "low52": lo52,
        "dari_high52": p / hi52 - 1, "dari_low52": p / lo52 - 1,
        "checks": checks, "stage": stage,
    }


def market_status(ihsg):
    p = float(ihsg.iloc[-1])
    m50 = float(ihsg.rolling(50).mean().iloc[-1])
    ma200 = ihsg.rolling(200).mean()
    m200 = float(ma200.iloc[-1])
    m200_up = bool(ma200.iloc[-1] > ma200.iloc[-1 - D1M])
    if p > m50 and p > m200 and m200_up:
        status, note = "uptrend", "IHSG di atas MA50 & MA200 yang menanjak. Pasar mendukung breakout."
    elif p > m200:
        status, note = "tertekan", "IHSG di atas MA200 tapi di bawah MA50/MA200 mendatar. Pilih hanya setup terbaik, posisi lebih kecil."
    else:
        status, note = "downtrend", "IHSG di bawah MA200. Kebanyakan breakout gagal; utamakan kas."
    return {
        "ihsg": p, "chg_1d": float(ihsg.iloc[-1] / ihsg.iloc[-2] - 1),
        "ma50": m50, "ma200": m200, "ma200_naik": m200_up,
        "ret_3m": float(p / ihsg.iloc[-1 - D3M] - 1), "ret_12m": float(p / ihsg.iloc[-1 - D12M] - 1),
        "dari_high52": float(p / ihsg.tail(D12M).max() - 1),
        "status": status, "catatan": note,
    }


def write_chart(folder, code, h, ihsg, rsr):
    """OHLCV ~1 tahun + IHSG (untuk RS Line) + RS Rating harian agar website bisa menggambar level sendiri."""
    t = h.tail(CHART_BARS)
    rsr = rsr.reindex(t.index)
    ih = ihsg.reindex(t.index, method="ffill")
    rnd = lambda s: [None if not ok(v) else round(float(v), 2) for v in s]  # noqa: E731
    data = {"t": [f"{d:%Y-%m-%d}" for d in t.index], "o": rnd(t["Open"]), "h": rnd(t["High"]), "l": rnd(t["Low"]),
            "c": rnd(t["Close"]), "v": [int(v) if ok(v) else 0 for v in t["Volume"]], "ihsg": rnd(ih),
            # MA dihitung dari histori penuh supaya awal grafik tidak kosong
            "ma50": rnd(h["Close"].rolling(50).mean().tail(CHART_BARS)),
            "ma150": rnd(h["Close"].rolling(150).mean().tail(CHART_BARS)),
            "ma200": rnd(h["Close"].rolling(200).mean().tail(CHART_BARS)),
            "rsr": [None if not ok(v) else int(round(float(v))) for v in rsr]}
    (folder / f"{code}.json").write_text(json.dumps(data, allow_nan=False), encoding="utf-8")


# ---------------------------------------------------------------- Main
def main():
    DATA_DIR.mkdir(exist_ok=True)
    SITE.mkdir(parents=True, exist_ok=True)
    uni = load_universe()
    meta = {u["kode"]: u for u in uni}
    codes = list(meta)
    print(f"Momentum: memindai {len(codes)} saham...")

    ihsg = download_ihsg()
    hist = download(codes)
    print(f"  data tersedia: {len(hist)} saham")
    peak, trough, ihsg_drop = ihsg_correction(ihsg)

    rows, frames = [], {}
    for c, h in hist.items():
        h = h.copy()
        h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
        frames[c] = h
        close = h["Close"]
        last_date = h.index[-1]
        if (ihsg.index[-1] - last_date).days > 7:
            continue  # suspensi / tidak diperdagangkan lagi
        t = trend_and_stage(h)
        value20 = float((h["Close"] * h["Volume"]).tail(20).mean())
        flags = []
        if value20 < MIN_AVG_VALUE_IDR:
            flags.append("TIDAK LIKUID")
        if len(close) <= D12M:
            flags.append("LISTING < 1 TAHUN")
        if int((h["Volume"].tail(20) == 0).sum()) >= 5:
            flags.append("SERING TIDAK DITRANSAKSIKAN")
        if t["harga"] < 50:
            flags.append("HARGA < 50")
        rows.append({
            "kode": c, "nama": meta[c]["nama"], "sektor": meta[c]["sektor"],
            "tgl_data": f"{last_date:%Y-%m-%d}",
            "chg_1d": float(close.iloc[-1] / close.iloc[-2] - 1),
            "ret_1m": float(close.iloc[-1] / close.iloc[-1 - D1M] - 1) if len(close) > D1M else None,
            "ret_3m": float(close.iloc[-1] / close.iloc[-1 - D3M] - 1) if len(close) > D3M else None,
            "ret_6m": float(close.iloc[-1] / close.iloc[-1 - D6M] - 1) if len(close) > D6M else None,
            "ret_12m": float(close.iloc[-1] / close.iloc[-1 - D12M] - 1) if len(close) > D12M else None,
            "nilai_rata2": value20,
            "rs_raw": rs_raw(close),
            "ketahanan": resilience(close, peak, trough, ihsg_drop),
            **rs_line_stats(close, ihsg),
            **t,
            "flags": flags,
        })

    df = pd.DataFrame(rows)
    # RS Rating: persentil 1-99 terhadap semua saham BEI yang punya skor (likuid maupun tidak, seperti IBD)
    has = df["rs_raw"].notna()
    df.loc[has, "rs_rating"] = (df.loc[has, "rs_raw"].rank(pct=True) * 98 + 1).round().clip(1, 99)

    out_rows = []
    for _, x in df.iterrows():
        rs = x.get("rs_rating")
        checks = list(x["checks"])
        checks[7] = bool(rs >= RS_MIN) if ok(rs) else None
        passed = sum(1 for v in checks if v)
        lolos = all(v is True for v in checks)
        # saham yang jarang ditransaksikan (sering ARA/ARB beruntun, suspensi) tidak bisa dieksekusi
        likuid = not {"TIDAK LIKUID", "SERING TIDAK DITRANSAKSIKAN"} & set(x["flags"])
        if lolos and likuid:
            label = "Stage 2 · RS 90+" if rs >= RS_FOCUS else "Stage 2"
        elif passed >= 6 and likuid:
            label = "Hampir"
        else:
            label = None
        out_rows.append({
            "kode": x["kode"], "nama": x["nama"], "sektor": x["sektor"], "tgl_data": x["tgl_data"],
            "harga": r(x["harga"], 2), "chg_1d": r(x["chg_1d"]),
            "ret_1m": r(x["ret_1m"]), "ret_3m": r(x["ret_3m"]), "ret_6m": r(x["ret_6m"]), "ret_12m": r(x["ret_12m"]),
            "nilai_rata2": r(x["nilai_rata2"], 0), "likuid": likuid,
            "rs_rating": int(rs) if ok(rs) else None, "rs_raw": r(x["rs_raw"]),
            "rs_line_naik_1b": x.get("rs_line_naik_1b"), "rs_line_naik_3b": x.get("rs_line_naik_3b"),
            "rs_line_high": x.get("rs_line_high"), "rs_line_mendahului": x.get("rs_line_mendahului"),
            "ketahanan": r(x["ketahanan"]),
            "ma50": r(x["ma50"], 2), "ma150": r(x["ma150"], 2), "ma200": r(x["ma200"], 2),
            "ma200_naik_hari": None if not ok(x["ma200_naik_hari"]) else int(x["ma200_naik_hari"]),
            "high52": r(x["high52"], 2), "low52": r(x["low52"], 2),
            "dari_high52": r(x["dari_high52"]), "dari_low52": r(x["dari_low52"]),
            "tt": checks, "tt_skor": passed, "lolos_tt": lolos, "stage": None if not ok(x["stage"]) else int(x["stage"]),
            "label": label, "flags": x["flags"],
        })

    # Matriks lintas saham: RS Rating harian & setup pembalikan pemimpin RS
    O, H, L, C, V = signals.matrices(frames, ihsg.index)
    rs_m = signals.rs_rating_matrix(C)
    tt_m = signals.trend_template_matrix(H, L, C, rs_m)
    rev_m = signals.reversal_matrix(O, H, L, C, V, ihsg, rs_m, tt_m, signals.tradable_matrix(C, V, MIN_AVG_VALUE_IDR))
    rev_recent = rev_m.iloc[-(vcp.TRACK + 1):].any()

    # Fase 2: VCP & entry untuk saham likuid yang lolos/hampir lolos Trend Template atau punya trigger pembalikan RS.
    # Kalau keduanya ada, trigger yang paling baru yang dipakai.
    chart_dir = SITE / "chart"
    chart_dir.mkdir(exist_ok=True)
    for f in chart_dir.glob("*.json"):
        f.unlink()
    for z in out_rows:
        z["entry"] = None
        code = z["kode"]
        has_rev = bool(rev_recent.get(code, False))
        if z["likuid"] and (z["tt_skor"] >= 6 or has_rev):
            h = frames[code]
            e_v = e_r = None
            try:
                e_v = vcp.analyze(h)
                e_r = signals.reversal_entry(h, rev_m[code]) if has_rev else None
            except Exception as e:  # noqa: BLE001
                print(f"  ! {code}: analisa setup gagal ({e})")
            if e_v:
                e_v.setdefault("setup", "vcp")
            if e_r and not (e_v and e_v.get("tgl_trigger") and e_v["tgl_trigger"] >= e_r["tgl_trigger"]):
                e_r["vcp_info"] = (e_v or {}).get("vcp")
                z["entry"] = e_r
            else:
                z["entry"] = e_v
            write_chart(chart_dir, code, h, ihsg, rs_m[code])

    market = market_status(ihsg)
    market["koreksi_3b"] = {"puncak": f"{peak:%Y-%m-%d}", "dasar": f"{trough:%Y-%m-%d}", "turun": round(ihsg_drop, 4)}

    # Fase 4: fundamental HGM & katalis hanya untuk kandidat (permintaan ke Yahoo dibatasi)
    cand = [z["kode"] for z in out_rows if z["likuid"] and (z["tt_skor"] >= 6 or z["entry"])]
    print(f"  HGM & katalis untuk {len(cand)} kandidat...")
    hg, kat = hgm.hgm_for(cand), hgm.katalis_for(cand)
    for z in out_rows:
        z["hgm"] = hg.get(z["kode"])
        z["katalis"] = kat.get(z["kode"], [])

    # Fase 3: skor setup & briefing untuk saham yang relevan (menjaga ukuran JSON tetap kecil).
    # Hasil backtest mingguan ikut dikutip di briefing sebagai bukti per kondisi pasar.
    try:
        bt_raw = json.loads((SITE / "backtest.json").read_text(encoding="utf-8"))["strategi"]
        bt = {m: {g["kelompok"]: (g["trade"], g["rata_r"]) for g in v["per_pasar"]} for m, v in bt_raw.items()}
    except (OSError, ValueError, KeyError):
        bt = {}
    for z in out_rows:
        relevant = z["likuid"] and (z["tt_skor"] >= 5 or z["entry"])
        z["skor_setup"] = analisa.skor_setup(z, market["status"]) if relevant else None
        z["briefing"] = analisa.briefing(z, market, TT_LABELS, bt) if relevant else None
    an = analisa.pasar(market, out_rows, frames, ihsg)
    an["pemimpin"] = [z["kode"] for z in sorted((z for z in out_rows if z["lolos_tt"] and z["likuid"]),
                                                key=lambda z: -z["skor_setup"])[:10]]

    out_rows.sort(key=lambda z: (not z["lolos_tt"] or not z["likuid"], -(z["rs_rating"] or 0)))
    payload = {
        "schema": 3,
        "updated": dt.datetime.now(WIB).isoformat(timespec="minutes"),
        "tgl_data": f"{ihsg.index[-1]:%Y-%m-%d}",
        "universe": len(codes), "dipindai": len(out_rows),
        "tt_labels": TT_LABELS,
        "pasar": {k: (r(v) if isinstance(v, float) else v) for k, v in market.items()},
        "analisa": an,
        "rows": out_rows,
    }
    (SITE / "momentum.json").write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    flat = pd.DataFrame(out_rows)
    for k in ("status", "tgl_trigger", "entry", "sl", "tp1", "tp2"):
        flat[f"e_{k}"] = flat["entry"].map(lambda e, k=k: (e or {}).get(k))
    flat["briefing"] = flat["briefing"].map(lambda b: b["vonis"] if b else None)
    flat = flat.drop(columns="entry")
    for i, lab in enumerate(TT_LABELS):
        flat[f"tt{i + 1}"] = flat["tt"].map(lambda v, i=i: v[i])
    flat.drop(columns="tt").assign(flags=flat["flags"].map(", ".join)).to_csv(
        DATA_DIR / f"momentum_{dt.datetime.now(WIB):%Y-%m-%d}.csv", index=False)

    sig = [z for z in out_rows if z["entry"] and z["entry"]["status"]]
    from collections import Counter
    print("Status entry:", dict(Counter(z["entry"]["status"] for z in sig)))
    for z in sig:
        e = z["entry"]
        if e["status"] in ("entry_hari_ini", "entry_baru", "setup", "kena_sl", "sl_naik_lagi", "kena_tp1"):
            print(f"  {z['kode']:5} {e['label']:<34} trig {e.get('tgl_trigger', '-'):10} entry {e['entry']:>7,} "
                  f"SL {e['sl']:>7,} ({e['sl_pct']:.1%}) TP1 {e['tp1']:>7,} · {e.get('setup')} {(e.get('vcp') or {}).get('kedalaman', '')}")
    print("Analisa:", an["teks"])
    print("Sektor:", [(x["sektor"], x["rs_median"], x["lolos_tt"]) for x in an["sektor"][:5]])
    print("Pemimpin (skor setup):", an["pemimpin"])
    n2 = sum(1 for z in out_rows if z["lolos_tt"] and z["likuid"])
    n90 = sum(1 for z in out_rows if z["label"] == "Stage 2 · RS 90+")
    print(f"Tersimpan: docs/data/momentum.json ({len(out_rows)} saham)")
    print(f"IHSG: {market['status']} · lolos Trend Template (likuid): {n2} · di antaranya RS 90+: {n90}")
    for z in [z for z in out_rows if z["lolos_tt"] and z["likuid"]][:15]:
        print(f"  {z['kode']:5} RS {z['rs_rating']:>2} · Rp{z['harga']:,.0f} · {z['dari_high52'] * 100:+.0f}% dr high · "
              f"RS line {'HIGH' if z['rs_line_high'] else '-'}")


if __name__ == "__main__":
    main()
