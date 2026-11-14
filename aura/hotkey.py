"""Windows global hold detection. No microphone or keyboard text capture here."""
import sys

MODIFIERS = {"CTRL": 0x11, "ALT": 0x12, "SHIFT": 0x10, "WIN": 0x5B}
KEYS = {"SPACE": 0x20, **{f"F{i}": 0x6F + i for i in range(1, 13)}}
DEFAULT_HOTKEY = "Ctrl+Alt+Space"


def parse_hotkey(value):
    parts = [part.strip().upper() for part in value.split("+")]
    if len(parts) < 2 or len(set(parts)) != len(parts):
        raise ValueError("Use a modifier plus Space or F1–F12, e.g. Ctrl+Alt+Space")
    if any(p not in MODIFIERS for p in parts[:-1]) or parts[-1] not in KEYS:
        raise ValueError("Use Ctrl/Alt/Shift/Win plus Space or F1–F12")
    return tuple(MODIFIERS[p] for p in parts[:-1]) + (KEYS[parts[-1]],)


class HoldDetector:
    def __init__(self):
        self.held = False
        self.armed = False

    def update(self, states):
        down = all(states)
        if not any(states):
            self.armed = True
        if self.held and not down:
            self.held = False
            return "release"
        if down and self.armed and not self.held:
            self.held = True
            self.armed = False
            return "press"
        return None


class WindowsHotkey:
    def __init__(self, value=DEFAULT_HOTKEY, reader=None):
        self.keys = parse_hotkey(value)
        self.detector = HoldDetector()
        if reader is None:
            if sys.platform != "win32":
                raise RuntimeError("Global push-to-talk requires Windows")
            import ctypes
            reader = ctypes.windll.user32.GetAsyncKeyState
        self.reader = reader

    def poll(self):
        # High bit = physical down. Releasing ANY member ends the hold;
        # auto-repeat and the unreliable 'since last call' bit are ignored.
        states = []
        for key in self.keys:
            value = self.reader(key)
            if key == MODIFIERS["WIN"]:
                value |= self.reader(0x5C)  # Either Windows key.
            states.append(bool(value & 0x8000))
        return self.detector.update(states)

    def escape_down(self):
        return bool(self.reader(0x1B) & 0x8000)
