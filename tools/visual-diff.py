#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "playwright>=1.40.0",
#     "pillow>=10.0.0",
# ]
# ///
"""
Visual Regression Testing Tool for Boccherini Quartets

Captures screenshots of the visualization at different viewport sizes and
compares them to detect unintended visual changes.

Usage:
    python visual-diff.py baseline [FILE]     Generate baseline images
    python visual-diff.py test FILE           Compare FILE against baselines
    python visual-diff.py compare A B         Compare two HTML files directly

Options:
    --format FORMAT     Only test specific format: pdf|desktop|ipad|iphone
    --threshold FLOAT   Pixel diff threshold (default: 0.01 = 1%)
    --open              Open HTML report in browser after completion
    --dark              Enable dark mode (adds .dark-mode CSS class)
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import webbrowser

from datetime import datetime
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

# Viewport configurations for each format
FORMATS = {
    'pdf': {'width': 850, 'height': 2000, 'print': True, 'full_page': False, 'browser': 'chromium'},  # letter width, tall enough for all content
    'desktop': {'width': 1400, 'height': 900, 'print': False, 'full_page': True, 'browser': 'chromium'},
    'ipad': {'width': 1024, 'height': 768, 'print': False, 'full_page': True, 'browser': 'webkit', 'touch': True},
    'iphone': {'width': 375, 'height': 1150, 'print': False, 'full_page': False, 'browser': 'webkit', 'device_scale_factor': 3, 'touch': True},  # 375px @ 3x retina
}

# Directories - project root is parent of tools/
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
BASELINES_DIR = PROJECT_ROOT / 'baselines'
DIFFS_DIR = PROJECT_ROOT / 'diffs'

# Default threshold (1%)
DEFAULT_THRESHOLD = 0.01


def ensure_server_running(port=8000):
    """Check if local dev server is running."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', port))
    sock.close()
    if result != 0:
        print(f"ERROR: Local server not running on port {port}")
        print("Start the server with: python -m http.server 8000")
        sys.exit(1)


def capture_screenshot(page, format_name, config, output_path, dark_mode=False):
    """Capture a screenshot for the given format configuration."""
    # Set viewport size
    page.set_viewport_size({'width': config['width'], 'height': config['height']})

    # Enable print media emulation if needed
    color_scheme = 'dark' if dark_mode else 'light'
    if config.get('print'):
        page.emulate_media(media='print', color_scheme=color_scheme)
    else:
        page.emulate_media(media='screen', color_scheme=color_scheme)

    # Wait for any animations/transitions to settle
    page.wait_for_timeout(500)

    # Take screenshot
    page.screenshot(
        path=str(output_path),
        full_page=config.get('full_page', True)
    )

    return output_path


def capture_all_formats(html_file, output_dir, formats=None, dark_mode=False):
    """Capture screenshots for all formats from an HTML file."""
    if formats is None:
        formats = list(FORMATS.keys())

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine URL
    if html_file == 'index.html':
        url = 'http://localhost:8000/'
    else:
        url = f'http://localhost:8000/{html_file}'

    results = {}

    # File suffix for dark mode
    suffix = '-dark' if dark_mode else ''

    # Group formats by browser type
    formats_by_browser = {}
    for format_name in formats:
        if format_name not in FORMATS:
            print(f"Unknown format: {format_name}")
            continue
        browser_type = FORMATS[format_name].get('browser', 'chromium')
        if browser_type not in formats_by_browser:
            formats_by_browser[browser_type] = []
        formats_by_browser[browser_type].append(format_name)

    with sync_playwright() as p:
        for browser_type, browser_formats in formats_by_browser.items():
            # Launch the appropriate browser
            if browser_type == 'webkit':
                browser = p.webkit.launch()
            else:
                browser = p.chromium.launch()

            for format_name in browser_formats:
                config = FORMATS[format_name]
                output_path = output_dir / f'{format_name}{suffix}.png'

                # Create page with device options
                device_scale_factor = config.get('device_scale_factor', 1)
                has_touch = config.get('touch', False)
                page = browser.new_page(device_scale_factor=device_scale_factor, has_touch=has_touch)
                page.goto(url)
                page.wait_for_load_state('networkidle')

                # Enable dark mode by adding CSS class
                if dark_mode:
                    page.evaluate("document.documentElement.classList.add('dark-mode')")

                capture_screenshot(page, format_name, config, output_path, dark_mode=dark_mode)
                results[format_name] = output_path

                browser_label = f" [{browser_type}]" if browser_type != 'chromium' else ""
                scale_label = f" @{device_scale_factor}x" if device_scale_factor > 1 else ""
                dark_label = " (dark)" if dark_mode else ""
                print(f"  Captured {format_name}{suffix}: {config['width']}x{config['height']}" +
                      (" (print)" if config.get('print') else "") + browser_label + scale_label + dark_label)

                page.close()

            browser.close()

    return results


def compute_diff(baseline_path, test_path, diff_path):
    """Compare two images and generate a diff image."""
    baseline = Image.open(baseline_path).convert('RGBA')
    test = Image.open(test_path).convert('RGBA')

    # Normalize sizes by padding smaller image with white
    max_width = max(baseline.width, test.width)
    max_height = max(baseline.height, test.height)

    size_mismatch = baseline.size != test.size

    if size_mismatch:
        # Pad images to same size
        baseline_padded = Image.new('RGBA', (max_width, max_height), (255, 255, 255, 255))
        baseline_padded.paste(baseline, (0, 0))
        baseline = baseline_padded

        test_padded = Image.new('RGBA', (max_width, max_height), (255, 255, 255, 255))
        test_padded.paste(test, (0, 0))
        test = test_padded

    width, height = max_width, max_height
    total_pixels = width * height

    # Create diff image - white background with baseline faded, changes highlighted
    diff_image = Image.new('RGB', (width, height), (255, 255, 255))

    baseline_data = baseline.load()
    test_data = test.load()
    diff_data = diff_image.load()

    diff_pixels = 0
    diff_locations = []

    for y in range(height):
        for x in range(width):
            b_pixel = baseline_data[x, y]
            t_pixel = test_data[x, y]

            if b_pixel != t_pixel:
                diff_pixels += 1
                diff_locations.append((x, y))
                # Bright red for changed pixels
                diff_data[x, y] = (255, 0, 0)
            else:
                # Faded grayscale version of baseline for context
                gray = int(0.299 * b_pixel[0] + 0.587 * b_pixel[1] + 0.114 * b_pixel[2])
                faded = 230 + int((gray - 230) * 0.3)  # Very light gray
                diff_data[x, y] = (faded, faded, faded)

    # Expand diff markers to make them more visible (3x3 blocks)
    for x, y in diff_locations:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    diff_data[nx, ny] = (255, 0, 0)

    diff_percent = (diff_pixels / total_pixels) * 100

    # Save diff image
    diff_path = Path(diff_path)
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_image.save(diff_path)

    result = {
        'diff_pixels': diff_pixels,
        'total_pixels': total_pixels,
        'diff_percent': diff_percent,
        'diff_path': diff_path
    }

    if size_mismatch:
        result['size_mismatch'] = True
        result['baseline_size'] = Image.open(baseline_path).size
        result['test_size'] = Image.open(test_path).size

    return result


def generate_html_report(results, threshold, output_path, dark_mode=False):
    """Generate an HTML report with side-by-side comparisons."""
    suffix = '-dark' if dark_mode else ''
    mode_label = " (Dark Mode)" if dark_mode else ""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visual Regression Report{mode_label} - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{ margin-bottom: 10px; }}
        .summary {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .summary table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .summary th, .summary td {{
            text-align: left;
            padding: 10px;
            border-bottom: 1px solid #eee;
        }}
        .pass {{ color: #2e7d32; font-weight: bold; }}
        .fail {{ color: #c62828; font-weight: bold; }}
        .format-section {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .format-section h2 {{
            margin-top: 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .status-badge {{
            font-size: 12px;
            padding: 4px 8px;
            border-radius: 4px;
            text-transform: uppercase;
        }}
        .status-badge.pass {{ background: #e8f5e9; color: #2e7d32; }}
        .status-badge.fail {{ background: #ffebee; color: #c62828; }}
        .comparison {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
        }}
        .comparison-item {{
            text-align: center;
        }}
        .comparison-item h3 {{
            margin: 0 0 10px 0;
            font-size: 14px;
            color: #666;
        }}
        .comparison-item img {{
            max-width: 100%;
            border: 1px solid #ddd;
            border-radius: 4px;
            cursor: zoom-in;
        }}
        .comparison-item img:hover {{
            transform: scale(1.02);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .zoom-modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
            z-index: 1000;
            cursor: zoom-out;
            overflow: auto;
        }}
        .zoom-modal img {{
            max-width: 100%;
            margin: 20px auto;
            display: block;
        }}
        .zoom-modal.active {{ display: block; }}
    </style>
</head>
<body>
    <h1>Visual Regression Report{mode_label}</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p>Threshold: {threshold * 100:.2f}%</p>

    <div class="summary">
        <h2>Summary</h2>
        <table>
            <tr>
                <th>Format</th>
                <th>Status</th>
                <th>Diff %</th>
                <th>Pixels Changed</th>
            </tr>
"""

    for format_name, result in results.items():
        status = 'pass' if result['diff_percent'] <= threshold * 100 else 'fail'
        status_text = 'PASS' if status == 'pass' else 'FAIL'

        size_note = ""
        if result.get('size_mismatch'):
            b_size = result['baseline_size']
            t_size = result['test_size']
            size_note = f" (size: {b_size[0]}x{b_size[1]} → {t_size[0]}x{t_size[1]})"

        html += f"""
            <tr>
                <td>{format_name}</td>
                <td class="{status}">{status_text}</td>
                <td>{result['diff_percent']:.4f}%{size_note}</td>
                <td>{result['diff_pixels']:,} / {result['total_pixels']:,}</td>
            </tr>
"""

    html += """
        </table>
    </div>
"""

    # Individual format sections
    for format_name, result in results.items():
        status = 'pass' if result['diff_percent'] <= threshold * 100 else 'fail'
        status_text = 'PASS' if status == 'pass' else 'FAIL'

        html += f"""
    <div class="format-section">
        <h2>
            {format_name.upper()}
            <span class="status-badge {status}">{status_text}</span>
            <span style="font-weight: normal; font-size: 14px; color: #666;">
                {result['diff_percent']:.4f}% difference
            </span>
        </h2>
        <div class="comparison">
            <div class="comparison-item">
                <h3>Baseline</h3>
                <img src="../baselines/{format_name}{suffix}.png" alt="Baseline" onclick="zoomImage(this)">
            </div>
            <div class="comparison-item">
                <h3>Current</h3>
                <img src="{format_name}{suffix}-test.png" alt="Current" onclick="zoomImage(this)">
            </div>
            <div class="comparison-item">
                <h3>Difference</h3>
                <img src="{format_name}{suffix}-diff.png" alt="Diff" onclick="zoomImage(this)">
            </div>
        </div>
    </div>
"""

    html += """
    <div id="zoomModal" class="zoom-modal" onclick="closeZoom()">
        <img id="zoomImg" src="" alt="Zoomed">
    </div>

    <script>
        function zoomImage(img) {
            document.getElementById('zoomImg').src = img.src;
            document.getElementById('zoomModal').classList.add('active');
        }
        function closeZoom() {
            document.getElementById('zoomModal').classList.remove('active');
        }
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeZoom();
        });
    </script>
</body>
</html>
"""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)

    return output_path


def cmd_baseline(args):
    """Generate baseline images."""
    html_file = args.file or 'index.html'
    formats = [args.format] if args.format else None
    dark_mode = getattr(args, 'dark', False)

    mode_label = " (dark mode)" if dark_mode else ""
    print(f"Generating baselines from {html_file}{mode_label}...")
    ensure_server_running()

    results = capture_all_formats(html_file, BASELINES_DIR, formats, dark_mode=dark_mode)

    suffix = '-dark' if dark_mode else ''
    print(f"\nBaselines saved to {BASELINES_DIR}/")
    for format_name, path in results.items():
        print(f"  {format_name}{suffix}.png")

    return 0


def cmd_test(args):
    """Test a file against baselines."""
    html_file = args.file
    threshold = args.threshold
    formats = [args.format] if args.format else list(FORMATS.keys())
    dark_mode = getattr(args, 'dark', False)

    suffix = '-dark' if dark_mode else ''
    mode_label = " (dark mode)" if dark_mode else ""

    print(f"Testing {html_file} against baselines{mode_label}...")
    ensure_server_running()

    # Check baselines exist
    missing_baselines = []
    for format_name in formats:
        baseline_path = BASELINES_DIR / f'{format_name}{suffix}.png'
        if not baseline_path.exists():
            missing_baselines.append(format_name)

    if missing_baselines:
        print(f"ERROR: Missing baselines for: {', '.join(missing_baselines)}")
        dark_flag = ' --dark' if dark_mode else ''
        print(f"Run 'python visual-diff.py baseline{dark_flag}' first")
        return 1

    # Capture test screenshots
    print("\nCapturing test screenshots...")
    test_results = capture_all_formats(html_file, DIFFS_DIR, formats, dark_mode=dark_mode)

    # Rename test screenshots and compute diffs
    print("\nComparing against baselines...")
    diff_results = {}

    for format_name in formats:
        test_path = DIFFS_DIR / f'{format_name}{suffix}.png'
        test_renamed = DIFFS_DIR / f'{format_name}{suffix}-test.png'
        baseline_path = BASELINES_DIR / f'{format_name}{suffix}.png'
        diff_path = DIFFS_DIR / f'{format_name}{suffix}-diff.png'

        # Rename test file
        if test_path.exists():
            test_path.rename(test_renamed)

        # Compute diff
        result = compute_diff(baseline_path, test_renamed, diff_path)
        diff_results[format_name] = result

    # Generate HTML report
    report_name = 'report-dark.html' if dark_mode else 'report.html'
    report_path = generate_html_report(diff_results, threshold, DIFFS_DIR / report_name, dark_mode=dark_mode)

    # Print console summary
    print("\n" + "=" * 70)
    print(f"Visual Regression Test Results{mode_label}")
    print("=" * 70)
    print(f"{'Format':<12} {'Status':<10} {'Diff %':<25} {'Threshold':<10}")
    print("-" * 70)

    failures = 0
    for format_name, result in diff_results.items():
        passed = result['diff_percent'] <= threshold * 100
        status = 'PASS' if passed else 'FAIL'
        diff_str = f"{result['diff_percent']:.4f}%"
        if result.get('size_mismatch'):
            b = result['baseline_size']
            t = result['test_size']
            diff_str += f" ({b[0]}x{b[1]}→{t[0]}x{t[1]})"
        if not passed:
            failures += 1

        print(f"{format_name:<12} {status:<10} {diff_str:<25} {threshold*100:.2f}%")

    print("-" * 70)

    if failures > 0:
        print(f"\n{failures} format(s) failed threshold check.")
    else:
        print("\nAll formats passed!")

    print(f"Report: {report_path}")

    if args.open:
        webbrowser.open(f'http://localhost:8000/diffs/{report_name}')

    return 1 if failures > 0 else 0


def cmd_compare(args):
    """Compare two HTML files directly."""
    file_a = args.file_a
    file_b = args.file_b
    threshold = args.threshold
    formats = [args.format] if args.format else list(FORMATS.keys())

    print(f"Comparing {file_a} vs {file_b}...")
    ensure_server_running()

    # Create temp directories
    dir_a = DIFFS_DIR / 'compare_a'
    dir_b = DIFFS_DIR / 'compare_b'

    # Capture screenshots for both files
    print(f"\nCapturing screenshots from {file_a}...")
    results_a = capture_all_formats(file_a, dir_a, formats)

    print(f"\nCapturing screenshots from {file_b}...")
    results_b = capture_all_formats(file_b, dir_b, formats)

    # Compute diffs
    print("\nComputing differences...")
    diff_results = {}

    for format_name in formats:
        path_a = dir_a / f'{format_name}.png'
        path_b = dir_b / f'{format_name}.png'
        diff_path = DIFFS_DIR / f'{format_name}-diff.png'

        # Copy files with descriptive names
        shutil.copy(path_a, DIFFS_DIR / f'{format_name}-a.png')
        shutil.copy(path_b, DIFFS_DIR / f'{format_name}-b.png')

        result = compute_diff(path_a, path_b, diff_path)
        diff_results[format_name] = result

    # Generate report (modified for compare mode)
    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Compare: {file_a} vs {file_b}</title>
    <style>
        body {{ font-family: sans-serif; padding: 20px; background: #f5f5f5; }}
        .section {{ background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; }}
        .comparison {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }}
        .comparison img {{ max-width: 100%; border: 1px solid #ddd; }}
        .pass {{ color: #2e7d32; }}
        .fail {{ color: #c62828; }}
    </style>
</head>
<body>
    <h1>Comparison: {file_a} vs {file_b}</h1>
    <p>Threshold: {threshold * 100:.2f}%</p>
"""

    for format_name, result in diff_results.items():
        status = 'pass' if result['diff_percent'] <= threshold * 100 else 'fail'
        report_html += f"""
    <div class="section">
        <h2>{format_name.upper()} - <span class="{status}">{result['diff_percent']:.4f}%</span></h2>
        <div class="comparison">
            <div><h3>{file_a}</h3><img src="{format_name}-a.png"></div>
            <div><h3>{file_b}</h3><img src="{format_name}-b.png"></div>
            <div><h3>Difference</h3><img src="{format_name}-diff.png"></div>
        </div>
    </div>
"""

    report_html += "</body></html>"

    report_path = DIFFS_DIR / 'compare-report.html'
    report_path.write_text(report_html)

    # Print summary
    print("\n" + "=" * 60)
    print(f"Comparison: {file_a} vs {file_b}")
    print("=" * 60)

    failures = 0
    for format_name, result in diff_results.items():
        passed = result['diff_percent'] <= threshold * 100
        status = 'PASS' if passed else 'FAIL'
        if not passed:
            failures += 1
        print(f"{format_name:<12} {status:<10} {result['diff_percent']:.4f}%")

    print(f"\nReport: {report_path}")

    if args.open:
        webbrowser.open('http://localhost:8000/diffs/report.html')

    return 1 if failures > 0 else 0


def main():
    parser = argparse.ArgumentParser(
        description='Visual regression testing for Boccherini Quartets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # baseline command
    baseline_parser = subparsers.add_parser('baseline', help='Generate baseline images')
    baseline_parser.add_argument('file', nargs='?', default='index.html',
                                  help='HTML file to use (default: index.html)')
    baseline_parser.add_argument('--format', choices=list(FORMATS.keys()),
                                  help='Only generate specific format')
    baseline_parser.add_argument('--dark', action='store_true',
                                  help='Enable dark mode (adds .dark-mode CSS class)')

    # test command
    test_parser = subparsers.add_parser('test', help='Test file against baselines')
    test_parser.add_argument('file', help='HTML file to test')
    test_parser.add_argument('--format', choices=list(FORMATS.keys()),
                              help='Only test specific format')
    test_parser.add_argument('--threshold', type=float, default=DEFAULT_THRESHOLD,
                              help=f'Diff threshold (default: {DEFAULT_THRESHOLD})')
    test_parser.add_argument('--open', action='store_true',
                              help='Open report in browser')
    test_parser.add_argument('--dark', action='store_true',
                              help='Enable dark mode (adds .dark-mode CSS class)')

    # compare command
    compare_parser = subparsers.add_parser('compare', help='Compare two HTML files')
    compare_parser.add_argument('file_a', help='First HTML file')
    compare_parser.add_argument('file_b', help='Second HTML file')
    compare_parser.add_argument('--format', choices=list(FORMATS.keys()),
                                 help='Only compare specific format')
    compare_parser.add_argument('--threshold', type=float, default=DEFAULT_THRESHOLD,
                                 help=f'Diff threshold (default: {DEFAULT_THRESHOLD})')
    compare_parser.add_argument('--open', action='store_true',
                                 help='Open report in browser')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == 'baseline':
        return cmd_baseline(args)
    elif args.command == 'test':
        return cmd_test(args)
    elif args.command == 'compare':
        return cmd_compare(args)

    return 0


if __name__ == '__main__':
    sys.exit(main())
