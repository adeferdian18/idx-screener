"""
Komposisi kepemilikan saham dari KSEI (bulanan).

Sumber: file publik KSEI "Balancepos" (https://web.ksei.co.id/Download/BalanceposEfekYYYYMMDD.zip),
diterbitkan setiap awal bulan untuk posisi akhir bulan sebelumnya. Isinya jumlah saham per jenis
investor, dipisah lokal dan asing:
  IS asuransi, CP korporasi, PF dana pensiun, IB bank/lembaga keuangan, ID individu (ritel),
  MF reksa dana, SC sekuritas, FD yayasan, OT lainnya.

Yang dihitung per saham: porsi asing, individu lokal, reksa dana, institusi lokal, korporasi, dan
perubahannya dibanding bulan sebelumnya. Catatan: kategori ID KSEI adalah *individu*, termasuk
pengendali/komisaris perorangan, jadi bukan murni ritel kecil. Asing + institusi lokal yang menambah
porsi sementara individu berkurang dibaca sebagai akumulasi; kebalikannya distribusi.

Output: docs/data/ksei.json
"""

import datetime as dt
import io
import json
import zipfile
from pathlib import Path

import requests

BASE = Path(__file__).parent
OUT = BASE / "docs" / "data" / "ksei.json"
URL = "https://web.ksei.co.id/Download/BalanceposEfek{:%Y%m%d}.zip"
HEADERS = {"User-Agent": "Mozilla/5.0 idx-screener (+https://github.com/adeferdian18/idx-screener)"}
WIB = dt.timezone(dt.timedelta(hours=7))
KINDS = ["IS", "CP", "PF", "IB", "ID", "MF", "SC", "FD", "OT"]


def month_end_candidates(year, month):
    """Hari kerja terakhir bulan itu dan beberapa hari sebelumnya (libur bursa)."""
    first_next = dt.date(year + (month == 12), month % 12 + 1, 1)
    d = first_next - dt.timedelta(days=1)
    out = []
    while len(out) < 6 and d.month == month:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return out


def fetch_month(year, month):
    for d in month_end_candidates(year, month):
        try:
            r = requests.get(URL.format(d), headers=HEADERS, timeout=60)
        except Exception as e:  # noqa: BLE001
            print(f"! KSEI {d}: {e}")
            continue
        if r.ok and r.content[:2] == b"PK":
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            text = zf.read(zf.namelist()[0]).decode("latin-1")
            print(f"KSEI {d}: {len(r.content):,} byte")
            return d, parse(text)
    return None, None


def parse(text):
    rows = {}
    lines = text.splitlines()
    header = lines[0].split("|")
    for ln in lines[1:]:
        p = ln.split("|")
        if len(p) != len(header) or p[2] != "EQUITY":
            continue
        try:
            nums = [float(x or 0) for x in p[3:]]
        except ValueError:
            continue
        sec, price = nums[0], nums[1]
        local = dict(zip(KINDS, nums[2:11]))
        foreign = dict(zip(KINDS, nums[12:21]))
        local_total, foreign_total = nums[11], nums[21]
        total = local_total + foreign_total
        if total <= 0:
            continue
        inst_local = sum(local[k] for k in ["IS", "PF", "IB", "MF", "SC", "FD"])  # tanpa individu, korporasi, lainnya
        rows[p[1]] = {
            "harga": price,
            "saham_beredar_ksei": total,
            "asing": foreign_total / total,
            "individu": local["ID"] / total,
            "reksadana": (local["MF"] + foreign["MF"]) / total,
            "institusi_lokal": inst_local / total,
            "korporasi": (local["CP"] + foreign["CP"]) / total,
        }
    return rows


def main():
    today = dt.datetime.now(WIB).date()
    months = []
    y, m = today.year, today.month
    for _ in range(4):  # cari 2 bulan terakhir yang sudah terbit
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        d, rows = fetch_month(y, m)
        if rows:
            months.append((d, rows))
        if len(months) == 2:
            break
    if not months:
        print("KSEI: tidak ada file yang bisa diambil, data lama dipertahankan")
        return
    (d_now, now), prev = months[0], (months[1] if len(months) > 1 else (None, {}))
    d_prev, before = prev
    keys = ["asing", "individu", "reksadana", "institusi_lokal", "korporasi"]
    out = {}
    for code, r in now.items():
        b = before.get(code)
        row = {k: round(r[k], 5) for k in keys}
        row["harga"] = r["harga"]
        if b:
            for k in keys:
                row[f"d_{k}"] = round(r[k] - b[k], 5)
            # akumulasi: asing + institusi lokal (termasuk reksa dana) naik >1 poin, individu turun
            smart = row["d_asing"] + row["d_institusi_lokal"]
            row["d_smart"] = round(smart, 5)
            row["sinyal"] = ("akumulasi" if smart > 0.01 and row["d_individu"] < 0
                             else "distribusi" if smart < -0.01 and row["d_individu"] > 0 else "netral")
        out[code] = row
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated": dt.datetime.now(WIB).isoformat(timespec="minutes"),
        "periode": d_now.isoformat(), "periode_lalu": d_prev.isoformat() if d_prev else None,
        "sumber": "KSEI Balancepos (bulanan)", "rows": out,
    }, ensure_ascii=False))
    akum = sorted((c for c, r in out.items() if r.get("sinyal") == "akumulasi"),
                  key=lambda c: -out[c]["d_smart"])
    print(f"Tersimpan {len(out)} saham, periode {d_now} vs {d_prev}. Akumulasi teratas: {', '.join(akum[:10])}")


if __name__ == "__main__":
    main()
