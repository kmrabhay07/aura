"""Compact Jarvis companion, sharing the existing window/controller."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QCheckBox, QFrame
from .desktop import exclude_from_capture


class DragTitle(QLabel):
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.offset=event.globalPosition().toPoint()-self.window().pos()
            event.accept()

    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.LeftButton and hasattr(self,'offset'):
            self.window().move(event.globalPosition().toPoint()-self.offset)
            event.accept()


class Companion(QWidget):
    def __init__(self, owner):
        super().__init__(None,Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.owner = owner
        self.setWindowTitle('Jarvis')
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(390)
        self.setStyleSheet('''QWidget {font-family:Segoe UI;color:#ede8ff;font-size:13px;}
            QFrame#card {background:#141321;border:1px solid #695582;border-radius:16px;}
            QLabel {background:transparent;border:0;}
            QPushButton {background:#b299f5;color:#161020;border:0;border-radius:9px;padding:9px;}
            QLineEdit {background:#232033;border:1px solid #514361;border-radius:8px;padding:10px;}
            QCheckBox {background:transparent;}
            QCheckBox::indicator {width:16px;height:16px;border:1px solid #8c7caa;border-radius:4px;background:#232033;}
            QCheckBox::indicator:checked {background:#b299f5;border:1px solid #e2d6ff;}''')
        outside = QVBoxLayout(self)
        outside.setContentsMargins(0,0,0,0)
        card = QFrame()
        card.setObjectName('card')
        outside.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16,16,16,16)
        title_row = QHBoxLayout()
        title = DragTitle('Jarvis')
        title.setToolTip('Drag to move Jarvis')
        title.setStyleSheet('font-size:20px;font-weight:700;')
        title_row.addWidget(title,1)
        expand = QPushButton('Workspace')
        expand.clicked.connect(self.expand)
        title_row.addWidget(expand)
        hide = QPushButton('Close')
        hide.clicked.connect(self.expand)
        title_row.addWidget(hide)
        layout.addLayout(title_row)
        self.status = QLabel('Ready')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.sharing = QLabel('Screen not shared')
        self.sharing.setStyleSheet('color:#c7b8e3;font-size:12px;')
        self.sharing.setWordWrap(True)
        layout.addWidget(self.sharing)
        self.answer = QLabel('Hold your shortcut and ask Jarvis.')
        self.answer.setWordWrap(True)
        self.answer.setTextFormat(Qt.PlainText)
        self.answer.setMinimumHeight(50)
        self.answer.setMaximumHeight(140)
        layout.addWidget(self.answer)
        self.screen = QCheckBox('Include selected screen once')
        self.screen.setToolTip('Sends a screenshot to your configured AI provider for the next request only.')
        self.screen.toggled.connect(owner.screen_once.setChecked)
        owner.screen_once.toggled.connect(self.screen.setChecked)
        layout.addWidget(self.screen)
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText('Ask Jarvis…')
        self.prompt.returnPressed.connect(self.submit)
        layout.addWidget(self.prompt)
        row = QHBoxLayout()
        hold = QPushButton('Hold to talk')
        hold.pressed.connect(lambda: owner.listen('companion'))
        hold.released.connect(owner.release_voice)
        row.addWidget(hold)
        stop = QPushButton('Stop / clear')
        stop.clicked.connect(owner.cancel)
        row.addWidget(stop)
        row.addWidget(QLabel('Esc stops'))
        layout.addLayout(row)
        self.adjustSize()
        exclude_from_capture(self)

    def submit(self):
        self.owner.prompt.setText(self.prompt.text())
        self.prompt.clear()
        self.owner.submit()

    def expand(self):
        self.owner.showNormal()
        self.owner.raise_()
        self.owner.activateWindow()
        self.hide()

    def update_state(self, text):
        if self.status.text()!=text:
            self.status.setText(text)
            self.adjustSize()

    def closeEvent(self, event):
        self.expand()
        event.ignore()
