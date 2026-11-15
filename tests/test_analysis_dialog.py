import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import time
from PySide6.QtWidgets import QApplication
from kardiaos.analysis_dialog import AutomaticAnalysisDialog
from kardiaos.automatic_analysis import automatic_analysis,Cancelled
from test_measurements import signal_record
from test_automatic_analysis import fake_infer


def wait(app,condition,seconds=20):
    deadline=time.monotonic()+seconds
    while not condition() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert condition()


def test_headless_dialog_repeat_and_close_cancel(monkeypatch,tmp_path):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('kardiaos.analysis_dialog.automatic_analysis',lambda r,emit,cancel:automatic_analysis(r,emit,cancel,fake_infer))
    dialog=AutomaticAnalysisDialog(signal_record(),autostart=False)
    dialog.resize(850,650);dialog.show();app.processEvents();dialog.start()
    wait(app,lambda:dialog.result is not None and not dialog.busy())
    assert dialog.measure_table.rowCount()==6 and dialog.score_table.rowCount()>=17
    assert dialog.rect().contains(dialog.export_button.geometry())
    dialog.tabs.setCurrentIndex(1);app.processEvents()
    assert dialog.grab().save(str(tmp_path/'synthetic-analysis.png'))
    dialog.start();wait(app,lambda:dialog.result is not None and not dialog.busy())
    assert dialog.score_table.rowCount()>=17
    dialog.reject();assert not dialog.isVisible()
    def slow(key,values,cancel):
        while not cancel():time.sleep(.01)
        raise Cancelled()
    monkeypatch.setattr('kardiaos.analysis_dialog.automatic_analysis',lambda r,emit,cancel:automatic_analysis(r,emit,cancel,slow,include_models=True))
    dialog=AutomaticAnalysisDialog(signal_record(),autostart=False);dialog.show();dialog.start()
    app.processEvents();dialog.reject()
    wait(app,lambda:not dialog.busy() and not dialog.isVisible())
    assert dialog.result['status']=='cancelled'
