"""
Fase 4 (A9): notifikasi momentum ke Telegram (dan opsional WhatsApp via Fonnte).

  python alert.py            -> ringkasan harian setelah momentum.py (16:30 WIB): arah pasar, entry trigger baru,
                                setup dekat pivot untuk dipasang alert malam ini, update posisi, pemimpin pasar.
  python alert.py intraday   -> dijalankan tiap 15 menit di jam bursa: kabari saat harga setup menembus entry
                                (beserta laju volume hari ini) atau posisi aktif menyentuh SL. Satu kabar per saham
                                per jenis per hari (status di data/alert_intraday.json).
  python alert.py pullback   -> setelah `python pullback.py` (penutupan): Entry hari ini baru, Kena TP/SL, daftar
                                Menunggu trigger. Tambah `s1` untuk snapshot Sesi 1 (hanya terkirim bila ada kabar).
                                Status terkirim di data/alert_pullback.json agar Sesi 1 dan penutupan tidak dobel.
  Pantauan intraday pullback (calon trigger, sentuh SL/TP) ada di pullback_live(), dipanggil live.py.

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


# ---------------------------------------------------------------- Pullback (saham kuat yang sedang pullback)
# Data dari pullback.py (lihat spesifikasi_pullback.md bagian 7). Semua akses kolom memakai .get()
# supaya alert tetap jalan walau ada kolom yang kosong/null.
PB_FILES = {"close": BASE / "docs" / "data" / "pullback.json", "s1": BASE / "docs" / "data" / "pullback_s1.json"}
PB_STATE = BASE / "data" / "alert_pullback.json"
PB_EXIT = ("Kena TP", "Kena SL", "Kena SL, naik lagi")
PB_AKTIF = ("Entry hari ini", "Entry baru")
PB_POLA = ("Bullish Engulfing", "Hammer", "Inverted Hammer", "Piercing Line", "Bullish Harami",
           "Morning Star", "Bullish Marubozu")
RISIKO_RP = 1_000_000  # risiko per transaksi untuk hitung lot (sama dengan situs referensi)


def num(x, d=1):
    """Angka desimal gaya Indonesia (1,4); '-' bila kosong."""
    return f"{x:.{d}f}".replace(".", ",") if isinstance(x, (int, float)) else "-"


def load_pullback(session=None):
    """Isi pullback.json / pullback_s1.json. Tanpa `session`: pilih snapshot yang paling baru dibuat."""
    out = []
    for s, f in PB_FILES.items():
        if session and s != session:
            continue
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append((str((m.get("market") or {}).get("generated_at") or ""), m))
    return max(out, key=lambda t: t[0])[1] if out else None


def pb_labels(r):
    lab = (["Syariah"] if r.get("syariah") else []) + (["⚠️ HSC"] if r.get("hsc") else [])
    return (" · " + " · ".join(lab)) if lab else ""


def pb_entry_text(r, tentative=False):
    lot = lambda x: f" · {x} lot" if x else ""  # noqa: E731
    vol = f" · volume {num(r.get('trig_vol_x'))}× rata-rata 5 hari" if r.get("trig_vol_x") is not None else ""
    return (f"• <b>{r['code']}</b> {r.get('pattern') or '-'} · Ranking 3 Bulan {num(r.get('rs3m_x'), 0)} · "
            f"Skor Momentum {num(r.get('rs_rating'), 0)}{vol}{pb_labels(r)}\n"
            f"   ATR: entry {rp(r.get('atr_entry'))} · SL {rp(r.get('atr_sl'))} · TP {rp(r.get('atr_tp'))}{lot(r.get('atr_lot'))}\n"
            f"   N-candle: beli di atas {rp(r.get('n_entry'))} · SL {rp(r.get('n_sl'))} · TP {rp(r.get('n_tp'))}{lot(r.get('n_lot'))}"
            + (" · <i>candle belum tutup</i>" if tentative else ""))


def pullback_daily(session="close"):
    """Alert dari snapshot pullback (dipanggil workflow setelah pullback.py):
    Entry hari ini yang baru, Kena TP / Kena SL hari ini; snapshot penutupan juga menyebut saham Menunggu trigger.
    Status terkirim disimpan di data/alert_pullback.json ({kunci: tanggal}) agar Sesi 1 dan penutupan tidak dobel."""
    m = load_pullback(session)
    if not m:
        print(f"{PB_FILES[session].name} belum ada; alert pullback dilewati.")
        return
    mk, rows = m.get("market") or {}, m.get("rows") or []
    as_of = mk.get("as_of") or f"{dt.datetime.now(WIB):%Y-%m-%d}"
    try:
        state = json.loads(PB_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    batas = f"{dt.date.fromisoformat(as_of) - dt.timedelta(days=40)}"
    state = {k: v for k, v in state.items() if v >= batas}  # buang riwayat lama
    s1 = session == "s1"

    entries = sorted((r for r in rows if r.get("status") == "Entry hari ini"), key=lambda r: -(r.get("rs3m_x") or 0))
    baru, konfirmasi = [], []
    for r in entries:
        key = f"entry:{r['code']}:{r.get('signal_date')}"
        if key in state:
            continue
        if not s1 and f"{key}:s1" in state:
            konfirmasi.append(r["code"])
        elif s1 and f"{key}:s1" in state:
            continue
        else:
            baru.append(r)
        state[key + (":s1" if s1 else "")] = as_of
    batal = []
    if not s1:  # entry yang terlihat di Sesi 1 tapi hilang di penutupan
        kode_entry = {r["code"] for r in entries}
        for k, v in list(state.items()):
            if k.startswith("entry:") and k.endswith(":s1") and v == as_of:
                code = k.split(":")[1]
                if code not in kode_entry and f"batal:{code}:{as_of}" not in state:
                    batal.append(code)
                    state[f"batal:{code}:{as_of}"] = as_of

    exits = []
    for r in rows:
        # status tetap "Entry baru" selama 5 hari; hasil posisi (SL/TP tetap metode ATR) ada di atr_trade
        if r.get("atr_trade") not in PB_EXIT or r.get("atr_exit_date") != as_of:
            continue
        key = f"exit:{r['code']}:{r.get('signal_date')}"
        if key in state:
            continue
        state[key] = as_of
        tp = r["atr_trade"] == "Kena TP"
        exits.append(f"• {'✅' if tp else '🔻'} <b>{r['code']}</b> {r['atr_trade']} "
                     f"di {rp(r.get('atr_exit') or (r.get('atr_tp') if tp else r.get('atr_sl')))} "
                     f"(entry {rp(r.get('atr_entry'))}, trigger {r.get('signal_date') or '-'})")

    menunggu = sorted((r for r in rows if r.get("status") == "Menunggu trigger"), key=lambda r: -(r.get("rs3m_x") or 0))
    ada_kabar = baru or konfirmasi or batal or exits
    if not ada_kabar and s1:
        print(f"Pullback {mk.get('session_label') or session} {as_of}: tidak ada entry/TP/SL baru.")
    else:
        lbl = mk.get("session_label") or ("Sesi 1" if s1 else "Penutupan")
        lines = [f"📐 <b>PULLBACK IDX</b> · {lbl} {as_of}"]
        if mk.get("ihsg_close") is not None:
            lines.append(f"IHSG {rp(mk.get('ihsg_close'))} · {mk.get('regime') or '-'} "
                         f"({num(mk.get('ihsg_dist'))}% dari MA50)")
        lines += ["", f"🎯 <b>Entry hari ini ({len(baru)})</b>" + (" · <i>sementara, candle Sesi 1 belum tutup</i>" if s1 else "")]
        lines += [pb_entry_text(r, s1) for r in baru] or ["Tidak ada yang baru."]
        if konfirmasi:
            lines.append("Terkonfirmasi di penutupan (sudah dikabarkan Sesi 1): " + ", ".join(konfirmasi))
        if batal:
            lines.append("⚠️ Batal di penutupan (syarat trigger tidak terpenuhi lagi): " + ", ".join(batal))
        if exits:
            lines += ["", "📊 <b>Update posisi</b>"] + exits
        if not s1 and menunggu:
            lines += ["", f"⏳ <b>Menunggu trigger ({len(menunggu)})</b>: "
                      + ", ".join(f"{r['code']} ({r.get('watch_days_left') if r.get('watch_days_left') is not None else '-'})"
                                  for r in menunggu[:15]) + (" …" if len(menunggu) > 15 else ""),
                      "<i>Angka dalam kurung = sisa candle jendela trigger.</i>"]
        lines += ["", f"Detail: {SITE_URL}",
                  "<i>Data Yahoo Finance. Alat bantu riset, bukan rekomendasi beli/jual.</i>"]
        send("\n".join(lines))
    PB_STATE.parent.mkdir(exist_ok=True)
    PB_STATE.write_text(json.dumps(dict(sorted(state.items())), indent=0), encoding="utf-8")


def pb_pattern(bars):
    """Pola candle bullish di candle terakhir. bars: list (open, high, low, close), terlama dulu, min 1 candle.
    Dipakai bila pullback.py tidak menyediakan fungsi pola sendiri."""
    o, h, l, c = bars[-1]
    body, rng = abs(c - o), max(h - l, 1e-9)
    up_sh, lo_sh = h - max(o, c), min(o, c) - l
    p1 = bars[-2] if len(bars) >= 2 else None
    p2 = bars[-3] if len(bars) >= 3 else None
    green = c > o
    if p1:
        po, _, _, pc_ = p1
        pbody = abs(pc_ - po)
        p_red = pc_ < po
        if p2 and p2[3] < p2[0] and abs(p2[3] - p2[0]) > 0 and pbody <= 0.5 * abs(p2[3] - p2[0]) \
                and green and c > (p2[0] + p2[3]) / 2:
            return "Morning Star"
        if p_red and green and o <= pc_ and c >= po and body > pbody:
            return "Bullish Engulfing"
        if p_red and green and o < pc_ and (pc_ + po) / 2 < c < po:
            return "Piercing Line"
        if p_red and green and pbody > 0 and o >= pc_ and c <= po and body < pbody:
            return "Bullish Harami"
    if green and body >= 0.9 * rng:
        return "Bullish Marubozu"
    if body > 0 and lo_sh >= 2 * body and up_sh <= body:
        return "Hammer"
    if body > 0 and up_sh >= 2 * body and lo_sh <= body:
        return "Inverted Hammer"
    return None


def _pb_pattern_fn():
    """Fungsi pola dari pullback.py bila ada (nama yang dicoba di bawah); selain itu pb_pattern."""
    try:
        import pullback  # noqa: PLC0415
        for name in ("detect_pattern", "bullish_pattern", "candle_pattern"):
            fn = getattr(pullback, name, None)
            if callable(fn):
                return fn
    except Exception:  # noqa: BLE001
        pass
    return None


def _tick_round(p, arah):
    try:
        import vcp  # noqa: PLC0415
        return vcp.up(p) if arah > 0 else vcp.down(p)
    except Exception:  # noqa: BLE001
        return round(p)


def pullback_watch(pb):
    """Kode yang dipantau live: Menunggu trigger + posisi Entry aktif."""
    return sorted({r["code"] for r in (pb or {}).get("rows") or []
                   if r.get("status") == "Menunggu trigger" or r.get("status") in PB_AKTIF})


def pullback_live(pb, quotes, prev, now, sent):
    """Cek intraday setup pullback (dipanggil live.py tiap siklus).
    quotes: {kode: {"open","last","high","low","vol"}} candle hari ini; prev: {kode: [(o,h,l,c,v), ...]} candle
    sebelum hari ini, terlama dulu. `sent` diperbarui: satu alert per saham per jenis per hari.
    Return (pesan, sinyal per kode)."""
    today = f"{now:%Y-%m-%d}"
    frac = session_fraction(now)
    pat_fn = _pb_pattern_fn()
    msgs, sig = [], {}
    for r in (pb or {}).get("rows") or []:
        c, st = r.get("code"), r.get("status")
        q = quotes.get(c)
        if not q or st not in ("Menunggu trigger",) + PB_AKTIF:
            continue
        last, hi, lo = q["last"], q.get("high", q["last"]), q.get("low", q["last"])
        if st in PB_AKTIF:
            if (r.get("signal_date") or today) >= today:  # posisi baru dimulai candle berikutnya
                continue
            if r.get("atr_trade") in ("Kena SL", "Kena TP"):  # posisi sudah selesai (status tetap "Entry baru")
                continue
            sl, tp = r.get("atr_sl"), r.get("atr_tp")
            ev = "kena_sl" if sl and lo <= sl else "kena_tp" if tp and hi >= tp else "berjalan"
            sig[c] = {"ev": ev}
            if ev != "berjalan" and f"pb_{ev}:{c}" not in sent:
                sent.add(f"pb_{ev}:{c}")
                msgs.append(f"🔻 <b>{c}</b> (pullback) menyentuh SL {rp(sl)} (harga {rp(last)}, low {rp(lo)}). Sesuai rencana: keluar."
                            if ev == "kena_sl" else
                            f"✅ <b>{c}</b> (pullback) menyentuh TP {rp(tp)} (harga {rp(last)}, high {rp(hi)}). Rencana: ambil untung.")
            continue
        # Menunggu trigger: candle hari ini hijau + pola bullish + laju volume >= 1,1x rata-rata 5 hari sebelumnya
        o = q.get("open")
        hist = prev.get(c) or []
        if o is None or len(hist) < 5:
            continue
        avg5 = sum(b[4] for b in hist[-5:]) / 5
        proj = q["vol"] / frac / avg5 if avg5 else None
        bars = [tuple(b[:4]) for b in hist[-2:]] + [(o, hi, lo, last)]
        pola = None
        if pat_fn:
            try:
                import pandas as pd  # noqa: PLC0415
                pola = pat_fn(pd.DataFrame(bars, columns=["Open", "High", "Low", "Close"]))
            except Exception:  # noqa: BLE001
                pola = None
        pola = pola if pola in PB_POLA else pb_pattern(bars)
        green = last > o
        ok = bool(green and pola and proj is not None and proj >= 1.1 and (r.get("rs_rating") or 0) >= 70)
        sig[c] = {"ev": "calon_trigger" if ok else "menunggu", "pola": pola,
                  "pace": round(proj, 2) if proj is not None else None}
        if ok and f"pb_calon:{c}" not in sent:
            sent.add(f"pb_calon:{c}")
            atr = r.get("atr")
            lv = ""
            if atr:
                sl, tp = _tick_round(last - 1.5 * atr, -1), _tick_round(last + 3 * atr, 1)
                lot = int(RISIKO_RP // ((last - sl) * 100)) if last > sl else None
                lv = f"\n   Bila tutup di sini (ATR): entry ±{rp(last)} · SL {rp(sl)} · TP {rp(tp)}" + (f" · {lot} lot" if lot else "")
            msgs.append(f"🔷 <b>{c}</b> calon entry trigger pullback: candle hijau, {pola}, laju volume diproyeksikan "
                        f"{num(proj)}× rata-rata 5 hari (harga {rp(last)}, open {rp(o)}). Ranking 3 Bulan "
                        f"{num(r.get('rs3m_x'), 0)} · Skor Momentum {num(r.get('rs_rating'), 0)}{pb_labels(r)}"
                        f"{lv}\n   <i>Belum sah sampai candle tutup; sisa jendela {r.get('watch_days_left', '-')} candle.</i>")
    return msgs, sig


def pullback_alert_text(now, msgs):
    return (f"📐 <b>ALERT PULLBACK</b> {now:%H:%M} WIB (harga tertunda ±15 menit)\n\n" + "\n\n".join(msgs)
            + f"\n\n{SITE_URL}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "intraday":
        intraday()
    elif mode == "pullback":
        pullback_daily("s1" if "s1" in sys.argv[2:] else "close")
    else:
        daily()
