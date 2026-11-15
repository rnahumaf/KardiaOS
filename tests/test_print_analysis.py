import io,time
import pytest
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication
from kardiaos.automatic_analysis import automatic_analysis,Cancelled
from kardiaos.report import page_plan,pdf_bytes
from kardiaos.preview import PrintPreview
from test_measurements import signal_record
from test_automatic_analysis import fake_infer
from test_analysis_dialog import wait

def test_one_sheet_has_same_window_top_three_without_scores_or_raw_qt():
    r=signal_record();a=automatic_analysis(r,infer=fake_infer);plan=page_plan(r,layout='di',analysis=a)
    assert len(plan['rows'])==2 and plan['end']-plan['start']==10
    text=PdfReader(io.BytesIO(pdf_bytes(r,layout='di',analysis=a))).pages[0].extract_text()
    for term in ['FC: 60 bpm','P:','QRS:','global; Fridericia','PR prolongado; possível atraso de condução AV']:assert term in text
    assert 'QT:' not in text and '0.2500' not in text
    assert not a['scenarios']
    assert a['classification']['summary'] in text

def test_short_blocked_and_poor_quality_trace_only():
    r=signal_record(seconds=4);a=automatic_analysis(r,infer=fake_infer)
    with pytest.raises(ValueError,match='10 s'):pdf_bytes(r,analysis=a)
    r=signal_record(noise=.7);a=automatic_analysis(r,infer=fake_infer);text=PdfReader(io.BytesIO(pdf_bytes(r,analysis=a,gain=5))).pages[0].extract_text()
    assert 'Somente traçado' in text
    for term in ['QTc:','FC:','Hipóteses','QRS:']:assert term not in text

def test_preview_automatically_runs_caches_and_cancels(monkeypatch):
    app=QApplication.instance();monkeypatch.setattr('kardiaos.analysis_dialog.automatic_analysis',lambda r,emit,cancel,**kw:automatic_analysis(r,emit,cancel,fake_infer,**kw))
    r=signal_record();p=PrintPreview(r);assert not p.save_button.isEnabled()
    wait(app,lambda:p.analysis['status']=='completed' and not p.thread.isRunning(),seconds=20)
    assert p.save_button.isEnabled() and p.analysis is r._automatic_analysis;p.close();p=PrintPreview(r)
    assert p.thread is None and p.save_button.isEnabled();p.close()
    def slow(key,values,cancel):
        while not cancel():time.sleep(.01)
        raise Cancelled()
    monkeypatch.setattr('kardiaos.analysis_dialog.automatic_analysis',lambda r,emit,cancel,**kw:automatic_analysis(r,emit,cancel,slow,include_models=True,**kw))
    p=PrintPreview(signal_record());p.show();app.processEvents();p.reject()
    wait(app,lambda:not p.thread.isRunning() and not p.isVisible(),seconds=20);assert p.analysis['status']=='cancelled'

def test_changed_amplitude_or_signal_never_reuses_stale_analysis():
    from kardiaos.automatic_analysis import cache_analysis
    r=signal_record();cache_analysis(r,automatic_analysis(r,infer=fake_infer));r.meta['mv_per_count']*=2
    p=PrintPreview(r,autostart=False);assert p.analysis['status']=='running' and not p.save_button.isEnabled();p.close()
