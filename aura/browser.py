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
    """Open a validated target in the user's default browser.

    This intentionally does not claim to automate playback or page clicks.
    """
    import webbrowser
    url = target_url(action, value)
    if not url:
        return "Blocked: invalid or missing browser target"
    return "Opened " + url if webbrowser.open(url) else "Browser could not be opened"
