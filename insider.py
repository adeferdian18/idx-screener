"""Pelacak transaksi orang dalam / pemegang saham besar di BEI.

Mencatat beli/jual saham oleh direksi, komisaris, pengendali, sekuritas & manajer investasi,
korporasi, dan individu pemilik >=5%. Hasil: docs/data/insider.json.

Sumber:
  0. Keterbukaan informasi BEI (laporan kepemilikan). Situs dilindungi Cloudflare; bila ditolak
     (403 / bukan JSON) sumber ini dilewati, tanpa mencoba mengakali proteksi.
  1. Google News RSS + RSS media (sama dengan corpact.py). Angka diambil dengan regex dari judul
     dan ringkasan; yang tidak terbaca dibiarkan null, tidak pernah dikarang.

Jalankan:  python insider.py          (python insider.py tes  -> hanya uji parser)
"""
import datetime as dt
import hashlib
import html
import re
import sys
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests

from corpact import (BASE, IDX_API, IDX_HEADERS, MEDIA_FEEDS, SITE, WIB, extract_codes, load_json,
                     load_tickers, parse_feed)

OUT = SITE / "insider.json"
KEEP_DAYS = 90

NEWS_QUERIES = [
    "laporan kepemilikan saham", "borong saham", "jual saham Tbk", "tambah kepemilikan saham",
    "kurangi kepemilikan saham", "divestasi saham Tbk", "direktur beli saham", "komisaris jual saham",
    "pengendali jual saham", "lepas saham Tbk", "lepas saham direktur", "pengendali tambah kepemilikan",
]
IDX_TITLE_WORDS = ("kepemilikan",)  # "Laporan Kepemilikan", "Perubahan Kepemilikan", dll.

# judul/ringkasan harus memuat salah satu ini agar dianggap transaksi kepemilikan
RELEVANT = ("kepemilikan", "borong", "jual saham", "beli saham", "lepas saham", "melepas saham", "menjual saham",
            "membeli saham", "divestasi", "serap saham", "akumulasi saham", "tambah saham", "kurangi saham",
            "menambah saham", "mengurangi saham", "lego saham", "obral saham", "lembar saham")
EXCLUDE = ("buyback", "buy back", "pembelian kembali", "rights issue", "hmetd", "ipo", "tender offer",
           "rekomendasi saham", "saham pilihan", "net sell asing", "net buy asing", "asing jual", "asing borong")

SELL_WORDS = ("jual", "lepas", "divestasi", "kurangi", "mengurangi", "lego", "obral", "pangkas", "susut")
BUY_WORDS = ("beli", "borong", "tambah", "menambah", "serap", "akumulasi", "caplok", "naikkan")
REPO_WORDS = ("repo", "gadai", "jaminan", "pledge")

ROLES = ("direksi_komisaris", "pengendali", "sekuritas_mi", "korporasi", "individu5")


# ---------------------------------------------------------------- Parser angka
def parse_id_number(s):
    """'388.417.412' -> 388417412, '1,2' -> 1.2, '15,09' -> 15.09, '1.5' -> 1.5, '336' -> 336."""
    s = s.strip().rstrip(".,")
    if not s:
        return None
    if "," in s:  # format Indonesia: titik = ribuan, koma = desimal
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


MULT = {"ribu": 1e3, "rb": 1e3, "juta": 1e6, "jt": 1e6, "miliar": 1e9, "milyar": 1e9, "triliun": 1e12}
_SHARES_RE = re.compile(r"(\d[\d.,]*)\s*(ribu|juta|jt|miliar|milyar)?\s*(?:lembar|helai|unit saham|saham)\b", re.I)
_PRICE_RE = re.compile(r"Rp\.?\s?(\d[\d.,]*)\s*(?:/|per)\s*(?:saham|lembar|unit)", re.I)
_PRICE2_RE = re.compile(r"(?:harga|level|di harga)\s+(?:rata-rata\s+)?Rp\.?\s?(\d[\d.,]*)(?!\s*(?:ribu|juta|miliar|triliun|jt|t\b))", re.I)
_PCT_RE = re.compile(r"dari\s+(\d[\d.,]*)\s?%\s+(?:menjadi|jadi|ke)\s+(\d[\d.,]*)\s?%", re.I)
_SHR_FROM_TO_RE = re.compile(r"dari\s+(\d[\d.,]*)\s*(juta|miliar)?\s*(?:lembar|saham)\s+(?:menjadi|jadi|ke)\s+"
                             r"(\d[\d.,]*)\s*(juta|miliar)?\s*(?:lembar|saham)", re.I)


def parse_shares(text):
    for m in _SHARES_RE.finditer(text):
        pre = text[max(0, m.start() - 4):m.start()]
        if re.search(r"Rp\.?\s?$", pre, re.I):  # "Rp336 per saham" adalah harga, bukan jumlah
            continue
        v = parse_id_number(m.group(1))
        if v is None:
            continue
        v *= MULT.get((m.group(2) or "").lower(), 1)
        if v >= 100:  # minimal 1 lot; buang angka kecil seperti "5 saham"
            return int(round(v))
    return None


def parse_price(text):
    m = _PRICE_RE.search(text) or _PRICE2_RE.search(text)
    if not m:
        return None
    v = parse_id_number(m.group(1))
    return v if v and 1 <= v <= 1_000_000 else None


def parse_pct(text):
    m = _PCT_RE.search(text)
    if not m:
        return None, None
    a, b = parse_id_number(m.group(1)), parse_id_number(m.group(2))
    if a is None or b is None or a > 100 or b > 100:
        return None, None
    return a, b


_PCT_AFTER_RE = re.compile(r"(?:naik|turun|bertambah|berkurang|menjadi|jadi)\s+(?:menjadi\s+|jadi\s+)?(\d[\d.,]*)\s?%", re.I)


def parse_after_pct(text):
    """Hanya persentase akhir, mis. 'Kepemilikan Naik Jadi 71,16%'."""
    m = _PCT_AFTER_RE.search(text)
    v = parse_id_number(m.group(1)) if m else None
    return v if v is not None and v <= 100 else None


def parse_shares_from_to(text):
    m = _SHR_FROM_TO_RE.search(text)
    if not m:
        return None, None
    a, b = parse_id_number(m.group(1)), parse_id_number(m.group(3))
    if a is None or b is None:
        return None, None
    return int(a * MULT.get((m.group(2) or "").lower(), 1)), int(b * MULT.get((m.group(4) or "").lower(), 1))


# ---------------------------------------------------------------- Klasifikasi teks
def detect_action(text, before_pct=None, after_pct=None):
    if before_pct is not None and after_pct is not None and before_pct != after_pct:
        return "beli" if after_pct > before_pct else "jual"
    t = text.lower()
    pos = []
    for words, act in ((SELL_WORDS, "jual"), (BUY_WORDS, "beli")):
        for w in words:
            i = t.find(w)
            if i >= 0:
                pos.append((i, act))
    return min(pos)[1] if pos else None


def classify_role(text, party=None):
    t = text.lower()
    p = (party or "").lower()
    if re.search(r"\b(direktur|direksi|komisaris|presdir|presiden direktur|ceo|dirut)\b", t):
        return "direksi_komisaris"
    if re.search(r"sekuritas|securities|asset management|aset manajemen|manajer investasi|capital\b|investama? fund", p or t):
        return "sekuritas_mi"
    if re.search(r"\bpengendali\b|induk usaha|perusahaan induk|\binduk\b|controlling", t):
        return "pengendali"
    if re.search(r"\bpt\b|\btbk\b|\bltd\b|\bpte\b|\binc\b|\bcorp|\bholding|\blimited\b|\bb\.?v\.?\b", p or t):
        return "korporasi"
    return "individu5"


_PARTY_RES = [
    re.compile(r"\b((?:PT\.?|Pt\.?)\s+[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,5}(?:\s+Tbk\.?)?)(?=\s|,|$)"),
    re.compile(r"\b([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4}\s+(?:Ltd\.?|Limited|Pte\.?(?:\s+Ltd\.?)?|Inc\.?|B\.V\.|Corp\.?))"),
    re.compile(r"\b(?:Direktur(?:\s+Utama)?|Komisaris(?:\s+Utama)?|Presiden Direktur|Dirut|Bos)\s+(?:[A-Z]{2,5}\s+)?"
               r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"),
    re.compile(r"\b(?:Konglomerat|Taipan|Investor(?:\s+Kakap)?|Crazy Rich)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})"),
]
_PARTY_STOP = {"Saham", "Tbk", "Bursa", "Efek", "Indonesia"}


def parse_party(text, code):
    for rx in _PARTY_RES:
        for m in rx.finditer(text):
            name = re.sub(r"\s+", " ", m.group(1)).strip(" ,.")
            name = re.sub(r"(\s+(?:Borong|Beli|Jual|Lepas|Tambah|Kurangi|Serap|Divestasi|Saham|Resmi|Kembali))+$", "", name)
            # nama berakhiran Tbk hampir selalu emitennya sendiri, bukan pelaku transaksi
            if code in name or name in _PARTY_STOP or len(name) < 4 or re.search(r"\bTbk\.?$", name):
                continue
            return name
    return None


def parse_purpose(text):
    m = re.search(r"tujuan(?:\s+transaksi)?\s*(?::|adalah|untuk)?\s*([^.;]{3,80})", text, re.I)
    if m:
        return m.group(1).strip()
    for w in ("investasi", "divestasi", "restrukturisasi", "repo", "gadai", "hibah", "warisan", "pelaksanaan opsi"):
        if re.search(rf"\b{w}\b", text, re.I):
            return w
    return None


def build_tx(code, title, desc, link, source, published, now):
    text = f"{title}. {desc}"
    bpct, apct = parse_pct(text)
    if apct is None:
        apct = parse_after_pct(text)
    action = detect_action(text, bpct, apct)
    if not action:
        return None
    shares = parse_shares(text)
    price = parse_price(text)
    bsh, ash = parse_shares_from_to(text)
    if shares is None and bsh is not None and ash is not None and bsh != ash:
        shares = abs(ash - bsh)
    party = parse_party(title, code) or parse_party(desc, code)  # judul lebih tepat menyebut pelaku
    return {
        "id": hashlib.md5(f"{code}|{title}".encode()).hexdigest()[:12],
        "date": published.date().isoformat(),
        "code": code, "party": party, "role": classify_role(text, party), "action": action,
        "shares": shares, "price": price,
        "value": float(shares * price) if shares is not None and price is not None else None,
        "before_pct": bpct, "after_pct": apct, "before_shares": bsh, "after_shares": ash,
        "purpose": parse_purpose(text),
        "is_repo": bool(re.search(r"\b(" + "|".join(REPO_WORDS) + r")\b", text, re.I)),
        "source": source, "link": link, "title": title, "first_seen": now,
    }


def relevant(title, desc):
    t = f"{title} {desc}".lower()
    tl = title.lower()
    return any(w in tl for w in RELEVANT) and not any(w in t for w in EXCLUDE)


# ---------------------------------------------------------------- Sumber 0: BEI
def fetch_idx_ownership(now, days=3):
    """Laporan kepemilikan resmi. Jika Cloudflare menolak, dilewati tanpa mengakali proteksi."""
    today = dt.datetime.now(WIB).date()
    params = {"kodeEmiten": "", "emitenType": "*", "indexFrom": 0, "pageSize": 100, "lang": "id",
              "keyword": "kepemilikan", "dateFrom": f"{today - dt.timedelta(days=days):%Y%m%d}",
              "dateTo": f"{today:%Y%m%d}"}
    try:
        r = requests.get(IDX_API, params=params, headers=IDX_HEADERS, timeout=20)
        if r.status_code in (403, 503):
            print("Laporan kepemilikan BEI: diblokir Cloudflare, dilewati")
            return [], "blocked"
        data = r.json() if r.ok and "json" in r.headers.get("content-type", "") else None
    except Exception as e:  # noqa: BLE001
        print(f"! laporan kepemilikan BEI: {e}")
        return [], "error"
    if not data:
        print("Laporan kepemilikan BEI: respons bukan JSON, dilewati")
        return [], "blocked"
    out = []
    for rep in data.get("Replies", []):
        p = rep.get("pengumuman") or {}
        code = (p.get("Kode_Emiten") or p.get("KodeEmiten") or "").strip().upper()[:4]
        title = html.unescape(p.get("JudulPengumuman") or p.get("PerihalPengumuman") or "")
        if len(code) != 4 or not any(w in title.lower() for w in IDX_TITLE_WORDS):
            continue
        try:
            published = dt.datetime.fromisoformat(str(p.get("TglPengumuman"))[:19]).replace(tzinfo=WIB)
        except Exception:  # noqa: BLE001
            published = dt.datetime.now(WIB)
        att = rep.get("attachments") or []
        link = att[0].get("FullSavePath", "") if att else ""
        tx = build_tx(code, title, "", link, "BEI", published, now)
        if tx:
            tx["id"] = hashlib.md5(f"{code}|idx|{p.get('NoPengumuman') or title}".encode()).hexdigest()[:12]
            out.append(tx)
    print(f"Laporan kepemilikan BEI: {len(out)} transaksi")
    return out, "ok"


# ---------------------------------------------------------------- Sumber 1: berita
_NAME_MAP = None


def _norm(s):
    s = re.sub(r"\(.*?\)", " ", s.lower())
    s = re.sub(r"\b(pt|tbk|persero)\b|[.,]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def codes_by_name(text):
    """Judul sering memakai nama emiten, bukan kode: 'Bank Mandiri' -> BMRI (dari data/universe.json)."""
    global _NAME_MAP
    if _NAME_MAP is None:
        rows = load_json(BASE / "data" / "universe.json", {}).get("rows", [])
        _NAME_MAP = sorted(((_norm(r["nama"]), r["kode"]) for r in rows if len(_norm(r.get("nama", ""))) >= 8),
                           key=lambda x: -len(x[0]))
    t = " " + _norm(text) + " "
    return [c for n, c in _NAME_MAP if f" {n} " in t][:1]


ENRICH_HOSTS = ("emitennews.com", "kontan.co.id")
ENRICH_MAX = 15
_enrich_cache = {}


def enrich(tx):
    """Baca artikel (hanya emitennews/kontan, link langsung) untuk mengisi field yang masih null."""
    link = tx["link"]
    if not any(h in link for h in ENRICH_HOSTS) or len(_enrich_cache) >= ENRICH_MAX:
        return tx
    if link not in _enrich_cache:
        try:
            r = requests.get(link, timeout=15, headers={"User-Agent": "Mozilla/5.0 idx-screener"})
            body = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", " ", r.text, flags=re.S | re.I))) if r.ok else ""
        except Exception:  # noqa: BLE001
            body = ""
        _enrich_cache[link] = re.sub(r"\s+", " ", body)[:20000]
        time.sleep(1)
    body = _enrich_cache[link]
    if not body:
        return tx
    bp, ap = parse_pct(body)
    bs, as_ = parse_shares_from_to(body)
    fill = {"shares": parse_shares(body), "price": parse_price(body), "before_pct": bp, "after_pct": ap,
            "before_shares": bs, "after_shares": as_, "purpose": parse_purpose(body),
            "party": parse_party(body, tx["code"])}
    for k, v in fill.items():
        if tx.get(k) is None and v is not None:
            tx[k] = v
    if tx["value"] is None and tx["shares"] is not None and tx["price"] is not None:
        tx["value"] = float(tx["shares"] * tx["price"])
    return tx


def _items_from_items(items, source_of, universe, now):
    out = []
    for it in items:
        title, desc = it["title"], it.get("desc", "")
        if not relevant(title, desc):
            continue
        codes = (extract_codes(title, universe) or codes_by_name(title)
                 or extract_codes(desc, universe)[:1] or codes_by_name(desc))
        for code in codes[:1]:  # satu transaksi per berita, kode utama saja
            tx = build_tx(code, title, desc, it["link"], source_of(it), it["published"], now)
            if tx:
                out.append(enrich(tx))
    return out


def fetch_news_insider(universe, now):
    out = []
    for q in NEWS_QUERIES:
        url = f"https://news.google.com/rss/search?q={quote_plus(q + ' when:7d')}&hl=id&gl=ID&ceid=ID:id"
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 idx-screener"})
            root = ET.fromstring(r.content)
        except Exception as e:  # noqa: BLE001
            print(f"! berita '{q}': {e}")
            continue
        items = []
        for item in root.iter("item"):
            try:
                published = parsedate_to_datetime(item.findtext("pubDate")).astimezone(WIB)
            except Exception:  # noqa: BLE001
                published = dt.datetime.now(WIB)
            desc = html.unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or ""))
            items.append({"title": html.unescape(item.findtext("title") or ""), "link": item.findtext("link") or "",
                          "desc": desc[:600], "published": published, "src": item.findtext("source") or "Google News"})
        # judul Google News berakhiran " - Nama Media"
        for it in items:
            it["title"] = re.sub(r"\s+-\s+[^-]{2,40}$", "", it["title"])
            for suffix in (it["src"], it["src"].split(" - ")[0]):
                if suffix and it["title"].endswith(" - " + suffix):
                    it["title"] = it["title"][: -len(suffix) - 3]
        out += _items_from_items(items, lambda it: it["src"], universe, now)
        time.sleep(1)
    for source, url in MEDIA_FEEDS:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 idx-screener"})
            items = parse_feed(r.content) if r.ok else []
        except Exception as e:  # noqa: BLE001
            print(f"! RSS {source}: {e}")
            continue
        out += _items_from_items(items, lambda it, s=source: s, universe, now)
    print(f"Berita: {len(out)} transaksi orang dalam terdeteksi")
    return out


# ---------------------------------------------------------------- Gabung & simpan
def merge(prev, new, today):
    by_id = {t["id"]: t for t in prev}
    for t in new:
        if t["id"] in by_id:
            t["first_seen"] = by_id[t["id"]].get("first_seen") or t["first_seen"]
        by_id[t["id"]] = t
    cutoff = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    rows = [t for t in by_id.values() if t.get("date", "") >= cutoff]
    rows.sort(key=lambda t: (t["date"], t.get("first_seen", "")), reverse=True)
    return rows


def net_by_code(rows):
    out = {}
    for t in rows:
        if t.get("is_repo"):
            continue  # repo/gadai bukan keyakinan jual/beli
        d = out.setdefault(t["code"], {"net_shares": 0, "net_value": 0.0, "count": 0})
        sign = 1 if t["action"] == "beli" else -1
        d["net_shares"] += sign * (t.get("shares") or 0)
        d["net_value"] += sign * (t.get("value") or 0.0)
        d["count"] += 1
    return out


def main():
    now_dt = dt.datetime.now(WIB)
    now = now_dt.isoformat(timespec="minutes")
    universe = load_tickers()
    idx_rows, idx_status = fetch_idx_ownership(now)
    news_rows = fetch_news_insider(universe, now)
    # deduplikasi dalam satu putaran (berita yang sama dari beberapa query)
    fresh = list({t["id"]: t for t in idx_rows + news_rows}.values())
    prev = load_json(OUT, {}).get("transactions", [])
    rows = merge(prev, fresh, now_dt.date())
    out = {"updated": now, "sources": {"idx": idx_status, "news": len({t["id"] for t in news_rows})},
           "transactions": rows, "net_by_code": net_by_code(rows)}
    SITE.mkdir(parents=True, exist_ok=True)
    OUT.write_text(__import__("json").dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Tersimpan {OUT}: {len(rows)} transaksi, {len(out['net_by_code'])} emiten")


def self_test():
    assert parse_shares("membeli 388.417.412 lembar saham") == 388417412
    assert parse_shares("melepas 1,2 miliar saham") == 1_200_000_000
    assert parse_shares("harga Rp336 per saham") is None
    assert parse_price("di harga Rp336 per saham") == 336
    assert parse_price("Rp1.250/saham") == 1250
    assert parse_pct("kepemilikan dari 15,09% menjadi 12,06%") == (15.09, 12.06)
    assert parse_pct("dari 5,02% menjadi 0,00%") == (5.02, 0.0)
    assert detect_action("x", 15.09, 12.06) == "jual"
    assert classify_role("Direktur ABCD borong saham") == "direksi_komisaris"
    assert classify_role("", "PT Mandiri Sekuritas") == "sekuritas_mi"
    h1 = "Komisaris Bank Mandiri Ini Tambah Kepemilikan Saham BMRI, Borong 29.100 Saham"
    h2 = "Pengendali HRTA Borong 5 Juta Saham, Kepemilikan Naik Jadi 71,16%"
    h3 = "Direktur BRI Alexander Dippo Borong 1,1 Juta Saham BBRI"
    assert (parse_shares(h1), detect_action(h1), classify_role(h1)) == (29100, "beli", "direksi_komisaris")
    assert (parse_shares(h2), detect_action(h2), classify_role(h2), parse_after_pct(h2)) ==         (5_000_000, "beli", "pengendali", 71.16)
    assert (parse_shares(h3), detect_action(h3), classify_role(h3)) == (1_100_000, "beli", "direksi_komisaris")
    assert parse_party(h3, "BBRI") == "Alexander Dippo", parse_party(h3, "BBRI")
    print("Uji parser: semua lulus")


if __name__ == "__main__":
    self_test()
    if "tes" not in sys.argv[1:]:
        main()
