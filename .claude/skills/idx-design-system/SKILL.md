---
name: idx-design-system
description: Visual rules for Meja Pantau IDX (docs/index.html and docs/js/*.js). Load before writing or reviewing any UI in this repo, so every page uses the same cream theme, fonts, cards and controls, in light and dark mode.
---

# Meja Pantau IDX: design system

Brand is **Meja Pantau IDX**. Never use another product's name, logo, mascot or copy.

## Tokens (defined on `:root` in docs/index.html; never hard-code colors)
| Token | Use |
|---|---|
| `--bg` / `--bg2` | page background / sidebar & inset areas |
| `--surface` | cards, tables, inputs |
| `--ink`, `--muted`, `--faint` | text: primary, secondary, labels |
| `--line`, `--line2` | borders; `--line2` for hover/strong borders |
| `--up` / `--good-soft` | price up, positive, active nav |
| `--down` / `--warn-soft` | price down, risk, stop loss |
| `--accent` / `--accent-soft` | amber: warnings, "watch" states |
| `--blue`, `--orange`, `--teal` | extra series colors (entry line = blue) |
| `--btn` / `--btn-fg` | solid dark buttons, pressed chips |
| `--shadow` | card shadow |
| `--font` (Plus Jakarta Sans), `--serif` (Literata) | body / headings and big numbers |

Dark mode works automatically if only tokens are used. In JS, call `App.dark()` to pick chart themes.

## Components (classes already styled — reuse, do not restyle)
- `.card` (16px radius, border, shadow) with `h2` (serif) and `> p` (muted intro).
- `.toolbar` row of controls; `.chip[aria-pressed]` toggle; `.seg > button[aria-pressed]` segmented; `.search` input; `.ck` checkbox label; `.hint` small muted text.
- `.table-wrap > table` with sticky `th`; first two columns left-aligned, numbers right-aligned; `.up` / `.down` for signed values.
- `.cell` (inset stat box: `<span>label</span><b>value</b>`), `.grid` auto-fill of cells, `.plan` grid of cells.
- `.pill` rounded label, `.badge`, `.badge.good`.
- Clicking a stock: put `data-code="KODE"` on a button/row; the global handler opens the stock detail.

## Rules
- Numbers: `App.fmt(x, d)`, percentages `App.pct(x)` (x is a fraction, 0.05 = 5%). Locale id-ID.
- Escape every data string with `App.esc()` before putting it in HTML.
- Mobile first: works at 375px with no horizontal page scroll (wide tables go inside `.table-wrap`). Bottom nav covers the last 84px; main already has padding for it.
- Indonesian UI copy, short and plain. No "rekomendasi beli/jual"; tools are "alat bantu riset".
- Prefix every new CSS class with the module name (e.g. `.peta-…`) and inject CSS from the module, scoped to its panel.
