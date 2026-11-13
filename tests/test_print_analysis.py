import io,os,time
os.environ['QT_QPA_PLATFORM']='offscreen'
import pytest
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication
from kardiaos.automatic_analysis import automatic_analysis,Cancelled
from kardiaos.report import page_plan,pdf_bytes
from kardiaos.preview import PrintPreview
from test_measurements import signal_record
from test_automatic_analysis import fake_infer
from test_analysis_dialog import wait

def test_one_sheet_contains_measures_and_every_model_sign_scenario():
    r=signal_record();a=automatic_analysis(r,infer=fake_infer)
    plan=page_plan(r,layout='di',analysis=a)
    assert len(plan['rows'])==3 and plan['remaining_seconds']==pytest.approx(0)
    assert min(v['top']-v['h'] for v in plan['rows'])>=80
    pdf=PdfReader(io.BytesIO(pdf_bytes(r,layout='di',analysis=a)))
    assert len(pdf.pages)==1
    text=pdf.pages[0].extract_text()
    for term in ['FC: 60 bpm','P:','QRS:','QTcF:','Fridericia','nao sao probabilidades','ECGFounder 1L','DeepPSP 2L','DeepPSP 6L']:
        assert term in text
    assert text.count('ECGFounder 1L |')==1
    assert text.count('DeepPSP 2L |')==1
    assert text.count('DeepPSP 6L |')==1

def test_print_unavailable_has_reason_and_never_fabricates_score():
    r=signal_record(seconds=4);a=automatic_analysis(r,infer=fake_infer)
    text=PdfReader(io.BytesIO(pdf_bytes(r,layout='di',analysis=a))).pages[0].extract_text()
    assert 'FC: indisponivel' in text and 'Motivo:' in text
    assert 'Indisponivel:' in text

def test_preview_automatically_runs_caches_and_cancels(monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('kardiaos.analysis_dialog.automatic_analysis',lambda r,emit,cancel:automatic_analysis(r,emit,cancel,fake_infer))
    r=signal_record();p=PrintPreview(r)
    assert not p.save_button.isEnabled()
    wait(app,lambda:p.analysis['status']=='completed' and not p.thread.isRunning())
    assert p.save_button.isEnabled() and p.analysis is r._automatic_analysis
    p.close();p=PrintPreview(r)
    assert p.thread is None and p.save_button.isEnabled();p.close()
    def slow(key,values,cancel):
        while not cancel():time.sleep(.01)
        raise Cancelled()
    monkeypatch.setattr('kardiaos.analysis_dialog.automatic_analysis',lambda r,emit,cancel:automatic_analysis(r,emit,cancel,slow))
    p=PrintPreview(signal_record());p.show();app.processEvents();p.reject()
    wait(app,lambda:not p.thread.isRunning() and not p.isVisible())
    assert p.analysis['status']=='cancelled'


def test_changed_amplitude_or_signal_never_reuses_stale_analysis():
    from kardiaos.automatic_analysis import analysis_key
    app=QApplication.instance() or QApplication([])
    r=signal_record();r._automatic_analysis=automatic_analysis(r,infer=fake_infer)
    r._automatic_analysis_key=analysis_key(r)
    r.meta['mv_per_count']*=2
    p=PrintPreview(r,autostart=False)
    assert p.analysis['status']=='running' and not p.save_button.isEnabled();p.close()
    r._automatic_analysis_key=analysis_key(r);r.raw[900,0]+=4
    p=PrintPreview(r,autostart=False)
    assert p.analysis['status']=='running' and not p.save_button.isEnabled();p.close()
