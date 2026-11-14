"""Qt capture and non-interactive screen annotations. Must run on the GUI thread."""
import math
import os
import sys
import time

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .screen import ScreenFrame, validate_shapes


def external_foreground():
    if sys.platform != 'win32' or QGuiApplication.platformName() == 'offscreen':
        return 0
    import ctypes
    from ctypes import wintypes
    api = ctypes.windll.user32
    api.GetForegroundWindow.restype = wintypes.HWND
    api.GetWindowThreadProcessId.argtypes = (wintypes.HWND,ctypes.POINTER(wintypes.DWORD))
    api.GetWindowThreadProcessId.restype = wintypes.DWORD
    hwnd = api.GetForegroundWindow()
    pid = wintypes.DWORD()
    api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(hwnd or 0) if pid.value != os.getpid() else 0


def window_rectangle(hwnd):
    if not hwnd or sys.platform!='win32' or QGuiApplication.platformName()=='offscreen':
        return ()
    import ctypes
    from ctypes import wintypes
    rect=wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd),ctypes.byref(rect)):
        return ()
    return (rect.left,rect.top,rect.right,rect.bottom)


def exclude_from_capture(widget):
    if sys.platform != 'win32' or QGuiApplication.platformName() == 'offscreen':
        return False
    import ctypes
    from ctypes import wintypes
    api = ctypes.windll.user32
    api.SetWindowDisplayAffinity.argtypes = (wintypes.HWND,wintypes.DWORD)
    api.SetWindowDisplayAffinity.restype = wintypes.BOOL
    return bool(api.SetWindowDisplayAffinity(int(widget.winId()),0x11))


def capture_monitor(screen_name='', foreground=0):
    screens = QGuiApplication.screens()
    screen = next((s for s in screens if s.name()==screen_name),None) if screen_name else QGuiApplication.screenAt(QCursor.pos())
    screen = screen or QGuiApplication.primaryScreen()
    if screen is None:
        raise RuntimeError('No display available')
    pixmap = screen.grabWindow(0)
    if pixmap.isNull():
        raise RuntimeError('Screen capture unavailable; unlock your desktop and try again')
    image = pixmap.toImage()
    image.setDevicePixelRatio(1)
    if image.width()>1600 or image.height()>1600:
        image = image.scaled(1600,1600,Qt.KeepAspectRatio,Qt.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer,'JPEG',80):
        raise RuntimeError('Unable to encode the selected screen')
    buffer.close()
    geometry = screen.geometry()
    return ScreenFrame(bytes(data),screen.name(),
        (geometry.x(),geometry.y(),geometry.width(),geometry.height()),
        (image.width(),image.height()),foreground=foreground,window_rect=window_rectangle(foreground))


class GuidanceOverlay(QWidget):
    def __init__(self, frame, shapes):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle('Jarvis · Visual guidance')
        self.frame = frame
        self.shapes = validate_shapes({'shapes':shapes})
        self.setGeometry(*frame.geometry)
        exclude_from_capture(self)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor('#b99aff')
        painter.setPen(QPen(color,3))
        for shape in self.shapes:
            a = QPointF(shape['x']*self.width(),shape['y']*self.height())
            b = QPointF(shape['x2']*self.width(),shape['y2']*self.height())
            rect = QRectF(a,b).normalized()
            if shape['kind'] == 'arrow':
                painter.drawLine(a,b)
                angle = math.atan2(b.y()-a.y(),b.x()-a.x())
                head = [b,QPointF(b.x()-16*math.cos(angle-.5),b.y()-16*math.sin(angle-.5)),
                        QPointF(b.x()-16*math.cos(angle+.5),b.y()-16*math.sin(angle+.5))]
                painter.setBrush(color)
                painter.drawPolygon(QPolygonF(head))
                painter.setBrush(Qt.NoBrush)
            elif shape['kind'] == 'circle':
                painter.drawEllipse(rect)
            else:
                painter.drawRoundedRect(rect,6,6)
            if shape['label']:
                label = shape['label'].replace('\n',' ')
                width = min(self.width()-16,painter.fontMetrics().horizontalAdvance(label)+20)
                x = max(8,min(a.x(),self.width()-width-8))
                y = max(8,min(a.y()-34,self.height()-34))
                label_rect = QRectF(x,y,width,28)
                painter.fillRect(label_rect,QColor('#181221'))
                painter.drawText(label_rect,Qt.AlignCenter,label)
        painter.end()


class Guidance:
    def __init__(self, parent=None):
        self.overlay = None
        self.timer = QTimer(parent)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.check)

    def show(self, frame, shapes):
        self.clear()
        if not self.valid(frame):
            return False
        self.overlay = GuidanceOverlay(frame,shapes)
        self.overlay.show()
        self.timer.start()
        return True

    def valid(self, frame):
        screen = next((s for s in QGuiApplication.screens() if s.name()==frame.screen_name),None)
        if not screen:
            return False
        r = screen.geometry()
        return frame.fresh((r.x(),r.y(),r.width(),r.height()), external_foreground(),
                           window_rect=window_rectangle(frame.foreground))

    def check(self):
        if self.overlay and not self.valid(self.overlay.frame):
            self.clear()

    def clear(self):
        self.timer.stop()
        if self.overlay:
            self.overlay.close()
            self.overlay.deleteLater()
            self.overlay = None
