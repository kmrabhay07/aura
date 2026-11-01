"""Regression tests use fake devices/providers: no microphone, keys or network."""
import threading
from types import SimpleNamespace as NS

import numpy as np
import pytest

from aura.conversation import Cancelled, Conversation, Sentences, Turn, normalize_request
from aura.hotkey import HoldDetector, WindowsHotkey, parse_hotkey
from aura.voice import Recorder, Speaker, Transcriber
from aura.actions import Approval, approved_execute


def test_hotkey_startup_repeat_modifier_release_and_rearm():
    detector = HoldDetector()
    assert detector.update([True, True, True]) is None
    assert detector.update([False, False, False]) is None
    assert detector.update([True, True, True]) == "press"
    assert detector.update([True, True, True]) is None
    assert detector.update([False, True, True]) == "release"
    assert detector.update([True, True, True]) is None
    detector.update([False, False, False])
    assert detector.update([True, True, True]) == "press"
    assert detector.update([False, False, False]) == "release"


def test_hotkey_checks_down_bit_not_press_history_and_validates_shortcut():
    state = {}
    key = WindowsHotkey("Ctrl+Alt+F8", reader=lambda vk: state.get(vk, 0))
    assert key.poll() is None
    state.update({vk: 1 for vk in key.keys})
    assert key.poll() is None
    state.update({vk: 0x8000 for vk in key.keys})
    assert key.poll() == "press"
    state[key.keys[-1]] = 0
    assert key.poll() == "release"
    for invalid in ("Space", "Ctrl+Ctrl+Space", "Ctrl+A", "Ctrl+", "Delete+F1"):
        with pytest.raises(ValueError):
            parse_hotkey(invalid)


def test_jarvis_optional_address_only_at_start():
    assert normalize_request("Jarvis, can you do this?") == "can you do this?"
    assert normalize_request("jarvis can you do that?") == "can you do that?"
    assert normalize_request("Can you help Jarvis?") == "Can you help Jarvis?"
    assert normalize_request("Jarvis!") == ""
    assert normalize_request("Jarvis's voice settings") == "Jarvis's voice settings"


def test_history_is_bounded_by_complete_pairs_and_cancellation_discards_stale_turns():
    session = Conversation(max_turns=2, max_chars=40)
    old = session.begin()
    new = session.begin()
    assert old.cancel.is_set() and old.released.is_set()
    assert not session.commit(old, "stale", "stale")
    assert session.commit(new, "hello", "hi")
    session.commit(session.begin(), "next", "yes")
    session.commit(session.begin(), "third", "fine")
    assert [m["content"] for m in session.history()] == ["next", "yes", "third", "fine"]
    snapshot = session.history()
    snapshot[0]["content"] = "changed"
    assert session.history()[0]["content"] == "next"
    session.clear()
    assert session.history() == []


def test_release_before_device_start_never_opens_microphone():
    turn = Turn(1)
    turn.released.set()
    def forbidden(**kwargs):
        pytest.fail("Microphone must not be opened after release")
    audio, capped = Recorder(forbidden).capture(turn)
    assert len(audio) == 0 and not capped


def test_recording_is_not_fixed_to_six_seconds_and_closes_on_release():
    turn = Turn(1)
    closed = []
    class Stream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]
        def __enter__(self):
            self.callback(np.ones((16000 * 8, 1), dtype=np.float32), 16000 * 8, None, None)
            turn.released.set()
        def __exit__(self, *args):
            closed.append(True)
    audio, capped = Recorder(Stream).capture(turn)
    assert len(audio) == 16000 * 8 and closed and not capped


def test_recorder_safety_limit_and_cancelled_device_start():
    turn = Turn(1)
    class Stream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]
        def __enter__(self):
            self.callback(np.ones((32000, 1), dtype=np.float32), 32000, None, None)
        def __exit__(self, *args):
            pass
    audio, capped = Recorder(Stream, max_seconds=1).capture(turn)
    assert len(audio) == 16000 and capped
    turn.cancel.set()
    with pytest.raises(Cancelled):
        Recorder(Stream).capture(turn)


def test_transcriber_reuses_model_and_discards_cancelled_native_result():
    creations = []
    active = [None]
    class Model:
        def __init__(self, *args, **kwargs):
            creations.append(True)
        def transcribe(self, audio, **kwargs):
            def segments():
                yield NS(text=" Jarvis, hello ")
                if active[0]:
                    active[0].cancel.set()
                yield NS(text=" world ")
            return segments(), None
    transcriber = Transcriber(Model)
    audio = np.ones(16000, dtype=np.float32)
    assert transcriber.transcribe(audio, Turn(1)) == "Jarvis, hello world"
    assert transcriber.transcribe(audio, Turn(2)) == "Jarvis, hello world"
    assert len(creations) == 1
    active[0] = Turn(3)
    with pytest.raises(Cancelled):
        transcriber.transcribe(audio, active[0])


def test_sentence_buffer_speaks_before_full_answer_and_flushes_tail():
    buffer = Sentences()
    assert buffer.feed("Hello") == []
    assert buffer.feed(" there. Next") == ["Hello there."]
    assert buffer.feed(" sentence!") == ["Next sentence!"]
    assert buffer.feed(" Remaining") == []
    assert buffer.feed("", final=True) == ["Remaining"]


def test_actions_fail_closed_denial_cancellation_and_bad_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr("aura.agent.execute", lambda *args: calls.append(args) or "done")
    turn = Turn(1)
    assert "denied" in approved_execute("open_app", {"app": "notepad"}, turn, None)
    assert "denied" in approved_execute("open_app", {"app": "notepad"}, turn, lambda *a: False)
    with pytest.raises(ValueError):
        approved_execute("open_app", {"app": "powershell"}, turn, lambda *a: True)
    assert not calls
    assert approved_execute("open_app", {"app": "notepad"}, turn, lambda *a: True) == "done"
    def cancel_before_execution(*args):
        turn.cancel.set()
        return True
    with pytest.raises(Cancelled):
        approved_execute("open_app", {"app": "notepad"}, turn, cancel_before_execution)
    assert len(calls) == 1


def test_approval_expiry_and_late_answer_cannot_override_first_answer():
    request = Approval(Turn(1), "open_app", {"app": "notepad"})
    request.answer(False)
    request.answer(True)
    assert not request.wait()
    assert not Approval(Turn(2), "open_app", {}).wait(timeout=0)
    cancelled = Turn(3)
    cancelled.cancel.set()
    with pytest.raises(Cancelled):
        Approval(cancelled, "open_app", {}).wait(timeout=0)


def test_speaker_serial_engine_reuse_and_interruption():
    finished = threading.Event()
    speaking = threading.Event()
    created = []
    said = []
    stopped = []
    class Engine:
        busy = False
        def startLoop(self, external):
            pass
        def iterate(self):
            if self.busy and self.current != "interrupt":
                self.busy = False
        def say(self, text):
            self.current = text
            self.busy = True
            said.append(text)
        def isBusy(self):
            return self.busy
        def stop(self):
            stopped.append(True)
            self.busy = False
        def endLoop(self):
            pass
    def factory():
        created.append(True)
        return Engine()
    def notify(turn, state, detail):
        if state == "speaking":
            speaking.set()
        if state == "speech_done":
            finished.set()
    speaker = Speaker(notify, factory)
    try:
        first = Turn(1)
        speaker.say(first, "one")
        speaker.say(first, "two")
        speaker.finish(first)
        assert finished.wait(2)
        assert said == ["one", "two"] and len(created) == 1
        speaking.clear()
        second = Turn(2)
        speaker.say(second, "interrupt")
        assert speaking.wait(2)
        second.cancel.set()
        assert speaker.wait_quiet(2)
        assert stopped
    finally:
        speaker.close()
        speaker._thread.join(2)


def test_speech_errors_are_visible_and_do_not_reinitialize_per_sentence():
    done = threading.Event()
    errors = []
    created = []
    def fail():
        created.append(True)
        raise RuntimeError("driver failed")
    def notify(turn, state, detail):
        if state == "speech_error":
            errors.append(detail)
        if state == "speech_done":
            done.set()
    speaker = Speaker(notify, fail)
    try:
        turn = Turn(1)
        speaker.say(turn, "one")
        speaker.say(turn, "two")
        speaker.finish(turn)
        assert done.wait(2)
        assert len(errors) == 1 and len(created) == 1
    finally:
        speaker.close()
        speaker._thread.join(2)


def test_expired_approval_cannot_be_revived():
    request = Approval(Turn(1), "open_app", {"app": "notepad"})
    assert not request.wait(timeout=0)
    request.answer(True)
    assert not request.wait()


def test_either_windows_key_can_activate_configured_shortcut():
    state = {}
    hotkey = WindowsHotkey("Win+F8", reader=lambda vk: state.get(vk, 0))
    hotkey.poll()
    state.update({0x5C: 0x8000, hotkey.keys[-1]: 0x8000})
    assert hotkey.poll() == "press"
    state[0x5C] = 0
    assert hotkey.poll() == "release"


def test_selected_voice_and_speed_are_applied_on_speech_thread():
    done=threading.Event()
    properties=[]
    class Engine:
        def startLoop(self,*a): pass
        def iterate(self): pass
        def setProperty(self,name,value): properties.append((name,value))
        def say(self,text): pass
        def isBusy(self): return False
        def stop(self): pass
        def endLoop(self): pass
    speaker=Speaker(lambda t,s,d:done.set() if s=='speech_done' else None,Engine)
    try:
        speaker.configure('test-voice',250)
        turn=Turn(1)
        speaker.say(turn,'one')
        speaker.say(turn,'two')
        speaker.finish(turn)
        assert done.wait(2)
        assert properties==[('voice','test-voice'),('rate',250)]
    finally:
        speaker.close()
        speaker._thread.join(2)
