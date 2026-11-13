"""One QApplication owns Qt objects for the whole offscreen test session."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='session',autouse=True)
def qt_application():
    # Local QApplication references in individual tests can disappear while other
    # tests still own widgets/deferred events. Keep its lifetime deterministic.
    app=QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    yield app
    app.processEvents()
    for widget in app.topLevelWidgets():widget.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    app.processEvents()
