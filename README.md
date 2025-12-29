# Periodic Table of Boccherini String Quartets

An interactive visualization of Luigi Boccherini's complete string quartet output (1761-1804), displayed as a periodic table-inspired grid.

## Updating the Gist

After making local changes, update the gist using the GitHub CLI:

```bash
# Get your gist ID (do this once)
gh gist list

# Update specific file(s) - replace GIST_ID with your actual gist ID
gh gist edit GIST_ID --add index.html
gh gist edit GIST_ID --add opera.json

# Or update multiple files at once
gh gist edit GIST_ID --add index.html --add opera.json
```

### Streamlined workflow

Save your gist ID to avoid typing it each time:

```bash
# Save the gist ID once
gh gist list | head -1 | awk '{print $1}' > .gist_id

# Update files
gh gist edit $(cat .gist_id) --add index.html

# Create an alias for convenience
alias update-gist='gh gist edit $(cat .gist_id) --add index.html'
```

## Viewing Online

### Using raw.githack.com (Recommended)

Get the raw file URL and use raw.githack.com to serve it:

1. Get the raw URL from your gist:
   ```
   https://gist.githubusercontent.com/USERNAME/GIST_ID/raw/index.html
   ```

2. Replace `gist.githubusercontent.com` with `gist.githack.com`:
   ```
   https://gist.githack.com/USERNAME/GIST_ID/raw/index.html
   ```

**Example for this gist:**
```
https://gist.githack.com/jsundram/a187ff2619b90eaf68d449462b1f9795/raw/index.html
```

### Why raw.githack.com?

- Properly serves files with correct MIME types
- Loads external scripts (like D3.js) without CORS issues
- No rate limiting for development use
- Updates automatically when you update your gist

**Note:** htmlpreview.github.io doesn't work because it can't load external scripts like D3.js.

## Data Overview (opera.json)

### Structure
The data is organized as an array of opus groups, where each opus contains:

```json
{
  "opus": 2,                    // Opus number
  "year": 1761,                 // Year of composition
  "dedication": "...",          // Optional: dedicatee
  "imslp": "...",              // Optional: IMSLP link for the opus
  "quartets": [...]            // Array of quartets in this opus
}
```

Each quartet contains:
```json
{
  "number": 1,                 // Quartet number within opus
  "gerard": 159,               // Gerard catalog number
  "key": "C",                  // Key (e.g., "C", "E-flat")
  "major": false,              // true = major, false = minor
  "nickname": "...",           // Optional: nickname
  "imslp": "...",             // Optional: IMSLP link
  "mvmts": [...],             // Array of movement names
  "category": "opera grande"   // "opera grande" or "opera piccola" variants
}
```

### Data Usage

**Displayed in visualization:**
- Opus number (row header)
- Year and Boccherini's age (row header, top)
- Category: Opera Grande/Piccola (row header, bottom)
- Dedication (row header, when present)
- Gerard catalog number (card header)
- Quartet number within opus (card header)
- Key signature (card center, with ♭ symbol)
- Major/minor mode (card center)
- Movement count with color coding (card bottom)
- Nickname (card center, when present)

**Used in interactions:**
- Individual movement names (shown in hover tooltip)
- IMSLP links (quartet and opus level, opened on click)

**Notable transformations:**
- "-flat" in key names is replaced with the Unicode flat symbol (♭)
- Boccherini's age calculated from birth year (1743)
- Category determines row background gradient color

### Unused/Metadata
All data fields are currently utilized either in the display, tooltips, or interactions. The data is comprehensive and fully integrated.

## Technical Overview (index.html)

### Architecture

**Single-file design:** All HTML, CSS, and JavaScript in one file for easy gist hosting and sharing.

**Technology stack:**
- D3.js v7 for data loading and DOM manipulation
- Pure CSS for styling (no CSS frameworks)
- Vanilla JavaScript (no additional frameworks)

### Design Decisions

**1. Periodic Table Metaphor**
- Square cards (140×140px) arranged in rows by opus
- Each opus group forms a "period" (row)
- Inspired by chemical periodic table organization

**2. Visual Alignment Strategy**
The design emphasizes vertical alignment across three levels:

```
Row Header          ↔  Quartet Cards
─────────────────────────────────────
Year (age)          ↔  Mode bar (G# / quartet #)
Opus number         ↔  Key signature
Category badge      ↔  Movement count
```

This creates strong visual relationships between semantically related information.

**3. Color Encoding System**

**Mode bar (top of each card):**
- Blue (#2196F3): Major keys
- Pink (#E91E63): Minor keys

**Movement count (diverging purple-green palette):**
- 1 movement: Deep purple (#9C27B0) - rare/incomplete
- 2 movements: Light purple (#CE93D8) - opera piccola
- 3 movements: Blue-gray (#B0BEC5) - standard
- 4 movements: Light green (#81C784) - substantial
- 5 movements: Deep green (#2E7D32) - rare/complete

**Category badges use the same palette:**
- Opera Piccola: Light purple (matches 2-movement works)
- Opera Grande: Light green (matches 4-movement works)

**Row background gradients:**
- Subtle gradient (12% opacity) extends from row header toward cards
- Uses category color to create visual flow across the row

**4. Layout System**

**Flexbox throughout:**
- Rows: `display: flex` with `flex-wrap` for cards
- Opus labels: `justify-content: space-between` for vertical distribution
- Cards: `flex-direction: column` for stacking elements

**Height constraints:**
- Opus label and cards both fixed at 140px for alignment
- `flex-grow: 1` on middle sections (opus number, key signature) for vertical centering
- Movement count uses `margin-top: auto` to anchor to bottom

**5. Typography Hierarchy**

Dramatic size contrast in row headers:
- Opus number: 2.8em, weight 900 (ultra bold)
- Year: 0.8em, weight 600
- Age: 0.65em (parenthetical)
- Category badge: 0.65em
- Dedication: 0.6em, italic

### Code Intricacies

**1. Commented sections for easy tweaking**
The opus label CSS and JavaScript are heavily commented with clear section markers (e.g., `=== OPUS LABEL SECTION ===`) to facilitate experimentation with layout and sizing.

**2. Dynamic class application**
Category background gradients are applied dynamically:
```javascript
const categoryClass = opus.quartets[0].category.includes('grande')
  ? 'grande-bg' : 'piccola-bg';
```

**3. Unicode transformation**
Flat symbols are rendered using Unicode replacement:
```javascript
const keyDisplay = quartet.key.replace('-flat', '♭');
```

**4. Nested container pattern**
Cards use multiple nested containers for precise alignment:
- `quartet-card` → `mode-bar` + `card-content`
- `card-content` → `key-section` + `nickname` + `movements-count`

This allows independent control of each vertical section.

**5. Age calculation**
Boccherini's age is calculated inline from a constant:
```javascript
const BOCCHERINI_BIRTH_YEAR = 1743;
const age = opus.year - BOCCHERINI_BIRTH_YEAR;
```

### Browser Compatibility

Requires modern browser support for:
- CSS Flexbox
- Unicode symbols (♭)
- ES6 JavaScript (const, arrow functions, template literals)
- D3.js v7

Tested in Chrome, Firefox, Safari, and Edge (2023+).

---

**Created:** December 2025
**Data source:** Luigi Boccherini quartet catalog (G.159-249)
