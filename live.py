"""
Mesin live: dijalankan di komputer pemilik selama jam bursa, karena jadwal GitHub Actions sering
molor 30-45 menit dan kadang terlewat saat pasar buka.

Setiap siklus (default 2 menit) selama jam bursa:
  1. ambil candle hari ini untuk SEMUA saham BEI + IHSG (Yahoo Finance, tertunda ±15 menit dari bursa);
  2. cocokkan dengan setup momentum: tembus entry (dengan proyeksi laju volume), kena SL, kena TP;
  3. kirim alert Telegram/WA seketika (sekali per saham per jenis per hari);
  4. tulis docs/data/live.json -> situs lokal http://localhost:8765 langsung memakai harga terbaru;
  5. tiap 5 menit unggah live.json ke branch `live` di GitHub -> situs publik (HP) ikut terbarui
     tanpa memicu build GitHub Pages (branch `live` selalu satu commit, riwayatnya tidak menumpuk).

Pemakaian:
  python live.py          loop selama jam bursa (biarkan jendela terbuka)
  python live.py sekali   satu siklus lalu berhenti (uji, tidak mengunggah; tambah --unggah untuk mengunggah)
  python live.py --lan    situs lokal juga bisa dibuka dari HP di Wi-Fi yang sama

Telegram: isi TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di file .env.local (tidak ikut di-commit), sama seperti
secret di GitHub. Tanpa itu alert hanya dicetak di layar.
"""

import json
import os
import subprocess
import sys
import threading
import time
import datetime as dt
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).parent
ENV_FILE = BASE / ".env.local"


def load_env():
    """KEY=VALUE per baris; dipasang sebelum `import alert` karena alert membaca environment saat diimpor."""
    if not ENV_FILE.exists():
        return
    for ln in ENV_FILE.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()

import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

import alert  # noqa: E402

SITE = BASE / "docs"
OUT = SITE / "data" / "live.json"
STATE_DIR = BASE / ".live-state"
WIB = dt.timezone(dt.timedelta(hours=7))
CYCLE_SEC = int(os.getenv("LIVE_CYCLE_SEC", 120))
PUSH_MIN = int(os.getenv("LIVE_PUSH_MIN", 5))
PORT = int(os.getenv("LIVE_PORT", 8765))
CHUNK = 250
OPEN, CLOSE = dt.time(8, 55), dt.time(16, 20)  # data Yahoo tertunda ±15 menit setelah penutupan 16:00


def load_universe():
    try:
        return [r["kode"] for r in json.loads((BASE / "data" / "universe.json").read_text(encoding="utf-8"))["rows"]]
    except (OSError, ValueError, KeyError):
        return [ln.strip().upper() for ln in (BASE / "tickers.txt").read_text().splitlines()
                if ln.strip() and not ln.startswith("#")]


def market_open(now):
    return now.weekday() < 5 and OPEN <= now.time() <= CLOSE


# ---------------------------------------------------------------- Harga
def fetch(codes, today):
    """{kode: candle hari ini + tutup kemarin}, dan IHSG. Saham yang belum diperdagangkan hari ini ditandai today=False."""
    out, ihsg = {}, None
    for i in range(0, len(codes), CHUNK):
        part = codes[i:i + CHUNK]
        syms = [f"{c}.JK" for c in part] + (["^JKSE"] if i == 0 else [])
        try:
            df = yf.download(syms, period="5d", interval="1d", group_by="ticker", auto_adjust=False,
                             threads=True, progress=False)
        except Exception as e:  # noqa: BLE001
            print(f"  ! unduh {i + 1}-{i + len(part)} gagal: {e}")
            continue
        for sym in syms:
            try:
                h = df[sym].dropna(subset=["Close"])
            except KeyError:
                continue
            if h.empty:
                continue
            is_today = f"{h.index[-1]:%Y-%m-%d}" == today
            last = float(h["Close"].iloc[-1])
            prev = float(h["Close"].iloc[-2]) if is_today and len(h) > 1 else last
            row = {"last": last, "prev": prev, "chg": last / prev - 1 if prev else 0.0, "today": is_today,
                   "high": float(h["High"].iloc[-1]) if is_today else last,
                   "low": float(h["Low"].iloc[-1]) if is_today else last,
                   "vol": float(h["Volume"].iloc[-1]) if is_today else 0.0}
            if sym == "^JKSE":
                ihsg = row
            else:
                out[sym[:-3]] = row
    return out, ihsg


# ---------------------------------------------------------------- Unggah ke branch `live`
def publish():
    """Satu commit tanpa induk berisi live.json, di-force-push ke refs/heads/live (tidak menyentuh branch kerja)."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "live-bot", "GIT_AUTHOR_EMAIL": "bot@users.noreply.github.com",
           "GIT_COMMITTER_NAME": "live-bot", "GIT_COMMITTER_EMAIL": "bot@users.noreply.github.com"}
    run = partial(subprocess.run, cwd=BASE, env=env, capture_output=True, text=True, check=True)
    try:
        blob = run(["git", "hash-object", "-w", str(OUT)]).stdout.strip()
        tree = run(["git", "mktree"], input=f"100644 blob {blob}\tlive.json\n").stdout.strip()
        commit = run(["git", "commit-tree", tree, "-m", f"live {dt.datetime.now(WIB):%F %H:%M}"]).stdout.strip()
        run(["git", "push", "-f", "-q", "origin", f"{commit}:refs/heads/live"])
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ! unggah ke GitHub gagal: {(e.stderr or e.stdout or '').strip()[:200]}")
        return False


# ---------------------------------------------------------------- Situs lokal
class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):  # jangan banjiri layar dengan log tiap permintaan
        pass


def serve(lan):
    host = "0.0.0.0" if lan else "127.0.0.1"
    try:
        httpd = ThreadingHTTPServer((host, PORT), partial(Handler, directory=str(SITE)))
    except OSError as e:
        print(f"! Situs lokal tidak bisa dibuka di port {PORT} ({e}); mungkin sudah berjalan.")
        return
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"Situs lokal: http://localhost:{PORT}" + ("  (juga dari HP: http://<IP-komputer>:%d)" % PORT if lan else ""))


# ---------------------------------------------------------------- Siklus
def cycle(codes, last_push):
    now = dt.datetime.now(WIB)
    today = f"{now:%Y-%m-%d}"
    t0 = time.time()
    quotes, ihsg = fetch(codes, today)
    m = alert.load()
    state_file = STATE_DIR / f"alert_{today}.json"
    try:
        sent = set(json.loads(state_file.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        sent = set()
    todays = {c: q for c, q in quotes.items() if q["today"]}
    msgs, sig = alert.check(m, todays, now, sent)
    STATE_DIR.mkdir(exist_ok=True)
    state_file.write_text(json.dumps(sorted(sent)), encoding="utf-8")

    r2 = lambda x: round(x, 2)  # noqa: E731
    payload = {
        "updated": now.isoformat(timespec="seconds"),
        "source": "Yahoo Finance via mesin live di komputer pemilik (tertunda ±15 menit dari bursa)",
        "fields": ["last", "chg", "high", "low", "vol"],
        "ihsg": {k: (r2(v) if isinstance(v, float) and k != "chg" else v) for k, v in (ihsg or {}).items()} or None,
        "p": {c: [r2(q["last"]), round(q["chg"], 5), r2(q["high"]), r2(q["low"]), int(q["vol"])]
              for c, q in quotes.items()},
        "sig": sig,
    }
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    tmp.replace(OUT)

    if msgs:
        alert.send(alert.alert_text(now, msgs))
    pushed = ""
    if time.time() - last_push >= PUSH_MIN * 60 - 5:
        if publish():
            last_push = time.time()
            pushed = " · diunggah ke GitHub"
    ih = f"IHSG {ihsg['last']:,.2f} ({ihsg['chg'] * 100:+.2f}%)".replace(",", "_").replace(".", ",").replace("_", ".") if ihsg else "IHSG -"
    n_sig = {k: sum(1 for v in sig.values() if v["ev"] == k) for k in ("tembus_entry", "lewat_zona", "kena_sl", "kena_tp1", "kena_tp2")}
    print(f"{now:%H:%M:%S} {ih} · {len(todays)}/{len(quotes)} saham sudah bertransaksi · "
          f"sinyal {', '.join(f'{k} {v}' for k, v in n_sig.items() if v) or 'tidak ada'} · alert {len(msgs)} · "
          f"{time.time() - t0:.0f} dtk{pushed}")
    return last_push


def main():
    once = "sekali" in sys.argv
    codes = load_universe()
    print(f"Mesin live: {len(codes)} saham, siklus {CYCLE_SEC} detik, unggah tiap {PUSH_MIN} menit."
          + ("" if os.getenv("TELEGRAM_TOKEN") else " Telegram belum diatur (.env.local), alert hanya dicetak."))
    if not once:
        serve("--lan" in sys.argv)
    # mode uji tidak mengunggah ke GitHub kecuali diminta dengan --unggah
    last_push = time.time() if once and "--unggah" not in sys.argv else 0.0
    while True:
        now = dt.datetime.now(WIB)
        if once or market_open(now):
            try:
                last_push = cycle(codes, last_push)
            except Exception as e:  # noqa: BLE001
                print(f"{now:%H:%M:%S} ! siklus gagal: {e}")
            if once:
                return
            time.sleep(max(10, CYCLE_SEC - (dt.datetime.now(WIB) - now).seconds))
        else:
            print(f"{now:%H:%M} di luar jam bursa (Senin-Jumat {OPEN:%H:%M}-{CLOSE:%H:%M} WIB); menunggu…", end="\r")
            time.sleep(300)


if __name__ == "__main__":
    main()
