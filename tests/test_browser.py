from aura.agent import execute

def test_block_local_file():
    assert execute("open_url", {"url": "file:///C:/secret.txt"}).startswith("Blocked")

def test_reject_unknown_app():
    assert execute("open_app", {"app": "something_else"}) in ("Unsupported application", "Windows applications require Windows")
