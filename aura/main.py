import json
import os
import time
import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtCore import QObject, QTimer, Signal, Slot, Qt, QEvent, QLockFile
from PySide6.QtGui import QTextCursor, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QTextEdit, QLineEdit, QPushButton, QFrame, QDialog,
    QComboBox, QDialogButtonBox, QFormLayout, QCheckBox, QMessageBox, QListWidget, QListWidgetItem, QSpinBox, QScrollArea)

from .pipeline import Pipeline
from .hotkey import WindowsHotkey, parse_hotkey
from .providers import PROVIDERS
from .settings import Settings
from .desktop import capture_monitor, external_foreground, exclude_from_capture, Guidance
from .companion import Companion
from .history import HistoryStore
from .voice import installed_voices, input_devices

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Events(QObject):
    update = Signal(object, str, object)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Jarvis · Settings")
        self.setMinimumWidth(470)
        settings = Settings()
        self.resize(600,680)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.provider = QComboBox()
        self.provider.addItems(PROVIDERS.keys())
        self.provider.setCurrentText(settings.provider())
        self.model = QLineEdit(settings.model())
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("Paste API key (leave blank to keep saved key)")
        self.provider.currentTextChanged.connect(lambda name: self.model.setText(PROVIDERS[name].default_model))
        form.addRow("Provider", self.provider)
        form.addRow("Model ID", self.model)
        form.addRow("API key", self.key)
        self.hotkey = QLineEdit(settings.hotkey())
        form.addRow("Hold-to-talk shortcut", self.hotkey)
        self.replies = QCheckBox("Speak Jarvis replies")
        self.replies.setChecked(settings.voice_replies())
        form.addRow(self.replies)
        voice,rate,device = getattr(settings,'speech_options',lambda:('',200,-1))()
        self.voice_choice = QComboBox()
        self.voice_choice.addItem('Default Windows voice','')
        for label,value in installed_voices():
            self.voice_choice.addItem(label,value)
        self.voice_choice.setCurrentIndex(max(0,self.voice_choice.findData(voice)))
        form.addRow('Voice',self.voice_choice)
        self.rate = QSpinBox()
        self.rate.setRange(100,300)
        self.rate.setValue(rate)
        self.rate.setSuffix(' words / minute')
        form.addRow('Speech speed',self.rate)
        self.input_choice = QComboBox()
        self.input_choice.addItem('Default microphone',-1)
        for label,value in input_devices():
            self.input_choice.addItem(label,value)
        self.input_choice.setCurrentIndex(max(0,self.input_choice.findData(device)))
        form.addRow('Microphone',self.input_choice)
        self.images = QCheckBox("My selected AI model accepts screen images")
        self.images.setChecked(getattr(settings,'image_inputs',lambda:False)())
        form.addRow(self.images)
        self.remember = QCheckBox("Remember completed chats on this PC")
        self.remember.setChecked(getattr(settings,'remember_chats',lambda:False)())
        form.addRow(self.remember)
        privacy = QLabel("Screens are sent only when Include screen once is selected. Verify your model supports images. Saved chats are local, unencrypted text (up to 30 conversations); no images or audio are saved. You can delete saved chats in Conversations.")
        privacy.setWordWrap(True)
        form.addRow(privacy)
        hint = QLabel("Ctrl/Alt/Shift/Win + Space or F1–F12. Release all keys between turns.\nGlobal shortcuts are observed, not swallowed; avoid shortcuts used by other apps.")
        hint.setWordWrap(True)
        form.addRow(hint)
        info = QLabel("Keys are stored in the OS credential vault, not in the repository.")
        info.setWordWrap(True)
        form.addRow(info)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        exclude_from_capture(self)

    def save(self):
        try:
            parse_hotkey(self.hotkey.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Jarvis shortcut", str(exc))
            return
        settings = Settings()
        try:
            settings.save_key(self.provider.currentText(), self.key.text())
        except Exception:
            QMessageBox.warning(self, "Jarvis credentials", "Could not save to the credential vault. Please try again.")
            return
        settings.set_voice_preferences(self.hotkey.text(), self.replies.isChecked())
        settings.set_provider(self.provider.currentText(), self.model.text())
        settings.set_experience_preferences(self.images.isChecked(),self.remember.isChecked())
        settings.set_speech_options(self.voice_choice.currentData(),self.rate.value(),self.input_choice.currentData())
        self.accept()

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis — Desktop Assistant")
        self.resize(1120, 760)
        self.setStyleSheet("""
          QWidget { background:#0b0d13; color:#e9eaf2; font-family:Segoe UI; font-size:14px; }
          QFrame#sidebar {background:#11141d; border-right:1px solid #262a39;}
          QLabel#brand {font-size:27px; font-weight:800; color:#d2b8ff;}
          QLabel#heading {font-size:31px; font-weight:700;}
          QLabel#muted {color:#9297ad;}
          QTextEdit {background:#111521; border:1px solid #292e40; border-radius:16px; padding:18px;}
          QLineEdit {background:#181c29; border:1px solid #35394d; border-radius:14px; padding:16px; font-size:15px;}
          QLineEdit:focus {border:1px solid #9d7cf8;}
          QCheckBox::indicator {width:16px;height:16px;border:1px solid #8c7caa;border-radius:4px;background:#181c29;}
          QCheckBox::indicator:checked {background:#b299f5;border:1px solid #e2d6ff;}
          QPushButton {background:#a98cff; color:#14101e; border:0; border-radius:13px; padding:15px 22px; font-weight:700;}
          QPushButton:hover {background:#c0a9ff;}
          QPushButton:disabled {background:#3b354c; color:#a4a0b0;}
        """)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(245)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(26, 32, 22, 25)
        side.setSpacing(16)
        brand = QLabel("Jarvis")
        brand.setObjectName("brand")
        side.addWidget(brand)
        side.addSpacing(35)
        for text,handler in [("Floating Jarvis",self.toggle_companion),
                             ("Conversations",self.open_history),
                             ("Activity / tasks",self.open_activity),
                             ("Run browser task",self.run_browser_task)]:
            button = QPushButton(text)
            button.clicked.connect(handler)
            side.addWidget(button)
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.configure)
        side.addWidget(self.settings_button)
        side.addStretch()
        status = QLabel("●  READY FOR COMMANDS")
        status.setStyleSheet("color:#a98cff; font-size:11px; font-weight:700;")
        side.addWidget(status)
        outer.addWidget(sidebar)

        main = QWidget()
        body = QVBoxLayout(main)
        body.setContentsMargins(46, 42, 46, 35)
        body.setSpacing(17)
        eyebrow = QLabel("YOUR INTELLIGENT WORKSPACE")
        eyebrow.setStyleSheet("color:#aa91ec; letter-spacing:2px; font-size:11px; font-weight:700;")
        body.addWidget(eyebrow)
        heading = QLabel("What can I do for you?")
        heading.setObjectName("heading")
        body.addWidget(heading)
        desc = QLabel("Hold to talk. Release to send. Continue the conversation.")
        desc.setObjectName("muted")
        body.addWidget(desc)
        body.addSpacing(12)
        sharing = QHBoxLayout()
        self.screen_once = QCheckBox("Include screen once")
        self.screen_once.setToolTip("Sends this selected monitor to your configured provider for the next request only.")
        sharing.addWidget(self.screen_once)
        self.screen_choice = QComboBox()
        self.screen_choice.addItem("Monitor under pointer",'')
        for screen in QApplication.screens():
            self.screen_choice.addItem(screen.name(),screen.name())
        sharing.addWidget(self.screen_choice)
        self.browser_once = QCheckBox("Browser tools once")
        self.browser_once.setToolTip("Uses a separate Jarvis Edge session. Every browser step still requires approval.")
        sharing.addWidget(self.browser_once)
        body.addLayout(sharing)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlainText("I’m Jarvis. Hold the talk button or your global shortcut, then release to send.\nYou can say ‘Jarvis, can you help?’ or just ask. Select Include screen once to share the selected monitor for your next request.\nConversation context stays in memory; local saved history is opt-in in Settings.")
        body.addWidget(self.log, 1)
        self.state_label = QLabel("Ready")
        self.state_label.setWordWrap(True)
        body.addWidget(self.state_label)
        controls = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel / stop · Esc")
        self.cancel_button.clicked.connect(self.cancel)
        self.new_button = QPushButton("New conversation")
        self.new_button.clicked.connect(self.new_conversation)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.new_button)
        body.addLayout(controls)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText("Ask Jarvis…")
        self.prompt.returnPressed.connect(self.submit)
        self.speech_toggle = QPushButton("Voice replies: OFF")
        self.speech_toggle.setCheckable(True)
        self.speech_toggle.toggled.connect(self.toggle_speech)
        self.speech_toggle.setChecked(Settings().voice_replies())
        self.voice = QPushButton("Hold to talk")
        self.voice.pressed.connect(lambda: self.listen("button"))
        self.voice.released.connect(self.release_voice)
        self.send = QPushButton("Send  ↗")
        self.send.clicked.connect(self.submit)
        row.addWidget(self.prompt, 1)
        row.addWidget(self.speech_toggle)
        row.addWidget(self.voice)
        row.addWidget(self.send)
        body.addLayout(row)
        foot = QLabel("Jarvis • Microphone opens only while activated • Actions require approval")
        foot.setObjectName("muted")
        foot.setAlignment(Qt.AlignCenter)
        body.addWidget(foot)
        outer.addWidget(main, 1)
        self.events = Events(self)
        self.events.update.connect(self.on_update, Qt.QueuedConnection)
        self.pipeline = Pipeline(self.events.update.emit)
        self.guidance = Guidance(self)
        self.companion = Companion(self)
        self.active_frame = None
        self.last_foreground = 0
        self.companion_text = ''
        self.activity = []
        self.apply_history_preference()
        exclude_from_capture(self)
        self.voice_source = None
        self.approval_dialog = None
        self.stream_started = False
        self.answer_done = False
        self.speech_failed = False
        self.escape = QShortcut(QKeySequence("Escape"), self)
        self.escape.activated.connect(self.cancel)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.poll_hotkey)
        self.bind_hotkey()
        self.timer.start()
        QApplication.instance().installEventFilter(self)

    def log_line(self, text):
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText("\n" + text)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def bind_hotkey(self):
        try:
            self.hotkey = WindowsHotkey(Settings().hotkey())
            self.state_label.setText("Ready · Hold " + Settings().hotkey())
        except (ValueError, RuntimeError):
            self.hotkey = None
            self.state_label.setText("Global shortcut unavailable; use Hold to talk or Settings")

    def configure(self):
        self.cancel()
        self.timer.stop()
        try:
            if SettingsDialog(self).exec() == QDialog.Accepted:
                self.pipeline.reset()
                self.pipeline.new_session()
                self.apply_history_preference()
                self.log_line("Session context cleared after changing settings.")
                self.speech_toggle.setChecked(Settings().voice_replies())
        finally:
            self.bind_hotkey()
            self.timer.start()

    def toggle_speech(self, enabled):
        self.speech_toggle.setText("Voice replies: ON" if enabled else "Voice replies: OFF")
        settings = Settings()
        settings.set_voice_preferences(settings.hotkey(), enabled)
        if hasattr(self, "pipeline"):
            self.cancel()

    def poll_hotkey(self):
        try:
            foreground = external_foreground()
            if foreground:
                self.last_foreground = foreground
            if self.active_frame and not self.guidance.valid(self.active_frame):
                self.active_frame = None
                self.guidance.clear()
                self.companion.sharing.setText('Screen guidance expired; share again if needed')
            if self.companion.isVisible():
                self.companion.update_state(self.state_label.text())
            if self.hotkey:
                edge = self.hotkey.poll()
                if self.hotkey.escape_down():
                    if self.pipeline.conversation.current or self.guidance.overlay:
                        self.cancel()
                    return
                if edge == "press":
                    self.listen("hotkey")
                elif edge == "release" and self.voice_source == "hotkey":
                    self.release_voice()
            if self.voice_source in ("button","companion") and not QApplication.mouseButtons() & Qt.LeftButton:
                self.release_voice()
        except Exception:
            self.cancel()
            self.hotkey = None
            self.state_label.setText("Shortcut error; use the talk button or re-save Settings")

    def eventFilter(self, obj, event):
        if obj in (self,self.companion) and event.type() == QEvent.WindowDeactivate:
            if self.voice_source in ("button","companion"):
                self.release_voice()
        return super().eventFilter(obj, event)

    def dismiss_approval(self):
        if self.approval_dialog:
            dialog = self.approval_dialog
            self.approval_dialog = None
            dialog.reject()

    def cancel(self):
        self.update_activity('Cancelled')
        self.pipeline.cancel()
        self.guidance.clear()
        self.active_frame = None
        self.companion.sharing.setText('Screen not shared')
        self.voice_source = None
        self.dismiss_approval()
        self.stream_started = False
        self.state_label.setText("Cancelled / stopping · Ready for a new request")

    def new_conversation(self):
        self.cancel()
        self.pipeline.new_session()
        self.activity.clear()
        self.log.clear()
        self.companion.answer.setText('New conversation. Hold your shortcut and ask Jarvis.')
        self.log_line("Jarvis · New conversation. Session context cleared.")
        self.state_label.setText("Ready")

    def prepare_turn(self):
        self.update_activity('Superseded')
        self.pipeline.cancel()
        self.guidance.clear()
        self.active_frame = None
        self.companion.sharing.setText('Screen not shared')
        self.companion_text = ''
        self.companion.answer.setText('Listening for your request…')
        self.dismiss_approval()
        self.stream_started = False
        self.answer_done = False
        self.speech_failed = False

    def listen(self, source="button"):
        self.prepare_turn()
        self.voice_source = source
        self.state_label.setText("Opening microphone…")
        try:
            frame,browser = self.turn_options()
        except RuntimeError as exc:
            self.voice_source = None
            self.state_label.setText(str(exc))
            return
        turn = self.pipeline.begin(spoken=self.speech_toggle.isChecked(),screen=frame,allow_browser=browser)
        self.register_activity(turn,'Voice request',browser)

    def release_voice(self):
        if self.voice_source:
            self.pipeline.release()
            self.voice_source = None
            self.state_label.setText("Transcribing…")

    def submit(self):
        prompt = self.prompt.text().strip()
        if not prompt:
            return
        self.prepare_turn()
        self.voice_source = None
        try:
            frame,browser = self.turn_options()
        except RuntimeError as exc:
            self.state_label.setText(str(exc))
            return
        self.prompt.clear()
        self.state_label.setText("Thinking…")
        turn = self.pipeline.begin(prompt, spoken=self.speech_toggle.isChecked(),screen=frame,allow_browser=browser)
        self.register_activity(turn,prompt,browser)

    @Slot(object, str, object)
    def on_update(self, turn, state, detail):
        # Signals already queued before cancellation must also be rejected here.
        if self.pipeline.conversation.current is not turn:
            return
        if turn.cancel.is_set() and state != "error":
            return
        labels = {"starting": "Opening microphone…", "listening": "Listening · release to send · Esc cancels",
                  "transcribing": "Transcribing…", "thinking": "Thinking…",
                  "speaking": "Speaking · hold to interrupt · Esc stops",
                  "idle": str(detail) or "Ready"}
        if state in labels:
            self.state_label.setText(labels[state])
            self.update_activity(state.capitalize())
        if state == "transcribing":
            self.voice_source = None
            if detail:
                self.state_label.setText("Transcribing… · " + str(detail))
        if state == "heard":
            self.update_activity('Thinking',title=detail)
            self.log_line("YOU › " + detail)
        elif state == "text":
            self.companion_text = (self.companion_text+detail)[-350:]
            self.companion.answer.setText(self.companion_text)
            if not self.stream_started:
                self.log_line("Jarvis › ")
                self.stream_started = True
            cursor = self.log.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(detail)
            self.log.setTextCursor(cursor)
            self.log.ensureCursorVisible()
        elif state in ("error", "speech_error", "notice", "action"):
            self.log_line(state.upper() + " › " + detail)
            self.stream_started = False
            if state == 'error':
                self.update_activity('Error',note=detail)
            elif state == 'action':
                self.update_activity('Working',note=detail)
            if state == "speech_error":
                self.speech_failed = True
            if state in ("error", "speech_error"):
                self.state_label.setText("Error · " + detail)
                self.voice_source = None
                self.dismiss_approval()
        elif state == "annotations":
            frame,shapes = detail
            if self.active_frame is not frame or not self.guidance.show(frame,shapes):
                self.log_line('GUIDANCE › Screen changed or expired; share a fresh screen for accurate guidance.')
        elif state == "approval":
            self.show_approval(detail)
        elif state == "approval_done":
            self.dismiss_approval()
        elif state == "answer_done":
            self.answer_done = True
            self.update_activity('Completed',note=detail[:500])
        elif state == "speech_done" and self.answer_done:
            self.state_label.setText("Ready · voice unavailable; see error above" if self.speech_failed else "Ready")

    def show_approval(self, request):
        self.update_activity('Awaiting approval')
        self.dismiss_approval()
        if not self.companion.isVisible() and (self.isMinimized() or not self.isVisible()):
            self.showNormal()
        self.state_label.setText("Awaiting your approval · expires in 60 seconds")
        dialog = QDialog(self.companion if self.companion.isVisible() else self)
        self.approval_dialog = dialog
        dialog.setWindowTitle("Jarvis · Approve action")
        layout = QVBoxLayout(dialog)
        label = QLabel("Allow this specific action once?\n" + request.name)
        layout.addWidget(label)
        details = QTextEdit()
        details.setReadOnly(True)
        details.setPlainText(json.dumps(request.arguments, indent=2, ensure_ascii=False))
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No)
        buttons.button(QDialogButtonBox.No).setDefault(True)
        buttons.button(QDialogButtonBox.Yes).setAutoDefault(False)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.finished.connect(lambda result: request.answer(result == QDialog.Accepted))
        dialog.finished.connect(dialog.deleteLater)
        dialog.finished.connect(lambda: self.clear_approval(dialog))
        dialog.show()
        exclude_from_capture(dialog)
        dialog.raise_()
        dialog.activateWindow()

    def clear_approval(self, dialog):
        if self.approval_dialog is dialog:
            self.approval_dialog = None

    def register_activity(self, turn, title, browser=False):
        if turn:
            self.activity.append({'id':turn.number,'title':title[:160],
                'kind':'Browser task' if browser else 'Conversation','state':'Starting','notes':[]})
            self.activity = self.activity[-50:]

    def update_activity(self, state, title=None, note=None):
        current = self.pipeline.conversation.current
        if not current:
            return
        item = next((x for x in reversed(self.activity) if x['id']==current.number),None)
        if item:
            if item['state'] not in ('Completed','Error','Cancelled','Superseded'):
                item['state'] = state
            if title:
                item['title'] = title[:160]
            if note:
                item['notes'].append(note[:1000])
                item['notes'] = item['notes'][-12:]

    def open_activity(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Jarvis · Activity and tasks')
        dialog.resize(650,480)
        layout = QVBoxLayout(dialog)
        info = QLabel('One supervised task at a time. Starting a new request cancels the previous one. Browser work continues while you use another app; approvals require your attention.')
        info.setWordWrap(True)
        layout.addWidget(info)
        listing = QListWidget()
        layout.addWidget(listing)
        details = QTextEdit()
        details.setReadOnly(True)
        layout.addWidget(details)
        stop = QPushButton('Stop current task')
        stop.clicked.connect(self.cancel)
        layout.addWidget(stop)
        def refresh():
            selected = listing.currentRow()
            listing.clear()
            for item in reversed(self.activity):
                row = QListWidgetItem(item['state']+' · '+item['kind']+' · '+item['title'])
                row.setData(Qt.UserRole,item['id'])
                listing.addItem(row)
            if listing.count():
                listing.setCurrentRow(min(max(0,selected),listing.count()-1))
        def show_details():
            row = listing.currentItem()
            item = next((x for x in self.activity if row and x['id']==row.data(Qt.UserRole)),None)
            details.setPlainText('\n'.join(item['notes']) if item else '')
        listing.currentRowChanged.connect(show_details)
        timer = QTimer(dialog)
        timer.setInterval(500)
        timer.timeout.connect(refresh)
        timer.start()
        refresh()
        dialog.finished.connect(timer.stop)
        dialog.finished.connect(dialog.deleteLater)
        dialog.show()
        exclude_from_capture(dialog)

    def turn_options(self):
        frame = None
        if self.screen_once.isChecked():
            if not getattr(Settings(),'image_inputs',lambda:False)():
                raise RuntimeError('In Settings, select an image-capable AI model and enable screen images first.')
            self.screen_once.setChecked(False)
            try:
                frame = capture_monitor(self.screen_choice.currentData(),self.last_foreground)
            except Exception:
                raise RuntimeError('Could not capture the selected monitor. Unlock the desktop and try again.') from None
            self.active_frame = frame
            self.companion.sharing.setText('Screenshot attached · this request only')
            self.log_line('SCREEN › Shared one monitor for this request; no image saved to disk.')
        browser = self.browser_once.isChecked()
        self.browser_once.setChecked(False)
        return frame,browser

    def toggle_companion(self):
        if self.companion.isVisible():
            self.companion.hide()
            self.showNormal()
            return
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        if screen:
            bounds = screen.availableGeometry()
            self.companion.move(bounds.right()-self.companion.width()-20,bounds.top()+28)
        self.companion.show()
        exclude_from_capture(self.companion)
        self.hide()

    def run_browser_task(self):
        if not self.prompt.text().strip():
            self.prompt.setFocus()
            self.state_label.setText('Describe the browser task, then choose Run browser task. Jarvis uses a separate Edge session.')
            return
        self.browser_once.setChecked(True)
        self.submit()
        if not self.companion.isVisible():
            self.toggle_companion()

    @staticmethod
    def history_path():
        return Path(os.getenv('LOCALAPPDATA',str(Path.home()))) / 'Jarvis' / 'conversations.sqlite3'

    def apply_history_preference(self):
        voice,rate,device = getattr(Settings(),'speech_options',lambda:('',200,-1))()
        getattr(self.pipeline.speaker,'configure',lambda *a:None)(voice,rate)
        self.pipeline.recorder.device = None if device<0 else device
        self.pipeline.history_store = None
        if getattr(Settings(),'remember_chats',lambda:False)():
            try:
                self.pipeline.history_store = HistoryStore(self.history_path())
            except Exception:
                self.log_line('HISTORY › Local history unavailable; continuing with session-only memory.')

    def open_history(self):
        store = self.pipeline.history_store
        if store is None and self.history_path().exists():
            try:
                store = HistoryStore(self.history_path())
            except Exception:
                pass
        if store is None:
            QMessageBox.information(self,'Jarvis · Conversations','Enable Remember completed chats in Settings to save local text history. Nothing has been saved by default.')
            return
        self.cancel()
        dialog = QDialog(self)
        dialog.setWindowTitle('Jarvis · Saved conversations')
        dialog.resize(540,440)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Local text history · Images/audio are never included'))
        search = QLineEdit()
        search.setPlaceholderText('Filter saved conversations…')
        layout.addWidget(search)
        entries = QListWidget()
        layout.addWidget(entries)
        try:
            sessions = store.list_sessions()
        except Exception:
            self.log_line('HISTORY › Could not read local conversations.')
            dialog.deleteLater()
            return
        for key,title,updated in sessions:
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole,key)
            entries.addItem(item)
        search.textChanged.connect(lambda text:[entries.item(i).setHidden(text.casefold() not in entries.item(i).text().casefold()) for i in range(entries.count())])
        row = QHBoxLayout()
        restore = QPushButton('Open selected')
        remove = QPushButton('Delete selected permanently')
        row.addWidget(restore)
        row.addWidget(remove)
        layout.addLayout(row)
        def open_selected():
            item = entries.currentItem()
            if not item:
                return
            try:
                messages = store.load(item.data(Qt.UserRole))
                self.pipeline.new_session(messages,item.data(Qt.UserRole))
                self.log.clear()
                for message in self.pipeline.conversation.history():
                    self.log_line(('YOU' if message['role']=='user' else 'Jarvis')+' › '+message['content'])
                dialog.accept()
            except Exception:
                self.log_line('HISTORY › Saved conversation could not be opened.')
        def delete_selected():
            item = entries.currentItem()
            if item:
                try:
                    key = item.data(Qt.UserRole)
                    store.delete(key)
                    if self.pipeline.session_id == key:
                        self.new_conversation()
                    entries.takeItem(entries.row(item))
                except Exception:
                    self.log_line('HISTORY › Saved conversation could not be deleted.')
        restore.clicked.connect(open_selected)
        remove.clicked.connect(delete_selected)
        dialog.finished.connect(dialog.deleteLater)
        dialog.show()
        exclude_from_capture(dialog)

    def closeEvent(self, event):
        self.timer.stop()
        self.dismiss_approval()
        self.pipeline.close()
        self.guidance.clear()
        self.companion.hide()
        self.companion.deleteLater()
        for dialog in self.findChildren(QDialog):
            dialog.reject()
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Jarvis")
    app.setApplicationName('Jarvis')
    folder = Path(os.getenv('LOCALAPPDATA',str(Path.home()))) / 'Jarvis'
    try:
        folder.mkdir(parents=True,exist_ok=True)
        instance_lock = QLockFile(str(folder / 'instance.lock'))
        if not instance_lock.tryLock(0):
            QMessageBox.information(None,'Jarvis','Jarvis is already running. Use its shortcut or return to its workspace.')
            return
    except OSError:
        QMessageBox.critical(None,'Jarvis','Could not open the local Jarvis application folder.')
        return
    app.aboutToQuit.connect(instance_lock.unlock)
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
