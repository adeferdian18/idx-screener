"""
Fase 4 (A4): High Growth Momentum (HGM) dan katalis untuk kandidat momentum.

Syarat modul: laba (EPS) kuartalan tumbuh > 20% YoY, penjualan > 15% YoY, margin laba melebar.
Data kuartalan Yahoo untuk saham BEI sering bolong (kuartal hilang, EPS kosong), jadi:
  - laba bersih dipakai sebagai pengganti EPS (jumlah saham jarang berubah antar kuartal);
  - kuartal terbaru dibandingkan dengan kuartal yang sama tahun lalu berdasarkan TANGGAL, bukan urutan kolom;
  - hasil disimpan di data/hgm_cache.json dan diperbarui paling cepat tiap 7 hari (laporan kuartalan jarang berubah).
Katalis diambil dari aksi korporasi yang sudah dipindai corpact.py (docs/data/corporate_actions.json).
"""

import json
import math
import time
import datetime as dt
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE = Path(__file__).parent
CACHE = BASE / "data" / "hgm_cache.json"
ACTIONS = BASE / "docs" / "data" / "corporate_actions.json"
REFRESH_DAYS = 7
EPS_MIN, SALES_MIN = 0.20, 0.15


def ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def _row(q, names):
    for n in names:
        if n in q.index:
            return q.loc[n]
    return None


def _yoy(series, d):
    """Nilai kuartal `d` dibanding kuartal dengan bulan yang sama setahun sebelumnya."""
    prev = [c for c in series.index if c.year == d.year - 1 and c.month == d.month]
    if not prev:
        return None, None
    a, b = series.get(d), series.get(prev[0])
    if not ok(a) or not ok(b) or b == 0:
        return None, None
    # dari rugi ke laba tidak bisa dihitung sebagai persen; tandai sebagai perbaikan besar
    return (float(a) / float(b) - 1 if b > 0 else (9.99 if a > 0 else None)), prev[0]


def compute(code):
    q = yf.Ticker(f"{code}.JK").quarterly_income_stmt
    if q is None or q.empty:
        return {"status": "data kurang", "skor": None}
    q = q.reindex(sorted(q.columns, reverse=True), axis=1)
    ni = _row(q, ["Net Income Common Stockholders", "Net Income"])
    rev = _row(q, ["Total Revenue", "Operating Revenue"])
    if ni is None or rev is None:
        return {"status": "data kurang", "skor": None}
    cols = [c for c in q.columns if ok(ni.get(c)) and ok(rev.get(c))]
    if not cols:
        return {"status": "data kurang", "skor": None}
    d0 = cols[0]
    eps_g, base = _yoy(ni, d0)
    sales_g, _ = _yoy(rev, d0)
    if eps_g is None and sales_g is None:
        return {"status": "data kurang", "skor": None, "kuartal": f"{d0:%Y-%m}"}
    m0 = float(ni[d0]) / float(rev[d0]) if rev[d0] else None
    m1 = float(ni[base]) / float(rev[base]) if base is not None and ok(rev.get(base)) and rev[base] else None
    # akselerasi: pertumbuhan laba kuartal ini lebih tinggi dari kuartal sebelumnya
    prev_cols = [c for c in cols[1:] if (d0 - c).days < 200]
    acc = None
    if prev_cols and eps_g is not None:
        g1, _ = _yoy(ni, prev_cols[0])
        acc = bool(eps_g > g1) if g1 is not None else None
    checks = {
        "laba": bool(eps_g is not None and eps_g > EPS_MIN),
        "penjualan": bool(sales_g is not None and sales_g > SALES_MIN),
        "margin": bool(m0 is not None and m1 is not None and m0 > m1),
    }
    skor = sum(checks.values())
    return {
        "status": "kuat" if skor == 3 else "sebagian" if skor >= 1 else "lemah",
        "skor": skor, "kuartal": f"{d0:%Y-%m}",
        "laba_yoy": round(eps_g, 4) if eps_g is not None else None,
        "penjualan_yoy": round(sales_g, 4) if sales_g is not None else None,
        "margin": round(m0, 4) if m0 is not None else None,
        "margin_lalu": round(m1, 4) if m1 is not None else None,
        "akselerasi": acc, "cek": checks,
    }


def load_cache():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def hgm_for(codes):
    """HGM untuk daftar kode; memakai cache kalau umurnya < REFRESH_DAYS."""
    cache = load_cache()
    today = dt.date.today()
    out = {}
    for c in codes:
        hit = cache.get(c)
        if hit and (today - dt.date.fromisoformat(hit["diambil"])).days < REFRESH_DAYS:
            out[c] = hit
            continue
        try:
            res = compute(c)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {c}: HGM gagal ({e})")
            res = {"status": "data kurang", "skor": None}
        res["diambil"] = today.isoformat()
        cache[c] = out[c] = res
        time.sleep(0.5)
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return out


def katalis_for(codes, days=30):
    """Aksi korporasi 30 hari terakhir per kode (buyback, dividen, akuisisi, rights issue, dll.)."""
    try:
        evs = json.loads(ACTIONS.read_text(encoding="utf-8")).get("events", [])
    except (OSError, ValueError):
        return {}
    cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    out = {}
    want = set(codes)
    for e in evs:
        if e.get("code") not in want:
            continue
        try:
            when = pd.Timestamp(e.get("date"))
            when = when.tz_localize("UTC") if when.tzinfo is None else when
        except (ValueError, TypeError):
            continue
        if when < cut:
            continue
        out.setdefault(e["code"], []).append({
            "jenis": e.get("label"), "judul": e.get("title"), "tgl": f"{when:%Y-%m-%d}",
            "sinyal": e.get("signal"), "vonis": e.get("verdict"),
        })
    return out
