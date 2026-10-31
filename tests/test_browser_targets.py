from aura.browser import target_url

def test_music_search_encoding():
    assert target_url("music_search", "slow songs") == "https://music.apple.com/search?term=slow+songs"

def test_blocks_non_web_schemes():
    assert target_url("navigate", "file:///C:/private") is None

def test_blocks_url_credentials():
    assert target_url("navigate", "https://user:pass@example.com") is None

def test_unknown_action():
    assert target_url("run_shell", "calc.exe") is None
