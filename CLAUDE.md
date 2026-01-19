# Claude Context for Boccherini Quartets Project

## Project Overview
Boccherini String Quartets Visualization - an interactive periodic table-style grid displaying all 91 of Luigi Boccherini's string quartets (1761-1804). It has 4 main output targets, each supporting both light and dark color modes:
- PDF (print output)
- Desktop
- iPad
- iPhone

**Color Modes**: All targets support both light mode (default) and dark mode via `@media (prefers-color-scheme: dark)` or explicit `.dark-mode` class.

## File Structure
- **Main file**: `index.html` - Single-file architecture: HTML + CSS + JavaScript
- **Data file**: `opera.json` - quartet metadata (opus, year, keys, movements, etc.)
- **Tools**: `tools/` - PDF generation and visual regression testing scripts
- **Baselines**: `baselines/` - Reference screenshots for visual regression testing
- **Documentation**: `README.md` - detailed technical documentation

## Development Workflow

### Preview Changes
- **Local preview**: `http://0.0.0.0:8000/`
- Assume server is running: prompt user to start server if it isn't.

### Visual Regression Testing
Use `tools/visual-diff.py` for automated regression testing across all output formats:

```bash
# Test current index.html against baselines
uv run tools/visual-diff.py test index.html

# Test and open HTML report in browser
uv run tools/visual-diff.py test index.html --open

# Update baselines after intentional changes
uv run tools/visual-diff.py baseline

# Dark mode testing (uses --dark flag)
uv run tools/visual-diff.py baseline --dark      # Generate dark mode baselines
uv run tools/visual-diff.py test index.html --dark --open  # Test dark mode

# Test specific format in dark mode
uv run tools/visual-diff.py test index.html --dark --format pdf
```

The `--dark` flag injects the `.dark-mode` CSS class and emulates `prefers-color-scheme: dark` before capturing screenshots. Dark mode baselines use `-dark` suffix (e.g., `desktop-dark.png`, `pdf-dark.png`). Dark mode works for all formats including PDF/print output.

See **Visual Regression Workflow** section below for detailed instructions.

### Git Updates
- Standard git workflow: `git add`, `git commit`, `git push`
- **Live site**: https://quartets.boccherini.org (via GitHub Pages)

## Design Principles

### Layout System
- **Periodic table metaphor**: Each opus is a row, quartets are cells
- **Card dimensions**: square
- **Flexbox throughout**: Rows, cards, and internal card layout

### Critical Vertical Alignment
Four levels must align across row headers and quartet cards:
1. **Top level**: Year (age) ↔ Mode bar (Gerard# / quartet#)
1. **Text Level**: Dedication ↔ Quartet Nickname
2. **Middle level**: Opus number ↔ Key signature
3. **Bottom level**: Category badge ↔ Movement count

### Color System
The visualization supports both light and dark color modes with semantic color tokens:

**Semantic Colors** (adapt to light/dark mode):
- **Major keys**: No special treatment (uses card background)
- **Minor keys**: Pink (#E91E63) - consistent across both modes
- **Movement counts**: Purple→Green diverging palette (consistent backgrounds, text adapts)
  - 1-2 movements: Purple (rare/piccola)
  - 3 movements: Blue-gray (standard)
  - 4-5 movements: Green (substantial/grande)

**Mode-Specific Backgrounds**:
- **Light mode**: Light gray body (#f5f5f5), white cards (#ffffff)
- **Dark mode**: Dark gray body (#1a1a1a), charcoal cards (#2d2d2d)

### CSS Variables
Use CSS custom properties for shared values to prevent inconsistencies:
- `--card-height`: Card size (square), scales with viewport via `clamp()`
- `--card-gap`: Gap between cards and margins
- `--opus-label-width`: Width of opus label column
- `--top-font-size`, `--middle-font-size`, `--bottom-font-size`: Aligned element sizes
- `--debug-mode`: Set to 1 to show bounding boxes for layout debugging

## Common Tasks

### Checking Alignment
Always verify these alignments after CSS changes:
- Row header year aligns with card mode bar (top)
- Row header opus number aligns with card key signature (middle)
- Row header category badge aligns with card movement count (bottom)

### Adding New Features
1. Read existing code first
2. Use CSS variables for shared dimensions/colors
3. Test alignment with playwright-mcp screenshots
4. Preview at http://0.0.0.0:8000/
5. Commit with descriptive message

### Debugging Layout
- Set `--debug-mode: 1` in CSS to show bounding boxes
- Use browser DevTools to inspect flexbox behavior
- Check that heights match (140px for both opus labels and cards)

### Generating a PDF
Use `uv run tools/generate-pdf.py` to generate PDF output.

## Visual Regression Workflow

### Output Formats
| Format  | Viewport | Media Query        | Notes                        |
|---------|----------|--------------------|------------------------------|
| PDF     | 850×2000 | `@media print`     | Print emulation, fixed sizes |
| Desktop | 1400×900 | Base styles        | Responsive `clamp()` sizing  |
| iPad    | 1024×768 | Base styles        | Responsive, uses WebKit      |
| iPhone  | 375×1150 | Touch device query | Fixed sizes, scaled down     |

**All formats** support both light and dark modes. Dark mode is activated via `@media (prefers-color-scheme: dark)` or the explicit `.dark-mode` CSS class for testing.

### Responsive vs Touch Device Targeting

- **Desktop/iPad**: Use responsive `clamp()` values that scale with viewport
- **iPhone (touch devices)**: Use `@media (hover: none) and (pointer: coarse) and (max-width: 800px)` to target touch-only devices with fixed sizes and `transform: scale()`
- **PDF**: Uses `@media print` with fixed sizes

This means desktop browser windows resized to < 800px still use responsive layout (with horizontal scroll), while actual mobile devices get the optimized scaled view.

### Making Targeted CSS Changes

When making CSS changes that should only affect specific formats:

1. **Specify the target**: PDF, iPhone, iPad, Desktop, or All
2. **Specify the color mode**: Light only, Dark only, or Both
3. **Make the change** using appropriate location:
   - **iPhone only**: `@media (hover: none) and (pointer: coarse) and (max-width: 800px)`
   - **iPad/Desktop**: Base CSS (they share responsive `clamp()` values)
   - **PDF only**: `@media print`
   - **Dark mode colors**: `@media (prefers-color-scheme: dark)` or `.dark-mode` class
   - **Light mode colors**: `:root` defaults
4. **Run regression tests** for both color modes:
   - Light mode: `uv run tools/visual-diff.py test index.html`
   - Dark mode: `uv run tools/visual-diff.py test index.html --dark`
   - **For color changes**: Always test BOTH modes to ensure no unintended changes
5. **Verify results**:
   - Only target format(s) and mode(s) should show FAIL (expected change)
   - Non-target formats/modes should show PASS
6. **Iterate if needed**: If non-target formats/modes changed, revise CSS to isolate
7. **WAIT for user approval**: Do NOT update baselines until user explicitly accepts the change
8. **Update baselines** (only after user approval):
   - Light mode: `uv run tools/visual-diff.py baseline --format <format>`
   - Dark mode: `uv run tools/visual-diff.py baseline --dark --format <format>`

### Important: Baseline Update Policy

**Do NOT automatically update baselines after making changes.** The user needs to inspect the diff report to verify the change is correct before baselines are updated. If baselines are updated prematurely, the diff tool shows nothing useful.

Workflow:
1. Make the CSS change
2. Run `uv run tools/visual-diff.py test index.html` (add `--dark` for dark mode)
3. Share the report for review: `uv run tools/share-diff.py` (add `--dark` for dark mode)
4. Tell user the results and provide the GitHack URL for inspection
5. **Wait for explicit user approval** (e.g., "looks good", "accept", "update baselines")
6. Only then run `uv run tools/visual-diff.py baseline` (add `--dark` for dark mode)

### Sharing Diff Reports (Claude Code Web/Mobile)

In sandboxed environments like Claude Code web/mobile, use `share-diff.py` to upload the visual diff report to a GitHub Gist and get a viewable URL:

```bash
# Share light mode report
uv run tools/share-diff.py

# Share dark mode report
uv run tools/share-diff.py --dark
```

**Authentication** - The script reads `GH_TOKEN` from the environment. In sandboxed environments, this should already be set. Verify with:
```bash
echo $GH_TOKEN  # Should show your GitHub token
```

If not set, create a token with `gist` scope at https://github.com/settings/tokens and set it:
```bash
export GH_TOKEN=your_github_token_here
```

Use the `--dark` flag to specify which report to share. Each mode has its own permanent gist:
- Light mode: https://gist.github.com/jsundram/836fc17f088e333c8387200498a1e434
- Dark mode: https://gist.github.com/jsundram/88dbd41e583cac61762e2c4e562c046f

The script outputs a GitHack URL that renders the HTML report with embedded images.

### Iteration Protocol

If a CSS change produces unexpected results:
1. Analyze the diff report to understand what changed
2. Check if the change leaked to other media queries or color modes
3. Revise CSS to isolate the change properly
4. Re-run tests for both light and dark modes
5. Repeat until only intended format(s) and mode(s) change

### Threshold
Current: **1%** - Changes below this are acceptable noise.

### Key CSS Locations
- **Lines 21-110**: CSS variables (`:root`) - light mode defaults
- **Lines 112-172**: Dark mode colors (`@media (prefers-color-scheme: dark)`)
- **Lines 174-233**: Explicit dark mode class (`.dark-mode`) for testing
- **Lines 291-314**: Header and title styles
- **Lines 434-439**: `.quartets-container` (flex layout, nowrap)
- **Lines 743-858**: `@media print` styles
- **Lines 863-913**: `@media (hover: none) and (pointer: coarse)` mobile/touch styles
