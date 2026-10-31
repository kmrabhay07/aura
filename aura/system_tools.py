"""Allowlisted Windows media-key controls, no arbitrary shell commands."""
import sys

KEYS = {
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "volume_mute": 0xAD,
    "play_pause": 0xB3,
    "next_track": 0xB0,
    "previous_track": 0xB1,
}

def system_action(action):
    if sys.platform != "win32":
        return "Windows-only action"
    if action == "lock_screen":
        return "Lock screen requires explicit user confirmation; not yet enabled"
    if action not in KEYS:
        return "Unsupported system action"
    import ctypes
    key = KEYS[action]
    user32 = ctypes.windll.user32
    user32.keybd_event(key, 0, 0, 0)
    user32.keybd_event(key, 0, 2, 0)
    return f"Sent Windows media key: {action}"
