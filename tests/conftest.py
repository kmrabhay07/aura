"""Qt tests render synthetic content; never capture the user's screen."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='session')
def app():
    instance=QApplication.instance() or QApplication([])
    yield instance
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    instance.processEvents()
