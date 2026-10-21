"""
Daftar semua saham biasa yang tercatat di BEI, disimpan ke data/universe.json.
RS Rating adalah persentil terhadap SELURUH bursa, jadi momentum.py butuh universe lengkap,
bukan hanya tickers.txt.

Sumber: endpoint scanner publik TradingView (situs idx.co.id diblokir Cloudflare untuk bot).
Kalau gagal, file lama dipertahankan.
"""

import json
import datetime as dt
from pathlib import Path

import requests

BASE = Path(__file__).parent
OUT = BASE / "data" / "universe.json"
WIB = dt.timezone(dt.timedelta(hours=7))
SCAN_URL = "https://scanner.tradingview.com/indonesia/scan"


def fetch():
    body = {
        "columns": ["name", "description", "sector", "subtype"],
        "filter": [{"left": "type", "operation": "equal", "right": "stock"},
                   {"left": "exchange", "operation": "equal", "right": "IDX"}],
        "range": [0, 3000],
        "markets": ["indonesia"],
    }
    r = requests.post(SCAN_URL, json=body, timeout=30, headers={"User-Agent": "Mozilla/5.0 idx-screener"})
    r.raise_for_status()
    rows = []
    for x in r.json().get("data", []):
        code, name, sector, subtype = x["d"]
        if subtype != "common" or not code or not code.isalpha():
            continue
        rows.append({"kode": code.upper(), "nama": name, "sektor": sector or "-"})
    return sorted(rows, key=lambda r: r["kode"])


def main():
    OUT.parent.mkdir(exist_ok=True)
    try:
        rows = fetch()
        if len(rows) < 500:  # respons janggal, jangan timpa daftar lama
            raise ValueError(f"hanya {len(rows)} saham")
    except Exception as e:  # noqa: BLE001
        print(f"! Gagal ambil universe ({e}); memakai file lama.")
        return
    OUT.write_text(json.dumps({"updated": dt.datetime.now(WIB).isoformat(timespec="minutes"),
                               "rows": rows}, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Tersimpan: {OUT} ({len(rows)} saham)")


if __name__ == "__main__":
    main()
