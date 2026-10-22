"""
Screener "Saham kuat yang sedang pullback"
==========================================
Rekonstruksi mesin situs referensi (indikator DL-PHunter Pro di TradingView), dikalibrasi terhadap
snapshot penutupan 21 Okt 2026. Rumus lengkap & kontrak data: spesifikasi_pullback.md.

  - Tiga poin setup     -> P1 pullback (close / SMA5 < 1), P2 performa vs IHSG 50 hari (> 1,05),
                           P3 volatilitas ATR(5) Wilder / close (> 3%).
  - Ranking 3 Bulan     -> persentil return 63 hari dibanding semua saham hari itu (>= 70).
  - Skor Momentum       -> percentrank 63 hari (gaya ta.percentrank) dari ret63 saham - ret63 IHSG (>= 70).
  - Garis Momentum      -> close / IHSG dan MA50-nya: Positif, Crossing, Puncak, Puncak+, Momentum Duluan.
  - Mesin keadaan       -> setup valid -> watchlist -> jendela 5 candle -> entry trigger (candle hijau,
                           volume >= 1,1x, pola candle bullish, Skor Momentum >= 70) -> posisi.
  - Level               -> metode ATR (SL 1,5 ATR, TP 3 ATR) dan N-candle (high/low 2 candle, TP 2R),
                           lot untuk risiko Rp1 juta, trailing stop kedua metode.

Pemakaian:
  python pullback.py      snapshot Penutupan -> docs/data/pullback.json
  python pullback.py s1   snapshot Sesi 1 (candle hari ini belum tutup) -> docs/data/pullback_s1.json
Grafik per saham (selain "Tidak ada sinyal"): docs/data/pullback_chart/KODE.json.
Data harian Yahoo Finance TANPA penyesuaian dividen (sama seperti situs referensi). Alat bantu riset, BUKAN rekomendasi.
"""

import json
import math
import sys
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

import vcp

# ---------------------------------------------------------------- Pengaturan
P1_MAX = 1.0           # close / SMA5 di bawah ini = sedang pullback
P2_MIN = 1.05          # kinerja 50 hari relatif IHSG
P3_MIN = 3.0           # ATR(5) / close dalam %
RS3M_MIN = 70          # Ranking 3 Bulan minimum (syarat setup)
RS_MIN = 70            # Skor Momentum minimum (syarat trigger)
SMA_P1 = 5
P2_LEN = 50
ATR_LEN = 5
RET_LEN = 63           # 3 bulan bursa
PRANK_LEN = 63
RL_MA = 50             # MA garis momentum
RS_HIGH_LEN = 50       # Momentum Puncak = tertinggi 50 hari
ADX_LEN = 14
EXT_EMA = 21           # ext_atr = (close - EMA21) / ATR(5)
EXT_MAX = 3.0          # *(ditebak)* batas "extended"; semua contoh situs <= 2,61 dan tidak extended
WATCH_DAYS = 5         # jendela trigger setelah watchlist
ENTRY_DAYS = 5         # "Entry baru" = trigger 1-5 hari bursa lalu
LEAD_RECENT = 5        # lead_date hanya Momentum Duluan <= 5 hari bursa terakhir *(disimpulkan)*
VOL_X = 1.1            # volume trigger >= 1,1x rata-rata 5 hari sebelumnya
VOL_AVG = 5
VALUE_AVG = 5          # value_avg = rata-rata nilai transaksi 5 hari (termasuk hari ini)
LIQUID_IDR = 1e9
QUALITY_VOL = 1.2      # Puncak+: volume >= 1,2x rata-rata 5 hari sebelumnya
ATR_SL, ATR_TP = 1.5, 3.0
N_BARS, N_RR = 2, 2.0
RISK_IDR = 1e6         # risiko per transaksi untuk hitung lot
MIN_BARS = RET_LEN + PRANK_LEN + 1   # kurang dari ini: "Riwayat belum cukup" (±6 bulan)
CHART_BARS = 130
PERIOD = "1y"          # situs memakai 1 tahun data harian
CHUNK = 100
CLOSE_READY = dt.time(16, 15)   # data Yahoo penutupan baru lengkap ±15 menit setelah 16:00 WIB

# Saham yang tidak ada di scanner TradingView (universe.json) tapi masih punya data Yahoo, kebanyakan
# sedang disuspensi. Situs referensi ikut memasukkannya (universe 921) sehingga ikut memengaruhi persentil
# Ranking 3 Bulan. Ditemukan dengan menguji kode ke Yahoo; data/syariah.json & data/hsc.json juga dipakai.
EXTRA_CODES = (
    "ALMI ALTO ARKA ARTI BIKA BIMA BOSS CMPP CNKO DEAL DIGI ETWA GLOB HITS INAF INCF INDX INPS INRU INTA "
    "KAYU LCKM MDRN MREI MTFN PLIN POLL POLY TELE TOPS TOYS WICO WIKA WSBP ZBRA ZINC").split()

PATTERNS = ["Bullish Engulfing", "Hammer", "Inverted Hammer", "Piercing Line", "Bullish Harami",
            "Morning Star", "Bullish Marubozu"]

STATUSES = ["Entry hari ini", "Entry baru", "Kena SL", "Kena TP", "Kena SL, naik lagi", "Menunggu trigger",
            "Setup valid", "Tidak ada sinyal", "Riwayat belum cukup"]

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
SITE = BASE / "docs" / "data"
CHART_DIR = SITE / "pullback_chart"
WIB = dt.timezone(dt.timedelta(hours=7))
SESSION_LABEL = {"close": "Penutupan", "s1": "Sesi 1"}


# ---------------------------------------------------------------- Utilitas
def ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def rn(x, d=2):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, d) if math.isfinite(x) else None


def num(x):
    """Harga bulat ditulis sebagai int (1140, bukan 1140.0)."""
    if not ok(x):
        return None
    x = float(x)
    return int(round(x)) if abs(x - round(x)) < 1e-6 else round(x, 2)


def inum(x):
    return int(round(float(x))) if ok(x) and math.isfinite(float(x)) else None


def ds(d):
    return f"{d:%Y-%m-%d}" if d is not None else None


def load_codes(name):
    try:
        return set(json.loads((DATA_DIR / name).read_text(encoding="utf-8"))["kode"])
    except (OSError, ValueError, KeyError):
        return set()


def load_universe():
    """{kode: nama}: universe.json + daftar Syariah/HSC + EXTRA_CODES."""
    try:
        rows = json.loads((DATA_DIR / "universe.json").read_text(encoding="utf-8"))["rows"]
        meta = {r["kode"]: r.get("nama") or r["kode"] for r in rows}
    except (OSError, ValueError, KeyError):
        meta = {ln.strip().upper(): ln.strip().upper() for ln in (BASE / "tickers.txt").read_text().splitlines()
                if ln.strip() and not ln.startswith("#")}
    for c in sorted(load_codes("syariah.json") | load_codes("hsc.json") | set(EXTRA_CODES)):
        meta.setdefault(c, c)
    return meta


# ---------------------------------------------------------------- Ambil data
def download(codes, period=PERIOD, retry=True):
    """Histori harian TIDAK disesuaikan dividen (auto_adjust=False). Return {kode: DataFrame OHLCV}.
    Kode yang gagal (Yahoo kadang melewatkan beberapa simbol dalam satu permintaan) dicoba sekali lagi."""
    import yfinance as yf
    out = {}
    for i in range(0, len(codes), CHUNK):
        part = codes[i:i + CHUNK]
        print(f"  unduh {i + 1}-{i + len(part)} dari {len(codes)}")
        try:
            df = yf.download([f"{c}.JK" for c in part], period=period, interval="1d", group_by="ticker",
                             auto_adjust=False, threads=True, progress=False)
        except Exception as e:  # noqa: BLE001
            print(f"  ! unduh gagal: {e}")
            continue
        for c in part:
            try:
                h = df[f"{c}.JK"] if isinstance(df.columns, pd.MultiIndex) else df
            except KeyError:
                continue
            h = h.dropna(subset=["Close"])
            if len(h):
                out[c] = h[["Open", "High", "Low", "Close", "Volume"]].copy()
    miss = [c for c in codes if c not in out]
    if retry and miss and len(miss) < len(codes):
        print(f"  ulang {len(miss)} kode yang gagal")
        out.update(download(miss, period, retry=False))
    return out


def download_ihsg(period=PERIOD):
    """Close IHSG harian. Yahoo kadang melewatkan satu hari di data harian ^JKSE (mis. 21 Okt 2026);
    hari yang hilang diisi dari close candle 1 jam terakhir hari itu."""
    import yfinance as yf
    t = yf.Ticker("^JKSE")
    h = t.history(period=period, auto_adjust=False)["Close"].dropna()
    h.index = h.index.tz_localize(None).normalize()
    try:
        hr = t.history(period="1mo", interval="1h")["Close"].dropna()
        hr.index = hr.index.tz_localize(None)
        daily = hr.groupby(hr.index.normalize()).last()
        for d, v in daily.items():
            if d not in h.index:
                h.loc[d] = v
    except Exception as e:  # noqa: BLE001
        print(f"  ! IHSG per jam gagal: {e}")
    return h.sort_index()


# ---------------------------------------------------------------- Indikator
def rma(x, n):
    """Wilder RMA gaya TradingView: benih SMA dari n nilai valid pertama."""
    a = np.asarray(x, float)
    out = np.full(len(a), np.nan)
    r, cnt, s = np.nan, 0, 0.0
    for i, v in enumerate(a):
        if np.isnan(r):
            if np.isnan(v):
                cnt, s = 0, 0.0
                continue
            cnt += 1
            s += v
            if cnt == n:
                r = s / n
                out[i] = r
        else:
            r = (r * (n - 1) + (0.0 if np.isnan(v) else v)) / n
            out[i] = r
    return out


def true_range(h):
    pc = h["Close"].shift(1)
    return pd.concat([h["High"] - h["Low"], (h["High"] - pc).abs(), (h["Low"] - pc).abs()], axis=1).max(axis=1)


def atr(h, n=ATR_LEN):
    """ATR Wilder; dikonfirmasi cocok dengan kolom atr situs (MARK 67,62): RMA dengan benih TR pertama."""
    return true_range(h).ewm(alpha=1 / n, adjust=False).mean()


def dmi(h, n=ADX_LEN):
    """DI+, DI-, ADX Wilder (ta.dmi TradingView)."""
    H, L, C = (h[k].to_numpy(float) for k in ("High", "Low", "Close"))
    upm = np.r_[np.nan, np.diff(H)]
    dnm = np.r_[np.nan, -np.diff(L)]
    pdm = np.where((upm > dnm) & (upm > 0), upm, 0.0)
    mdm = np.where((dnm > upm) & (dnm > 0), dnm, 0.0)
    pdm[0] = mdm[0] = np.nan
    pc = np.r_[np.nan, C[:-1]]
    tr = np.fmax(H - L, np.fmax(np.abs(H - pc), np.abs(L - pc)))
    tr[0] = np.nan
    t = rma(tr, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = 100 * rma(pdm, n) / t
        m = 100 * rma(mdm, n) / t
        s = p + m
        dx = 100 * np.abs(p - m) / np.where(s == 0, 1, s)
    return p, m, rma(dx, n)


def percentrank(x, n=PRANK_LEN):
    """ta.percentrank: % dari n nilai SEBELUMNYA yang <= nilai sekarang."""
    a = np.asarray(x, float)
    out = np.full(len(a), np.nan)
    if len(a) <= n:
        return out
    w = np.lib.stride_tricks.sliding_window_view(a, n + 1)
    with np.errstate(invalid="ignore"):
        v = (w[:, :n] <= w[:, n:]).sum(axis=1) / n * 100
    v[np.isnan(w).any(axis=1)] = np.nan
    out[n:] = v
    return out


# ---------------------------------------------------------------- Pola candle
def pattern_flags(df):
    """DataFrame boolean 7 pola bullish per candle. Definisi disimpulkan dari contoh & jumlah pola situs
    (21 Okt 2026), tanpa filter tren SMA50 seperti skrip "All Candlestick Patterns" TradingView:
      Engulfing  : kemarin merah, hari ini hijau, open <= close kemarin, close >= open kemarin, badan lebih besar
      Hammer     : bayangan bawah >= 2x badan, bayangan atas <= 0,5x badan (badan boleh merah)
      Inv. Hammer: hijau setelah candle merah, bayangan atas >= 2x badan, bawah <= 0,5x badan, badan >= 10% rentang
      Piercing   : kemarin merah, open < low kemarin, close di atas tengah badan kemarin tapi < open kemarin
      Harami     : kemarin merah, badan hijau hari ini di dalam badan kemarin (tegas, open > close kemarin)
      Morning St.: H-2 merah, H-1 badan < 0,5x badan H-2 dan di bawah badan H-2, hari ini hijau tutup > tengah H-2
      Marubozu   : hijau, badan >= 85% rentang"""
    O, H, L, C = (df[k].astype(float) for k in ("Open", "High", "Low", "Close"))
    bh, bl = np.maximum(O, C), np.minimum(O, C)
    body = bh - bl
    rng = H - L
    ups, dns = H - bh, bl - L
    white, black = C > O, C < O
    mid = bl + body / 2
    s = lambda x, k=1: x.shift(k)  # noqa: E731
    f = {}
    f["Bullish Engulfing"] = white & s(black) & (O <= s(C)) & (C >= s(O)) & (body > s(body))
    f["Hammer"] = (rng > 0) & (body > 0) & (dns >= 2 * body) & (ups <= 0.5 * body)
    f["Inverted Hammer"] = (white & s(black) & (ups >= 2 * body) & (dns <= 0.5 * body)
                            & (body >= 0.1 * rng))
    f["Piercing Line"] = white & s(black) & (O < s(L)) & (C > s(mid)) & (C < s(O))
    f["Bullish Harami"] = white & s(black) & (O > s(C)) & (C < s(O))
    f["Morning Star"] = (s(black, 2) & (s(body) < 0.5 * s(body, 2)) & (s(bh) <= s(bl, 2)) & white
                         & (C > s(mid, 2)))
    f["Bullish Marubozu"] = white & (rng > 0) & (body >= 0.85 * rng)
    return pd.DataFrame(f).fillna(False).astype(bool)[PATTERNS_ORDER]


# urutan prioritas bila satu candle cocok beberapa pola
PATTERNS_ORDER = ["Morning Star", "Bullish Engulfing", "Piercing Line", "Hammer", "Inverted Hammer",
                  "Bullish Harami", "Bullish Marubozu"]


def pattern_series(df):
    f = pattern_flags(df)
    arr = f.to_numpy()
    names = np.array(PATTERNS_ORDER, dtype=object)
    first = arr.argmax(axis=1)
    out = np.where(arr.any(axis=1), names[first], None)
    return pd.Series(out, index=df.index, dtype=object)


def detect_pattern(df):
    """Nama pola candle bullish pada baris terakhir `df` (kolom Open/High/Low/Close), atau None.
    Dipakai juga oleh alert.py / live.py."""
    if df is None or len(df) == 0:
        return None
    return pattern_series(df.tail(5)).iloc[-1]


# ---------------------------------------------------------------- Per saham
def indicators(h, ih):
    """Semua deret indikator untuk satu saham (indeks = tanggal bursa saham itu)."""
    C, V = h["Close"], h["Volume"]
    i = ih.reindex(C.index).ffill()
    a = atr(h)
    ret = (C / C.shift(RET_LEN) - 1) * 100
    raw = ret - (i / i.shift(RET_LEN) - 1) * 100
    rl = C / i
    rm = rl.rolling(RL_MA).mean()
    vavg = V.shift(1).rolling(VOL_AVG).mean()
    dip, dim, adx = dmi(h)
    x = pd.DataFrame({
        "p1": C / C.rolling(SMA_P1).mean(),
        "p2": (C / C.shift(P2_LEN)) / (i / i.shift(P2_LEN)),
        "p3": a / C * 100,
        "atr": a, "ret": ret, "raw": raw,
        "rs": percentrank(raw.to_numpy()),
        "rl": rl, "rm": rm,
        "vavg": vavg, "vr": V / vavg.replace(0, np.nan),
        "value": (C * V).rolling(VALUE_AVG).mean(),
        "ext": (C - C.ewm(span=EXT_EMA, adjust=False).mean()) / a,
        "dip": dip, "dim": dim, "adx": adx,
    }, index=C.index)
    up_day = C >= C.shift(1)
    x["rs_high"] = rl >= rl.rolling(RS_HIGH_LEN, min_periods=RS_HIGH_LEN).max()
    price_high = C >= C.rolling(RS_HIGH_LEN, min_periods=1).max()
    x["rs_lead"] = x["rs_high"] & ~price_high & up_day
    x["rs_quality"] = x["rs_high"] & (C > C.shift(1)) & (V >= QUALITY_VOL * vavg) & (x["value"] >= LIQUID_IDR)
    above = rl > rm
    x["rs_above"] = above
    prev_above = above.shift(1)
    valid = rm.notna() & rm.shift(1).notna()
    cross = pd.Series([None] * len(x), index=x.index, dtype=object)
    cross[valid & above & (prev_above == False)] = "Up"  # noqa: E712
    cross[valid & ~above & (prev_above == True)] = "Down"  # noqa: E712
    x["cross"] = cross
    x["pattern"] = pattern_series(h)
    return x


def fixed_trade(h, d, entry, sl, tp, buy_stop=False):
    """Posisi SL/TP tetap setelah candle trigger `d`. buy_stop: order beli bersyarat (N-candle).
    Return dict status/exit/date/pl. SL & TP di candle yang sama -> SL dulu."""
    O, H, L, C = (h[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    n = len(h)
    filled = not buy_stop
    px = entry
    for t in range(d + 1, n):
        if not filled:
            if H[t] >= entry:
                filled = True
                px = max(O[t], entry)
                if L[t] <= sl:          # hari terisi langsung jatuh ke SL (konservatif)
                    return {"st": "Kena SL", "exit": sl, "date": h.index[t], "px": px}
            continue
        if L[t] <= sl:
            return {"st": "Kena SL", "exit": min(O[t], sl), "date": h.index[t], "px": px}
        if H[t] >= tp:
            return {"st": "Kena TP", "exit": max(O[t], tp), "date": h.index[t], "px": px}
    return {"st": "Berjalan" if filled else "Belum terisi", "exit": None, "date": None, "px": px if filled else None}


def trail_trade(h, d, entry, sl, buy_stop=False):
    """Trailing stop: stop awal SL, naik mengikuti high tertinggi sejak entry dikurangi risiko awal,
    tidak pernah turun, tanpa TP. Kenaikan stop dari high hari ini berlaku mulai candle berikutnya."""
    O, H, L, C = (h[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    n = len(h)
    risk = entry - sl
    stop = sl
    filled = not buy_stop
    hh = -np.inf                    # high candle trigger sendiri tidak ikut (entry di harga tutupnya)
    px = entry
    for t in range(d + 1, n):
        if not filled:
            if H[t] < entry:
                continue
            filled = True
            px = max(O[t], entry)
            hh = H[t]
            if L[t] <= stop:
                return {"st": "Kena trailing", "stop": stop, "exit": stop, "date": h.index[t], "px": px}
            stop = max(stop, vcp.down(hh - risk))
            continue
        if L[t] <= stop:
            return {"st": "Kena trailing", "stop": stop, "exit": min(O[t], stop), "date": h.index[t], "px": px}
        hh = max(hh, H[t])
        stop = max(stop, vcp.down(hh - risk))
    if not filled:
        return {"st": "Belum terisi", "stop": None, "exit": None, "date": None, "px": None}
    st = "Kemungkinan sudah kena" if C[-1] < stop else "Berjalan"
    return {"st": st, "stop": stop, "exit": None, "date": None, "px": px}


def atr_levels(entry, a):
    sl = vcp.down(entry - ATR_SL * a)
    tp = vcp.up(entry + ATR_TP * a)
    return entry, sl, tp


def n_levels(h, t):
    lo = max(0, t - N_BARS + 1)
    e = float(h["High"].iloc[lo:t + 1].max())
    sl = float(h["Low"].iloc[lo:t + 1].min())
    return e, sl, vcp.up(e + N_RR * (e - sl))


def lot(entry, sl):
    r = entry - sl
    return int(RISK_IDR // (r * 100)) if r > 0 else None


def run_state(h, x, setup):
    """Mesin keadaan watchlist -> jendela -> trigger. Return (indeks watchlist, indeks trigger, watchlist aktif)."""
    n = len(h)
    O, C = h["Open"].to_numpy(float), h["Close"].to_numpy(float)
    rs, vr = x["rs"].to_numpy(float), x["vr"].to_numpy(float)
    pat = x["pattern"].to_numpy(object)
    trig_ok = (C > O) & (vr >= VOL_X) & (pat != None) & (rs >= RS_MIN)  # noqa: E711
    watches, triggers = [], []
    watch = None
    for t in range(n):
        # watchlist = hari pertama setup valid setelah hari tidak valid. Watchlist baru menggantikan jendela
        # lama (candle watchlist sendiri tidak bisa trigger) dan tetap boleh terbentuk walau posisi sebelumnya
        # masih berjalan (cocok dengan data situs).
        if setup[t] and (t == 0 or not setup[t - 1]):
            watch = t
            watches.append(t)
            continue
        if watch is not None:
            k = t - watch
            if 1 <= k <= WATCH_DAYS and trig_ok[t]:
                triggers.append(t)
                watch = None
            elif k >= WATCH_DAYS:
                watch = None
    return watches, triggers, watch


def last_lead_in_window(lead, watches, triggers, n):
    best = None
    trig = sorted(triggers)
    for k, w in enumerate(watches):
        end = min(w + WATCH_DAYS, n - 1)
        if k + 1 < len(watches):
            end = min(end, watches[k + 1] - 1)
        tr = [d for d in trig if w < d <= end]
        if tr:
            end = tr[0]
        hit = np.flatnonzero(lead[w:end + 1])
        if len(hit):
            best = w + int(hit[-1]) if best is None else max(best, w + int(hit[-1]))
    return best


# ---------------------------------------------------------------- Hitung
def compute(hist, ihsg, session="close", meta=None, now=None):
    """hist: {KODE: DataFrame[Open,High,Low,Close,Volume]} berindeks tanggal; ihsg: Series close IHSG.
    Return objek JSON pullback (belum ditulis ke disk). Kunci tambahan "_charts": {KODE: data grafik}."""
    meta = meta or {}
    now = now or dt.datetime.now(WIB)
    ih = ihsg.copy()
    ih.index = pd.to_datetime(ih.index).tz_localize(None).normalize() if getattr(ih.index, "tz", None) else \
        pd.to_datetime(ih.index).normalize()
    ih = ih[~ih.index.duplicated(keep="last")].sort_index().dropna()

    frames = {}
    for c, h in hist.items():
        h = h[["Open", "High", "Low", "Close", "Volume"]].copy()
        idx = pd.to_datetime(h.index)
        h.index = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
        h = h[~h.index.duplicated(keep="last")].sort_index()
        h = h.dropna(subset=["Close"])
        h = h[h["Close"] > 0]
        h["Volume"] = h["Volume"].fillna(0)
        for k in ("Open", "High", "Low"):
            h[k] = h[k].fillna(h["Close"])
        if len(h) >= 2:
            frames[c] = h
    if not frames:
        raise ValueError("tidak ada data saham")
    as_of = max(h.index[-1] for h in frames.values())
    ih = ih[ih.index <= as_of]

    X = {c: indicators(h, ih) for c, h in frames.items()}
    # Ranking 3 Bulan: persentil ret63 lintas saham per hari
    R = pd.DataFrame({c: x["ret"] for c, x in X.items()})
    R3 = R.rank(axis=1, pct=True) * 100

    syariah, hsc = load_codes("syariah.json"), load_codes("hsc.json")
    ih_ma50 = ih.rolling(50).mean()
    s1 = session == "s1"
    rows, charts = [], {}
    for c, h in frames.items():
        x = X[c]
        x["r3"] = R3[c].reindex(x.index)
        n = len(h)
        t = n - 1
        C = h["Close"].to_numpy(float)
        setup = ((x["p1"] < P1_MAX) & (x["p2"] > P2_MIN) & (x["p3"] > P3_MIN) & (x["r3"] >= RS3M_MIN)).to_numpy()
        enough = n >= MIN_BARS and ok(x["rs"].iloc[-1])
        watches, triggers, watch = run_state(h, x, setup) if enough else ([], [], None)
        last = x.iloc[-1]
        trading_today = h.index[-1] == as_of and h["Volume"].iloc[-1] > 0
        traded = h.index[h["Volume"] > 0]

        # status
        status, signal_d, watch_left = None, None, None
        if not enough:
            status = "Riwayat belum cukup"
        elif triggers and t - triggers[-1] <= ENTRY_DAYS:
            signal_d = triggers[-1]
            status = "Entry hari ini" if signal_d == t else "Entry baru"
        elif watch is not None and t - watch < WATCH_DAYS:
            status = "Menunggu trigger"
            # Sesi 1: candle hari ini belum tutup, jadi hari ini ikut dihitung (1 = hari ini terakhir)
            watch_left = WATCH_DAYS - (t - watch) + (1 if s1 and t > watch else 0)
        elif s1 and watches and t - watches[-1] == WATCH_DAYS and not any(g > watches[-1] for g in triggers):
            status, watch_left = "Menunggu trigger", 1
        elif setup[t]:
            status = "Setup valid"
        else:
            status = "Tidak ada sinyal"

        # level: dari candle trigger, atau candle terakhir sebagai gambaran
        lv_t = signal_d if signal_d is not None else t
        a_lv = float(x["atr"].iloc[lv_t])
        ae, asl, atp = atr_levels(C[lv_t], a_lv)
        ne, nsl, ntp = n_levels(h, lv_t)

        row = {
            "code": c, "name": meta.get(c, c), "board": None, "status": status,
            "signal_date": ds(h.index[signal_d]) if signal_d is not None else None,
            "days_since_signal": (t - signal_d) if signal_d is not None else None,
            "watch_days_left": watch_left,
            "last_trade": ds(traded[-1]) if len(traded) else None,
            "no_trade_today": not trading_today,
            "close": num(C[-1]),
            "chg": rn((C[-1] / C[-2] - 1) * 100) if n > 1 else None,
            "p1": rn(last["p1"], 3), "p2": rn(last["p2"], 3), "p3": rn(last["p3"], 2),
            "p1_ok": bool(last["p1"] < P1_MAX), "p2_ok": bool(last["p2"] > P2_MIN), "p3_ok": bool(last["p3"] > P3_MIN),
            "rs_rating": int(math.floor(last["rs"] + 0.5)) if enough else None,
            "raw_mom": rn(last["raw"], 1),
            "rs_ok": bool(enough and last["rs"] >= RS_MIN),
            "ret3m": rn(last["ret"], 2), "rs3m_x": rn(last["r3"], 1),
            "rs3m_ok": bool(ok(last["r3"]) and last["r3"] >= RS3M_MIN),
            "rs_above_ma": bool(last["rs_above"]), "rs_lead": bool(last["rs_lead"]),
            "rs_high": bool(last["rs_high"]), "rs_quality": bool(last["rs_quality"]),
            "rs_cross": last["cross"],
            "adx": rn(last["adx"], 1), "di_plus": rn(last["dip"], 1), "di_minus": rn(last["dim"], 1),
            "trend": trend_label(last["adx"], last["dip"], last["dim"]),
            "value_avg": inum(last["value"]), "value_today": inum(C[-1] * h["Volume"].iloc[-1]),
            "vol_avg": inum(last["vavg"]), "vol_today": int(h["Volume"].iloc[-1]),
            "vol_ratio": rn(last["vr"], 2),
            "liquid": bool(ok(last["value"]) and last["value"] >= LIQUID_IDR),
            "ext_atr": rn(last["ext"], 2), "extended": bool(ok(last["ext"]) and last["ext"] > EXT_MAX),
            "pattern": x["pattern"].iloc[lv_t],
            "trig_lead": bool(x["rs_lead"].iloc[signal_d]) if signal_d is not None else None,
            "lead_date": None, "lead_days_ago": None, "lead_close": None,
            "atr": rn(a_lv, 2), "atr_entry": num(ae), "atr_sl": num(asl), "atr_tp": num(atp),
            "n_entry": num(ne), "n_sl": num(nsl), "n_tp": num(ntp),
            "atr_lot": lot(ae, asl), "n_lot": lot(ne, nsl),
            "atr_trade": None, "n_trade": None,
            "trig_vol_x": rn(x["vr"].iloc[signal_d], 2) if signal_d is not None else None,
            "trig_rs": int(math.floor(x["rs"].iloc[signal_d] + 0.5)) if signal_d is not None else None,
            "rewatch_date": None, "rewatch_days_left": None,
            "atr_exit": None, "atr_exit_date": None, "atr_pl": None,
            "n_exit": None, "n_exit_date": None, "n_pl": None,
            "atr_trail": None, "atr_trail_out": None, "atr_trail_exit": None, "atr_trail_date": None,
            "atr_trail_pl": None,
            "n_trail": None, "n_trail_out": None, "n_trail_exit": None, "n_trail_date": None, "n_trail_pl": None,
            "syariah": c in syariah, "hsc": c in hsc,
        }
        # Momentum Duluan terakhir yang terjadi selama jendela watchlist (watchlist s.d. trigger/akhir jendela)
        li = last_lead_in_window(x["rs_lead"].to_numpy(bool), watches, triggers, n)
        if li is not None and t - li <= LEAD_RECENT:
            row.update(lead_date=ds(h.index[li]), lead_days_ago=t - li, lead_close=num(C[li]))

        if signal_d is not None:
            d = signal_d
            for pre, (e, sl, tp, bs) in (("atr", (ae, asl, atp, False)), ("n", (ne, nsl, ntp, True))):
                fx = fixed_trade(h, d, e, sl, tp, buy_stop=bs)
                row[f"{pre}_trade"] = fx["st"]
                if fx["exit"] is not None:
                    row[f"{pre}_exit"] = num(fx["exit"])
                    row[f"{pre}_exit_date"] = ds(fx["date"])
                    row[f"{pre}_pl"] = rn((fx["exit"] / fx["px"] - 1) * 100)
                elif fx["px"] is not None:
                    row[f"{pre}_pl"] = rn((C[-1] / fx["px"] - 1) * 100)
                tr = trail_trade(h, d, e, sl, buy_stop=bs)
                row[f"{pre}_trail"] = num(tr["stop"])
                row[f"{pre}_trail_out"] = tr["st"]
                if tr["exit"] is not None:
                    row[f"{pre}_trail_exit"] = num(tr["exit"])
                    row[f"{pre}_trail_date"] = ds(tr["date"])
                    row[f"{pre}_trail_pl"] = rn((tr["exit"] / tr["px"] - 1) * 100)
                elif tr["px"] is not None:
                    row[f"{pre}_trail_pl"] = rn((C[-1] / tr["px"] - 1) * 100)
            # watchlist baru setelah posisi (SL/TP tetap metode ATR) selesai
            ex = row["atr_exit_date"]
            later = [w for w in watches if ex and ds(h.index[w]) > ex]
            if later:
                w = later[-1]
                row["rewatch_date"] = ds(h.index[w])
                left = WATCH_DAYS - (t - w) + (1 if s1 and t > w else 0)
                row["rewatch_days_left"] = left if left > 0 and not any(g > w for g in triggers) else None
        rows.append(row)

        if status != "Tidak ada sinyal":
            charts[c] = chart_data(c, h, x, watches, triggers)

    rows.sort(key=lambda r: -(r["rs3m_x"] if r["rs3m_x"] is not None else -1))
    counts = {s: 0 for s in STATUSES}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    counts = {k: v for k, v in counts.items() if v or k in STATUSES[:2] + STATUSES[5:]}
    pc = {p: sum(1 for r in rows if r["pattern"] == p) for p in PATTERNS}
    ic = float(ih.iloc[-1])
    im = float(ih_ma50.iloc[-1]) if ok(ih_ma50.iloc[-1]) else None
    market = {
        "as_of": ds(as_of), "session": session, "session_label": SESSION_LABEL.get(session, session),
        "generated_at": now.strftime("%Y-%m-%d %H:%M WIB"),
        "ihsg_close": rn(ic), "ihsg_ma50": rn(im), "ihsg_dist": rn((ic / im - 1) * 100) if im else None,
        "regime": "Bullish" if im and ic > im else "Bearish",
        "universe": len(rows),
        "lead_count": sum(1 for r in rows if r["rs_lead"]),
        "patterns": pc,
    }
    return {"market": market, "counts": counts, "rows": rows, "_charts": charts}


def trend_label(adx, dip, dim):
    if not ok(adx):
        return None
    s = "Lemah" if adx < 25 else ("Kuat" if adx < 40 else "Sangat kuat")
    return f"{s}, {'Naik' if dip > dim else 'Turun'}"


def chart_data(code, h, x, watches, triggers):
    k = min(len(h), CHART_BARS)
    t0 = len(h) - k
    tail = h.iloc[t0:]
    xt = x.iloc[t0:]
    bars = []
    for (d, r), (_, y) in zip(tail.iterrows(), xt.iterrows()):
        bars.append([ds(d), num(r["Open"]), num(r["High"]), num(r["Low"]), num(r["Close"]), int(r["Volume"]),
                     int(math.floor(y["rs"] + 0.5)) if ok(y["rs"]) else None, rn(y["r3"], 1),
                     rn(y["rl"], 6), rn(y["rm"], 6)])
    dates = lambda idx: [ds(h.index[i]) for i in idx if i >= t0]  # noqa: E731
    flag = lambda col: [ds(d) for d, v in xt[col].items() if v]  # noqa: E731
    return {"code": code, "bars": bars,
            "marks": {"watch": dates(watches), "trigger": dates(triggers), "lead": flag("rs_lead"),
                      "rs_high": flag("rs_high"),
                      "rs_cross": [ds(d) for d, v in xt["cross"].items() if v]}}


# ---------------------------------------------------------------- Main
def write(payload, session):
    SITE.mkdir(parents=True, exist_ok=True)
    charts = payload.pop("_charts", {})
    out = SITE / ("pullback_s1.json" if session == "s1" else "pullback.json")
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(out)
    CHART_DIR.mkdir(exist_ok=True)
    if session == "close":   # grafik dipakai bersama kedua snapshot; yang usang dibersihkan saat penutupan
        for f in CHART_DIR.glob("*.json"):
            if f.stem not in charts:
                f.unlink()
    for c, data in charts.items():
        (CHART_DIR / f"{c}.json").write_text(json.dumps(data, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    return out, len(charts)


def main():
    session = "s1" if any(a.lower() == "s1" for a in sys.argv[1:]) else "close"
    meta = load_universe()
    codes = list(meta)
    print(f"Pullback ({SESSION_LABEL[session]}): memindai {len(codes)} saham...")
    ihsg = download_ihsg()
    hist = download(codes)
    print(f"  data tersedia: {len(hist)} saham")
    now = dt.datetime.now(WIB)
    if session == "close" and now.time() < CLOSE_READY:
        # Snapshot Penutupan dijalankan saat bursa masih buka: buang candle hari ini yang belum tutup
        today = pd.Timestamp(now.date())
        cut = lambda df: df[pd.to_datetime(df.index).tz_localize(None).normalize() < today]  # noqa: E731
        hist = {c: cut(h) for c, h in hist.items()}
        ihsg = cut(ihsg)
        print("  bursa belum tutup: candle hari ini diabaikan untuk snapshot Penutupan")
    payload = compute(hist, ihsg, session=session, meta=meta)
    out, nch = write(payload, session)
    m = payload["market"]
    print(f"Tersimpan: {out} ({len(payload['rows'])} saham, {nch} grafik) · data {m['as_of']} · "
          f"IHSG {m['ihsg_close']} vs MA50 {m['ihsg_ma50']} ({m['ihsg_dist']}%) {m['regime']}")
    print("Status:", payload["counts"])
    for r in payload["rows"]:
        if r["status"] in ("Entry hari ini", "Entry baru"):
            print(f"  {r['code']:5} {r['status']:<15} {r['signal_date']} {r['pattern'] or '-':<18} "
                  f"entry {r['atr_entry']} SL {r['atr_sl']} TP {r['atr_tp']} · {r['atr_trade']}")


if __name__ == "__main__":
    main()
