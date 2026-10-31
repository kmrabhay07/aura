from aura.agent import execute

def test_invalid_url_blocked():
    assert execute("open_url", {"url": "file:///etc/passwd"}).startswith("Blocked")

def test_unknown_tool():
    assert execute("not_a_tool", {}) == "Unsupported action"
