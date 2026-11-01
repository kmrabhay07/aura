"""Offscreen Qt tests. No real keyboard, microphone, speech or credentials."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDialog

from aura import main
from aura.actions import Approval
from aura.pipeline import Pipeline
from tests_support import FakeSettings, SilentSpeaker


@pytest.fixture(autouse=True)
def no_device_enumeration(monkeypatch):
    monkeypatch.setattr(main,'installed_voices',lambda:[])
    monkeypatch.setattr(main,'input_devices',lambda:[])


@pytest.fixture
def window(app, monkeypatch):
    monkeypatch.setattr(main, "Settings", FakeSettings)
    class Keys:
        def __init__(self, value):
            pass
        def poll(self):
            return None
        def escape_down(self):
            return False
    monkeypatch.setattr(main, "WindowsHotkey", Keys)
    monkeypatch.setattr(main, "Pipeline", lambda notify: Pipeline(notify, speaker=SilentSpeaker()))
    window = main.Window()
    window.timer.stop()
    yield window
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def test_window_is_jarvis_and_rejects_queued_stale_and_cancelled_text(window):
    assert "Jarvis" in window.windowTitle()
    assert "I’m Jarvis" in window.log.toPlainText()
    old = window.pipeline.conversation.begin()
    current = window.pipeline.conversation.begin()
    window.on_update(old, "text", "STALE")
    window.cancel()
    window.on_update(current, "text", "CANCELLED TEXT")
    assert "STALE" not in window.log.toPlainText()
    assert "CANCELLED TEXT" not in window.log.toPlainText()
    window.on_update(current, "error", "STALE ERROR")
    assert "STALE ERROR" not in window.state_label.text()
    current = window.pipeline.conversation.begin()
    current.cancel.set()  # Worker errors invalidate work before queuing the signal.
    window.on_update(current, "error", "Device unavailable")
    assert "Device unavailable" in window.state_label.text()


def test_streamed_text_is_plain_and_clear_conversation_removes_memory(window):
    turn = window.pipeline.conversation.begin()
    window.on_update(turn, "text", "<b>literal text</b>")
    assert "<b>literal text</b>" in window.log.toPlainText()
    window.pipeline.conversation.commit(turn, "hello", "hi")
    window.new_conversation()
    assert window.pipeline.conversation.history() == []
    assert "literal text" not in window.log.toPlainText()


def test_cancel_dismisses_approval_without_execution(window):
    turn = window.pipeline.conversation.begin()
    request = Approval(turn, "open_app", {"app": "notepad"})
    window.on_update(turn, "approval", request)
    assert window.approval_dialog is not None
    window.cancel()
    assert window.approval_dialog is None
    assert request.resolved.is_set() and not request.allowed


def test_window_deactivation_releases_only_button_capture(window):
    turn = window.pipeline.conversation.begin()
    window.voice_source = "button"
    window.eventFilter(window, QEvent(QEvent.WindowDeactivate))
    assert turn.released.is_set()
    turn = window.pipeline.conversation.begin()
    window.voice_source = "hotkey"
    window.eventFilter(window, QEvent(QEvent.WindowDeactivate))
    assert not turn.released.is_set()
    window.on_update(turn, "transcribing", "")
    assert window.voice_source is None


def test_settings_shortcut_and_reply_preferences_save_without_changing_vault_identity(app, monkeypatch):
    monkeypatch.setattr(main, "Settings", FakeSettings)
    dialog = main.SettingsDialog()
    try:
        dialog.hotkey.setText("Ctrl+Shift+F9")
        dialog.replies.setChecked(True)
        dialog.save()
        assert dialog.result() == QDialog.Accepted
        assert FakeSettings.saved_voice == ("Ctrl+Shift+F9", True)
        from aura.settings import SERVICE
        assert SERVICE == "AURA-Desktop-Agent"
    finally:
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()


def test_background_pipeline_updates_are_delivered_by_gui_loop(window, app):
    import time
    class Agent:
        def run(self, prompt, progress, **kwargs):
            kwargs["on_text"]("A streamed answer.")
            return "A streamed answer."
    window.pipeline.agent_factory = Agent
    window.prompt.setText("Jarvis, hello")
    window.submit()
    deadline = time.monotonic() + 3
    while "A streamed answer." not in window.log.toPlainText() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert "A streamed answer." in window.log.toPlainText()
    for worker in list(window.pipeline._threads):
        worker.join(2)
        assert not worker.is_alive()
    app.processEvents()


def test_screen_sharing_cannot_capture_without_model_opt_in(window,monkeypatch):
    monkeypatch.setattr(main,'capture_monitor',lambda *a:pytest.fail('Captured without model opt-in'))
    window.screen_once.setChecked(True)
    window.prompt.setText('what is this?')
    window.submit()
    assert 'image-capable' in window.state_label.text()
    assert window.prompt.text()=='what is this?'


def test_one_shot_screen_is_passed_and_checkbox_resets(window,monkeypatch,app):
    import time
    from aura.screen import ScreenFrame
    monkeypatch.setattr(FakeSettings,'image_inputs',lambda self:True)
    capture=ScreenFrame(b'synthetic','display',(0,0,800,600),(800,600))
    monkeypatch.setattr(main,'capture_monitor',lambda *args:capture)
    observed=[]
    class Agent:
        def run(self,prompt,progress,**kwargs):
            observed.append(kwargs['screen'])
            kwargs['on_text']('Screen answer')
            return 'Screen answer'
    window.pipeline.agent_factory=Agent
    window.screen_once.setChecked(True)
    window.prompt.setText('Explain this')
    window.submit()
    for worker in list(window.pipeline._threads):
        worker.join(2)
        assert not worker.is_alive()
    app.processEvents()
    assert observed==[capture]
    assert not window.screen_once.isChecked()
    assert 'Screen answer' in window.log.toPlainText()
    window.cancel()
    assert window.active_frame is None and window.guidance.overlay is None


def test_companion_uses_same_controller_and_mirrors_screen_consent(window):
    assert window.companion.owner is window
    window.screen_once.setChecked(True)
    assert window.companion.screen.isChecked()
    window.companion.screen.setChecked(False)
    assert not window.screen_once.isChecked()
    turn=window.pipeline.conversation.begin()
    window.on_update(turn,'text','A companion answer')
    assert window.companion.answer.text()=='A companion answer'


def test_activity_records_completion_and_does_not_relabel_it_cancelled(window,app):
    class Agent:
        def run(self,prompt,progress,**kwargs):
            kwargs['on_text']('Done')
            return 'Done'
    window.pipeline.agent_factory=Agent
    window.prompt.setText('A task')
    window.submit()
    for worker in list(window.pipeline._threads):
        worker.join(2)
    app.processEvents()
    assert window.activity[-1]['state']=='Completed'
    window.cancel()
    assert window.activity[-1]['state']=='Completed'
    window.new_conversation()
    assert window.activity==[]
