"""Synthetic end-to-end UI flows: no private captures or physical print jobs."""
import time
import numpy as np
from PySide6.QtCore import QSettings,QTimer
from PySide6.QtWidgets import QApplication
from kardiaos.app import Window,synthetic_pairs
from kardiaos.recording import save_recording
from kardiaos.automatic_analysis import automatic_analysis,analysis_key,cached_analysis
from kardiaos.analysis_dialog import AutomaticAnalysisDialog
from kardiaos.signal import FilterConfig
from test_measurements import signal_record
from test_analysis_dialog import wait


def window(tmp_path):
    w=Window(settings=QSettings(str(tmp_path/'settings.ini'),QSettings.Format.IniFormat));w.tick_timer.stop();w.show()
    return w


def attach(w,r):
    w.recording=w.paper.recording=r;w.paper.cursor=r.last_time;w.paper.overlay='';w.sync_clinical_context();w.update_buttons()


def no_preview(monkeypatch):
    def forbidden(*args,**kw):raise AssertionError('Preview opened without an explicit Print action')
    monkeypatch.setattr('kardiaos.preview.PrintPreview',forbidden)


def test_context_changes_debounce_recompute_and_keep_raw(tmp_path,monkeypatch):
    app=QApplication.instance();w=window(tmp_path);r=signal_record(noise=.025);attach(w,r);no_preview(monkeypatch)
    w.start_background_analysis();wait(app,lambda:cached_analysis(r) is not None and not w._analysis_thread.isRunning())
    old=analysis_key(r);before=r.raw[:r.n].copy()
    w.age.setValue(37);w.sex.setCurrentIndex(w.sex.findData('male'))
    assert w.measure_values['qrs_duration'].text()=='—' and w._analysis_timer.isActive()
    wait(app,lambda:cached_analysis(r) is not None and not w._analysis_thread.isRunning() and not w._analysis_timer.isActive())
    assert analysis_key(r)!=old and r.meta['clinical_context']==dict(age_years=37,sex='male')
    assert w.measure_values['heart_rate'].text()=='60 bpm'
    assert w.analysis_summary.text()=='Sinusal, regular, normal nos critérios avaliados'
    assert w.dirty;np.testing.assert_array_equal(before,r.raw[:r.n])
    w.sex.setCurrentIndex(0)
    wait(app,lambda:cached_analysis(r) is not None and not w._analysis_thread.isRunning() and not w._analysis_timer.isActive())
    assert 'normal nos critérios avaliados' in w.analysis_summary.text()
    assert not w.analysis_pending.text() and not w.analysis_pending.isVisible()
    assert any('Sexo não informado' in text for rule in cached_analysis(r)['classification']['rules'] for text in rule['limitations'])
    w.dirty=False;w.close()


def test_visual_changes_keep_measures_and_change_only_display(tmp_path,monkeypatch):
    app=QApplication.instance();w=window(tmp_path);r=signal_record(noise=.05);attach(w,r);no_preview(monkeypatch)
    a=automatic_analysis(r);w.background_result(r,a);before=r.raw[:r.n].copy();metadata=repr(r.meta);key=analysis_key(r)
    w.apply_filters(FilterConfig(.5,80,60));first=w.paper.display_values(300,3300).copy()
    w.smooth.setCurrentIndex(w.smooth.findData(25));w.speed.setCurrentIndex(1);w.gain.setCurrentIndex(2);w.raw_check.setChecked(True);app.processEvents()
    assert not w._analysis_timer.isActive() and w.paper.current_analysis() is a and cached_analysis(r) is a
    assert analysis_key(r)==key and repr(r.meta)==metadata
    w.raw_check.setChecked(False);second=w.paper.display_values(300,3300)
    assert not np.allclose(first,second,equal_nan=True)
    np.testing.assert_array_equal(before,r.raw[:r.n]);w.dirty=False;w.close()


def test_capture_completion_and_loading_stay_on_main_screen(tmp_path,monkeypatch):
    app=QApplication.instance();w=window(tmp_path);w.demo=True;no_preview(monkeypatch);w.start()
    began=time.monotonic()-12
    for i in range(0,3600,9):w.accept_samples(began+i/300,synthetic_pairs(i,9))
    w.stop();wait(app,lambda:cached_analysis(w.recording) is not None and not w._analysis_thread.isRunning())
    assert w.isVisible() and w.measure_panel.isVisible()
    r=signal_record();r.meta['clinical_context']=dict(age_years=55,sex='female');path=tmp_path/'synthetic.kardia';save_recording(path,r)
    w.dirty=False;monkeypatch.setattr('kardiaos.app.QFileDialog.getOpenFileName',lambda *a,**k:(str(path),''))
    w.open_button.click();wait(app,lambda:cached_analysis(w.recording) is not None and not w._analysis_thread.isRunning() and not w._analysis_timer.isActive())
    assert w.age.value()==55 and w.sex.currentData()=='female'
    assert w.measure_values['pr'].text()!='—' and w.isVisible()
    w.dirty=False;w.close()


def test_pdf_export_is_direct_and_preview_is_print_only(tmp_path,monkeypatch):
    app=QApplication.instance();w=window(tmp_path);r=signal_record();attach(w,r);w.background_result(r,automatic_analysis(r))
    no_preview(monkeypatch);target=tmp_path/'synthetic.pdf'
    monkeypatch.setattr('kardiaos.app.QFileDialog.getSaveFileName',lambda *a,**k:(str(target),''))
    w.pdf_button.click();assert target.read_bytes().startswith(b'%PDF')
    from kardiaos.preview import PrintPreview as ignored
    calls=[]
    class Explicit:
        def __init__(self,*args,**kw):calls.append(args)
        def exec(self):calls.append('shown')
    monkeypatch.setattr('kardiaos.preview.PrintPreview',Explicit)
    w.print_button.click();assert len(calls)==2 and calls[-1]=='shown'
    w.dirty=False;w.close()


def test_details_summary_measures_curves_and_expandable_criteria(tmp_path):
    app=QApplication.instance();w=window(tmp_path);r=signal_record();attach(w,r)
    d=AutomaticAnalysisDialog(r,w,autostart=False);d.resize(850,650);d.show()
    assert not d.lead_selector.isEnabled() and not d.export_button.isEnabled()
    d.start()
    wait(app,lambda:d.result is not None and not d.busy())
    assert d.tabs.currentIndex()==0 and not d.technical_body.isVisible()
    assert d.lead_selector.isEnabled() and d.export_button.isEnabled()
    assert not d.pending_label.isVisible()
    assert d.limitations_label.isVisible() and 'Idade não informada' in d.limitations_label.text()
    assert w.paper.analysis is d.result and w.measure_values['heart_rate'].text()=='60 bpm'
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    d.criteria_toggle.setFocus();QTest.keyClick(d.criteria_toggle,Qt.Key.Key_Space);app.processEvents()
    assert d.technical_body.isVisible() and d.criteria_toggle.isChecked()
    d.tabs.setCurrentIndex(1);app.processEvents();assert d.measure_table.rowCount()==6 and d.feature_table.rowCount()==6
    d.tabs.setCurrentIndex(2);d.lead_selector.setCurrentIndex(5);app.processEvents()
    assert d.timing_plot.isVisible() and d.lead_selector.currentIndex()==5
    assert d.export_button.isVisible();d.close();w.dirty=False;w.close()


def test_intense_smoothing_is_default_and_explicit_preference_persists(tmp_path):
    w=window(tmp_path);assert w.smooth.currentData()==25
    w.smooth.setCurrentIndex(w.smooth.findData(80));w.close()
    w=window(tmp_path);assert w.smooth.currentData()==80;w.close()

