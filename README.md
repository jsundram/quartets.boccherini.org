# Periodic Table of Boccherini String Quartets

An interactive visualization of Luigi Boccherini's complete string quartet output (1761-1804), displayed as a periodic table-inspired grid.

**Live site:** https://quartets.boccherini.org

**Printable PDF:** https://quartets.boccherini.org/print.pdf

## About

91 string quartets organized by opus (rows) with cards showing:
- Gerard catalog number and key signature
- Major/minor mode (blue/pink)
- Movement count (purple→green gradient)
- Nickname (when applicable)

Click any card to open the score on IMSLP. Hover for movement details.

## Progressive Web App

The site is an installable, offline-capable PWA:

- **Offline:** a service worker (`sw.js`) precaches the app shell (HTML, JSON data,
  d3, icons) on first load, so the table works with no network afterward. Shell
  files are served network-first (data updates land on the next reload) and images
  cache-first. Cross-origin score links still need connectivity, naturally.
- **Installable:** `manifest.json` + a periodic-table "element" icon (`Bc`, 91 —
  regenerate the PNGs from the SVGs with `./make-icons.sh`, needs `librsvg` +
  `pngquant`).
- **Shareable:** Open Graph / Twitter Card metadata with a share image
  (`index-preview.png`, a real screenshot of the layout — regenerate with
  `uv run tools/make-og.py`).

> **Cache-busting:** bump `V` in `sw.js` whenever you change a precached shell file
> (`index.html`, the JSON data, etc.), or installed copies keep the stale version.
> The pre-commit hook runs `tools/sw_lint.py` to warn if you forget.

## Data (opera.json)

The visualization is driven by `opera.json`, an array of opus groups:

```json
{
  "opus": 2,
  "year": 1761,
  "dedication": "Don Carlos III",
  "quartets": [
    {
      "number": 1,
      "gerard": 159,
      "key": "C",
      "major": true,
      "mvmts": ["Allegro moderato", "Largo", "Allegro"],
      "category": "opera piccola"
    }
  ]
}
```

## Development

See `CLAUDE.md` for development workflow, visual regression testing, and CSS architecture.

```bash
# Local preview
python -m http.server 8000
open http://localhost:8000

# After cloning, enable pre-commit hook (auto-generates PDF)
git config core.hooksPath hooks
```

## Credits

The PWA layer (offline service worker, installable manifest, share-card and icon
tooling, and the `sw_lint` cache-version guard) follows the pattern from
[jsundram/pwa-starter](https://github.com/jsundram/pwa-starter), by way of its
sibling project [jsundram/haydn-info-card](https://github.com/jsundram/haydn-info-card).

---

**Data source:** Luigi Boccherini quartet catalog (G.159-249)
