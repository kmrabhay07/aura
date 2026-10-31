import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QLineEdit, QPushButton, QFrame

from .agent import AuraAgent
from .voice import transcribe_once

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

class Worker(QObject):
    done = Signal(str)
    progress = Signal(str)

    def __init__(self, prompt):
        super().__init__()
        self.prompt = prompt

    @Slot()
    def run(self):
        try:
            result = AuraAgent().run(self.prompt, self.progress.emit)
        except Exception as exc:
            result = f"Unable to complete: {exc}"
        self.done.emit(result)

class VoiceWorker(QObject):
    done = Signal(str)
    error = Signal(str)

    @Slot()
    def run(self):
        try:
            self.done.emit(transcribe_once())
        except Exception as exc:
            self.error.emit(str(exc))

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AURA — Desktop Intelligence")
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
        brand = QLabel("✦  AURA")
        brand.setObjectName("brand")
        side.addWidget(brand)
        side.addSpacing(35)
        for item in ["◈   Workspace", "◷   Activity", "⚙   Settings"]:
            label = QLabel(item)
            label.setStyleSheet("color:#b5b9cb; padding:13px 7px;")
            side.addWidget(label)
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
        desc = QLabel("One command. Multiple actions. Your desktop, orchestrated.")
        desc.setObjectName("muted")
        body.addWidget(desc)
        body.addSpacing(12)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlainText("AURA is ready. Try: Open Apple Music or Search for Python tutorials.\n\nGrok API key required for AI commands.")
        body.addWidget(self.log, 1)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText("Ask AURA to do something...")
        self.prompt.returnPressed.connect(self.submit)
        self.voice = QPushButton("🎙 Speak")
        self.voice.clicked.connect(self.listen)
        self.send = QPushButton("Execute  ↗")
        self.send.clicked.connect(self.submit)
        row.addWidget(self.prompt, 1)
        row.addWidget(self.voice)
        row.addWidget(self.send)
        body.addLayout(row)
        foot = QLabel("AURA  /  GROK-POWERED  •  Actions are logged in this session")
        foot.setObjectName("muted")
        foot.setAlignment(Qt.AlignCenter)
        body.addWidget(foot)
        outer.addWidget(main, 1)

    def listen(self):
        self.voice.setEnabled(False)
        self.log.append("\\nVOICE  ›  Listening for 6 seconds...")
        self.voice_thread = QThread()
        self.voice_worker = VoiceWorker()
        self.voice_worker.moveToThread(self.voice_thread)
        self.voice_thread.started.connect(self.voice_worker.run)
        self.voice_worker.done.connect(self.heard)
        self.voice_worker.error.connect(lambda error: self.log.append("VOICE ERROR  ›  " + error))
        self.voice_worker.done.connect(self.voice_thread.quit)
        self.voice_worker.error.connect(self.voice_thread.quit)
        self.voice_thread.finished.connect(lambda: self.voice.setEnabled(True))
        self.voice_thread.finished.connect(self.voice_worker.deleteLater)
        self.voice_thread.finished.connect(self.voice_thread.deleteLater)
        self.voice_thread.start()

    def heard(self, text):
        if text:
            self.prompt.setText(text)
            self.submit()
        else:
            self.log.append("VOICE  ›  No speech detected.")

    def submit(self):
        prompt = self.prompt.text().strip()
        if not prompt or not self.send.isEnabled():
            return
        self.log.append(f"\nYOU  ›  {prompt}\n")
        self.prompt.clear()
        self.send.setEnabled(False)
        self.thread = QThread()
        self.worker = Worker(prompt)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(lambda s: self.log.append("ACTION  ›  " + s))
        self.worker.done.connect(self.finished)
        self.worker.done.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def finished(self, result):
        self.log.append("\nAURA  ›  " + result + "\n")
        self.send.setEnabled(True)

def main():
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
