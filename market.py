"""
Ambil harga terkini semua saham di tickers.txt + IHSG, simpan ke docs/data/quotes.json.
Dijalankan tiap 15 menit saat jam bursa oleh GitHub Actions.
Sumber: Yahoo Finance (tertunda sekitar 10-15 menit dari bursa).
"""

import json
import math
import datetime as dt
from pathlib import Path

import yfinance as yf

BASE = Path(__file__).parent
OUT = BASE / "docs" / "data" / "quotes.json"
WIB = dt.timezone(dt.timedelta(hours=7))


def clean(x):
    try:
        x = float(x)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def load_tickers():
    out = []
    for ln in (BASE / "tickers.txt").read_text().splitlines():
        ln = ln.strip().upper()
        if ln and not ln.startswith("#") and ln not in out:
            out.append(ln)
    return out


def main():
    codes = load_tickers()
    symbols = [f"{c}.JK" for c in codes]
    df = yf.download(symbols, period="5d", interval="1d", group_by="ticker",
                     auto_adjust=False, threads=True, progress=False)
    stocks = {}
    for c, s in zip(codes, symbols):
        try:
            d = df[s].dropna(subset=["Close"])
            if len(d) < 2:
                continue
            last, prev = clean(d["Close"].iloc[-1]), clean(d["Close"].iloc[-2])
            vol = clean(d["Volume"].iloc[-1]) or 0
            stocks[c] = {
                "last": last, "prev": prev,
                "chg": (last / prev - 1) if last and prev else None,
                "high": clean(d["High"].iloc[-1]), "low": clean(d["Low"].iloc[-1]),
                "volume": vol, "value": (last or 0) * vol,
                "date": d.index[-1].strftime("%Y-%m-%d"),
            }
        except Exception as e:  # noqa: BLE001
            print(f"! {c}: {e}")

    ihsg = {}
    try:
        y = yf.Ticker("^JKSE").history(period="1y")["Close"].dropna()
        intra = yf.Ticker("^JKSE").history(period="1d", interval="5m")["Close"].dropna()
        last = float(intra.iloc[-1]) if len(intra) else float(y.iloc[-1])
        prev = float(y.iloc[-2]) if y.index[-1].date() == dt.datetime.now(WIB).date() else float(y.iloc[-1])
        ihsg = {
            "last": last, "prev": prev, "chg": last / prev - 1,
            "peak52": float(y.max()), "low52": float(y.min()),
            "intraday": [round(float(v), 2) for v in intra.tolist()],
            "year": [round(float(v), 2) for v in y.tolist()[-120:]],
        }
    except Exception as e:  # noqa: BLE001
        print("! IHSG:", e)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated": dt.datetime.now(WIB).isoformat(timespec="minutes"),
        "source": "Yahoo Finance (tertunda ±15 menit)",
        "ihsg": ihsg, "stocks": stocks,
    }, ensure_ascii=False))
    print(f"Tersimpan {len(stocks)} harga saham ke {OUT}")


if __name__ == "__main__":
    main()
