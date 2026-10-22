"""
Fase 4 (A9): notifikasi momentum ke Telegram (dan opsional WhatsApp via Fonnte).

  python alert.py            -> ringkasan harian setelah momentum.py (16:30 WIB): arah pasar, entry trigger baru,
                                setup dekat pivot untuk dipasang alert malam ini, update posisi, pemimpin pasar.
  python alert.py intraday   -> dijalankan tiap 15 menit di jam bursa: kabari saat harga setup menembus entry
                                (beserta laju volume hari ini) atau posisi aktif menyentuh SL. Satu kabar per saham
                                per jenis per hari (status di data/alert_intraday.json).

Harga intraday dari Yahoo tertunda sekitar 15 menit. Ini pengingat, bukan perintah beli/jual.
"""

import json
import os
import sys
import datetime as dt
from pathlib import Path

import requests
import yfinance as yf

BASE = Path(__file__).parent
MOM = BASE / "docs" / "data" / "momentum.json"
STATE = BASE / "data" / "alert_intraday.json"
WIB = dt.timezone(dt.timedelta(hours=7))
SITE_URL = os.getenv("SITE_URL", "https://adeferdian18.github.io/idx-screener/")
LIVE_URL = "https://raw.githubusercontent.com/adeferdian18/idx-screener/live/live.json"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
FONNTE_TOKEN = os.getenv("FONNTE_TOKEN", "")
WA_TARGET = os.getenv("WA_TARGET", "")

AKTIF = ("entry_hari_ini", "entry_baru", "berjalan", "kena_tp1")


def rp(x):
    return f"{x:,.0f}".replace(",", ".") if x is not None else "-"


def pc(x, d=1):
    return (f"{x * 100:+.{d}f}%").replace(".", ",") if x is not None else "-"


# ---------------------------------------------------------------- Kirim
def send(text):
    print(text)
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        chunks, buf = [], ""
        for line in text.split("\n"):
            if len(buf) + len(line) + 1 > 3900:
                chunks.append(buf)
                buf = ""
            buf += line + "\n"
        chunks.append(buf)
        for c in chunks:
            r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", timeout=30, data={
                "chat_id": TELEGRAM_CHAT_ID, "text": c, "parse_mode": "HTML", "disable_web_page_preview": True})
            if not r.ok:
                print("Telegram error:", r.text[:300])
    else:
        print("(Telegram belum diatur, pesan hanya dicetak)")
    if FONNTE_TOKEN and WA_TARGET:
        plain = text.replace("<b>", "*").replace("</b>", "*").replace("<i>", "_").replace("</i>", "_")
        requests.post("https://api.fonnte.com/send", headers={"Authorization": FONNTE_TOKEN},
                      data={"target": WA_TARGET, "message": plain}, timeout=30)


def load():
    return json.loads(MOM.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- Ringkasan harian
def daily():
    m = load()
    p, an, rows = m["pasar"], m.get("analisa", {}), m["rows"]
    tgl = m["tgl_data"]
    lines = [f"🚀 <b>MOMENTUM IDX</b> · data {tgl}", ""]
    lbl = {"uptrend": "🟢 Uptrend", "tertekan": "🟡 Tertekan", "downtrend": "🔴 Downtrend"}[p["status"]]
    b200 = (an.get("breadth") or [{}])[-1].get("di_atas_ma200")
    lines.append(f"Pasar: <b>{lbl}</b> · IHSG {rp(p['ihsg'])} ({pc(p['chg_1d'], 2)})")
    lines.append(f"Saham di atas MA200: {pc(b200, 0).lstrip('+')} · lolos Trend Template: {an.get('n_lolos_tt', '-')} · "
                 f"eksposur disarankan <b>{an.get('eksposur', '-')}</b>")

    def entry_line(z):
        e, b = z["entry"], z.get("briefing") or {}
        return (f"• <b>{z['kode']}</b> RS {z['rs_rating']} · entry {rp(e['entry'])} (maks {rp(e['beli_maks'])}) · "
                f"SL {rp(e['sl'])} ({pc(-e['sl_pct'])}) · TP {rp(e['tp1'])}/{rp(e['tp2'])}"
                + (f"\n   <i>{b['vonis']}</i>" if b.get("vonis") else ""))

    new = [z for z in rows if (z.get("entry") or {}).get("status") == "entry_hari_ini"]
    lines += ["", f"🎯 <b>Entry trigger hari ini ({len(new)})</b>"]
    lines += [entry_line(z) for z in new] or ["Tidak ada."]

    setup = sorted((z for z in rows if (z.get("entry") or {}).get("status") == "setup"),
                   key=lambda z: -(z.get("skor_setup") or 0))
    lines += ["", f"⏳ <b>Setup dekat pivot: pasang alert malam ini ({len(setup)})</b>"]
    lines += [f"• <b>{z['kode']}</b> alert {rp(z['entry']['entry'])} ({pc(z['entry'].get('jarak_pivot'))} dari harga) · "
              f"SL {rp(z['entry']['sl'])} · skor {z.get('skor_setup')}" for z in setup[:10]] or ["Tidak ada."]

    upd = []
    for z in rows:
        e = z.get("entry") or {}
        for k, name in (("tp2", "kena TP2 ✅"), ("tp1", "kena TP1, stop ke impas"), ("sl", "kena SL ❌"), ("impas", "keluar impas")):
            if (e.get("hit") or {}).get(k) == tgl:
                upd.append(f"• <b>{z['kode']}</b> {name} (trigger {e.get('tgl_trigger')})")
                break
    if upd:
        lines += ["", "📊 <b>Update posisi hari ini</b>"] + upd

    aktif = [z for z in rows if (z.get("entry") or {}).get("status") in AKTIF and z["entry"].get("status") != "entry_hari_ini"]
    if aktif:
        lines += ["", "📌 <b>Posisi masih berjalan</b>"]
        lines += [f"• {z['kode']} {z['entry']['label']} · {z['entry'].get('r_sekarang', 0):+.1f}R · SL {rp(z['entry']['sl'])}"
                  for z in aktif]

    if an.get("pemimpin"):
        lines += ["", "🏆 <b>Pemimpin pasar</b>: " + ", ".join(an["pemimpin"][:8])]
    lines += ["", f"Detail grafik & briefing: {SITE_URL}",
              "<i>Data Yahoo Finance. Alat bantu riset, bukan rekomendasi beli/jual.</i>"]
    send("\n".join(lines))


# ---------------------------------------------------------------- Intraday
def session_fraction(now):
    """Porsi jam perdagangan BEI yang sudah lewat (sesi 1 & 2), untuk memproyeksikan volume akhir hari."""
    fri = now.weekday() == 4
    s1 = (dt.time(9, 0), dt.time(11, 30) if fri else dt.time(12, 0))
    s2 = (dt.time(14, 0) if fri else dt.time(13, 30), dt.time(15, 50))
    mins = lambda a, b: (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)  # noqa: E731
    total = mins(*s1) + mins(*s2)
    t = (now - dt.timedelta(minutes=15)).time()  # data Yahoo tertunda ~15 menit
    done = 0
    for a, b in (s1, s2):
        if t >= b:
            done += mins(a, b)
        elif t > a:
            done += mins(a, t)
    return max(done / total, 0.05)


def watch_codes(m):
    """Saham yang dipantau intraday: setup/VCP yang lolos Trend Template dan semua posisi aktif."""
    return sorted({z["kode"] for z in m["rows"] if (z.get("entry") or {}).get("status") in AKTIF
                   or ((z.get("entry") or {}).get("status") in ("setup", "vcp", "volume_kurang")
                       and z["lolos_tt"] and z["likuid"])})


def check(m, quotes, now, sent):
    """Bandingkan harga hari ini dengan level setiap setup.
    quotes: {kode: {"last", "vol", "high", "low"}} hanya untuk candle hari ini.
    Return (pesan alert baru, sinyal live per kode). `sent` (set) diperbarui agar satu alert per jenis per hari."""
    rows = {z["kode"]: z for z in m["rows"]}
    frac = session_fraction(now)
    msgs, sig = [], {}
    for c in watch_codes(m):
        q = quotes.get(c)
        if not q:
            continue
        e = rows[c]["entry"]
        last, vol, hi, lo = q["last"], q["vol"], q.get("high", q["last"]), q.get("low", q["last"])
        v50 = (e.get("vcp") or {}).get("vol50") or (e.get("vcp_info") or {}).get("vol50")
        proj = vol / frac / v50 if v50 else None
        risk = e["entry"] - e["sl"]
        r_now = round((last - e["entry"]) / risk, 2) if risk > 0 else None
        if e["status"] in AKTIF:
            ev = ("kena_sl" if lo <= e["sl"] else "kena_tp2" if hi >= e["tp2"]
                  else "kena_tp1" if hi >= e["tp1"] and e["status"] != "kena_tp1" else "berjalan")
            sig[c] = {"ev": ev, "r": r_now}
            if ev == "kena_sl" and f"sl:{c}" not in sent:
                msgs.append(f"🔻 <b>{c}</b> menyentuh SL {rp(e['sl'])} (harga {rp(last)}, low {rp(lo)}). Sesuai rencana: keluar.")
                sent.add(f"sl:{c}")
            elif ev in ("kena_tp1", "kena_tp2") and f"{ev}:{c}" not in sent:
                lvl = e["tp1"] if ev == "kena_tp1" else e["tp2"]
                todo = "jual 50% dan naikkan stop ke impas" if ev == "kena_tp1" else "ambil untung sisa posisi"
                msgs.append(f"✅ <b>{c}</b> menyentuh {'TP1' if ev == 'kena_tp1' else 'TP2'} {rp(lvl)} (harga {rp(last)}). Rencana: {todo}.")
                sent.add(f"{ev}:{c}")
        elif last >= e["entry"]:
            ev = "lewat_zona" if last > e["beli_maks"] else "tembus_entry"
            sig[c] = {"ev": ev, "pace": round(proj, 2) if proj is not None else None, "r": r_now}
            if f"entry:{c}" not in sent:
                pace = ""
                if proj is not None:
                    pace = (f" Volume sejauh ini diproyeksikan {proj:.1f}".replace(".", ",") + "× rata-rata harian "
                            + ("✅ memenuhi 1,5×." if proj >= 1.5 else "⚠️ belum 1,5×, konfirmasi lemah."))
                zone = " ⚠️ Sudah di atas zona beli, jangan kejar." if ev == "lewat_zona" else ""
                msgs.append(f"⚡ <b>{c}</b> menembus entry {rp(e['entry'])} (harga {rp(last)}, maks {rp(e['beli_maks'])}). "
                            f"SL {rp(e['sl'])}, TP {rp(e['tp1'])}/{rp(e['tp2'])}.{pace}{zone}")
                sent.add(f"entry:{c}")
        else:
            sig[c] = {"ev": "menunggu", "jarak": round(last / e["entry"] - 1, 4)}
    return msgs, sig


def alert_text(now, msgs):
    return (f"⏱️ <b>ALERT MOMENTUM</b> {now:%H:%M} WIB (harga tertunda ±15 menit)\n\n" + "\n\n".join(msgs)
            + f"\n\n{SITE_URL}")


def live_engine_active(max_age_min=12):
    """True jika mesin live di komputer pemilik (live.py) baru saja memperbarui branch `live`:
    alert intraday dari GitHub dilewati supaya tidak terkirim dua kali."""
    try:
        r = requests.get(LIVE_URL, timeout=15)
        upd = dt.datetime.fromisoformat(r.json()["updated"])
        return (dt.datetime.now(WIB) - upd).total_seconds() < max_age_min * 60
    except Exception:  # noqa: BLE001
        return False


def intraday():
    now = dt.datetime.now(WIB)
    today = f"{now:%Y-%m-%d}"
    if live_engine_active():
        print("Mesin live di komputer pemilik aktif; alert intraday dari GitHub dilewati.")
        return
    m = load()
    codes = watch_codes(m)
    if not codes:
        print("Tidak ada saham untuk dipantau.")
        return
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    sent = set(state.get(today, []))
    df = yf.download([f"{c}.JK" for c in codes], period="5d", interval="1d", group_by="ticker",
                     auto_adjust=False, threads=True, progress=False)
    quotes = {}
    for c in codes:
        try:
            h = df[f"{c}.JK"].dropna(subset=["Close"]) if len(codes) > 1 else df.dropna(subset=["Close"])
        except KeyError:
            continue
        if h.empty or f"{h.index[-1]:%Y-%m-%d}" != today:
            continue
        quotes[c] = {"last": float(h["Close"].iloc[-1]), "vol": float(h["Volume"].iloc[-1]),
                     "high": float(h["High"].iloc[-1]), "low": float(h["Low"].iloc[-1])}
    msgs, _ = check(m, quotes, now, sent)
    state = {today: sorted(sent)}  # simpan hanya hari ini
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state), encoding="utf-8")
    if msgs:
        send(alert_text(now, msgs))
    else:
        print(f"{now:%H:%M}: {len(codes)} saham dipantau, belum ada yang menembus entry/SL/TP.")


if __name__ == "__main__":
    intraday() if len(sys.argv) > 1 and sys.argv[1] == "intraday" else daily()
