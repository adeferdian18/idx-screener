"""
Pemantau aksi korporasi BEI + narasi fundamental.

Sumber:
  0. Keterbukaan informasi BEI (dicoba, tapi diblokir Cloudflare untuk akses otomatis).
  1. RSS langsung media pasar modal (IDX Channel, Liputan6 Saham, Stockwatch, Kontan, CNBC, dll.):
     lebih cepat dari Google News karena tidak menunggu Google mengindeks.
  2. Google News RSS (berita berbahasa Indonesia) untuk kata kunci buyback, dividen, stock split,
     rights issue, private placement, tender offer, akuisisi, pembelian saham oleh orang dalam.
  3. Yahoo Finance: jadwal ex-dividen yang akan datang untuk saham di tickers.txt.

Mode:
  python corpact.py         -> lengkap (sumber 0-3, berita 14 hari)
  python corpact.py cepat   -> tiap 10 menit di jam bursa: sumber 0, 1 dan Google News 24 jam terakhir saja

Setiap aksi korporasi diberi "skor momentum" yang menggabungkan jenis aksi
(buyback = sinyal positif, private placement = dilusi, dst.) dengan skor fundamental
dari screener.py, lalu diberi narasi. Jika secret ANTHROPIC_API_KEY diisi, narasinya
ditulis oleh Claude; jika tidak, dipakai narasi berbasis aturan.

Output: docs/data/corporate_actions.json, plus ringkasan aksi baru ke Telegram.
"""

import hashlib
import html
import json
import math
import os
import re
import time
import datetime as dt
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
import yfinance as yf

BASE = Path(__file__).parent
SITE = BASE / "docs" / "data"
OUT = SITE / "corporate_actions.json"
WIB = dt.timezone(dt.timedelta(hours=7))
KEEP_DAYS = 30

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_AI_NARRATIVES = int(os.getenv("MAX_AI_NARRATIVES", 12))
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
EMAIL_MIN_SCORE = int(os.getenv("EMAIL_MIN_SCORE", 50))  # aksi dengan skor di bawah ini tidak diemail

NEWS_QUERIES = [
    "buyback saham emiten",
    "pembelian kembali saham tanpa RUPS",
    "dividen interim emiten",
    "jadwal cum dividen saham",
    "stock split saham emiten",
    "rights issue HMETD emiten",
    "private placement emiten",
    "tender offer saham",
    "akuisisi emiten Tbk",
    "direktur komisaris borong saham",
    "pengendali tambah kepemilikan saham",
]

# Query kilat (24 jam terakhir) untuk menangkap berita yang bersumber dari keterbukaan informasi,
# biasanya terbit beberapa menit sampai jam setelah emiten melapor ke BEI.
FAST_QUERIES = [
    "keterbukaan informasi Tbk",
    "laporan kepemilikan saham Tbk",
    "rencana buyback Tbk",
    "pengumuman dividen Tbk",
    "rencana private placement Tbk",
    "rencana rights issue Tbk",
]

# RSS langsung media yang feed-nya aktif dan terbaru dalam hitungan menit (dicek 21 Okt 2026).
# EmitenNews, KabarBursa, Bisnis, Investor.id tidak punya feed yang bisa dibaca; isinya tetap tertangkap via Google News.
MEDIA_FEEDS = [
    ("IDX Channel", "https://www.idxchannel.com/rss"),
    ("Liputan6 Saham", "https://feed.liputan6.com/rss/saham"),
    ("Stockwatch", "https://www.stockwatch.id/rss"),
    ("Kontan Investasi", "https://investasi.kontan.co.id/rss"),
    ("CNBC Indonesia Market", "https://www.cnbcindonesia.com/market/rss"),
    ("CNN Indonesia Ekonomi", "https://www.cnnindonesia.com/ekonomi/rss"),
    ("Detik Finance", "https://finance.detik.com/rss"),
    ("Okezone Ekonomi", "https://sindikasi.okezone.com/index.php/rss/11/RSS2.0"),
    ("Antara Bursa", "https://www.antaranews.com/rss/ekonomi-bursa.xml"),
]

IDX_API = "https://www.idx.co.id/primary/ListedCompany/GetAnnouncement"
IDX_HEADERS = {
    "User-Agent": "Mozilla/5.0 idx-screener (+https://github.com/adeferdian18/idx-screener)",
    "Accept": "application/json",
    "Referer": "https://www.idx.co.id/id/perusahaan-tercatat/keterbukaan-informasi/",
}
EARLY_HOURS = 3  # berita/pengumuman yang terbit < 3 jam lalu dianggap "baru terbit"

# jenis aksi: (kata kunci, label, sinyal dasar -3..+3, penjelasan singkat)
TYPES = [
    ("insider", ["borong saham", "tambah kepemilikan", "menambah kepemilikan", "beli saham sendiri",
                 "serap saham", "akumulasi saham"], "Pembelian orang dalam", 3,
     "Pengendali, direksi atau komisaris membeli saham perusahaannya sendiri. Mereka paling tahu kondisi bisnis, "
     "jadi pembelian dengan uang pribadi biasanya dibaca sebagai keyakinan bahwa harga sudah murah."),
    ("buyback", ["buyback", "buy back", "pembelian kembali"], "Buyback", 3,
     "Perusahaan membeli kembali sahamnya memakai kas internal. Jumlah saham beredar berkurang sehingga laba per saham naik, "
     "dan manajemen memberi sinyal bahwa mereka menilai harga di bawah nilai wajar."),
    ("tender", ["tender offer", "penawaran tender"], "Tender offer", 2,
     "Pihak tertentu menawar membeli saham dari publik, biasanya di atas harga pasar."),
    ("dividend", ["dividen", "dividend", "cum date", "cum dividen"], "Dividen", 2,
     "Pembagian laba tunai. Dividen yang stabil atau naik menandakan arus kas nyata, bukan sekadar laba akuntansi."),
    ("split", ["stock split", "pemecahan saham", "pemecahan nilai nominal"], "Stock split", 1,
     "Harga per lembar diperkecil agar lebih terjangkau dan likuid. Nilai perusahaan tidak berubah, efeknya lebih ke sentimen."),
    ("acquisition", ["akuisisi", "ambil alih", "caplok", "mengakuisisi"], "Akuisisi", 1,
     "Ekspansi lewat pembelian perusahaan lain. Bisa menambah laba, bisa juga membebani neraca jika dibiayai utang."),
    ("rights", ["rights issue", "hmetd", "penambahan modal dengan"], "Rights issue", -1,
     "Penerbitan saham baru untuk pemegang saham lama. Jika tidak ikut menebus, kepemilikan terdilusi."),
    ("placement", ["private placement", "tanpa hmetd", "pmtdhmetd", "pmthmetd"], "Private placement", -2,
     "Saham baru dijual ke pihak tertentu tanpa hak memesan bagi pemegang saham lama, sehingga terjadi dilusi."),
    ("reverse", ["reverse stock", "penggabungan saham", "reverse split"], "Reverse split", -1,
     "Penggabungan saham, umumnya dilakukan emiten yang harganya sudah sangat rendah."),
    ("delisting", ["delisting", "go private", "penghapusan pencatatan"], "Delisting / go private", -1,
     "Saham akan keluar dari bursa. Perhatikan harga tender offer yang ditawarkan sebelum keputusan."),
]

CODE_RE = re.compile(r"\b([A-Z]{4})\b")
NOT_TICKERS = {"IHSG", "RUPS", "OJK", "HMETD", "BUMN", "IPO", "LQ45", "BEI", "IDX", "JATS", "KSEI", "MSCI",
               "TBK", "YOY", "QOQ", "CEO", "CFO", "USD", "IDR", "ASEAN", "OPEC", "GDP", "PMTD", "PPN", "NPL", "CASA"}


# ---------------------------------------------------------------- Bantuan umum
def ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def pct(x, d=0):
    return f"{x * 100:.{d}f}%" if ok(x) else "n/a"


def num(x, d=1):
    return f"{x:.{d}f}" if ok(x) else "n/a"


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return default


def load_tickers():
    """Semua saham BEI (data/universe.json dari universe.py) + tickers.txt sebagai cadangan."""
    out = set()
    for ln in (BASE / "tickers.txt").read_text().splitlines():
        ln = ln.strip().upper()
        if ln and not ln.startswith("#"):
            out.add(ln)
    try:
        out |= {r["kode"] for r in json.loads((BASE / "data" / "universe.json").read_text(encoding="utf-8"))["rows"]}
    except (OSError, ValueError, KeyError):
        pass
    return out


def classify(text):
    t = text.lower()
    for key, words, label, signal, why in TYPES:
        if any(w in t for w in words):
            return key, label, signal, why
    return None


def extract_codes(title, universe):
    """Kode saham: yang di dalam kurung (PRDA) selalu diterima; kode lain hanya jika ada di tickers.txt."""
    codes = re.findall(r"\(([A-Z]{4})\)", title)
    codes += [c for c in CODE_RE.findall(title) if c in universe]
    seen = []
    for c in codes:
        if c not in NOT_TICKERS and c not in seen:
            seen.append(c)
    return seen


# ---------------------------------------------------------------- Sumber 1: RSS langsung media
_ITEM_RE = re.compile(r"<item\b.*?</item>", re.S | re.I)


def _tag(block, name):
    m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, re.S | re.I)
    if not m:
        return ""
    v = re.sub(r"^\s*<!\[CDATA\[(.*)\]\]>\s*$", r"\1", m.group(1), flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", v)).strip()


def parse_feed(content):
    """Item RSS (judul, link, ringkasan, tanggal). Dibaca dengan regex karena beberapa feed media XML-nya tidak valid."""
    out = []
    for block in _ITEM_RE.findall(content.decode("utf-8", "replace")):
        try:
            published = parsedate_to_datetime(_tag(block, "pubDate")).astimezone(WIB)
        except Exception:  # noqa: BLE001
            published = dt.datetime.now(WIB)
        out.append({"title": _tag(block, "title"), "link": _tag(block, "link") or _tag(block, "guid"),
                    "desc": _tag(block, "description")[:600], "published": published})
    return out


def fetch_media(universe):
    events = []
    for source, url in MEDIA_FEEDS:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 idx-screener"})
            items = parse_feed(r.content) if r.ok else []
        except Exception as e:  # noqa: BLE001
            print(f"! RSS {source}: {e}")
            continue
        for it in items:
            kind = classify(it["title"])
            if not kind:
                continue
            # kode saham sering hanya ada di ringkasan ("BCA Perpanjang Buyback" -> "(BBCA)" di ringkasan)
            codes = extract_codes(it["title"], universe) or extract_codes(it["desc"], universe)[:1]
            for code in codes[:2]:
                events.append({
                    "id": hashlib.md5(f"{code}|{it['title']}".encode()).hexdigest()[:12],
                    "code": code, "type": kind[0], "label": kind[1], "signal": kind[2], "why": kind[3],
                    "title": it["title"], "link": it["link"], "source": source,
                    "date": it["published"].isoformat(timespec="minutes"), "origin": "media",
                })
    print(f"RSS media langsung: {len(events)} aksi korporasi terdeteksi")
    return events


# ---------------------------------------------------------------- Sumber 2: Google News
def fetch_news(universe, fast=False):
    events = []
    queries = [(q, "1d") for q in FAST_QUERIES] + ([] if fast else [(q, "14d") for q in NEWS_QUERIES])
    for q, window in queries:
        url = f"https://news.google.com/rss/search?q={quote_plus(q + ' when:' + window)}&hl=id&gl=ID&ceid=ID:id"
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 idx-screener"})
            root = ET.fromstring(r.content)
        except Exception as e:  # noqa: BLE001
            print(f"! berita '{q}': {e}")
            continue
        for item in root.iter("item"):
            title = html.unescape(item.findtext("title") or "")
            link = item.findtext("link") or ""
            source = item.findtext("source") or ""
            try:
                published = parsedate_to_datetime(item.findtext("pubDate")).astimezone(WIB)
            except Exception:  # noqa: BLE001
                published = dt.datetime.now(WIB)
            kind = classify(title)
            codes = extract_codes(title, universe)
            if not kind or not codes:
                continue
            for code in codes[:2]:
                events.append({
                    "id": hashlib.md5(f"{code}|{title}".encode()).hexdigest()[:12],
                    "code": code, "type": kind[0], "label": kind[1], "signal": kind[2], "why": kind[3],
                    "title": title, "link": link, "source": source,
                    "date": published.isoformat(timespec="minutes"), "origin": "berita",
                })
        time.sleep(1)
    print(f"Berita: {len(events)} aksi korporasi terdeteksi")
    return events


# ---------------------------------------------------------------- Sumber 0: keterbukaan informasi BEI
def fetch_idx_disclosures(days=2):
    """Pengumuman resmi emiten dari idx.co.id. Situs ini dilindungi Cloudflare; jika permintaan
    ditolak (403/halaman tantangan) sumber ini dilewati begitu saja, tanpa mencoba mengakali proteksi."""
    today = dt.datetime.now(WIB).date()
    params = {"kodeEmiten": "", "emitenType": "*", "indexFrom": 0, "pageSize": 100, "lang": "id", "keyword": "",
              "dateFrom": f"{today - dt.timedelta(days=days):%Y%m%d}", "dateTo": f"{today:%Y%m%d}"}
    try:
        r = requests.get(IDX_API, params=params, headers=IDX_HEADERS, timeout=20)
        data = r.json() if r.ok and "json" in r.headers.get("content-type", "") else None
    except Exception as e:  # noqa: BLE001
        data = None
        print(f"! keterbukaan informasi BEI: {e}")
    if not data:
        print("Keterbukaan informasi BEI: tidak dapat diakses (diblokir Cloudflare), dilewati")
        return []
    events = []
    for rep in data.get("Replies", []):
        p = rep.get("pengumuman") or {}
        code = (p.get("Kode_Emiten") or p.get("KodeEmiten") or "").strip().upper()[:4]
        title = html.unescape(p.get("JudulPengumuman") or p.get("PerihalPengumuman") or "")
        kind = classify(title)
        if not kind or len(code) != 4:
            continue
        try:
            published = dt.datetime.fromisoformat(str(p.get("TglPengumuman"))[:19]).replace(tzinfo=WIB)
        except Exception:  # noqa: BLE001
            published = dt.datetime.now(WIB)
        att = rep.get("attachments") or []
        link = att[0].get("FullSavePath", "") if att else ""
        events.append({
            "id": hashlib.md5(f"{code}|idx|{p.get('NoPengumuman') or title}".encode()).hexdigest()[:12],
            "code": code, "type": kind[0], "label": kind[1], "signal": kind[2], "why": kind[3],
            "title": title, "link": link, "source": "Keterbukaan Informasi BEI",
            "date": published.isoformat(timespec="minutes"), "origin": "idx",
        })
    print(f"Keterbukaan informasi BEI: {len(events)} aksi korporasi")
    return events


def hours_since(iso):
    try:
        return (dt.datetime.now(WIB) - dt.datetime.fromisoformat(iso)).total_seconds() / 3600
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- Sumber 2: jadwal dividen Yahoo
def fetch_dividend_calendar(universe, screener_rows):
    events = []
    today = dt.datetime.now(WIB).date()
    for code in sorted(universe):
        try:
            cal = yf.Ticker(f"{code}.JK").calendar or {}
            exd = cal.get("Ex-Dividend Date")
            if not exd:
                continue
            exd = exd if isinstance(exd, dt.date) else dt.date.fromisoformat(str(exd)[:10])
            if not (today <= exd <= today + dt.timedelta(days=30)):
                continue
            row = screener_rows.get(code, {})
            dy = row.get("div_yield")
            title = f"{code} memasuki ex-dividen {exd:%d-%m-%Y}" + (f" (yield 12 bln ±{pct(dy, 1)})" if ok(dy) else "")
            events.append({
                "id": hashlib.md5(f"{code}|exdiv|{exd}".encode()).hexdigest()[:12],
                "code": code, "type": "dividend", "label": "Jadwal dividen", "signal": 2, "why": TYPES[3][4],
                "title": title, "link": "", "source": "Yahoo Finance",
                "date": dt.datetime.now(WIB).isoformat(timespec="minutes"), "ex_date": exd.isoformat(),
                "origin": "jadwal",
            })
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.4)
    print(f"Jadwal dividen 30 hari: {len(events)}")
    return events


# ---------------------------------------------------------------- Fundamental untuk saham di luar daftar
_extra_cache = {}


def light_fundamentals(code):
    if code in _extra_cache:
        return _extra_cache[code]
    row = {"kode": code}
    try:
        info = yf.Ticker(f"{code}.JK").info or {}
        der = info.get("debtToEquity")
        row.update({
            "nama": info.get("shortName") or code, "sektor": info.get("sector") or "-",
            "roe": info.get("returnOnEquity"), "per": info.get("trailingPE"), "pbv": info.get("priceToBook"),
            "der": der / 100 if ok(der) else None, "harga": info.get("currentPrice") or info.get("regularMarketPrice"),
            "dari_puncak_52w": (info["currentPrice"] / info["fiftyTwoWeekHigh"] - 1)
            if info.get("currentPrice") and info.get("fiftyTwoWeekHigh") else None,
            "flags": "DI LUAR DAFTAR SCREENER",
        })
    except Exception:  # noqa: BLE001
        row["flags"] = "DATA KURANG"
    _extra_cache[code] = row
    return row


# ---------------------------------------------------------------- Skor & narasi
def momentum_score(ev, f):
    s = 50 + ev["signal"] * 10
    score = f.get("skor")
    if ok(score):
        s += (score - 50) * 0.5
    dd = f.get("dari_puncak_52w")
    flags = f.get("flags") or ""
    if ok(dd) and dd < -0.25 and ev["signal"] > 0 and not flags:
        s += 8  # aksi positif pada saham sehat yang sudah turun dalam
    for bad in ["RUGI", "EKUITAS NEGATIF", "Z-SCORE BAHAYA", "UTANG TINGGI"]:
        if bad in flags:
            s -= 10
    if "TIDAK LIKUID" in flags:
        s -= 5
    return round(max(0, min(100, s)))


def verdict(score):
    if score >= 70:
        return "Layak dicermati"
    if score >= 45:
        return "Netral, cek detail"
    return "Waspada"


def rule_narrative(ev, f):
    name = f.get("nama") or ev["code"]
    parts = [ev["why"]]
    facts = []
    if ok(f.get("skor")):
        facts.append(f"skor fundamental {f['skor']:.0f}/100 (peringkat {f.get('peringkat', '?')} di screener)")
    if ok(f.get("piotroski")):
        facts.append(f"Piotroski {f['piotroski']:.0f}/9")
    if ok(f.get("altman_z")):
        facts.append(f"Altman Z {f['altman_z']:.1f}")
    if ok(f.get("roe")):
        facts.append(f"ROE {pct(f['roe'])}")
    if ok(f.get("pbv")):
        facts.append(f"PBV {num(f['pbv'])}x")
    if ok(f.get("der")) and not f.get("bank"):
        facts.append(f"DER {num(f['der'])}x")
    if facts:
        parts.append(f"{name} saat ini memiliki " + ", ".join(facts) + ".")
    dd = f.get("dari_puncak_52w")
    if ok(dd):
        parts.append(f"Harga berada {pct(abs(dd))} di bawah puncak 52 minggu.")
    t = ev["type"]
    if t == "buyback":
        if ok(f.get("fcf")) and f["fcf"] > 0:
            parts.append("Arus kas bebas positif, jadi buyback didanai dari bisnis, bukan utang.")
        elif ok(f.get("fcf")):
            parts.append("Perhatikan: arus kas bebas negatif, pastikan buyback tidak menggerus likuiditas.")
        parts.append("Pantau realisasinya di keterbukaan informasi; anggaran besar yang tidak dieksekusi tidak berarti apa-apa.")
    elif t in ("rights", "placement"):
        parts.append("Kuncinya adalah untuk apa dana dipakai dan harga pelaksanaannya: ekspansi produktif lebih baik daripada menambal utang.")
    elif t == "dividend":
        parts.append("Bandingkan dividen dengan arus kas bebas; dividen yang melebihi FCF berulang kali tidak berkelanjutan.")
    flags = f.get("flags")
    if flags:
        parts.append(f"Tanda bahaya: {flags.lower()}.")
    return " ".join(parts)


def ai_narrative(ev, f):
    fields = ["nama", "sektor", "bank", "harga", "dari_puncak_52w", "skor", "peringkat", "piotroski", "altman_z",
              "roe", "roa", "per", "pbv", "der", "current_ratio", "fcf", "div_yield", "margin_of_safety", "flags"]
    data = {k: f.get(k) for k in fields if ok(f.get(k))}
    prompt = (
        "Kamu analis fundamental saham Indonesia. Tulis narasi 3-4 kalimat dalam bahasa Indonesia yang lugas "
        "tentang aksi korporasi berikut: apa artinya bagi pemegang saham, bagaimana kaitannya dengan kondisi "
        "fundamental perusahaan, dan risiko utama yang perlu dicek. Hanya gunakan data yang diberikan; jangan "
        "mengarang angka. Jangan memberi rekomendasi beli/jual atau target harga. Tanpa pembuka, tanpa markdown.\n\n"
        f"Aksi: {ev['label']}\nJudul berita: {ev['title']}\nSumber: {ev['source']}\n"
        f"Konteks pasar: IHSG sedang tertekan setelah MSCI membuka konsultasi penurunan status Indonesia "
        f"menjadi Standalone Market (Oktober 2026).\nData fundamental: {json.dumps(data, ensure_ascii=False)}"
    )
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
        "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json",
    }, json={"model": CLAUDE_MODEL, "max_tokens": 400, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()


def send_email(subject, html_body):
    """Kirim email lewat SMTP Gmail. Butuh secret GMAIL_USER + GMAIL_APP_PASSWORD (App Password Google,
    bukan password biasa). Penerima: EMAIL_TO, atau GMAIL_USER sendiri jika kosong."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, GMAIL_USER, EMAIL_TO or GMAIL_USER
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            s.send_message(msg)
        print(f"Email terkirim ke {msg['To']}")
    except Exception as e:  # noqa: BLE001
        print(f"! email: {e}")


def email_html(events):
    cards = []
    for e in events:
        f = e.get("fund") or {}
        facts = " · ".join(x for x in [
            f"Skor fundamental {f['skor']:.0f}" if ok(f.get("skor")) else "",
            f"ROE {pct(f['roe'])}" if ok(f.get("roe")) else "",
            f"PBV {num(f['pbv'])}x" if ok(f.get("pbv")) else "",
            f"PER {num(f['per'])}x" if ok(f.get("per")) else "",
            f"{pct(f['dari_puncak_52w'])} dari puncak 52 mgg" if ok(f.get("dari_puncak_52w")) else "",
        ] if x)
        early = f" · ⚡ {e['age_hours']:.1f} jam lalu" if e.get("early") else ""
        link = f'<a href="{html.escape(e["link"])}">Buka sumber</a>' if e.get("link") else ""
        flags = f'<p style="color:#b42318;margin:4px 0">⚠ {html.escape(f["flags"])}</p>' if f.get("flags") else ""
        cards.append(
            f'<div style="border:1px solid #ddd;border-radius:8px;padding:12px;margin:10px 0">'
            f'<b style="font-size:16px">{e["code"]}</b> · {html.escape(e.get("company", ""))}<br>'
            f'<b>{html.escape(e["label"])}</b> · skor {e["score"]} ({e["verdict"]}){early}<br>'
            f'<p style="margin:6px 0">{html.escape(e["title"])}</p>'
            f'<p style="margin:4px 0;color:#555">{facts}</p>{flags}'
            f'<p style="margin:6px 0"><i>{html.escape(e["narrative"])}</i></p>{link}</div>'
        )
    return (
        '<div style="font-family:Arial,sans-serif;max-width:640px">'
        f'<h2>🏢 {len(events)} aksi korporasi baru</h2>' + "".join(cards) +
        '<p style="color:#777;font-size:12px">Ringkasan otomatis dari idx-screener. Bukan rekomendasi beli/jual; '
        'verifikasi di keterbukaan informasi resmi idx.co.id.<br>'
        '<a href="https://adeferdian18.github.io/idx-screener/">Buka dashboard</a></p></div>'
    )


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", timeout=30, data={
        "chat_id": TELEGRAM_CHAT_ID, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True,
    })


# ---------------------------------------------------------------- Main
def main(fast=False):
    universe = load_tickers()
    screener = load_json(SITE / "screener.json", {"rows": []})
    rows = {r["kode"]: r for r in screener.get("rows", [])}

    old = load_json(OUT, {"events": []})
    old_by_id = {e["id"]: e for e in old.get("events", [])}

    new_events = fetch_idx_disclosures() + fetch_media(universe) + fetch_news(universe, fast)
    if not fast:
        # kalender dividen tetap untuk saham screener saja: memanggil Yahoo per saham, 843 saham terlalu lama
        new_events += fetch_dividend_calendar(set(rows) or universe, rows)

    now = dt.datetime.now(WIB)
    cutoff = now - dt.timedelta(days=KEEP_DAYS)
    merged = dict(old_by_id)
    fresh_ids = []
    for ev in new_events:
        if ev["id"] not in merged:
            # kapan pertama kali tertangkap, untuk mengukur keterlambatan dari waktu terbit
            ev["terdeteksi"] = now.isoformat(timespec="minutes")
            age = hours_since(ev["date"]) if ev.get("origin") != "jadwal" else None
            ev["telat_menit"] = round(age * 60) if age is not None and age >= 0 else None
            merged[ev["id"]] = ev
            fresh_ids.append(ev["id"])

    events = []
    ai_used = 0
    for ev in merged.values():
        try:
            if dt.datetime.fromisoformat(ev["date"]) < cutoff:
                continue
        except Exception:  # noqa: BLE001
            pass
        # saham di luar daftar screener: pakai data yang sudah tersimpan agar run tiap 10 menit tetap cepat
        prev = dict(ev["fund"], nama=ev.get("company")) if ev.get("fund") and ev.get("company") else None
        f = rows.get(ev["code"]) or prev or light_fundamentals(ev["code"])
        ev["company"] = f.get("nama") or ev["code"]
        ev["fund"] = {k: f.get(k) for k in ["skor", "peringkat", "piotroski", "altman_z", "roe", "pbv", "per",
                                              "der", "dari_puncak_52w", "harga", "flags", "bank", "sektor"]}
        ev["score"] = momentum_score(ev, f)
        ev["verdict"] = verdict(ev["score"])
        age = hours_since(ev["date"]) if ev.get("origin") != "jadwal" else None
        ev["age_hours"] = round(age, 1) if age is not None else None
        ev["early"] = age is not None and 0 <= age < EARLY_HOURS
        if not ev.get("narrative"):
            ev["narrative"] = rule_narrative(ev, f)
            ev["narrative_by"] = "aturan"
        events.append(ev)

    # Narasi Claude untuk aksi baru dengan skor tertinggi (hemat biaya API)
    if ANTHROPIC_API_KEY:
        for ev in sorted(events, key=lambda e: -e["score"]):
            if ai_used >= MAX_AI_NARRATIVES:
                break
            if ev.get("narrative_by") == "claude":
                continue
            try:
                ev["narrative"] = ai_narrative(ev, rows.get(ev["code"]) or light_fundamentals(ev["code"]))
                ev["narrative_by"] = "claude"
                ai_used += 1
            except Exception as e:  # noqa: BLE001
                print(f"! narasi Claude {ev['code']}: {e}")
                break

    # Satu kartu per (kode, jenis) per hari agar tidak dobel dari banyak media
    dedup = {}
    for ev in events:
        ev.pop("also", None)
    # Pengumuman resmi BEI didahulukan sebagai kartu utama; media lain masuk ke "also"
    for ev in sorted(events, key=lambda e: (e.get("origin") == "idx", e["date"]), reverse=True):
        key = (ev["code"], ev["type"], ev["date"][:10])
        if key in dedup:
            dedup[key].setdefault("also", []).append({"source": ev["source"], "link": ev["link"]})
            continue
        dedup[key] = ev
    events = sorted(dedup.values(), key=lambda e: (e["score"], e["date"]), reverse=True)

    SITE.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "mode": "cepat" if fast else "lengkap",
        "updated": dt.datetime.now(WIB).isoformat(timespec="minutes"),
        "events": events,
    }, ensure_ascii=False))
    print(f"Tersimpan {len(events)} aksi korporasi ({ai_used} narasi Claude baru)")

    mail = [e for e in events if e["id"] in fresh_ids and e["score"] >= EMAIL_MIN_SCORE][:15]
    if os.getenv("EMAIL_TEST") == "true" and not mail:
        mail = events[:3]  # tes manual: kirim 3 aksi teratas walau bukan yang baru
    if mail:
        top = ", ".join(sorted({e["code"] for e in mail})[:6])
        early = "⚡ " if any(e.get("early") for e in mail) else ""
        send_email(f"{early}[IDX] {len(mail)} aksi korporasi baru: {top}", email_html(mail))

    fresh = [e for e in events if e["id"] in fresh_ids and e["score"] >= 60][:6]
    if os.getenv("EMAIL_TEST") == "true" and not fresh:
        fresh = events[:3]  # tes manual juga ke Telegram
    if fresh:
        lines = ["🏢 <b>AKSI KORPORASI BARU</b>", ""]
        for e in fresh:
            early = f" · ⚡ terbit {e['age_hours']:.1f} jam lalu".replace(".", ",") if e.get("early") else ""
            lines.append(f"<b>{e['code']}</b> · {e['label']} · skor {e['score']} ({e['verdict']}){early}")
            lines.append(html.escape(e["title"][:160]) + f" <i>({html.escape(e.get('source') or '-')})</i>")
            lines.append(f"<i>{html.escape(e['narrative'][:350])}</i>")
            lines.append("")
        lines.append("Bukan rekomendasi. Baca keterbukaan informasi resmi di idx.co.id.")
        send_telegram("\n".join(lines))


if __name__ == "__main__":
    import sys
    main(fast=len(sys.argv) > 1 and sys.argv[1] == "cepat")
