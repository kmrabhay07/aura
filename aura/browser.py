"""Browser operations. Playwright uses a dedicated automation profile."""
from pathlib import Path
from urllib.parse import quote_plus, urlparse
import os

def browse(action, value=None):
    from playwright.sync_api import sync_playwright
    profile = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "AURA" / "browser-profile"
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(str(profile), headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            if action == "search":
                page.goto("https://www.google.com/search?q=" + quote_plus(value), wait_until="domcontentloaded", timeout=30000)
                return "Opened Google results for: " + value
            if action == "navigate":
                parsed = urlparse(value)
                if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
                    return "Blocked: invalid web address"
                page.goto(value, wait_until="domcontentloaded", timeout=30000)
                return "Opened " + page.title()
            if action == "music":
                page.goto("https://music.apple.com/", wait_until="domcontentloaded", timeout=30000)
                return "Opened Apple Music. Playback requires login and further site automation."
            return "Unsupported browser action"
        finally:
            # The starter uses one browser session per tool invocation.
            context.close()
