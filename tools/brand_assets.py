"""Gambar aset merek Meja Pantau IDX: docs/og.png (1200x630), ikon PWA 192/512 (maskable),
apple-touch-icon 180, dan docs/favicon.svg. Jalankan: python tools/brand_assets.py"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DOCS = Path(__file__).resolve().parent.parent / "docs"
BG, BG2, INK, MUTED, LINE = "#F6F2EA", "#EFE9DD", "#17242A", "#56625F", "#E5DDD0"
ACC, UP, DOWN, CREAM = "#A86F1C", "#1D7A5C", "#C4554A", "#F6F2EA"
F = "C:/Windows/Fonts/"

def font(names, size):
    for n in names:
        try: return ImageFont.truetype(F + n, size)
        except OSError: pass
    return ImageFont.load_default()

# Batang naik + garis tren: dipakai di ikon (koordinat dalam kotak 0..1)
BARS = [(0.22, 0.62), (0.38, 0.50), (0.54, 0.40), (0.70, 0.26)]  # (x tengah, puncak)
TREND = [(0.16, 0.66), (0.38, 0.46), (0.54, 0.52), (0.84, 0.20)]

def icon(size, pad=0.0, radius=0.22):
    """pad: zona aman maskable (ikon digambar dalam kotak lebih kecil di atas latar penuh)."""
    s = size * 4
    im = Image.new("RGB", (s, s), INK)
    d = ImageDraw.Draw(im)
    if pad == 0:
        im = Image.new("RGBA", (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * radius), fill=INK)
    o, w = s * pad, s * (1 - 2 * pad)
    P = lambda x, y: (o + x * w, o + y * w)
    bw = w * 0.10
    for x, top in BARS:
        x0, y0 = P(x, top); _, y1 = P(x, 0.80)
        d.rounded_rectangle([x0 - bw / 2, y0, x0 + bw / 2, y1], radius=int(bw * 0.25), fill=BG2)
    d.line([P(*p) for p in TREND], fill=ACC, width=int(w * 0.065), joint="curve")
    cx, cy = P(*TREND[-1]); r = w * 0.06
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACC)
    return im.resize((size, size), Image.LANCZOS)

def og():
    W, H = 1200, 630
    im = Image.new("RGB", (W * 2, H * 2), BG); d = ImageDraw.Draw(im)
    S = lambda *v: [x * 2 for x in v]
    # kisi halus
    for y in range(120, 600, 60): d.line(S(720, y, 1140, y), fill=LINE, width=2)
    # grafik candle sederhana yang naik
    import math
    x, price = 740, 470
    for i in range(18):
        o = price; c = price - 9 + 18 * math.sin(i * 1.7) * 0.6 - 6
        hi, lo = min(o, c) - 12, max(o, c) + 12
        col = UP if c < o else DOWN
        d.line(S(x + 8, hi, x + 8, lo), fill=col, width=4)
        d.rectangle(S(x, min(o, c), x + 16, max(o, c) + 2), fill=col)
        price = c; x += 22
    pts = [(740, 490), (820, 450), (900, 420), (980, 350), (1060, 300), (1140, 240)]
    d.line([tuple(S(*p)) for p in pts], fill=ACC, width=8, joint="curve")
    # logo kecil
    ic = icon(96); im.paste(ic, (120, 120), ic)
    serif = font(["georgiab.ttf", "georgia.ttf"], 152)
    sans = font(["segoeui.ttf", "arial.ttf"], 60)
    sansb = font(["seguisb.ttf", "arialbd.ttf"], 44)
    d.text((120, 300), "Meja Pantau", font=serif, fill=INK)
    d.text((120, 470), "IDX", font=serif, fill=ACC)
    d.text((120, 690), "Screener saham Bursa Efek Indonesia", font=sans, fill=INK)
    d.text((120, 780), "Momentum · VCP · Pullback · KSEI", font=sans, fill=MUTED)
    url, uf = "adeferdian18.github.io/idx-screener", font(["segoeui.ttf", "arial.ttf"], 38)
    tw = d.textlength(url, font=uf)
    d.rounded_rectangle([120, 1060, 120 + tw + 80, 1060 + 96], radius=48, fill=INK)
    d.text((160, 1080), url, font=uf, fill=CREAM)
    im.resize((W, H), Image.LANCZOS).save(DOCS / "og.png", optimize=True)

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="{INK}"/>
{''.join(f'<rect x="{x*64-3.2:.1f}" y="{t*64:.1f}" width="6.4" height="{(0.80-t)*64:.1f}" rx="1.6" fill="{BG2}"/>' for x, t in BARS)}
<polyline points="{' '.join(f'{x*64:.1f},{y*64:.1f}' for x, y in TREND)}" fill="none" stroke="{ACC}" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="{TREND[-1][0]*64:.1f}" cy="{TREND[-1][1]*64:.1f}" r="3.8" fill="{ACC}"/>
</svg>
"""

if __name__ == "__main__":
    og()
    icon(192, pad=0.12).save(DOCS / "icon-192.png", optimize=True)
    icon(512, pad=0.12).save(DOCS / "icon-512.png", optimize=True)
    icon(180, pad=0.10).save(DOCS / "apple-touch-icon.png", optimize=True)
    (DOCS / "favicon.svg").write_text(SVG, encoding="utf-8")
    print("ok")
