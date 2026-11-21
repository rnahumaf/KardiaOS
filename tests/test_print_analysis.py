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

def test_one_sheet_has_patient_timestamp_and_metrics_without_scores_or_raw_qt():
    r=signal_record()
    r.meta.update(patient_name='Paciente Teste da Conceição', recorded_at='2025-03-04T14:27:01-03:00')
    a=automatic_analysis(r,infer=fake_infer);plan=page_plan(r,layout='di',analysis=a)
    assert len(plan['rows'])==6 and plan['end']-plan['start']==pytest.approx(30)
    text=PdfReader(io.BytesIO(pdf_bytes(r,layout='di',analysis=a))).pages[0].extract_text()
    assert 'Paciente: Paciente Teste da Conceição' in text
    assert 'Gravado em 04/03/2025 14:27:01' in text
    assert 'DI 0.000–30.000 s' in text
    offset = a['report_window']['offset_seconds']
    assert f'Janela automática {offset:.3f}–{offset+10:.3f} s' in text
    metrics = next(line for line in text.splitlines() if 'FC: 60 bpm' in line)
    for term in ('P:', 'QRS:', 'QTcF:', 'Fridericia'):
        assert term in metrics
    assert 'PR prolongado; possível atraso de condução AV' in text
    assert 'QTc:' not in text and 'QT:' not in text and '0.2500' not in text
    assert not a['scenarios']
    assert a['classification']['summary'] in text


def test_long_di_keeps_late_automatic_window_and_median_on_the_page():
    r = signal_record(seconds=81)
    r.review_as_di = True
    a = automatic_analysis(r, infer=fake_infer, offset=70, duration=10)
    plan = page_plan(r, speed=50, analysis=a)
    assert plan['layout'] == 'di' and len(plan['rows']) == 6
    assert plan['first'] < a['report_window']['first_sample']
    assert plan['last'] == a['report_window']['last_sample_exclusive'] == r.n
    assert plan['end']-plan['start'] > 30 and plan['remaining_seconds'] > 0
    last = plan['rows'][-1]
    assert last['template'] == a['representative']['I'] and last['template_side'] >= 48
    assert last['template_x'] + last['template_side'] <= plan['content_bounds'][2]
    for row in plan['rows'][:-1]:
        assert not row['template']
        if row['top'] - row['h'] < last['template_bottom'] + last['template_side']:
            assert row['data_x'] + row['duration']*50 < last['template_x']

def test_short_blocked_and_poor_quality_trace_only():
    r=signal_record(seconds=4);a=automatic_analysis(r,infer=fake_infer)
    with pytest.raises(ValueError,match='10 s'):pdf_bytes(r,analysis=a)
    r=signal_record(noise=.7);r.meta['created']='2025-03-04T14:27:01-03:00'
    a=automatic_analysis(r,infer=fake_infer);text=PdfReader(io.BytesIO(pdf_bytes(r,analysis=a,gain=5))).pages[0].extract_text()
    assert 'Somente traçado' in text
    assert 'Gravado em 04/03/2025 14:27:01' in text and 'Paciente:' not in text
    for term in ['QTcF:','FC:','Hipóteses','QRS:']:assert term not in text

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
