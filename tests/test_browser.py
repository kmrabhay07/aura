from aura.agent import execute

def test_block_local_file():
    assert execute("open_url", {"url": "file:///C:/secret.txt"}).startswith("Blocked")

def test_reject_unknown_app():
    assert "failed" in execute("open_app", {"app": "something_else"}).lower() or "Unsupported" in execute("open_app", {"app": "something_else"})
