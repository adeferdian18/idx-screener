---
name: idx-qa
description: Checklist for verifying a change to Meja Pantau IDX in a real browser (desktop, mobile, dark mode, console). Load before reporting any UI work as done.
---

# QA checklist

1. Serve locally: `python -m http.server 8765 -d docs` (from the repo root, in the background) and open http://localhost:8765/.
2. Open the tab you changed. Check:
   - No errors in the browser console.
   - Data renders (not stuck on "Memuat…"); empty states read sensibly.
   - Clicking a stock opens the detail dialog.
3. Viewport 375×812: no horizontal page scroll (`document.documentElement.scrollWidth === innerWidth`), text readable, controls tappable, nothing hidden behind the bottom nav.
4. Dark mode: `localStorage.theme='dark'` then reload. All text has contrast; no hard-coded light colors.
5. Reload: the tab and any saved inputs persist where expected.
6. Report what you checked and anything you could not check. Never claim a check you did not run.
