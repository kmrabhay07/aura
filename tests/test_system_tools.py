from aura.system_tools import system_action

def test_unknown_action():
    assert system_action("delete_all_files") in ("Unsupported system action", "Windows-only action")

def test_lock_requires_confirmation():
    assert "confirmation" in system_action("lock_screen").lower() or system_action("lock_screen") == "Windows-only action"
