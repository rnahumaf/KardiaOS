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


@pytest.fixture(autouse=True)
def isolate_qt_worker_and_clean_widgets(monkeypatch,qt_application):
    """Unit tests substitute only the subprocess. Packaged smokes run real weights."""
    from kardiaos.qt_client import WEIGHT_SHA256
    from PySide6.QtCore import QThread
    def unavailable(x,cancelled):
        return dict(checkpoint_sha256=WEIGHT_SHA256,leads=[dict(metrics={},beats=[]) for _ in range(x.shape[1])])
    monkeypatch.setattr('kardiaos.qt_client.infer_qt',unavailable)
    yield
    # A failed assertion must not leave a running QThread for Python GC to destroy.
    widgets=list(qt_application.topLevelWidgets())
    for widget in widgets:
        for worker in widget.findChildren(QThread):
            if worker.isRunning():worker.requestInterruption();worker.wait(15000)
    qt_application.processEvents()
    for widget in widgets:
        if hasattr(widget,'dirty'):widget.dirty=False
        widget.close()
    qt_application.processEvents()
