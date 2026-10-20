"""
IDX Fundamental Screener
========================
Memindai saham BEI setiap hari, menilai kesehatan fundamental dengan metode
para fundamentalis klasik, lalu mengirim peringkat ke Telegram (dan opsional WhatsApp).

Metode yang dipakai:
  - Piotroski F-Score (Joseph Piotroski)      -> kualitas & tren perbaikan bisnis
  - Altman Z''-Score emerging market           -> risiko kebangkrutan
  - Magic Formula (Joel Greenblatt)            -> bisnis bagus di harga murah
  - Graham Number & kriteria defensif (Benjamin Graham) -> margin of safety
  - Filter kualitas ala Buffett                -> ROE tinggi, utang rendah, FCF positif
  - PEG Ratio (Peter Lynch)                    -> pertumbuhan vs harga
  - Diskon dari puncak 52 minggu               -> seberapa "merah" sahamnya

Bank/lembaga keuangan dinilai dengan rumus terpisah (Altman & Piotroski tidak cocok untuk bank).

Data: Yahoo Finance via yfinance (gratis, kadang telat/tidak lengkap untuk saham BEI).
Ini alat bantu riset, BUKAN rekomendasi beli/jual.
"""

import math
import os
import sys
import time
import datetime as dt
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

# ---------------------------------------------------------------- Pengaturan
MIN_AVG_VALUE_IDR = float(os.getenv("MIN_AVG_VALUE_IDR", 5e9))   # likuiditas min: Rp5 miliar/hari
TOP_N = int(os.getenv("TOP_N", 15))                                # jumlah saham di pesan
SLEEP_BETWEEN = float(os.getenv("SLEEP_BETWEEN", 1.0))             # jeda antar saham (hindari blokir Yahoo)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
FONNTE_TOKEN = os.getenv("FONNTE_TOKEN", "")                       # opsional, untuk WhatsApp
WA_TARGET = os.getenv("WA_TARGET", "")                             # nomor WA, contoh 6281234567890

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
WIB = dt.timezone(dt.timedelta(hours=7))

WEIGHTS = {"quality": 0.35, "safety": 0.25, "value": 0.25, "discount": 0.15}


# ---------------------------------------------------------------- Utilitas
def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def lin(x, bad, good):
    """Skala linear 0..1: nilai `bad` -> 0, nilai `good` -> 1 (arah bebas)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if good == bad:
        return 0.0
    return clamp((x - bad) / (good - bad))


def avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def get_row(df, names, col=0):
    """Ambil angka dari laporan keuangan yfinance; coba beberapa nama baris."""
    if df is None or df.empty or col >= df.shape[1]:
        return None
    for n in names:
        if n in df.index:
            v = df.loc[n].iloc[col]
            if ok(v):
                return float(v)
    return None


def safe_div(a, b):
    if not ok(a) or not ok(b) or b == 0:
        return None
    return a / b


# ---------------------------------------------------------------- Ambil data
def load_tickers():
    lines = (BASE / "tickers.txt").read_text().splitlines()
    out = []
    for ln in lines:
        ln = ln.strip().upper()
        if ln and not ln.startswith("#") and ln not in out:
            out.append(ln)
    return out


def fetch(code, retries=2):
    for attempt in range(retries + 1):
        try:
            t = yf.Ticker(f"{code}.JK")
            hist = t.history(period="1y", auto_adjust=False)
            if hist is None or hist.empty:
                raise ValueError("histori harga kosong")
            info = t.info or {}
            return {
                "info": info,
                "hist": hist,
                "inc": t.income_stmt,
                "bal": t.balance_sheet,
                "cf": t.cashflow,
            }
        except Exception as e:  # noqa: BLE001
            if attempt == retries:
                print(f"  ! {code}: gagal ambil data ({e})")
                return None
            time.sleep(3 * (attempt + 1))


# ---------------------------------------------------------------- Metode fundamentalis
def piotroski(inc, bal, cf):
    """Piotroski F-Score 0..9. Butuh 2 tahun laporan. Return (skor, jumlah_kriteria_terhitung)."""
    ni0, ni1 = get_row(inc, ["Net Income"], 0), get_row(inc, ["Net Income"], 1)
    ta0, ta1 = get_row(bal, ["Total Assets"], 0), get_row(bal, ["Total Assets"], 1)
    ta2 = get_row(bal, ["Total Assets"], 2) or ta1
    cfo0 = get_row(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], 0)
    ltd0 = get_row(bal, ["Long Term Debt"], 0) or 0.0
    ltd1 = get_row(bal, ["Long Term Debt"], 1) or 0.0
    ca0, ca1 = get_row(bal, ["Current Assets"], 0), get_row(bal, ["Current Assets"], 1)
    cl0, cl1 = get_row(bal, ["Current Liabilities"], 0), get_row(bal, ["Current Liabilities"], 1)
    sh_names = ["Ordinary Shares Number", "Share Issued"]
    sh0, sh1 = get_row(bal, sh_names, 0), get_row(bal, sh_names, 1)
    gp0, gp1 = get_row(inc, ["Gross Profit"], 0), get_row(inc, ["Gross Profit"], 1)
    rev0, rev1 = get_row(inc, ["Total Revenue"], 0), get_row(inc, ["Total Revenue"], 1)

    roa0, roa1 = safe_div(ni0, ta1), safe_div(ni1, ta2)
    checks = [
        roa0 > 0 if ok(roa0) else None,                                   # 1 ROA positif
        cfo0 > 0 if ok(cfo0) else None,                                   # 2 CFO positif
        roa0 > roa1 if ok(roa0) and ok(roa1) else None,                   # 3 ROA naik
        cfo0 > ni0 if ok(cfo0) and ok(ni0) else None,                     # 4 kualitas laba (accrual)
        (safe_div(ltd0, ta0) or 0) <= (safe_div(ltd1, ta1) or 0) if ok(ta0) and ok(ta1) else None,  # 5 leverage turun
        safe_div(ca0, cl0) > safe_div(ca1, cl1)
        if all(ok(x) for x in [safe_div(ca0, cl0), safe_div(ca1, cl1)]) else None,                 # 6 likuiditas naik
        sh0 <= sh1 * 1.001 if ok(sh0) and ok(sh1) else None,              # 7 tidak terbit saham baru
        safe_div(gp0, rev0) > safe_div(gp1, rev1)
        if all(ok(x) for x in [safe_div(gp0, rev0), safe_div(gp1, rev1)]) else None,               # 8 margin naik
        safe_div(rev0, ta1) > safe_div(rev1, ta2)
        if all(ok(x) for x in [safe_div(rev0, ta1), safe_div(rev1, ta2)]) else None,               # 9 asset turnover naik
    ]
    counted = [c for c in checks if c is not None]
    if len(counted) < 6:
        return None, len(counted)
    # skala ke 9 kalau ada kriteria yang datanya tidak tersedia
    return round(sum(counted) / len(counted) * 9, 1), len(counted)


def altman_z_em(inc, bal, info):
    """Altman Z''-Score versi emerging market. >2.6 aman, 1.1-2.6 abu-abu, <1.1 bahaya."""
    ta = get_row(bal, ["Total Assets"])
    wc = get_row(bal, ["Working Capital"])
    if not ok(wc):
        ca, cl = get_row(bal, ["Current Assets"]), get_row(bal, ["Current Liabilities"])
        wc = ca - cl if ok(ca) and ok(cl) else None
    re_ = get_row(bal, ["Retained Earnings"])
    ebit = get_row(inc, ["EBIT", "Operating Income"])
    eq = get_row(bal, ["Stockholders Equity", "Common Stock Equity"])
    tl = get_row(bal, ["Total Liabilities Net Minority Interest", "Total Liabilities"])
    if not all(ok(x) for x in [ta, wc, re_, ebit, eq, tl]) or ta == 0 or tl == 0:
        return None
    return 3.25 + 6.56 * wc / ta + 3.26 * re_ / ta + 6.72 * ebit / ta + 1.05 * eq / tl


def magic_formula_parts(inc, bal, info, fx=1.0):
    """Greenblatt: Earnings Yield = EBIT/EV, Return on Capital = EBIT/(NWC + aset tetap bersih).
    `fx` mengubah angka laporan keuangan ke IDR agar sebanding dengan kapitalisasi pasar."""
    ebit = get_row(inc, ["EBIT", "Operating Income"])
    ebit = ebit * fx if ok(ebit) else None
    mcap = info.get("marketCap")
    debt = (get_row(bal, ["Total Debt"]) or 0.0) * fx
    cash = (get_row(bal, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]) or 0.0) * fx
    ev = mcap + debt - cash if ok(mcap) else None
    ca, cl = get_row(bal, ["Current Assets"]), get_row(bal, ["Current Liabilities"])
    nppe = get_row(bal, ["Net PPE"])
    nppe = nppe * fx if ok(nppe) else None
    nwc = max((ca - cl) * fx - cash, 0) if ok(ca) and ok(cl) else None
    capital = (nwc or 0) + (nppe or 0) if ok(nwc) or ok(nppe) else None
    ey = safe_div(ebit, ev) if ok(ev) and ev > 0 else None
    roc = safe_div(ebit, capital) if ok(capital) and capital > 0 else None
    return ey, roc


_fx_cache = {"IDR": 1.0}


def fx_to_idr(ccy):
    """Kurs mata uang laporan keuangan -> IDR. Emiten batu bara/nikel/petrokimia (ITMG, ADRO, TPIA, ...)
    melapor dalam USD sementara harga sahamnya dalam IDR; tanpa konversi PBV, Graham dan EV jadi kacau."""
    ccy = (ccy or "IDR").upper()
    if ccy not in _fx_cache:
        try:
            _fx_cache[ccy] = float(yf.Ticker(f"{ccy}IDR=X").history(period="5d")["Close"].iloc[-1])
        except Exception:  # noqa: BLE001
            _fx_cache[ccy] = None
    return _fx_cache[ccy]


def graham(eps, bvps, price):
    if not ok(eps) or not ok(bvps) or eps <= 0 or bvps <= 0:
        return None, None
    gn = math.sqrt(22.5 * eps * bvps)
    mos = (gn - price) / gn  # positif = harga di bawah Graham Number
    return gn, mos


# ---------------------------------------------------------------- Penilaian per saham
def analyze(code, d):
    info, hist = d["info"], d["hist"]
    inc, bal, cf = d["inc"], d["bal"], d["cf"]
    close = hist["Close"]
    price = float(close.iloc[-1])
    high52 = float(close.max())
    drawdown = price / high52 - 1  # negatif
    chg_1d = float(close.iloc[-1] / close.iloc[-2] - 1) if len(close) > 1 else 0.0
    avg_value = float((hist["Close"] * hist["Volume"]).tail(20).mean())

    sector = info.get("sector") or "-"
    is_fin = sector == "Financial Services"
    name = info.get("shortName") or code

    fin_ccy = (info.get("financialCurrency") or "IDR").upper()
    fx = fx_to_idr(fin_ccy)

    roe = info.get("returnOnEquity")
    roa = info.get("returnOnAssets")
    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    der = info.get("debtToEquity")
    der = der / 100 if ok(der) else None  # yfinance memberi dalam persen
    cr = info.get("currentRatio")
    eg = info.get("earningsGrowth")
    # yfinance >= 0.2.54 memberi dividendYield dalam persen (7.52 = 7,52%). Aturan lama "bagi 100
    # jika > 1" membuat yield 0,5% terbaca 50%.
    dy = info.get("dividendYield")
    dy = dy / 100 if ok(dy) else None
    fcf = get_row(cf, ["Free Cash Flow"])
    ni = get_row(inc, ["Net Income"])
    eq = get_row(bal, ["Stockholders Equity", "Common Stock Equity"])
    ta = get_row(bal, ["Total Assets"])

    # Nilai buku per saham dihitung sendiri dalam IDR. bookValue/priceToBook dari Yahoo memakai mata uang
    # laporan (USD untuk ITMG/ADRO/TPIA) sehingga PBV bisa terbaca 15.000x.
    shares = info.get("sharesOutstanding")
    eps = info.get("trailingEps")  # sudah dalam mata uang harga (IDR)
    bvps = info.get("bookValue")
    if fin_ccy != "IDR":
        bvps = eq * fx / shares if ok(eq) and ok(fx) and ok(shares) and shares > 0 else None
        pb = price / bvps if ok(bvps) and bvps > 0 else None
        fcf = fcf * fx if ok(fcf) and ok(fx) else None

    fscore, _ = (None, 0) if is_fin else piotroski(inc, bal, cf)
    z = None if is_fin else altman_z_em(inc, bal, info)
    ey, roc = (None, None) if is_fin or not ok(fx) else magic_formula_parts(inc, bal, info, fx)
    gn, mos = graham(eps, bvps, price)
    peg = safe_div(pe, eg * 100) if ok(pe) and ok(eg) and eg > 0 else None

    # --- Komponen skor (0..1)
    if is_fin:
        quality = avg([lin(roe, 0.05, 0.20), lin(roa, 0.005, 0.02), lin(eg, -0.10, 0.15)])
        safety = avg([lin(safe_div(eq, ta), 0.06, 0.15), 1.0 if ok(ni) and ni > 0 else 0.0])
        value = avg([
            lin(safe_div(roe, pb), 0.05, 0.20) if ok(roe) and ok(pb) and pb > 0 else None,  # ROE/PBV
            lin(pe, 20, 7) if ok(pe) and pe > 0 else None,
            lin(dy, 0.0, 0.07),
        ])
    else:
        quality = avg([
            fscore / 9 if ok(fscore) else None,
            lin(roe, 0.05, 0.20),
            lin(roc, 0.05, 0.30),
        ])
        safety = avg([
            lin(z, 1.1, 2.6),
            lin(der, 2.0, 0.5),
            lin(cr, 0.8, 2.0),
            (1.0 if fcf > 0 else 0.0) if ok(fcf) else None,
        ])
        value = avg([
            lin(mos, -1.0, 0.33),
            lin(ey, 0.02, 0.15),
            lin(pe, 25, 8) if ok(pe) and pe > 0 else None,
            lin(peg, 2.0, 0.7),
            lin(dy, 0.0, 0.07),
        ])
    discount = lin(drawdown, 0.0, -0.50)

    parts = {"quality": quality, "safety": safety, "value": value, "discount": discount}
    total_w = sum(WEIGHTS[k] for k, v in parts.items() if v is not None)
    score = sum(WEIGHTS[k] * v for k, v in parts.items() if v is not None) / total_w * 100 if total_w else None

    # --- Tanda bahaya (value trap / data jelek)
    flags = []
    if ok(ni) and ni < 0:
        flags.append("RUGI")
    if ok(eq) and eq <= 0:
        flags.append("EKUITAS NEGATIF")
    if ok(z) and z < 1.1:
        flags.append("Z-SCORE BAHAYA")
    if ok(fscore) and fscore <= 3:
        flags.append("F-SCORE LEMAH")
    if ok(der) and der > 2 and not is_fin:
        flags.append("UTANG TINGGI")
    if ok(fcf) and fcf < 0 and not is_fin:
        flags.append("FCF NEGATIF")
    if avg_value < MIN_AVG_VALUE_IDR:
        flags.append("TIDAK LIKUID")
    coverage = sum(v is not None for v in [quality, safety, value])
    if coverage < 2:
        flags.append("DATA KURANG")
    report_date = inc.columns[0] if inc is not None and not inc.empty else None
    if report_date is not None and (dt.datetime.now() - pd.Timestamp(report_date).to_pydatetime()).days > 550:
        flags.append("LAPORAN USANG")  # laporan tahunan terakhir di Yahoo lebih dari ~18 bulan
    if (ok(pb) and pb > 50) or (ok(pe) and pe > 500) or (fin_ccy != "IDR" and not ok(fx)):
        flags.append("DATA JANGGAL")  # angka tidak masuk akal, kemungkinan salah data/kurs

    graham_defensive = bool(
        ok(pe) and ok(pb) and 0 < pe < 15 and 0 < pb < 1.5 and pe * pb < 22.5 and (is_fin or (ok(cr) and cr >= 1.5))
    )

    return {
        "kode": code, "nama": name, "sektor": sector, "bank": is_fin,
        "harga": price, "chg_1d": chg_1d, "dari_puncak_52w": drawdown,
        "nilai_transaksi_rata2": avg_value,
        "skor": round(score, 1) if ok(score) else None,
        "kualitas": quality, "keamanan": safety, "valuasi": value, "diskon": discount,
        "piotroski": fscore, "altman_z": z, "earnings_yield": ey, "roc": roc,
        "graham_number": gn, "margin_of_safety": mos, "graham_defensif": graham_defensive,
        "roe": roe, "roa": roa, "per": pe, "pbv": pb, "der": der, "current_ratio": cr,
        "peg": peg, "div_yield": dy, "fcf": fcf,
        "mata_uang_lapkeu": fin_ccy,
        "tgl_lapkeu": f"{pd.Timestamp(report_date):%Y-%m-%d}" if report_date is not None else None,
        "flags": ", ".join(flags),
    }


def add_magic_formula_rank(df):
    m = df[~df["bank"] & df["earnings_yield"].notna() & df["roc"].notna()].copy()
    m["mf_rank"] = m["earnings_yield"].rank(ascending=False) + m["roc"].rank(ascending=False)
    df["magic_formula_rank"] = m["mf_rank"].rank(method="min")
    return df


def add_rank_change(df):
    """Bandingkan dengan file hasil terakhir untuk melihat naik/turun peringkat."""
    prev_files = sorted(DATA_DIR.glob("hasil_*.csv"))
    today = f"hasil_{dt.datetime.now(WIB):%Y-%m-%d}.csv"
    prev_files = [p for p in prev_files if p.name != today]
    if not prev_files:
        df["perubahan_peringkat"] = None
        return df
    prev = pd.read_csv(prev_files[-1])[["kode", "peringkat"]].rename(columns={"peringkat": "peringkat_lalu"})
    df = df.merge(prev, on="kode", how="left")
    df["perubahan_peringkat"] = df["peringkat_lalu"] - df["peringkat"]
    return df.drop(columns=["peringkat_lalu"])


# ---------------------------------------------------------------- Format pesan
def pct(x, d=1):
    return f"{x * 100:+.{d}f}%" if ok(x) else "-"


def num(x, d=1):
    return f"{x:.{d}f}" if ok(x) else "-"


def build_message(df, ihsg_info, n_scanned, n_failed):
    now = dt.datetime.now(WIB)
    hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"][now.weekday()]
    bulan = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
             "September", "Oktober", "November", "Desember"][now.month - 1]
    lines = ["📊 <b>SCREENER FUNDAMENTAL BEI</b>", f"{hari}, {now.day} {bulan} {now.year} · {now:%H:%M} WIB", ""]
    if ihsg_info:
        lines.append(f"IHSG: <b>{ihsg_info[0]:,.0f}</b> ({pct(ihsg_info[1], 2)} hari ini, {pct(ihsg_info[2])} dari puncak 52 mgg)")
        lines.append("")

    clean = df[df["flags"] == ""].head(TOP_N)
    lines.append(f"🏆 <b>TOP {len(clean)} — sehat & lolos semua filter</b>")
    for _, r in clean.iterrows():
        arrow = ""
        if ok(r.get("perubahan_peringkat")) and r["perubahan_peringkat"] != 0:
            arrow = f" {'⬆️' if r['perubahan_peringkat'] > 0 else '⬇️'}{abs(int(r['perubahan_peringkat']))}"
        detail = (
            f"ROE {pct(r['roe'], 0)} · PBV {num(r['pbv'])} · PER {num(r['per'])}"
            if r["bank"] else
            f"F {num(r['piotroski'], 0)}/9 · Z {num(r['altman_z'])} · ROE {pct(r['roe'], 0)} · MoS {pct(r['margin_of_safety'], 0)}"
        )
        lines.append(
            f"{int(r['peringkat'])}. <b>{r['kode']}</b> {r['skor']:.0f}{arrow} · Rp{r['harga']:,.0f} "
            f"({pct(r['chg_1d'])}, {pct(r['dari_puncak_52w'], 0)} dr puncak)\n    {detail}"
        )

    mf = df[df["magic_formula_rank"].notna() & (df["flags"] == "")].sort_values("magic_formula_rank").head(5)
    if not mf.empty:
        lines += ["", "🧙 <b>Magic Formula Greenblatt (top 5)</b>", ", ".join(mf["kode"])]

    gd = df[df["graham_defensif"] & (df["flags"] == "")]["kode"].tolist()
    if gd:
        lines += ["", "🛡️ <b>Lolos kriteria defensif Graham</b>", ", ".join(gd[:15])]

    traps = df[(df["dari_puncak_52w"] < -0.35) & (df["flags"] != "") & ~df["flags"].str.contains("TIDAK LIKUID")]
    if not traps.empty:
        lines += ["", "⚠️ <b>Turun dalam tapi fundamental bermasalah (waspada value trap)</b>"]
        for _, r in traps.head(6).iterrows():
            lines.append(f"• {r['kode']} {pct(r['dari_puncak_52w'], 0)} — {r['flags']}")

    lines += [
        "",
        f"<i>Dipindai {n_scanned} saham, {n_failed} gagal diambil. Data Yahoo Finance (bisa telat/kurang lengkap). "
        f"Alat bantu riset, bukan rekomendasi. Cek laporan keuangan di idx.co.id sebelum beli.</i>",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- Kirim notifikasi
def send_telegram(text, file_path=None):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("(Telegram belum diatur, pesan hanya dicetak)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    chunks, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > 3900:
            chunks.append(buf)
            buf = ""
        buf += line + "\n"
    chunks.append(buf)
    for c in chunks:
        r = requests.post(f"{url}/sendMessage", data={
            "chat_id": TELEGRAM_CHAT_ID, "text": c, "parse_mode": "HTML", "disable_web_page_preview": True,
        }, timeout=30)
        if not r.ok:
            print("Telegram error:", r.text)
    if file_path:
        with open(file_path, "rb") as f:
            requests.post(f"{url}/sendDocument", data={"chat_id": TELEGRAM_CHAT_ID, "caption": "Data lengkap semua saham"},
                          files={"document": f}, timeout=60)


def send_whatsapp(text):
    if not FONNTE_TOKEN or not WA_TARGET:
        return
    plain = text.replace("<b>", "*").replace("</b>", "*").replace("<i>", "_").replace("</i>", "_")
    r = requests.post("https://api.fonnte.com/send", headers={"Authorization": FONNTE_TOKEN},
                      data={"target": WA_TARGET, "message": plain}, timeout=30)
    print("WhatsApp:", r.status_code, r.text[:200])


# ---------------------------------------------------------------- Data untuk website
def export_site_json(df):
    import json
    site = BASE / "docs" / "data"
    site.mkdir(parents=True, exist_ok=True)
    rows = json.loads(df.to_json(orient="records"))
    payload = {"updated": dt.datetime.now(WIB).isoformat(timespec="minutes"), "rows": rows}
    (site / "screener.json").write_text(json.dumps(payload, ensure_ascii=False))
    print("Tersimpan: docs/data/screener.json")


# ---------------------------------------------------------------- Main
def ihsg_snapshot():
    try:
        h = yf.Ticker("^JKSE").history(period="1y")["Close"]
        return float(h.iloc[-1]), float(h.iloc[-1] / h.iloc[-2] - 1), float(h.iloc[-1] / h.max() - 1)
    except Exception:  # noqa: BLE001
        return None


def main():
    DATA_DIR.mkdir(exist_ok=True)
    tickers = load_tickers()
    print(f"Memindai {len(tickers)} saham...")
    rows, failed = [], []
    for i, code in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {code}")
        d = fetch(code)
        if d is None:
            failed.append(code)
            continue
        try:
            rows.append(analyze(code, d))
        except Exception as e:  # noqa: BLE001
            print(f"  ! {code}: gagal dianalisis ({e})")
            failed.append(code)
        time.sleep(SLEEP_BETWEEN)

    if not rows:
        send_telegram("❌ Screener gagal: tidak ada data yang berhasil diambil hari ini.")
        sys.exit(1)

    df = pd.DataFrame(rows)
    df = add_magic_formula_rank(df)
    df["_bersih"] = df["flags"] == ""
    df = df.sort_values(["_bersih", "skor"], ascending=[False, False], na_position="last").drop(columns="_bersih")
    df["peringkat"] = range(1, len(df) + 1)
    df = add_rank_change(df)

    out = DATA_DIR / f"hasil_{dt.datetime.now(WIB):%Y-%m-%d}.csv"
    df.to_csv(out, index=False)
    print(f"Tersimpan: {out}")
    export_site_json(df)

    msg = build_message(df, ihsg_snapshot(), len(tickers), len(failed))
    print("\n" + msg)
    send_telegram(msg, out)
    send_whatsapp(msg)


if __name__ == "__main__":
    main()
