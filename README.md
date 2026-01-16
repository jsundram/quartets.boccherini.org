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

---

**Data source:** Luigi Boccherini quartet catalog (G.159-249)
