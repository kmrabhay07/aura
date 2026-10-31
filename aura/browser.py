"""Browser navigation in an isolated Chromium profile.

Each action opens an interactive browser window. The session profile preserves
cookies across invocations; no page DOM interaction is attempted.
"""
from pathlib import Path
from urllib.parse import quote_plus, urlparse
import os

def target_url(action, value=None):
    if action == "search":
        if not value:
            return None
        return "https://www.google.com/search?q=" + quote_plus(value)
    if action == "music":
        return "https://music.apple.com/"
    if action == "music_search":
        if not value:
            return None
        return "https://music.apple.com/search?term=" + quote_plus(value)
    if action == "chatgpt":
        return "https://chatgpt.com/"
    if action == "navigate":
        parsed = urlparse(value or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
            return None
        return value
    return None

def browse(action, value=None):
    url = target_url(action, value)
    if not url:
        return "Blocked: invalid or missing browser target"
    # Browser process is independent from the UI; cookies are kept in a dedicated profile.
    import subprocess
    import sys
    if getattr(sys, "frozen", False):
        # Frozen applications cannot assume a Python interpreter is installed.
        from playwright.sync_api import sync_playwright
        profile = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "AURA" / "browser-profile"
        profile.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(str(profile), headless=False)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                return "Opened " + url + " (automation window closes after navigation)"
            finally:
                context.close()
    # For source development, open the requested site in the default browser,
    # which persists beyond the command and supports normal sign-in.
    import webbrowser
    return "Opened " + url if webbrowser.open(url) else "Browser could not be opened"
