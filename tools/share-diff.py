#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Share Visual Diff Report via GitHub Gist

Creates a self-contained HTML report with embedded images and uploads it
to a GitHub Gist, then provides a GitHack URL for viewing.

Usage:
    uv run tools/share-diff.py --token TOKEN    Upload with explicit token
    uv run tools/share-diff.py                  Upload (prompts for token if needed)

Authentication (in order of preference):
    1. --token argument
    2. GH_TOKEN or GITHUB_TOKEN environment variable
    3. gh CLI (if authenticated)
    4. Interactive prompt (will ask for token)

The script auto-detects light/dark mode from the report filename and
updates the appropriate hard-coded gist.

To create a token: https://github.com/settings/tokens
Required scope: gist

Requirements:
    - diffs/ directory with report.html and images from visual-diff.py
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Directories
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DIFFS_DIR = PROJECT_ROOT / 'diffs'
BASELINES_DIR = PROJECT_ROOT / 'baselines'

# Hard-coded gist IDs (light and dark mode)
GIST_ID_LIGHT = '9fc50df2a1437d2d1582abcfb70dfa7b'
GIST_ID_DARK = 'cae03a252a66aa123ebfb4914e367801'

GIST_FILENAME = 'visual-diff-report.html'
GIST_FILENAME_DARK = 'visual-diff-report-dark.html'
GITHUB_API = 'https://api.github.com'


class GitHubAuth:
    """Handle GitHub authentication via token, GH_TOKEN, gh CLI, or interactive prompt."""

    def __init__(self, token=None):
        self.token = token or os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        self.username = None
        self._check_auth()

    def _check_auth(self):
        """Verify authentication and get username."""
        if self.token:
            # Use token directly
            if self._try_token(self.token):
                return

        # Try gh CLI
        result = subprocess.run(['gh', 'auth', 'status'], capture_output=True, text=True)
        if result.returncode == 0:
            # Get username from gh
            result = subprocess.run(
                ['gh', 'api', 'user', '--jq', '.login'],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self.username = result.stdout.strip()
                print(f"Authenticated via gh CLI as: {self.username}")
                return

        # Prompt for token interactively
        self._prompt_for_token()

    def _try_token(self, token):
        """Try to authenticate with a token. Returns True on success."""
        self.token = token
        try:
            data = self._api_request('GET', '/user')
            self.username = data['login']
            print(f"Authenticated as: {self.username}")
            return True
        except Exception as e:
            print(f"Token authentication failed: {e}")
            self.token = None
            return False

    def _prompt_for_token(self):
        """Prompt user to enter a GitHub token interactively."""
        print("=" * 70)
        print("GitHub authentication required")
        print("=" * 70)
        print("\nTo create a personal access token:")
        print("  1. Go to: https://github.com/settings/tokens")
        print("  2. Click 'Generate new token (classic)'")
        print("  3. Select scope: 'gist'")
        print("  4. Copy the token and paste below")
        print("=" * 70)

        while True:
            try:
                token = input("\nEnter GitHub token (or 'q' to quit): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                sys.exit(1)

            if token.lower() == 'q':
                sys.exit(0)

            if not token:
                print("Token cannot be empty.")
                continue

            if self._try_token(token):
                return

            print("Invalid token. Please try again.")

    def _api_request(self, method, endpoint, data=None):
        """Make a GitHub API request."""
        url = f"{GITHUB_API}{endpoint}"
        headers = {
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'share-diff-script',
        }

        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        body = None
        if data:
            body = json.dumps(data).encode('utf-8')
            headers['Content-Type'] = 'application/json'

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise Exception(f"GitHub API error {e.code}: {error_body}")

    def create_gist(self, filename, content, description, public=True):
        """Create a new gist."""
        if self.token:
            data = {
                'description': description,
                'public': public,
                'files': {
                    filename: {'content': content}
                }
            }
            result = self._api_request('POST', '/gists', data)
            return result['id'], result['html_url']
        else:
            # Use gh CLI
            temp_file = DIFFS_DIR / filename
            temp_file.write_text(content)

            cmd = ['gh', 'gist', 'create', str(temp_file), '--desc', description]
            if public:
                cmd.append('--public')

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"gh gist create failed: {result.stderr}")

            gist_url = result.stdout.strip()
            gist_id = gist_url.split('/')[-1]
            return gist_id, gist_url

    def update_gist(self, gist_id, filename, content):
        """Update an existing gist."""
        if self.token:
            data = {
                'files': {
                    filename: {'content': content}
                }
            }
            result = self._api_request('PATCH', f'/gists/{gist_id}', data)
            return result['id'], result['html_url']
        else:
            # Use gh CLI
            temp_file = DIFFS_DIR / filename
            temp_file.write_text(content)

            result = subprocess.run(
                ['gh', 'gist', 'edit', gist_id, '--add', str(temp_file)],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                raise Exception(f"gh gist edit failed: {result.stderr}")

            return gist_id, f"https://gist.github.com/{gist_id}"


def image_to_data_url(image_path):
    """Convert an image file to a base64 data URL."""
    path = Path(image_path)
    if not path.exists():
        print(f"  Warning: Image not found: {path}")
        return None

    suffix = path.suffix.lower()
    mime_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
    }
    mime_type = mime_types.get(suffix, 'image/png')

    with open(path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('ascii')

    return f'data:{mime_type};base64,{data}'


def detect_dark_mode():
    """Detect if we're working with a dark mode report."""
    dark_report = DIFFS_DIR / 'report-dark.html'
    light_report = DIFFS_DIR / 'report.html'

    if dark_report.exists():
        return True
    elif light_report.exists():
        return False
    else:
        # Neither exists, will error in create_self_contained_report
        return False


def create_self_contained_report(dark_mode=False):
    """Read the report HTML and embed all images as base64 data URLs."""
    report_filename = 'report-dark.html' if dark_mode else 'report.html'
    report_path = DIFFS_DIR / report_filename

    if not report_path.exists():
        print(f"ERROR: Report not found at {report_path}")
        dark_flag = ' --dark' if dark_mode else ''
        print(f"Run: uv run tools/visual-diff.py test index.html{dark_flag}")
        sys.exit(1)

    html = report_path.read_text()

    # Find all image src attributes
    img_pattern = r'<img\s+[^>]*src="([^"]+)"'

    def replace_image(match):
        full_match = match.group(0)
        src = match.group(1)

        # Skip if already a data URL
        if src.startswith('data:'):
            return full_match

        # Resolve relative path
        if src.startswith('../baselines/'):
            image_path = BASELINES_DIR / src.replace('../baselines/', '')
        else:
            image_path = DIFFS_DIR / src

        data_url = image_to_data_url(image_path)
        if data_url:
            return full_match.replace(f'src="{src}"', f'src="{data_url}"')
        return full_match

    # Replace all image sources with data URLs
    print("Embedding images...")
    embedded_html = re.sub(img_pattern, replace_image, html)

    # Add a note about the source
    note = '''
    <div style="background: #fff3cd; border: 1px solid #ffc107; padding: 10px; margin-bottom: 20px; border-radius: 4px;">
        <strong>Shared Report</strong> - This is a self-contained visual diff report.
        Images are embedded as base64.
    </div>
'''
    embedded_html = embedded_html.replace('<h1>', note + '<h1>', 1)

    return embedded_html


def get_githack_url(username, gist_id, dark_mode=False):
    """Generate the GitHack URL for viewing the HTML."""
    # GitHack CDN URL format for gists
    filename = GIST_FILENAME_DARK if dark_mode else GIST_FILENAME
    return f"https://gistcdn.githack.com/{username}/{gist_id}/raw/{filename}"


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Share visual diff report via GitHub Gist',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--token', '-t',
                        help='GitHub personal access token (alternative to GH_TOKEN env var)')
    args = parser.parse_args()

    # Check prerequisites and get auth
    auth = GitHubAuth(token=args.token)

    # Detect dark mode from report filename
    dark_mode = detect_dark_mode()
    mode_label = ' (dark mode)' if dark_mode else ''
    gist_id = GIST_ID_DARK if dark_mode else GIST_ID_LIGHT
    gist_filename = GIST_FILENAME_DARK if dark_mode else GIST_FILENAME

    # Create self-contained HTML
    html_content = create_self_contained_report(dark_mode)
    print(f"Report size: {len(html_content) / 1024:.1f} KB")

    # Update the hard-coded gist
    print(f"Updating gist {gist_id}{mode_label}...")
    try:
        gist_id, gist_url = auth.update_gist(gist_id, gist_filename, html_content)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Generate URLs
    githack_url = get_githack_url(auth.username, gist_id, dark_mode)

    print("\n" + "=" * 70)
    print(f"Visual Diff Report Shared{mode_label}!")
    print("=" * 70)
    print(f"\nGist URL:    {gist_url}")
    print(f"\nView Report: {githack_url}")
    print("\n" + "=" * 70)

    return 0


if __name__ == '__main__':
    sys.exit(main())
