"""
Fase 3: briefing per saham dan analisa pasar, berbasis aturan (bukan opini).
Dipakai momentum.py; hasilnya ikut di docs/data/momentum.json supaya website dan notifikasi
memakai kalimat yang sama.

  - skor_setup(): 0-100, menggabungkan RS, Trend Template, RS Line, ketahanan, kualitas VCP, arah pasar.
  - briefing(): vonis, tingkat (valid/siap/pantau/selesai/tidak), kenapa kuat, kenapa hati-hati, langkah berikutnya.
  - pasar(): breadth (berapa % saham di atas MA50/MA200, rekor high/low 52 minggu), sektor terkuat,
    panduan eksposur, dan riwayat breadth 120 hari.
"""

import math

import pandas as pd

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

SEKTOR_ID = {
    "Commercial Services": "Jasa komersial", "Communications": "Telekomunikasi",
    "Consumer Durables": "Barang konsumen tahan lama", "Consumer Non-Durables": "Barang konsumen primer",
    "Consumer Services": "Jasa konsumen", "Distribution Services": "Distribusi",
    "Electronic Technology": "Teknologi elektronik", "Energy Minerals": "Energi & batu bara", "Finance": "Keuangan",
    "Health Services": "Layanan kesehatan", "Health Technology": "Farmasi & alat kesehatan",
    "Industrial Services": "Jasa industri", "Miscellaneous": "Lain-lain", "Non-Energy Minerals": "Tambang non-energi",
    "Process Industries": "Industri dasar & agribisnis", "Producer Manufacturing": "Manufaktur",
    "Retail Trade": "Ritel", "Technology Services": "Teknologi", "Transportation": "Transportasi",
    "Utilities": "Utilitas",
}


# ---------------------------------------------------------------- Format angka gaya Indonesia
def ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def rp(x):
    return f"{x:,.0f}".replace(",", ".") if ok(x) else "-"


def pc(x, d=0, sign=True):
    if not ok(x):
        return "-"
    s = f"{x * 100:+.{d}f}" if sign else f"{x * 100:.{d}f}"
    return s.replace(".", ",") + "%"


def tgl(s):
    if not s:
        return "-"
    y, m, d = s.split("-")
    return f"{int(d)} {BULAN[int(m) - 1]}"


def lin(x, bad, good):
    if not ok(x):
        return 0.0
    return max(0.0, min(1.0, (x - bad) / (good - bad)))


# ---------------------------------------------------------------- Skor setup
def skor_setup(z, status_pasar):
    """0-100. Bobot: RS 25, Trend Template 20, kualitas VCP 25, RS Line 10, ketahanan 10, HGM 5, pasar 5."""
    rs = z.get("rs_rating") or 0
    s = rs / 99 * 25 + z["tt_skor"] / 8 * 20
    g = z.get("hgm") or {}
    s += (g.get("skor") or 0) / 3 * 5
    s += 10 if z.get("rs_line_mendahului") else 7 if z.get("rs_line_high") else 3 if z.get("rs_line_naik_1b") else 0
    s += lin(z.get("ketahanan"), -0.10, 0.30) * 10
    e = z.get("entry") or {}
    v = e.get("vcp") or {}
    # pola yang sudah dipakai (trade selesai / gagal) tidak lagi menjadi peluang
    if v.get("valid") and e.get("status") not in ("kena_sl", "time_stop", "kena_tp2", "tp1_impas", "extended"):
        s += 15 + (5 if v.get("ketat") else 0) + (5 if v.get("kering") else 0)
    s += {"uptrend": 5, "tertekan": 2}.get(status_pasar, 0)
    return round(s)


# ---------------------------------------------------------------- Briefing per saham
def briefing(z, pasar, tt_labels):
    st_pasar = pasar["status"]
    e = z.get("entry") or {}
    v = e.get("vcp") or {}
    hit = e.get("hit") or {}
    rs = z.get("rs_rating")
    kuat, hati = [], []

    if ok(rs) and rs >= 90:
        kuat.append(f"RS Rating {rs}: kinerjanya mengalahkan sekitar {rs}% saham BEI")
    elif ok(rs) and rs >= 70:
        kuat.append(f"RS Rating {rs}, lolos syarat minimum tapi belum di zona 90+")
    elif ok(rs):
        hati.append(f"RS Rating {rs} di bawah 70: kalah dari mayoritas saham")
    if z.get("rs_line_mendahului"):
        kuat.append("RS Line sudah cetak rekor 52 minggu sebelum harganya (jejak akumulasi)")
    elif z.get("rs_line_high"):
        kuat.append("RS Line di puncak 52 minggu")
    elif z.get("rs_line_naik_1b") is False:
        hati.append("RS Line turun sebulan terakhir")
    k = z.get("ketahanan")
    if ok(k) and k > 0:
        kuat.append(f"{pc(k)} lebih kuat dari IHSG saat koreksi terakhir")
    elif ok(k) and k < 0:
        hati.append(f"lebih lemah dari IHSG saat koreksi terakhir ({pc(k)})")
    gagal = [tt_labels[i] for i, x in enumerate(z["tt"]) if x is False]
    if gagal:
        hati.append("gagal Trend Template: " + "; ".join(gagal).lower())
    if v.get("valid"):
        kuat.append("VCP valid (" + " → ".join(pc(d, 0, False) for d in v["kedalaman"]) + ")"
                    + (", volume mengering" if v.get("kering") else ""))
    elif v.get("alasan"):
        hati.append("pola VCP belum terbentuk: " + "; ".join(v["alasan"]))
    g = z.get("hgm")
    if g and g.get("skor") is not None:
        rinci = (f"laba {pc(g.get('laba_yoy'))} YoY, penjualan {pc(g.get('penjualan_yoy'))}, margin "
                 f"{pc(g.get('margin'), 1, False)} (setahun lalu {pc(g.get('margin_lalu'), 1, False)}), kuartal {g['kuartal']}")
        if g["skor"] == 3:
            kuat.append("fundamental HGM kuat: " + rinci + (", laba berakselerasi" if g.get("akselerasi") else ""))
        else:
            gagal_f = [n for n, okk in (("laba > 20%", g["cek"]["laba"]), ("penjualan > 15%", g["cek"]["penjualan"]),
                                       ("margin melebar", g["cek"]["margin"])) if not okk]
            hati.append(f"fundamental belum HGM penuh ({g['skor']}/3, kurang: {', '.join(gagal_f)}): " + rinci)
    elif g:
        hati.append("data laporan kuartalan di Yahoo tidak lengkap; cek laporan keuangan di idx.co.id")
    for k in z.get("katalis") or []:
        teks = f"katalis {k['jenis'].lower()} ({tgl(k['tgl'])}): {k['judul']}"
        (kuat if (k.get("sinyal") or 0) > 0 else hati).append(teks)
    if e.get("risiko_ok") is False:
        hati.append("stop loss struktur lebih lebar dari 8%")
    if e.get("extended"):
        hati.append("harga sudah lebih dari 5% di atas entry, jangan dikejar")
    if st_pasar != "uptrend":
        hati.append(f"arah pasar {st_pasar}, breakout lebih sering gagal")
    hati += [f.lower() for f in z["flags"]]

    st = e.get("status")
    lolos = z["lolos_tt"] and z["likuid"]
    kecil = "" if st_pasar == "uptrend" else " Pasar belum uptrend: pakai separuh ukuran posisi normal."
    if st == "kena_sl":
        tingkat, vonis = "selesai", f"Trigger {tgl(e['tgl_trigger'])} sudah kena SL pada {tgl(hit.get('sl'))}."
        langkah = "Posisi ditutup sesuai rencana. Tunggu basis baru minimal 2 minggu sebelum menilai lagi."
    elif st == "sl_naik_lagi":
        tingkat, vonis = "pantau", f"Sempat kena SL ({tgl(hit.get('sl'))}) dan kini naik lagi di atas SL."
        langkah = "Jangan masuk lagi tanpa pivot baru. Kembali ke watchlist dan tunggu basis baru."
    elif st == "time_stop":
        tingkat, vonis = "selesai", f"Time stop: {e['hari_sejak']} hari bursa sejak trigger belum naik 1R."
        langkah = "Keluar dan pindahkan modal ke setup lain yang bergerak."
    elif st == "kena_tp1":
        tingkat, vonis = "selesai", f"TP1 tercapai {tgl(hit.get('tp1'))}, stop sudah di titik impas."
        langkah = f"Biarkan sisa posisi berjalan ke TP2 {rp(e['tp2'])}; stop di {rp(e['entry'])}."
    elif st == "kena_tp2":
        tingkat, vonis = "selesai", f"Trade selesai di TP2 ({tgl(hit.get('tp2'))}), +3R."
        langkah = "Ambil untung sudah terjadi. Tunggu basis baru sebelum masuk lagi."
    elif st == "tp1_impas":
        tingkat, vonis = "selesai", f"TP1 tercapai {tgl(hit.get('tp1'))}, sisa posisi keluar impas {tgl(hit.get('impas'))}."
        langkah = "Trade selesai dengan untung. Tunggu basis baru."
    elif st == "extended":
        tingkat, vonis = "pantau", f"Sudah lewat zona beli (maks {rp(e['beli_maks'])})."
        langkah = "Jangan kejar. Tunggu pullback ke area pivot atau basis baru."
    elif st == "volume_kurang":
        tingkat, vonis = "pantau", "Harga tembus pivot tanpa volume konfirmasi (< 1,5× rata-rata 50 hari)."
        langkah = f"Belum valid. Eksekusi hanya jika ada candle tutup di atas {rp(e['entry'])} dengan volume besar."
    elif not lolos:
        tingkat, vonis = "tidak", "Belum valid untuk strategi momentum."
        langkah = "Abaikan dulu; fokus ke saham yang lolos 8 poin Trend Template."
    elif st in ("entry_hari_ini", "entry_baru", "berjalan") and e.get("risiko_ok"):
        tingkat = "valid"
        vonis = ("Entry trigger VALID: Stage 2, VCP, breakout pivot dengan volume, risiko dalam batas."
                 if st_pasar == "uptrend" else f"Entry trigger terjadi, tapi pasar sedang {st_pasar}.")
        langkah = (f"Beli di {rp(e['entry'])} sampai maksimal {rp(e['beli_maks'])}, SL {rp(e['sl'])}, "
                   f"TP1 {rp(e['tp1'])}, TP2 {rp(e['tp2'])}." + kecil)
    elif st in ("entry_hari_ini", "entry_baru", "berjalan"):
        tingkat, vonis = "pantau", "Entry trigger terjadi, tapi stop loss struktur lebih lebar dari 8%."
        langkah = "Risiko tidak ideal menurut modul. Lewati, atau kecilkan posisi agar rugi tetap ≤ 1,25% modal."
    elif st == "setup":
        tingkat, vonis = "siap", f"Setup siap: harga {pc(e.get('jarak_pivot'), 1)} dari entry {rp(e['entry'])}."
        langkah = (f"Pasang price alert di {rp(e['entry'])}. Beli hanya jika candle tutup di atas entry dengan "
                   f"volume ≥ 1,5× rata-rata; SL {rp(e['sl'])}." + kecil)
    elif st == "vcp":
        tingkat, vonis = "pantau", "VCP terbentuk, harga masih lebih dari 5% di bawah entry."
        langkah = f"Pantau. Pasang alert di {rp(e['entry'])}."
    else:
        tingkat, vonis = "pantau", "Kandidat watchlist Stage 2, pola VCP belum terbentuk."
        langkah = "Tunggu kontraksi menyusut dan volume mengering, jangan beli hanya karena lolos filter."
    return {"tingkat": tingkat, "vonis": vonis, "kuat": kuat, "hati": hati, "langkah": langkah}


# ---------------------------------------------------------------- Analisa pasar
def _breadth_hist(frames, codes, ihsg, days=120):
    close = pd.DataFrame({c: frames[c]["Close"] for c in codes}).reindex(ihsg.index).ffill(limit=3)
    ma50, ma200 = close.rolling(50).mean(), close.rolling(200).mean()
    hi52, lo52 = close.rolling(252, min_periods=200).max(), close.rolling(252, min_periods=200).min()
    out = []
    for d in close.index[-days:]:
        c = close.loc[d]
        a50 = (c > ma50.loc[d])[ma50.loc[d].notna()]
        a200 = (c > ma200.loc[d])[ma200.loc[d].notna()]
        out.append({
            "t": f"{d:%Y-%m-%d}", "ihsg": round(float(ihsg.loc[d]), 2),
            "di_atas_ma50": round(float(a50.mean()), 4) if len(a50) else None,
            "di_atas_ma200": round(float(a200.mean()), 4) if len(a200) else None,
            "high52": int((c >= hi52.loc[d] * 0.999).sum()), "low52": int((c <= lo52.loc[d] * 1.001).sum()),
        })
    return out


def _eksposur(status, b200):
    if status == "uptrend":
        return "75–100%" if ok(b200) and b200 >= 0.5 else "50–75%"
    if status == "tertekan":
        return "25–50%"
    return "0–25%"


def pasar(pasar_dict, rows, frames, ihsg):
    liq = [z for z in rows if z["likuid"]]
    hist = _breadth_hist(frames, [z["kode"] for z in liq], ihsg)
    now, lalu = hist[-1], hist[-22] if len(hist) > 22 else hist[0]

    sek = {}
    for z in liq:
        sek.setdefault(z["sektor"], []).append(z)
    sektor = []
    for name, zs in sek.items():
        if len(zs) < 3:
            continue
        rss = sorted(z["rs_rating"] for z in zs if ok(z.get("rs_rating")))
        if not rss:
            continue
        r3 = [z["ret_3m"] for z in zs if ok(z.get("ret_3m"))]
        sektor.append({
            "sektor": SEKTOR_ID.get(name, name), "n": len(zs),
            "rs_median": rss[len(rss) // 2], "stage2": sum(1 for z in zs if z["stage"] == 2),
            "lolos_tt": sum(1 for z in zs if z["lolos_tt"]),
            "ret_3m": round(sum(r3) / len(r3), 4) if r3 else None,
            "pemimpin": [z["kode"] for z in sorted(zs, key=lambda z: -(z.get("rs_rating") or 0))[:3]],
        })
    sektor.sort(key=lambda s: (-s["rs_median"], -s["lolos_tt"]))

    n_tt = sum(1 for z in liq if z["lolos_tt"])
    n_s2 = sum(1 for z in liq if z["stage"] == 2)
    b200, b200_lalu = now["di_atas_ma200"], lalu["di_atas_ma200"]
    arah = "naik" if ok(b200) and ok(b200_lalu) and b200 > b200_lalu + 0.02 else \
        "turun" if ok(b200) and ok(b200_lalu) and b200 < b200_lalu - 0.02 else "datar"
    eks = _eksposur(pasar_dict["status"], b200)
    top = ", ".join(s["sektor"].lower() for s in sektor[:3])
    teks = (f"{pasar_dict['catatan']} Hanya {pc(b200, 0, False)} saham likuid di atas MA200 "
            f"(sebulan lalu {pc(b200_lalu, 0, False)}, arah {arah}); {n_s2} saham di Stage 2 dan {n_tt} lolos Trend Template. "
            f"Rekor high 52 minggu hari ini: {now['high52']} saham, rekor low: {now['low52']}. "
            f"Sektor dengan RS terkuat: {top}. Panduan eksposur modal di saham: {eks}.")
    if ok(b200) and b200 >= 0.5:
        teks = teks.replace("Hanya ", "")
    return {"teks": teks, "eksposur": eks, "breadth_arah": arah, "n_lolos_tt": n_tt, "n_stage2": n_s2,
            "n_likuid": len(liq), "sektor": sektor, "breadth": hist}
