---
name: idx-feature-module
description: How to add a new page/feature to Meja Pantau IDX as a self-contained module in docs/js/<name>.js, without touching docs/index.html. Load when building any new tab (heatmap, calculator, journal, ownership, etc.).
---

# Adding a feature module

The site is a static GitHub Pages app: `docs/index.html` + JSON in `docs/data/`. New features live in their own file so several people can work in parallel.

## Contract
`docs/index.html` already has, for each module, a sidebar button `.tab[data-tab="<name>"]`, an empty `<section class="panel" id="panel-<name>" hidden>`, and a `<script src="js/<name>.js" defer>`. Your file must only do:

```js
App.register("<name>", {
  // called the first time the tab opens, and again after each data refresh (every 60 s) while visible
  render(el, ctx){ /* el = the panel <section>; build its innerHTML */ },
});
```

`ctx` / global `App` gives you:
- `App.S` — loaded data: `S.momentum` (rows: kode, nama, sektor, harga, chg_1d, ret_1m/3m/6m/12m, nilai_rata2, likuid, rs_rating, ma50/150/200, high52, low52, dari_high52 …), `S.quotes` (stocks{KODE:{last,prev,chg,volume,value}}, ihsg), `S.screener` (fundamental rows), `S.ksei` (rows{KODE:{asing,individu,reksadana,institusi_lokal,korporasi, d_* changes, d_smart, sinyal}}, periode), `S.insider`, `S.actions`. Any can be null while loading — render a short "Memuat data…" and return.
- `App.getJSON(name)` to fetch `docs/data/<name>.json` yourself if needed.
- Helpers: `App.fmt, App.pct, App.esc, App.cls, App.isNum, App.dark()`, `App.store.get/set` (localStorage, safe).
- `App.openStock(code)` opens the stock detail; or put `data-code="KODE"` on any clickable element.

## Rules
- Do not edit `docs/index.html` or other modules. Inject your CSS once via a `<style id="<name>-css">` appended to `document.head`, all selectors prefixed `#panel-<name>`.
- Follow the `idx-design-system` skill (tokens, `.card`, `.toolbar`, `.chip`, `.table-wrap`).
- Keep state in module-scope variables; re-render must be idempotent and keep the user's filters/inputs (don't wipe a form the user is typing in on refresh — render the shell once, then update parts).
- No external libraries unless already loaded on the page. Plain DOM + SVG.
- Vanilla JS, no build step, must parse in current Chrome/Safari.
- Test with the `idx-qa` skill before reporting done.
